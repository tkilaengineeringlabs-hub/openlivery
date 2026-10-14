"""Versioned starter configurations; recommendations never provision resources."""
from dataclasses import asdict, dataclass
from ...industries import Label
from .objectives import recommendations, OBJECTIVES
from .capabilities import TOOLS

# IDs of executable templates in the existing automation module.
AUTOMATIONS = frozenset({"confirmation", "reminder24", "reminder2", "afterAppointment", "followUp", "recover", "handoff", "webhook", "notify"})
CHANNELS = frozenset({"whatsapp", "instagram", "messenger", "widget"})


@dataclass(frozen=True)
class AgentTemplateDefinition:
    id: str
    name: Label
    description: Label
    industry: str
    business_type: str
    objectives: tuple[str, ...]
    recommended_channels: tuple[str, ...]
    recommended_tools: tuple[str, ...]
    system_prompt_template: Label
    suggested_automations: tuple[str, ...]
    required_business_fields: tuple[str, ...]
    optional_business_fields: tuple[str, ...] = ("contact", "faq")
    handoff_rules: tuple[str, ...] = ("human_request", "cannot_solve")
    default_tone: str = "friendly"
    tags: tuple[str, ...] = ()
    version: int = 1
    active: bool = True


# Stable industry/business codes come from app.industries, including veterinary
# and dental as business types of health_wellness. Existing template IDs survive.
SECTORS = (
    ("veterinary", "health_wellness", "veterinary", "Veterinary", "veterinaria", ("hours", "services", "location", "policies"),
     "Never diagnose or prescribe; urgent health concerns require a professional.", "No diagnostiques ni recetes; las urgencias requieren atención profesional."),
    ("dental", "health_wellness", "dental", "Dental", "dental", ("hours", "services", "location", "policies"),
     "Do not diagnose or invent treatment prices.", "No diagnostiques ni inventes precios de tratamientos."),
    ("restaurant", "restaurants_food", "restaurant", "Restaurant", "de restaurante", ("hours", "menu", "location", "reservations", "delivery"),
     "Never claim a table or order is confirmed without a configured tool confirming it.", "No confirmes una mesa ni un pedido sin confirmación de una herramienta configurada."),
    ("ecommerce", "retail_ecommerce", "online_store", "Ecommerce", "de ecommerce", ("products", "shipping", "returns", "policies"),
     "Order status and inventory require an explicitly configured external tool; otherwise offer human assistance.", "El estado de pedidos e inventario requiere una herramienta externa configurada; si falta, ofrece atención humana."),
    ("real_estate", "real_estate", "agency", "Real estate", "inmobiliaria", ("listings", "location", "policies"),
     "Use verified listings; collect budget, location and requirements without promising financing.", "Usa inmuebles verificados; pregunta presupuesto, ubicación y requisitos sin prometer financiamiento."),
    ("automotive", "automotive", "workshop", "Workshop", "de taller", ("hours", "services", "location", "policies"),
     "Collect vehicle details; estimates are preliminary, never a diagnosis or final quote.", "Recoge datos del vehículo; las estimaciones son iniciales, no diagnósticos ni cotizaciones finales."),
    ("beauty", "beauty_personal_care", "salon", "Beauty", "de belleza", ("hours", "services", "location", "policies"),
     "Explain verified services and aftercare; do not promise outcomes.", "Explica servicios y cuidados documentados; no prometas resultados."),
    ("clinic", "health_wellness", "clinic", "Clinic", "de clínica", ("hours", "services", "location", "policies"),
     "Do not diagnose, prescribe or triage emergencies; refer urgent concerns to a professional.", "No diagnostiques, recetes ni clasifiques urgencias; deriva las urgencias a un profesional."),
    ("agency", "professional_services", "marketing_agency", "Agency", "de agencia", ("services", "audience", "hours", "policies"),
     "Qualify the prospect's goals and budget; do not promise campaign results.", "Califica objetivos y presupuesto; no prometas resultados de campañas."),
    ("professional", "professional_services", "consulting", "Professional services", "de servicios profesionales", ("services", "hours", "location", "policies"),
     "Collect requirements and explain documented scope; personalized professional advice requires human review.", "Recoge requisitos y explica el alcance documentado; el asesoramiento personalizado requiere revisión humana."),
)
ROLES = {
    "receptionist": ("receptionist", "Recepcionista", ("customer_support", "book_appointment", "reschedule_appointment", "cancel_appointment", "follow_up", "appointment_reminder", "handoff_to_human"), ("confirmation", "reminder24", "reminder2", "afterAppointment")),
    "agenda": ("appointment assistant", "Agenda", ("book_appointment", "reschedule_appointment", "cancel_appointment", "handoff_to_human"), ("confirmation", "reminder24", "reminder2")),
    "follow_up": ("follow-up assistant", "Seguimiento", ("follow_up", "customer_support", "handoff_to_human"), ("followUp", "afterAppointment")),
    "sales": ("sales assistant", "Ventas", ("sales", "respond_questions", "handoff_to_human"), ("followUp",)),
    "reminders": ("appointment reminders", "Recordatorios de cita", ("appointment_reminder", "respond_questions", "handoff_to_human"), ("reminder24", "reminder2")),
    "recovery": ("customer recovery", "Recuperación de clientes", ("follow_up", "customer_support", "handoff_to_human"), ("recover",)),
    "care": ("customer care", "Atención general", ("customer_support", "respond_questions", "handoff_to_human"), ()),
    "faq": ("FAQ assistant", "Preguntas frecuentes", ("respond_questions", "handoff_to_human"), ()),
    "orders": ("order information", "Pedidos e información", ("respond_questions", "resolve_support", "handoff_to_human"), ()),
    "support": ("after-sales support", "Soporte postventa", ("resolve_support", "handoff_to_human"), ()),
    "leads": ("lead capture", "Captación de leads", ("lead_qualification", "customer_support", "handoff_to_human"), ("followUp",)),
    "qualification": ("lead qualifier", "Calificación de prospectos", ("lead_qualification", "handoff_to_human"), ("followUp", "handoff", "webhook")),
    "quote": ("initial estimate", "Cotización inicial", ("sales", "lead_qualification", "handoff_to_human"), ("followUp",)),
    "reservations": ("reservation assistant", "Reservaciones", ("book_appointment", "customer_support", "handoff_to_human"), ("confirmation",)),
    "menu": ("menu information", "Pedidos e información de menú", ("respond_questions", "customer_support", "handoff_to_human"), ()),
}
SECTOR_ROLES = (
    ("receptionist", "agenda", "follow_up", "sales"), ("receptionist", "agenda", "reminders", "recovery"),
    ("reservations", "care", "faq", "menu"), ("sales", "orders", "support", "recovery"),
    ("leads", "qualification", "agenda", "follow_up"), ("receptionist", "agenda", "follow_up", "quote"),
    ("receptionist", "agenda", "reminders", "follow_up"), ("receptionist", "agenda", "reminders", "faq"),
    ("qualification", "follow_up", "agenda", "care"), ("receptionist", "agenda", "qualification", "follow_up"),
)
LEGACY_IDS = {("ecommerce", "sales"): "ecommerce_assistant", ("restaurant", "care"): "restaurant_assistant", ("real_estate", "leads"): "real_estate_assistant"}


