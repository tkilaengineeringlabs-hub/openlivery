"""Durable Google sync using appointment rows; serializes with booking mutations."""
import asyncio
import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select

from ..database import new_session
from ..models import Appointment, Client, now_utc
from . import google_calendar as google


def process_one():
    with new_session() as db:
        # Lock the client first, matching the booking/configuration lock order.
        eligible = select(Appointment.client_id).where(Appointment.calendar_sync_status == "pending",
            or_(Appointment.calendar_retry_at.is_(None), Appointment.calendar_retry_at <= now_utc()))
        client = db.scalar(select(Client).where(Client.id.in_(eligible)).order_by(Client.id)
                           .with_for_update(skip_locked=True).limit(1))
        if not client:
            return False
        appointment = db.scalar(select(Appointment).where(Appointment.client_id == client.id,
            Appointment.agency_id == client.agency_id, Appointment.calendar_sync_status == "pending",
            or_(Appointment.calendar_retry_at.is_(None), Appointment.calendar_retry_at <= now_utc()))
            .order_by(Appointment.calendar_retry_at).limit(1))
        if not appointment:
            return False
        try:
            google.sync(db, appointment, google.connection(db, client))
        except Exception as exc:
            appointment.calendar_sync_attempts += 1
            # Never persist raw provider/transport errors (may contain credentials).
            appointment.calendar_sync_error = exc.detail if isinstance(exc, HTTPException) else "calendar_unavailable"
            appointment.calendar_sync_status = "error" if appointment.calendar_sync_attempts >= 5 else "pending"
            appointment.calendar_retry_at = now_utc() + timedelta(seconds=min(900, 15 * 2 ** appointment.calendar_sync_attempts))
        db.commit()
        return True


async def worker_loop():
    while True:
        try:
            worked = await asyncio.to_thread(process_one)
        except Exception:
            logging.getLogger(__name__).warning("Calendar sync transaction failed; durable work will be retried")
            worked = False
        await asyncio.sleep(0.1 if worked else 5)
