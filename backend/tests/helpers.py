"""Utilitários de teste com dados sintéticos (nunca dados reais)."""

from typing import Any

from fastapi.testclient import TestClient

TERMS = "2026-10-13"
PASSWORD = "cavalo-bispo-torre-42"


def register(client: TestClient, n: int = 1, **overrides: Any) -> Any:
    body = {
        "email": f"jogador{n}@example.test",
        "password": PASSWORD,
        "display_name": f"jogador_teste_{n:02d}",
        "age_band": "18_plus",
        "accept_terms_version": TERMS,
    }
    body.update(overrides)
    return client.post("/api/v1/auth/register", json=body)


def login(client: TestClient, n: int = 1, password: str = PASSWORD) -> Any:
    return client.post(
        "/api/v1/auth/login", json={"email": f"jogador{n}@example.test", "password": password}
    )


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("bh_csrf") or ""}
