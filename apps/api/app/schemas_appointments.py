"""Validated native booking inputs. All instants must carry an explicit offset."""
import uuid
from datetime import datetime, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, EmailStr, field_validator, model_validator

AppointmentStatus = Literal["scheduled", "confirmed", "completed", "cancelled", "no_show"]


def valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Invalid IANA timezone") from None
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ServiceWrite(Strict):
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=4000)
    price: str | None = Field(default=None, pattern=r"^\d{1,10}(\.\d{1,2})?$", max_length=32)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    duration_minutes: int = Field(ge=1, le=1440)
    buffer_before_minutes: int = Field(default=0, ge=0, le=360)
    buffer_after_minutes: int = Field(default=0, ge=0, le=360)
    active: bool = True


class ServiceCreate(ServiceWrite):
    client_id: uuid.UUID


class ServicePatch(Strict):
    price: str | None = None
    color: str | None = None
    name: str | None = None
    description: str | None = None
    duration_minutes: int | None = None
    buffer_before_minutes: int | None = None
    buffer_after_minutes: int | None = None
    active: bool | None = None


class Interval(Strict):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    active: bool = True

    @model_validator(mode="after")
    def valid_interval(self):
        if self.start_time.tzinfo or self.end_time.tzinfo or self.start_time >= self.end_time:
            raise ValueError("Use increasing local times within one day")
        if any((self.start_time.second, self.start_time.microsecond, self.end_time.second, self.end_time.microsecond)):
            raise ValueError("Use whole minutes")
        return self


class AvailabilityWrite(Strict):
    client_id: uuid.UUID
    timezone: str = Field(max_length=64)
    slot_minutes: int = Field(default=15, ge=5, le=120)
    min_notice_minutes: int = Field(default=0, ge=0, le=43200)
    booking_days: int = Field(default=365, ge=1, le=730)
    reminders: list[Literal[120, 1440]] = Field(default_factory=list, max_length=2)
    rules: list[Interval] = Field(max_length=42)
    _timezone = field_validator("timezone")(valid_timezone)

    @model_validator(mode="after")
    def nonoverlapping(self):
        for day in range(7):
            intervals = sorted((r.start_time, r.end_time) for r in self.rules if r.active and r.weekday == day)
            if any(left[1] > right[0] for left, right in zip(intervals, intervals[1:])):
                raise ValueError("Working intervals cannot overlap")
        return self


class BlockCreate(Strict):
    client_id: uuid.UUID
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def increasing(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("End must follow start")
        return self


class AppointmentCreate(Strict):
    client_id: uuid.UUID
    service_id: uuid.UUID
    starts_at: AwareDatetime
    customer_name: str = Field(min_length=1, max_length=180)
    customer_phone: str | None = Field(default=None, max_length=40)
    customer_email: EmailStr | None = None
    notes: str = Field(default="", max_length=8000)
    agent_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    status: Literal["scheduled", "confirmed"] = "scheduled"
    source: Literal["manual", "agent", "whatsapp", "instagram", "web", "automation"] = "manual"


class AppointmentPatch(Strict):
    customer_name: str | None = Field(default=None, min_length=1, max_length=180)
    customer_phone: str | None = Field(default=None, max_length=40)
    customer_email: EmailStr | None = None
    notes: str | None = Field(default=None, max_length=8000)
    status: AppointmentStatus | None = None


class Reschedule(Strict):
    starts_at: AwareDatetime
    service_id: uuid.UUID | None = None
