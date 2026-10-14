"""Knowledge search over the existing agent-owned retrieval and Q&A."""
import json
from pydantic import Field
from sqlalchemy import select
from ...database import new_session
from ...models import Agent, Client, AppointmentService
from ...schemas_appointments import Strict
from ..knowledge import retrieve_knowledge, _chunks, _terms
from .specs import ToolSpec


class Search(Strict):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)


def build_knowledge_spec(agent):
    if not agent.knowledge_enabled:
        return None
    agency_id, client_id, agent_id = agent.agency_id, agent.client_id, agent.id

    async def execute(arguments):
        args = Search.model_validate(arguments)
        with new_session() as db:
            current = db.scalar(select(Agent).join(Client, Client.id == Agent.client_id).where(
                Agent.id == agent_id, Agent.agency_id == agency_id, Agent.client_id == client_id,
                Client.agency_id == agency_id, Client.is_active.is_(True), Agent.knowledge_enabled.is_(True),
                Agent.is_active.is_(True), Agent.deleted_at.is_(None)))
            if not current:
                return json.dumps({"ok": False, "error": "knowledge_unavailable"}), True
            knowledge = await retrieve_knowledge(db, current, args.query)
            from ..objectives import sources
            permissions = sources(current)
            text = knowledge.text + "\n\n" + "\n\n".join(f"{qa.question}\n{qa.answer}" for qa in current.qa_pairs if permissions["faqs"])
            if permissions["business"]:
                text += "\n" + "\n".join([current.brief_summary, current.brief_products, current.brief_policies])
            if permissions["services"]:
                text += "\n" + "\n".join(row.name for row in db.scalars(select(AppointmentService).where(AppointmentService.agency_id == agency_id, AppointmentService.client_id == client_id, AppointmentService.active.is_(True))))
            terms = _terms(args.query)
            pieces = sorted(_chunks(text), key=lambda chunk: sum(chunk.lower().count(term) for term in terms), reverse=True)
            results = [{"text": chunk} for chunk in pieces[:args.limit] if chunk.strip()]
            return json.dumps({"ok": True, "results": results, "sources": knowledge.sources,
                "instruction": "Answer from these business facts. If no relevant fact exists, say it is unavailable."}), False

    return ToolSpec("knowledge_search", "Search this agent's authorized business documents and Q&A. Use for factual business questions. Never invent facts when results do not contain the answer.",
        Search.model_json_schema(), handler=execute, permission_source="knowledge_enabled")
