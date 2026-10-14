"""Ollama acceptance contracts over mocked HTTP; no running Ollama required."""
import asyncio
import json
import uuid
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from conftest import TestingSession
from app.config import get_settings
from app.models import Agency, Agent, AgentTool, Client, ProviderCredential
from app.services import ollama
from app.services.model_providers import get_provider, supported_providers
from app.services.providers import resolve_provider_credentials
from app.services.tools.runner import run_completion
from app.services.tools.specs import ToolSpec

URL = "http://localhost:11434"
MODEL = "fixture-model:local"


@pytest.fixture
def server(monkeypatch):
    state = {"models": [MODEL], "capabilities": ["completion", "tools"], "requests": [], "replies": []}
    original = httpx.AsyncClient

    def respond(request):
        state["requests"].append(request)
        if state.get("exception"):
            raise state["exception"]
        if state.get("status"):
            return httpx.Response(state["status"], json={"error": "private upstream detail"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in state["models"]]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": state["capabilities"]})
        assert request.url.path == "/api/chat"
        message = state["replies"].pop(0) if state["replies"] else {"role": "assistant", "content": "OK"}
        return httpx.Response(200, json={"message": message, "done": True, "prompt_eval_count": 12, "eval_count": 2})

    monkeypatch.setattr(ollama.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    return state


def test_registration_and_unknown_capabilities():
    provider = get_provider("ollama")
    assert isinstance(provider, ollama.OllamaProvider)
    assert supported_providers() == ("openai", "anthropic", "ollama", "groq")
    assert provider.capabilities(MODEL).tools is None
    assert provider.capabilities(MODEL).vision is None
    with pytest.raises(NotImplementedError):
        provider.stream()


def test_connection_models_and_empty_list(server):
    provider = get_provider("ollama")
    assert asyncio.run(provider.test_connection(URL)) == {"ok": True, "message": "ollama.connected", "models": [MODEL]}
    server["models"] = []
    assert asyncio.run(provider.list_models(URL, "")) == []
    assert asyncio.run(provider.test_connection(URL))["ok"] is True


@pytest.mark.parametrize("exception,code", [
    (httpx.ConnectError("secret address"), "connection_refused"),
    (httpx.ReadTimeout("secret address"), "timeout"),
    (httpx.ConnectTimeout("secret address"), "timeout"),
    (httpx.RemoteProtocolError("secret upstream"), "unavailable"),
])
def test_unavailable_and_timeouts(server, exception, code):
    server["exception"] = exception
    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_provider("ollama").test_connection(URL))
    assert caught.value.detail == f"ollama.{code}"


@pytest.mark.parametrize("data", [[], {}, {"models": None}, {"models": [{}]}, {"models": ["bad"]}, {"models": [{"name": ""}]}])
def test_invalid_model_responses(monkeypatch, data):
    original = httpx.AsyncClient
    monkeypatch.setattr(ollama.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data)), **kwargs))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_provider("ollama").list_models(URL, ""))
    assert caught.value.detail == "ollama.invalid_response"


