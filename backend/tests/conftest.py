"""Fixtures comuns. Usa PostgreSQL real (serviço do CI ou docker compose)."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "chave-de-teste-somente-para-ci-0123456789abcdef")
os.environ.setdefault("POSTGRES_DB", "boardhub_test")
os.environ.setdefault("POSTGRES_USER", "boardhub_test")
os.environ.setdefault("POSTGRES_PASSWORD", "senha-de-teste")

from app.main import create_app  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c
