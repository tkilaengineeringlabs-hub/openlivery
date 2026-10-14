"""Native automation event evaluation and durable, ordered scheduling."""
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...models import Automation, AutomationRun, Client, Conversation, Message, ScheduledAutomationAction, now_utc
from ...schemas_automations import FIELDS, TRIGGERS

logger = logging.getLogger(__name__)


def evaluate_conditions(conditions: list, payload: dict) -> bool:
    for condition in conditions:
        field = condition["field"]
        if field not in FIELDS:
            raise ValueError("Unsupported condition field")
        # Read only the explicit JSON shape, never Python model properties.
        parts = field.split(".")
        value = payload.get(parts[0])
        if len(parts) == 2:
            value = value.get(parts[1]) if isinstance(value, dict) else None
        expected = condition.get("value", "")
        operator = condition["operator"]
        exists = value is not None and value != ""
        matched = {
            "equals": value == expected,
            "not_equals": value != expected,
            "contains": isinstance(value, str) and expected.casefold() in value.casefold(),
            "not_contains": isinstance(value, str) and expected.casefold() not in value.casefold(),
            "exists": exists,
            "not_exists": not exists,
        }
        if operator not in matched:
            raise ValueError("Unsupported operator")
        if not matched[operator]:
            return False
    return True


def schedule_action(db: Session, run: AutomationRun, index: int, *, execute_at=None):
    action = {"type": "appointment_check"} if index == -2 else ({"type": "inactivity_check"} if index == -1 else run.actions[index])
    if execute_at is None:
        execute_at = now_utc()
        if action["type"] == "delay":
            execute_at += timedelta(minutes=action["amount"] * {"minutes": 1, "hours": 60, "days": 1440}[action["unit"]])
    job = ScheduledAutomationAction(agency_id=run.agency_id, automation_id=run.automation_id,
        automation_run_id=run.id, action_index=index, action=action, execute_at=execute_at)
    db.add(job)
    return job


def evaluate_automation(db: Session, automation: Automation, event_type: str, payload: dict, event_key: str):
    if not automation.enabled or str(automation.agency_id) != payload["agency_id"] or (automation.managed_by == "objective" and str(automation.agent_id) != payload.get("agent_id")):
        return None
    if db.scalar(select(AutomationRun.id).where(AutomationRun.agency_id == automation.agency_id,
        AutomationRun.automation_id == automation.id, AutomationRun.event_key == event_key)):
        return None
    run = AutomationRun(automation_id=automation.id, agency_id=automation.agency_id,
        revision=automation.revision, event_type=event_type, event_key=event_key, event_payload=payload,
        actions=automation.actions)
    db.add(run)
    db.flush()
    if event_type == "appointment_upcoming":
        due = datetime.fromisoformat(payload["appointment"]["starts_at"]) - timedelta(minutes=automation.trigger_config["minutes"])
        if due <= now_utc():
            run.status, run.completed_at = "skipped", now_utc()
        else:
            schedule_action(db, run, -2, execute_at=due)
    elif event_type == "conversation_inactive":
        schedule_action(db, run, -1, execute_at=now_utc() + timedelta(minutes=automation.trigger_config["minutes"]))
    elif evaluate_conditions(automation.conditions, payload):
        schedule_action(db, run, 0)
    else:
        run.status, run.completed_at = "skipped", now_utc()
    return run


def emit_event(db: Session, event_type: str, *, agency_id: uuid.UUID, client_id: uuid.UUID,
               message_id: uuid.UUID | None = None):
    """Called in the source transaction. External actions only run after commit.

    Rebuild the minimal payload from tenant-scoped rows, not caller-supplied data.
    Isolate each rule with a savepoint so one invalid rule cannot break ingestion.
    """
    if event_type not in TRIGGERS:
        raise ValueError("Unsupported event")
    client = db.scalar(select(Client).where(Client.id == client_id, Client.agency_id == agency_id))
    if not client or not client.is_active:
        return
    payload = {"agency_id": str(agency_id), "client_id": str(client.id),
               "client": {"name": client.name, "industry": client.industry}}
    if event_type != "client_created":
        row = db.execute(select(Message, Conversation).join(Conversation, Message.conversation_id == Conversation.id)
            .where(Message.id == message_id, Conversation.agency_id == agency_id,
                   Conversation.client_id == client.id)).first()
        if not row:
            return
        message, conversation = row
        if (message.is_historical or message.kind != "message" or conversation.channel == "playground"
                or conversation.status != "open" or conversation.archived_at
                or (conversation.contact and conversation.contact.blocked_at)):
            return
        if event_type == "message_received" and message.role != "user":
            return
        if event_type == "conversation_inactive":
            payload["message_role"] = message.role
        payload.update(conversation_id=str(conversation.id), agent_id=str(conversation.agent_id),
            message_id=str(message.id), message={"text": message.content}, channel=conversation.channel,
            timestamp=message.created_at.isoformat(), conversation={"mode": conversation.mode})
    event_key = f"{event_type}:{message_id or client_id}"
    automations = db.scalars(select(Automation).where(Automation.agency_id == agency_id,
        Automation.enabled.is_(True), Automation.trigger_type == event_type,
        or_(Automation.client_id.is_(None), Automation.client_id == client_id))).all()
    for automation in automations:
        if automation.managed_by == "objective" and automation.objective_id == "follow_up" and (message.role != "assistant" or message.sender_type == "automation"):
            continue
        try:
            with db.begin_nested():
                evaluate_automation(db, automation, event_type, payload, event_key)
        except Exception:
            # Never persist exception text: a provider error could contain a secret.
            logger.warning("Automation evaluation failed: %s", automation.id)
            with db.begin_nested():
                if not db.scalar(select(AutomationRun.id).where(AutomationRun.agency_id == agency_id,
                    AutomationRun.automation_id == automation.id, AutomationRun.event_key == event_key)):
                    db.add(AutomationRun(agency_id=agency_id, automation_id=automation.id,
                        revision=automation.revision, event_type=event_type, event_key=event_key,
                        event_payload=payload, actions=[], status="failed", error="evaluation_failed", completed_at=now_utc()))
