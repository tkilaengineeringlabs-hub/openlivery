"""Capture newly persisted messages across existing channel paths, in their transaction.

Historical imports, system activities, playground and automation output are excluded.
No internal HTTP requests, provider calls or conversation scans occur here.
"""
import logging
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from ...models import Conversation, Message
from . import emit_event

logger = logging.getLogger(__name__)


@event.listens_for(Session, "before_flush")
def collect_messages(db, *_):
    if db.info.get("automation_emitting"):
        return
    messages = db.info.setdefault("automation_messages", [])
    messages.extend(item for item in db.new if isinstance(item, Message) and item not in messages)


@event.listens_for(Session, "before_commit")
def emit_messages(db):
    if db.info.get("automation_emitting") or db.in_nested_transaction():
        return
    db.flush()
    messages = db.info.pop("automation_messages", [])
    db.info["automation_emitting"] = True
    try:
        for message in messages:
            if message.kind != "message" or message.is_historical or message.sender_type == "automation":
                continue
            conversation = db.scalar(select(Conversation).where(Conversation.id == message.conversation_id))
            if not conversation:
                continue
            try:
                with db.begin_nested():
                    if message.role == "user":
                        emit_event(db, "message_received", agency_id=conversation.agency_id,
                            client_id=conversation.client_id, message_id=message.id)
                    if message.role in {"user", "assistant"}:
                        emit_event(db, "conversation_inactive", agency_id=conversation.agency_id,
                            client_id=conversation.client_id, message_id=message.id)
            except Exception:
                logger.warning("Automation message capture failed for %s", message.id)
    finally:
        db.info.pop("automation_emitting", None)


@event.listens_for(Session, "after_soft_rollback")
def clear_rolled_back_messages(db, transaction):
    if not transaction.nested:
        db.info.pop("automation_messages", None)
