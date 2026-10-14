"""Native Ollama transport; uses the shared Completion and authorized ToolRegistry.

Only the deployment's exact private origins bypass the shared SSRF guard.
No redirects, model pulls, global capability cache, or conversation persistence.
"""
import asyncio
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from ..config import get_settings
from .ai import Completion
from .tools.http_exec import _blocked_reason
from .tools.registry import ToolRegistry
from .tools.specs import ToolSpec


def default_base_url() -> str:
    value = get_settings().ollama_base_url or (
        "http://host.docker.internal:11434" if Path("/.dockerenv").exists() else "http://localhost:11434"
    )
    return normalize_url(value)


def normalize_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
                or any(c.isspace() for c in value) or "\\" in value):
            raise ValueError()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        host = parsed.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        return f"{parsed.scheme}://{host}:{port}"
    except ValueError:
        raise HTTPException(422, "ollama.invalid_url") from None


def validate_url(value: str) -> str:
    url = normalize_url(value)
    allowed = {normalize_url(item) for item in get_settings().ollama_allowed_private_origins}
    if url not in allowed:
        reason = _blocked_reason(url, allow_private=False)
        if reason:
            code = "host_unavailable" if "resolve host" in reason else "url_blocked"
            raise HTTPException(422, f"ollama.{code}")
    return url


async def checked_url(value: str) -> str:
    # Bound DNS validation as well as HTTP; never block the ASGI event loop.
    try:
        async with asyncio.timeout(5):
            return await asyncio.to_thread(validate_url, value)
    except TimeoutError:
        raise HTTPException(504, "ollama.timeout") from None


def _headers(api_key: str) -> dict[str, str]:
    # Optional proxy bearer authentication uses the existing encrypted credential.
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def _request(base_url: str, api_key: str, method: str, path: str, payload: dict | None = None,
                   *, generation: bool = False) -> dict:
    seconds = get_settings().ollama_timeout_seconds if generation else 15
    try:
        # An absolute deadline also bounds servers that drip response bytes forever.
        async with asyncio.timeout(seconds):
            url = await checked_url(base_url)
            async with httpx.AsyncClient(timeout=httpx.Timeout(seconds, connect=5),
                                         follow_redirects=False, trust_env=False) as client:
                response = await client.request(method, url + path, headers=_headers(api_key), json=payload)
        if response.status_code == 404 and path in {"/api/show", "/api/chat"}:
            raise HTTPException(422, "ollama.model_missing")
        if response.status_code >= 300:
            raise HTTPException(502, "ollama.server_error")
        data = response.json()
        if not isinstance(data, dict) or "error" in data:
            raise ValueError()
        return data
    except (TimeoutError, httpx.TimeoutException):
        raise HTTPException(504, "ollama.timeout") from None
    except httpx.ConnectError:
        raise HTTPException(502, "ollama.connection_refused") from None
    except httpx.HTTPError:
        raise HTTPException(502, "ollama.unavailable") from None
    except ValueError:
        raise HTTPException(502, "ollama.invalid_response") from None


def adapt_messages(messages: list[dict]) -> list[dict]:
    result = []
    for message in messages:
        if message.get("role") not in {"system", "user", "assistant"} or not isinstance(message.get("content"), str):
            raise HTTPException(422, "ollama.unsupported_message")
        result.append({"role": message["role"], "content": message["content"]})
    return result


class OllamaProvider:
    id = "ollama"

    def capabilities(self, model: str):
        from .model_providers import ModelCapabilities
        # A model name is insufficient: different agencies can host different builds.
        return ModelCapabilities(None, None)

    async def model_capabilities(self, base_url: str, api_key: str, model: str):
        from .model_providers import ModelCapabilities
        data = await _request(base_url, api_key, "POST", "/api/show", {"model": model})
        capabilities = data.get("capabilities")
        if capabilities is None:
            return self.capabilities(model)
        if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
            raise HTTPException(502, "ollama.invalid_response")
        return ModelCapabilities("tools" in capabilities, "vision" in capabilities)

    async def list_models(self, base_url: str, api_key: str) -> list[str]:
        data = await _request(base_url, api_key, "GET", "/api/tags")
        rows = data.get("models")
        if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get("name"), str)
                                            or not row["name"].strip() for row in rows):
            raise HTTPException(502, "ollama.invalid_response")
        return sorted({row["name"] for row in rows})

    async def test_connection(self, base_url: str, api_key: str = "") -> dict:
        models = await self.list_models(base_url, api_key)
        return {"ok": True, "message": "ollama.connected", "models": models}

    async def chat(self, base_url: str, api_key: str, model: str, messages: list[dict], *,
                   tools: list[ToolSpec] | None = None, temperature: float | None = None,
                   max_tokens: int | None = None) -> Completion:
        from .tools.loop import MAX_TOOL_ITERATIONS
        from .tools.executor import ToolDispatcher
        if model not in await self.list_models(base_url, api_key):
            raise HTTPException(422, "ollama.model_missing")
        registry = ToolRegistry.from_specs(tools or [])
        if tools and (await self.model_capabilities(base_url, api_key, model)).tools is not True:
            raise HTTPException(422, "ollama.tools_unconfirmed")
        convo = adapt_messages(messages)
        schemas = [{"type": "function", "function": {"name": spec.name, "description": spec.description,
                    "parameters": spec.input_schema}} for spec in registry.specs.values()]
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        dispatcher = ToolDispatcher(tools or [], "ollama")
        metadata = dispatcher.metadata
        input_tokens = output_tokens = 0
        for iteration in range(MAX_TOOL_ITERATIONS + 1):
            payload = {"model": model, "messages": convo, "stream": False, "options": options}
            if schemas and iteration < MAX_TOOL_ITERATIONS:
                payload["tools"] = schemas
            data = await _request(base_url, api_key, "POST", "/api/chat", payload, generation=True)
            message = data.get("message")
            if (data.get("done") is not True or not isinstance(message, dict)
                    or message.get("role") != "assistant" or not isinstance(message.get("content"), str)):
                raise HTTPException(502, "ollama.invalid_response")
            for field in ("prompt_eval_count", "eval_count"):
                if type(data.get(field, 0)) is not int or data.get(field, 0) < 0:
                    raise HTTPException(502, "ollama.invalid_response")
            input_tokens += data.get("prompt_eval_count", 0)
            output_tokens += data.get("eval_count", 0)
            calls = message.get("tool_calls", [])
            if not isinstance(calls, list):
                raise HTTPException(502, "ollama.invalid_response")
            if not calls:
                if not message["content"].strip():
                    raise HTTPException(502, "ollama.invalid_response")
                return Completion(message["content"].strip(), input_tokens, output_tokens, metadata or None)
            if iteration == MAX_TOOL_ITERATIONS or len(calls) > 16:
                raise HTTPException(502, "ollama.tool_limit")
            convo.append(message)
            for call in calls:
                function = call.get("function") if isinstance(call, dict) else None
                if (not isinstance(function, dict) or not isinstance(function.get("name"), str)):
                    raise HTTPException(502, "ollama.invalid_response")
                name, args = function["name"], function.get("arguments", {})
                result, is_error = await dispatcher.call(name, args)
                convo.append({"role": "tool", "tool_name": name, "content": result})
        raise HTTPException(502, "ollama.tool_limit")

    def stream(self, *args, **kwargs):
        raise NotImplementedError("Streaming is not implemented by this runtime")
