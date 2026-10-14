"""Google transport is mocked; database/ownership/queue behavior is real."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from conftest import TestingSession
from test_appointments import setup, slots, booking
from app.config import get_settings
from app.models import Appointment, AppointmentCalendar, AppointmentCalendarOAuth, Client, now_utc
from app.security import decrypt_secret
from app.services import google_calendar as google, calendar_worker


def connected(cid):
    with TestingSession() as db:
        client = db.get(Client, uuid.UUID(cid))
        row = AppointmentCalendar(agency_id=client.agency_id, client_id=client.id, connected=True,
                                  calendar_id="test-calendar", calendar_name="Fixture calendar", account_email="test@example.com")
        google.save_tokens(row, {"access_token": "fixture-access", "refresh_token": "fixture-refresh", "expires_in": 3600})
        db.add(row)
        db.commit()


@pytest.fixture
def provider(monkeypatch):
    events, calls, busy = {}, [], []
    def request(row, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/freeBusy":
            return {"calendars": {"test-calendar": {"busy": list(busy)}}}
        if path == "/users/me/calendarList":
            return {"items": [{"id": "test-calendar", "summary": "Fixture calendar"}, {"id": "other", "summary": "Other"}]}
        if method == "GET" and path.endswith("/events"):
            return {"items": list(events.values())}
        event_id = path.rsplit("/", 1)[-1]
        if method == "GET":
            return events.get(event_id, {"_status": 404})
        if method == "POST":
            body = kwargs["json"]
            if body["id"] in events:
                return {"_status": 409}
            events[body["id"]] = body.copy()
            return body
        if method == "PATCH":
            events[event_id].update(kwargs["json"])
            return events[event_id]
        if method == "DELETE":
            events.pop(event_id, None)
            return {}
        raise AssertionError((method, path))
    monkeypatch.setattr(google, "request", request)
    monkeypatch.setattr(calendar_worker, "new_session", TestingSession)
    return events, calls, busy


def test_sync_lifecycle_freebusy_and_reschedule_exclusion(authenticated_client, provider):
    client = authenticated_client
    cid, sid, day = setup(client, before=15, after=15)
    original = slots(client, cid, sid, day)["slots"]
    connected(cid)
    events, calls, busy = provider
    busy.append({"start": original[0]["starts_at"], "end": original[0]["ends_at"]})
    available = slots(client, cid, sid, day)["slots"]
    assert original[0]["starts_at"] not in {s["starts_at"] for s in available}
    created = client.post("/api/appointments", json=booking(cid, sid, available[0]["starts_at"]))
    assert created.status_code == 201, created.text
    aid = created.json()["id"]
    assert created.json()["calendar_sync_status"] == "pending"
    assert calendar_worker.process_one()
    event_id = "tkila" + uuid.UUID(aid).hex
    assert events[event_id]["start"]["dateTime"] == available[0]["starts_at"]
    assert client.get(f"/api/appointments/{aid}").json()["calendar_sync_status"] == "synced"
    # Own event does not block its current slot when rescheduling; another event does.
    options = slots(client, cid, sid, day, aid)["slots"]
    assert available[0]["starts_at"] in {s["starts_at"] for s in options}
    events["external"] = {"id": "external", "start": {"dateTime": available[0]["starts_at"]},
                          "end": {"dateTime": available[0]["ends_at"]}}
    assert available[0]["starts_at"] not in {s["starts_at"] for s in slots(client, cid, sid, day, aid)["slots"]}
    target = slots(client, cid, sid, day, aid)["slots"][-1]["starts_at"]
    moved = client.post(f"/api/appointments/{aid}/reschedule", json={"starts_at": target})
    assert moved.status_code == 200, moved.text
    assert calendar_worker.process_one()
    assert events[event_id]["start"]["dateTime"] == target
    assert client.patch(f"/api/appointments/{aid}", json={"notes": "Updated details"}).status_code == 200
    assert calendar_worker.process_one()
    assert events[event_id]["description"] == "Updated details"
    assert client.post(f"/api/appointments/{aid}/cancel").status_code == 200
    assert calendar_worker.process_one()
    assert event_id not in events and "external" in events
    assert client.put(f"/api/appointment-calendars/{cid}/google/calendar", json={"calendar_id": "other"}).status_code == 409


def test_uncertain_insert_is_recovered_without_duplicate(authenticated_client, provider, monkeypatch):
    cid, sid, day = setup(authenticated_client)
    connected(cid)
    start = slots(authenticated_client, cid, sid, day)["slots"][0]["starts_at"]
    aid = authenticated_client.post("/api/appointments", json=booking(cid, sid, start)).json()["id"]
    original = google.request
    def uncertain(row, method, path, **kwargs):
        result = original(row, method, path, **kwargs)
        if method == "POST":
            raise HTTPException(502, "calendar_unavailable")
        return result
    monkeypatch.setattr(google, "request", uncertain)
    assert calendar_worker.process_one()
    assert len(provider[0]) == 1
    with TestingSession() as db:
        appointment = db.get(Appointment, uuid.UUID(aid))
        assert appointment.calendar_sync_attempts == 1
        appointment.calendar_retry_at = now_utc()
        db.commit()
    monkeypatch.setattr(google, "request", original)
    assert calendar_worker.process_one()
    assert len(provider[0]) == 1
    assert authenticated_client.get(f"/api/appointments/{aid}").json()["calendar_sync_status"] == "synced"


def test_foreign_event_never_deleted(authenticated_client, provider):
    cid, sid, day = setup(authenticated_client)
    connected(cid)
    start = slots(authenticated_client, cid, sid, day)["slots"][0]["starts_at"]
    aid = authenticated_client.post("/api/appointments", json=booking(cid, sid, start)).json()["id"]
    event_id = "tkila" + uuid.UUID(aid).hex
    provider[0][event_id] = {"id": event_id, "summary": "Not Tkila"}
    assert authenticated_client.post(f"/api/appointments/{aid}/cancel").status_code == 200
    assert calendar_worker.process_one()
    assert event_id in provider[0]
    assert not any(method == "DELETE" for method, _, _ in provider[1])
    assert authenticated_client.get(f"/api/appointments/{aid}").json()["calendar_sync_error"] == "calendar_event_ownership_mismatch"


def test_unavailable_google_fails_closed(authenticated_client, monkeypatch):
    cid, sid, day = setup(authenticated_client)
    start = slots(authenticated_client, cid, sid, day)["slots"][0]["starts_at"]
    connected(cid)
    def fail(*args, **kwargs):
        raise HTTPException(502, "calendar_unavailable")
    monkeypatch.setattr(google, "request", fail)
    assert authenticated_client.get("/api/appointments/availability", params={"client_id": cid, "service_id": sid, "date": day}).status_code == 502
    assert authenticated_client.post("/api/appointments", json=booking(cid, sid, start)).status_code == 502


def test_settings_limits_prices_and_client_isolation(authenticated_client):
    client = authenticated_client
    cid, sid, day = setup(client)
    other, _, _ = setup(client)
    hours = client.get("/api/availability", params={"client_id": cid}).json()
    for rule in hours["rules"]:
        for key in ("id", "agency_id", "client_id"):
            rule.pop(key)
    hours.update(min_notice_minutes=43200, booking_days=30, reminders=[120, 1440])
    assert client.put("/api/availability", json=hours).status_code == 200
    assert slots(client, cid, sid, day)["slots"] == []
    assert client.get("/api/availability", params={"client_id": other}).json()["min_notice_minutes"] == 0
    assert client.patch(f"/api/appointment-services/{sid}", json={"price": "12.50", "color": "#8BE800"}).status_code == 200
    assert client.patch(f"/api/appointment-services/{sid}", json={"price": "-1"}).status_code == 422
    connected(cid)
    status = client.get(f"/api/appointment-calendars/{cid}/google")
    assert "fixture-access" not in status.text and "encrypted_tokens" not in status.text
    assert client.get(f"/api/appointment-calendars/{other}/google").json()["connected"] is False


def test_google_oauth_state_session_encryption_and_replay(authenticated_client, monkeypatch):
    client = authenticated_client
    cid, _, _ = setup(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "google_calendar_client_id", "fixture-client")
    monkeypatch.setattr(settings, "google_calendar_client_secret", "fixture-secret")
    result = client.post(f"/api/appointment-calendars/{cid}/google/connect")
    assert result.status_code == 200
    query = parse_qs(urlparse(result.json()["url"]).query)
    assert query["access_type"] == ["offline"] and query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    assert client.get("/api/appointment-calendars/google/callback", params={"state": "wrong", "code": "fixture"}).status_code == 400
    monkeypatch.setattr(google, "token_request", lambda data: {"access_token": "fixture-access", "refresh_token": "fixture-refresh", "scope": google.SCOPES})
    monkeypatch.setattr(google, "calendars", lambda row: [{"id": "test-calendar", "name": "Fixture"}])
    monkeypatch.setattr(google, "account_email", lambda token: "test@example.com")
    response = client.get("/api/appointment-calendars/google/callback", params={"state": state, "code": "fixture"}, follow_redirects=False)
    assert response.status_code == 303 and "calendar=connected" in response.headers["location"]
    with TestingSession() as db:
        row = db.scalar(select(AppointmentCalendar).where(AppointmentCalendar.client_id == uuid.UUID(cid)))
        assert "fixture-refresh" not in row.encrypted_tokens
        assert json.loads(decrypt_secret(row.encrypted_tokens))["refresh_token"] == "fixture-refresh"
        assert db.get(AppointmentCalendarOAuth, hashlib.sha256(state.encode()).hexdigest()) is None
    assert client.get("/api/appointment-calendars/google/callback", params={"state": state, "code": "fixture"}).status_code == 400
    assert client.delete(f"/api/appointment-calendars/{cid}/google").json()["connected"] is False
    with TestingSession() as db:
        assert db.scalar(select(AppointmentCalendar).where(AppointmentCalendar.client_id == uuid.UUID(cid))).encrypted_tokens is None


def test_google_cross_agency_routes_are_denied(authenticated_client):
    from app.models import Agency
    client = authenticated_client
    with TestingSession() as db:
        agency = Agency(name="Other agency", slug="other-calendar-agency")
        db.add(agency); db.flush()
        other = Client(agency_id=agency.id, name="Other business", portal_slug="other-calendar")
        db.add(other); db.commit()
        cid = str(other.id)
    for method, suffix, body in [("GET", "", None), ("POST", "/connect", None), ("GET", "/calendars", None),
                                  ("PUT", "/calendar", {"calendar_id": "test"}), ("DELETE", "", None), ("POST", "/retry", None)]:
        assert client.request(method, f"/api/appointment-calendars/{cid}/google{suffix}", **({"json": body} if body else {})).status_code == 404


def test_refresh_transport_and_provider_errors_are_sanitized(monkeypatch):
    row = AppointmentCalendar(connected=True)
    google.save_tokens(row, {"access_token": "expired-fixture", "refresh_token": "private-fixture", "expires_in": -1})
    seen = []
    class Transport:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, data):
            seen.append(data)
            return httpx.Response(200, json={"access_token": "new-fixture", "expires_in": 3600})
        def request(self, method, url, headers, **kwargs):
            assert headers["Authorization"] == "Bearer new-fixture"
            return httpx.Response(403, json={"error": "private-fixture must never escape"})
    monkeypatch.setattr(httpx, "Client", Transport)
    with pytest.raises(HTTPException) as error:
        google.request(row, "GET", "/users/me/calendarList")
    assert error.value.detail == "calendar_reconnect_required"
    assert seen[0]["grant_type"] == "refresh_token"
    assert json.loads(decrypt_secret(row.encrypted_tokens))["refresh_token"] == "private-fixture"


def test_google_freebusy_errors_all_day_and_pagination(authenticated_client, provider, monkeypatch):
    client = authenticated_client
    cid, sid, day = setup(client)
    connected(cid)
    start = slots(client, cid, sid, day)["slots"][0]["starts_at"]
    aid = client.post("/api/appointments", json=booking(cid, sid, start)).json()["id"]
    assert calendar_worker.process_one()
    original = google.request
    def paged(row, method, path, **kwargs):
        if path.endswith("/events") and method == "GET":
            if "pageToken" not in kwargs["params"]:
                return {"items": [], "nextPageToken": "page2"}
            return {"timeZone": "America/Mexico_City", "items": [{"id": "external-day", "start": {"date": day},
                "end": {"date": (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat()}}]}
        return original(row, method, path, **kwargs)
    monkeypatch.setattr(google, "request", paged)
    assert slots(client, cid, sid, day, aid)["slots"] == []
    monkeypatch.setattr(google, "request", lambda *args, **kwargs: {"calendars": {"test-calendar": {"errors": [{"reason": "notFound"}]}}})
    assert client.get("/api/appointments/availability", params={"client_id": cid, "service_id": sid, "date": day}).status_code == 502


def test_native_agent_uses_google_availability_and_pending_sync(authenticated_client, provider):
    from conftest import customer_conversation
    from app.models import Agent, Conversation
    from app.services.tools.appointments import build_appointment_specs
    client = authenticated_client
    cid, sid, day = setup(client)
    original = slots(client, cid, sid, day)["slots"][0]
    connected(cid)
    provider[2].append({"start": original["starts_at"], "end": original["ends_at"]})
    agent_id = client.post("/api/agents", json={"client_id": cid, "name": "Calendar agent", "appointments_enabled": True}).json()["id"]
    conversation_id = customer_conversation(client, agent_id)["id"]
    with TestingSession() as db:
        specs = {s.name: s for s in build_appointment_specs(db.get(Agent, uuid.UUID(agent_id)), db.get(Conversation, uuid.UUID(conversation_id)))}
    result, failed = specs["check_appointment_availability"].handler({"service_id": sid, "date": day})
    assert not failed
    available = json.loads(result)["slots"]
    assert original["starts_at"] not in {s["starts_at"] for s in available}
    result, failed = specs["create_appointment"].handler({"service_id": sid, "starts_at": available[0]["starts_at"], "customer_name": "Fixture"})
    assert not failed and json.loads(result)["appointment"]["calendar_sync_status"] == "pending"
    assert calendar_worker.process_one()
    assert len(provider[0]) == 1
