"""RF-016 / CA-016 — motor do jogo da velha (T-016)."""

import itertools
import json
import random

import pytest

from app.game_engines.base import IllegalMove, InvalidState, Outcome, state_hash
from app.game_engines.tictactoe import LINES, State, TicTacToeEngine, winner_of

E = TicTacToeEngine()


def _reachable() -> dict[State, None]:
    seen: dict[State, None] = {E.initial_state(): None}
    frontier = [E.initial_state()]
    while frontier:
        nxt = []
        for s in frontier:
            for m in E.legal_moves(s):
                t = E.apply(s, m)
                if t not in seen:
                    seen[t] = None
                    nxt.append(t)
        frontier = nxt
    return seen


REACHABLE = _reachable()


def test_numero_de_posicoes_alcancaveis_e_5478() -> None:
    assert len(REACHABLE) == 5478


@pytest.mark.parametrize("line", LINES)
def test_todas_as_oito_linhas_sao_detectadas(line: tuple[int, int, int]) -> None:
    for player in "XO":
        board = ["_"] * 9
        for i in line:
            board[i] = player
        assert winner_of("".join(board)) == player


def test_empate_em_tabuleiro_cheio() -> None:
    s = State("XOXXOOOXX", "O")
    assert E.outcome(s) == Outcome(None, "draw")
    assert E.legal_moves(s) == []


def test_jogada_em_casa_ocupada_e_rejeitada() -> None:
    s = E.apply(E.initial_state(), 4)
    with pytest.raises(IllegalMove):
        E.apply(s, 4)


@pytest.mark.parametrize("move", [-1, 9, 100])
def test_jogada_fora_do_tabuleiro_e_rejeitada(move: int) -> None:
    with pytest.raises(IllegalMove):
        E.apply(E.initial_state(), move)


def test_nao_se_joga_apos_o_fim() -> None:
    s = State("XXXOO____", "O")
    assert E.outcome(s) == Outcome("X", "line")
    with pytest.raises(IllegalMove):
        E.apply(s, 8)


def test_x_comeca_e_as_vezes_alternam() -> None:
    s = E.initial_state()
    assert s.to_move == "X"
    assert E.apply(s, 0).to_move == "O"


def test_invariantes_em_todas_as_posicoes_alcancaveis() -> None:
    for s in REACHABLE:
        x, o = s.board.count("X"), s.board.count("O")
        assert x - o in (0, 1)
        assert s.to_move == ("O" if x > o else "X")
        assert E.deserialize(E.serialize(s)) == s
        assert (E.legal_moves(s) == []) == (E.outcome(s) is not None)


def test_apply_nao_altera_o_estado_original() -> None:
    s = E.initial_state()
    E.apply(s, 0)
    assert s == E.initial_state()


@pytest.mark.parametrize("raw", ["", "9", "-1", "ab", "10", " 1", "1\n", "٣"])
def test_parse_move_recusa_texto_invalido(raw: str) -> None:
    with pytest.raises(IllegalMove):
        E.parse_move(raw)


def test_parse_move_aceita_digitos() -> None:
    assert [E.parse_move(str(i)) for i in range(9)] == list(range(9))


@pytest.mark.parametrize("data", [
    {},
    {"schema_version": 2, "board": "_________", "to_move": "X"},
    {"schema_version": 1, "board": "________", "to_move": "X"},
    {"schema_version": 1, "board": "_________", "to_move": "O"},
    {"schema_version": 1, "board": "XX_______", "to_move": "O"},
    {"schema_version": 1, "board": "XXXOO____", "to_move": "X"},  # X venceu mas é vez de X
    {"schema_version": 1, "board": "OOOXX_X__", "to_move": "O"},  # O venceu e X tem mais peças
    {"schema_version": 1, "board": "XZ_______", "to_move": "O"},
    {"schema_version": 1, "board": 123, "to_move": "X"},
])
def test_estado_inconsistente_e_recusado(data: dict[str, object]) -> None:
    with pytest.raises(InvalidState):
        E.deserialize(data)


def test_hash_do_estado_e_canonico() -> None:
    a = {"schema_version": 1, "board": "_________", "to_move": "X"}
    b = dict(reversed(list(a.items())))
    assert state_hash(a) == state_hash(b)
    assert state_hash(a) != state_hash({**a, "to_move": "O"})
    assert json.loads(json.dumps(E.serialize(E.initial_state()))) == a


def test_partidas_aleatorias_sempre_terminam_com_resultado_valido() -> None:
    rng = random.Random(7)
    for _ in range(500):
        s = E.initial_state()
        while (m := E.legal_moves(s)):
            s = E.apply(s, rng.choice(m))
        out = E.outcome(s)
        assert out is not None
        assert out.winner in ("X", "O", None)
        assert 5 <= 9 - s.board.count("_") <= 9


def test_todas_as_sequencias_de_ate_4_lances_sao_legais() -> None:
    for seq in itertools.permutations(range(9), 4):
        s = E.initial_state()
        for m in seq:
            s = E.apply(s, m)
