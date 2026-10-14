from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import ProviderCredential, User
from ..schemas import ProviderKeyUpdate, ProviderOut, ProviderModelTest
from ..security import decrypt_secret, encrypt_secret, mask_secret
from ..services.ai import test_provider
from ..services.groq import GroqProvider
from ..config import get_settings
from ..services.providers import PROVIDERS, SUPPORTED, base_url_for, resolve_provider_credentials
from ..services.ollama import OllamaProvider, checked_url, normalize_url


router = APIRouter(prefix="/providers", tags=["AI providers"])


def _require_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Unknown provider")


def _credential(db: Session, user: User, provider: str) -> ProviderCredential | None:
    return db.scalar(
        select(ProviderCredential).where(
            ProviderCredential.agency_id == user.agency_id,
            ProviderCredential.provider == provider,
        )
    )


def _out(provider: str, credential: ProviderCredential | None) -> dict:
    url = None
    if provider == "ollama":
        try:
            url = normalize_url((credential.base_url if credential else None) or base_url_for(provider))
        except HTTPException:
            # Invalid installation defaults must not break the cloud provider UI
            # or expose URL userinfo. Validation reports the error on actual use.
            pass
    return {
        "provider": provider,
        "label": PROVIDERS[provider]["label"],
        "configured": credential is not None or (provider == "groq" and bool(get_settings().groq_api_key)),
        "api_key_masked": "" if provider == "groq" else mask_secret(decrypt_secret(credential.encrypted_api_key)) if credential and credential.encrypted_api_key else "",
        "name": credential.name if credential else None,
        "base_url": url,
        "default_model": credential.default_model if credential else None,
    }


@router.get("", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    by_provider = {c.provider: c for c in db.scalars(
        select(ProviderCredential).where(ProviderCredential.agency_id == user.agency_id)
    ).all()}
    return [_out(provider, by_provider.get(provider)) for provider in SUPPORTED]


@router.put("/{provider}", response_model=ProviderOut)
async def set_provider_key(provider: str, payload: ProviderKeyUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_provider(provider)
    credential = _credential(db, user, provider)
    if provider == "groq" and payload.api_key is not None and not payload.api_key.strip():
        raise HTTPException(422, "An API key is required")
    if provider != "ollama" and not payload.api_key and not (provider == "groq" and resolve_provider_credentials(db, user.agency_id, provider)):
        raise HTTPException(422, "An API key is required")
    url = None
    if provider == "ollama":
        url = await checked_url(payload.base_url or base_url_for(provider))
        if (credential and _key(credential) and payload.api_key is None
                and url != normalize_url(credential.base_url or base_url_for(provider))):
            raise HTTPException(422, "ollama.auth_required")
        if payload.default_model:
            key = payload.api_key if payload.api_key is not None else _key(credential)
            if payload.default_model not in await OllamaProvider().list_models(url, key):
                raise HTTPException(422, "ollama.model_missing")
    if provider == "groq" and payload.default_model:
        key = payload.api_key or _resolved(db, user, provider)[1]
        if payload.default_model not in await GroqProvider().list_models(base_url_for(provider), key):
            raise HTTPException(422, "groq.model_missing")
    if provider == "groq" and not credential and payload.api_key is None:
        payload.api_key = _resolved(db, user, provider)[1]
    if not credential:
        credential = ProviderCredential(agency_id=user.agency_id, provider=provider, encrypted_api_key="")
        db.add(credential)
    if payload.api_key is not None:
        credential.encrypted_api_key = encrypt_secret(payload.api_key) if payload.api_key else ""
    if provider in ("ollama", "groq"):
        credential.name = payload.name
        credential.base_url = url
        credential.default_model = payload.default_model or None
    db.commit()
    return _out(provider, credential)


def _key(credential: ProviderCredential | None) -> str:
    return decrypt_secret(credential.encrypted_api_key) if credential and credential.encrypted_api_key else ""


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider_key(provider: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_provider(provider)
    credential = _credential(db, user, provider)
    if credential:
        db.delete(credential)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{provider}/test")
async def test_provider_key(provider: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_provider(provider)
    credential = _credential(db, user, provider)
    if provider == "groq":
        return await GroqProvider().test_connection(*_resolved(db, user, provider))
    if not credential:
        raise HTTPException(status_code=400, detail="ollama.not_configured" if provider == "ollama" else "No API key configured for this provider")
    if provider == "ollama":
        return await OllamaProvider().test_connection(credential.base_url or base_url_for(provider), _key(credential))
    return await test_provider(provider, base_url_for(provider), _key(credential))


@router.post("/{provider}/validate")
async def validate_provider_key(provider: str, payload: ProviderKeyUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Verify a raw key against the provider before it is stored."""
    _require_provider(provider)
    if provider == "ollama":
        credential = _credential(db, user, provider)
        key = payload.api_key if payload.api_key is not None else _key(credential)
        url = await checked_url(payload.base_url or base_url_for(provider))
        # Never forward a saved proxy secret to a different draft endpoint.
        if credential and key and url != normalize_url(credential.base_url or base_url_for(provider)) and payload.api_key is None:
            raise HTTPException(422, "ollama.auth_required")
        return await OllamaProvider().test_connection(url, key)
    if provider == "groq":
        key = payload.api_key or _resolved(db, user, provider)[1]
        return await GroqProvider().test_connection(base_url_for(provider), key)
    if not payload.api_key:
        raise HTTPException(422, "An API key is required")
    return await test_provider(provider, base_url_for(provider), payload.api_key)


def _resolved(db: Session, user: User, provider: str) -> tuple[str, str]:
    _require_provider(provider)
    connection = resolve_provider_credentials(db, user.agency_id, provider)
    if not connection:
        raise HTTPException(422, f"{provider}.not_configured" if provider in ("ollama", "groq") else "Provider not configured")
    return connection


@router.get("/ollama/capabilities")
async def ollama_capabilities(model: str = Query(min_length=1, max_length=180), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    url, key = _resolved(db, user, "ollama")
    return asdict(await OllamaProvider().model_capabilities(url, key, model))


@router.post("/ollama/probe")
async def probe_ollama(payload: ProviderModelTest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    url, key = _resolved(db, user, "ollama")
    completion = await OllamaProvider().chat(url, key, payload.model, [{"role": "user", "content": "Responde únicamente: OK"}],
                                           temperature=0, max_tokens=256)
    return {"ok": completion.text.strip() == "OK", "response": completion.text,
            "message": "ollama.probe_ok" if completion.text.strip() == "OK" else "ollama.probe_unexpected"}


@router.get("/groq/models")
async def groq_models(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"models": await GroqProvider().list_models(*_resolved(db, user, "groq"))}


@router.get("/groq/capabilities")
async def groq_capabilities(model: str = Query(min_length=1, max_length=180), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return asdict(await GroqProvider().model_capabilities(*_resolved(db, user, "groq"), model))


@router.post("/groq/probe")
async def probe_groq(payload: ProviderModelTest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    connection = _resolved(db, user, "groq")
    provider = GroqProvider()
    if payload.model not in await provider.list_models(*connection):
        raise HTTPException(422, "groq.model_missing")
    completion = await provider.chat(*connection, payload.model, [{"role": "user", "content": "Responde únicamente con: OK"}], temperature=0, max_tokens=256)
    return {"ok": completion.text == "OK", "response": completion.text}
