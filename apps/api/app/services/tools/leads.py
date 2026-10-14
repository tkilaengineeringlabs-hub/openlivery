"""Persist explicitly requested lead fields and deterministic temperature."""
import json
from pydantic import Field
from sqlalchemy import select
from ...database import new_session
from ...models import Agent, Conversation
from ...schemas_appointments import Strict
from .specs import ToolSpec


class LeadInput(Strict):
    name: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    need: str | None = Field(default=None, max_length=2000)
    budget: str | None = Field(default=None, max_length=120)
    date: str | None = Field(default=None, max_length=120)


def build_lead_spec(agent, conversation):
    if not agent.objectives_managed or "lead_qualification" not in agent.objectives or not conversation or conversation.channel == "playground":
        return None
    async def execute(arguments):
        values = LeadInput.model_validate(arguments).model_dump(exclude_none=True)
        with new_session() as db:
            current = db.scalar(select(Agent).where(Agent.id == agent.id, Agent.agency_id == agent.agency_id,
                Agent.client_id == agent.client_id, Agent.is_active.is_(True), Agent.deleted_at.is_(None)))
            conv = db.scalar(select(Conversation).where(Conversation.id == conversation.id,
                Conversation.agency_id == agent.agency_id, Conversation.client_id == agent.client_id, Conversation.agent_id == agent.id))
            if not current or not current.objectives_managed or "lead_qualification" not in current.objectives or not conv or conv.mode != "ai" or conv.status != "open":
                return "Lead qualification is unavailable", True
            allowed = set(current.objective_config["lead_qualification"]["fields"])
            if not set(values) <= allowed:
                return "Unselected lead fields are not permitted", True
            profile = {**conv.lead_profile, **values}
            # Hot requires an expressed need, budget and timing; warm needs a
            # stated need. No model-generated score or purchase prediction.
            temperature = "hot" if all(profile.get(key) for key in ("need", "budget", "date")) else "warm" if profile.get("need") else "cold"
            conv.lead_profile, conv.lead_temperature = profile, temperature
            db.commit()
            return json.dumps({"ok": True, "temperature": temperature, "recorded_fields": list(values)}), False
    return ToolSpec("qualify_lead", "Record only customer-provided lead information for selected fields; never invent values. Temperature is calculated by the backend.", LeadInput.model_json_schema(), handler=execute, permission_source="lead_qualification")
