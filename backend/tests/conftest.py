"""Fixtures comuns. Usa PostgreSQL real (serviço do CI ou docker compose) — nunca SQLite."""

import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

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

from app.core import clock  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.mailer import Mail, get_mailer  # noqa: E402

ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")


def alembic_config() -> Config:
    return Config(ALEMBIC_INI)


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    command.upgrade(alembic_config(), "head")


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    limiter.reset()
    yield
    limiter.reset()
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE users, matches, audit_log RESTART IDENTITY CASCADE"))


@pytest.fixture
def db() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session


class MemoryMailer:
    """Dublê de teste: guarda as mensagens em vez de enviar."""

    def __init__(self) -> None:
        self.sent: list[Mail] = []

    def send(self, mail: Mail) -> None:
        self.sent.append(mail)

    def last_token(self, to: str) -> str:
        for mail in reversed(self.sent):
            if mail.to == to and (m := re.search(r"token=([A-Za-z0-9_-]+)", mail.body)):
                return m.group(1)
        raise AssertionError(f"nenhum token enviado para {to}")


@pytest.fixture
def mailer() -> MemoryMailer:
    return MemoryMailer()


@pytest.fixture
def client(mailer: MemoryMailer) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_mailer] = lambda: mailer
    with TestClient(app, base_url="https://testserver") as c:
        yield c


class FakeClock:
    def __init__(self) -> None:
        self.offset = timedelta()

    def advance(self, **kwargs: float) -> None:
        self.offset += timedelta(**kwargs)

    def now(self) -> datetime:
        return datetime.now(UTC) + self.offset


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fc = FakeClock()
    monkeypatch.setattr(clock, "now", fc.now)
    return fc
