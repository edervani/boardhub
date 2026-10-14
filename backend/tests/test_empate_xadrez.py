"""RF-018, RF-015, RF-019 (CA-018, P-17): reivindicação de empate no xadrez (FIDE 9.2 e 9.3).

A repetição tripla e a regra dos 50 lances são reivindicadas por quem tem a vez; o servidor
confere com python-chess. Contas sintéticas (`@example.test`). As sequências são montadas pelo
próprio motor e cada teste afirma, antes de reivindicar, que a posição realmente habilita (ou
não) a reivindicação.
"""

import uuid

import chess
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.game_engines.chess import ChessEngine, State
from app.models import Match
from tests.conftest import MemoryMailer
from tests.helpers import API, conta_logada, csrf, novo_cliente
from tests.online_helpers import duas_contas, lance, partida
from tests.ranking_helpers import partida_ranqueada, post, ratings_por_conta
from tests.ws_helpers import abrir, ate, entrar, enviar, receber

E = ChessEngine()
# Cavalos de ida e volta: a cada 4 meios-lances volta a posição inicial (brancas a jogar).
CAVALOS = ["g1f3", "g8f6", "f3g1", "f6g8"]
A, B = "jogador1@example.test", "jogador2@example.test"


def cavalos(plies: int) -> list[str]:
    return [CAVALOS[i % 4] for i in range(plies)]


def estado(ucis: list[str]) -> State:
    s = E.initial_state()
    for u in ucis:
        s = E.apply(s, E.parse_move(u))
    return s


def lances_sem_progresso(n: int) -> list[str]:
    """`n` meios-lances sem captura, sem lance de peão e sem repetir posição.

    Escolha determinística: o primeiro lance legal, em ordem alfabética, que leva a uma posição
    ainda não vista.
    """
    state = E.initial_state()
    vistos = {state.board.epd()}
    out: list[str] = []
    for _ in range(n):
        for mv in sorted(E.legal_moves(state), key=lambda m: m.uci()):
            b = state.board
            if b.piece_type_at(mv.from_square) == chess.PAWN or b.is_capture(mv):
                continue
            nxt = E.apply(state, mv)
            if nxt.board.epd() in vistos:
                continue
            vistos.add(nxt.board.epd())
            state = nxt
            out.append(mv.uci())
            break
        else:
            raise AssertionError("sem lance que evite captura, peão e repetição")
    assert state.board.halfmove_clock == n
    return out


def jogar_todos(a: TestClient, b: TestClient, mid: str, ucis: list[str]) -> None:
    for i, u in enumerate(ucis):
        autor = a if i % 2 == 0 else b
        resp = lance(autor, mid, u, i)
        assert resp.status_code == 200, resp.text


def ver(c: TestClient, mid: str) -> dict[str, object]:
    return dict(c.get(f"{API}/matches/{mid}").json())


# ---------- motor: quando cabe reivindicar ----------

def test_motor_repeticao_tripla_so_cabe_a_partir_da_terceira_ocorrencia() -> None:
    for plies in range(0, 7):  # nenhuma posição ocorreu 3x nem se repetiria com um lance
        s = estado(cavalos(plies))
        assert not s.board.can_claim_draw(), plies
        assert E.claimable_draw(s) is None, plies
    # 7 meios-lances, pretas a jogar: Ng8 levaria à posição inicial pela 3ª vez (FIDE 9.2.2).
    s7 = estado(cavalos(7))
    assert s7.board.can_claim_threefold_repetition()
    assert E.claimable_draw(s7) == "repetition"
    # 8 meios-lances: a posição inicial já ocorreu 3 vezes, sem ser empate automático.
    s8 = estado(cavalos(8))
    assert s8.board.can_claim_threefold_repetition()
    assert not s8.board.is_fivefold_repetition() and E.outcome(s8) is None
    assert E.claimable_draw(s8) == "repetition"


def test_motor_quintupla_repeticao_e_automatica_e_nao_e_reivindicavel() -> None:
    s = estado(cavalos(16))
    assert s.board.is_fivefold_repetition()
    out = E.outcome(s)
    assert out is not None and out.reason == "repetition"
    assert E.claimable_draw(s) is None


@pytest.mark.parametrize(("halfmove", "esperado"), [
    (0, None), (97, None), (98, None), (99, "fifty_move"), (100, "fifty_move"), (120, "fifty_move"),
])
def test_motor_regra_dos_50_lances(halfmove: int, esperado: str | None) -> None:
    # Rei e torre de cada lado: material suficiente, sem repetição (estado sem histórico).
    board = chess.Board(f"4k3/8/8/8/8/8/8/R3K3 w - - {halfmove} 80")
    s = State((), board)
    assert board.can_claim_fifty_moves() == (esperado == "fifty_move")
    assert board.can_claim_draw() == (esperado is not None)
    assert E.claimable_draw(s) == esperado


