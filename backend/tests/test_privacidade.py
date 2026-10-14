"""RF-029 e RF-030 (CA-029, CA-030): exportação e exclusão de conta, com o fluxo do responsável."""

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import jobs
from app.models import (
    AuditLog,
    AuthSession,
    DataExportRequest,
    ExerciseAttempt,
    Match,
    MatchPlayer,
    User,
    UserProfile,
)
from app.services import privacy_service
from tests.conftest import FakeClock, MemoryMailer
from tests.helpers import API, PASSWORD, conta_logada, csrf, login, novo_cliente, register
from tests.online_helpers import duas_contas, jogar_aleatorio, partida


def _me(c: TestClient) -> dict[str, Any]:
    resp = c.get(f"{API}/me")
    assert resp.status_code == 200
    return dict(resp.json())


def _uid(c: TestClient) -> uuid.UUID:
    return uuid.UUID(_me(c)["id"])


def _responder(c: TestClient, exercise_id: str, answer: str) -> None:
    resp = c.post(f"{API}/academy/exercises/{exercise_id}/attempts", headers=csrf(c),
                  json={"answer": answer})
    assert resp.status_code == 200, resp.text


def _pedir_exclusao(c: TestClient, senha: str = PASSWORD) -> Any:
    return c.post(f"{API}/me/delete", headers=csrf(c), json={"password": senha})


def _pedir_exportacao(c: TestClient) -> Any:
    return c.post(f"{API}/me/export", headers=csrf(c))


def _com_historico(client: TestClient, mailer: MemoryMailer
                   ) -> tuple[TestClient, TestClient, dict[str, Any]]:
    """A (titular) e B (oponente): partida online em andamento, partida contra a IA e Academy."""
    a, b = duas_contas(client, mailer)
    online = partida(a, b)
    jogar_aleatorio(a, b, online["id"], 3)
    ia = a.post(f"{API}/matches", headers=csrf(a),
                json={"game_id": "tictactoe", "mode": "ai", "ai_level": 2})
    assert ia.status_code == 201
    _responder(a, "tt-win-1", "2")
    return a, b, online


# ---------- RF-029 / CA-029: exportação ----------

def test_exportacao_traz_os_dados_do_titular_sem_segredos_nem_terceiros(
    client: TestClient, mailer: MemoryMailer, db: Session,
) -> None:
    a, b, online = _com_historico(client, mailer)
    b_id = _me(b)["id"]
    a2 = novo_cliente(client)
    assert login(a2, 1).status_code == 200  # 2ª sessão para aparecer no histórico de sessões

    resp = _pedir_exportacao(a)
    assert resp.status_code == 202
    export_id = resp.json()["id"]
    baixar = a.get(f"{API}/me/export/{export_id}")
    assert baixar.status_code == 200
    assert "attachment" in baixar.headers["content-disposition"]
    bruto = baixar.text
    dados = baixar.json()

    assert dados["account"]["email"] == "jogador1@example.test"
    assert dados["profile"]["display_name"] == "jogador_teste_01"
    assert dados["profile"]["preferences"]["locale"] == "pt-BR"
    assert len(dados["sessions"]) >= 2
    assert {m["mode"] for m in dados["matches"]} == {"online_casual", "ai"}
    on = next(m for m in dados["matches"] if m["mode"] == "online_casual")
    assert on["id"] == online["id"] and len(on["moves"]) == 3
    assert on["opponent"] == "human" and len(on["your_seats"]) == 1
    assert dados["academy"]["attempts"][0]["exercise_id"] == "tt-win-1"
    assert dados["academy"]["skill_progress"]
    assert any(e["action"] == "account_created" for e in dados["audit_events"])

    # Nada de segredos nem de terceiros.
    assert "$argon2" not in bruto and "password" not in bruto and "token" not in bruto
    assert "jogador2@example.test" not in bruto
    assert "jogador_teste_02" not in bruto
    assert b_id not in bruto
    sessao_hash = db.scalar(select(AuthSession.token_hash).where(
        AuthSession.user_id == _uid(a)))
    assert sessao_hash is not None and sessao_hash.hex() not in bruto
    # Auditoria e banco registram o pedido, sem conteúdo da exportação.
    evento = db.scalar(select(AuditLog).where(AuditLog.action == "data_export_requested"))
    assert evento is not None and "email" not in json.dumps(evento.details)


