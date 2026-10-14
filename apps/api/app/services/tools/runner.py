"""Single entry point for generating an agent reply, with or without tools.

Drop-in replacement for chat_completion at the chat call sites: same error
semantics (HTTPException 502 on provider failure), same Completion result —
plus tool_calls metadata when tools ran.
"""

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...models import Agent, Conversation
from ..ai import Completion
from .registry import load_custom_tool_specs, ToolRegistry, validate_runtime_scope
from .executor import CURRENT_EXECUTOR, ToolExecutor, NATIVE_NAMES

# Injected whenever the agent has tools: a failing tool must never be papered
# over with the model's own knowledge.
TOOL_FAILURE_RULE = (
    "Tool usage rules: when the user's request depends on a tool and the tool call fails or returns an error, "
    "do not answer from memory and do not invent data. Tell the user that the information or action is not "
    "available right now and that they can try again later."
)


def _with_tool_rules(messages: list[dict]) -> list[dict]:
    amended = list(messages)
    for index, message in enumerate(amended):
        if message["role"] == "system":
            amended[index] = {**message, "content": f"{message['content']}\n\n{TOOL_FAILURE_RULE}"}
            return amended
    return [{"role": "system", "content": TOOL_FAILURE_RULE}, *amended]


async def run_completion(
    db: Session,
    agent: Agent,
    base_url: str,
    api_key: str,
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    extra_specs: list | None = None,
    conversation: Conversation | None = None,
) -> Completion:
    validate_runtime_scope(agent, conversation)
    from ..model_providers import get_provider
    provider = get_provider(agent.provider)
    model = agent.model.strip()
    custom_specs = load_custom_tool_specs(db, agent)
    from .appointments import build_appointment_specs
    native = build_appointment_specs(agent, conversation)
    from .knowledge import build_knowledge_spec
    knowledge_spec = build_knowledge_spec(agent)
    if knowledge_spec:
        native.append(knowledge_spec)
    from .leads import build_lead_spec
    lead_spec = build_lead_spec(agent, conversation)
    if lead_spec:
        native.append(lead_spec)
    from ..objectives import runtime_guidance
    if agent.objectives_managed:
        messages = [*messages, {"role": "system", "content": runtime_guidance(agent)}]
    additions = list(extra_specs or [])
    escalation_holder = []
    if agent.objectives_managed and conversation and conversation.channel != "playground" and "handoff_to_human" in agent.objectives:
        cfg = agent.objective_config["handoff_to_human"]
        last_user = next((str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"), "")
        if cfg["human_request"] and any(word.casefold() in last_user.casefold() for word in cfg["keywords"]):
            from ..escalation import build_escalation_spec, apply_escalation
            spec = build_escalation_spec([], escalation_holder)
            executor = ToolExecutor(agent.agency_id, agent.client_id, agent.id, conversation.id, agent.provider, model)
            _, failed = await executor.execute("escalate_to_human", spec, {"trigger": "human_request", "reason": "Explicit human request"})
            if not failed:
                await apply_escalation(db, conversation, agent, escalation_holder[-1])
                return Completion("Una persona continuará la conversación contigo." if agent.prompt_language == "es" else "A person will continue the conversation with you.", tool_calls=executor.metadata)
    if conversation and conversation.channel != "playground" and not any(spec.name == "escalate_to_human" for spec in additions):
        from ..escalation import active_rules, escalation_enabled, build_escalation_spec, escalation_prompt
        rules = active_rules(db, agent)
        if escalation_enabled(db, agent, rules):
            additions.append(build_escalation_spec(rules, escalation_holder, builtin_enabled=agent.escalation_builtin_enabled))
            messages = [*messages, {"role": "system", "content": escalation_prompt(rules, builtin_enabled=agent.escalation_builtin_enabled)}]
    specs = native + [spec for spec in custom_specs if spec.name not in NATIVE_NAMES] + additions
    specs = list(ToolRegistry.from_specs(specs).specs.values())
    if any(spec.permission_source == "appointments_enabled" for spec in native):
        messages = [*messages, {"role": "system", "content": (
            "For appointments, use the business timezone and current date from check_appointment_availability. "
            "Always check real availability. Never say an appointment is booked, moved or cancelled unless "
            "the corresponding native tool returned ok=true. On slot_unavailable, check again and offer alternatives. "
            "Ask the customer to choose a slot and provide their name before booking.")} ]
    capabilities = provider.capabilities(model)
    if specs and agent.provider in ("ollama", "groq"):
        capabilities = await provider.model_capabilities(base_url, api_key, model)
    if specs and (capabilities.tools is False or (agent.provider in ("groq", "ollama") and capabilities.tools is not True)):
        specs = []
        messages = [*messages, {"role": "system", "content": "Tools are unavailable with this model. Answer as chat only. Never claim to perform appointments, webhooks or handoff. Some agent capabilities are unavailable."}]
    if specs:
        messages = _with_tool_rules(messages)
        messages = [*messages, {"role": "system", "content": "Authorized tools: " + ", ".join(spec.name for spec in specs) + ". Objectives never grant extra permissions. At most five tool calls per turn."}]
    system = "\n\n".join(message["content"] for message in messages if message.get("role") == "system")
    messages = [{"role": "system", "content": system}, *[message for message in messages if message.get("role") != "system"]]
    executor = ToolExecutor(agent.agency_id, agent.client_id, agent.id, conversation.id if conversation else None, agent.provider, model)
    token = CURRENT_EXECUTOR.set(executor)
    try:
        completion = await provider.chat(base_url, api_key, model, messages, tools=specs or None, temperature=temperature, max_tokens=max_tokens)
        if escalation_holder:
            from ..escalation import apply_escalation
            await apply_escalation(db, conversation, agent, escalation_holder[-1])
        return completion
    except HTTPException as exc:
        if str(exc.detail).endswith(".tool_limit"):
            return Completion("Se alcanzó el límite de herramientas de este turno. Revisa las acciones realizadas antes de intentar de nuevo." if agent.prompt_language == "es" else "This turn reached its tool limit. Check completed actions before trying again.", tool_calls=executor.metadata or None)
        raise
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise HTTPException(502, "Could not get a valid response from the AI provider. Check the API key and the model.") from exc
    finally:
        # A registered handoff survives a later provider error; existing social
        # delivery holders retain their deferred/uncertain-send policy.
        try:
            if escalation_holder and conversation.mode != "human":
                from ..escalation import apply_escalation
                await apply_escalation(db, conversation, agent, escalation_holder[-1])
        finally:
            CURRENT_EXECUTOR.reset(token)
