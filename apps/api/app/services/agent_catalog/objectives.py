"""Stable objective identifiers, bilingual labels and honest capability guidance."""
from dataclasses import dataclass
from ...industries import Label


@dataclass(frozen=True)
class ObjectiveDefinition:
    id: str
    label: Label
    recommended_tools: tuple[str, ...] = ()
    suggested_automations: tuple[str, ...] = ()
    requires_configuration: bool = False


OBJECTIVES = (
    ObjectiveDefinition("respond_questions", Label("Answer questions", "Responder preguntas"), ("knowledge",)),
    ObjectiveDefinition("customer_support", Label("Customer support", "Atender clientes"), ("knowledge", "escalate_to_human")),
    ObjectiveDefinition("sales", Label("Sell", "Vender"), ("knowledge",)),
    ObjectiveDefinition("lead_qualification", Label("Qualify leads", "Calificar leads"), ("knowledge", "qualify_lead")),
    ObjectiveDefinition("follow_up", Label("Follow up", "Dar seguimiento"), (), ("followUp",), True),
    ObjectiveDefinition("book_appointment", Label("Book appointments", "Agendar citas"), ("check_appointment_availability", "create_appointment"), ("confirmation",), True),
    ObjectiveDefinition("reschedule_appointment", Label("Reschedule appointments", "Reagendar citas"), ("check_appointment_availability", "reschedule_appointment"), (), True),
    ObjectiveDefinition("cancel_appointment", Label("Cancel appointments", "Cancelar citas"), ("cancel_appointment",), (), True),
    ObjectiveDefinition("appointment_reminder", Label("Remind customers", "Recordar citas"), (), ("reminder24", "reminder2"), True),
    ObjectiveDefinition("post_appointment_followup", Label("After-service follow-up", "Seguimiento postservicio"), (), ("afterAppointment",), True),
    ObjectiveDefinition("order_lookup", Label("Look up orders", "Consultar pedidos"), ("http",), (), True),
    ObjectiveDefinition("inventory_lookup", Label("Look up inventory", "Consultar inventario"), ("http",), (), True),
    ObjectiveDefinition("resolve_support", Label("Resolve support requests", "Resolver soporte"), ("knowledge", "escalate_to_human")),
    ObjectiveDefinition("handoff_to_human", Label("Pass to a human", "Pasar a humano"), ("escalate_to_human",)),
)
_BY_ID = {objective.id: objective for objective in OBJECTIVES}


def validate_objectives(values: list[str]) -> list[str]:
    if any(value not in _BY_ID for value in values):
        raise ValueError("Unknown agent objective")
    if len(set(values)) != len(values):
        raise ValueError("Duplicate agent objective")
    return values


def recommendations(objectives: list[str]) -> dict[str, list[str]]:
    validate_objectives(objectives)
    return {
        "tools": list(dict.fromkeys(tool for code in objectives for tool in _BY_ID[code].recommended_tools)),
        "automations": list(dict.fromkeys(rule for code in objectives for rule in _BY_ID[code].suggested_automations)),
    }
