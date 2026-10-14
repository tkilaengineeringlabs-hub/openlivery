import os
import tempfile

from database_safety import is_disposable_test_target

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Validate before importing the app or connecting: fixtures reset every table.
_test_url = os.environ.get("TEST_DATABASE_URL", "")
_safe = is_disposable_test_target(_test_url, os.environ.get("TKILA_TEST_ALLOW_RESET"))
if not _safe:
    raise pytest.UsageError(
        "Refusing table resets: use make verify-api, or explicitly set "
        "TEST_DATABASE_URL to a disposable local PostgreSQL database ending in "
        "_test and TKILA_TEST_ALLOW_RESET=1. URL query overrides are forbidden."
    )

# Tests must never inherit private dotenv files, credentials or storage paths.
from app.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None
for _field in Settings.model_fields:
    for _key in list(os.environ):
        if _key.lower() == _field.lower():
            del os.environ[_key]
_test_storage = tempfile.TemporaryDirectory(prefix="tkila-test-storage-")
os.environ.update(
    DATABASE_URL=_test_url,
    STORAGE_DIR=_test_storage.name,
    RATE_LIMIT_ENABLED="false",
    SOCIAL_WORKER_ENABLED="false",
    AUTOMATION_WORKER_ENABLED="false",
    CALENDAR_WORKER_ENABLED="false",
    AUTO_RESOLVE_AFTER_HOURS="0",
)

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import whatsapp_inbound  # noqa: E402


test_engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def immediate_replies(monkeypatch):
    """Answer inbound WhatsApp messages synchronously, whatever the agent's delay.

    The reply delay is a per-agent setting with a non-zero default, and most
    tests want the reply back in the inbound response. Tests of the delayed
    path patch a short delay of their own on top of this.
    """
    monkeypatch.setattr(whatsapp_inbound, "reply_delay_seconds", lambda agent: 0.0)


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield
    Base.metadata.drop_all(test_engine)


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client: TestClient):
    response = client.post(
        "/api/auth/register",
        json={
            "agency_name": "Agencia Prisma",
            "name": "Ana Admin",
            "email": "ana@prisma.com",
            "password": "contrasena-segura",
        },
    )
    assert response.status_code == 201
    return client


def customer_conversation(client: TestClient, agent_id: str) -> dict:
    """A conversation as a customer would open it (widget channel), so it shows
    in the client portal. Playground conversations are rehearsals and never do."""
    from app.models import Conversation

    created = client.post("/api/conversations", json={"agent_id": agent_id}).json()
    with TestingSession() as db:
        conversation = db.get(Conversation, created["id"])
        conversation.channel = "widget"
        db.commit()
    created["channel"] = "widget"
    return created
