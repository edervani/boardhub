"""Fixtures comuns. Usa PostgreSQL real (serviço do CI ou docker compose) — nunca SQLite."""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "chave-de-teste-somente-para-ci-0123456789abcdef")
os.environ.setdefault("POSTGRES_DB", "boardhub_test")
os.environ.setdefault("POSTGRES_USER", "boardhub_test")
os.environ.setdefault("POSTGRES_PASSWORD", "senha-de-teste")

from app.db.session import get_engine  # noqa: E402
from app.main import create_app  # noqa: E402

ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")


def alembic_config() -> Config:
    return Config(ALEMBIC_INI)


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    command.upgrade(alembic_config(), "head")


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    yield
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE users, audit_log RESTART IDENTITY CASCADE"))


@pytest.fixture
def db() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c
