import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import ModelCatalogOut
from ..services import model_catalog
from ..services.model_catalog import get_model, list_models


router = APIRouter(prefix="/catalog", tags=["Model catalog"])


@router.get("/available")
def available_models(user: User = Depends(get_current_user)):
    """Model ids this workspace can pick, per provider and capability. A
    module call on purpose, so a deployment can narrow the answer."""
    return model_catalog.available_models()


@router.get("/models", response_model=list[ModelCatalogOut])
def list_catalog_models(user: User = Depends(get_current_user)):
    return [asdict(model) for model in list_models()]


@router.get("/models/{model_id:path}", response_model=ModelCatalogOut)
def get_catalog_model(model_id: str, user: User = Depends(get_current_user)):
    model = get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found in the catalog")
    return asdict(model)


@router.get("/agent-configuration")
def agent_configuration(language: str = "en", user: User = Depends(get_current_user)):
    """Static metadata only: no credentials, tenant rows or provisioning effects."""
    if language not in {"en", "es"}:
        raise HTTPException(422, "Unsupported language")
    from ..services.agent_catalog.objective_config import SCHEMAS, defaults, category
    from ..services.agent_catalog.objectives import OBJECTIVES
    from ..services.agent_catalog.templates import TEMPLATES
    from ..services.agent_catalog.capabilities import TOOLS
    from ..services.model_providers import supported_providers
    return {
        "version": 1,
        "objectives": [{**asdict(item), "category": category(item.id), "default_config": defaults(item.id, language),
                        "configuration_schema": SCHEMAS[item.id].model_json_schema(),
                        "available": item.id not in {"order_lookup", "inventory_lookup"}} for item in OBJECTIVES],
        "templates": [asdict(item) for item in TEMPLATES],
        "tools": [asdict(item) for item in TOOLS],
        "providers": list(supported_providers()),
        "channels": ["whatsapp", "whatsapp_cloud", "instagram", "messenger", "widget"],
        "applies_configuration": False,
    }


@router.get("/agent-configuration/{client_id}")
def agent_business_configuration(client_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.agent_builder import context
    return context(db, user.agency_id, client_id)


from pydantic import BaseModel, Field
from ..schemas import AgentObjectives


class TemplateMatchRequest(BaseModel):
    objectives: AgentObjectives = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list, max_length=4)


@router.post("/agent-templates/{client_id}/recommendations")
def agent_template_recommendations(client_id: uuid.UUID, payload: TemplateMatchRequest,
                                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.agent_builder import template_matches, CHANNELS
    if not set(payload.channels) <= CHANNELS:
        raise HTTPException(422, "builder.invalid_selection")
    return template_matches(db, user.agency_id, client_id, payload.objectives, payload.channels)


@router.get("/agent-templates/{client_id}/{template_id}/preview")
def agent_template_preview(client_id: uuid.UUID, template_id: str, language: str = "en",
                           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.agent_builder import template_preview
    if language not in {"en", "es"}:
        raise HTTPException(422, "Unsupported language")
    return template_preview(db, user.agency_id, client_id, template_id, language)


class ObjectivePreviewRequest(BaseModel):
    objectives: AgentObjectives = Field(default_factory=list)
    objective_config: dict[str, dict] = Field(default_factory=dict)
    language: str = "en"


@router.post("/objective-configuration/{client_id}")
def objective_configuration(client_id: uuid.UUID, payload: ObjectivePreviewRequest,
                            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.objectives import prepare_objectives
    if payload.language not in {"en", "es"}:
        raise HTTPException(422, "Unsupported language")
    values = prepare_objectives(db, user.agency_id, {"client_id": client_id, "objectives": payload.objectives,
        "objective_config": payload.objective_config, "prompt_language": payload.language})
    return {key: values[key] for key in ("objective_config", "selected_tools", "appointments_enabled", "knowledge_enabled", "escalation_builtin_enabled")}
