"""Automation contracts against disposable PostgreSQL; network effects are mocked."""
import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from conftest import TestingSession, customer_conversation
from app.models import Agency, Automation, AutomationRun, Client, Conversation, Message, ScheduledAutomationAction, now_utc
from app.services.automations import emit_event, evaluate_conditions
from app.services.automations import worker
from app.services.automations.secrets import STORED


def definition(**changes):
    result = {"name": "Follow-up", "trigger_type": "message_received", "actions": [{"type": "handoff_to_human"}]}
    result.update(changes)
    return result


def setup_conversation(client):
    business = client.post("/api/clients", json={"name": "Test business"}).json()
    agent = client.post("/api/agents", json={"name": "Test agent", "client_id": business["id"]}).json()
    conversation = customer_conversation(client, agent["id"])
    return business, uuid.UUID(conversation["id"])


def incoming(conversation_id, text="precio", **values):
    with TestingSession() as db:
        message = Message(conversation_id=conversation_id, role="user", content=text, **values)
        db.add(message)
        db.commit()
        return message.id


def drain():
    with TestingSession() as db:
        return asyncio.run(worker.process_due(db))


def due_now():
    with TestingSession() as db:
        for job in db.scalars(select(ScheduledAutomationAction).where(ScheduledAutomationAction.status == "pending")):
            job.execute_at = now_utc() - timedelta(seconds=1)
        db.commit()


def test_crud_and_validation(authenticated_client):
    client = authenticated_client
    response = client.post("/api/automations", json=definition())
    assert response.status_code == 201, response.text
    item = response.json()
    assert client.get(f"/api/automations/{item['id']}").json()["name"] == "Follow-up"
    assert len(client.get("/api/automations").json()) == 1
    assert client.patch(f"/api/automations/{item['id']}", json={"name": "Changed"}).json()["name"] == "Changed"
    assert client.post(f"/api/automations/{item['id']}/disable").json()["enabled"] is False
    assert client.post(f"/api/automations/{item['id']}/enable").json()["enabled"] is True
    for payload in [definition(actions=[{"type": "execute_code"}]), definition(conditions=[{"field": "__class__", "operator": "exists"}]),
                    definition(trigger_type="conversation_inactive", trigger_config={"minutes": 7}),
                    definition(trigger_type="client_created"), definition(actions=[{"type": "delay", "amount": 31, "unit": "days"}])]:
        assert client.post("/api/automations", json=payload).status_code == 422
    assert client.delete(f"/api/automations/{item['id']}").status_code == 204
    assert client.get(f"/api/automations/{item['id']}").status_code == 404


def test_agency_isolation(authenticated_client):
    client = authenticated_client
    with TestingSession() as db:
        other = Agency(name="Other", slug="other")
        db.add(other); db.flush()
        business = Client(agency_id=other.id, name="Private", portal_slug="private")
        db.add(business); db.flush()
        rule = Automation(agency_id=other.id, client_id=business.id, name="Private", trigger_type="message_received", actions=[])
        db.add(rule); db.commit()
        rule_id, business_id = rule.id, business.id
    assert client.get("/api/automations").json() == []
    for suffix in ("", "/runs"):
        assert client.get(f"/api/automations/{rule_id}{suffix}").status_code == 404
    assert client.patch(f"/api/automations/{rule_id}", json={"name": "Stolen"}).status_code == 404
    assert client.delete(f"/api/automations/{rule_id}").status_code == 404
    for verb in ("enable", "disable"):
        assert client.post(f"/api/automations/{rule_id}/{verb}").status_code == 404
    assert client.post("/api/automations", json=definition(client_id=str(business_id))).status_code == 404
    _, conversation_id = setup_conversation(client)
    incoming(conversation_id)
    assert drain() == 0


@pytest.mark.parametrize("operator,value,expected", [
    ("equals", "precio", True), ("not_equals", "precio", False), ("contains", "PRE", True),
    ("not_contains", "hola", True), ("exists", "", True), ("not_exists", "", False)])
def test_conditions(operator, value, expected):
    assert evaluate_conditions([{"field": "message.text", "operator": operator, "value": value}], {"message": {"text": "precio"}}) is expected


