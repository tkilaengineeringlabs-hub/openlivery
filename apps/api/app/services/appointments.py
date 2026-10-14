"""One capacity per business. All calendar mutations lock its Client row.

Slots use IANA wall time; persisted instants and occupied buffer ranges use UTC.
No business date is derived from the server's local timezone.
"""
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Agent, Appointment, AppointmentBlock, AppointmentService, AvailabilityRule, Client, Conversation, now_utc
from ..schemas_appointments import AppointmentCreate

ACTIVE = ("scheduled", "confirmed")


def business(db: Session, agency_id, client_id, *, lock=False):
    query = select(Client).where(Client.id == client_id, Client.agency_id == agency_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if not row:
        raise HTTPException(404, "client_not_found")
    return row


def service(db, agency_id, client_id, service_id, *, active=False):
    row = db.scalar(select(AppointmentService).where(AppointmentService.id == service_id,
        AppointmentService.agency_id == agency_id, AppointmentService.client_id == client_id))
    if not row:
        raise HTTPException(404, "service_not_found")
    if active and not row.active:
        raise HTTPException(409, "service_inactive")
    return row


def owned(db, agency_id, appointment_id):
    row = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.agency_id == agency_id))
    if not row:
        raise HTTPException(404, "appointment_not_found")
    return row


def local_instants(wall: datetime, zone: ZoneInfo):
    """Return both folds, or none for a nonexistent DST wall time."""
    result = set()
    for fold in (0, 1):
        stamp = wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if stamp.astimezone(zone).replace(tzinfo=None) == wall:
            result.add(stamp)
    return sorted(result)


def working_intervals(db, client, day):
    zone = ZoneInfo(client.timezone)
    rules = db.scalars(select(AvailabilityRule).where(AvailabilityRule.agency_id == client.agency_id,
        AvailabilityRule.client_id == client.id, AvailabilityRule.weekday == day.weekday(), AvailabilityRule.active.is_(True))).all()
    intervals = []
    for rule in rules:
        starts = local_instants(datetime.combine(day, rule.start_time), zone)
        ends = local_instants(datetime.combine(day, rule.end_time), zone)
        if starts and ends:
            intervals.append((min(starts), max(ends)))
    return intervals


def occupied(db, client, start, end, exclude_id=None):
    query = select(Appointment).where(Appointment.agency_id == client.agency_id, Appointment.client_id == client.id,
        Appointment.status.in_(ACTIVE), Appointment.reserved_starts_at < end, Appointment.reserved_ends_at > start)
    if exclude_id:
        query = query.where(Appointment.id != exclude_id)
    spans = [(a.reserved_starts_at, a.reserved_ends_at) for a in db.scalars(query)]
    spans += [(b.starts_at, b.ends_at) for b in db.scalars(select(AppointmentBlock).where(
        AppointmentBlock.agency_id == client.agency_id, AppointmentBlock.client_id == client.id,
        AppointmentBlock.starts_at < end, AppointmentBlock.ends_at > start))]
    return spans


def get_available_slots(db, client, selected_service, day, *, exclude_id=None):
    if not client.is_active or not selected_service.active:
        return []
    now = now_utc()
    if day > now.astimezone(ZoneInfo(client.timezone)).date() + timedelta(days=client.appointment_booking_days):
        return []
    intervals = working_intervals(db, client, day)
    if not intervals:
        return []
    before = timedelta(minutes=selected_service.buffer_before_minutes)
    duration = timedelta(minutes=selected_service.duration_minutes)
    after = timedelta(minutes=selected_service.buffer_after_minutes)
    taken = occupied(db, client, min(s for s, _ in intervals), max(e for _, e in intervals), exclude_id)
    from .google_calendar import busy_spans
    taken += busy_spans(db, client, min(s for s, _ in intervals), max(e for _, e in intervals), exclude_id)
    now = now_utc()
    earliest = now + timedelta(minutes=client.appointment_min_notice_minutes)
    result = {}
    for opening, closing in intervals:
        start = opening
        while start + duration + after <= closing:
            reserved_start, reserved_end = start - before, start + duration + after
            if start > earliest and reserved_start >= opening and not any(a < reserved_end and b > reserved_start for a, b in taken):
                result[start] = {"starts_at": start, "ends_at": start + duration, "available": True}
            start += timedelta(minutes=client.appointment_slot_minutes)
    return [result[key] for key in sorted(result)]


def get_availability(db, agency_id, client_id, service_id, day, *, exclude_id=None):
    client = business(db, agency_id, client_id)
    selected_service = service(db, agency_id, client.id, service_id, active=True)
    if exclude_id:
        existing = owned(db, agency_id, exclude_id)
        if existing.client_id != client.id:
            raise HTTPException(404, "appointment_not_found")
    return {"date": day.isoformat(), "timezone": client.timezone,
        "slots": get_available_slots(db, client, selected_service, day, exclude_id=exclude_id)}


