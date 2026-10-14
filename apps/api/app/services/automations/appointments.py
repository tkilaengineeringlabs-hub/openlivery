"""Appointment events and reminders on the existing automation job queue."""
import logging
import re
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import or_, select
from ...models import Appointment, Automation, AutomationRun, Client, ScheduledAutomationAction, now_utc
from . import evaluate_automation

logger = logging.getLogger(__name__)
APPOINTMENT_EVENTS = {"appointment_created", "appointment_rescheduled", "appointment_cancelled", "appointment_completed", "appointment_upcoming"}
VARIABLES = {"appointment.id", "appointment.starts_at", "appointment.ends_at", "appointment.status", "customer.name", "customer.phone",
    "customer.email", "service.name", "service.duration_minutes", "client.name", "appointment_date", "appointment_time",
    "customer_name", "service_name"}
TOKEN = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}")


def payload_for(db, appointment):
    client = db.scalar(select(Client).where(Client.id == appointment.client_id, Client.agency_id == appointment.agency_id))
    local = appointment.starts_at.astimezone(ZoneInfo(client.timezone))
    return {"agency_id": str(appointment.agency_id), "client_id": str(client.id),
        "agent_id": str(appointment.agent_id) if appointment.agent_id else None,
        "conversation_id": str(appointment.conversation_id) if appointment.conversation_id else None,
        "client": {"name": client.name, "industry": client.industry},
        "appointment": {"id": str(appointment.id), "revision": appointment.revision, "starts_at": appointment.starts_at.isoformat(),
            "ends_at": appointment.ends_at.isoformat(), "status": appointment.status},
        "customer": {"name": appointment.customer_name, "phone": appointment.customer_phone, "email": appointment.customer_email},
        "service": {"name": appointment.service_name, "duration_minutes": int((appointment.ends_at - appointment.starts_at).total_seconds() / 60)},
        "appointment_date": local.strftime("%Y-%m-%d"), "appointment_time": local.strftime("%H:%M"),
        "customer_name": appointment.customer_name, "service_name": appointment.service_name}


def render_message(text, payload):
    def replace(match):
        key = match.group(1)
        if key not in VARIABLES:
            raise ValueError("Unsupported message variable")
        value = payload
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        return "" if value is None else str(value)
    return TOKEN.sub(replace, text)


def invalidate_reminders(db, appointment):
    runs = db.scalars(select(AutomationRun).where(AutomationRun.agency_id == appointment.agency_id,
        AutomationRun.event_type == "appointment_upcoming", AutomationRun.status == "running",
        AutomationRun.event_payload["appointment"]["id"].as_string() == str(appointment.id))).all()
    for run in runs:
        jobs = db.scalars(select(ScheduledAutomationAction).where(ScheduledAutomationAction.agency_id == appointment.agency_id,
            ScheduledAutomationAction.automation_run_id == run.id, ScheduledAutomationAction.status == "pending").with_for_update()).all()
        for job in jobs:
            job.status, job.last_error, job.completed_at = "skipped", "appointment_changed", now_utc()
        if jobs:
            run.status, run.error, run.completed_at = "skipped", "appointment_changed", now_utc()


def emit_for_rule(db, rule, appointment, event_type):
    payload = payload_for(db, appointment)
    key = f"{event_type}:{appointment.id}:{appointment.revision}:{rule.revision}"
    try:
        with db.begin_nested():
            evaluate_automation(db, rule, event_type, payload, key)
    except Exception:
        logger.warning("Appointment automation evaluation failed: %s", rule.id)
        with db.begin_nested():
            if not db.scalar(select(AutomationRun.id).where(AutomationRun.agency_id == rule.agency_id,
                AutomationRun.automation_id == rule.id, AutomationRun.event_key == key)):
                db.add(AutomationRun(agency_id=rule.agency_id, automation_id=rule.id, revision=rule.revision,
                    event_key=key, event_type=event_type, event_payload=payload, actions=[], status="failed",
                    error="evaluation_failed", completed_at=now_utc()))


def appointment_event(db, appointment, event_type):
    invalidate_reminders(db, appointment)
    types = [event_type] if event_type else []
    if appointment.status in {"scheduled", "confirmed"}:
        types.append("appointment_upcoming")
    rules = db.scalars(select(Automation).where(Automation.agency_id == appointment.agency_id, Automation.enabled.is_(True),
        Automation.trigger_type.in_(types), or_(Automation.client_id.is_(None), Automation.client_id == appointment.client_id))).all()
    for rule in rules:
        emit_for_rule(db, rule, appointment, rule.trigger_type)


def seed_reminders(db, rule):
    """Called on rule create/edit/enable, never from a periodic conversation scan."""
    if not rule.enabled or rule.trigger_type != "appointment_upcoming":
        return
    query = select(Appointment).where(Appointment.agency_id == rule.agency_id, Appointment.status.in_(("scheduled", "confirmed")),
        Appointment.starts_at > now_utc() + timedelta(minutes=rule.trigger_config["minutes"]))
    if rule.client_id:
        query = query.where(Appointment.client_id == rule.client_id)
    for appointment in db.scalars(query):
        emit_for_rule(db, rule, appointment, "appointment_upcoming")


def reminder_current(db, run):
    snapshot = run.event_payload["appointment"]
    row = db.scalar(select(Appointment).where(Appointment.id == uuid.UUID(snapshot["id"]),
        Appointment.agency_id == run.agency_id, Appointment.client_id == uuid.UUID(run.event_payload["client_id"])))
    return row is not None and row.revision == snapshot["revision"] and row.status in {"scheduled", "confirmed"} and row.starts_at > now_utc()
