"""Native bookings on disposable PostgreSQL. Provider calls are always mocked."""
import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from conftest import TestingSession, customer_conversation
from app.models import Agency, Agent, Appointment, AutomationRun, Client, Conversation, ScheduledAutomationAction, now_utc
from app.schemas_appointments import AppointmentCreate
from app.services import appointments as engine
from app.services.tools.appointments import build_appointment_specs


def setup(client, zone="America/Mexico_City", before=0, after=0):
    business = client.post("/api/clients", json={"name": "Calendar business"}).json()
    cid = business["id"]
    service = client.post("/api/appointment-services", json={"client_id": cid, "name": "Consultation", "duration_minutes": 60,
        "buffer_before_minutes": before, "buffer_after_minutes": after})
    assert service.status_code == 201, service.text
    hours = client.put("/api/availability", json={"client_id": cid, "timezone": zone, "slot_minutes": 15,
        "rules": [{"weekday": day, "start_time": "09:00", "end_time": "18:00"} for day in range(5)]})
    assert hours.status_code == 200, hours.text
    today = now_utc().astimezone(ZoneInfo(zone)).date()
    day = today + timedelta(days=7 - today.weekday())
    return cid, service.json()["id"], day.isoformat()


def slots(client, cid, sid, day, exclude=None):
    response = client.get("/api/appointments/availability", params={"client_id": cid, "service_id": sid, "date": day,
        **({"exclude_id": exclude} if exclude else {})})
    assert response.status_code == 200, response.text
    return response.json()


def booking(cid, sid, start, **extra):
    return {"client_id": cid, "service_id": sid, "starts_at": start, "customer_name": "Test Customer", **extra}


def test_calendar_lifecycle_timezone_buffers_blocks(authenticated_client):
    client = authenticated_client
    cid, sid, day = setup(client, before=15, after=30)
    result = slots(client, cid, sid, day)
    first = result["slots"][0]
    assert result["timezone"] == "America/Mexico_City"
    assert datetime.fromisoformat(first["starts_at"]).astimezone(ZoneInfo(result["timezone"])).strftime("%H:%M") == "09:15"
    last = result["slots"][-1]
    assert datetime.fromisoformat(last["ends_at"]).astimezone(ZoneInfo(result["timezone"])).strftime("%H:%M") == "17:30"
    created = client.post("/api/appointments", json=booking(cid, sid, first["starts_at"]))
    assert created.status_code == 201, created.text
    aid = created.json()["id"]
    assert client.post("/api/appointments", json=booking(cid, sid, first["starts_at"])).status_code == 409
    assert client.post("/api/appointments", json=booking(cid, sid, f"{day}T08:00:00-06:00")).status_code == 409
    assert client.post("/api/appointments", json=booking(cid, sid, f"{day}T10:00:00")).status_code == 422
    remaining = slots(client, cid, sid, day)["slots"]
    assert datetime.fromisoformat(remaining[0]["starts_at"]).astimezone(ZoneInfo(result["timezone"])).strftime("%H:%M") == "11:00"
    moved = client.post(f"/api/appointments/{aid}/reschedule", json={"starts_at": remaining[0]["starts_at"]})
    assert moved.status_code == 200
    assert client.patch(f"/api/appointments/{aid}", json={"status": "confirmed", "notes": "Changed"}).json()["status"] == "confirmed"
    assert client.post(f"/api/appointments/{aid}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/appointments/{aid}/reschedule", json={"starts_at": first["starts_at"]}).status_code == 409
    for status, endpoint in [("completed", "complete"), ("no_show", "no-show")]:
        row = client.post("/api/appointments", json=booking(cid, sid, first["starts_at"])).json()
        assert client.post(f"/api/appointments/{row['id']}/{endpoint}").json()["status"] == status
    block = client.post("/api/appointment-blocks", json={"client_id": cid, "starts_at": first["starts_at"], "ends_at": first["ends_at"], "reason": "Lunch"})
    assert block.status_code == 201, block.text
    assert first["starts_at"] not in [s["starts_at"] for s in slots(client, cid, sid, day)["slots"]]
    assert client.delete(f"/api/appointment-blocks/{block.json()['id']}").status_code == 204
    assert client.post("/api/appointment-blocks", json={"client_id": cid, "starts_at": first["ends_at"], "ends_at": first["starts_at"]}).status_code == 422
    assert client.get("/api/appointments", params={"client_id": cid, "date_from": day, "date_to": day, "search": "Test"}).status_code == 200
    assert client.patch(f"/api/appointment-services/{sid}", json={"duration_minutes": 0}).status_code == 422
    assert client.delete(f"/api/appointment-services/{sid}").status_code == 204
    assert client.post("/api/appointments", json=booking(cid, sid, first["starts_at"])).status_code == 409


