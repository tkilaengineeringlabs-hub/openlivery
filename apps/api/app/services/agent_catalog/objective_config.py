"""Human-facing objective schemas and validated defaults, shared by API and UI."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Questions(Strict):
    business: bool = True
    knowledge: bool = True
    faqs: bool = True
    services: bool = True


class FollowUp(Strict):
    first_minutes: int = Field(default=120, ge=1, le=43200)
    second_minutes: int = Field(default=1440, ge=1, le=43200)
    max_attempts: int = Field(default=2, ge=1, le=2)
    message: str = Field(default="Hello, can we help you continue?", min_length=1, max_length=8000)


class Reminders(Strict):
    confirmation: bool = True
    reminder24: bool = True
    reminder2: bool = True
    reminder24_minutes: int = Field(default=1440, ge=1, le=43200)
    reminder2_minutes: int = Field(default=120, ge=1, le=43200)
    after_appointment: bool = False
    confirmation_message: str = Field(default="Hello {{customer.name}}, your appointment is on {{appointment_date}} at {{appointment_time}}.", min_length=1, max_length=8000)
    reminder_message: str = Field(default="Hello {{customer.name}}, remember your appointment on {{appointment_date}} at {{appointment_time}}.", min_length=1, max_length=8000)
    after_message: str = Field(default="Thank you for your visit, {{customer.name}}. Can we help you further?", min_length=1, max_length=8000)


class Booking(Strict):
    calendar: Literal["internal", "google"] = "internal"
    service_ids: list[str] = Field(default_factory=list, max_length=100)
    allow_reschedule: bool = True
    allow_cancel: bool = True


class Handoff(Strict):
    human_request: bool = True
    cannot_solve: bool = True
    keywords: list[str] = Field(default_factory=lambda: ["human", "person", "advisor"], max_length=10)


class Leads(Strict):
    fields: list[Literal["name", "phone", "email", "need", "budget", "date"]] = Field(default_factory=lambda: ["name", "need", "budget", "date"], max_length=6)


class Sales(Strict):
    present_products: bool = True
    answer_questions: bool = True
    recommend_next_action: bool = True
    human_help: bool = True


class After(Strict):
    message: str = Field(default="Thank you for your visit, {{customer.name}}. Can we help you further?", min_length=1, max_length=8000)


SCHEMAS = {"respond_questions": Questions, "customer_support": Questions, "resolve_support": Questions,
           "sales": Sales, "lead_qualification": Leads, "follow_up": FollowUp,
           "book_appointment": Booking, "reschedule_appointment": Booking, "cancel_appointment": Booking,
           "appointment_reminder": Reminders, "post_appointment_followup": After, "handoff_to_human": Handoff,
           "order_lookup": Strict, "inventory_lookup": Strict}


def defaults(code, language="en"):
    values = SCHEMAS[code]().model_dump()
    if language == "es":
        if code == "follow_up":
            values["message"] = "Hola, ¿pudiste revisar la información? Si quieres puedo ayudarte a continuar."
        if code == "handoff_to_human":
            values["keywords"] = ["asesor", "persona", "humano"]
        for field in ("confirmation_message", "reminder_message"):
            if field in values:
                values[field] = "Hola {{customer.name}}, tu cita es el {{appointment_date}} a las {{appointment_time}}."
        for field in ("after_message", "message"):
            if code in {"appointment_reminder", "post_appointment_followup"} and field in values:
                values[field] = "Gracias por tu visita, {{customer.name}}. ¿Podemos ayudarte con algo más?"
    return values


def validate_config(code, values, language="en"):
    from ..automations.appointments import TOKEN, VARIABLES
    result = SCHEMAS[code].model_validate({**defaults(code, language), **values}).model_dump()
    for key, value in result.items():
        if key.endswith("message") or key == "message":
            if not value.strip():
                raise ValueError("Message cannot be blank")
            variables = TOKEN.findall(value)
            if (code == "follow_up" and variables) or any(variable not in VARIABLES for variable in variables):
                raise ValueError("Unsupported message variable")
    if code == "handoff_to_human" and any(not word.strip() or len(word) > 80 for word in result["keywords"]):
        raise ValueError("Invalid handoff keyword")
    if code == "lead_qualification" and len(set(result["fields"])) != len(result["fields"]):
        raise ValueError("Duplicate lead field")
    return result


def category(code):
    if code in {"book_appointment", "reschedule_appointment", "cancel_appointment", "appointment_reminder"}:
        return "appointments"
    if code in {"follow_up", "post_appointment_followup"}:
        return "followup"
    if code in {"sales", "lead_qualification"}:
        return "sales"
    if code in {"resolve_support", "order_lookup", "inventory_lookup"}:
        return "support"
    return "care"