def test_message_received_handoff_and_dedup(authenticated_client):
    client = authenticated_client
    _, conversation_id = setup_conversation(client)
    item = client.post("/api/automations", json=definition(conditions=[{"field": "message.text", "operator": "contains", "value": "precio"}])).json()
    message_id = incoming(conversation_id)
    with TestingSession() as db:
        conversation = db.get(Conversation, conversation_id)
        emit_event(db, "message_received", agency_id=conversation.agency_id, client_id=conversation.client_id, message_id=message_id)
        db.commit()
    assert drain() == 1
    with TestingSession() as db:
        assert db.get(Conversation, conversation_id).mode == "human"
        assert len(db.scalars(select(AutomationRun)).all()) == 1
    runs = client.get(f"/api/automations/{item['id']}/runs").json()
    assert runs[0]["status"] == "success"
    assert runs[0]["actions_executed"] == 1


def test_false_condition_and_disabled(authenticated_client):
    client = authenticated_client
    _, cid = setup_conversation(client)
    item = client.post("/api/automations", json=definition(conditions=[{"field": "message.text", "operator": "equals", "value": "no"}])).json()
    incoming(cid)
    assert drain() == 0
    assert client.get(f"/api/automations/{item['id']}/runs").json()[0]["status"] == "skipped"
    client.post(f"/api/automations/{item['id']}/disable")
    incoming(cid)
    assert len(client.get(f"/api/automations/{item['id']}/runs").json()) == 1


def test_delay_survives_sessions_and_order(authenticated_client, monkeypatch):
    client = authenticated_client
    _, cid = setup_conversation(client)
    send = AsyncMock(return_value="external-1")
    monkeypatch.setattr(worker, "send_channel_message", send)
    item = client.post("/api/automations", json=definition(actions=[
        {"type": "delay", "amount": 30, "unit": "minutes"}, {"type": "send_message", "text": "Hello"}, {"type": "handoff_to_human"}])).json()
    incoming(cid)
    with TestingSession() as db:
        job = db.scalar(select(ScheduledAutomationAction))
        assert job.status == "pending" and job.execute_at > now_utc() + timedelta(minutes=29)
    assert drain() == 0
    due_now()
    assert drain() == 3
    assert drain() == 0
    send.assert_awaited_once()
    runs = client.get(f"/api/automations/{item['id']}/runs").json()
    assert runs[0]["status"] == "success" and runs[0]["actions_executed"] == 3


def test_inactivity_reschedules_and_cancels(authenticated_client):
    client = authenticated_client
    _, cid = setup_conversation(client)
    item = client.post("/api/automations", json=definition(trigger_type="conversation_inactive", trigger_config={"minutes": 5})).json()
    incoming(cid)
    incoming(cid, "new activity")
    due_now()
    drain()
    runs = client.get(f"/api/automations/{item['id']}/runs").json()
    assert {run["status"] for run in runs} == {"success", "skipped"}
    assert any(run["error"] == "new_activity" for run in runs)


def test_http_ssrf_and_encrypted_headers(authenticated_client, monkeypatch):
    client = authenticated_client
    action = {"type": "http_request", "url": "http://127.0.0.1/private", "headers": {"Authorization": "Bearer secret-value"}}
    assert client.post("/api/automations", json=definition(actions=[action])).status_code == 422
    from app.routers import automations as router
    monkeypatch.setattr(router, "_blocked_reason", lambda *args, **kwargs: None)
    action["url"] = "https://example.test/hook"
    response = client.post("/api/automations", json=definition(actions=[action]))
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["actions"][0]["headers"]["Authorization"] == STORED
    assert "secret-value" not in response.text
    assert client.patch(f"/api/automations/{item['id']}", json={"name": "Keep headers"}).status_code == 200
    with TestingSession() as db:
        saved = db.get(Automation, uuid.UUID(item["id"]))
        assert "secret-value" not in str(saved.actions)
        assert "encrypted_headers" in saved.actions[0]
    _, cid = setup_conversation(client)
    incoming(cid)
    monkeypatch.setattr(worker, "_blocked_reason", lambda *args, **kwargs: "blocked")
    drain()
    assert client.get(f"/api/automations/{item['id']}/runs").json()[0]["error"] == "url_blocked"


