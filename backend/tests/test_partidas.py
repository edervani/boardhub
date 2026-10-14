"""RF-009, RF-010, RF-013, RF-015, RF-020 (CA-009, CA-010, CA-013, CA-015, CA-020) e T-122."""

import random
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.game_engines.base import state_hash
from app.game_engines.tictactoe import TicTacToeEngine
from app.models import Match, MatchMove
from tests.conftest import MemoryMailer
from tests.helpers import API, conta_logada, csrf, novo_cliente

E = TicTacToeEngine()


def criar(c: TestClient, **kw: object) -> dict[str, Any]:
    body: dict[str, object] = {"game_id": "tictactoe", "mode": "ai", "ai_level": 3}
    body.update(kw)
    resp = c.post(f"{API}/matches", headers=csrf(c), json=body)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


def jogar(c: TestClient, match: dict[str, Any], move: str, *, ply: int | None = None,
          cid: str | None = None) -> Response:
    return c.post(f"{API}/matches/{match['id']}/moves", headers=csrf(c), json={
        "expected_ply": match["ply"] if ply is None else ply, "move": move,
        "client_move_id": cid or str(uuid.uuid4())})


@pytest.fixture
def jogador(client: TestClient, mailer: MemoryMailer) -> TestClient:
    return conta_logada(client, mailer)


# ---------- criação ----------

def test_partida_contra_ia_comeca_com_estado_inicial(jogador: TestClient) -> None:
    m = criar(jogador)
    assert m["status"] == "in_progress"
    assert m["ply"] == 0
    assert m["legal_moves"] == [str(i) for i in range(9)]
    assert m["seats"] == [{"seat": 1, "is_ai": False, "is_you": True},
                          {"seat": 2, "is_ai": True, "is_you": False}]
    assert m["to_move_seat"] == 1


def test_ia_joga_primeiro_quando_o_usuario_escolhe_o_assento_2(jogador: TestClient) -> None:
    m = criar(jogador, preferred_seat=2)
    assert m["ply"] == 1
    assert m["to_move_seat"] == 2
    assert m["seats"][1]["is_you"] is True
    assert len(jogador.get(f"{API}/matches/{m['id']}/moves").json()) == 1


@pytest.mark.parametrize("extra", [
    {"mode": "ai", "ai_level": None},
    {"mode": "ai", "ai_level": 6},
    {"mode": "local", "ai_level": 3},
    {"mode": "online_ranked"},
    {"game_id": "go"},
    {"game_id": "chess"},   # sem motor implementado
    {"user_id": "x"},
])
def test_criacao_invalida_e_recusada(jogador: TestClient, extra: dict[str, object]) -> None:
    body: dict[str, object] = {"game_id": "tictactoe", "mode": "ai", "ai_level": 3, **extra}
    resp = jogador.post(f"{API}/matches", headers=csrf(jogador), json=body)
    assert resp.status_code in (404, 422)


def test_jogo_desabilitado_nao_cria_partida(jogador: TestClient) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE games SET enabled = false"))
    try:
        resp = jogador.post(f"{API}/matches", headers=csrf(jogador),
                            json={"game_id": "tictactoe", "mode": "local"})
        assert resp.status_code == 404
    finally:
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE games SET enabled = (id IN ('tictactoe', 'checkers'))"))


def test_limite_de_20_partidas_por_hora(jogador: TestClient) -> None:
    for _ in range(20):
        criar(jogador, mode="local", ai_level=None)
    resp = jogador.post(f"{API}/matches", headers=csrf(jogador),
                        json={"game_id": "tictactoe", "mode": "local"})
    assert resp.status_code == 429


def test_exige_autenticacao_e_csrf(client: TestClient, jogador: TestClient) -> None:
    anon = novo_cliente(client)
    assert anon.post(f"{API}/matches", json={"game_id": "tictactoe", "mode": "local"}
                     ).status_code in (401, 403)
    assert jogador.post(f"{API}/matches", json={"game_id": "tictactoe", "mode": "local"}
                        ).status_code == 403


# ---------- lances ----------

