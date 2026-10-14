"""Critérios de aceite CA-001 a CA-005 (RF-001 a RF-005) e controles SEC-02, SEC-05, SEC-07."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthToken, User, UserProfile
from tests.conftest import FakeClock, MemoryMailer
from tests.helpers import PASSWORD, csrf, login, register

EMAIL = "jogador1@example.test"


def _sem_request_id(body: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in body.items() if k != "request_id"}


# ---------- CA-001 ----------

def test_cadastro_cria_conta_com_argon2id(client: TestClient, db: Session) -> None:
    resp = register(client)
    assert resp.status_code == 201
    user = db.scalar(select(User).where(User.email == EMAIL))
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert db.get(UserProfile, user.id) is not None


def test_email_existente_recebe_resposta_identica(client: TestClient, mailer: MemoryMailer) -> None:
    primeira = register(client)
    segunda = register(client, display_name="outro_nome")
    assert segunda.status_code == primeira.status_code == 201
    assert segunda.json() == primeira.json()
    assert "Tentativa de cadastro" in mailer.sent[-1].subject


def test_email_normalizado_impede_duplicata_por_maiusculas(client: TestClient, db: Session) -> None:
    register(client)
    register(client, email="JOGADOR1@Example.TEST", display_name="outro_nome")
    assert len(db.scalars(select(User)).all()) == 1


@pytest.mark.parametrize("senha", ["curta-11car", "123456789012", "a" * 129])
def test_senha_fraca_e_recusada(client: TestClient, senha: str) -> None:
    assert register(client, password=senha).status_code == 422


def test_nome_de_exibicao_repetido_retorna_409(client: TestClient) -> None:
    register(client)
    resp = register(client, 2, display_name="JOGADOR_TESTE_01")
    assert resp.status_code == 409


def test_sexto_cadastro_por_ip_em_uma_hora_e_limitado(client: TestClient) -> None:
    for n in range(1, 6):
        assert register(client, n).status_code == 201
    resp = register(client, 6)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_termos_desatualizados_sao_recusados(client: TestClient) -> None:
    assert register(client, accept_terms_version="2020-01-01").status_code == 422


def test_logs_nao_contem_senha_nem_email(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """RNF-013 / SEC-12."""
    with caplog.at_level(logging.DEBUG, logger="boardhub"):
        register(client)
        login(client)
        login(client, password="senha-errada-123")
    texto = caplog.text + " ".join(str(vars(r)) for r in caplog.records)
    assert PASSWORD not in texto
    assert EMAIL not in texto


def test_corpo_de_erro_de_validacao_nao_ecoa_a_senha(client: TestClient) -> None:
    resp = register(client, password="x")
    assert "x" not in [e.get("input") for e in resp.json().get("errors", [])]
    assert "input" not in str(resp.json())


# ---------- Menores (RF-034 no cadastro) ----------

def test_menor_de_12_exige_email_do_responsavel(client: TestClient) -> None:
    assert register(client, age_band="under_12").status_code == 422


def test_menor_de_12_dispara_convite_ao_responsavel(
    client: TestClient, mailer: MemoryMailer
) -> None:
    resp = register(client, age_band="under_12", guardian_email="responsavel@example.test")
    assert resp.status_code == 201
    assert any(m.to == "responsavel@example.test" for m in mailer.sent)


def test_conta_de_menor_nasce_protegida(client: TestClient, db: Session) -> None:
    register(client, age_band="12_15")
    user = db.scalar(select(User).where(User.email == EMAIL))
    assert user is not None
    assert user.profile.is_public is False
    assert user.profile.show_in_ranking is False
    assert user.preferences.allow_open_matchmaking is False


# ---------- CA-002 ----------

def test_verificacao_de_email_e_uso_unico(client: TestClient, mailer: MemoryMailer,
                                         db: Session) -> None:
    register(client)
    token = mailer.last_token(EMAIL)
    assert db.scalar(select(AuthToken).where(AuthToken.token_hash == token.encode())) is None
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 204
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
    login(client)
    assert client.get("/api/v1/me").json()["email_verified"] is True


def test_token_de_verificacao_expira(client: TestClient, mailer: MemoryMailer,
                                     fake_clock: FakeClock) -> None:
    register(client)
    token = mailer.last_token(EMAIL)
    fake_clock.advance(hours=25)
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400


# ---------- CA-003 ----------

def test_login_define_cookies_seguros(client: TestClient) -> None:
    register(client)
    resp = login(client)
    assert resp.status_code == 200
    cookies = resp.headers.get_list("set-cookie")
    sessao = next(c for c in cookies if c.startswith("bh_session="))
    assert "HttpOnly" in sessao and "Secure" in sessao and "samesite=lax" in sessao.lower()
    assert resp.json()["display_name"] == "jogador_teste_01"


def test_erro_de_login_nao_revela_se_email_existe(client: TestClient) -> None:
    register(client)
    errada = login(client, password="senha-errada-123")
    inexistente = login(client, n=99)
    assert errada.status_code == inexistente.status_code == 401
    assert _sem_request_id(errada.json()) == _sem_request_id(inexistente.json())


def test_sexta_falha_de_login_em_15_minutos_e_limitada(client: TestClient) -> None:
    register(client)
    for _ in range(5):
        assert login(client, password="senha-errada-123").status_code == 401
    assert login(client, password="senha-errada-123").status_code == 429
    assert login(client).status_code == 429  # bloqueia até a senha certa, por conta+IP


# ---------- CA-004 ----------

def test_logout_invalida_sessao_no_servidor(client: TestClient) -> None:
    register(client)
    login(client)
    token = client.cookies.get("bh_session")
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204
    client.cookies.set("bh_session", token or "", domain="testserver")
    assert client.get("/api/v1/me").status_code == 401


def test_requisicao_sem_token_csrf_e_recusada(client: TestClient) -> None:
    register(client)
    login(client)
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 403
    assert resp.json()["type"] == "csrf_failed"


def test_sessao_expira_por_tempo_absoluto(client: TestClient, fake_clock: FakeClock) -> None:
    register(client)
    login(client)
    fake_clock.advance(days=91)
    assert client.get("/api/v1/me").status_code == 401


def test_sessao_expira_por_inatividade(client: TestClient, fake_clock: FakeClock) -> None:
    register(client)
    login(client)
    fake_clock.advance(days=31)
    assert client.get("/api/v1/me").status_code == 401


def test_revogar_outra_sessao_propria(client: TestClient, mailer: MemoryMailer) -> None:
    register(client)
    login(client)
    outro = TestClient(client.app, base_url="https://testserver")
    login(outro)
    sessoes = client.get("/api/v1/auth/sessions").json()
    assert len(sessoes) == 2
    alvo = next(s for s in sessoes if not s["current"])
    resp = client.delete(f"/api/v1/auth/sessions/{alvo['id']}", headers=csrf(client))
    assert resp.status_code == 204
    assert outro.get("/api/v1/me").status_code == 401


def test_nao_revoga_sessao_de_outro_usuario(client: TestClient) -> None:
    """SEC-05 / IDOR."""
    register(client)
    register(client, 2)
    vitima = TestClient(client.app, base_url="https://testserver")
    login(vitima, 2)
    alvo = vitima.get("/api/v1/auth/sessions").json()[0]["id"]
    login(client)
    resp = client.delete(f"/api/v1/auth/sessions/{alvo}", headers=csrf(client))
    assert resp.status_code == 404
    assert vitima.get("/api/v1/me").status_code == 200


# ---------- CA-005 ----------

def test_pedido_de_redefinicao_nao_revela_cadastro(client: TestClient) -> None:
    register(client)
    a = client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    b = client.post("/api/v1/auth/password/forgot", json={"email": "ninguem@example.test"})
    assert a.status_code == b.status_code == 202
    assert a.json() == b.json()


def test_redefinicao_troca_senha_e_encerra_sessoes(client: TestClient, mailer: MemoryMailer,
                                                   db: Session) -> None:
    register(client)
    login(client)
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    token = mailer.last_token(EMAIL)
    nova = "rainha-peao-roque-77"
    body = {"token": token, "new_password": nova}
    anonimo = TestClient(client.app, base_url="https://testserver")
    assert anonimo.post("/api/v1/auth/password/reset", json=body).status_code == 204
    assert anonimo.post("/api/v1/auth/password/reset", json=body).status_code == 400
    assert client.get("/api/v1/me").status_code == 401
    assert login(anonimo).status_code == 401
    assert login(anonimo, password=nova).status_code == 200
    assert "alterada" in mailer.sent[-1].subject


def test_token_de_redefinicao_expira_em_30_minutos(client: TestClient, mailer: MemoryMailer,
                                                   fake_clock: FakeClock) -> None:
    register(client)
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    token = mailer.last_token(EMAIL)
    fake_clock.advance(minutes=31)
    resp = client.post("/api/v1/auth/password/reset",
                       json={"token": token, "new_password": "rainha-peao-roque-77"})
    assert resp.status_code == 400


def test_cabecalhos_de_seguranca_presentes(client: TestClient) -> None:
    resp = client.get("/api/v1/health/live")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert len(resp.headers["X-Request-ID"]) == 32
