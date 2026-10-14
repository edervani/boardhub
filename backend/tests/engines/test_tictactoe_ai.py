"""IA do jogo da velha (doc 07 §2, RNF-002): níveis 1 a 5."""

import random
import time

import pytest

from app.ai.opponents.tictactoe import LEVELS, choose_move
from app.game_engines.tictactoe import State, TicTacToeEngine

E = TicTacToeEngine()


def _play(level_x: int, level_o: int, seed: int) -> str | None:
    rng = random.Random(seed)
    s = E.initial_state()
    while E.outcome(s) is None:
        lvl = level_x if s.to_move == "X" else level_o
        s = E.apply(s, choose_move(s, lvl, rng))
    out = E.outcome(s)
    assert out is not None
    return out.winner


@pytest.mark.parametrize("level", LEVELS)
def test_ia_so_joga_lances_legais(level: int) -> None:
    rng = random.Random(level)
    for _ in range(100):
        s = E.initial_state()
        while E.outcome(s) is None:
            m = choose_move(s, level, rng)
            assert m in E.legal_moves(s)
            s = E.apply(s, m)


def test_nivel_5_nunca_perde_contra_aleatorio_em_1000_partidas() -> None:
    for seed in range(500):
        assert _play(5, 1, seed) in ("X", None)  # IA como X
        assert _play(1, 5, seed) in ("O", None)  # IA como O


def test_nivel_5_contra_si_mesmo_sempre_empata() -> None:
    assert {_play(5, 5, seed) for seed in range(20)} == {None}


def test_nivel_5_e_deterministico() -> None:
    s = E.initial_state()
    first = choose_move(s, 5, random.Random(0))
    assert {choose_move(s, 5, random.Random(i)) for i in range(20)} == {first}


def test_nivel_2_vence_quando_pode() -> None:
    s = State("XX_OO____", "X")
    assert all(choose_move(s, 2, random.Random(i)) == 2 for i in range(30))


def test_nivel_3_bloqueia_quando_nao_pode_vencer() -> None:
    s = State("XX_O_____", "O")
    assert all(choose_move(s, 3, random.Random(i)) == 2 for i in range(30))


def test_nivel_2_nao_bloqueia_sempre() -> None:
    s = State("XX_O_____", "O")
    assert len({choose_move(s, 2, random.Random(i)) for i in range(200)}) > 1


def test_nivel_4_erra_em_cerca_de_25_por_cento() -> None:
    s = State("OO_X_X___", "X")  # X vence em 4; os demais lances são piores
    best = choose_move(s, 5, random.Random(0))
    rng = random.Random(1)
    errors = sum(choose_move(s, 4, rng) != best for _ in range(2000))
    assert 0.18 < errors / 2000 < 0.32


def test_mesma_semente_gera_mesmo_lance() -> None:
    s = E.initial_state()
    for lvl in LEVELS:
        assert choose_move(s, lvl, random.Random(42)) == choose_move(s, lvl, random.Random(42))


def test_nivel_ou_partida_invalidos() -> None:
    with pytest.raises(ValueError):
        choose_move(E.initial_state(), 6, random.Random(0))
    with pytest.raises(ValueError):
        choose_move(State("XXXOO____", "O"), 5, random.Random(0))


def test_tempo_de_resposta_dentro_do_rnf_002() -> None:
    rng = random.Random(0)
    worst = 0.0
    for lvl in LEVELS:
        s = E.initial_state()
        t0 = time.perf_counter()
        choose_move(s, lvl, rng)
        worst = max(worst, time.perf_counter() - t0)
    # RNF-002: níveis 1–3 ≤ 1 s, 4–5 ≤ 3 s; aqui exige-se ≤ 1 s mesmo com o cache frio.
    assert worst < 1.0