def test_client_created_event(authenticated_client):
    client = authenticated_client
    item = client.post("/api/automations", json=definition(trigger_type="client_created", actions=[{"type": "delay", "amount": 1, "unit": "minutes"}])).json()
    client.post("/api/clients", json={"name": "New business"})
    assert len(client.get(f"/api/automations/{item['id']}/runs").json()) == 1
    due_now(); drain()
    assert client.get(f"/api/automations/{item['id']}/runs").json()[0]["status"] == "success"


def test_disable_cancels_pending_and_edit_keeps_history(authenticated_client):
    client = authenticated_client
    _, cid = setup_conversation(client)
    item = client.post("/api/automations", json=definition(actions=[{"type": "delay", "amount": 1, "unit": "days"}])).json()
    incoming(cid)
    client.post(f"/api/automations/{item['id']}/disable")
    due_now()
    assert drain() == 0
    assert client.get(f"/api/automations/{item['id']}/runs").json()[0]["status"] == "skipped"


def test_historical_and_playground_do_not_trigger(authenticated_client):
    client = authenticated_client
    _, cid = setup_conversation(client)
    client.post("/api/automations", json=definition())
    incoming(cid, is_historical=True)
    with TestingSession() as db:
        db.get(Conversation, cid).channel = "playground"
        db.commit()
    incoming(cid)
    assert drain() == 0
    with TestingSession() as db:
        assert db.scalar(select(AutomationRun)) is None


def test_recovery_never_replays_uncertain_send(authenticated_client, monkeypatch):
    client = authenticated_client
    _, cid = setup_conversation(client)
    item = client.post("/api/automations", json=definition(actions=[{"type": "send_message", "text": "Hello"}])).json()
    incoming(cid)
    with TestingSession() as db:
        job = db.scalar(select(ScheduledAutomationAction))
        job.status, job.locked_until = "running", now_utc() - timedelta(minutes=1)
        db.commit()
    send = AsyncMock()
    monkeypatch.setattr(worker, "send_channel_message", send)
    drain()
    send.assert_not_awaited()
    assert client.get(f"/api/automations/{item['id']}/runs").json()[0]["error"] == "delivery_uncertain"


def test_connection_errors_retry_without_repeating_completed_actions(authenticated_client, monkeypatch):
    client = authenticated_client
    _, cid = setup_conversation(client)
    item = client.post("/api/automations", json=definition(actions=[{"type": "send_message", "text": "Hello"}])).json()
    incoming(cid)
    send = AsyncMock(side_effect=[httpx.ConnectError("secret error must not be stored"), "sent"])
    monkeypatch.setattr(worker, "send_channel_message", send)
    drain()
    with TestingSession() as db:
        job = db.scalar(select(ScheduledAutomationAction))
        assert job.status == "pending" and job.attempts == 1
        assert job.last_error == "connection_failed"
    due_now(); drain()
    assert send.await_count == 2
    assert client.get(f"/api/automations/{item['id']}/runs").json()[0]["status"] == "success"


def test_rollback_does_not_emit(authenticated_client):
    client = authenticated_client
    _, cid = setup_conversation(client)
    client.post("/api/automations", json=definition())
    with TestingSession() as db:
        db.add(Message(conversation_id=cid, role="user", content="unsaved"))
        db.flush(); db.rollback(); db.commit()
        assert db.scalar(select(AutomationRun)) is None


def test_multiple_workers_claim_once(authenticated_client, monkeypatch):
    client = authenticated_client
    _, cid = setup_conversation(client)
    client.post("/api/automations", json=definition(actions=[{"type": "send_message", "text": "Only once"}]))
    incoming(cid)
    send = AsyncMock(return_value="sent-once")
    monkeypatch.setattr(worker, "send_channel_message", send)

    async def concurrently():
        with TestingSession() as first, TestingSession() as second:
            return await asyncio.gather(worker.process_due(first), worker.process_due(second))
    assert sum(asyncio.run(concurrently())) == 1
    send.assert_awaited_once()


