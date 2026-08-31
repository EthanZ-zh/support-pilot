import os
from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = os.getenv(
    "SUPPORT_PILOT_TEST_DATABASE_URL",
    "postgresql+psycopg://support_pilot:support_pilot@localhost:54330/support_pilot_test",
)
if TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1] != "support_pilot_test":
    raise RuntimeError("integration tests require a database named support_pilot_test")
os.environ["SUPPORT_PILOT_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SUPPORT_PILOT_AGENT_PROVIDER"] = "deterministic"
os.environ["SUPPORT_PILOT_ALLOW_LEGACY_USER_HEADER"] = "true"
os.environ["SUPPORT_PILOT_JWT_SECRET"] = "unit-test-jwt-secret-with-at-least-32-characters"

from support_pilot.infrastructure.database import get_db  # noqa: E402
from support_pilot.infrastructure.seed import seed_synthetic_data  # noqa: E402
from support_pilot.main import app  # noqa: E402

PROJECT_TABLES = (
    "human_feedback",
    "ticket_transitions",
    "agent_runs",
    "agent_conversations",
    "knowledge_chunk_embeddings",
    "knowledge_chunks",
    "knowledge_documents",
    "audit_events",
    "idempotency_records",
    "tickets",
    "support_requests",
    "incident_components",
    "incidents",
    "service_components",
    "quota_snapshots",
    "entitlements",
    "users",
    "tenants",
    "plans",
)


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with engine.begin() as connection:
        table_list = ", ".join(f'"{table}"' for table in PROJECT_TABLES)
        connection.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))
    with factory() as session:
        seed_synthetic_data(session)
    return factory


@pytest.fixture()
def db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    with session_factory() as session:
        yield session


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
