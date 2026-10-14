"""Objective permissions and managed-rule sync over the existing automation engine."""
import uuid
from sqlalchemy import select
from fastapi import HTTPException
from ..models import Agent, AppointmentService, Automation, AutomationRun, ToolExecution
from .agent_catalog.objectives import _BY_ID
from .agent_catalog.objective_config import defaults, validate_config

KNOWLEDGE_GOALS = {"respond_questions", "customer_support", "sales", "lead_qualification", "resolve_support"}
CALENDAR_GOALS = {"book_appointment", "reschedule_appointment", "cancel_appointment"}


def prepare_objectives(db, agency_id, values, existing=None, *, guided=False, template=False):
    explicit = "objective_config" in values or ("objectives" in values and (existing is not None or bool(values["objectives"])))
    managed = bool((existing and existing.objectives_managed) or explicit or ((guided or template) and existing is None))
    if not managed:
        return values
    client_id = values.get("client_id", existing.client_id if existing else None)
    goals = values.get("objectives", existing.objectives if existing else [])
    language = values.get("prompt_language", existing.prompt_language if existing else "es")
    config = dict(existing.objective_config or {}) if existing else {}
    submitted = values.get("objective_config", {})
    if any(code not in _BY_ID for code in submitted):
        raise HTTPException(422, "Unknown objective configuration")
    try:
        for code in set(goals) | set(submitted):
            config[code] = validate_config(code, {**config.get(code, {}), **submitted.get(code, {})}, language)
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid objective configuration") from None
    from .agent_builder import context
    ctx = context(db, agency_id, client_id)
    for code in CALENDAR_GOALS & set(config):
        ids = config[code].get("service_ids", [])
        try:
            parsed = [uuid.UUID(value) for value in ids]
        except ValueError:
            raise HTTPException(422, "Invalid service selection") from None
        count = len(db.scalars(select(AppointmentService.id).where(AppointmentService.id.in_(parsed),
            AppointmentService.agency_id == agency_id, AppointmentService.client_id == client_id, AppointmentService.active.is_(True))).all())
        if count != len(ids):
            raise HTTPException(422, "Service does not belong to this business")
    if {"order_lookup", "inventory_lookup"} & set(goals):
        # No native order/inventory connector exists. Arbitrary HTTP tools cannot
        # establish those semantics, so future objectives stay unavailable.
        raise HTTPException(422, "This commerce objective is not available")
    values["objectives_managed"] = True
    values["objective_config"] = config
    values["knowledge_enabled"] = bool(set(goals) & KNOWLEDGE_GOALS)
    values["escalation_builtin_enabled"] = "handoff_to_human" in goals
    ready = ctx["appointments_ready"]
    active_calendar = [code for code in goals if code in CALENDAR_GOALS and (config[code]["calendar"] == "internal" or ctx["google_connected"])]
    values["appointments_enabled"] = bool(ready and active_calendar)
    proxy = type("ObjectiveGrants", (), {"objectives_managed": True, "objectives": goals, "objective_config": config, "appointments_enabled": values["appointments_enabled"]})()
    selected = [name for name in ("knowledge", "check_appointment_availability", "create_appointment", "reschedule_appointment", "cancel_appointment", "escalate_to_human")
                if (name == "knowledge" and values["knowledge_enabled"]) or (name == "escalate_to_human" and values["escalation_builtin_enabled"]) or tool_allowed(proxy, name)]
    requested = values.get("selected_tools")
    if requested is None and existing and existing.objectives_managed and not explicit:
        requested = existing.selected_tools or []
    if requested is not None:
        if "selected_tools" in values and not set(requested) <= set(selected):
            raise HTTPException(422, "Selected tools exceed objective permissions")
        selected = [name for name in selected if name in requested]
        values["knowledge_enabled"] = "knowledge" in selected
        values["escalation_builtin_enabled"] = "escalate_to_human" in selected
        values["appointments_enabled"] = bool(set(selected) & {"check_appointment_availability", "create_appointment", "reschedule_appointment", "cancel_appointment"})
    values["selected_tools"] = selected
    return values


