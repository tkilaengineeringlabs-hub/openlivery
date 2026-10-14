"""PostgreSQL queue, SKIP LOCKED claims and bounded in-process execution."""
import asyncio
import json
import logging
import uuid
from datetime import timedelta

import httpx
from sqlalchemy import select

from ...database import new_session
from ...models import Agent, Automation, AutomationRun, Client, Conversation, Message, ScheduledAutomationAction, now_utc
from ...security import decrypt_secret
from ..conversation_state import note_reply, set_mode
from ..tools.http_exec import _blocked_reason
from ..whatsapp import send_channel_message
from . import evaluate_conditions, schedule_action

logger = logging.getLogger(__name__)


class ActionFailure(Exception):
    pass


def conversation_for_run(db, run):
    conversation_id = run.event_payload.get("conversation_id")
    conversation = db.scalar(select(Conversation).where(Conversation.id == uuid.UUID(conversation_id),
        Conversation.agency_id == run.agency_id, Conversation.client_id == uuid.UUID(run.event_payload["client_id"]))) if conversation_id else None
    if (not conversation or conversation.status != "open" or conversation.archived_at
            or not conversation.agent.is_active or conversation.agent.deleted_at):
        raise ActionFailure("conversation_unavailable")
    if conversation.contact and conversation.contact.blocked_at:
        raise ActionFailure("contact_blocked")
    return conversation


async def execute_action(db, run, action, *, actor):
    kind = action["type"]
    if kind == "delay":
        return
    if kind == "http_request":
        # Shared tool guard, checked at execution as DNS/configuration can change.
        if _blocked_reason(action["url"], allow_private=False):
            raise ActionFailure("url_blocked")
        headers = json.loads(decrypt_secret(action["encrypted_headers"]))
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as http:
            async with http.stream(action["method"], action["url"], headers=headers, params=action["query"],
                                   json=action["body"] if action["method"] != "GET" else None) as response:
                if response.status_code >= 300:
                    raise ActionFailure("http_failed")
        return
    conversation = conversation_for_run(db, run)
    if kind == "handoff_to_human":
        set_mode(db, conversation, "human", actor=actor)
    elif kind == "send_message":
        # Automatic follow-ups must not speak over a human operator.
        if conversation.mode == "human":
            raise ActionFailure("human_control")
        from .appointments import render_message
        content = render_message(action["text"], run.event_payload)
        message = Message(conversation_id=conversation.id, role="assistant", content=content,
                          sender_type="automation", sender_name=actor)
        db.add(message)
        if conversation.channel in {"instagram", "messenger"}:
            from ..social_delivery import queue_message
            queue_message(db, conversation, message)
        else:
            if conversation.channel not in {"whatsapp", "whatsapp_cloud", "widget"}:
                raise ActionFailure("channel_unsupported")
            if conversation.channel == "whatsapp_cloud":
                latest = db.scalar(select(Message.created_at).where(Message.conversation_id == conversation.id,
                    Message.role == "user", Message.is_historical.is_(False)).order_by(Message.created_at.desc()).limit(1))
                if not latest or latest < now_utc() - timedelta(hours=24):
                    raise ActionFailure("reply_window_closed")
            message.external_message_id = await send_channel_message(db, conversation, content)
            note_reply(conversation)
        conversation.updated_at = now_utc()
    else:
        raise ActionFailure("action_unsupported")


def finish(run, job, status, error=None):
    run.status, run.error, run.completed_at = status, error, now_utc()
    job.status = "done" if status == "success" else status
    job.last_error, job.completed_at = error, now_utc()


