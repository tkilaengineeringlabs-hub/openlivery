"""Agency-authenticated Google authorization and client calendar settings."""
import base64
import hashlib
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Appointment, AppointmentCalendar, AppointmentCalendarOAuth, User, now_utc
from ..schemas_appointments import Strict
from ..security import decrypt_secret, encrypt_secret
from ..services import appointments as engine, google_calendar as google

router = APIRouter(prefix="/appointment-calendars", tags=["Appointment calendars"])


class CalendarSelection(Strict):
    calendar_id: str = Field(min_length=1, max_length=1024)


def client_connection(db, user, client_id, *, lock=False):
    client = engine.business(db, user.agency_id, client_id, lock=lock)
    return client, google.connection(db, client)


@router.get("/{client_id}/google")
def status(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, row = client_connection(db, user, client_id)
    counts = dict(db.execute(select(Appointment.calendar_sync_status, func.count()).where(
        Appointment.agency_id == user.agency_id, Appointment.client_id == client_id,
        Appointment.external_provider == "google").group_by(Appointment.calendar_sync_status)).all())
    return {"configured": google.configured(), "connected": bool(row and row.connected),
        "account_email": row.account_email if row else None, "calendar_id": row.calendar_id if row else None,
        "calendar_name": row.calendar_name if row else None, "sync_counts": counts}


@router.post("/{client_id}/google/connect")
def connect(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client_connection(db, user, client_id, lock=True)
    if not google.configured():
        raise HTTPException(503, "calendar_oauth_not_configured")
    s = get_settings()
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    db.execute(delete(AppointmentCalendarOAuth).where(AppointmentCalendarOAuth.expires_at < now_utc()))
    db.execute(delete(AppointmentCalendarOAuth).where(AppointmentCalendarOAuth.client_id == client_id,
        AppointmentCalendarOAuth.agency_id == user.agency_id, AppointmentCalendarOAuth.user_id == user.id))
    db.add(AppointmentCalendarOAuth(id=hashlib.sha256(state.encode()).hexdigest(), agency_id=user.agency_id,
        client_id=client_id, user_id=user.id, encrypted_verifier=encrypt_secret(verifier), expires_at=now_utc() + timedelta(minutes=10)))
    db.commit()
    return {"url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({"client_id": s.google_calendar_client_id,
        "redirect_uri": s.google_calendar_redirect_uri, "response_type": "code", "scope": google.SCOPES,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("="),
        "code_challenge_method": "S256"})}


@router.get("/google/callback")
def callback(state: str = Query(max_length=256), code: str | None = Query(default=None, max_length=4096),
             error: str | None = Query(default=None, max_length=256),
             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    oauth = db.scalar(select(AppointmentCalendarOAuth).where(AppointmentCalendarOAuth.id == hashlib.sha256(state.encode()).hexdigest(),
        AppointmentCalendarOAuth.user_id == user.id, AppointmentCalendarOAuth.agency_id == user.agency_id).with_for_update())
    if not oauth or oauth.expires_at <= now_utc():
        raise HTTPException(400, "calendar_invalid_oauth_state")
    client_id, verifier = oauth.client_id, decrypt_secret(oauth.encrypted_verifier)
    engine.business(db, user.agency_id, client_id)
    db.delete(oauth)
    db.commit()  # Consume once, including denial and failed exchanges.
    result = "denied" if error or not code else "connected"
    if result == "connected":
        try:
            tokens = google.token_request({"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
                                           "redirect_uri": get_settings().google_calendar_redirect_uri})
            if not tokens.get("refresh_token") or not set(google.SCOPES.split()).issubset(set(tokens.get("scope", "").split())):
                raise HTTPException(400, "calendar_permissions_required")
            client, row = client_connection(db, user, client_id, lock=True)
            # Email is informational only; calendar ownership is checked separately.
            account = google.account_email(tokens["access_token"])
            if row and row.account_email and row.account_email != account and row.calendar_id:
                raise HTTPException(409, "calendar_account_mismatch")
            if not row:
                row = AppointmentCalendar(agency_id=user.agency_id, client_id=client.id)
                db.add(row)
            google.save_tokens(row, tokens)
            row.connected, row.account_email = True, account
            choices = google.calendars(row)
            if row.calendar_id and row.calendar_id not in {c["id"] for c in choices}:
                raise HTTPException(409, "calendar_access_lost")
            db.commit()
        except (HTTPException, httpx.HTTPError, ValueError, KeyError):
            db.rollback()
            result = "failed"
    return RedirectResponse(get_settings().frontend_url.rstrip("/") + "/appointments?" + urlencode({"client_id": str(client_id), "calendar": result}),
                            status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/{client_id}/google/calendars")
def calendars(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, row = client_connection(db, user, client_id, lock=True)
    result = google.calendars(row)
    db.commit()
    return result


@router.put("/{client_id}/google/calendar")
def select_calendar(client_id: uuid.UUID, payload: CalendarSelection, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, row = client_connection(db, user, client_id, lock=True)
    choice = next((c for c in google.calendars(row) if c["id"] == payload.calendar_id), None)
    if not choice:
        raise HTTPException(422, "calendar_not_writable")
    # A mapping remains pinned: switching must never orphan or retarget events.
    linked = db.scalar(select(Appointment.id).where(Appointment.client_id == client_id, Appointment.agency_id == user.agency_id,
                                                   Appointment.external_event_id.is_not(None)).limit(1))
    if linked and row.calendar_id != choice["id"]:
        raise HTTPException(409, "calendar_has_linked_appointments")
    row.calendar_id, row.calendar_name = choice["id"], choice["name"]
    db.commit()
    return status(client_id, db, user)


@router.delete("/{client_id}/google")
def disconnect(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, row = client_connection(db, user, client_id, lock=True)
    if row:
        row.encrypted_tokens, row.connected = None, False
    db.execute(delete(AppointmentCalendarOAuth).where(AppointmentCalendarOAuth.client_id == client_id,
                                                     AppointmentCalendarOAuth.agency_id == user.agency_id))
    db.commit()
    return status(client_id, db, user)


@router.post("/{client_id}/google/retry")
def retry(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, row = client_connection(db, user, client_id, lock=True)
    if not row or not row.connected or not row.calendar_id:
        raise HTTPException(409, "calendar_not_connected")
    for appointment in db.scalars(select(Appointment).where(Appointment.client_id == client_id,
        Appointment.agency_id == user.agency_id, Appointment.calendar_sync_status == "error")):
        google.enqueue(db, appointment)
    db.commit()
    return status(client_id, db, user)