def tool_allowed(agent, name):
    if not getattr(agent, "objectives_managed", False):
        return getattr(agent, "appointments_enabled", False)
    if not agent.appointments_enabled:
        return False
    grants = getattr(agent, "selected_tools", None)
    if grants is not None and name not in grants:
        return False
    goals = set(agent.objectives)
    book = agent.objective_config.get("book_appointment", {})
    return {"check_appointment_availability": bool(goals & CALENDAR_GOALS),
            "create_appointment": "book_appointment" in goals,
            "reschedule_appointment": "reschedule_appointment" in goals or ("book_appointment" in goals and book.get("allow_reschedule", True)),
            "cancel_appointment": "cancel_appointment" in goals or ("book_appointment" in goals and book.get("allow_cancel", True))}.get(name, False)


def desired_rules(agent):
    result = {}
    def add(goal, key, trigger, actions, config=None):
        result[(goal, key)] = {"trigger_type": trigger, "trigger_config": config or {}, "actions": actions, "conditions": []}
    def message(text):
        return {"id": str(uuid.uuid4()), "type": "send_message", "text": text}
    if "follow_up" in agent.objectives:
        cfg = agent.objective_config["follow_up"]
        actions = [message(cfg["message"])]
        if cfg["max_attempts"] == 2:
            actions += [{"id": str(uuid.uuid4()), "type": "delay", "amount": cfg["second_minutes"], "unit": "minutes"}, message(cfg["message"])]
        add("follow_up", "followup", "conversation_inactive", actions, {"minutes": cfg["first_minutes"]})
    if "appointment_reminder" in agent.objectives:
        cfg = agent.objective_config["appointment_reminder"]
        if cfg["confirmation"]:
            add("appointment_reminder", "confirmation", "appointment_created", [message(cfg["confirmation_message"])])
        for key, minutes in (("reminder24", cfg["reminder24_minutes"]), ("reminder2", cfg["reminder2_minutes"])):
            if cfg[key]:
                add("appointment_reminder", key, "appointment_upcoming", [message(cfg["reminder_message"])], {"minutes": minutes})
        if cfg["after_appointment"] and "post_appointment_followup" not in agent.objectives:
            add("appointment_reminder", "after", "appointment_completed", [message(cfg["after_message"])])
    if "post_appointment_followup" in agent.objectives:
        add("post_appointment_followup", "after", "appointment_completed", [message(agent.objective_config["post_appointment_followup"]["message"])])
    return result


def sync_rules(db, agent):
    if not agent.objectives_managed:
        return
    from ..routers.automations import cancel_pending
    from .automations.appointments import seed_reminders
    rows = db.scalars(select(Automation).where(Automation.agency_id == agent.agency_id, Automation.agent_id == agent.id,
        Automation.managed_by == "objective").with_for_update()).all()
    existing = {(r.objective_id, r.rule_key): r for r in rows}
    desired = desired_rules(agent) if agent.is_active and not agent.deleted_at else {}
    for key, definition in desired.items():
        row = existing.get(key)
        enabled = agent.is_active
        if not row:
            row = Automation(agency_id=agent.agency_id, client_id=agent.client_id, agent_id=agent.id,
                managed_by="objective", objective_id=key[0], rule_key=key[1], name=f"{agent.name}: {key[0]} / {key[1]}", enabled=enabled, **definition)
            db.add(row)
        else:
            # Preserve action IDs for unchanged configurations and stable retries.
            old_actions = [{k: v for k, v in a.items() if k != "id"} for a in row.actions]
            new_actions = [{k: v for k, v in a.items() if k != "id"} for a in definition["actions"]]
            if old_actions == new_actions and row.trigger_config == definition["trigger_config"] and row.enabled == enabled and row.client_id == agent.client_id:
                continue
            cancel_pending(db, row)
            row.revision += 1
            for field, value in definition.items():
                setattr(row, field, value)
            row.enabled, row.client_id = enabled, agent.client_id
        db.flush()
        seed_reminders(db, row)
    for key, row in existing.items():
        if key not in desired and row.enabled:
            row.enabled = False
            row.revision += 1
            cancel_pending(db, row)


