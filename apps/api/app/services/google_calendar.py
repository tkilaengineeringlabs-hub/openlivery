"""Google Calendar boundary. Tokens and raw provider errors never leave this module."""
import json
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from ..config import get_settings
from ..models import Appointment, AppointmentCalendar, now_utc
from ..security import decrypt_secret, encrypt_secret

BASE = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.calendarlist.readonly https://www.googleapis.com/auth/calendar.freebusy https://www.googleapis.com/auth/userinfo.email"


def connection(db, client):
    return db.scalar(select(AppointmentCalendar).where(AppointmentCalendar.agency_id == client.agency_id,
                                                       AppointmentCalendar.client_id == client.id))


def configured():
    s = get_settings()
    return bool(s.google_calendar_client_id and s.google_calendar_client_secret and s.google_calendar_redirect_uri)


def token_request(data):
    settings = get_settings()
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as http:
            response = http.post("https://oauth2.googleapis.com/token", data={**data,
                "client_id": settings.google_calendar_client_id, "client_secret": settings.google_calendar_client_secret})
        if response.status_code != 200:
            raise HTTPException(502, "calendar_reconnect_required")
        result = response.json()
        if not result.get("access_token"):
            raise ValueError()
        return result
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(502, "calendar_unavailable") from None


def account_email(access_token):
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as http:
        response = http.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": "Bearer " + access_token})
    if response.status_code != 200:
        raise HTTPException(502, "calendar_account_unavailable")
    return response.json().get("email")


def save_tokens(row, tokens):
    tokens = dict(tokens)
    tokens["expires_at"] = (now_utc() + timedelta(seconds=int(tokens.get("expires_in", 3600)))).timestamp()
    row.encrypted_tokens = encrypt_secret(json.dumps(tokens))


def request(row, method, path, *, allowed=(), **kwargs):
    if not row or not row.connected or not row.encrypted_tokens:
        raise HTTPException(409, "calendar_not_connected")
    try:
        tokens = json.loads(decrypt_secret(row.encrypted_tokens))
        if tokens.get("expires_at", 0) < now_utc().timestamp() + 60:
            refreshed = token_request({"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
            tokens.update(refreshed)
            save_tokens(row, tokens)
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as http:
            response = http.request(method, BASE + path, headers={"Authorization": "Bearer " + tokens["access_token"]}, **kwargs)
        if response.status_code in allowed:
            return {"_status": response.status_code}
        if response.status_code >= 300:
            raise HTTPException(502, "calendar_reconnect_required" if response.status_code in (401, 403) else "calendar_unavailable")
        return response.json() if response.content else {}
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(502, "calendar_unavailable") from None


def calendars(row):
    result, page = [], None
    while True:
        response = request(row, "GET", "/users/me/calendarList", params={"minAccessRole": "writer", **({"pageToken": page} if page else {})})
        result.extend({"id": item["id"], "name": item.get("summary", item["id"]), "primary": item.get("primary", False)} for item in response.get("items", []))
        page = response.get("nextPageToken")
        if not page:
            return result


def event_path(calendar_id, event_id=None):
    return "/calendars/" + quote(calendar_id, safe="") + "/events" + ("/" + quote(event_id, safe="") if event_id else "")


def busy_spans(db, client, start, end, exclude_id=None):
    row = connection(db, client)
    if not row or not row.connected:
        return []
    if not row.calendar_id:
        raise HTTPException(409, "calendar_selection_required")
    excluded = db.get(Appointment, exclude_id) if exclude_id else None
    if excluded and (excluded.client_id != client.id or excluded.agency_id != client.agency_id):
        raise HTTPException(404, "appointment_not_found")
    if not excluded or not excluded.external_event_id or excluded.external_calendar_id != row.calendar_id:
        data = request(row, "POST", "/freeBusy", json={"timeMin": start.isoformat(), "timeMax": end.isoformat(),
            "timeZone": client.timezone, "items": [{"id": row.calendar_id}]})
        calendar = data.get("calendars", {}).get(row.calendar_id)
        if calendar is None or calendar.get("errors"):
            raise HTTPException(502, "calendar_unavailable")
        return [(datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])) for b in calendar.get("busy", [])]
    # FreeBusy merges intervals and cannot exclude one event. Enumerate expanded
    # instances when moving a linked appointment, preserving overlapping events.
    spans, page = [], None
    while True:
        data = request(row, "GET", event_path(row.calendar_id), params={"timeMin": start.isoformat(), "timeMax": end.isoformat(),
            "singleEvents": "true", "timeZone": client.timezone, "maxResults": 2500, **({"pageToken": page} if page else {})})
        for event in data.get("items", []):
            if event.get("status") == "cancelled" or event.get("transparency") == "transparent":
                continue
            if event.get("id") == excluded.external_event_id and is_ours(event, excluded):
                continue
            def instant(value):
                if "dateTime" in value:
                    return datetime.fromisoformat(value["dateTime"])
                return datetime.fromisoformat(value["date"]).replace(tzinfo=ZoneInfo(data.get("timeZone", client.timezone)))
            spans.append((instant(event["start"]), instant(event["end"])))
        page = data.get("nextPageToken")
        if not page:
            return spans


