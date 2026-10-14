"""Utilitários de teste com dados sintéticos (nunca dados reais)."""

from typing import Any

from fastapi.testclient import TestClient

API = "/api/v1"

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


def novo_cliente(app: TestClient) -> TestClient:
    """Novo cliente HTTP (cookies próprios) sobre a mesma aplicação."""
    return TestClient(app.app, base_url="https://testserver")


def conta_logada(client: TestClient, mailer: Any, n: int = 1, **kw: object) -> TestClient:
    """Cadastra, confirma o e-mail e autentica `client`."""
    assert register(client, n, **kw).status_code == 201
    token = mailer.last_token(f"jogador{n}@example.test")
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 204
    assert login(client, n).status_code == 200
    return client