def test_chat_adaptation_usage_and_selected_model_missing(server):
    provider = get_provider("ollama")
    messages = [{"role": "system", "content": "Rules"}, {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"}, {"role": "user", "content": "Now OK"}]
    completion = asyncio.run(provider.chat(URL, "", MODEL, messages, temperature=0.3, max_tokens=42))
    assert (completion.text, completion.input_tokens, completion.output_tokens) == ("OK", 12, 2)
    payload = json.loads(server["requests"][-1].content)
    assert payload == {"model": MODEL, "messages": messages, "stream": False,
                       "options": {"temperature": 0.3, "num_predict": 42}}
    assert "authorization" not in server["requests"][-1].headers
    with pytest.raises(HTTPException) as caught:
        asyncio.run(provider.chat(URL, "", "removed", messages))
    assert caught.value.detail == "ollama.model_missing"


def test_tools_execute_only_allowlist_and_return_results(server):
    handler = Mock(return_value=("real tool result", False))
    spec = ToolSpec("allowed", "Allowed action", {"type": "object"}, handler=handler)
    server["replies"] = [{"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "foreign_tool", "arguments": {}}},
        {"function": {"name": "allowed", "arguments": {"value": 1}}},
    ]}, {"role": "assistant", "content": "Done"}]
    result = asyncio.run(get_provider("ollama").chat(URL, "", MODEL, [], tools=[spec]))
    handler.assert_called_once_with({"value": 1})
    assert result.text == "Done" and result.input_tokens == 24
    assert result.tool_calls[0]["is_error"] is True
    assert result.tool_calls[1]["is_error"] is False
    payload = json.loads(server["requests"][-1].content)
    assert payload["tools"][0]["function"]["parameters"] == spec.input_schema
    assert payload["messages"][-1] == {"role": "tool", "tool_name": "allowed", "content": "real tool result"}


@pytest.mark.parametrize("capabilities", [None, [], ["completion"], ["vision"]])
def test_tools_fail_closed_for_unconfirmed_models(server, capabilities):
    server["capabilities"] = capabilities
    handler = Mock()
    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_provider("ollama").chat(URL, "", MODEL, [], tools=[
            ToolSpec("allowed", "Action", {}, handler=handler)]))
    assert caught.value.detail == "ollama.tools_unconfirmed"
    handler.assert_not_called()
    assert not any(r.url.path == "/api/chat" for r in server["requests"])


def test_tool_loop_bounded_and_unknown_tools_denied_without_specs(server):
    call = {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "unallowed", "arguments": {}}}]}
    server["replies"] = [call] * 6
    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_provider("ollama").chat(URL, "", MODEL, []))
    assert caught.value.detail == "ollama.tool_limit"
    requests = [json.loads(r.content) for r in server["requests"] if r.url.path == "/api/chat"]
    assert len(requests) == 6
    assert requests[1]["messages"][-1]["content"].startswith("Tool call denied")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://user:secret@localhost:11434", "http://localhost:11434/api",
                                 "http://localhost:11434?token=private", "http://localhost:11434#fragment", "http://localhost:99999"])
def test_reject_dangerous_url_shapes(url):
    with pytest.raises(HTTPException):
        ollama.validate_url(url)


@pytest.mark.parametrize("url", ["http://169.254.169.254", "http://127.0.0.1:8000", "http://10.0.0.1:11434", "http://[::1]:8000"])
def test_private_network_not_blanket_allowed(url, monkeypatch):
    monkeypatch.setattr(get_settings(), "tools_allow_private_urls", True)
    with pytest.raises(HTTPException) as caught:
        ollama.validate_url(url)
    assert caught.value.detail == "ollama.url_blocked"


def test_public_guard_and_explicit_private_origin(monkeypatch):
    guard = Mock(return_value=None)
    monkeypatch.setattr(ollama, "_blocked_reason", guard)
    assert ollama.validate_url("https://ollama.example") == "https://ollama.example:443"
    guard.assert_called_once_with("https://ollama.example:443", allow_private=False)
    monkeypatch.setattr(get_settings(), "ollama_allowed_private_origins", ["http://10.0.0.4:11434"])
    assert ollama.validate_url("http://10.0.0.4:11434") == "http://10.0.0.4:11434"


@pytest.mark.parametrize("status", [301, 302, 401, 500])
def test_no_redirects_or_upstream_error_leaks(server, status):
    server["status"] = status
    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_provider("ollama").test_connection(URL))
    assert caught.value.detail == "ollama.server_error"
    assert len(server["requests"]) == 1


def configure(client, **values):
    result = client.put("/api/providers/ollama", json={"name": "Local test", "base_url": URL, **values})
    assert result.status_code == 200, result.text
    return result.json()


