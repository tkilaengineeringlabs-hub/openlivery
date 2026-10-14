"""Shared, scoped execution boundary and durable, secret-free tool audit."""
import inspect
import asyncio
import json
import time
import uuid
from datetime import datetime
from contextvars import ContextVar
from dataclasses import dataclass, field

from fastapi import HTTPException
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry
from sqlalchemy import select

from ...database import new_session
from ...models import Agent, AgentTool, Client, Conversation, ToolExecution, now_utc
from .specs import ToolSpec

CURRENT_EXECUTOR = ContextVar("agent_tool_executor", default=None)
MAX_TOOL_EXECUTIONS = 5
NATIVE_NAMES = {"qualify_lead", "knowledge_search", "check_appointment_availability", "create_appointment", "reschedule_appointment", "cancel_appointment", "escalate_to_human"}
SENSITIVE = ("secret", "token", "password", "authorization", "cookie", "api_key", "header", "phone", "email", "notes", "customer_name", "query", "reason")


def safe_arguments(value, depth=0):
    if depth > 4:
        return "[omitted]"
    if isinstance(value, dict):
        return {str(k)[:80]: "[redacted]" if any(word in str(k).lower() for word in SENSITIVE) else safe_arguments(v, depth+1)
                for k, v in list(value.items())[:30]}
    if isinstance(value, list):
        return [safe_arguments(item, depth+1) for item in value[:20]]
    if isinstance(value, str):
        # Keep domain IDs and instants, never arbitrary free-form payloads.
        try:
            uuid.UUID(value)
            return value
        except ValueError:
            pass
        try:
            if len(value) <= 40:
                datetime.fromisoformat(value)
                return value
        except ValueError:
            pass
        return value if len(value) <= 100 and (value.replace('-', '').replace(':', '').replace('+', '').replace('.', '').isdigit()) else "[omitted]"
    return value if isinstance(value, (bool, int, float, type(None))) else "[omitted]"


def safe_result(name, result, failed, custom=False):
    if custom:
        return "External tool failed" if failed else "External tool completed"
    try:
        data = json.loads(result.removeprefix("Tool call failed: "))
        if name == "qualify_lead":
            return json.dumps({"ok": not failed, "temperature": data.get("temperature")})
        if name == "knowledge_search":
            return json.dumps({"ok": not failed, "result_count": len(data.get("results", []))})
        if name == "check_appointment_availability":
            return json.dumps({"ok": not failed, "available_slots": len(data.get("slots", []))})
        appointment = data.get("appointment") or {}
        return json.dumps({"ok": not failed, "appointment_id": appointment.get("id"), "status": appointment.get("status")})
    except (ValueError, TypeError, AttributeError):
        return "Tool failed" if failed else "Tool completed"


async def invoke(spec, args):
    """Schema validation also applies to direct provider transport tests."""
    try:
        Draft202012Validator.check_schema(spec.input_schema)
        valid = isinstance(args, dict) and Draft202012Validator(spec.input_schema, format_checker=FormatChecker(), registry=Registry()).is_valid(args)
    except Exception:
        # External schema references are never fetched from the network.
        valid = False
    if not valid:
        return "Tool call denied: invalid arguments", True
    try:
        if spec.handler is not None:
            result = spec.handler(args)
            if inspect.isawaitable(result):
                result = await result
        elif spec.mcp_tool_name is not None:
            from .mcp_client import call_mcp_tool
            if CURRENT_EXECUTOR.get() is not None:
                from urllib.parse import urlsplit
                from .http_exec import _blocked_reason
                parsed = urlsplit(spec.tool.url)
                if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
                    return "Tool call denied: invalid integration URL", True
                blocked = await asyncio.wait_for(asyncio.to_thread(_blocked_reason, spec.tool.url, allow_private=False), 5)
                if blocked:
                    return "Tool call denied: integration destination blocked", True
            result = await call_mcp_tool(spec.tool, spec.mcp_tool_name, args)
        else:
            from .http_exec import execute_http_tool
            result = await execute_http_tool(spec.tool, args, strict=CURRENT_EXECUTOR.get() is not None)
        text, failed = result
        return (f"Tool call failed: {text}" if failed else text), failed
    except Exception:
        return "Tool call failed: tool unavailable. Do not confirm success.", True