def test_lance_valido_avanca_e_a_ia_responde(jogador: TestClient) -> None:
    m = criar(jogador)
    resp = jogar(jogador, m, "4")
    assert resp.status_code == 200
    novo = resp.json()
    assert novo["ply"] == 2
    assert novo["state"]["board"].count("_") == 7
    assert "4" not in novo["legal_moves"]


@pytest.mark.parametrize("move", ["9", "-1", "x", "44", ""])
def test_lance_invalido_retorna_422_sem_alterar_a_partida(jogador: TestClient, move: str) -> None:
    m = criar(jogador)
    resp = jogar(jogador, m, move)
    assert resp.status_code == 422
    assert jogador.get(f"{API}/matches/{m['id']}").json()["ply"] == 0


def test_casa_ocupada_retorna_illegal_move(jogador: TestClient) -> None:
    m = criar(jogador, mode="local", ai_level=None)
    after = jogar(jogador, m, "4").json()
    resp = jogar(jogador, after, "4")
    assert resp.status_code == 422
    assert resp.json()["type"] == "illegal_move"


def test_estado_desatualizado_retorna_409(jogador: TestClient) -> None:
    m = criar(jogador)
    resp = jogar(jogador, m, "0", ply=3)
    assert resp.status_code == 409
    assert resp.json()["type"] == "stale_state"


def test_reenvio_com_o_mesmo_client_move_id_nao_duplica(jogador: TestClient,
                                                        db: Session) -> None:
    m = criar(jogador)
    cid = str(uuid.uuid4())
    a = jogar(jogador, m, "4", cid=cid)
    b = jogar(jogador, m, "4", cid=cid)
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert db.scalar(select(MatchMove.ply).where(MatchMove.client_move_id == uuid.UUID(cid))) == 0
    assert len(jogador.get(f"{API}/matches/{m['id']}/moves").json()) == 2  # seu lance + IA


def test_cliente_nao_informa_resultado_nem_estado(jogador: TestClient) -> None:
    m = criar(jogador)
    resp = jogador.post(f"{API}/matches/{m['id']}/moves", headers=csrf(jogador), json={
        "expected_ply": 0, "move": "4", "client_move_id": str(uuid.uuid4()),
        "result": "p1_win", "state": {"board": "XXX______"}})
    assert resp.status_code == 422


def test_partida_local_alterna_os_assentos_e_x_vence(jogador: TestClient) -> None:
    m = criar(jogador, mode="local", ai_level=None)
    for mv in ("0", "3", "1", "4"):
        m = jogar(jogador, m, mv).json()
    assert m["status"] == "in_progress"
    m = jogar(jogador, m, "2").json()
    assert (m["status"], m["result"], m["end_reason"]) == ("finished", "p1_win", "normal")
    assert m["legal_moves"] == [] and m["to_move_seat"] is None
    assert jogar(jogador, m, "5", ply=5).status_code == 409


def test_empate_em_partida_local(jogador: TestClient) -> None:
    m = criar(jogador, mode="local", ai_level=None)
    for mv in ("0", "1", "2", "4", "3", "5", "7", "6", "8"):
        m = jogar(jogador, m, mv).json()
    assert (m["status"], m["result"]) == ("finished", "draw")


def test_ia_nivel_5_nunca_perde_para_jogador_aleatorio(jogador: TestClient) -> None:
    rng = random.Random(11)
    for i in range(15):
        m = criar(jogador, ai_level=5, preferred_seat=1 + i % 2)
        while m["status"] == "in_progress":
            lance = rng.choice(m["legal_moves"])
            m = jogar(jogador, m, lance).json()
        meu = next(s["seat"] for s in m["seats"] if s["is_you"])
        assert m["result"] in ("draw", "p2_win" if meu == 1 else "p1_win")


def test_desistir_encerra_com_vitoria_da_ia(jogador: TestClient) -> None:
    m = criar(jogador)
    resp = jogador.post(f"{API}/matches/{m['id']}/resign", headers=csrf(jogador))
    assert resp.status_code == 200
    assert (resp.json()["result"], resp.json()["end_reason"]) == ("p2_win", "resign")
    again = jogador.post(f"{API}/matches/{m['id']}/resign", headers=csrf(jogador))
    assert again.status_code == 409