def test_ownership_and_configuration_validation(authenticated_client):
    client = authenticated_client
    cid, sid, day = setup(client)
    first = slots(client, cid, sid, day)["slots"][0]
    aid = client.post("/api/appointments", json=booking(cid, sid, first["starts_at"])).json()["id"]
    other_client = client.post("/api/clients", json={"name": "Second business"}).json()["id"]
    assert client.post("/api/appointments", json=booking(other_client, sid, first["starts_at"])).status_code == 404
    assert client.get("/api/appointments/availability", params={"client_id": other_client, "service_id": sid, "date": day}).status_code == 404
    with TestingSession() as db:
        agency = Agency(name="Other agency", slug="other-calendar")
        db.add(agency); db.flush()
        other = Client(agency_id=agency.id, name="Private", portal_slug="private-calendar")
        db.add(other); db.flush()
        row = db.get(Appointment, uuid.UUID(aid))
        row.agency_id, row.client_id = agency.id, other.id
        db.commit()
        other_id = str(other.id)
    assert client.get(f"/api/appointments/{aid}").status_code == 404
    for path in ("cancel", "complete", "no-show"):
        assert client.post(f"/api/appointments/{aid}/{path}").status_code == 404
    assert client.delete(f"/api/appointments/{aid}").status_code == 404
    assert client.get("/api/availability", params={"client_id": other_id}).status_code == 404
    assert client.get("/api/appointment-blocks", params={"client_id": other_id}).status_code == 404
    assert client.post("/api/appointment-services", json={"client_id": other_id, "name": "Bad", "duration_minutes": 60}).status_code == 404
    for rules in [[{"weekday": 7, "start_time": "09:00", "end_time": "10:00"}],
                  [{"weekday": 0, "start_time": "12:00", "end_time": "09:00"}],
                  [{"weekday": 0, "start_time": "09:00", "end_time": "12:00"}, {"weekday": 0, "start_time": "11:00", "end_time": "13:00"}]]:
        assert client.put("/api/availability", json={"client_id": cid, "timezone": "UTC", "rules": rules}).status_code == 422
    assert client.put("/api/availability", json={"client_id": cid, "timezone": "Invalid/Zone", "rules": []}).status_code == 422


def test_concurrent_booking_only_one_succeeds(authenticated_client):
    client = authenticated_client
    cid, sid, day = setup(client)
    start = slots(client, cid, sid, day)["slots"][0]["starts_at"]
    with TestingSession() as db:
        agency_id = db.get(Client, uuid.UUID(cid)).agency_id
    payload = AppointmentCreate.model_validate(booking(cid, sid, start))
    def reserve(_):
        with TestingSession() as db:
            try:
                engine.create_appointment(db, agency_id, payload)
                db.commit()
                return 201
            except HTTPException as exc:
                db.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [201, 409]


def test_dst_wall_time_roundtrips():
    zone = ZoneInfo("America/New_York")
    assert engine.local_instants(datetime(2027, 3, 14, 2, 30), zone) == []
    folded = engine.local_instants(datetime(2027, 11, 7, 1, 30), zone)
    assert len(folded) == 2 and folded[1] - folded[0] == timedelta(hours=1)


