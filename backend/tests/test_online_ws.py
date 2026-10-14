"""WebSocket das partidas online: RF-011, RF-013, RF-014, RF-015 (CA-011, CA-013, CA-014, CA-015).

Dois usuários sintéticos, cada um com seu cliente HTTP; a conexão usa o cookie de sessão.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.game_engines.base import state_hash
from app.models import Match, MatchMove
from app.realtime import endpoint
from tests.conftest import FakeClock, MemoryMailer
from tests.helpers import API, conta_logada, csrf, novo_cliente
from tests.online_helpers import (
    criar_convite,
    duas_contas,
    entrar_por_codigo,
    jogar_aleatorio,
    lance,
    partida,
)
from tests.ws_helpers import abrir, ate, codigo_de_fechamento, entrar, enviar, receber


def mover(sessao: Any, match_id: str, move: str, ply: int, cid: str | None = None) -> str:
    return enviar(sessao, "submit_move", {"match_id": match_id, "expected_ply": ply, "move": move,
                                          "client_move_id": cid or str(uuid.uuid4())})


# ---------- handshake e segurança (SEC-06) ----------

def test_sem_cookie_fecha_com_4401(client: TestClient) -> None:
    anonimo = novo_cliente(client)
    with abrir(anonimo) as w, pytest.raises(WebSocketDisconnect) as exc:
        receber(w)
    assert exc.value.code == 4401


def test_sessao_revogada_nao_conecta(client: TestClient, mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    token = a.cookies.get("bh_session")
    assert a.post(f"{API}/auth/logout", headers=csrf(a)).status_code == 204
    with abrir(a, token=token) as w, pytest.raises(WebSocketDisconnect) as exc:
        receber(w)
    assert exc.value.code == 4401


@pytest.mark.parametrize("origem", [None, "https://evil.example.test", "http://localhost:5173/x"])
def test_origem_fora_da_lista_fecha_com_4403(client: TestClient, mailer: MemoryMailer,
                                             origem: str | None) -> None:
    a, _ = duas_contas(client, mailer)
    with abrir(a, origem=origem) as w, pytest.raises(WebSocketDisconnect) as exc:
        receber(w)
    assert exc.value.code == 4403


def test_logout_fecha_conexoes_abertas_no_proximo_batimento(
        client: TestClient, mailer: MemoryMailer, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(endpoint, "PING_INTERVAL", 0.05)
    a, _ = duas_contas(client, mailer)
    with abrir(a) as w:
        assert a.post(f"{API}/auth/logout", headers=csrf(a)).status_code == 204
        assert codigo_de_fechamento(w) == 4401


def test_sem_resposta_ao_ping_a_conexao_cai(client: TestClient, mailer: MemoryMailer,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(endpoint, "PING_INTERVAL", 0.05)
    monkeypatch.setattr(endpoint, "PONG_TIMEOUT", 0.2)
    a, _ = duas_contas(client, mailer)
    with abrir(a) as w:
        assert codigo_de_fechamento(w) == 4408


def test_pong_mantem_a_conexao_viva(client: TestClient, mailer: MemoryMailer,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(endpoint, "PING_INTERVAL", 0.05)
    monkeypatch.setattr(endpoint, "PONG_TIMEOUT", 1.0)
    a, _ = duas_contas(client, mailer)
    with abrir(a) as w:
        for _ in range(8):
            assert receber(w)["type"] == "ping"
            w.send_json({"type": "pong"})


def test_mensagem_maior_que_4_kb_fecha_com_1009(client: TestClient, mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    with abrir(a) as w:
        w.send_text("x" * 5000)
        assert codigo_de_fechamento(w) == 1009


def test_mais_de_20_mensagens_por_segundo_fecha_com_4429(client: TestClient,
                                                         mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    with abrir(a) as w:
        for _ in range(30):
            w.send_json({"type": "pong"})
        assert codigo_de_fechamento(w) == 4429


@pytest.mark.parametrize("bruto", [
    "{nao e json",
    '{"type": "hack", "id": "%s", "payload": {}}',
    '{"type": "resign", "id": "nao-e-uuid", "payload": {"match_id": "%s"}}',
    '{"type": "resign", "id": "%s", "payload": {"match_id": "%s", "user_id": "x"}}',
    '{"type": "resign", "id": "%s", "payload": {"match_id": "%s"}, "result": "p1_win"}',
])
def test_mensagens_invalidas_geram_erro_de_validacao_sem_derrubar(
        client: TestClient, mailer: MemoryMailer, bruto: str) -> None:
    a, _ = duas_contas(client, mailer)
    texto = bruto.replace("%s", str(uuid.uuid4()))
    with abrir(a) as w:
        w.send_text(texto)
        erro = ate(w, "error")
        assert erro["payload"]["code"] == "validation_error" and erro["payload"]["status"] == 422
        w.send_json({"type": "pong"})  # a conexão continua aberta


def test_campos_do_cliente_nao_sao_aceitos_no_lance(client: TestClient,
                                                    mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    with abrir(a) as w:
        entrar(w, mid)
        for extra in ({"result": "p1_win"}, {"state": {"board": "XXX______"}}, {"seat": 2},
                      {"user_id": str(uuid.uuid4())}):
            req = enviar(w, "submit_move", {"match_id": mid, "expected_ply": 0, "move": "0",
                                            "client_move_id": str(uuid.uuid4()), **extra})
            erro = ate(w, "error", reply_to=req)
            assert erro["payload"]["code"] == "validation_error"
    assert a.get(f"{API}/matches/{mid}").json()["ply"] == 0


# ---------- IDOR (SEC-05) ----------

def test_terceiro_recebe_nao_encontrada_no_ws(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    intruso = conta_logada(novo_cliente(client), mailer, 3)
    with abrir(intruso) as w:
        for tipo, payload in (
            ("join_match", {"match_id": mid, "last_known_ply": 0}),
            ("submit_move", {"match_id": mid, "expected_ply": 0, "move": "0",
                             "client_move_id": str(uuid.uuid4())}),
            ("resign", {"match_id": mid}),
            ("offer_draw", {"match_id": mid}),
            ("respond_draw", {"match_id": mid, "accept": True}),
            ("claim_abandon", {"match_id": mid}),
            ("join_match", {"match_id": str(uuid.uuid4()), "last_known_ply": 0}),
        ):
            req = enviar(w, tipo, payload)
            erro = ate(w, "error", reply_to=req)
            assert erro["payload"]["code"] == "not_found", tipo
            assert erro["payload"]["status"] == 404
    assert a.get(f"{API}/matches/{mid}").json()["status"] == "in_progress"


def test_comandos_online_recusam_partida_contra_ia(client: TestClient,
                                                   mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    m = a.post(f"{API}/matches", headers=csrf(a),
               json={"game_id": "tictactoe", "mode": "ai", "ai_level": 1}).json()
    with abrir(a) as w:
        req = mover(w, m["id"], "4", m["ply"])
        assert ate(w, "error", reply_to=req)["payload"]["code"] == "not_online_match"


# ---------- convite: match_started (RF-011) ----------

def test_ambos_recebem_match_started_quando_o_segundo_entra(client: TestClient,
                                                            mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    sala = criar_convite(a)
    with abrir(a) as wa, abrir(b) as wb:
        snap = entrar(wa, sala["id"])[-1]
        assert snap["payload"]["status"] == "waiting" and snap["payload"]["your_seat"] == 1
        assert entrar_por_codigo(b, sala["invite_code"]).status_code == 200
        for w in (wa, wb):
            msg = ate(w, "match_started")
            assert msg["payload"] == {"match_id": sala["id"], "game_id": "tictactoe"}


def test_fila_avisa_quem_esperava_por_websocket(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    with abrir(a) as wa:
        assert a.post(f"{API}/matchmaking/queue", headers=csrf(a),
                      json={"game_id": "tictactoe"}).status_code == 202
        r = b.post(f"{API}/matchmaking/queue", headers=csrf(b), json={"game_id": "tictactoe"})
        assert r.json()["state"] == "matched"
        assert ate(wa, "match_started")["payload"]["match_id"] == r.json()["match_id"]


# ---------- lances (RF-013 / CA-013) ----------

def test_lance_e_aplicado_e_difundido_aos_dois(client: TestClient, mailer: MemoryMailer,
                                               db: Session) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    with abrir(a) as wa, abrir(b) as wb:
        snap_a = entrar(wa, mid)[-1]["payload"]
        entrar(wb, mid)
        assert snap_a["legal_moves"] == [str(i) for i in range(9)] and snap_a["your_seat"] == 1
        req = mover(wa, mid, "4", 0)
        resposta = ate(wa, "move_applied", reply_to=req)
        difundido = ate(wb, "move_applied")
        for msg in (resposta, difundido):
            assert msg["seq"] == 1
            assert msg["payload"]["ply"] == 1 and msg["payload"]["seat"] == 1
            assert msg["payload"]["move"] == "4" and msg["payload"]["next_seat"] == 2
            assert msg["payload"]["state"]["board"] == "____X____"
            assert msg["payload"]["legal_moves"] == [str(i) for i in range(9) if i != 4]
        assert "reply_to" not in difundido
        oficial = db.execute(select(Match.state)).scalar_one()
        assert state_hash(difundido["payload"]["state"]) == state_hash(oficial)


def test_erros_de_lance_pelo_ws(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    with abrir(a) as wa, abrir(b) as wb:
        entrar(wa, mid)
        entrar(wb, mid)
        fora = mover(wb, mid, "0", 0)
        assert ate(wb, "error", reply_to=fora)["payload"]["code"] == "not_your_turn"
        velho = mover(wa, mid, "0", 7)
        erro = ate(wa, "error", reply_to=velho)["payload"]
        assert erro["code"] == "stale_state" and erro["current_ply"] == 0
        ilegal = mover(wa, mid, "9", 0)
        assert ate(wa, "error", reply_to=ilegal)["payload"]["code"] == "illegal_move"
        mover(wa, mid, "0", 0)
        ate(wb, "move_applied")
        ocupada = mover(wb, mid, "0", 1)
        assert ate(wb, "error", reply_to=ocupada)["payload"]["code"] == "illegal_move"
    assert a.get(f"{API}/matches/{mid}").json()["ply"] == 1


def test_reenvio_do_mesmo_client_move_id_nao_duplica(client: TestClient, mailer: MemoryMailer,
                                                     db: Session) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    cid = str(uuid.uuid4())
    with abrir(a) as wa:
        entrar(wa, mid)
        primeira = mover(wa, mid, "4", 0, cid)
        assert "duplicate" not in ate(wa, "move_applied", reply_to=primeira)["payload"]
        segunda = mover(wa, mid, "4", 0, cid)
        repetida = ate(wa, "move_applied", reply_to=segunda)
        assert repetida["payload"]["duplicate"] is True and repetida["payload"]["ply"] == 1
    assert db.scalar(select(MatchMove.ply).where(MatchMove.client_move_id == uuid.UUID(cid))) == 0
    assert db.execute(text("SELECT count(*) FROM match_moves")).scalar_one() == 1


def test_partida_online_termina_e_avisa_os_dois(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    with abrir(a) as wa, abrir(b) as wb:
        entrar(wa, mid)
        entrar(wb, mid)
        for autor, mv, ply in ((wa, "0", 0), (wb, "3", 1), (wa, "1", 2), (wb, "4", 3),
                               (wa, "2", 4)):
            req = mover(autor, mid, mv, ply)
            ate(autor, "move_applied", reply_to=req)
        for w in (wa, wb):
            fim = ate(w, "match_ended")
            assert fim["payload"]["result"] == "p1_win" and fim["payload"]["end_reason"] == "normal"
        tarde = mover(wb, mid, "5", 5)
        assert ate(wb, "error", reply_to=tarde)["payload"]["code"] == "match_finished"


def test_lance_por_rest_chega_ao_oponente_conectado(client: TestClient,
                                                    mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    with abrir(b) as wb:
        entrar(wb, mid)
        assert lance(a, mid, "4", 0).status_code == 200
        msg = ate(wb, "move_applied")
        assert msg["payload"]["move"] == "4" and msg["payload"]["next_seat"] == 2


# ---------- desistência e empate (RF-015) ----------

def test_desistencia_pelo_ws(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, seat=1)["id"]
    with abrir(a) as wa, abrir(b) as wb:
        entrar(wa, mid)
        entrar(wb, mid)
        req = enviar(wb, "resign", {"match_id": mid})
        proprio = ate(wb, "match_ended", reply_to=req)
        outro = ate(wa, "match_ended")
        for msg in (proprio, outro):
            assert msg["payload"]["result"] == "p1_win" and msg["payload"]["end_reason"] == "resign"
    assert b.get(f"{API}/matches/{mid}").json()["status"] == "finished"


def test_desistencia_por_rest_avisa_quem_esta_conectado(client: TestClient,
                                                        mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    with abrir(a) as wa:
        entrar(wa, mid)
        assert b.post(f"{API}/matches/{mid}/resign", headers=csrf(b)).status_code == 200
        assert ate(wa, "match_ended")["payload"]["end_reason"] == "resign"


def test_empate_por_acordo_pelo_ws(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess")["id"]
    with abrir(a) as wa, abrir(b) as wb:
        entrar(wa, mid)
        entrar(wb, mid)
        req = enviar(wa, "offer_draw", {"match_id": mid})
        assert ate(wa, "draw_offered", reply_to=req)["payload"]["by_seat"] == 1
        assert ate(wb, "draw_offered")["payload"] == {"match_id": mid, "by_seat": 1}
        resp = enviar(wb, "respond_draw", {"match_id": mid, "accept": True})
        fim = ate(wb, "match_ended", reply_to=resp)
        assert fim["payload"]["result"] == "draw" and fim["payload"]["end_reason"] == "agreement"
        assert ate(wa, "match_ended")["payload"]["end_reason"] == "agreement"


def test_empate_recusado_e_proposta_repetida_pelo_ws(client: TestClient,
                                                     mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess")["id"]
    with abrir(a) as wa, abrir(b) as wb:
        entrar(wa, mid)
        entrar(wb, mid)
        enviar(wa, "offer_draw", {"match_id": mid})
        ate(wb, "draw_offered")
        enviar(wb, "respond_draw", {"match_id": mid, "accept": False})
        recusa = ate(wa, "draw_declined")
        assert recusa["payload"]["by_seat"] == 2 and recusa["payload"]["reason"] == "declined"
        de_novo = enviar(wa, "offer_draw", {"match_id": mid})
        erro = ate(wa, "error", reply_to=de_novo)["payload"]
        assert erro["code"] == "draw_offer_limited" and erro["status"] == 429


def test_lance_do_destinatario_recusa_a_proposta_e_avisa(client: TestClient,
                                                         mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess")["id"]
    with abrir(a) as wa, abrir(b) as wb:
        entrar(wa, mid)
        entrar(wb, mid)
        enviar(wa, "offer_draw", {"match_id": mid})
        ate(wb, "draw_offered")
        mover(wa, mid, "e2e4", 0)
        ate(wb, "move_applied")
        mover(wb, mid, "e7e5", 1)
        recusa = ate(wa, "draw_declined")
        assert recusa["payload"]["reason"] == "moved" and recusa["payload"]["by_seat"] == 2


# ---------- presença, reconexão e abandono (RF-014 / CA-014) ----------

def test_oponente_e_avisado_de_desconexao_e_reconexao(client: TestClient,
                                                      mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, seat=1)["id"]
    with abrir(b) as wb:
        entrar(wb, mid)
        with abrir(a) as wa:
            entrar(wa, mid)
            on = ate(wb, "player_connection")["payload"]
            assert on["seat"] == 1 and on["connected"] is True and on["grace_deadline"] is None
        off = ate(wb, "player_connection")["payload"]
        assert off["seat"] == 1 and off["connected"] is False and off["grace_deadline"]
        visao = b.get(f"{API}/matches/{mid}").json()
        presenca = {p["seat"]: p["connected"] for p in visao["players"]}
        assert presenca == {1: False, 2: True}
        with abrir(a) as wa2:
            entrar(wa2, mid)
            assert ate(wb, "player_connection")["payload"]["connected"] is True


def test_reconexao_recebe_lances_perdidos_e_estado_identico_ao_do_servidor(
        client: TestClient, mailer: MemoryMailer, db: Session) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, seat=1)["id"]
    with abrir(a) as wa, abrir(b) as wb:
        entrar(wa, mid)
        entrar(wb, mid)
        req = mover(wa, mid, "0", 0)
        ate(wa, "move_applied", reply_to=req)
        ate(wb, "move_applied")
        req = mover(wb, mid, "4", 1)
        ate(wb, "move_applied", reply_to=req)
    # A conexão de `a` caiu depois do lance 1 (ply conhecido = 1); o jogo seguiu sem ela.
    assert lance(a, mid, "1", 2).status_code == 200
    with abrir(b) as wb2:
        entrar(wb2, mid, last=3)
        req = mover(wb2, mid, "3", 3)
        ate(wb2, "move_applied", reply_to=req)
    with abrir(a) as wa2:
        vistas = entrar(wa2, mid, last=1)
        perdidos = next(m for m in vistas if m["type"] == "moves_since")["payload"]
        assert [(m["ply"], m["seat"], m["move"]) for m in perdidos["moves"]] == [
            (1, 2, "4"), (2, 1, "1"), (3, 2, "3")]
        snap = vistas[-1]["payload"]
        assert snap["ply"] == 4 and snap["your_seat"] == 1 and snap["to_move_seat"] == 1
        oficial = db.execute(select(Match.state)).scalar_one()
        assert state_hash(snap["state"]) == state_hash(oficial)


def test_acima_de_20_lances_perdidos_vem_so_o_snapshot(client: TestClient,
                                                       mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess")["id"]
    view = jogar_aleatorio(a, b, mid, ate_ply=22)
    assert view["status"] == "in_progress"
    with abrir(a) as w:
        vistas = entrar(w, mid, last=0)
        assert [m["type"] for m in vistas] == ["match_snapshot"]  # 22 > 20: sem lista de lances
        assert vistas[0]["payload"]["ply"] == view["ply"]
        vistas = entrar(w, mid, last=view["ply"] - 5)
        perdidos = next(m for m in vistas if m["type"] == "moves_since")["payload"]["moves"]
        assert len(perdidos) == 5
        vistas = entrar(w, mid, last=view["ply"])  # em dia: só o snapshot
        assert [m["type"] for m in vistas] == ["match_snapshot"]


def test_snapshot_traz_proposta_de_empate_em_aberto(client: TestClient,
                                                    mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "checkers")["id"]
    a.post(f"{API}/matches/{mid}/draw-offer", headers=csrf(a))
    with abrir(b) as wb:
        snap = entrar(wb, mid)[-1]["payload"]
        assert snap["draw_offer_by_seat"] == 1 and snap["your_seat"] == 2


def test_abandono_pelo_ws_apos_a_tolerancia(client: TestClient, mailer: MemoryMailer,
                                            fake_clock: FakeClock) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, seat=1)["id"]
    with abrir(b) as wb:
        entrar(wb, mid)
        antes = enviar(wb, "claim_abandon", {"match_id": mid})
        assert ate(wb, "error", reply_to=antes)["payload"]["code"] == "too_early"
        fake_clock.advance(seconds=61)  # a (na vez) nunca conectou
        req = enviar(wb, "claim_abandon", {"match_id": mid})
        fim = ate(wb, "match_ended", reply_to=req)["payload"]
        assert fim["end_reason"] == "abandon" and fim["result"] == "p2_win"


def test_abandono_por_inatividade_de_quem_esta_conectado(client: TestClient, mailer: MemoryMailer,
                                                         fake_clock: FakeClock) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, seat=1)["id"]
    with abrir(a) as wa, abrir(b) as wb:
        entrar(wa, mid)
        entrar(wb, mid)
        fake_clock.advance(seconds=300)
        req = enviar(wb, "claim_abandon", {"match_id": mid})
        assert ate(wb, "error", reply_to=req)["payload"]["code"] == "too_early"
        fake_clock.advance(seconds=301)  # a está conectado, mas parado há mais de 10 minutos
        req = enviar(wb, "claim_abandon", {"match_id": mid})
        ate(wb, "match_ended", reply_to=req)
        assert ate(wa, "match_ended")["payload"]["end_reason"] == "abandon"


def test_fechar_a_ultima_aba_marca_desconexao_mas_a_segunda_aba_mantem_a_presenca(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, seat=1)["id"]
    with abrir(b) as wb:
        entrar(wb, mid)
        with abrir(a) as wa1:
            entrar(wa1, mid)
            ate(wb, "player_connection")
            with abrir(a) as wa2:
                entrar(wa2, mid)
            # Fechou só a segunda aba: a continua conectado.
            visao = b.get(f"{API}/matches/{mid}").json()
            assert {p["seat"]: p["connected"] for p in visao["players"]}[1] is True
        assert ate(wb, "player_connection")["payload"]["connected"] is False