def test_exportacao_exige_login_e_csrf(client: TestClient, mailer: MemoryMailer) -> None:
    assert client.post(f"{API}/me/export").status_code in (401, 403)
    assert client.get(f"{API}/me/export").status_code == 401
    conta_logada(client, mailer)
    assert client.post(f"{API}/me/export").status_code == 403  # sem token CSRF


def test_segundo_pedido_em_24h_retorna_429_e_depois_libera(
    client: TestClient, mailer: MemoryMailer, fake_clock: FakeClock,
) -> None:
    a = conta_logada(client, mailer)
    assert _pedir_exportacao(a).status_code == 202
    limitado = _pedir_exportacao(a)
    assert limitado.status_code == 429
    assert int(limitado.headers["retry-after"]) > 0
    fake_clock.advance(hours=25)
    assert _pedir_exportacao(a).status_code == 202
    assert len(a.get(f"{API}/me/export").json()) == 2


def test_exportacao_e_so_de_quem_pediu_idor(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    export_id = _pedir_exportacao(a).json()["id"]
    assert b.get(f"{API}/me/export/{export_id}").status_code == 404
    assert b.get(f"{API}/me/export").json() == []
    assert a.get(f"{API}/me/export/00000000-0000-4000-8000-000000000000").status_code == 404
    assert a.get(f"{API}/me/export/{export_id}").status_code == 200


def test_link_da_exportacao_expira_em_7_dias_e_o_arquivo_e_apagado(
    client: TestClient, mailer: MemoryMailer, fake_clock: FakeClock, db: Session,
) -> None:
    a = conta_logada(client, mailer)
    export_id = _pedir_exportacao(a).json()["id"]
    fake_clock.advance(days=6)
    assert a.get(f"{API}/me/export/{export_id}").status_code == 200
    fake_clock.advance(days=2)
    assert a.get(f"{API}/me/export/{export_id}").status_code == 410
    assert a.get(f"{API}/me/export").json() == []
    assert db.scalar(select(func.count()).select_from(DataExportRequest)) == 1
    assert privacy_service.purge_expired_exports(db) == 1
    assert db.scalar(select(func.count()).select_from(DataExportRequest)) == 0


# ---------- RF-030 / CA-030: exclusão ----------

def test_exclusao_exige_a_senha_e_limita_tentativas(
    client: TestClient, mailer: MemoryMailer,
) -> None:
    a = conta_logada(client, mailer)
    assert a.post(f"{API}/me/delete", json={"password": PASSWORD}).status_code == 403  # CSRF
    assert _pedir_exclusao(a, "senha-errada-qualquer").status_code == 401
    assert _me(a)["deletion_scheduled_for"] is None  # nada mudou
    assert a.get(f"{API}/me/profile").status_code == 200
    assert _pedir_exclusao(a, "outra-senha-errada").status_code == 401
    assert _pedir_exclusao(a, "mais-uma-errada").status_code == 401
    limitado = _pedir_exclusao(a)  # 4ª tentativa no dia, mesmo com a senha certa
    assert limitado.status_code == 429
    assert a.get(f"{API}/me/profile").status_code == 200


def test_pedido_de_exclusao_revoga_sessoes_e_restringe_a_conta(
    client: TestClient, mailer: MemoryMailer, db: Session,
) -> None:
    a, b, online = _com_historico(client, mailer)
    outra_sessao = novo_cliente(client)
    assert login(outra_sessao, 1).status_code == 200

    resp = _pedir_exclusao(a)
    assert resp.status_code == 202
    assert "scheduled_for" in resp.json()
    # Todas as sessões foram revogadas e os cookies, limpos.
    assert a.get(f"{API}/me").status_code == 401
    assert outra_sessao.get(f"{API}/me").status_code == 401
    assert db.scalar(select(func.count()).select_from(AuthSession).where(
        AuthSession.revoked_at.is_(None))) == 1  # só a sessão de B
    # Aviso por e-mail sem a senha.
    aviso = next(m for m in mailer.sent if m.subject.startswith("Exclusão de conta"))
    assert aviso.to == "jogador1@example.test" and PASSWORD not in aviso.body
    assert db.scalar(select(AuditLog).where(AuditLog.action == "account_deletion_requested"))

    # Em carência, o login só serve para ver o estado e cancelar.
    c = novo_cliente(client)
    assert login(c, 1).status_code == 200
    assert _me(c)["deletion_scheduled_for"] is not None
    for path in ("/me/profile", "/me/preferences", "/me/active-matches", "/academy/tracks"):
        r = c.get(f"{API}{path}")
        assert r.status_code == 403 and r.json()["type"] == "account_pending_deletion", path
    assert c.post(f"{API}/matches", headers=csrf(c),
                  json={"game_id": "tictactoe", "mode": "local"}).status_code == 403
    assert novo_cliente(client).get(f"{API}/users/jogador_teste_01").status_code == 404

    # O oponente não espera: a partida em andamento foi encerrada e o nome já some.
    visao = b.get(f"{API}/matches/{online['id']}").json()
    assert visao["status"] == "finished" and visao["end_reason"] == "resign"
    assert {p["seat"]: p["display_name"] for p in visao["players"]}.get(
        next(s["seat"] for s in visao["seats"] if not s["is_you"])) is None


def test_cancelar_exclusao_restaura_a_conta(client: TestClient, mailer: MemoryMailer) -> None:
    a = conta_logada(client, mailer)
    assert _pedir_exclusao(a).status_code == 202
    c = novo_cliente(client)
    assert login(c, 1).status_code == 200
    assert c.post(f"{API}/me/delete/cancel", headers=csrf(c)).status_code == 204
    assert _me(c)["deletion_scheduled_for"] is None
    assert c.get(f"{API}/me/profile").status_code == 200
    assert c.post(f"{API}/me/delete/cancel", headers=csrf(c)).status_code == 409
    assert novo_cliente(client).get(f"{API}/users/jogador_teste_01").status_code == 200


def test_exportacao_continua_disponivel_durante_a_carencia(
    client: TestClient, mailer: MemoryMailer,
) -> None:
    a = conta_logada(client, mailer)
    assert _pedir_exclusao(a).status_code == 202
    c = novo_cliente(client)
    login(c, 1)
    assert _pedir_exportacao(c).status_code == 202


def test_exclusao_so_conclui_apos_14_dias_e_anonimiza_sem_quebrar_o_oponente(
    client: TestClient, mailer: MemoryMailer, db: Session, fake_clock: FakeClock,
) -> None:
    a, b, online = _com_historico(client, mailer)
    a_id = _uid(a)
    _pedir_exportacao(a)
    assert _pedir_exclusao(a).status_code == 202
    fake_clock.advance(days=13)
    assert jobs.run_daily(db) == 0
    assert db.get(User, a_id) is not None

    fake_clock.advance(days=2)
    assert jobs.run_daily(db) == 0
    db.expire_all()
    assert db.get(User, a_id) is None
    assert db.scalar(select(func.count()).select_from(UserProfile)) == 1  # só a de B
    assert db.scalar(select(func.count()).select_from(ExerciseAttempt)) == 0
    assert db.scalar(select(func.count()).select_from(DataExportRequest)) == 0
    # Não é mais possível entrar.
    assert login(novo_cliente(client), 1).status_code == 401

    # Partida com B permanece; o lado de A virou "conta removida".
    jogadores = db.scalars(select(MatchPlayer).where(
        MatchPlayer.match_id == uuid.UUID(online["id"])).order_by(MatchPlayer.seat)).all()
    assert [p.removed_account for p in jogadores].count(True) == 1
    removido = next(p for p in jogadores if p.removed_account)
    assert removido.user_id is None and not removido.is_ai
    visao = b.get(f"{API}/matches/{online['id']}").json()
    assert visao["status"] == "finished" and visao["ply"] == 3
    assert [p["display_name"] for p in visao["players"]].count(None) == 1
    assert len(b.get(f"{API}/matches/{online['id']}/moves").json()) == 3
    assert b.get(f"{API}/me/matches").status_code == 200
    # A partida contra a IA era só desta conta e foi apagada.
    assert db.scalar(select(func.count()).select_from(Match).where(Match.mode == "ai")) == 0
    # Auditoria mínima: sem autor e sem dados pessoais.
    registro = db.scalar(select(AuditLog).where(AuditLog.action == "account_deleted"))
    assert registro is not None and registro.actor_user_id is None and registro.details == {}
    todos = json.dumps([[r.action, r.target_id, r.details] for r in db.scalars(select(AuditLog))])
    assert "jogador1@example.test" not in todos and "jogador_teste_01" not in todos
    assert db.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.actor_user_id == a_id)) == 0
    # O nome de exibição volta a ficar livre.
    assert register(novo_cliente(client), 9, display_name="jogador_teste_01").status_code == 201