def test_config_endpoints_refresh_probe_no_conversation(authenticated_client, server):
    client = authenticated_client
    validation = client.post("/api/providers/ollama/validate", json={"base_url": URL})
    assert validation.json()["models"] == [MODEL]
    assert next(p for p in client.get("/api/providers").json() if p["provider"] == "ollama")["configured"] is False
    configured = configure(client, default_model=MODEL)
    assert configured["name"] == "Local test" and configured["default_model"] == MODEL
    assert configured["api_key_masked"] == ""
    assert client.post("/api/providers/ollama/test").json()["ok"] is True
    assert client.post("/api/providers/ollama/test").json()["models"] == [MODEL]
    before = client.get("/api/conversations").json()
    probe = client.post("/api/providers/ollama/probe", json={"model": MODEL})
    assert probe.status_code == 200 and probe.json()["ok"] is True
    assert client.get("/api/conversations").json() == before
    server["models"] = []
    assert client.post("/api/providers/ollama/test").json()["models"] == []
    assert client.post("/api/providers/ollama/probe", json={"model": MODEL}).status_code == 422
    assert client.delete("/api/providers/ollama").status_code == 204
    assert client.post("/api/providers/ollama/test").status_code == 400


def test_saved_url_priority_and_optional_auth(authenticated_client, server, monkeypatch):
    configure(authenticated_client, api_key="proxy-fixture-secret")
    monkeypatch.setattr(get_settings(), "ollama_base_url", "http://host.docker.internal:11434")
    with TestingSession() as db:
        credential = db.scalar(select(ProviderCredential))
        assert credential.encrypted_api_key != "proxy-fixture-secret"
        assert resolve_provider_credentials(db, credential.agency_id, "ollama") == (URL, "proxy-fixture-secret")
        credential.base_url = None
        db.commit()
        assert resolve_provider_credentials(db, credential.agency_id, "ollama")[0] == "http://host.docker.internal:11434"
    assert "proxy-fixture-secret" not in authenticated_client.get("/api/providers").text
    assert authenticated_client.post("/api/providers/ollama/test").status_code == 200
    assert server["requests"][-1].headers["authorization"] == "Bearer proxy-fixture-secret"
    for route, method in [("validate", "post"), ("", "put")]:
        response = getattr(authenticated_client, method)("/api/providers/ollama" + ("/" + route if route else ""), json={"base_url": URL})
        assert response.status_code == 422
        assert response.json()["detail"] == "ollama.auth_required"
    configure(authenticated_client, api_key="")
    assert authenticated_client.post("/api/providers/ollama/test").status_code == 200
    assert "authorization" not in server["requests"][-1].headers


def test_tenant_isolation_and_agent_selection(authenticated_client, server, monkeypatch):
    client = authenticated_client
    configure(client, default_model=MODEL)
    business = client.post("/api/clients", json={"name": "Local company"}).json()
    agent = client.post("/api/agents", json={"name": "Local agent", "client_id": business["id"], "provider": "ollama", "model": MODEL})
    assert agent.status_code == 201
    agent_id = agent.json()["id"]
    assert client.patch(f"/api/agents/{agent_id}", json={"model": "missing"}).status_code == 422
    monkeypatch.setattr(get_settings(), "allow_multi_agency", True)
    client.post("/api/auth/logout")
    assert client.post("/api/auth/register", json={"agency_name": "Other", "name": "Other", "email": "other@example.com", "password": "other-password"}).status_code == 201
    assert client.post("/api/providers/ollama/test").status_code == 400
    assert client.post("/api/providers/ollama/test").status_code == 400
    assert client.get("/api/providers/ollama/capabilities", params={"model": MODEL}).status_code == 422
    assert client.post("/api/providers/ollama/probe", json={"model": MODEL}).status_code == 422
    assert client.patch(f"/api/agents/{agent_id}", json={"provider": "ollama"}).status_code == 404
    other_business = client.post("/api/clients", json={"name": "Other company"}).json()
    assert client.post("/api/agents", json={"name": "No connection", "client_id": other_business["id"], "provider": "ollama", "model": MODEL}).status_code == 422


