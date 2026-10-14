"""Guided configuration over existing agents, capabilities and tool permissions."""
import uuid

from fastapi import HTTPException
from sqlalchemy import select

from ..models import Agent, AgentTool, AppointmentService, AvailabilityRule, AppointmentCalendar, Client
from .model_providers import get_provider
from .providers import resolve_provider_credentials

APPOINTMENT_TOOLS = {"check_appointment_availability", "create_appointment", "reschedule_appointment", "cancel_appointment"}
BUILDER_TOOLS = APPOINTMENT_TOOLS | {"knowledge", "escalate_to_human"}
CHANNELS = {"whatsapp", "instagram", "messenger", "widget"}
TONES = {"professional", "friendly", "warm", "direct", "formal", ""}


def validate_choices(values):
    for key, allowed in (("selected_channels", CHANNELS), ("selected_tools", BUILDER_TOOLS)):
        items = values.get(key, [])
        if len(items) != len(set(items)) or not set(items) <= allowed:
            raise HTTPException(422, "builder.invalid_selection")
    if values.get("tone", "") not in TONES:
        raise HTTPException(422, "builder.invalid_selection")


def context(db, agency_id, client_id):
    client = db.scalar(select(Client).where(Client.id == client_id, Client.agency_id == agency_id))
    if not client:
        raise HTTPException(404, "Client not found")
    services = bool(db.scalar(select(AppointmentService.id).where(AppointmentService.agency_id == agency_id,
        AppointmentService.client_id == client_id, AppointmentService.active.is_(True))))
    availability = bool(db.scalar(select(AvailabilityRule.id).where(AvailabilityRule.agency_id == agency_id,
        AvailabilityRule.client_id == client_id, AvailabilityRule.active.is_(True))))
    connection = db.scalar(select(AppointmentCalendar).where(AppointmentCalendar.agency_id == agency_id,
        AppointmentCalendar.client_id == client_id))
    tools = db.scalars(select(AgentTool).join(Agent, Agent.id == AgentTool.agent_id).where(
        Agent.agency_id == agency_id, Agent.client_id == client_id, Agent.deleted_at.is_(None),
        AgentTool.enabled.is_(True))).all()
    service_rows = db.scalars(select(AppointmentService).where(AppointmentService.agency_id == agency_id, AppointmentService.client_id == client_id, AppointmentService.active.is_(True))).all()
    return {"services": [{"id": str(row.id), "name": row.name} for row in service_rows], "appointments_ready": services and availability,
            "google_connected": bool(connection and connection.connected and connection.calendar_id),
            "tools": [{"id": str(tool.id), "name": tool.name, "description": tool.description,
                       "type": tool.type, "agent_id": str(tool.agent_id)} for tool in tools]}


def validate_shared_tools(db, agency_id, client_id, ids, agent_id=None):
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "builder.invalid_selection")
    if not ids:
        return []
    rows = db.scalars(select(AgentTool).join(Agent, Agent.id == AgentTool.agent_id).where(
        AgentTool.id.in_([uuid.UUID(str(item)) for item in ids]), Agent.agency_id == agency_id,
        Agent.client_id == client_id, Agent.deleted_at.is_(None), AgentTool.enabled.is_(True))).all()
    if len(rows) != len(ids) or any(row.agent_id == agent_id for row in rows):
        raise HTTPException(422, "builder.tool_not_allowed")
    own_names = set(db.scalars(select(AgentTool.name).where(AgentTool.agent_id == agent_id)).all()) if agent_id else set()
    names = [row.name for row in rows]
    if len(names) != len(set(names)) or own_names.intersection(names):
        raise HTTPException(422, "builder.duplicate_tools")
    return [str(item) for item in ids]


