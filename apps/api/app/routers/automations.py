"""Agency-scoped automation management. Saved HTTP headers are write-only."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import get_current_user
from ..models import Automation, AutomationRun, Client, ScheduledAutomationAction, User, now_utc
from ..schemas_automations import AutomationBatch, AutomationPatch, AutomationWrite
from ..services.automations.secrets import public_actions, store_actions
from ..services.tools.http_exec import _blocked_reason
from ..services.automations.appointments import seed_reminders

router = APIRouter(prefix="/automations", tags=["Automations"])


def owned(db, user, automation_id):
    item = db.scalar(select(Automation).where(Automation.id == automation_id, Automation.agency_id == user.agency_id))
    if not item:
        raise HTTPException(404, "Automation not found")
    if item.managed_by == "objective":
        raise HTTPException(409, "Configure this managed flow from agent objectives")
    return item


def public(db, item):
    latest = db.scalar(select(AutomationRun).where(AutomationRun.automation_id == item.id,
        AutomationRun.agency_id == item.agency_id).order_by(AutomationRun.started_at.desc()).limit(1))
    return {"id": item.id, "name": item.name, "template_id": item.template_id, "client_id": item.client_id, "enabled": item.enabled,
        "trigger_type": item.trigger_type, "trigger_config": item.trigger_config, "conditions": item.conditions,
        "actions": public_actions(item.actions), "created_at": item.created_at, "updated_at": item.updated_at,
        "last_run_at": latest.started_at if latest else None, "last_run_status": latest.status if latest else None}


def apply(db, user, item, payload):
    if payload.client_id and not db.scalar(select(Client.id).where(Client.id == payload.client_id, Client.agency_id == user.agency_id)):
        raise HTTPException(404, "Client not found")
    for action in payload.actions:
        if action.type == "http_request" and _blocked_reason(action.url, allow_private=False):
            raise HTTPException(422, "HTTP URL is blocked or cannot be resolved")
    values = payload.model_dump(mode="json")
    try:
        values["actions"] = store_actions(values["actions"], item.actions or [])
    except ValueError:
        raise HTTPException(422, "Invalid saved header reference") from None
    values["client_id"] = payload.client_id
    for key, value in values.items():
        setattr(item, key, value)


def cancel_pending(db, item):
    runs = db.scalars(select(AutomationRun).where(AutomationRun.automation_id == item.id,
        AutomationRun.agency_id == item.agency_id, AutomationRun.status == "running")).all()
    for run in runs:
        jobs = db.scalars(select(ScheduledAutomationAction).where(ScheduledAutomationAction.automation_run_id == run.id,
            ScheduledAutomationAction.agency_id == item.agency_id, ScheduledAutomationAction.status == "pending")
            .with_for_update()).all()
        for job in jobs:
            job.status, job.completed_at, job.last_error = "skipped", now_utc(), "automation_changed"
        if jobs:
            run.status, run.completed_at, run.error = "skipped", now_utc(), "automation_changed"


@router.get("")
def list_automations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [public(db, item) for item in db.scalars(select(Automation).where(Automation.agency_id == user.agency_id, Automation.managed_by.is_(None))
        .order_by(Automation.created_at.desc())).all()]


@router.post("", status_code=201)
def create(payload: AutomationWrite, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = Automation(agency_id=user.agency_id)
    apply(db, user, item, payload)
    db.add(item)
    db.flush()
    seed_reminders(db, item)
    db.commit()
    return public(db, item)


@router.get("/recommendations")
def recommendations(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..models import Agent
    from ..services.agent_builder import template_matches, context
    from ..services.agent_catalog.objectives import recommendations as objective_recommendations
    from ..services.agent_catalog.templates import AUTOMATIONS
    ctx = context(db, user.agency_id, client_id)
    agents = db.scalars(select(Agent).where(Agent.agency_id == user.agency_id, Agent.client_id == client_id,
                                          Agent.deleted_at.is_(None), Agent.is_active.is_(True))).all()
    objectives = list(dict.fromkeys(goal for agent in agents for goal in agent.objectives))
    ranked = template_matches(db, user.agency_id, client_id, objectives)
    best = next((row for row in ranked if row["recommended"]), None)
    suggestions = list(best["template"]["suggested_automations"]) if best else []
    suggestions.extend(objective_recommendations(objectives)["automations"])
    for agent in agents:
        suggestions.extend((agent.template_snapshot or {}).get("suggested_automations", []))
    if "handoff_to_human" in objectives or "customer_support" in objectives:
        suggestions.append("handoff")
    return {"ids": list(dict.fromkeys(code for code in suggestions if code in AUTOMATIONS)),
            "appointments_ready": ctx["appointments_ready"], "client_id": client_id}


@router.post("/batch", status_code=201)
def create_batch(payload: AutomationBatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import copy
    import json
    from ..security import decrypt_secret
    records = []
    # Stable caller-generated IDs make retries after a lost response safe.
    # Existing records are returned only for identical, owned configurations.
    with db.no_autoflush:
        for entry in payload.items:
            existing = db.get(Automation, entry.id)
            configuration = entry.configuration
            if existing:
                if existing.managed_by == "objective":
                    raise HTTPException(409, "Configure this managed flow from agent objectives")
                if existing.agency_id != user.agency_id:
                    raise HTTPException(404, "Automation not found")
                values = {key: getattr(existing, key) for key in AutomationWrite.model_fields}
                values["actions"] = copy.deepcopy(existing.actions)
                for action in values["actions"]:
                    if action["type"] == "http_request":
                        action["headers"] = json.loads(decrypt_secret(action.pop("encrypted_headers")))
                if AutomationWrite.model_validate(values).model_dump(mode="json") != configuration.model_dump(mode="json"):
                    raise HTTPException(409, "Batch retry configuration changed; reload saved automations")
                records.append(existing)
                continue
            item = Automation(id=entry.id, agency_id=user.agency_id)
            apply(db, user, item, configuration)
            db.add(item)
            records.append(item)
    from sqlalchemy.exc import IntegrityError
    try:
        db.flush()
        for item in records:
            # Reminder seeding deduplicates pending appointment revision jobs.
            seed_reminders(db, item)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Batch request conflicted; retry the same request") from None
    return [public(db, item) for item in records]


@router.get("/{automation_id}")
def get(automation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return public(db, owned(db, user, automation_id))


@router.patch("/{automation_id}")
def update(automation_id: uuid.UUID, payload: AutomationPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = owned(db, user, automation_id)
    values = {key: value for key, value in public(db, item).items() if key in AutomationWrite.model_fields}
    values.update(payload.model_dump(exclude_unset=True))
    try:
        validated = AutomationWrite.model_validate(values)
    except ValidationError:
        raise HTTPException(422, "Invalid automation configuration") from None
    apply(db, user, item, validated)
    item.revision += 1
    cancel_pending(db, item)
    db.flush()
    seed_reminders(db, item)
    db.commit()
    return public(db, item)


@router.delete("/{automation_id}", status_code=204)
def delete(automation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = owned(db, user, automation_id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


def set_enabled(db, user, automation_id, enabled):
    item = owned(db, user, automation_id)
    if item.enabled != enabled:
        item.enabled = enabled
        item.revision += 1
        if not enabled:
            cancel_pending(db, item)
        db.flush()
        seed_reminders(db, item)
        db.commit()
    return public(db, item)


@router.post("/{automation_id}/enable")
def enable(automation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return set_enabled(db, user, automation_id, True)


@router.post("/{automation_id}/disable")
def disable(automation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return set_enabled(db, user, automation_id, False)


@router.get("/{automation_id}/runs")
def runs(automation_id: uuid.UUID, limit: int = 50, offset: int = 0,
         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    owned(db, user, automation_id)
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "Invalid pagination")
    items = db.scalars(select(AutomationRun).where(AutomationRun.automation_id == automation_id,
        AutomationRun.agency_id == user.agency_id).order_by(AutomationRun.started_at.desc(), AutomationRun.id.desc())
        .limit(limit).offset(offset)).all()
    return [{"id": run.id, "event_type": run.event_type, "status": run.status, "started_at": run.started_at,
        "completed_at": run.completed_at, "actions_executed": run.actions_executed,
        "action_count": len(run.actions), "error": run.error,
        "duration_seconds": (run.completed_at - run.started_at).total_seconds() if run.completed_at else None} for run in items]