def test_estado_corrompido_aborta_a_partida(jogador: TestClient, db: Session) -> None:
    m = criar(jogador)
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE matches SET state = '{\"board\": \"XXXXXXXXX\"}'::jsonb"))
    resp = jogar(jogador, m, "0")
    assert resp.status_code == 409
    assert resp.json()["type"] == "match_aborted"
    row = db.execute(text("SELECT status FROM matches")).scalar_one()
    assert row == "aborted"


# ---------- autorização (SEC-05 / IDOR) ----------

def test_outro_usuario_nao_ve_nem_joga_nem_desiste(client: TestClient,
                                                   mailer: MemoryMailer) -> None:
    dono = conta_logada(client, mailer, 1)
    m = criar(dono)
    intruso = conta_logada(novo_cliente(client), mailer, 2)
    assert intruso.get(f"{API}/matches/{m['id']}").status_code == 404
    assert intruso.get(f"{API}/matches/{m['id']}/moves").status_code == 404
    assert jogar(intruso, m, "0").status_code == 404
    assert intruso.post(f"{API}/matches/{m['id']}/resign",
                        headers=csrf(intruso)).status_code == 404
    assert intruso.get(f"{API}/matches/{uuid.uuid4()}").status_code == 404
    assert dono.get(f"{API}/matches/{m['id']}").json()["ply"] == 0


# ---------- replay (T-122) ----------

def test_replay_dos_lances_reproduz_o_estado_e_os_hashes(jogador: TestClient,
                                                         db: Session) -> None:
    m = criar(jogador, ai_level=2)
    while m["status"] == "in_progress":
        m = jogar(jogador, m, m["legal_moves"][0]).json()
    match = db.scalar(select(Match))
    assert match is not None
    state = E.initial_state()
    moves = db.scalars(select(MatchMove).where(MatchMove.match_id == match.id)
                       .order_by(MatchMove.ply)).all()
    assert [mv.ply for mv in moves] == list(range(len(moves)))
    for mv in moves:
        state = E.apply(state, E.parse_move(mv.move))
        assert mv.state_after_hash.hex() == state_hash(E.serialize(state))
    assert E.serialize(state) == match.state
    assert match.ply == len(moves)


# ---------- histórico (CA-020) ----------

def test_historico_paginado_por_cursor(jogador: TestClient) -> None:
    ids = [criar(jogador, mode="local", ai_level=None)["id"] for _ in range(3)]
    p1 = jogador.get(f"{API}/me/matches?limit=2").json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = jogador.get(f"{API}/me/matches?limit=2&cursor={p1['next_cursor']}").json()
    assert len(p2["items"]) == 1 and p2["next_cursor"] is None
    vistos = [i["id"] for i in p1["items"] + p2["items"]]
    assert sorted(vistos) == sorted(ids) and len(set(vistos)) == 3


def test_historico_filtra_e_isola_usuarios(client: TestClient, mailer: MemoryMailer) -> None:
    a = conta_logada(client, mailer, 1)
    b = conta_logada(novo_cliente(client), mailer, 2)
    criar(a, mode="local", ai_level=None)
    criar(a)
    assert len(a.get(f"{API}/me/matches").json()["items"]) == 2
    assert len(a.get(f"{API}/me/matches?mode=ai").json()["items"]) == 1
    assert len(a.get(f"{API}/me/matches?game_id=chess").json()["items"]) == 0
    assert b.get(f"{API}/me/matches").json()["items"] == []


@pytest.mark.parametrize("cursor", ["!!!", "YWJj", "Zm9vfGJhcg"])
def test_cursor_invalido_retorna_422(jogador: TestClient, cursor: str) -> None:
    assert jogador.get(f"{API}/me/matches?cursor={cursor}").status_code == 422


def test_limite_acima_de_100_e_recusado(jogador: TestClient) -> None:
    assert jogador.get(f"{API}/me/matches?limit=101").status_code == 422


