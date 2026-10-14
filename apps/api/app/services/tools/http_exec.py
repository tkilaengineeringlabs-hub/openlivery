"""Execute a user-defined HTTP tool with LLM-provided arguments.

Never raises: every failure becomes text handed back to the LLM so a broken
tool does not break the chat.
"""

import ipaddress
import json
import socket
import asyncio
from urllib.parse import quote, urlparse

import httpx

from ...config import get_settings
from ...models import AgentTool
from ...security import decrypt_secret
from .specs import path_placeholders

MAX_RESPONSE_CHARS = 100_000


async def execute_http_tool(tool: AgentTool, args: dict, *, strict: bool = False) -> tuple[str, bool]:
    """Run the tool and return (result_text, is_error)."""
    original = urlparse(tool.url)
    if "{" in original.netloc or "}" in original.netloc:
        return "Error: the tool origin must be fixed", True
    url = tool.url
    for name in path_placeholders(tool.url):
        if name not in args:
            return f"Error: missing required path parameter '{name}'", True
        url = url.replace("{" + name + "}", quote(str(args[name]), safe=""))

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return "Error: invalid tool URL", True
    try:
        validation = asyncio.to_thread(_blocked_reason, url, allow_private=False) if strict else asyncio.to_thread(_blocked_reason, url)
        blocked = await asyncio.wait_for(validation, 5)
    except TimeoutError:
        return "Error: destination validation timed out", True
    if blocked:
        return blocked, True

    query_names = {param.get("name") for param in tool.query_params or []}
    params = {key: value for key, value in args.items() if key in query_names}
    body_names = {param.get("name") for param in tool.body_params or []}
    body = {key: value for key, value in args.items() if key in body_names}

    headers = {}
    if tool.encrypted_headers:
        try:
            headers = json.loads(decrypt_secret(tool.encrypted_headers))
        except Exception:
            return "Error: the tool's stored headers could not be decrypted", True

    request: dict = {"params": params or None, "headers": headers or None}
    if tool.http_method in ("POST", "PUT", "PATCH"):
        request["json"] = body

    try:
        async with httpx.AsyncClient(timeout=tool.timeout_seconds, follow_redirects=False, trust_env=False) as client:
            response = await client.request(tool.http_method, url, **request)
    except httpx.HTTPError as exc:
        return f"Error: the request failed ({type(exc).__name__})", True

    text = response.text
    text = redact_header_values(text, headers)
    if len(text) > MAX_RESPONSE_CHARS:
        text = text[:MAX_RESPONSE_CHARS] + "... [truncated]"
    # Redirects (3xx) count as failures: they are never followed, so the data
    # was not retrieved.
    return f"HTTP {response.status_code}: {text}", response.status_code >= 300


def _blocked_reason(url: str, *, allow_private: bool = True) -> str | None:
    """Reject URLs resolving to private/loopback/reserved addresses (SSRF).

    Redirects are disabled at the client. DNS rebinding between this check and
    the request remains theoretically possible; pinning the resolved IP is not
    worth the transport complexity here.
    """
    if allow_private and get_settings().tools_allow_private_urls:
        return None
    host = urlparse(url).hostname
    if not host:
        return "Error: invalid URL"
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return f"Error: could not resolve host '{host}'"
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved
                or (not allow_private and (not address.is_global or address.is_multicast))):
            return "Error: the tool URL resolves to a private or reserved address, which is not allowed"
    return None


def redact_header_values(text: str, headers: dict) -> str:
    for secret in headers.values():
        if isinstance(secret, str) and secret:
            text = text.replace(secret, "[redacted]")
            for part in secret.split():
                if len(part) >= 8:
                    text = text.replace(part, "[redacted]")
    try:
        data = json.loads(text)
        changed = False
        def redact(value):
            nonlocal changed
            if isinstance(value, dict):
                result = {}
                for key, item in value.items():
                    normalized = str(key).lower().replace("-", "_")
                    if (normalized.endswith("token") or any(marker in normalized for marker in ("password", "secret", "api_key", "authorization", "cookie"))):
                        result[key] = "[redacted]"
                        changed = True
                    else:
                        result[key] = redact(item)
                return result
            if isinstance(value, list):
                return [redact(item) for item in value]
            return value
        cleaned = redact(data)
        if changed:
            text = json.dumps(cleaned)
    except (ValueError, RecursionError):
        pass
    return text