async def process_due(db, *, limit=25):
    # This is the only cross-agency query: a trusted queue dispatcher. Every run,
    # rule and domain object below is fetched with the claimed agency_id.
    stale = db.scalars(select(ScheduledAutomationAction).where(ScheduledAutomationAction.status == "running",
        ScheduledAutomationAction.locked_until < now_utc()).with_for_update(skip_locked=True).limit(limit)).all()
    for job in stale:
        run = db.scalar(select(AutomationRun).where(AutomationRun.id == job.automation_run_id, AutomationRun.agency_id == job.agency_id))
        if job.action["type"] in {"delay", "inactivity_check", "appointment_check", "handoff_to_human"}:
            job.status = "pending"
        elif run:
            finish(run, job, "failed", "delivery_uncertain")
    db.commit()
    processed = 0
    for _ in range(limit):
        job = db.scalar(select(ScheduledAutomationAction).where(ScheduledAutomationAction.status == "pending",
            ScheduledAutomationAction.execute_at <= now_utc()).order_by(ScheduledAutomationAction.execute_at)
            .with_for_update(skip_locked=True).limit(1))
        if not job:
            db.rollback()
            break
        job.status, job.locked_until = "running", now_utc() + timedelta(minutes=5)
        job.attempts += 1
        job_id, agency_id, claim_attempt = job.id, job.agency_id, job.attempts
        db.commit()
        db.expire_all()
        # A durable running marker prevents another replica from replaying an
        # external effect after an uncertain crash. Hold the claim during work.
        job = db.scalar(select(ScheduledAutomationAction).where(ScheduledAutomationAction.id == job_id,
            ScheduledAutomationAction.agency_id == agency_id).with_for_update().execution_options(populate_existing=True))
        if not job or job.status != "running" or job.attempts != claim_attempt:
            db.rollback()
            continue
        run = db.scalar(select(AutomationRun).where(AutomationRun.id == job.automation_run_id,
            AutomationRun.automation_id == job.automation_id, AutomationRun.agency_id == agency_id))
        automation = db.scalar(select(Automation).where(Automation.id == job.automation_id, Automation.agency_id == agency_id))
        try:
            client = db.scalar(select(Client).where(Client.id == uuid.UUID(run.event_payload["client_id"]), Client.agency_id == agency_id))
            managed_agent = db.scalar(select(Agent).where(Agent.id == automation.agent_id, Agent.agency_id == agency_id, Agent.client_id == client.id)) if automation and automation.managed_by == "objective" and client else None
            managed_invalid = automation and automation.managed_by == "objective" and (not managed_agent or not managed_agent.is_active or managed_agent.deleted_at or automation.objective_id not in managed_agent.objectives or str(managed_agent.id) != run.event_payload.get("agent_id"))
            if managed_invalid or not automation or not automation.enabled or automation.revision != run.revision or not client or not client.is_active:
                finish(run, job, "skipped", "automation_changed")
            else:
                from .appointments import reminder_current
                if run.event_type == "appointment_upcoming" and not reminder_current(db, run):
                    finish(run, job, "skipped", "appointment_changed")
                    db.commit()
                    processed += 1
                    continue
                if automation.managed_by == "objective" and automation.objective_id == "follow_up":
                    conversation = conversation_for_run(db, run)
                    latest = db.scalar(select(Message.id).where(Message.conversation_id == conversation.id, Message.kind == "message", Message.is_historical.is_(False), Message.sender_type != "automation").order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
                    if str(latest) != run.event_payload.get("message_id") or conversation.mode != "ai":
                        finish(run, job, "skipped", "new_activity")
                        db.commit()
                        processed += 1
                        continue
                with db.begin_nested():
                    if job.action_index == -2:
                        if evaluate_conditions(automation.conditions, run.event_payload):
                            job.status, job.completed_at = "done", now_utc()
                            schedule_action(db, run, 0)
                        else:
                            finish(run, job, "skipped")
                    elif job.action_index == -1:
                        conversation = conversation_for_run(db, run)
                        latest = db.scalar(select(Message.id).where(Message.conversation_id == conversation.id,
                            Message.kind == "message", Message.is_historical.is_(False),
                            *([Message.sender_type != "automation"] if automation.managed_by == "objective" else []))
                            .order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
                        if str(latest) != run.event_payload["message_id"]:
                            finish(run, job, "skipped", "new_activity")
                        elif not evaluate_conditions(automation.conditions, run.event_payload):
                            finish(run, job, "skipped")
                        else:
                            job.status, job.completed_at = "done", now_utc()
                            schedule_action(db, run, 0)
                    else:
                        await asyncio.wait_for(execute_action(db, run, job.action, actor=automation.name), timeout=60)
                        job.status, job.completed_at = "done", now_utc()
                        run.actions_executed += 1
                        if job.action_index + 1 < len(run.actions):
                            schedule_action(db, run, job.action_index + 1)
                        else:
                            finish(run, job, "success")
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # A connection failure happens before dispatch. Other failures may
            # have reached the destination and must never be blindly retried.
            if job.attempts < 3:
                job.status, job.execute_at = "pending", now_utc() + timedelta(seconds=30 * job.attempts)
                job.last_error = "connection_failed"
            else:
                finish(run, job, "failed", "connection_failed")
        except ActionFailure as exc:
            finish(run, job, "skipped" if str(exc) == "human_control" else "failed", str(exc))
        except Exception:
            finish(run, job, "failed", "execution_failed")
        db.commit()
        processed += 1
    return processed


async def worker_loop():
    while True:
        try:
            with new_session() as db:
                await process_due(db)
        except Exception:
            logger.warning("Automation worker iteration failed")
        await asyncio.sleep(2)