def test_native_agent_tools_and_conflict_results(authenticated_client, monkeypatch):
    from app.services.tools import loop, runner
    client = authenticated_client
    cid, sid, day = setup(client)
    agent_id = client.post("/api/agents", json={"client_id": cid, "name": "Booking agent", "model": "gpt-4.1-mini", "appointments_enabled": True}).json()["id"]
    conversation_id = customer_conversation(client, agent_id)["id"]
    with TestingSession() as db:
        agent, conversation = db.get(Agent, uuid.UUID(agent_id)), db.get(Conversation, uuid.UUID(conversation_id))
        specs = build_appointment_specs(agent, conversation)
        assert len(specs) == 4
        tools = {s.name: s for s in specs}
        availability, failed = tools["check_appointment_availability"].handler({"service_id": sid, "date": day})
        assert not failed
        start = json.loads(availability)["slots"][0]["starts_at"]
        args = {"service_id": sid, "starts_at": start, "customer_name": "Agent Customer"}
        result, failed = tools["create_appointment"].handler(args)
        assert not failed and json.loads(result)["ok"]
        aid = json.loads(result)["appointment"]["id"]
        conflict, failed = tools["create_appointment"].handler(args)
        assert failed and json.loads(conflict)["ok"] is False
        assert json.loads(conflict)["error"] == "slot_unavailable"
        calls = []
        async def provider(url, headers, payload, sampling):
            calls.append(payload)
            if len(calls) == 1:
                return {"output": [{"type": "function_call", "name": "create_appointment", "call_id": "c1", "arguments": json.dumps(args)}]}
            result = payload["input"][-1]["output"]
            assert "Tool call failed" in result and '"ok": false' in result
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Please choose another available time."}]}]}
        monkeypatch.setattr(loop, "_post_json", provider)
        completion = asyncio.run(runner.run_completion(db, agent, "https://mock.invalid", "mock", [{"role": "user", "content": "Book"}], conversation=conversation))
        assert completion.tool_calls[0]["is_error"] is True
        assert "choose another" in completion.text
        next_start = (datetime.fromisoformat(start) + timedelta(hours=2)).isoformat()
        moved, failed = tools["reschedule_appointment"].handler({"appointment_id": aid, "starts_at": next_start})
        assert not failed
        cancelled, failed = tools["cancel_appointment"].handler({"appointment_id": aid})
        assert not failed and json.loads(cancelled)["appointment"]["status"] == "cancelled"
        agent.appointments_enabled = False
        assert build_appointment_specs(agent, conversation) == []
        db.commit()
        denied, failed = tools["create_appointment"].handler(args)
        assert failed and json.loads(denied)["ok"] is False


def test_appointment_automation_events_reminders_and_variables(authenticated_client):
    from app.services.automations.appointments import render_message
    from app.services.automations.worker import process_due
    client = authenticated_client
    cid, sid, day = setup(client)
    ids = {}
    for trigger in ("appointment_created", "appointment_rescheduled", "appointment_cancelled", "appointment_completed", "appointment_upcoming"):
        response = client.post("/api/automations", json={"name": trigger, "client_id": cid, "trigger_type": trigger,
            "trigger_config": {"minutes": 15} if trigger == "appointment_upcoming" else {},
            "actions": [{"type": "delay", "amount": 1, "unit": "minutes"}]})
        assert response.status_code == 201, response.text
        ids[trigger] = response.json()["id"]
    first = slots(client, cid, sid, day)["slots"][0]
    row = client.post("/api/appointments", json=booking(cid, sid, first["starts_at"])).json()
    aid = row["id"]
    with TestingSession() as db:
        run = db.scalar(select(AutomationRun).where(AutomationRun.event_type == "appointment_upcoming"))
        job = db.scalar(select(ScheduledAutomationAction).where(ScheduledAutomationAction.automation_run_id == run.id))
        assert job.action_index == -2
        assert job.execute_at == datetime.fromisoformat(first["starts_at"]) - timedelta(minutes=15)
        assert "Test Customer" in render_message("Hello {{customer.name}}: {{service.name}} {{appointment_time}}", run.event_payload)
        old_id = run.id
    new_start = (datetime.fromisoformat(first["starts_at"]) + timedelta(hours=2)).isoformat()
    assert client.post(f"/api/appointments/{aid}/reschedule", json={"starts_at": new_start}).status_code == 200
    with TestingSession() as db:
        assert db.get(AutomationRun, old_id).status == "skipped"
        current = db.scalars(select(AutomationRun).where(AutomationRun.event_type == "appointment_upcoming", AutomationRun.status == "running")).all()
        assert len(current) == 1
        job = db.scalar(select(ScheduledAutomationAction).where(ScheduledAutomationAction.automation_run_id == current[0].id))
        job.execute_at = now_utc() - timedelta(seconds=1)
        db.commit()
        asyncio.run(process_due(db))
        assert db.scalar(select(ScheduledAutomationAction).where(ScheduledAutomationAction.automation_run_id == current[0].id, ScheduledAutomationAction.action_index == 0)) is not None
    assert client.post(f"/api/appointments/{aid}/cancel").status_code == 200
    second = client.post("/api/appointments", json=booking(cid, sid, first["starts_at"])).json()
    assert client.post(f"/api/appointments/{second['id']}/complete").status_code == 200
    for event in ids:
        assert client.get(f"/api/automations/{ids[event]}/runs").json()
    with TestingSession() as db:
        assert not db.scalars(select(AutomationRun).where(AutomationRun.event_type == "appointment_upcoming", AutomationRun.status == "running")).all()
