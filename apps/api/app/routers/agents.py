import re
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pypdf import PdfReader
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Agent, AgentQA, AgentTool, Client, EscalationRule, KnowledgeChunk, KnowledgeDocument, PortalUser, Team, User, WhatsAppChannel, WhatsAppCloudChannel, WidgetChannel, now_utc
from ..schemas import AgentCreate, AgentOut, AgentPromptOut, AgentUpdate, DocumentOut, EscalationConfigIn, EscalationConfigOut, QAPairCreate, QAPairOut, check_reply_delay
from ..services.knowledge import build_system_prompt, embed_document_chunks


router = APIRouter(prefix="/agents", tags=["Agents"])
MAX_PDF_BYTES = 20 * 1024 * 1024


def _agent(db: Session, user: User, agent_id: uuid.UUID) -> Agent:
    agent = db.scalar(
        select(Agent)
        .options(joinedload(Agent.client).selectinload(Client.agents))
        .where(Agent.id == agent_id, Agent.agency_id == user.agency_id, Agent.deleted_at.is_(None))
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _enrich_agents(db, user, [agent])[0]


def _validate_client(db: Session, user: User, client_id: uuid.UUID) -> None:
    client = db.scalar(select(Client).where(Client.id == client_id, Client.agency_id == user.agency_id))
    if not client:
        raise HTTPException(status_code=400, detail="The selected client does not exist")


def _channels_of(db: Session, agent: Agent) -> list[WhatsAppChannel | WhatsAppCloudChannel | WidgetChannel]:
    """Every channel this agent answers: both WhatsApp lines and the web chat."""
    from ..models import SocialChannel
    return [
        *db.scalars(select(SocialChannel).where(SocialChannel.agent_id == agent.id)).all(),
        *db.scalars(select(WhatsAppChannel).where(WhatsAppChannel.agent_id == agent.id)).all(),
        *db.scalars(select(WhatsAppCloudChannel).where(WhatsAppCloudChannel.agent_id == agent.id)).all(),
        *db.scalars(select(WidgetChannel).where(WidgetChannel.agent_id == agent.id)).all(),
    ]


async def _validate_ollama(db: Session, user: User, provider: str, model: str) -> None:
    if provider not in ("ollama", "groq"):
        return
    from ..services.providers import resolve_provider_credentials
    from ..services.model_providers import get_provider
    connection = resolve_provider_credentials(db, user.agency_id, provider)
    if not connection:
        raise HTTPException(422, f"{provider}.not_configured")
    if model not in await get_provider(provider).list_models(*connection):
        raise HTTPException(422, f"{provider}.model_missing")


def _enrich_agents(db: Session, user: User, agents: list[Agent]) -> list[Agent]:
    from ..models import SocialChannel
    if not agents:
        return agents
    by_id = {agent.id: agent for agent in agents}
    for agent in agents:
        from ..services.objectives import statuses
        agent.objective_status = statuses(db, agent)
        agent.channel_types = []
        agent.custom_tool_names = []
    for model, kind in ((WhatsAppChannel, "whatsapp"), (WhatsAppCloudChannel, "whatsapp_cloud"), (WidgetChannel, "widget"), (SocialChannel, None)):
        for row in db.scalars(select(model).where(model.agency_id == user.agency_id, model.agent_id.in_(by_id))):
            owner = by_id[row.agent_id]
            if row.client_id == owner.client_id:
                owner.channel_types.append(kind or row.provider)
    # Resolve only the requested agents' own tools and explicit shared grants.
    from sqlalchemy import or_
    shared_ids = {uuid.UUID(str(item)) for agent in agents for item in agent.shared_tool_ids}
    rows = db.execute(select(AgentTool, Agent.client_id).join(Agent, Agent.id == AgentTool.agent_id).where(
        Agent.agency_id == user.agency_id, Agent.deleted_at.is_(None), AgentTool.enabled.is_(True),
        or_(AgentTool.agent_id.in_(by_id), AgentTool.id.in_(shared_ids)))).all()
    for tool, client_id in rows:
        for agent in agents:
            if client_id == agent.client_id and (tool.agent_id == agent.id or str(tool.id) in agent.shared_tool_ids):
                agent.custom_tool_names.append(tool.name)
    return agents


@router.get("", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agents = db.scalars(
        select(Agent)
        .options(joinedload(Agent.client).selectinload(Client.agents))
        .where(Agent.agency_id == user.agency_id, Agent.deleted_at.is_(None))
        .order_by(Agent.created_at.desc())
    ).unique().all()
    return _enrich_agents(db, user, list(agents))


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _validate_client(db, user, payload.client_id)
    await _validate_ollama(db, user, payload.provider, payload.model)
    from ..services.agent_builder import prepare
    values = payload.model_dump(exclude={"apply_builder", "apply_template"}, exclude_unset=payload.apply_template)
    if "objective_config" not in payload.model_fields_set:
        values.pop("objective_config", None)
    if payload.apply_template:
        values.setdefault("prompt_language", payload.prompt_language)
    # Legacy forms keep their defaults; guided selections explicitly apply grants.
    if not payload.apply_builder and not payload.apply_template and "selected_tools" not in payload.model_fields_set:
        values.pop("selected_tools", None)
    values = await prepare(db, user.agency_id, values, guided=payload.apply_builder, apply_template=payload.apply_template)
    agent = Agent(agency_id=user.agency_id, **values)
    db.add(agent)
    db.flush()
    from ..services.objectives import sync_rules
    sync_rules(db, agent)
    db.commit()
    return _agent(db, user, agent.id)


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _agent(db, user, agent_id)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: uuid.UUID, payload: AgentUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    values = payload.model_dump(exclude_unset=True, exclude={"apply_builder", "apply_template"})
    if "provider" in values or "model" in values:
        await _validate_ollama(db, user, values.get("provider", agent.provider), values.get("model", agent.model))
    client_id = values.get("client_id", agent.client_id)
    if client_id != agent.client_id and _channels_of(db, agent):
        raise HTTPException(
            status_code=409,
            detail="This agent answers a channel of its client. Assign another agent to it before changing the client.",
        )
    _validate_client(db, user, client_id)
    try:
        check_reply_delay(
            values.get("reply_delay_min_seconds", agent.reply_delay_min_seconds),
            values.get("reply_delay_max_seconds", agent.reply_delay_max_seconds),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from ..services.agent_builder import prepare
    values = await prepare(db, user.agency_id, values, agent, guided=payload.apply_builder, apply_template=payload.apply_template)
    for key, value in values.items():
        setattr(agent, key, value)
    from ..services.objectives import sync_rules
    sync_rules(db, agent)
    db.commit()
    return _agent(db, user, agent_id)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Delete the agent's configuration and knowledge; keep its conversations.

    The conversations it handled are the client's history and stay in the
    portal under the agent's name, so the row remains as a tombstone
    (``deleted_at``) and everything it owned is purged.
    """
    agent = _agent(db, user, agent_id)
    if _channels_of(db, agent):
        raise HTTPException(
            status_code=409,
            detail="This agent answers a channel of its client. Assign another agent to it before deleting this one.",
        )
    for model in (AgentTool, AgentQA, KnowledgeChunk, KnowledgeDocument, EscalationRule):
        db.execute(delete(model).where(model.agent_id == agent.id))
    for field in ("instructions", "personality", "brief_summary", "brief_products", "brief_audience", "brief_policies", "brief_dos", "brief_donts"):
        setattr(agent, field, "")
    agent.selected_channels = []
    agent.selected_tools = []
    agent.shared_tool_ids = []
    agent.tone = ""
    agent.welcome_message = ""
    agent.knowledge_enabled = False
    agent.objectives = []
    agent.template_id = None
    agent.template_version = None
    agent.template_snapshot = None
    agent.escalation_team_id = None
    agent.escalation_assignee_id = None
    agent.is_active = False
    agent.deleted_at = now_utc()
    from ..services.objectives import sync_rules
    sync_rules(db, agent)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{agent_id}/prompt", response_model=AgentPromptOut)
def get_prompt(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """What the model receives on every message, minus the knowledge retrieved per message."""
    agent = _agent(db, user, agent_id)
    return AgentPromptOut(prompt=build_system_prompt(agent, ""))


def _document_out(doc: KnowledgeDocument) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "error_message": doc.error_message,
        "created_at": doc.created_at,
        "character_count": len(doc.extracted_text or ""),
    }


@router.get("/{agent_id}/documents", response_model=list[DocumentOut])
def list_documents(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    docs = db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.agent_id == agent.id)
        .order_by(KnowledgeDocument.created_at.desc())
    ).all()
    return [_document_out(doc) for doc in docs]


@router.post("/{agent_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    agent_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = _agent(db, user, agent_id)
    original_name = file.filename or "document.pdf"
    if file.content_type != "application/pdf" and not original_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="The PDF exceeds the 20 MB limit")

    safe_name = re.sub(r"[^\w. -]", "_", Path(original_name).name)[:220] or "document.pdf"
    document = KnowledgeDocument(agent_id=agent.id, filename=safe_name, file_data=data, status="processed")
    try:
        reader = PdfReader(BytesIO(data))
        document.extracted_text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
        if not document.extracted_text:
            document.status = "error"
            document.error_message = "No extractable text was found in the PDF. It may be a scanned document."
    except Exception:
        document.status = "error"
        document.error_message = "The PDF could not be processed. Check that the file is not damaged or protected."
    db.add(document)
    db.commit()
    db.refresh(document)
    if document.status == "processed":
        # Best-effort: index embeddings for semantic search. Never fail the
        # upload if the provider has no embeddings support.
        try:
            await embed_document_chunks(db, agent, document)
        except Exception:
            db.rollback()
    return _document_out(document)


@router.delete("/{agent_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(agent_id: uuid.UUID, document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    document = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.agent_id == agent.id,
        )
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(document)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{agent_id}/qa", response_model=list[QAPairOut])
def list_qa(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    return db.scalars(select(AgentQA).where(AgentQA.agent_id == agent.id).order_by(AgentQA.position, AgentQA.created_at)).all()


@router.post("/{agent_id}/qa", response_model=QAPairOut, status_code=status.HTTP_201_CREATED)
def create_qa(agent_id: uuid.UUID, payload: QAPairCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    position = db.scalar(select(func.count(AgentQA.id)).where(AgentQA.agent_id == agent.id)) or 0
    pair = AgentQA(agent_id=agent.id, question=payload.question.strip(), answer=payload.answer.strip(), position=position)
    db.add(pair)
    db.commit()
    db.refresh(pair)
    return pair


@router.delete("/{agent_id}/qa/{qa_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_qa(agent_id: uuid.UUID, qa_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    pair = db.scalar(select(AgentQA).where(AgentQA.id == qa_id, AgentQA.agent_id == agent.id))
    if not pair:
        raise HTTPException(status_code=404, detail="Q&A pair not found")
    db.delete(pair)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

def _rule_out(rule: EscalationRule) -> dict:
    return {
        "id": rule.id,
        "position": rule.position,
        "condition": rule.condition,
        "team_id": rule.team_id,
        "team_name": rule.team.name if rule.team else None,
        "assignee_id": rule.assignee_id,
        "assignee_name": (rule.assignee.name.strip() or rule.assignee.email) if rule.assignee else None,
        "is_active": rule.is_active,
        "broken": rule.team_id is None and rule.assignee_id is None,
    }


def _escalation_out(db: Session, agent: Agent) -> dict:
    rules = db.scalars(
        select(EscalationRule).where(EscalationRule.agent_id == agent.id).order_by(EscalationRule.position)
    ).all()
    default_team = db.get(Team, agent.escalation_team_id) if agent.escalation_team_id else None
    default_person = db.get(PortalUser, agent.escalation_assignee_id) if agent.escalation_assignee_id else None
    return {
        "default_team_id": agent.escalation_team_id,
        "default_team_name": default_team.name if default_team else None,
        "default_assignee_id": agent.escalation_assignee_id,
        "default_assignee_name": (default_person.name.strip() or default_person.email) if default_person else None,
        "builtin_enabled": agent.escalation_builtin_enabled,
        "rules": [_rule_out(rule) for rule in rules],
    }


@router.get("/{agent_id}/escalation-rules", response_model=EscalationConfigOut)
def get_escalation_config(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _escalation_out(db, _agent(db, user, agent_id))


@router.put("/{agent_id}/escalation-rules", response_model=EscalationConfigOut)
def replace_escalation_config(
    agent_id: uuid.UUID,
    config: EscalationConfigIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The whole ordered list at once: the editor works on the list, so the
    server converges to it. Every destination must be a team or person of the
    agent's client, and exactly one of the two."""
    agent = _agent(db, user, agent_id)
    payload = config.rules
    team_ids = {row for row in db.scalars(select(Team.id).where(Team.client_id == agent.client_id))}
    person_ids = {row for row in db.scalars(select(PortalUser.id).where(PortalUser.client_id == agent.client_id))}
    if config.default_team_id and config.default_assignee_id:
        raise HTTPException(status_code=422, detail="The general destination is a team or a person, not both")
    if config.default_team_id and config.default_team_id not in team_ids:
        raise HTTPException(status_code=422, detail="The destination team does not belong to this client")
    if config.default_assignee_id and config.default_assignee_id not in person_ids:
        raise HTTPException(status_code=422, detail="The destination person does not belong to this client")
    agent.escalation_team_id = config.default_team_id
    agent.escalation_assignee_id = config.default_assignee_id
    agent.escalation_builtin_enabled = config.builtin_enabled
    for rule in payload:
        if (rule.team_id is None) == (rule.assignee_id is None):
            raise HTTPException(status_code=422, detail="Each rule needs exactly one destination: a team or a person")
        if rule.team_id and rule.team_id not in team_ids:
            raise HTTPException(status_code=422, detail="The destination team does not belong to this client")
        if rule.assignee_id and rule.assignee_id not in person_ids:
            raise HTTPException(status_code=422, detail="The destination person does not belong to this client")
    for existing in db.scalars(select(EscalationRule).where(EscalationRule.agent_id == agent.id)):
        db.delete(existing)
    for position, rule in enumerate(payload):
        db.add(
            EscalationRule(
                agent_id=agent.id,
                position=position,
                condition=rule.condition.strip(),
                team_id=rule.team_id,
                assignee_id=rule.assignee_id,
                is_active=rule.is_active,
            )
        )
    db.commit()
    return _escalation_out(db, agent)