@dataclass
class ToolExecutor:
    agency_id: object
    client_id: object
    agent_id: object
    conversation_id: object | None
    provider: str
    model: str
    metadata: list = field(default_factory=list)
    handoff_registered: bool = False

    def permitted(self, db, spec):
        if self.handoff_registered:
            return False
        agent = db.scalar(select(Agent).join(Client, Client.id == Agent.client_id).where(
            Agent.id == self.agent_id, Agent.agency_id == self.agency_id, Agent.client_id == self.client_id,
            Client.agency_id == self.agency_id, Client.is_active.is_(True), Agent.is_active.is_(True), Agent.deleted_at.is_(None)))
        if not agent:
            return False
        if self.conversation_id:
            conversation = db.scalar(select(Conversation).where(Conversation.id == self.conversation_id,
                Conversation.agency_id == self.agency_id, Conversation.client_id == self.client_id, Conversation.agent_id == self.agent_id))
            if (not conversation or conversation.mode != "ai" or conversation.status != "open"
                    or (conversation.contact and conversation.contact.blocked_at)):
                return False
        if spec is None:
            return False
        if spec.tool is not None:
            owner = db.scalar(select(AgentTool).join(Agent, Agent.id == AgentTool.agent_id).where(
                AgentTool.id == spec.tool.id, AgentTool.enabled.is_(True), Agent.agency_id == self.agency_id,
                Agent.client_id == self.client_id, Agent.is_active.is_(True), Agent.deleted_at.is_(None)))
            if not owner or not (owner.agent_id == self.agent_id or str(owner.id) in agent.shared_tool_ids):
                return False
            from .specs import build_tool_specs
            fresh = next((item for item in build_tool_specs([owner]) if item.name == spec.name), None)
            if fresh is None:
                return False
            spec.tool, spec.input_schema = owner, fresh.input_schema
            return True
        if spec.name == "qualify_lead":
            return bool(self.conversation_id and agent.objectives_managed and "lead_qualification" in agent.objectives)
        if spec.name == "knowledge_search":
            return agent.knowledge_enabled
        if spec.name in NATIVE_NAMES - {"knowledge_search", "escalate_to_human"}:
            from ..objectives import calendar_ready
            return calendar_ready(db, agent, spec.name)
        if spec.name == "escalate_to_human":
            from ..escalation import active_rules, escalation_enabled
            return self.conversation_id is not None and escalation_enabled(db, agent, active_rules(db, agent))
        return False

    async def execute(self, name, spec, args):
        started = time.monotonic()
        with new_session() as db:
            permitted = self.permitted(db, spec)
            current = db.get(Agent, self.agent_id)
            if permitted and name == "escalate_to_human" and current.objectives_managed and isinstance(args, dict) and args.get("rule") is None:
                cfg = current.objective_config.get("handoff_to_human", {})
                permitted = "handoff_to_human" in current.objectives and args.get("trigger") in {key for key in ("human_request", "cannot_solve") if cfg.get(key, True)}
            conversation = db.get(Conversation, self.conversation_id) if self.conversation_id else None
            channel = conversation.channel if conversation else None
            row = ToolExecution(agency_id=self.agency_id, client_id=self.client_id, agent_id=self.agent_id,
                conversation_id=self.conversation_id, provider=self.provider, model=self.model, channel=channel,
                tool_name=name[:64], status="started" if permitted else "denied", arguments=safe_arguments(args))
            db.add(row)
            db.commit()  # Fail closed before side effects if audit storage is unavailable.
            execution_id = row.id
        result, failed = await invoke(spec, args) if permitted else ("Tool call denied: tool is not permitted", True)
        if name == "escalate_to_human" and not failed:
            self.handoff_registered = True
        summary = safe_result(name, result, failed, custom=bool(spec and spec.tool)) if permitted else "Tool call denied: tool is not permitted"
        latency = int((time.monotonic()-started)*1000)
        with new_session() as db:
            row = db.get(ToolExecution, execution_id)
            row.status = "denied" if not permitted else "failed" if failed else "succeeded"
            row.result_summary = summary
            row.latency_ms = latency
            row.finished_at = now_utc()
            db.commit()
        self.metadata.append({"name": name, "arguments": safe_arguments(args), "result_preview": summary,
            "is_error": failed, "execution_id": str(execution_id), "latency_ms": latency})
        return result, failed


class ToolDispatcher:
    """Normalize calls from every provider into the same execution boundary."""
    def __init__(self, specs, provider):
        from .registry import ToolRegistry
        self.registry = ToolRegistry.from_specs(specs)
        self.provider = provider
        self.calls = 0
        self.executor = CURRENT_EXECUTOR.get()
        self.metadata = self.executor.metadata if self.executor else []

    async def call(self, name, args):
        if self.calls >= MAX_TOOL_EXECUTIONS:
            raise HTTPException(502, f"{self.provider}.tool_limit")
        self.calls += 1
        spec = self.registry.get(name)
        if self.executor:
            return await self.executor.execute(name, spec, args)
        if spec is None:
            result, failed = "Tool call denied: tool is not permitted", True
        else:
            result, failed = await invoke(spec, args)
        self.metadata.append({"name": name, "arguments": safe_arguments(args), "result_preview": result[:500], "is_error": failed})
        return result, failed