ROLE_LABELS = {
    ("veterinary", "follow_up"): ("Post-consultation follow-up", "Seguimiento postconsulta"),
    ("veterinary", "sales"): ("Product sales", "Ventas de productos"),
    ("dental", "agenda"): ("Consultation appointments", "Agenda de consultas"),
    ("dental", "recovery"): ("Patient recovery", "Recuperación de pacientes"),
    ("real_estate", "agenda"): ("Viewing appointments", "Agenda de visitas"),
    ("automotive", "agenda"): ("Service appointments", "Agenda de servicios"),
    ("beauty", "follow_up"): ("Post-service follow-up", "Seguimiento postservicio"),
    ("agency", "follow_up"): ("Sales follow-up", "Seguimiento comercial"),
    ("agency", "agenda"): ("Meeting appointments", "Agenda de reuniones"),
}
ROLE_GUIDANCE = {
    "qualification": ("Ask about needs, budget and timing; request only relevant contact information.", "Pregunta necesidades, presupuesto y plazo; pide solo datos de contacto pertinentes."),
    "agenda": ("Ask which service and date the customer needs; check availability before offering times.", "Pregunta servicio y fecha; consulta disponibilidad antes de ofrecer horarios."),
    "sales": ("Recommend documented products or services based on the customer's needs; never invent availability.", "Recomienda productos o servicios documentados según las necesidades; no inventes disponibilidad."),
    "follow_up": ("Answer follow-up questions using documented instructions; never promise an automatic future message.", "Responde preguntas de seguimiento con instrucciones documentadas; no prometas mensajes futuros automáticos."),
    "reminders": ("Explain appointment policies; reminders follow the saved objective settings.", "Explica políticas de citas; los recordatorios siguen la configuración guardada del objetivo."),
}

CATEGORY_OBJECTIVES = {
    "appointments": {"book_appointment", "appointment_reminder"}, "sales": {"sales"},
    "care": {"customer_support", "respond_questions"}, "leads": {"lead_qualification"},
    "support": {"resolve_support"},
}


