"""RF-031 (CA-031) e RF-032 (CA-032): amizades, bloqueio, convites diretos, denúncias, moderação.

Duas a quatro contas sintéticas (`@example.test`); relógio injetado (`fake_clock`). O cadastro
real é limitado a 5 contas/hora/IP, então os testes zeram o limitador antes de cada cadastro.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.ratelimit import limiter
from app.models import AuditLog, Report, User
from tests.conftest import FakeClock, MemoryMailer
from tests.helpers import API, conta_logada, csrf, login, novo_cliente, register
from tests.online_helpers import partida


def nome(n: int) -> str:
    return f"jogador_teste_{n:02d}"


def conta(app: TestClient, mailer: MemoryMailer, n: int) -> TestClient:
    limiter.reset()
    return conta_logada(novo_cliente(app), mailer, n)


def promover(db: Session, n: int, role: str) -> None:
    db.execute(update(User).where(User.email == f"jogador{n}@example.test").values(role=role))
    db.commit()


def adulto(app: TestClient, mailer: MemoryMailer, n: int) -> TestClient:
    return conta(app, mailer, n)


def menor(app: TestClient, mailer: MemoryMailer, n: int, g: int, resp: TestClient,
          liberar: bool) -> TestClient:
    """Menor 12–15 `n` supervisionado pela conta `g` (logada em `resp`); `liberar` abre o social."""
    limiter.reset()
    c = novo_cliente(app)
    email = f"jogador{g}@example.test"
    assert register(c, n, age_band="12_15", guardian_email=email).status_code == 201
    ok = resp.post(f"{API}/guardian/links/confirm", headers=csrf(resp),
                   json={"token": mailer.last_token(email)})
    assert ok.status_code == 200, ok.text
    assert c.post(f"{API}/auth/verify-email",
                  json={"token": mailer.last_token(f"jogador{n}@example.test")}).status_code == 204
    assert login(c, n).status_code == 200
    if liberar:
        r = resp.put(f"{API}/guardian/children/{ok.json()['id']}/settings", headers=csrf(resp),
                     json={"allow_open_matchmaking": True, "profile_public": True})
        assert r.status_code == 200, r.text
    return c


def pedir(c: TestClient, n: int) -> Any:
    return c.post(f"{API}/friends/requests", headers=csrf(c), json={"display_name": nome(n)})


def amigos(a: TestClient, b: TestClient, nb: int) -> str:
    """`a` pede, `b` aceita; devolve o id da amizade."""
    r = pedir(a, nb)
    assert r.status_code == 201, r.text
    fid = str(r.json()["friendship_id"])
    ok = b.post(f"{API}/friends/requests/{fid}/accept", headers=csrf(b))
    assert ok.status_code == 200, ok.text
    return fid


# ---------- amizades ----------

def test_pedir_aceitar_listar_e_remover(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    r = pedir(a, 2)
    assert r.status_code == 201
    assert set(r.json()) == {"friendship_id", "display_name", "avatar_key", "created_at"}
    assert b.get(f"{API}/friends/requests").json()["incoming"][0]["display_name"] == nome(1)
    assert a.get(f"{API}/friends/requests").json()["outgoing"][0]["display_name"] == nome(2)
    assert pedir(a, 2).status_code == 409  # já pendente
    fid = r.json()["friendship_id"]
    assert b.post(f"{API}/friends/requests/{fid}/accept", headers=csrf(b)).status_code == 200
    lista = a.get(f"{API}/friends").json()
    assert [f["display_name"] for f in lista] == [nome(2)]
    assert "email" not in str(lista).lower() and "@" not in str(lista)
    assert pedir(b, 1).status_code == 409  # já amigos
    assert a.delete(f"{API}/friends/{fid}", headers=csrf(a)).status_code == 204
    assert b.get(f"{API}/friends").json() == []


def test_pedido_cruzado_vira_amizade(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    assert pedir(a, 2).status_code == 201
    assert pedir(b, 1).status_code == 201
    assert len(a.get(f"{API}/friends").json()) == 1


def test_pessoa_inexistente_privada_ou_a_si_mesmo_e_404(client: TestClient,
                                                        mailer: MemoryMailer) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    assert b.patch(f"{API}/me/profile", headers=csrf(b),
                   json={"is_public": False}).status_code == 200
    privado, ausente, proprio = pedir(a, 2), pedir(a, 9), pedir(a, 1)
    assert privado.status_code == ausente.status_code == proprio.status_code == 404
    assert privado.json()["type"] == ausente.json()["type"] == "user_not_found"


def test_idor_de_amizade_e_convite(client: TestClient, mailer: MemoryMailer) -> None:
    a, b, c = (adulto(client, mailer, n) for n in (1, 2, 3))
    fid = amigos(a, b, 2)
    inv = a.post(f"{API}/friends/{fid}/invitations", headers=csrf(a), json={"game_id": "tictactoe"})
    assert inv.status_code == 201, inv.text
    iid = inv.json()["id"]
    for resp in (
        c.delete(f"{API}/friends/{fid}", headers=csrf(c)),
        c.post(f"{API}/friends/{fid}/invitations", headers=csrf(c),
               json={"game_id": "tictactoe"}),
        c.post(f"{API}/invitations/{iid}/accept", headers=csrf(c)),
        c.post(f"{API}/invitations/{iid}/decline", headers=csrf(c)),
        c.post(f"{API}/invitations/{iid}/cancel", headers=csrf(c)),
        c.post(f"{API}/friends/requests/{fid}/accept", headers=csrf(c)),
    ):
        assert resp.status_code == 404, resp.text
    assert a.post(f"{API}/invitations/{iid}/accept", headers=csrf(a)).status_code == 404


def test_so_o_destinatario_aceita_ou_recusa_pedido(client: TestClient,
                                                   mailer: MemoryMailer) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    fid = pedir(a, 2).json()["friendship_id"]
    assert a.post(f"{API}/friends/requests/{fid}/accept", headers=csrf(a)).status_code == 404
    assert a.post(f"{API}/friends/requests/{fid}/decline", headers=csrf(a)).status_code == 404
    assert b.post(f"{API}/friends/requests/{fid}/decline", headers=csrf(b)).status_code == 204
    assert b.get(f"{API}/friends/requests").json()["incoming"] == []


def test_recusado_espera_sete_dias_para_repetir(client: TestClient, mailer: MemoryMailer,
                                                fake_clock: FakeClock) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    fid = pedir(a, 2).json()["friendship_id"]
    b.post(f"{API}/friends/requests/{fid}/decline", headers=csrf(b))
    r = pedir(a, 2)
    assert r.status_code == 409 and r.json()["type"] == "request_cooldown"
    assert int(r.headers["Retry-After"]) > 0
    fake_clock.advance(days=3.5)
    a.get(f"{API}/friends")  # mantém a sessão ativa
    fake_clock.advance(days=3.6)
    assert pedir(a, 2).status_code == 201
    assert len(b.get(f"{API}/friends/requests").json()["incoming"]) == 1


def test_limite_de_denuncias_por_dia(client: TestClient, mailer: MemoryMailer,
                                     fake_clock: FakeClock) -> None:
    a, _ = adulto(client, mailer, 1), adulto(client, mailer, 2)
    body = {"target_type": "user", "target_id": nome(2), "reason": "other"}
    codes = [a.post(f"{API}/reports", headers=csrf(a), json=body).status_code
             for _ in range(11)]
    assert codes[0] == 201 and codes[1:10] == [409] * 9 and codes[10] == 429
    fake_clock.advance(days=1, minutes=1)
    a.get(f"{API}/friends")
    assert a.post(f"{API}/reports", headers=csrf(a), json=body).status_code == 409


# ---------- bloqueio (CA-032) ----------

def test_bloqueado_nao_consegue_convidar_quem_bloqueou(client: TestClient,
                                                       mailer: MemoryMailer) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    fid = amigos(a, b, 2)
    r = b.post(f"{API}/blocks", headers=csrf(b), json={"display_name": nome(1)})
    assert r.status_code == 201 and set(r.json()) == {
        "block_id", "display_name", "avatar_key", "created_at"}
    # a amizade acabou e o bloqueado não vê que foi bloqueado: tudo responde 404
    assert a.post(f"{API}/friends/{fid}/invitations", headers=csrf(a),
                  json={"game_id": "tictactoe"}).status_code == 404
    assert pedir(a, 2).status_code == 404
    assert a.get(f"{API}/friends").json() == []
    # quem bloqueou também não pede amizade enquanto o bloqueio existir? pede, mas nada muda
    assert [x["display_name"] for x in b.get(f"{API}/blocks").json()] == [nome(1)]
    bid = r.json()["block_id"]
    assert a.delete(f"{API}/blocks/{bid}", headers=csrf(a)).status_code == 404  # IDOR
    assert b.delete(f"{API}/blocks/{bid}", headers=csrf(b)).status_code == 204
    assert pedir(a, 2).status_code == 201


def test_bloqueio_cancela_convite_pendente_e_encerra_sala(client: TestClient,
                                                          mailer: MemoryMailer) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    fid = amigos(a, b, 2)
    inv = a.post(f"{API}/friends/{fid}/invitations", headers=csrf(a),
                 json={"game_id": "tictactoe"}).json()
    b.post(f"{API}/blocks", headers=csrf(b), json={"display_name": nome(1)})
    assert b.get(f"{API}/invitations").json() == []
    assert a.get(f"{API}/matches/{inv['match_id']}").json()["status"] == "aborted"


# ---------- convites diretos ----------

def test_convite_direto_aceito_inicia_partida(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    fid = amigos(a, b, 2)
    inv = a.post(f"{API}/friends/{fid}/invitations", headers=csrf(a),
                 json={"game_id": "tictactoe"})
    assert inv.status_code == 201 and "invite_code" not in inv.text
    again = a.post(f"{API}/friends/{fid}/invitations", headers=csrf(a),
                   json={"game_id": "tictactoe"})
    assert again.status_code == 409
    recebido = b.get(f"{API}/invitations").json()
    assert len(recebido) == 1 and recebido[0]["other"]["display_name"] == nome(1)
    assert recebido[0]["match_id"] is None  # só o remetente vê a sala
    assert len(a.get(f"{API}/invitations?box=sent").json()) == 1
    ok = b.post(f"{API}/invitations/{inv.json()['id']}/accept", headers=csrf(b))
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "in_progress"
    assert a.get(f"{API}/matches/{inv.json()['match_id']}").json()["status"] == "in_progress"
    assert b.get(f"{API}/invitations").json() == []
    assert b.post(f"{API}/invitations/{inv.json()['id']}/accept",
                  headers=csrf(b)).status_code == 404


def test_convite_recusado_cancelado_e_expirado(client: TestClient, mailer: MemoryMailer,
                                               fake_clock: FakeClock) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    fid = amigos(a, b, 2)
    corpo = {"game_id": "tictactoe"}
    i1 = a.post(f"{API}/friends/{fid}/invitations", headers=csrf(a), json=corpo).json()
    assert b.post(f"{API}/invitations/{i1['id']}/decline", headers=csrf(b)).status_code == 204
    assert a.get(f"{API}/matches/{i1['match_id']}").json()["status"] == "aborted"
    i2 = a.post(f"{API}/friends/{fid}/invitations", headers=csrf(a), json=corpo).json()
    assert a.post(f"{API}/invitations/{i2['id']}/cancel", headers=csrf(a)).status_code == 204
    i3 = a.post(f"{API}/friends/{fid}/invitations", headers=csrf(a), json=corpo).json()
    fake_clock.advance(minutes=16)
    assert b.get(f"{API}/invitations").json() == []
    assert b.post(f"{API}/invitations/{i3['id']}/accept", headers=csrf(b)).status_code == 404


def test_remover_amigo_cancela_convites(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    fid = amigos(a, b, 2)
    a.post(f"{API}/friends/{fid}/invitations", headers=csrf(a), json={"game_id": "chess"})
    a.delete(f"{API}/friends/{fid}", headers=csrf(a))
    assert b.get(f"{API}/invitations").json() == []


def test_nao_ha_chat_livre(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    fid = amigos(a, b, 2)
    for path in (f"/friends/{fid}/messages", "/messages", "/chat"):
        r = a.post(f"{API}{path}", headers=csrf(a), json={"text": "oi"})
        assert r.status_code in (404, 405)


# ---------- ECA ----------

def test_menor_sem_liberacao_do_responsavel_nao_usa_o_social(client: TestClient,
                                                             mailer: MemoryMailer) -> None:
    resp = adulto(client, mailer, 2)
    m = menor(client, mailer, 1, 2, resp, liberar=False)
    r = pedir(m, 2)
    assert r.status_code == 403 and r.json()["type"] == "supervision_required"
    assert m.get(f"{API}/friends").status_code == 200  # a lista (vazia) não revela ninguém
    assert m.get(f"{API}/friends").json() == []


def test_menor_e_adulto_nunca_sao_amigos(client: TestClient, mailer: MemoryMailer) -> None:
    resp, outro = adulto(client, mailer, 2), adulto(client, mailer, 3)
    m = menor(client, mailer, 1, 2, resp, liberar=True)
    assert pedir(m, 3).status_code == 404  # adulto qualquer
    assert pedir(outro, 1).status_code == 404  # e o inverso
    assert pedir(m, 2).status_code == 404  # nem o próprio responsável


def test_menores_liberados_viram_amigos_e_perdem_o_acesso_se_o_responsavel_revoga(
        client: TestClient, mailer: MemoryMailer) -> None:
    r1, r2 = adulto(client, mailer, 3), adulto(client, mailer, 4)
    m1 = menor(client, mailer, 1, 3, r1, liberar=True)
    m2 = menor(client, mailer, 2, 4, r2, liberar=True)
    fid = amigos(m1, m2, 2)
    filho = r1.get(f"{API}/guardian/children").json()[0]["id"]
    r1.put(f"{API}/guardian/children/{filho}/settings", headers=csrf(r1),
           json={"allow_open_matchmaking": False})
    r = m1.post(f"{API}/friends/{fid}/invitations", headers=csrf(m1),
                json={"game_id": "tictactoe"})
    assert r.status_code == 403 and r.json()["type"] == "supervision_required"
    assert m2.post(f"{API}/friends/{fid}/invitations", headers=csrf(m2),
                   json={"game_id": "tictactoe"}).status_code == 404


# ---------- denúncias ----------

def test_denunciar_usuario_e_partida(client: TestClient, mailer: MemoryMailer,
                                     db: Session) -> None:
    a, b, c = (adulto(client, mailer, n) for n in (1, 2, 3))
    ok = a.post(f"{API}/reports", headers=csrf(a), json={
        "target_type": "user", "target_id": nome(2), "reason": "offensive_bio",
        "note": "  <script>alert(1)</script>\x00 texto​   com   espaços  "})
    assert ok.status_code == 201 and set(ok.json()) == {"id", "status", "created_at"}
    rep = db.scalars(select(Report)).one()
    assert rep.note == "scriptalert(1)/script texto com espaços"
    assert a.post(f"{API}/reports", headers=csrf(a), json={
        "target_type": "user", "target_id": nome(1), "reason": "other"}).status_code == 422
    assert a.post(f"{API}/reports", headers=csrf(a), json={
        "target_type": "user", "target_id": nome(9), "reason": "other"}).status_code == 404
    assert a.post(f"{API}/reports", headers=csrf(a), json={
        "target_type": "user", "target_id": nome(2), "reason": "bogus"}).status_code == 422
    sala = partida(a, b)
    corpo = {"target_type": "match", "target_id": sala["id"], "reason": "cheating"}
    assert a.post(f"{API}/reports", headers=csrf(a), json=corpo).status_code == 201
    assert c.post(f"{API}/reports", headers=csrf(c), json=corpo).status_code == 404  # IDOR
    assert a.post(f"{API}/reports", headers=csrf(a), json={
        **corpo, "reason": "offensive_name"}).status_code == 422
    assert db.scalars(select(Report).where(Report.target_type == "match")).one() \
        .target_user_id == db.scalar(select(User.id).where(User.email == "jogador2@example.test"))


def test_denuncia_exige_conta_logada_e_csrf(client: TestClient, mailer: MemoryMailer) -> None:
    a = adulto(client, mailer, 1)
    adulto(client, mailer, 2)
    body = {"target_type": "user", "target_id": nome(2), "reason": "other"}
    assert a.post(f"{API}/reports", json=body).status_code in (400, 403)
    assert novo_cliente(client).post(f"{API}/reports", json=body).status_code in (401, 403)


# ---------- moderação (CA-031) ----------

def _denunciar(c: TestClient, alvo: int, motivo: str = "harassment") -> str:
    r = c.post(f"{API}/reports", headers=csrf(c), json={
        "target_type": "user", "target_id": nome(alvo), "reason": motivo, "note": "ofensivo"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_usuario_comum_recebe_403_em_admin(client: TestClient, mailer: MemoryMailer) -> None:
    a = adulto(client, mailer, 1)
    adulto(client, mailer, 2)
    rid = _denunciar(a, 2)
    uid = "00000000-0000-4000-8000-000000000000"
    for resp in (
        a.get(f"{API}/admin/reports"),
        a.post(f"{API}/admin/reports/{rid}/resolve", headers=csrf(a), json={"action": "archive"}),
        a.post(f"{API}/admin/users/{uid}/suspend", headers=csrf(a), json={"reason": "teste"}),
        a.post(f"{API}/admin/users/{uid}/reinstate", headers=csrf(a)),
    ):
        assert resp.status_code == 403, resp.text
    assert novo_cliente(client).get(f"{API}/admin/reports").status_code == 401


def test_fila_nao_expoe_denunciante(client: TestClient, mailer: MemoryMailer,
                                    db: Session) -> None:
    a, _, mod = (adulto(client, mailer, n) for n in (1, 2, 3))
    promover(db, 3, "moderator")
    _denunciar(a, 2)
    fila = mod.get(f"{API}/admin/reports")
    assert fila.status_code == 200
    item = fila.json()["items"][0]
    assert item["target_display_name"] == nome(2) and item["open_reports_on_target"] == 1
    assert nome(1) not in fila.text and "reporter" not in fila.text and "@" not in fila.text
    assert mod.get(f"{API}/admin/reports?status=resolved").json()["total"] == 0
    assert mod.get(f"{API}/admin/reports?limit=0").status_code == 422


def test_suspender_gera_auditoria_e_impede_login_e_uso(client: TestClient, mailer: MemoryMailer,
                                                      db: Session) -> None:
    a, b, mod = (adulto(client, mailer, n) for n in (1, 2, 3))
    promover(db, 3, "moderator")
    sala = partida(a, b)
    rid = _denunciar(a, 2)
    r = mod.post(f"{API}/admin/reports/{rid}/resolve", headers=csrf(mod),
                 json={"action": "suspend", "note": "assédio"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resolved" and r.json()["resolution_action"] == "suspend"
    acoes = db.scalars(select(AuditLog.action).order_by(AuditLog.created_at)).all()
    assert "user_suspended" in acoes and "report_resolved" in acoes
    log = db.scalars(select(AuditLog).where(AuditLog.action == "user_suspended")).one()
    assert log.actor_user_id == db.scalar(
        select(User.id).where(User.email == "jogador3@example.test"))
    # sessão revogada, login recusado e partida em andamento encerrada
    assert b.get(f"{API}/me/profile").status_code == 401
    assert login(b, 2).status_code == 403
    assert a.get(f"{API}/matches/{sala['id']}").json()["status"] == "finished"
    assert mailer.sent[-1].to == "jogador2@example.test"
    assert nome(1) not in mailer.sent[-1].body
    # segunda resolução e suspensão repetida são recusadas
    assert mod.post(f"{API}/admin/reports/{rid}/resolve", headers=csrf(mod),
                    json={"action": "archive"}).status_code == 409
    uid = str(db.scalar(select(User.id).where(User.email == "jogador2@example.test")))
    assert mod.post(f"{API}/admin/users/{uid}/suspend", headers=csrf(mod),
                    json={"reason": "de novo"}).status_code == 409
    # reativar devolve o acesso
    assert mod.post(f"{API}/admin/users/{uid}/reinstate", headers=csrf(mod)).status_code == 200
    assert login(b, 2).status_code == 200
    assert "user_reinstated" in db.scalars(select(AuditLog.action)).all()


def test_advertir_e_arquivar_nao_suspendem(client: TestClient, mailer: MemoryMailer,
                                          db: Session) -> None:
    a, b, mod = (adulto(client, mailer, n) for n in (1, 2, 3))
    promover(db, 3, "moderator")
    r1, r2 = _denunciar(a, 2), _denunciar(a, 2, "other")
    assert mod.post(f"{API}/admin/reports/{r1}/resolve", headers=csrf(mod),
                    json={"action": "warn"}).status_code == 200
    assert mod.post(f"{API}/admin/reports/{r2}/resolve", headers=csrf(mod),
                    json={"action": "archive"}).status_code == 200
    assert b.get(f"{API}/me/profile").status_code == 200
    detalhes = db.scalars(select(AuditLog).where(AuditLog.action == "report_resolved")).all()
    assert sorted(d.details["action"] for d in detalhes) == ["archive", "warn"]
    assert mod.get(f"{API}/admin/reports?status=all").json()["total"] == 2
    assert mod.post(f"{API}/admin/reports/00000000-0000-4000-8000-000000000000/resolve",
                    headers=csrf(mod), json={"action": "archive"}).status_code == 404


def test_ocultar_conteudo_apaga_bio_e_troca_apelido(client: TestClient, mailer: MemoryMailer,
                                                    db: Session) -> None:
    a, b, mod = (adulto(client, mailer, n) for n in (1, 2, 3))
    promover(db, 3, "moderator")
    b.patch(f"{API}/me/profile", headers=csrf(b), json={"bio": "texto ofensivo"})
    rid = _denunciar(a, 2, "offensive_name")
    r = mod.post(f"{API}/admin/reports/{rid}/resolve", headers=csrf(mod),
                 json={"action": "warn", "hide_content": True})
    assert r.status_code == 200
    perfil = b.get(f"{API}/me/profile").json()
    assert perfil["bio"] is None and perfil["display_name"].startswith("jogador-")


def test_hierarquia_de_papeis(client: TestClient, mailer: MemoryMailer, db: Session) -> None:
    a, mod, adm, mod2 = (adulto(client, mailer, n) for n in (1, 2, 3, 4))
    promover(db, 2, "moderator")
    promover(db, 3, "admin")
    promover(db, 4, "moderator")
    uid = {n: str(db.scalar(select(User.id).where(User.email == f"jogador{n}@example.test")))
           for n in (2, 3, 4)}
    corpo = {"reason": "teste de hierarquia"}
    assert mod.post(f"{API}/admin/users/{uid[3]}/suspend", headers=csrf(mod),
                    json=corpo).status_code == 403  # moderador × admin
    assert mod.post(f"{API}/admin/users/{uid[4]}/suspend", headers=csrf(mod),
                    json=corpo).status_code == 403  # moderador × moderador
    assert mod.post(f"{API}/admin/users/{uid[2]}/suspend", headers=csrf(mod),
                    json=corpo).status_code == 403  # a si mesmo
    assert adm.post(f"{API}/admin/users/{uid[3]}/suspend", headers=csrf(adm),
                    json=corpo).status_code == 403
    assert adm.post(f"{API}/admin/users/{uid[4]}/suspend", headers=csrf(adm),
                    json=corpo).status_code == 200
    assert mod2.get(f"{API}/admin/reports").status_code == 401  # sessão revogada
    assert a.get(f"{API}/admin/reports").status_code == 403


def test_suspenso_some_das_listas_e_nao_recebe_pedidos(client: TestClient, mailer: MemoryMailer,
                                                      db: Session) -> None:
    a, b, mod = (adulto(client, mailer, n) for n in (1, 2, 3))
    promover(db, 3, "moderator")
    amigos(a, b, 2)
    uid = str(db.scalar(select(User.id).where(User.email == "jogador2@example.test")))
    assert mod.post(f"{API}/admin/users/{uid}/suspend", headers=csrf(mod),
                    json={"reason": "teste de suspensão"}).status_code == 200
    assert a.get(f"{API}/friends").json() == []
    assert pedir(a, 2).status_code == 404


@pytest.mark.parametrize("campo", ["reporter_id", "reporter"])
def test_resposta_do_denunciado_nao_tem_rota_para_ver_denuncias(
        client: TestClient, mailer: MemoryMailer, campo: str) -> None:
    a, b = adulto(client, mailer, 1), adulto(client, mailer, 2)
    _denunciar(a, 2)
    for path in ("/reports", "/me/reports", "/users/" + nome(2)):
        resp = b.get(f"{API}{path}")
        assert campo not in resp.text
