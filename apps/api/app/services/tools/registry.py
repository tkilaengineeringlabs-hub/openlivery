"""Resolve the existing per-agent HTTP/MCP allowlist inside its tenant boundary.

This registry contains execution specs, not integration marketing entries. Native
appointment and escalation specs keep their existing contextual permission checks.
"""
from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping

from fastapi import HTTPException
import uuid
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ...models import Agent, AgentTool, Client
from .specs import ToolSpec, build_tool_specs


@dataclass(frozen=True)
class ToolRegistry:
    specs: Mapping[str, ToolSpec]

    @classmethod
    def from_specs(cls, specs: list[ToolSpec]) -> "ToolRegistry":
        indexed: dict[str, ToolSpec] = {}
        for spec in specs:
            if spec.name in indexed:
                raise ValueError("Duplicate tool name")
            indexed[spec.name] = spec
        return cls(MappingProxyType(indexed))

    def get(self, name: str) -> ToolSpec | None:
        return self.specs.get(name)


def load_custom_tool_specs(db: Session, agent: Agent) -> list[ToolSpec]:
    owned = db.scalar(select(Agent.id).join(Client, Client.id == Agent.client_id).where(
        Agent.id == agent.id, Agent.agency_id == agent.agency_id,
        Agent.client_id == agent.client_id, Client.agency_id == agent.agency_id,
        Agent.deleted_at.is_(None),
    ))
    if not owned:
        raise HTTPException(404, "Agent not found")
    shared = [uuid.UUID(str(item)) for item in getattr(agent, "shared_tool_ids", [])]
    rows = db.scalars(select(AgentTool).join(Agent, Agent.id == AgentTool.agent_id).where(
        or_(AgentTool.agent_id == owned, AgentTool.id.in_(shared)),
        AgentTool.enabled.is_(True), Agent.deleted_at.is_(None),
        Agent.agency_id == agent.agency_id, Agent.client_id == agent.client_id,
    ).order_by(AgentTool.created_at, AgentTool.id)).all()
    specs = build_tool_specs(list(rows))
    try:
        return list(ToolRegistry.from_specs(specs).specs.values())
    except ValueError:
        raise HTTPException(422, "builder.duplicate_tools") from None


def validate_runtime_scope(agent: Agent, conversation=None):
    """Check related ownership before credentials, knowledge or provider calls."""
    client = agent.client
    if not client or client.id != agent.client_id or client.agency_id != agent.agency_id:
        raise HTTPException(404, "Agent context unavailable")
    if conversation and (conversation.agent_id != agent.id or conversation.agency_id != agent.agency_id
                         or conversation.client_id != agent.client_id):
        raise HTTPException(404, "Agent context unavailable")