async def prepare(db, agency_id, values, existing=None, *, guided=False, apply_template=False):
    """Validate atomically before saving; selected channels do not reassign live ones."""
    client_id = values.get("client_id", existing.client_id if existing else None)
    template_id = values.get("template_id")
    if apply_template:
        if not template_id:
            raise HTTPException(422, "Template is required")
        preview = template_preview(db, agency_id, client_id, template_id, values.get("prompt_language", existing.prompt_language if existing else "en"))
        # An explicit apply replaces starter settings; subsequent PATCH requests
        # never reapply them. Custom values in this request may override defaults.
        values = {**preview["defaults"], **values}
    if template_id and (not existing or template_id != existing.template_id or apply_template):
        preview = template_preview(db, agency_id, client_id, template_id, values.get("prompt_language", existing.prompt_language if existing else "en"))
        values["template_version"] = preview["template_version"]
        values["template_snapshot"] = preview["template_snapshot"]
    elif "template_id" in values and template_id is None:
        values["template_version"] = None
        values["template_snapshot"] = None
    validate_choices(values)
    if "shared_tool_ids" in values or (existing and client_id != existing.client_id):
        values["shared_tool_ids"] = validate_shared_tools(db, agency_id, client_id,
            values.get("shared_tool_ids", existing.shared_tool_ids if existing else []), existing.id if existing else None)
    objective_intent = bool((existing and existing.objectives_managed) or values.get("objectives") or "objective_config" in values or (existing and "objectives" in values) or guided or apply_template)
    if "selected_tools" in values and not objective_intent:
        selected = set(values["selected_tools"])
        appointments = selected & APPOINTMENT_TOOLS
        if appointments and appointments != APPOINTMENT_TOOLS:
            raise HTTPException(422, "builder.appointments_bundle")
        if appointments and not context(db, agency_id, client_id)["appointments_ready"]:
            raise HTTPException(422, "builder.appointments_not_ready")
        values["appointments_enabled"] = bool(appointments)
        values["knowledge_enabled"] = "knowledge" in selected
        values["escalation_builtin_enabled"] = "escalate_to_human" in selected
    from .objectives import prepare_objectives
    values = prepare_objectives(db, agency_id, values, existing, guided=guided, template=apply_template)
    if not guided:
        return values
    provider_id = values.get("provider", existing.provider if existing else "openai")
    model = values.get("model", existing.model if existing else "").strip()
    connection = resolve_provider_credentials(db, agency_id, provider_id)
    if not connection:
        raise HTTPException(422, "builder.provider_not_ready")
    provider = get_provider(provider_id)
    if model not in await provider.list_models(*connection):
        raise HTTPException(422, "builder.model_not_available")
    needs_tools = values.get("appointments_enabled", existing.appointments_enabled if existing else False) or values.get("shared_tool_ids", existing.shared_tool_ids if existing else [])
    needs_tools = needs_tools or values.get("escalation_builtin_enabled", existing.escalation_builtin_enabled if existing else False)
    if existing and db.scalar(select(AgentTool.id).where(AgentTool.agent_id == existing.id, AgentTool.enabled.is_(True))):
        needs_tools = True
    if not existing and not values.get("instructions", "").strip():
        lang = values.get("prompt_language", "en")
        template = values.get("template_id")
        instructions = template_preview(db, agency_id, client_id, template, lang)["defaults"]["instructions"] if template else ""
        values["instructions"] = instructions
    values["model"] = model
    return values


def template_preview(db, agency_id, client_id, template_id, language="en"):
    """Scoped, side-effect-free defaults using currently available capabilities."""
    from .agent_catalog.templates import _BY_ID, validated_definition
    template = _BY_ID.get(template_id)
    if not template or not template.active:
        raise HTTPException(404, "Template not found")
    ctx = context(db, agency_id, client_id)
    client = db.get(Client, client_id)
    definition, warnings = validated_definition(template)
    selected = [tool for tool in definition["recommended_tools"] if tool in BUILDER_TOOLS
                and (tool not in APPOINTMENT_TOOLS or ctx["appointments_ready"])]
    unavailable = [tool for tool in definition["recommended_tools"] if tool not in selected and tool != "qualify_lead"]
    # Business-specific content remains in the existing agent brief/knowledge
    # editor; missing checklist items are advisory and never synthesized.
    missing = [field for field in definition["required_business_fields"]
               if not (field in {"hours", "services"} and ctx["appointments_ready"])]
    from .agent_catalog.objective_config import defaults
    instructions = template.system_prompt_template.get(language).replace("{{business_name}}", client.name)
    snapshot = {key: value for key, value in definition.items() if key != "system_prompt_template"}
    return {"template": snapshot, "warnings": warnings, "unavailable_tools": unavailable,
            "missing_business_fields": missing, "google_connected": ctx["google_connected"],
            "defaults": {"template_id": template.id, "name": template.name.get(language), "objectives": definition["objectives"], "objective_config": {goal: defaults(goal, language) for goal in definition["objectives"]},
                         "selected_tools": selected, "selected_channels": definition["recommended_channels"],
                         "tone": template.default_tone, "instructions": instructions},
            "template_version": template.version, "template_snapshot": snapshot}


def template_matches(db, agency_id, client_id, objectives, channels=()):
    from .agent_catalog.templates import matches
    from ..models import WhatsAppChannel, WhatsAppCloudChannel, WidgetChannel, SocialChannel
    ctx = context(db, agency_id, client_id)
    business = db.get(Client, client_id)
    available = ["knowledge", "escalate_to_human"]
    if ctx["appointments_ready"]:
        available.extend(APPOINTMENT_TOOLS)
    available.extend(item["type"] for item in ctx["tools"])
    connected = set()
    for model, kind in ((WhatsAppChannel, "whatsapp"), (WhatsAppCloudChannel, "whatsapp"), (WidgetChannel, "widget"), (SocialChannel, None)):
        for row in db.scalars(select(model).where(model.agency_id == agency_id, model.client_id == client_id)):
            if row.is_enabled and (model is WidgetChannel or row.status == "connected"):
                connected.add(kind or row.provider)
    return matches(business.industry, business.business_type, objectives, connected | set(channels), available)