def statuses(db, agent):
    if not agent.objectives:
        return {}
    from .agent_builder import context
    ctx = context(db, agent.agency_id, agent.client_id)
    status = {}
    for goal in agent.objectives:
        state = "active" if agent.objectives_managed and agent.is_active else "paused" if agent.objectives_managed else "legacy"
        if goal in (CALENDAR_GOALS | {"appointment_reminder", "post_appointment_followup"}) and (not ctx["appointments_ready"] or (agent.objective_config.get(goal, {}).get("calendar") == "google" and not ctx["google_connected"])):
            state = "needs_configuration"
        if (goal in KNOWLEDGE_GOALS and not agent.knowledge_enabled) or (goal == "handoff_to_human" and not agent.escalation_builtin_enabled):
            state = "needs_configuration"
        if goal in {"order_lookup", "inventory_lookup"}:
            state = "unavailable"
        rules = db.scalars(select(Automation.id).where(Automation.agent_id == agent.id, Automation.agency_id == agent.agency_id, Automation.objective_id == goal, Automation.managed_by == "objective")).all()
        latest = db.scalar(select(AutomationRun).where(AutomationRun.agency_id == agent.agency_id, AutomationRun.automation_id.in_(rules)).order_by(AutomationRun.started_at.desc()).limit(1)) if rules else None
        tool_names = {"respond_questions": ["knowledge_search"], "customer_support": ["knowledge_search"], "sales": ["knowledge_search"],
                      "resolve_support": ["knowledge_search"], "lead_qualification": ["qualify_lead"], "book_appointment": ["create_appointment", "check_appointment_availability"],
                      "reschedule_appointment": ["reschedule_appointment"], "cancel_appointment": ["cancel_appointment"], "handoff_to_human": ["escalate_to_human"]}.get(goal, [])
        tool = db.scalar(select(ToolExecution).where(ToolExecution.agent_id == agent.id, ToolExecution.agency_id == agent.agency_id, ToolExecution.tool_name.in_(tool_names)).order_by(ToolExecution.created_at.desc()).limit(1)) if tool_names else None
        status[goal] = {"state": state, "last_run_at": latest.started_at if latest else tool.created_at if tool else None, "last_run_status": latest.status if latest else tool.status if tool else None}
    return status


def sources(agent):
    if not getattr(agent, "objectives_managed", False):
        return {key: True for key in ("business", "knowledge", "faqs", "services")}
    configs = [agent.objective_config.get(goal, {}) for goal in agent.objectives if goal in KNOWLEDGE_GOALS]
    return {key: any(cfg.get(key, True) for cfg in configs) for key in ("business", "knowledge", "faqs", "services")}


def runtime_guidance(agent):
    if not getattr(agent, "objectives_managed", False):
        return ""
    return "Objective behavior configuration (use only authorized tools; never promise an action without success):\n" + "\n".join(
        f"{goal}: {agent.objective_config.get(goal, {})}" for goal in agent.objectives if goal not in {"follow_up", "appointment_reminder", "post_appointment_followup"})


def calendar_config(agent, name):
    code = {"reschedule_appointment": "reschedule_appointment", "cancel_appointment": "cancel_appointment"}.get(name, "book_appointment")
    if code not in agent.objectives:
        code = next((goal for goal in ("book_appointment", "reschedule_appointment", "cancel_appointment") if goal in agent.objectives), code)
    return agent.objective_config.get(code, {})


def calendar_ready(db, agent, name):
    if not tool_allowed(agent, name):
        return False
    if not agent.objectives_managed:
        return True
    from .agent_builder import context
    ctx = context(db, agent.agency_id, agent.client_id)
    cfg = calendar_config(agent, name)
    return ctx["appointments_ready"] and (cfg.get("calendar", "internal") == "internal" or ctx["google_connected"])