def test_motor_75_lances_e_automatico_e_nao_e_reivindicavel() -> None:
    s = State((), chess.Board("4k3/8/8/8/8/8/8/R3K3 w - - 150 100"))
    assert s.board.is_seventyfive_moves()
    assert E.claimable_draw(s) is None


def test_motor_posicao_comum_e_partida_terminada_nao_habilitam() -> None:
    assert E.claimable_draw(E.initial_state()) is None
    mate = estado(["f2f3", "e7e5", "g2g4", "d8h4"])
    assert E.claimable_draw(mate) is None


def test_motor_sequencia_sem_progresso_longe_do_limite_nao_habilita() -> None:
    s = estado(lances_sem_progresso(97))
    assert s.board.halfmove_clock == 97 and E.claimable_draw(s) is None


# ---------- REST: repetição tripla ----------

def test_repeticao_tripla_so_quem_tem_a_vez_reivindica(client: TestClient,
                                                       mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess", seat=1)["id"]
    assert post(a, f"/matches/{mid}/claim-draw").status_code == 409  # nada a reivindicar
    assert ver(a, mid)["can_claim_draw"] is False
    seq = cavalos(8)
    assert estado(seq).board.can_claim_threefold_repetition()
    jogar_todos(a, b, mid, seq)
    va, vb = ver(a, mid), ver(b, mid)
    assert va["to_move_seat"] == 1 and va["status"] == "in_progress"
    assert va["can_claim_draw"] is True and vb["can_claim_draw"] is False
    negado = post(b, f"/matches/{mid}/claim-draw")  # sem a vez
    assert negado.status_code == 403 and negado.json()["type"] == "not_your_turn"
    assert ver(a, mid)["status"] == "in_progress"
    ok = post(a, f"/matches/{mid}/claim-draw")
    assert ok.status_code == 200, ok.text
    corpo = ok.json()
    assert corpo["status"] == "finished" and corpo["result"] == "draw"
    assert corpo["end_reason"] == "repetition"
    assert corpo["can_claim_draw"] is False and corpo["legal_moves"] == []
    assert ver(b, mid)["result"] == "draw"
    # Idempotente: repetir (por qualquer parte) devolve o mesmo resultado sem erro.
    for c in (a, b):
        again = post(c, f"/matches/{mid}/claim-draw")
        assert again.status_code == 200 and again.json()["end_reason"] == "repetition"
    assert lance(a, mid, "g1f3", 8).status_code == 409  # partida encerrada


def test_pretas_reivindicam_pela_repeticao_que_o_proximo_lance_criaria(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess", seat=1)["id"]
    jogar_todos(a, b, mid, cavalos(7))
    assert estado(cavalos(7)).board.can_claim_threefold_repetition()
    assert ver(b, mid)["to_move_seat"] == 2 and ver(b, mid)["can_claim_draw"] is True
    assert post(a, f"/matches/{mid}/claim-draw").status_code == 403
    ok = post(b, f"/matches/{mid}/claim-draw")
    assert ok.status_code == 200 and ok.json()["end_reason"] == "repetition"


def test_reivindicacao_idor_e_validacoes(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess", seat=1)["id"]
    jogar_todos(a, b, mid, cavalos(8))
    c = conta_logada(novo_cliente(client), mailer, 3)
    assert post(c, f"/matches/{mid}/claim-draw").status_code == 404
    assert post(c, f"/matches/{uuid.uuid4()}/claim-draw").status_code == 404
    anonimo = novo_cliente(client)
    assert anonimo.post(f"{API}/matches/{mid}/claim-draw").status_code in (401, 403)
    sem_csrf = a.post(f"{API}/matches/{mid}/claim-draw")
    assert sem_csrf.status_code == 403
    assert ver(a, mid)["status"] == "in_progress"  # nada mudou
    # Partida encerrada por outro motivo: não vira empate.
    assert post(a, f"/matches/{mid}/resign").status_code == 200
    r = post(a, f"/matches/{mid}/claim-draw")
    assert r.status_code == 409 and r.json()["type"] == "match_finished"


def test_outros_jogos_nao_tem_reivindicacao(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "tictactoe", seat=1)["id"]
    r = post(a, f"/matches/{mid}/claim-draw")
    assert r.status_code == 422 and r.json()["type"] == "draw_claim_not_available"
    assert ver(a, mid)["can_claim_draw"] is False


def test_partida_local_de_xadrez_tambem_reivindica(client: TestClient,
                                                   mailer: MemoryMailer) -> None:
    a = conta_logada(client, mailer)
    m = a.post(f"{API}/matches", headers=csrf(a), json={"game_id": "chess", "mode": "local"}).json()
    for i, u in enumerate(cavalos(8)):
        r = a.post(f"{API}/matches/{m['id']}/moves", headers=csrf(a), json={
            "expected_ply": i, "move": u, "client_move_id": str(uuid.uuid4())})
        assert r.status_code == 200, r.text
    assert r.json()["can_claim_draw"] is True
    ok = post(a, f"/matches/{m['id']}/claim-draw")
    assert ok.status_code == 200
    assert ok.json()["result"] == "draw" and ok.json()["end_reason"] == "repetition"
    assert ok.json()["rating_changes"] == []


# ---------- REST: regra dos 50 lances ----------

def test_cinquenta_lances_reivindicados_em_partida_online(
        client: TestClient, mailer: MemoryMailer, db: Session) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess", seat=1)["id"]
    seq = lances_sem_progresso(100)
    final = estado(seq)
    assert final.board.halfmove_clock == 100 and final.board.can_claim_fifty_moves()
    assert not final.board.can_claim_threefold_repetition()
    assert E.outcome(final) is None
    match = db.get(Match, uuid.UUID(mid))
    assert match is not None
    match.state = E.serialize(final)  # estado equivalente a 100 lances jogados (replay consistente)
    match.ply = 100
    db.commit()
    assert ver(a, mid)["can_claim_draw"] is True and ver(b, mid)["can_claim_draw"] is False
    assert post(b, f"/matches/{mid}/claim-draw").status_code == 403
    ok = post(a, f"/matches/{mid}/claim-draw")
    assert ok.status_code == 200, ok.text
    assert ok.json()["result"] == "draw" and ok.json()["end_reason"] == "fifty_move"
    assert post(a, f"/matches/{mid}/claim-draw").json()["end_reason"] == "fifty_move"


# ---------- rating ----------

def test_reivindicacao_em_partida_ranqueada_liquida_o_rating(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b, "chess")
    jogar_todos(a, b, mid, cavalos(8))
    ok = post(a, f"/matches/{mid}/claim-draw")
    assert ok.status_code == 200, ok.text
    assert ok.json()["result"] == "draw" and ok.json()["end_reason"] == "repetition"
    assert ok.json()["rating_changes"] == [{"seat": 1, "before": 1200, "after": 1200},
                                           {"seat": 2, "before": 1200, "after": 1200}]
    assert ratings_por_conta() == {A: (1200, 1), B: (1200, 1)}
    post(a, f"/matches/{mid}/claim-draw")  # idempotente: não liquida de novo
    assert ratings_por_conta() == {A: (1200, 1), B: (1200, 1)}


# ---------- WebSocket ----------

def test_ws_reivindicacao_notifica_a_outra_parte(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess", seat=1)["id"]
    with abrir(a) as wa, abrir(b) as wb:
        entrar(wa, mid)
        entrar(wb, mid)
        antes = enviar(wa, "claim_draw", {"match_id": mid})  # ainda não cabe
        erro = ate(wa, "error", reply_to=antes)
        assert erro["payload"]["code"] == "draw_not_claimable" and erro["payload"]["status"] == 409
        jogar_todos(a, b, mid, cavalos(8))
        ultimo = None
        for _ in range(40):
            msg = receber(wa)
            if msg["type"] == "move_applied" and msg["payload"]["ply"] == 8:
                ultimo = msg
                break
        assert ultimo is not None
        assert ultimo["payload"]["can_claim_draw"] is True and ultimo["payload"]["next_seat"] == 1
        fora = enviar(wb, "claim_draw", {"match_id": mid})  # sem a vez
        assert ate(wb, "error", reply_to=fora)["payload"]["code"] == "not_your_turn"
        req = enviar(wa, "claim_draw", {"match_id": mid})
        proprio = ate(wa, "match_ended", reply_to=req)
        outro = ate(wb, "match_ended")
        for msg in (proprio, outro):
            assert msg["payload"]["result"] == "draw"
            assert msg["payload"]["end_reason"] == "repetition"
        repetido = enviar(wa, "claim_draw", {"match_id": mid})
        assert ate(wa, "ack", reply_to=repetido)["payload"]["match_id"] == mid
    assert ver(b, mid)["status"] == "finished"


def test_ws_claim_draw_rejeita_campos_extras(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess", seat=1)["id"]
    with abrir(a) as wa:
        entrar(wa, mid)
        wa.send_json({"type": "claim_draw", "id": str(uuid.uuid4()),
                      "payload": {"match_id": mid, "result": "draw"}})
        assert ate(wa, "error")["payload"]["code"] == "validation_error"