def _tags(code, role, goals):
    categories = [category for category, ids in CATEGORY_OBJECTIVES.items() if set(goals) & ids]
    return tuple(dict.fromkeys((role, *goals, *categories, *(("ecommerce",) if code == "ecommerce" else ()))))


def _make(sector, role):
    code, industry, kind, en, es, fields, guard_en, guard_es = sector
    job_en, job_es, goals, automations = ROLES[role]
    guidance = recommendations(list(goals))
    # A template recommends native capabilities; unknown external APIs are never
    # auto-granted. Their setup remains a visible requirement.
    tools = tuple(guidance["tools"])
    if set(tools) & {"create_appointment", "reschedule_appointment", "cancel_appointment"}:
        tools = tuple(dict.fromkeys((*tools, "check_appointment_availability", "create_appointment", "reschedule_appointment", "cancel_appointment")))
    role_en, role_es = ROLE_GUIDANCE.get(role, ("", ""))
    instruction_en = "You assist {{business_name}}. Use verified business context and authorized tools. Confirm actions only after successful tool results. Configured follow-ups and reminders are handled by the objective scheduler. " + guard_en + " " + role_en
    instruction_es = "Asistes a {{business_name}}. Usa contexto verificado y herramientas autorizadas. Confirma acciones solo después de resultados exitosos. El backend ejecuta los seguimientos y recordatorios configurados en los objetivos. " + guard_es + " " + role_es
    label_en, label_es = ROLE_LABELS.get((code, role), (f"{en} {job_en}", f"{job_es} {es}"))
    return AgentTemplateDefinition(LEGACY_IDS.get((code, role), f"{code}_{role}"), Label(label_en, label_es),
        Label(f"Help with {job_en} using verified business information.", f"Ayuda con {job_es.lower()} usando información verificada del negocio."),
        industry, kind, goals, ("whatsapp", "widget") if code not in {"ecommerce", "real_estate", "beauty"} else ("whatsapp", "instagram", "widget"),
        tools, Label(instruction_en, instruction_es), automations, fields,
        tags=_tags(code, role, goals))


TEMPLATES = tuple(_make(sector, role) for sector, roles in zip(SECTORS, SECTOR_ROLES) for role in roles) + tuple(
    _make(("general", "other", "other", "General", "general", ("services", "hours", "policies"), "Do not invent business facts.", "No inventes información del negocio."), role)
    for role in ("receptionist", "sales", "support", "qualification", "agenda", "follow_up")
)
_BY_ID = {template.id: template for template in TEMPLATES}


def validate_template_id(value: str | None) -> str | None:
    if value is not None and value not in _BY_ID:
        raise ValueError("Unknown agent template")
    return value


def validated_definition(template):
    """Prune retired references with explicit warnings rather than breaking apply."""
    data = asdict(template)
    warnings = []
    for field, allowed in (("objectives", {o.id for o in OBJECTIVES}), ("recommended_tools", {t.id for t in TOOLS}),
                           ("recommended_channels", CHANNELS), ("suggested_automations", AUTOMATIONS)):
        warnings.extend(f"{field}:{value}" for value in data[field] if value not in allowed)
        data[field] = [value for value in data[field] if value in allowed]
    return data, warnings


def template_defaults(template_id: str, language: str = "en") -> dict:
    validate_template_id(template_id)
    template = _BY_ID[template_id]
    data, _ = validated_definition(template)
    return {"template_id": template.id, "objectives": data["objectives"],
            "instructions": template.system_prompt_template.get(language), "prompt_language": "es" if language == "es" else "en"}


def matches(industry, business_type, objectives, channels=(), tools=()):
    scored = []
    for item in TEMPLATES:
        if not item.active:
            continue
        exact = item.industry == industry and item.business_type == business_type and business_type != "other"
        reasons = {"industry": 100 if item.industry == industry and industry != "other" else 0,
                   "business_type": 80 if exact else 0,
                   "objectives": 15 * len(set(item.objectives) & set(objectives)),
                   "tools": 2 * len(set(item.recommended_tools) & set(tools)),
                   "channels": len(set(item.recommended_channels) & set(channels))}
        # Broad receptionist coverage breaks equal matches for combined goals.
        score = sum(reasons.values())
        data, warnings = validated_definition(item)
        scored.append({"template": data, "score": score, "reasons": reasons, "warnings": warnings,
                       "exact_match": exact, "recommended": exact or (item.industry == "other" and not any(t.industry == industry and t.business_type == business_type for t in TEMPLATES))})
    return sorted(scored, key=lambda row: row["score"], reverse=True)


def recommend_templates(industry, business_type, objectives, channels, tools=()):
    """Compatibility helper retained for callers of the phase-one catalog."""
    return [_BY_ID[row["template"]["id"]] for row in matches(industry, business_type, objectives, channels, tools)
            if row["template"]["industry"] == industry]