def test_widget_endpoint_emits_real_event(authenticated_client, monkeypatch):
    from app.routers import widget
    from app.services.ai import Completion
    client = authenticated_client
    business, cid = setup_conversation(client)
    with TestingSession() as db:
        agent_id = str(db.get(Conversation, cid).agent_id)
    channel = client.put(f"/api/webchat/channels/{business['id']}", json={"agent_id": agent_id, "is_enabled": True}).json()
    item = client.post("/api/automations", json=definition()).json()
    monkeypatch.setattr(widget, "run_completion", AsyncMock(return_value=Completion(text="Hello")))
    response = client.post(f"/api/widget/{channel['public_id']}/messages", json={"session_id": "automation-test", "content": "human please"})
    assert response.status_code == 200, response.text
    drain()
    runs = client.get(f"/api/automations/{item['id']}/runs").json()
    assert len(runs) == 1 and runs[0]["status"] == "success"


def test_human_mode_blocks_send(authenticated_client, monkeypatch):
    client = authenticated_client
    _, cid = setup_conversation(client)
    with TestingSession() as db:
        db.get(Conversation, cid).mode = "human"
        db.commit()
    item = client.post("/api/automations", json=definition(actions=[{"type": "send_message", "text": "Hello"}])).json()
    incoming(cid)
    send = AsyncMock()
    monkeypatch.setattr(worker, "send_channel_message", send)
    drain()
    send.assert_not_awaited()
    assert client.get(f"/api/automations/{item['id']}/runs").json()[0]["error"] == "human_control"


def test_broken_rule_does_not_break_message_persistence(authenticated_client):
    client = authenticated_client
    _, cid = setup_conversation(client)
    item = client.post("/api/automations", json=definition()).json()
    with TestingSession() as db:
        rule = db.get(Automation, uuid.UUID(item["id"]))
        rule.conditions = [{"field": "forbidden", "operator": "exists"}]
        db.commit()
    message_id = incoming(cid)
    with TestingSession() as db:
        assert db.get(Message, message_id) is not None
    assert client.get(f"/api/automations/{item['id']}/runs").json()[0]["error"] == "evaluation_failed"


def test_optional_template_origin_roundtrip(authenticated_client):
    client = authenticated_client
    legacy = client.post("/api/automations", json=definition()).json()
    assert legacy["template_id"] is None
    business, _ = setup_conversation(client)
    payload = definition(template_id="handoff", client_id=business["id"],
        conditions=[{"field": "message.text", "operator": "contains", "value": "human"}])
    response = client.post("/api/automations", json=payload)
    assert response.status_code == 201
    item = response.json()
    endpoint = f"/api/automations/{item['id']}"
    assert client.get(endpoint).json()["template_id"] == "handoff"
    assert client.patch(endpoint, json={"name": "Renamed"}).json()["template_id"] == "handoff"
    assert client.post(endpoint + "/disable").json()["template_id"] == "handoff"
    assert client.post(endpoint + "/enable").json()["template_id"] == "handoff"
    assert client.patch(endpoint, json={"template_id": None}).json()["template_id"] is None
    assert client.post("/api/automations", json=definition(template_id="x" * 81)).status_code == 422
    assert client.get(f"/api/automations/{legacy['id']}").json()["template_id"] is None


@pytest.mark.parametrize("template_id,trigger,minutes,action", [
    ("reminder24", "appointment_upcoming", 1440, "send_message"),
    ("reminder2", "appointment_upcoming", 120, "send_message"),
    ("confirmation", "appointment_created", None, "send_message"),
    ("afterAppointment", "appointment_completed", None, "send_message"),
    ("followUp", "conversation_inactive", 30, "send_message"),
    ("recover", "conversation_inactive", 1440, "send_message"),
    ("handoff", "message_received", None, "handoff_to_human"),
])
def test_template_rules_use_existing_persistence(authenticated_client, template_id, trigger, minutes, action):
    client = authenticated_client
    business, _ = setup_conversation(client)
    step = {"type": action}
    if action == "send_message":
        step["text"] = "Hello {{customer.name}}" if trigger.startswith("appointment_") else "Hello"
    payload = definition(template_id=template_id, client_id=business["id"], trigger_type=trigger,
        trigger_config={"minutes": minutes} if minutes else {}, actions=[step])
    response = client.post("/api/automations", json=payload)
    assert response.status_code == 201, response.text
    saved = client.get(f"/api/automations/{response.json()['id']}").json()
    assert saved["template_id"] == template_id
    assert saved["trigger_type"] == trigger
    assert saved["trigger_config"].get("minutes") == minutes
    assert saved["actions"][0]["type"] == action
    assert saved["client_id"] == business["id"]
