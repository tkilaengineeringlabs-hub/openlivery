"""Supported AI provider connections, one per provider per agency."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Agent, ProviderCredential
from ..security import decrypt_secret


PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1"},
    "anthropic": {"label": "Anthropic", "base_url": "https://api.anthropic.com/v1"},
    "ollama": {"label": "Ollama", "base_url": ""},
    "groq": {"label": "Groq", "base_url": "https://api.groq.com/openai/v1"},
}
SUPPORTED = tuple(PROVIDERS)


def base_url_for(provider: str) -> str:
    if provider == "ollama":
        from .ollama import default_base_url
        return default_base_url()
    return PROVIDERS[provider]["base_url"]


def resolve_provider_credentials(db: Session, agency_id, provider: str) -> tuple[str, str] | None:
    """(base_url, api_key) for an agency's connection, or None if unknown or unset."""
    if provider not in PROVIDERS:
        return None
    credential = db.scalar(
        select(ProviderCredential).where(
            ProviderCredential.agency_id == agency_id,
            ProviderCredential.provider == provider,
        )
    )
    if not credential:
        if provider == "groq":
            from ..config import get_settings
            key = get_settings().groq_api_key
            return (base_url_for(provider), key) if key else None
        return None
    url = (credential.base_url or base_url_for(provider)) if provider == "ollama" else base_url_for(provider)
    return url, decrypt_secret(credential.encrypted_api_key) if credential.encrypted_api_key else ""


def resolve_agent_credentials(db: Session, agent: Agent) -> tuple[str, str] | None:
    """(base_url, api_key) for the agent's provider using the agency's connection."""
    return resolve_provider_credentials(db, agent.agency_id, agent.provider)
