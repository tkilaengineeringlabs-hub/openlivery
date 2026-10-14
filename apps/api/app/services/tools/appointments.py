"""Native booking tools, scoped to the agent and the current verified conversation."""
import json
import uuid
from datetime import date as Date
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from pydantic import AwareDatetime, EmailStr, Field, ValidationError
from sqlalchemy import or_, select
from ...database import new_session
from ...models import Agent, Appointment, AppointmentService, Conversation, now_utc
from ...schemas_appointments import AppointmentCreate, Strict
from .. import appointments as calendar
from .specs import ToolSpec


class CheckAvailability(Strict):
    appointment_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    date: Date | None = None


class Book(Strict):
    service_id: uuid.UUID
    starts_at: AwareDatetime
    customer_name: str = Field(min_length=1, max_length=180)
    customer_phone: str | None = Field(default=None, max_length=40)
    customer_email: EmailStr | None = None
    notes: str = Field(default="", max_length=8000)


class Move(Strict):
    appointment_id: uuid.UUID
    starts_at: AwareDatetime


class Cancel(Strict):
    appointment_id: uuid.UUID


def build_appointment_specs(agent, conversation):
    if not agent.appointments_enabled or not conversation or conversation.channel == "playground":
        return []
    agency_id, client_id, agent_id, conversation_id = agent.agency_id, agent.client_id, agent.id, conversation.id

    def handler(kind, schema):
        def execute(arguments):
            try:
                args = schema.model_validate(arguments)
                with new_session() as db:
                    current_agent = db.scalar(select(Agent).where(Agent.id == agent_id, Agent.agency_id == agency_id,
                        Agent.client_id == client_id, Agent.appointments_enabled.is_(True), Agent.is_active.is_(True), Agent.deleted_at.is_(None)))
                    current = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.agency_id == agency_id,
                        Conversation.client_id == client_id, Conversation.agent_id == agent_id, Conversation.channel != "playground"))
                    client = calendar.business(db, agency_id, client_id)
                    if (not current_agent or not current or not client.is_active or current.mode != "ai" or current.status != "open"
                            or (current.contact and current.contact.blocked_at)):
                        raise HTTPException(403, "appointments_unavailable")
                    from ..objectives import calendar_ready, calendar_config
                    if not calendar_ready(db, current_agent, kind):
                        raise HTTPException(403, "appointments_unavailable")
                    cfg = calendar_config(current_agent, kind) if current_agent.objectives_managed else {}
                    allowed_services = cfg.get("service_ids", [])
                    if allowed_services and getattr(args, "service_id", None) and str(args.service_id) not in allowed_services:
                        raise HTTPException(403, "service_not_allowed")
                    customer_scope = [Appointment.conversation_id == current.id]
                    if current.contact_id:
                        related = select(Conversation.id).where(Conversation.agency_id == agency_id,
                            Conversation.client_id == client_id, Conversation.contact_id == current.contact_id)
                        customer_scope.append(Appointment.conversation_id.in_(related))
                    owned_query = select(Appointment).where(Appointment.agency_id == agency_id,
                        Appointment.client_id == client_id, or_(*customer_scope))
                    if kind == "check_appointment_availability":
                        catalog = db.scalars(select(AppointmentService).where(AppointmentService.agency_id == agency_id,
                            AppointmentService.client_id == client_id, AppointmentService.active.is_(True), *([AppointmentService.id.in_([uuid.UUID(value) for value in allowed_services])] if allowed_services else []))).all()
                        result = {"ok": True, "timezone": client.timezone, "business_now": now_utc().astimezone(ZoneInfo(client.timezone)).isoformat(),
                            "customer": {"name": current.contact.name, "phone": current.contact.phone, "email": current.contact.email} if current.contact else {"name": current.contact_name},
                            "services": [{"id": str(s.id), "name": s.name, "duration_minutes": s.duration_minutes} for s in catalog],
                            "customer_appointments": [calendar.appointment_out(a) for a in db.scalars(owned_query.where(Appointment.status.in_(calendar.ACTIVE)).order_by(Appointment.starts_at).limit(20))]}
                        if args.service_id and args.date:
                            if args.appointment_id and not db.scalar(owned_query.where(Appointment.id == args.appointment_id)):
                                raise HTTPException(404, "appointment_not_found")
                            result.update(calendar.get_availability(db, agency_id, client_id, args.service_id, args.date, exclude_id=args.appointment_id))
                    elif kind == "create_appointment":
                        payload = AppointmentCreate(client_id=client_id, agent_id=agent_id, conversation_id=conversation_id, **args.model_dump())
                        booked = calendar.create_appointment(db, agency_id, payload, source="agent")
                        db.commit()  # Never report success before the booking is durable.
                        result = {"ok": True, "appointment": calendar.appointment_out(booked)}
                    else:
                        booked = db.scalar(owned_query.where(Appointment.id == args.appointment_id))
                        if booked and allowed_services and str(booked.service_id) not in allowed_services:
                            raise HTTPException(403, "service_not_allowed")
                        if not booked:
                            raise HTTPException(404, "appointment_not_found")
                        if kind == "reschedule_appointment":
                            booked = calendar.reschedule_appointment(db, agency_id, booked.id, args.starts_at)
                        else:
                            booked = calendar.cancel_appointment(db, agency_id, booked.id)
                        db.commit()
                        result = {"ok": True, "appointment": calendar.appointment_out(booked)}
                    return json.dumps(result, default=str), False
            except (ValidationError, HTTPException) as exc:
                error = exc.detail if isinstance(exc, HTTPException) else "invalid_arguments"
                return json.dumps({"ok": False, "error": error,
                    "instruction": "Do not confirm a booking. For a slot conflict, check availability again and offer alternatives."}), True
            except Exception:
                return json.dumps({"ok": False, "error": "booking_failed", "instruction": "Do not confirm success. Check current appointments before retrying."}), True
        return execute

    descriptions = {
        "check_appointment_availability": (CheckAvailability, "Read real business availability. Omit arguments to discover services, business timezone/current date and this customer's bookings. Supply service_id and date (YYYY-MM-DD) for available slots. For rescheduling, supply appointment_id to exclude only that customer appointment. Never invent slots."),
        "create_appointment": (Book, "Reserve a real appointment after the customer chooses an available slot. Use the returned offset-aware starts_at. Ask for the customer's name if unknown. Confirm ONLY after ok=true. Calendar synchronization is separate: do not claim Google is updated unless calendar_sync_status is synced."),
        "reschedule_appointment": (Move, "Move this customer's appointment to a real available slot. Confirm ONLY after ok=true; a conflict leaves the original booking unchanged."),
        "cancel_appointment": (Cancel, "Cancel this customer's appointment only when requested. Confirm cancellation only after ok=true; Google deletion is pending until calendar_sync_status is synced."),
    }
    from ..objectives import tool_allowed
    return [ToolSpec(name=name, description=description, input_schema=schema.model_json_schema(), handler=handler(name, schema), permission_source="appointments_enabled")
        for name, (schema, description) in descriptions.items() if tool_allowed(agent, name)]
