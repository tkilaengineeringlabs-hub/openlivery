"""Closed, bounded automation DSL. No model attribute access or expressions."""
import json
import re
import uuid
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

UPCOMING_MINUTES = (15, 30, 60, 120, 720, 1440, 2880)
INACTIVITY_MINUTES = (5, 15, 30, 60, 120, 360, 720, 1440, 2880)
TRIGGERS = {"message_received", "client_created", "conversation_inactive", "appointment_created", "appointment_rescheduled", "appointment_cancelled", "appointment_completed", "appointment_upcoming"}
FIELDS = {"message.text", "channel", "client.name", "client.industry", "conversation.mode"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Condition(StrictModel):
    field: Literal["message.text", "channel", "client.name", "client.industry", "conversation.mode"]
    operator: Literal["equals", "not_equals", "contains", "not_contains", "exists", "not_exists"]
    value: str = Field(default="", max_length=2000)


class TriggerConfig(StrictModel):
    minutes: int | None = None


class Action(StrictModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)


class SendMessage(Action):
    type: Literal["send_message"]
    text: str = Field(min_length=1, max_length=8000)

    @field_validator("text")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value.strip()


class Handoff(Action):
    type: Literal["handoff_to_human"]


class Delay(Action):
    type: Literal["delay"]
    amount: int = Field(ge=1, le=43200)
    unit: Literal["minutes", "hours", "days"]

    @model_validator(mode="after")
    def bounded_delay(self):
        if self.amount * {"minutes": 1, "hours": 60, "days": 1440}[self.unit] > 43200:
            raise ValueError("Delay cannot exceed 30 days")
        return self


class HttpRequest(Action):
    type: Literal["http_request"]
    method: Literal["GET", "POST", "PUT", "PATCH"] = "POST"
    url: str = Field(min_length=1, max_length=2048)
    headers: dict[str, str] = Field(default_factory=dict, max_length=30)
    query: dict[str, str] = Field(default_factory=dict, max_length=30)
    body: dict = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ValueError("Use an HTTP(S) URL without credentials or fragments")
        _ = parts.port
        return value

    @model_validator(mode="after")
    def valid_http(self):
        if len(json.dumps([self.headers, self.query, self.body])) > 16000:
            raise ValueError("HTTP configuration exceeds 16 KB")
        for name, value in self.headers.items():
            if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]+", name) or "\r" in value or "\n" in value:
                raise ValueError("Invalid HTTP header")
            if name.lower() in {"host", "content-length", "transfer-encoding", "connection", "proxy-authorization"}:
                raise ValueError("Reserved HTTP header")
        return self


AutomationAction = Annotated[SendMessage | Handoff | Delay | HttpRequest, Field(discriminator="type")]


class AutomationWrite(StrictModel):
    template_id: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=1, max_length=180)
    client_id: uuid.UUID | None = None
    enabled: bool = True
    trigger_type: Literal["message_received", "client_created", "conversation_inactive", "appointment_created", "appointment_rescheduled", "appointment_cancelled", "appointment_completed", "appointment_upcoming"]
    trigger_config: TriggerConfig = Field(default_factory=TriggerConfig)
    conditions: list[Condition] = Field(default_factory=list, max_length=20)
    actions: list[AutomationAction] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def consistent(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Name cannot be blank")
        if self.trigger_type == "conversation_inactive":
            if self.trigger_config.minutes not in INACTIVITY_MINUTES:
                raise ValueError("Unsupported inactivity duration")
        elif self.trigger_type == "appointment_upcoming":
            if self.trigger_config.minutes not in UPCOMING_MINUTES:
                raise ValueError("Unsupported reminder lead time")
        elif self.trigger_config.minutes is not None:
            raise ValueError("This trigger has no duration")
        if len({a.id for a in self.actions}) != len(self.actions):
            raise ValueError("Action IDs must be unique")
        if self.trigger_type == "client_created":
            if any(a.type in {"send_message", "handoff_to_human"} for a in self.actions):
                raise ValueError("Client creation has no conversation destination")
            if any(not c.field.startswith("client.") for c in self.conditions):
                raise ValueError("Client creation only supports client fields")
        return self


class AutomationPatch(StrictModel):
    template_id: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_]+$")
    name: str | None = None
    client_id: uuid.UUID | None = None
    enabled: bool | None = None
    trigger_type: str | None = None
    trigger_config: dict | None = None
    conditions: list[dict] | None = None
    actions: list[dict] | None = None


class AutomationBatchItem(StrictModel):
    id: uuid.UUID
    configuration: AutomationWrite


class AutomationBatch(StrictModel):
    items: list[AutomationBatchItem] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_records(self):
        from .services.agent_catalog.templates import AUTOMATIONS
        if any(item.configuration.template_id not in AUTOMATIONS for item in self.items):
            raise ValueError("Unsupported batch template")
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate automation IDs")
        if any(item.configuration.client_id is None for item in self.items):
            raise ValueError("Batch automation requires a business")
        if len({item.configuration.client_id for item in self.items}) != 1:
            raise ValueError("Batch automations must belong to one business")
        return self