def test_actual_agent_runtime_history_and_allowlist(authenticated_client, server):
    client = authenticated_client
    configure(client)
    business = client.post("/api/clients", json={"name": "Local company"}).json()
    agent = client.post("/api/agents", json={"name": "Local agent", "instructions": "Fixture system instructions", "client_id": business["id"], "provider": "ollama", "model": MODEL}).json()
    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    reply = client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "Responde únicamente: OK"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["messages"][-1]["content"] == "OK"
    payload = json.loads(server["requests"][-1].content)
    assert payload["model"] == MODEL
    assert "Fixture system instructions" in payload["messages"][0]["content"]
    assert payload["messages"][-1]["content"] == "Responde únicamente: OK"
    with TestingSession() as db:
        row = db.get(Agent, uuid.UUID(agent["id"]))
        db.add(AgentTool(agent_id=row.id, type="http", name="disabled", enabled=False, url="https://example.test"))
        other = Agency(name="Other", slug="other-tools")
        db.add(other); db.flush()
        foreign = Client(agency_id=other.id, name="Foreign", portal_slug="foreign-tools")
        db.add(foreign); db.flush()
        foreign_agent = Agent(agency_id=other.id, client_id=foreign.id, name="Foreign")
        db.add(foreign_agent); db.flush()
        db.add(AgentTool(agent_id=foreign_agent.id, type="http", name="foreign", url="https://example.test"))
        db.commit()
        server["replies"] = [{"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "disabled", "arguments": {}}}, {"function": {"name": "foreign", "arguments": {}}},
        ]}, {"role": "assistant", "content": "Unavailable"}]
        result = asyncio.run(run_completion(db, row, URL, "", [{"role": "user", "content": "Try tools"}]))
        assert all(call["is_error"] for call in result.tool_calls)
        assert all("not permitted" in call["result_preview"] for call in result.tool_calls)


def test_probe_reports_unexpected_actual_response(authenticated_client, server):
    configure(authenticated_client)
    server["replies"] = [{"role": "assistant", "content": "Something else"}]
    response = authenticated_client.post("/api/providers/ollama/probe", json={"model": MODEL})
    assert response.json() == {"ok": False, "response": "Something else", "message": "ollama.probe_unexpected"}


def test_host_resolution_failure_is_safe(monkeypatch):
    monkeypatch.setattr(ollama, "_blocked_reason", lambda *args, **kwargs: "Error: could not resolve host 'fixture'")
    with pytest.raises(HTTPException) as caught:
        ollama.validate_url("https://unresolvable.example")
    assert caught.value.detail == "ollama.host_unavailable"


def test_absolute_generation_deadline(monkeypatch):
    original = httpx.AsyncClient
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={})
    monkeypatch.setattr(ollama.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(slow), **kwargs))
    monkeypatch.setattr(get_settings(), "ollama_timeout_seconds", 0.01)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(ollama._request(URL, "", "POST", "/api/chat", {}, generation=True))
    assert caught.value.status_code == 504


@pytest.mark.parametrize("message", [{}, {"role": "assistant", "content": None}, {"role": "assistant", "content": ""},
                                     {"role": "assistant", "content": "", "tool_calls": [None]}])
def test_malformed_chat_fails_cleanly(server, message):
    server["replies"] = [message]
    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_provider("ollama").chat(URL, "", MODEL, []))
    assert caught.value.detail == "ollama.invalid_response"


def test_invalid_ollama_env_does_not_break_cloud_provider_listing(authenticated_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "ollama_base_url", "http://user:private-default@localhost:11434")
    response = authenticated_client.get("/api/providers")
    assert response.status_code == 200 and "private-default" not in response.text
    assert {row["provider"] for row in response.json()} == {"openai", "anthropic", "ollama", "groq"}
    assert authenticated_client.put("/api/providers/openai", json={"api_key": "fixture-key"}).status_code == 200