def test_moves_since_ply(jogador: TestClient) -> None:
    m = criar(jogador)
    jogar(jogador, m, "4")
    todos = jogador.get(f"{API}/matches/{m['id']}/moves").json()
    assert [x["ply"] for x in todos] == [0, 1]
    assert [x["ply"] for x in jogador.get(f"{API}/matches/{m['id']}/moves?since_ply=1").json()
            ] == [1]


# ---------- motor sem estado (visitante, DT-007) ----------

def test_visitante_valida_lance_sem_conta_nem_persistencia(client: TestClient,
                                                           db: Session) -> None:
    estado = E.serialize(E.initial_state())
    resp = client.post(f"{API}/engines/tictactoe/apply", json={"state": estado, "move": "4"})
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["state"]["board"] == "____X____" and corpo["outcome"] is None
    assert db.scalar(select(Match.id)) is None


def test_motor_sem_estado_informa_o_resultado(client: TestClient) -> None:
    estado = {"schema_version": 1, "board": "XX_OO____", "to_move": "X"}
    corpo = client.post(f"{API}/engines/tictactoe/apply", json={"state": estado, "move": "2"}
                        ).json()
    assert corpo["outcome"] == {"winner": "X", "reason": "line"}
    assert corpo["legal_moves"] == []


@pytest.mark.parametrize(("estado", "move", "esperado"), [
    ({"schema_version": 1, "board": "X________", "to_move": "O"}, "0", "illegal_move"),
    ({"schema_version": 1, "board": "XXXXXXXXX", "to_move": "O"}, "0", "invalid_state"),
    ({"x": "y" * 9000}, "0", "state_too_large"),
])
def test_motor_sem_estado_recusa_entradas_ruins(client: TestClient, estado: dict[str, str],
                                                move: str, esperado: str) -> None:
    resp = client.post(f"{API}/engines/tictactoe/apply", json={"state": estado, "move": move})
    assert resp.status_code == 422
    assert resp.json()["type"] == esperado


def test_motor_sem_estado_jogo_inexistente(client: TestClient) -> None:
    resp = client.post(f"{API}/engines/go/apply", json={"state": {}, "move": "0"})
    assert resp.status_code == 404


def test_motor_sem_estado_tem_limite_de_taxa(client: TestClient) -> None:
    estado = E.serialize(E.initial_state())
    codigos = {client.post(f"{API}/engines/tictactoe/apply",
                           json={"state": estado, "move": "4"}).status_code for _ in range(125)}
    assert 429 in codigos


# ---------- damas ----------

def test_damas_contra_ia_comeca_com_lances_legais_do_motor(jogador: TestClient) -> None:
    from app.game_engines.checkers import CheckersEngine

    eng = CheckersEngine()
    m = criar(jogador, game_id="checkers", ai_level=2)
    esperado = sorted(str(x) for x in eng.legal_moves(eng.initial_state()))
    assert m["ply"] == 0
    assert sorted(m["legal_moves"]) == esperado
    assert len(esperado) == 7


def test_damas_lance_ilegal_e_recusado_e_legal_avanca(jogador: TestClient) -> None:
    m = criar(jogador, game_id="checkers", ai_level=1)
    assert jogar(jogador, m, "1-5").status_code in (409, 422)
    lance = m["legal_moves"][0]
    resp = jogar(jogador, m, lance)
    assert resp.status_code == 200, resp.text
    assert resp.json()["ply"] == 2


def test_damas_partida_local_aleatoria_mantem_replay_consistente(
        jogador: TestClient, db: Session) -> None:
    from app.game_engines.checkers import CheckersEngine

    rng = random.Random(7)
    m = criar(jogador, game_id="checkers", mode="local", ai_level=None)
    for _ in range(80):
        if m["status"] != "in_progress":
            break
        resp = jogar(jogador, m, rng.choice(m["legal_moves"]))
        assert resp.status_code == 200, resp.text
        m = resp.json()
    eng = CheckersEngine()
    moves = db.scalars(select(MatchMove).where(MatchMove.match_id == uuid.UUID(m["id"]))
                       .order_by(MatchMove.ply)).all()
    state = eng.initial_state()
    for mv in moves:
        state = eng.apply(state, eng.parse_move(mv.move))
        assert mv.state_after_hash.hex() == state_hash(eng.serialize(state))