def test_conta_cancelada_nao_e_apagada_pelo_job(
    client: TestClient, mailer: MemoryMailer, db: Session, fake_clock: FakeClock,
) -> None:
    a = conta_logada(client, mailer)
    _pedir_exclusao(a)
    c = novo_cliente(client)
    login(c, 1)
    c.post(f"{API}/me/delete/cancel", headers=csrf(c))
    fake_clock.advance(days=30)
    assert privacy_service.purge_due_deletions(db) == (0, 0)
    assert db.scalar(select(func.count()).select_from(User)) == 1


# ---------- fluxo do responsável (RF-034) ----------

def _familia(client: TestClient, mailer: MemoryMailer
             ) -> tuple[TestClient, TestClient, str]:
    """Menor (conta 1, logada) vinculado ao responsável (conta 2, 18+)."""
    responsavel = conta_logada(novo_cliente(client), mailer, 2)
    assert register(client, 1, age_band="12_15",
                    guardian_email="jogador2@example.test").status_code == 201
    token = mailer.last_token("jogador1@example.test")
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 204
    assert login(client, 1).status_code == 200
    link = mailer.last_token("jogador2@example.test")
    ok = responsavel.post(f"{API}/guardian/links/confirm", headers=csrf(responsavel),
                          json={"token": link})
    assert ok.status_code == 200
    return client, responsavel, str(ok.json()["id"])