def is_slot_available(db, client, selected_service, starts_at, *, exclude_id=None):
    starts_at = starts_at.astimezone(timezone.utc)
    day = starts_at.astimezone(ZoneInfo(client.timezone)).date()
    return any(slot["starts_at"] == starts_at for slot in get_available_slots(db, client, selected_service, day, exclude_id=exclude_id))


def assign_slot(db, client, appointment, selected_service, starts_at, *, exclude_id=None):
    if not is_slot_available(db, client, selected_service, starts_at, exclude_id=exclude_id):
        raise HTTPException(409, "slot_unavailable")
    appointment.starts_at = starts_at.astimezone(timezone.utc)
    appointment.ends_at = appointment.starts_at + timedelta(minutes=selected_service.duration_minutes)
    appointment.reserved_starts_at = appointment.starts_at - timedelta(minutes=selected_service.buffer_before_minutes)
    appointment.reserved_ends_at = appointment.ends_at + timedelta(minutes=selected_service.buffer_after_minutes)
    appointment.timezone, appointment.service_id, appointment.service_name = client.timezone, selected_service.id, selected_service.name


def emit_booking_event(db, appointment, event_type):
    # Persist the booking even if an individual automation rule fails.
    from .automations.appointments import appointment_event
    try:
        with db.begin_nested():
            appointment_event(db, appointment, event_type)
    except Exception:
        logging.getLogger(__name__).exception("Appointment automation dispatch failed")


def create_appointment(db, agency_id, payload: AppointmentCreate, *, source=None):
    client = business(db, agency_id, payload.client_id, lock=True)
    if not client.is_active:
        raise HTTPException(409, "client_inactive")
    selected_service = service(db, agency_id, client.id, payload.service_id, active=True)
    values = payload.model_dump(exclude={"starts_at", "service_id", "source"})
    if payload.agent_id and not db.scalar(select(Agent.id).where(Agent.id == payload.agent_id,
        Agent.agency_id == agency_id, Agent.client_id == client.id, Agent.deleted_at.is_(None))):
        raise HTTPException(404, "agent_not_found")
    if payload.conversation_id:
        conversation = db.scalar(select(Conversation).where(Conversation.id == payload.conversation_id,
            Conversation.agency_id == agency_id, Conversation.client_id == client.id, Conversation.channel != "playground"))
        if not conversation or (payload.agent_id and conversation.agent_id != payload.agent_id):
            raise HTTPException(404, "conversation_not_found")
        values["agent_id"] = conversation.agent_id
        if not values["customer_phone"] and conversation.contact:
            values["customer_phone"] = conversation.contact.phone
        if not values["customer_email"] and conversation.contact:
            values["customer_email"] = conversation.contact.email
    appointment = Appointment(agency_id=agency_id, source=source or payload.source, **values)
    assign_slot(db, client, appointment, selected_service, payload.starts_at)
    db.add(appointment)
    db.flush()
    from .google_calendar import enqueue
    enqueue(db, appointment)
    emit_booking_event(db, appointment, "appointment_created")
    return appointment


def reschedule_appointment(db, agency_id, appointment_id, starts_at, service_id=None):
    initial = owned(db, agency_id, appointment_id)
    client = business(db, agency_id, initial.client_id, lock=True)
    db.refresh(initial)
    if initial.status not in ACTIVE:
        raise HTTPException(409, "appointment_closed")
    selected_service = service(db, agency_id, client.id, service_id or initial.service_id, active=True)
    assign_slot(db, client, initial, selected_service, starts_at, exclude_id=initial.id)
    initial.revision += 1
    db.flush()
    from .google_calendar import enqueue
    enqueue(db, initial)
    emit_booking_event(db, initial, "appointment_rescheduled")
    return initial


def change_status(db, agency_id, appointment_id, status):
    row = owned(db, agency_id, appointment_id)
    business(db, agency_id, row.client_id, lock=True)
    db.refresh(row)
    if row.status == status:
        return row
    if row.status not in ACTIVE or status not in {"confirmed", "completed", "cancelled", "no_show"}:
        raise HTTPException(409, "appointment_closed")
    row.status = status
    if status == "cancelled":
        row.cancelled_at = now_utc()
    if status != "confirmed":
        row.revision += 1
    db.flush()
    from .google_calendar import enqueue
    enqueue(db, row)
    if status in {"cancelled", "completed"}:
        emit_booking_event(db, row, f"appointment_{status}")
    elif status == "no_show":
        from .automations.appointments import invalidate_reminders
        invalidate_reminders(db, row)
    return row


def cancel_appointment(db, agency_id, appointment_id):
    return change_status(db, agency_id, appointment_id, "cancelled")


def appointment_out(row):
    fields = ("id", "agency_id", "client_id", "agent_id", "conversation_id", "service_id", "service_name", "customer_name",
        "external_provider", "external_calendar_id", "calendar_sync_status", "calendar_sync_error", "calendar_synced_at",
        "customer_phone", "customer_email", "starts_at", "ends_at", "timezone", "status", "source", "notes", "created_at", "updated_at", "cancelled_at")
    return {key: getattr(row, key) for key in fields}