def is_ours(event, appointment):
    private = event.get("extendedProperties", {}).get("private", {})
    return private.get("tkila_appointment_id") == str(appointment.id) and private.get("tkila_client_id") == str(appointment.client_id)


def enqueue(db, appointment):
    row = db.scalar(select(AppointmentCalendar).where(AppointmentCalendar.agency_id == appointment.agency_id,
                                                     AppointmentCalendar.client_id == appointment.client_id))
    if not appointment.external_event_id and row and row.connected and row.calendar_id:
        appointment.external_provider = "google"
        appointment.external_calendar_id = row.calendar_id
        appointment.external_event_id = "tkila" + appointment.id.hex
    if appointment.external_event_id:
        appointment.calendar_sync_status = "pending"
        appointment.calendar_sync_error = None
        appointment.calendar_sync_attempts = 0
        appointment.calendar_retry_at = now_utc()


def sync(db, appointment, row):
    if not row or not row.connected or appointment.external_calendar_id != row.calendar_id:
        raise HTTPException(409, "calendar_reconnect_required")
    path = event_path(appointment.external_calendar_id, appointment.external_event_id)
    event = request(row, "GET", path, allowed=(404, 410))
    missing = event.get("_status") in (404, 410)
    if not missing and not is_ours(event, appointment):
        raise HTTPException(409, "calendar_event_ownership_mismatch")
    if appointment.status == "cancelled":
        if not missing and event.get("status") != "cancelled":
            request(row, "DELETE", path, allowed=(404, 410), params={"sendUpdates": "none"})
    else:
        body = {"summary": appointment.service_name + " · " + appointment.customer_name,
            "description": appointment.notes,
            "start": {"dateTime": appointment.starts_at.isoformat(), "timeZone": appointment.timezone},
            "end": {"dateTime": appointment.ends_at.isoformat(), "timeZone": appointment.timezone},
            "extendedProperties": {"private": {"tkila_appointment_id": str(appointment.id), "tkila_client_id": str(appointment.client_id)}},
            "reminders": {"useDefault": False}}
        if missing:
            result = request(row, "POST", event_path(row.calendar_id), allowed=(409,), params={"sendUpdates": "none"},
                             json={"id": appointment.external_event_id, **body})
            if result.get("_status") == 409:
                # A previous uncertain insert may have succeeded. Verify ownership
                # before the next retry updates it; never insert a random new ID.
                raise HTTPException(409, "calendar_retry_required")
        else:
            request(row, "PATCH", path, json=body, params={"sendUpdates": "none"})
    appointment.calendar_sync_status = "synced"
    appointment.calendar_sync_error = None
    appointment.calendar_synced_at = now_utc()
    appointment.calendar_retry_at = None