def test_responsavel_exporta_os_dados_do_menor(client: TestClient, mailer: MemoryMailer) -> None:
    menor, responsavel, filho = _familia(client, mailer)
    base = f"{API}/guardian/children/{filho}"
    pedido = responsavel.post(f"{base}/export", headers=csrf(responsavel))
    assert pedido.status_code == 202
    export_id = pedido.json()["id"]
    dados = responsavel.get(f"{base}/export/{export_id}").json()
    assert dados["account"]["email"] == "jogador1@example.test"
    assert dados["account"]["supervised"] is True
    assert "jogador2@example.test" not in json.dumps(dados)  # nem o e-mail do responsável
    assert len(responsavel.get(f"{base}/export").json()) == 1
    # O arquivo é de quem pediu; o menor não o baixa e o pedido não aparece para ele.
    assert menor.get(f"{API}/me/export/{export_id}").status_code == 404
    assert menor.get(f"{API}/me/export").json() == []


def test_adulto_nao_vinculado_nao_acessa_dados_nem_exclui_menor(
    client: TestClient, mailer: MemoryMailer,
) -> None:
    _, _, filho = _familia(client, mailer)
    intruso = conta_logada(novo_cliente(client), mailer, 3)
    base = f"{API}/guardian/children/{filho}"
    assert intruso.post(f"{base}/export", headers=csrf(intruso)).status_code == 404
    assert intruso.get(f"{base}/export").status_code == 404
    assert intruso.post(f"{base}/delete", headers=csrf(intruso),
                        json={"password": PASSWORD}).status_code == 404
    assert intruso.post(f"{base}/delete/cancel", headers=csrf(intruso)).status_code == 404


