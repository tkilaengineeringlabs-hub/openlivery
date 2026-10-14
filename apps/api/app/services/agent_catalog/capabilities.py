"""Descriptors of existing capabilities, separate from executable ToolSpec objects."""
from dataclasses import dataclass
from typing import Literal
from ...industries import Label


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    label: Label
    mode: Literal["context", "native_tool", "custom_tool"]
    permission_source: str
    requirements: tuple[str, ...]


TOOLS = (
    ToolDefinition("qualify_lead", Label("Lead qualification", "Calificación de leads"), "native_tool", "lead_qualification", ("verified_conversation",)),
    ToolDefinition("knowledge", Label("Knowledge base", "Base de conocimiento"), "native_tool", "knowledge_enabled", ("agent_knowledge",)),
    ToolDefinition("check_appointment_availability", Label("Check availability", "Consultar disponibilidad"), "native_tool", "appointments_enabled", ("client_appointment_services", "verified_conversation")),
    ToolDefinition("create_appointment", Label("Book appointment", "Agendar cita"), "native_tool", "appointments_enabled", ("client_appointment_services", "verified_conversation")),
    ToolDefinition("reschedule_appointment", Label("Reschedule appointment", "Reagendar cita"), "native_tool", "appointments_enabled", ("owned_customer_appointment", "verified_conversation")),
    ToolDefinition("cancel_appointment", Label("Cancel appointment", "Cancelar cita"), "native_tool", "appointments_enabled", ("owned_customer_appointment", "verified_conversation")),
    ToolDefinition("escalate_to_human", Label("Human handoff", "Pasar a humano"), "native_tool", "escalation_configuration", ("verified_conversation",)),
    ToolDefinition("http", Label("External API / webhook", "API externa / webhook"), "custom_tool", "enabled_agent_tool", ("configured_http_tool",)),
    ToolDefinition("mcp", Label("MCP tools", "Herramientas MCP"), "custom_tool", "enabled_agent_tool", ("configured_mcp_server",)),
)
