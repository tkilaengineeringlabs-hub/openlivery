"""Groq cloud adapter using the shared agent runtime and tool executor."""
import asyncio
import json
import hashlib
import time

import httpx
from fastapi import HTTPException

from .ai import Completion
from .tools.specs import ToolSpec, find_spec

BASE_URL = "https://api.groq.com/openai/v1"
_TOOL_CAPABILITIES: dict[tuple[str, str], tuple[float, bool | None]] = {}


async def _request(api_key, method, path, payload=None, *, capability_probe=False):
    try:
        async with asyncio.timeout(60):
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                response = await client.request(method, BASE_URL + path,
                    headers={"Authorization": f"Bearer {api_key}"}, json=payload)
        if response.status_code in (401, 403):
            raise HTTPException(502, "groq.unauthorized")
        if response.status_code == 429:
            raise HTTPException(429, "groq.rate_limit")
        if capability_probe and response.status_code in (400, 422):
            return {}
        if response.status_code >= 300:
            raise HTTPException(502, "groq.unavailable")
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (TimeoutError, httpx.TimeoutException):
        raise HTTPException(504, "groq.timeout") from None
    except httpx.HTTPError:
        raise HTTPException(502, "groq.unavailable") from None
    except (ValueError, TypeError):
        raise HTTPException(502, "groq.invalid_response") from None


class GroqProvider:
    id = "groq"

    def capabilities(self, model):
        from .model_providers import ModelCapabilities
        return ModelCapabilities(None, None)

    async def list_models(self, base_url, api_key):
        data = await _request(api_key, "GET", "/models")
        rows = data.get("data")
        if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] for row in rows):
            raise HTTPException(502, "groq.invalid_response")
        return sorted({row["id"] for row in rows if row.get("active", True) is not False})

    async def test_connection(self, base_url, api_key):
        return {"ok": True, "message": "groq.connected", "models": await self.list_models(base_url, api_key)}

    async def model_capabilities(self, base_url, api_key, model):
        from .model_providers import ModelCapabilities
        if model not in await self.list_models(base_url, api_key):
            raise HTTPException(422, "groq.model_missing")
        # Confirm local function calling with a harmless, forced function request.
        # No tool is executed. Cache by credential digest and model, never by tenant
        # alone or model alone; an agency cannot inherit another key's result.
        cache_key = (hashlib.sha256(api_key.encode()).hexdigest(), model)
        cached = _TOOL_CAPABILITIES.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return ModelCapabilities(cached[1], None)
        name = "tkila_capability_check"
        data = await _request(api_key, "POST", "/chat/completions", {
            "model": model, "messages": [{"role": "user", "content": "Call tkila_capability_check with no arguments."}],
            "stream": False, "max_completion_tokens": 256,
            "tools": [{"type": "function", "function": {"name": name, "description": "Verify function calling without executing an action.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}],
            "tool_choice": {"type": "function", "function": {"name": name}},
        }, capability_probe=True)
        confirmed = None
        try:
            calls = data["choices"][0]["message"].get("tool_calls", [])
            confirmed = any(call["function"]["name"] == name and json.loads(call["function"]["arguments"]) == {} for call in calls) or None
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            pass
        if len(_TOOL_CAPABILITIES) >= 256:
            _TOOL_CAPABILITIES.clear()
        _TOOL_CAPABILITIES[cache_key] = (time.monotonic() + 300, confirmed)
        return ModelCapabilities(confirmed, None)

    async def chat(self, base_url, api_key, model, messages, *, tools: list[ToolSpec] | None = None,
                   temperature=None, max_tokens=None):
        from .tools.loop import MAX_TOOL_ITERATIONS
        from .tools.executor import ToolDispatcher
        if tools and (await self.model_capabilities(base_url, api_key, model)).tools is not True:
            raise HTTPException(422, "groq.tools_unconfirmed")
        convo = list(messages)
        dispatcher = ToolDispatcher(tools or [], "groq")
        metadata = dispatcher.metadata
        input_tokens = output_tokens = 0
        try:
            for iteration in range(MAX_TOOL_ITERATIONS + 1):
                payload = {"model": model, "messages": convo, "stream": False}
                if temperature is not None:
                    payload["temperature"] = temperature
                if max_tokens is not None:
                    payload["max_completion_tokens"] = max_tokens
                if tools:
                    payload["tools"] = [{"type": "function", "function": {"name": s.name, "description": s.description, "parameters": s.input_schema}} for s in tools]
                    payload["tool_choice"] = "none" if iteration == MAX_TOOL_ITERATIONS else "auto"
                data = await _request(api_key, "POST", "/chat/completions", payload)
                message = data["choices"][0]["message"]
                usage = data.get("usage") or {}
                input_tokens += int(usage.get("prompt_tokens") or 0)
                output_tokens += int(usage.get("completion_tokens") or 0)
                calls = message.get("tool_calls") or []
                if not calls:
                    content = message.get("content")
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError()
                    return Completion(content.strip(), input_tokens, output_tokens, metadata or None)
                if iteration == MAX_TOOL_ITERATIONS:
                    raise HTTPException(502, "groq.tool_limit")
                convo.append(message)
                for call in calls:
                    name = call["function"]["name"]
                    try:
                        args = json.loads(call["function"]["arguments"])
                        valid = isinstance(args, dict)
                    except (ValueError, TypeError):
                        args, valid = {}, False
                    result, is_error = await dispatcher.call(name, args if valid else None)
                    convo.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise HTTPException(502, "groq.invalid_response") from None

    def stream(self, *args, **kwargs):
        raise NotImplementedError("Streaming is not implemented by this runtime")
