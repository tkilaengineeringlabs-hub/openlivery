"""Phase-one contracts; all provider calls mocked, persistence is disposable."""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from conftest import TestingSession
from app.models import Agency, Agent, AgentTool, Client
from app.services import ai, model_providers
from app.services.agent_catalog.capabilities import TOOLS
from app.services.agent_catalog.objectives import OBJECTIVES, recommendations
from app.services.agent_catalog.templates import TEMPLATES, recommend_templates, template_defaults
from app.services.tools import loop, runner
from app.services.tools.registry import ToolRegistry, load_custom_tool_specs
from app.services.tools.specs import ToolSpec


def new_agent(client, **changes):
    business = client.post("/api/clients", json={"name": "Architecture test"}).json()
    response = client.post("/api/agents", json={"name": "Assistant", "client_id": business["id"], **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_legacy_defaults_and_objective_persistence(authenticated_client):
    client = authenticated_client
    item = new_agent(client)
    url = f"/api/agents/{item['id']}"
    assert item["objectives"] == [] and item["template_id"] is None
    values = {"objectives": ["book_appointment", "respond_questions"], "template_id": "veterinary_receptionist"}
    assert client.patch(url, json=values).status_code == 200
    assert client.patch(url, json={"name": "Renamed"}).json()["objectives"] == values["objectives"]
    loaded = client.get(url).json()
    assert loaded["template_id"] == values["template_id"]
    assert loaded["appointments_enabled"] is False
    assert loaded["instructions"] == item["instructions"]
    assert client.get(url + "/tools").json() == []
    for invalid in ({"objectives": ["not_real"]}, {"objectives": ["sales", "sales"]},
                    {"objectives": None}, {"template_id": "not_real"}):
        assert client.patch(url, json=invalid).status_code == 422
    cleared = client.patch(url, json={"objectives": [], "template_id": None}).json()
    assert cleared["objectives"] == [] and cleared["template_id"] is None


def test_template_defaults_are_explicit_and_do_not_provision(authenticated_client):
    values = template_defaults("veterinary_receptionist", "es")
    item = new_agent(authenticated_client, **values)
    assert item["objectives"] == values["objectives"]
    assert item["instructions"] == values["instructions"]
    assert item["appointments_enabled"] is False
    assert authenticated_client.get("/api/automations").json() == []
    assert authenticated_client.get(f"/api/agents/{item['id']}/tools").json() == []


def test_catalog_is_authenticated_and_exposes_only_executable_providers(client, authenticated_client):
    # The two fixtures share a client; explicitly remove its authentication first.
    authenticated_client.post("/api/auth/logout")
    assert client.get("/api/catalog/agent-configuration").status_code == 401


def test_catalog_and_template_references(authenticated_client):
    response = authenticated_client.get("/api/catalog/agent-configuration")
    assert response.status_code == 200
    data = response.json()
    assert data["providers"] == ["openai", "anthropic", "ollama", "groq"]
    assert data["applies_configuration"] is False
    tool_ids = {tool.id for tool in TOOLS}
    objective_ids = {objective.id for objective in OBJECTIVES}
    for template in TEMPLATES:
        assert set(template.objectives) <= objective_ids
        assert set(template.recommended_tools) <= tool_ids
        assert template.name.es and template.name.en
    for objective in OBJECTIVES:
        assert set(objective.recommended_tools) <= tool_ids
    assert recommendations(["book_appointment", "appointment_reminder"])["automations"] == ["confirmation", "reminder24", "reminder2"]
    assert recommend_templates("health_wellness", "veterinary", ["book_appointment"], ["whatsapp"])[0].id == "veterinary_receptionist"
    assert recommend_templates("unsupported_industry", "other", [], []) == []


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_provider_adapters_reuse_transports(monkeypatch, provider):
    adapter = model_providers.get_provider(provider)
    plain = AsyncMock(return_value=ai.Completion("plain"))
    tool_transport = AsyncMock(return_value=ai.Completion("tool result"))
    models = AsyncMock(return_value={"models": ["fixture-model"]})
    monkeypatch.setattr(ai, "chat_completion", plain)
    monkeypatch.setattr(ai, "test_provider", models)
    monkeypatch.setattr(loop, f"{provider}_tool_loop", tool_transport)
    assert asyncio.run(adapter.chat("https://example.test", "fixture", "fixture-model", [] )).text == "plain"
    assert plain.call_args.args[0] == provider
    specs = [ToolSpec("allowed", "Allowed", {"type": "object"})]
    assert asyncio.run(adapter.chat("https://example.test", "fixture", "fixture-model", [], tools=specs)).text == "tool result"
    assert tool_transport.call_args.args[4] is specs
    assert asyncio.run(adapter.list_models("https://example.test", "fixture")) == ["fixture-model"]
    assert adapter.capabilities("unknown-model").tools is None
    assert adapter.capabilities("unknown-model").streaming is False
    with pytest.raises(NotImplementedError):
        adapter.stream()


@pytest.mark.parametrize("provider", ["google", "gemini", "unknown"])
def test_unimplemented_providers_fail_closed(provider):
    with pytest.raises(HTTPException) as caught:
        model_providers.get_provider(provider)
    assert caught.value.status_code == 422


def test_registry_excludes_unassigned_disabled_and_other_tenant_tools(authenticated_client):
    item = new_agent(authenticated_client)
    with TestingSession() as db:
        agent = db.get(Agent, uuid.UUID(item["id"]))
        other = Agency(name="Other workspace", slug="other-workspace")
        db.add(other); db.flush()
        business = Client(agency_id=other.id, name="Other business", portal_slug="other-business")
        db.add(business); db.flush()
        foreign_agent = Agent(agency_id=other.id, client_id=business.id, name="Private")
        sibling = Agent(agency_id=agent.agency_id, client_id=agent.client_id, name="Sibling")
        db.add_all([foreign_agent, sibling]); db.flush()
        for owner, name, enabled in [(agent, "allowed", True), (agent, "disabled", False),
                                     (foreign_agent, "foreign", True), (sibling, "unassigned", True)]:
            db.add(AgentTool(agent_id=owner.id, type="http", name=name, url="https://example.test", enabled=enabled))
        db.commit()
        specs = load_custom_tool_specs(db, agent)
        registry = ToolRegistry.from_specs(specs)
        assert list(registry.specs) == ["allowed"]
        assert registry.get("foreign") is None and registry.get("disabled") is None
        spoofed = SimpleNamespace(id=foreign_agent.id, client_id=business.id, agency_id=agent.agency_id)
        with pytest.raises(HTTPException):
            load_custom_tool_specs(db, spoofed)
        spoofed_business = SimpleNamespace(id=agent.id, client_id=business.id, agency_id=agent.agency_id)
        with pytest.raises(HTTPException):
            load_custom_tool_specs(db, spoofed_business)
        foreign_id, business_id = str(foreign_agent.id), str(business.id)
    assert authenticated_client.patch(f"/api/agents/{foreign_id}", json={"objectives": ["sales"]}).status_code == 404
    assert authenticated_client.post("/api/agents", json={"name": "No", "client_id": business_id, "objectives": ["sales"]}).status_code == 400


def test_runtime_loads_only_assigned_tools(authenticated_client, monkeypatch):
    item = new_agent(authenticated_client, model="fixture-model")
    completion = AsyncMock(return_value=ai.Completion("verified"))
    monkeypatch.setattr(model_providers, "get_provider", lambda provider: SimpleNamespace(chat=completion, capabilities=lambda model: model_providers.ModelCapabilities(True, None)))
    with TestingSession() as db:
        agent = db.get(Agent, uuid.UUID(item["id"]))
        db.add_all([AgentTool(agent_id=agent.id, type="http", name="allowed", url="https://example.test"),
                    AgentTool(agent_id=agent.id, type="http", name="disabled", url="https://example.test", enabled=False)])
        db.commit()
        result = asyncio.run(runner.run_completion(db, agent, "https://example.test", "fixture", []))
        assert result.text == "verified"
        assert [spec.name for spec in completion.call_args.kwargs["tools"] if spec.tool is not None] == ["allowed"]
        assert "knowledge_search" in [spec.name for spec in completion.call_args.kwargs["tools"]]


def test_registry_rejects_ambiguous_names():
    spec = ToolSpec("duplicate", "Duplicate", {"type": "object"})
    with pytest.raises(ValueError):
        ToolRegistry.from_specs([spec, spec])


def test_model_cannot_execute_a_tool_outside_its_allowlist(monkeypatch):
    responses = AsyncMock(side_effect=[
        {"output": [{"type": "function_call", "call_id": "attempt", "name": "not_assigned", "arguments": "{}"}]},
        {"output_text": "That action is unavailable."},
    ])
    execute = AsyncMock()
    monkeypatch.setattr(loop, "_post_json", responses)
    monkeypatch.setattr(loop, "_execute", execute)
    completion = asyncio.run(loop.openai_tool_loop("https://example.test", "fixture", "fixture", [], [], None, None))
    execute.assert_not_awaited()
    assert completion.tool_calls[0]["is_error"] is True


def test_runtime_registry_matches_credential_support():
    from app.services.providers import SUPPORTED
    assert model_providers.supported_providers() == SUPPORTED
