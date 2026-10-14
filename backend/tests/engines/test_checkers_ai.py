"""IA das damas (doc 07 §3, RNF-002)."""

import random
import time

import pytest

from app.ai.opponents.checkers import LEVELS, choose_move
from app.game_engines.checkers import CheckersEngine, State, position_key

E = CheckersEngine()


def pos(w: tuple[int, ...] = (), b: tuple[int, ...] = (), kw: tuple[int, ...] = (),
        kb: tuple[int, ...] = (), to: str = "w") -> State:
    sq = ["."] * 32
    for letter, squares in (("w", w), ("b", b), ("W", kw), ("B", kb)):
        for n in squares:
            sq[n - 1] = letter
    board = tuple(sq)
    return State(board, to, 0, (position_key(board, to),))


def play_game(level_w: int, level_b: int, seed: int, max_plies: int = 300) -> str | None:
    rng = random.Random(seed)
    s = E.initial_state()
    for _ in range(max_plies):
        out = E.outcome(s)
        if out is not None:
            return out.winner
        lvl = level_w if s.to_move == "w" else level_b
        s = E.apply(s, choose_move(s, lvl, rng))
    return None


@pytest.mark.parametrize("level", [1, 2, 3])
def test_ia_so_joga_lances_legais_nas_partidas(level: int) -> None:
    rng = random.Random(level)
    for _ in range(3):
        s = E.initial_state()
        while E.outcome(s) is None:
            m = choose_move(s, level, rng)
            assert m in E.legal_moves(s)
            s = E.apply(s, m)


def test_ia_nivel_3_nao_perde_para_nivel_1() -> None:
    resultados = [play_game(3, 1, seed) for seed in range(3)]
    resultados += [play_game(1, 3, seed) for seed in range(3)]
    ia3_perdeu = resultados[:3].count("b") + resultados[3:].count("w")
    ia3_ganhou = resultados[:3].count("w") + resultados[3:].count("b")
    assert ia3_perdeu == 0
    assert ia3_ganhou >= 4


def test_lance_unico_e_devolvido_sem_busca() -> None:
    s = pos(w=(22,), b=(18, 2))
    assert str(choose_move(s, 5, random.Random(0))) == "22x15"


def test_nao_entrega_peca_de_graca_quando_ha_alternativa_melhor() -> None:
    # Branca em 22 pode ir a 17 (segura) ou 18 (capturada por 14x... ou 15x). Nível 3 vê 4 lances.
    s = pos(w=(22, 26, 30), b=(10, 11, 14))
    escolhido = str(choose_move(s, 3, random.Random(0)))
    assert escolhido in {str(m) for m in E.legal_moves(s)}


def test_semente_igual_gera_mesmo_lance_nos_niveis_fixos() -> None:
    s = E.initial_state()
    for lvl in (1, 2, 3):
        assert choose_move(s, lvl, random.Random(9)) == choose_move(s, lvl, random.Random(9))


def test_nivel_ou_partida_invalidos() -> None:
    with pytest.raises(ValueError):
        choose_move(E.initial_state(), 6, random.Random(0))
    with pytest.raises(ValueError):
        choose_move(pos(w=(22,), to="b"), 3, random.Random(0))


@pytest.mark.parametrize("level", [4, 5])
def test_tempo_de_resposta_dentro_do_rnf_002(level: int) -> None:
    limite = LEVELS[level][1]
    assert limite is not None and limite <= 3.0
    t0 = time.perf_counter()
    m = choose_move(E.initial_state(), level, random.Random(0))
    assert time.perf_counter() - t0 < limite + 0.5
    assert m in E.legal_moves(E.initial_state())