def test_responsavel_exclui_o_menor_com_a_propria_senha(
    client: TestClient, mailer: MemoryMailer, db: Session, fake_clock: FakeClock,
) -> None:
    menor, responsavel, filho = _familia(client, mailer)
    base = f"{API}/guardian/children/{filho}"
    assert responsavel.post(f"{base}/delete", headers=csrf(responsavel),
                            json={"password": "senha-errada-qualquer"}).status_code == 401
    assert responsavel.post(f"{base}/delete", headers=csrf(responsavel),
                            json={"password": PASSWORD}).status_code == 202
    # Sessões do menor revogadas; o responsável continua logado.
    assert menor.get(f"{API}/me").status_code == 401
    assert responsavel.get(f"{API}/guardian/children").json()[0]["deletion_scheduled_for"]
    evento = db.scalar(select(AuditLog).where(AuditLog.action == "account_deletion_requested"))
    assert evento is not None and evento.details["by_guardian"] is True
    assert evento.actor_user_id == _uid(responsavel)

    # O menor não desfaz a decisão do responsável; o responsável, sim.
    c = novo_cliente(client)
    assert login(c, 1).status_code == 200
    assert c.post(f"{API}/me/delete/cancel", headers=csrf(c)).status_code == 403
    assert responsavel.post(f"{base}/delete/cancel",
                            headers=csrf(responsavel)).status_code == 204
    assert c.post(f"{API}/me/delete", headers=csrf(c),
                  json={"password": PASSWORD}).status_code == 202  # pedido do próprio menor
    # Agora o responsável não cancela a decisão do menor.
    assert responsavel.post(f"{base}/delete/cancel", headers=csrf(responsavel)).status_code == 403
    fake_clock.advance(days=15)
    assert jobs.run_daily(db) == 0
    assert db.scalar(select(func.count()).select_from(User)) == 1  # só o responsável


def test_exclusao_do_responsavel_devolve_o_menor_ao_padrao_protetivo(
    client: TestClient, mailer: MemoryMailer, db: Session, fake_clock: FakeClock,
) -> None:
    menor, responsavel, filho = _familia(client, mailer)
    limite = responsavel.put(f"{API}/guardian/children/{filho}/settings",
                             headers=csrf(responsavel),
                             json={"profile_public": True, "daily_minutes_limit": 60})
    assert limite.status_code == 200
    assert _pedir_exclusao(responsavel).status_code == 202
    fake_clock.advance(days=15)
    assert jobs.run_daily(db) == 0
    db.expire_all()
    crianca = db.get(User, uuid.UUID(filho))
    assert crianca is not None and crianca.guardian_user_id is None
    assert crianca.profile.is_public is False and crianca.profile.show_in_ranking is False
    assert crianca.preferences.daily_minutes_limit is None
    assert crianca.preferences.allow_open_matchmaking is False
    assert menor.get(f"{API}/me").status_code == 200


def test_job_diario_remove_exportacoes_vencidas_e_nao_falha_sem_trabalho(
    client: TestClient, mailer: MemoryMailer, db: Session, fake_clock: FakeClock,
) -> None:
    a = conta_logada(client, mailer)
    _pedir_exportacao(a)
    fake_clock.advance(days=8)
    assert jobs.run_daily(db) == 0
    assert db.scalar(select(func.count()).select_from(DataExportRequest)) == 0


def test_tabelas_novas_dependem_de_users_em_cascata(db: Session) -> None:
    rows = db.execute(text(
        "SELECT conname, confdeltype FROM pg_constraint "
        "WHERE conrelid = 'data_export_requests'::regclass AND contype = 'f' ORDER BY conname"
    )).all()
    assert {r.confdeltype for r in rows} == {"c", "n"}  # CASCADE (titular) e SET NULL (autor)


@pytest.mark.parametrize("campo", ["user_id", "requested_by_user_id", "id"])
def test_cliente_nao_escolhe_o_titular(client: TestClient, mailer: MemoryMailer,
                                       campo: str) -> None:
    a, b = duas_contas(client, mailer)
    b_id = _me(b)["id"]
    resp = a.post(f"{API}/me/delete", headers=csrf(a), json={"password": PASSWORD, campo: b_id})
    assert resp.status_code == 422
    assert _me(b)["deletion_scheduled_for"] is None
