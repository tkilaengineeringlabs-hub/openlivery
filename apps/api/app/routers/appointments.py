"""Authenticated agency calendar APIs; every mutation shares the business lock."""
import uuid
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import get_current_user
from ..models import Appointment, AppointmentBlock, AppointmentService, AvailabilityRule, User
from ..schemas_appointments import AppointmentCreate, AppointmentPatch, AppointmentStatus, AvailabilityWrite, BlockCreate, Reschedule, ServiceCreate, ServicePatch, ServiceWrite
from ..services import appointments as engine

router = APIRouter(tags=["Appointments"])


def row_out(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.get("/appointments/availability")
def slots(client_id: uuid.UUID, service_id: uuid.UUID, date: date, exclude_id: uuid.UUID | None = None,
          db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return engine.get_availability(db, user.agency_id, client_id, service_id, date, exclude_id=exclude_id)


@router.get("/appointments")
def list_appointments(client_id: uuid.UUID, date_from: date, date_to: date,
    service_id: uuid.UUID | None = None, status: AppointmentStatus | None = None, search: str = Query(default="", max_length=180),
    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from datetime import datetime, time
    from zoneinfo import ZoneInfo
    client = engine.business(db, user.agency_id, client_id)
    if date_to < date_from or (date_to - date_from).days > 93:
        raise HTTPException(422, "invalid_date_range")
    zone = ZoneInfo(client.timezone)
    start, end = datetime.combine(date_from, time(), zone), datetime.combine(date_to + timedelta(days=1), time(), zone)
    query = select(Appointment).where(Appointment.agency_id == user.agency_id, Appointment.client_id == client_id,
        Appointment.starts_at < end, Appointment.ends_at > start)
    if service_id:
        engine.service(db, user.agency_id, client_id, service_id)
        query = query.where(Appointment.service_id == service_id)
    if status:
        query = query.where(Appointment.status == status)
    if search.strip():
        pattern = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(or_(Appointment.customer_name.ilike(pattern, escape="\\"),
            Appointment.customer_phone.ilike(pattern, escape="\\"), Appointment.customer_email.ilike(pattern, escape="\\")))
    return [engine.appointment_out(row) for row in db.scalars(query.order_by(Appointment.starts_at))]


@router.post("/appointments", status_code=201)
def create(payload: AppointmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = engine.create_appointment(db, user.agency_id, payload)
    db.commit()
    return engine.appointment_out(row)


@router.get("/appointments/{appointment_id}")
def get(appointment_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return engine.appointment_out(engine.owned(db, user.agency_id, appointment_id))


@router.patch("/appointments/{appointment_id}")
def update(appointment_id: uuid.UUID, payload: AppointmentPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = engine.owned(db, user.agency_id, appointment_id)
    engine.business(db, user.agency_id, row.client_id, lock=True)
    db.refresh(row)
    values = payload.model_dump(exclude_unset=True)
    if any(values.get(key, "") is None for key in ("customer_name", "notes", "status")):
        raise HTTPException(422, "invalid_appointment")
    status = values.pop("status", None)
    for key, value in values.items():
        setattr(row, key, value)
    db.flush()
    if status:
        row = engine.change_status(db, user.agency_id, appointment_id, status)
    if values and row.status in engine.ACTIVE:
        row.revision += 1
        db.flush()
        engine.emit_booking_event(db, row, None)
    from ..services.google_calendar import enqueue
    enqueue(db, row)
    db.commit()
    return engine.appointment_out(row)


@router.post("/appointments/{appointment_id}/reschedule")
def reschedule(appointment_id: uuid.UUID, payload: Reschedule, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = engine.reschedule_appointment(db, user.agency_id, appointment_id, payload.starts_at, payload.service_id)
    db.commit()
    return engine.appointment_out(row)


@router.post("/appointments/{appointment_id}/cancel")
def cancel(appointment_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = engine.cancel_appointment(db, user.agency_id, appointment_id)
    db.commit()
    return engine.appointment_out(row)


@router.post("/appointments/{appointment_id}/complete")
def complete(appointment_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = engine.change_status(db, user.agency_id, appointment_id, "completed")
    db.commit()
    return engine.appointment_out(row)


@router.post("/appointments/{appointment_id}/no-show")
def no_show(appointment_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = engine.change_status(db, user.agency_id, appointment_id, "no_show")
    db.commit()
    return engine.appointment_out(row)


@router.delete("/appointments/{appointment_id}", status_code=204)
def remove(appointment_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Cancellation preserves the audit trail and suppresses old reminders.
    engine.cancel_appointment(db, user.agency_id, appointment_id)
    db.commit()
    return Response(status_code=204)


@router.get("/appointment-services")
def services(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    engine.business(db, user.agency_id, client_id)
    return [row_out(row) for row in db.scalars(select(AppointmentService).where(AppointmentService.agency_id == user.agency_id,
        AppointmentService.client_id == client_id).order_by(AppointmentService.name))]


@router.post("/appointment-services", status_code=201)
def create_service(payload: ServiceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    engine.business(db, user.agency_id, payload.client_id, lock=True)
    row = AppointmentService(agency_id=user.agency_id, **payload.model_dump())
    db.add(row); db.commit()
    return row_out(row)


def owned_service(db, user, service_id):
    row = db.scalar(select(AppointmentService).where(AppointmentService.id == service_id, AppointmentService.agency_id == user.agency_id))
    if not row:
        raise HTTPException(404, "service_not_found")
    engine.business(db, user.agency_id, row.client_id, lock=True)
    db.refresh(row)
    return row


@router.patch("/appointment-services/{service_id}")
def update_service(service_id: uuid.UUID, payload: ServicePatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = owned_service(db, user, service_id)
    values = {key: getattr(row, key) for key in ServiceWrite.model_fields}
    values.update(payload.model_dump(exclude_unset=True))
    try:
        validated = ServiceWrite.model_validate(values)
    except ValidationError:
        raise HTTPException(422, "invalid_service") from None
    for key, value in validated.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return row_out(row)


@router.delete("/appointment-services/{service_id}", status_code=204)
def delete_service(service_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = owned_service(db, user, service_id)
    row.active = False
    db.commit()
    return Response(status_code=204)


@router.get("/availability")
def availability(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = engine.business(db, user.agency_id, client_id)
    rules = db.scalars(select(AvailabilityRule).where(AvailabilityRule.agency_id == user.agency_id, AvailabilityRule.client_id == client_id)
        .order_by(AvailabilityRule.weekday, AvailabilityRule.start_time)).all()
    return {"client_id": client.id, "timezone": client.timezone, "slot_minutes": client.appointment_slot_minutes,
        "min_notice_minutes": client.appointment_min_notice_minutes, "booking_days": client.appointment_booking_days,
        "reminders": client.appointment_reminders, "rules": [row_out(r) for r in rules]}


@router.put("/availability")
def save_availability(payload: AvailabilityWrite, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = engine.business(db, user.agency_id, payload.client_id, lock=True)
    client.timezone, client.appointment_slot_minutes = payload.timezone, payload.slot_minutes
    client.appointment_min_notice_minutes, client.appointment_booking_days = payload.min_notice_minutes, payload.booking_days
    client.appointment_reminders = sorted(set(payload.reminders))
    db.execute(delete(AvailabilityRule).where(AvailabilityRule.agency_id == user.agency_id, AvailabilityRule.client_id == client.id))
    for rule in payload.rules:
        db.add(AvailabilityRule(agency_id=user.agency_id, client_id=client.id, **rule.model_dump()))
    db.commit()
    return availability(client.id, db, user)


@router.get("/appointment-blocks")
def blocks(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    engine.business(db, user.agency_id, client_id)
    return [row_out(row) for row in db.scalars(select(AppointmentBlock).where(AppointmentBlock.agency_id == user.agency_id,
        AppointmentBlock.client_id == client_id).order_by(AppointmentBlock.starts_at))]


@router.post("/appointment-blocks", status_code=201)
def create_block(payload: BlockCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = engine.business(db, user.agency_id, payload.client_id, lock=True)
    # Do not silently invalidate a previously promised appointment.
    if engine.occupied(db, client, payload.starts_at, payload.ends_at):
        raise HTTPException(409, "block_conflict")
    row = AppointmentBlock(agency_id=user.agency_id, **payload.model_dump())
    db.add(row); db.commit()
    return row_out(row)


@router.delete("/appointment-blocks/{block_id}", status_code=204)
def delete_block(block_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.scalar(select(AppointmentBlock).where(AppointmentBlock.id == block_id, AppointmentBlock.agency_id == user.agency_id))
    if not row:
        raise HTTPException(404, "block_not_found")
    engine.business(db, user.agency_id, row.client_id, lock=True)
    db.delete(row); db.commit()
    return Response(status_code=204)
