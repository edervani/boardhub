"""IA do xadrez (doc 07 §4, RNF-002): legalidade, determinismo por semente e tempo."""

import random
import time

import chess
import pytest

from app.ai.opponents.chess import (
    LEVELS,
    TABLES,
    choose_move,
    evaluate,
    move_order_key,
)
from app.game_engines.chess import ChessEngine, State

E = ChessEngine()
MATE_EM_1 = "6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1"        # Ta1-a8 é mate
DAMA_DE_GRACA = "4k3/8/8/3q4/8/8/8/3RK3 w - - 0 1"     # Txd5 ganha a dama
POUCAS_PECAS = "4k3/8/8/8/8/8/8/R3K3 w Q - 0 1"        # rei e torre contra rei: busca rápida
UM_LANCE = "k7/8/8/8/8/8/6r1/7K w - - 0 1"             # só o rei captura a torre (h1g2)


def pos(fen: str) -> State:
    return State((), chess.Board(fen))


def partida(nivel_brancas: int, nivel_pretas: int, seed: int, max_plies: int) -> State:
    rng = random.Random(seed)
    s = E.initial_state()
    for _ in range(max_plies):
        if E.outcome(s) is not None:
            break
        nivel = nivel_brancas if s.to_move == "w" else nivel_pretas
        lance = choose_move(s, nivel, rng)
        assert isinstance(lance, str)
        legais = {m.uci() for m in E.legal_moves(s)}
        assert lance in legais, f"{lance} ilegal em {s.board.fen()}"
        s = E.apply(s, E.parse_move(lance))
    return s


# ---------- legalidade ----------

def test_nivel_1_joga_partidas_inteiras_so_com_lances_legais() -> None:
    for seed in range(3):
        s = partida(1, 1, seed, 300)
        assert len(s.moves) > 0


@pytest.mark.parametrize(("brancas", "pretas"), [(2, 1), (1, 2), (2, 2)])
def test_ia_x_ia_curta_termina_sem_lance_ilegal(brancas: int, pretas: int) -> None:
    s = partida(brancas, pretas, brancas * 10 + pretas, 24)
    assert len(s.moves) == 24 or E.outcome(s) is not None


def test_nivel_3_joga_lance_legal_em_posicao_com_poucas_pecas() -> None:
    s = pos(POUCAS_PECAS)
    assert choose_move(s, 3, random.Random(0)) in {m.uci() for m in E.legal_moves(s)}


@pytest.mark.parametrize("level", [4, 5])
def test_niveis_fortes_jogam_lance_legal_e_respeitam_o_rnf_002(level: int) -> None:
    limite = LEVELS[level][1]
    assert limite is not None and limite <= 3.0
    s = E.initial_state()
    t0 = time.perf_counter()
    lance = choose_move(s, level, random.Random(0))
    assert time.perf_counter() - t0 < limite + 1.0
    assert lance in {m.uci() for m in E.legal_moves(s)}


# ---------- determinismo ----------

@pytest.mark.parametrize("level", [1, 2])
def test_semente_igual_gera_mesmo_lance_na_posicao_inicial(level: int) -> None:
    s = E.initial_state()
    assert choose_move(s, level, random.Random(9)) == choose_move(s, level, random.Random(9))


@pytest.mark.parametrize("level", [1, 2, 3])
def test_semente_igual_gera_mesmo_lance_com_poucas_pecas(level: int) -> None:
    s = pos(POUCAS_PECAS)
    assert choose_move(s, level, random.Random(5)) == choose_move(s, level, random.Random(5))


def test_nivel_1_varia_com_a_semente() -> None:
    s = E.initial_state()
    assert len({choose_move(s, 1, random.Random(seed)) for seed in range(40)}) > 3


# ---------- qualidade mínima ----------

def test_nivel_1_prefere_capturas() -> None:
    s = pos(DAMA_DE_GRACA)
    escolhas = [choose_move(s, 1, random.Random(seed)) for seed in range(200)]
    assert escolhas.count("d1d5") / len(escolhas) > 0.5


@pytest.mark.parametrize("level", [2, 3, 4, 5])
def test_acha_mate_em_um(level: int) -> None:
    assert choose_move(pos(MATE_EM_1), level, random.Random(0)) == "a1a8"


@pytest.mark.parametrize("level", [2, 3, 4])
def test_captura_dama_indefesa(level: int) -> None:
    assert choose_move(pos(DAMA_DE_GRACA), level, random.Random(0)) == "d1d5"


def test_nao_entrega_a_dama_de_graca() -> None:
    # Dama branca em d4 pode ir a d5 (capturada pelo peão c6) ou a outro lugar seguro.
    s = pos("4k3/8/2p5/8/3Q4/8/8/4K3 w - - 0 1")
    assert choose_move(s, 2, random.Random(1)) != "d4d5"


# ---------- casos de borda ----------

def test_lance_unico_e_devolvido_sem_busca() -> None:
    s = pos(UM_LANCE)
    assert [m.uci() for m in E.legal_moves(s)] == ["h1g2"]
    assert choose_move(s, 5, random.Random(0)) == "h1g2"


def test_nivel_ou_posicao_invalidos() -> None:
    with pytest.raises(ValueError):
        choose_move(E.initial_state(), 6, random.Random(0))
    with pytest.raises(ValueError):
        choose_move(E.initial_state(), 0, random.Random(0))
    mate = pos("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
    with pytest.raises(ValueError):
        choose_move(mate, 3, random.Random(0))


def test_nao_altera_o_estado_recebido() -> None:
    s = E.initial_state()
    antes = (s.board.fen(), len(s.board.move_stack), s.moves)
    choose_move(s, 2, random.Random(3))
    assert (s.board.fen(), len(s.board.move_stack), s.moves) == antes


# ---------- avaliação e ordenação ----------

def test_tabelas_tem_64_casas() -> None:
    assert all(len(t) == 64 for t in TABLES.values())


def test_avaliacao_inicial_e_simetrica() -> None:
    assert evaluate(chess.Board()) == 0


def test_avaliacao_e_do_ponto_de_vista_de_quem_joga() -> None:
    com_dama_a_mais = chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")
    assert evaluate(com_dama_a_mais) > 800
    com_dama_a_mais.turn = chess.BLACK
    assert evaluate(com_dama_a_mais) < -800


def test_avaliacao_e_espelhada_entre_as_cores() -> None:
    branca = chess.Board("4k3/8/8/8/8/2N5/8/4K3 w - - 0 1")
    preta = chess.Board("4k3/8/2n5/8/8/8/8/4K3 b - - 0 1")
    assert evaluate(branca) == evaluate(preta)


def test_ordenacao_mvv_lva() -> None:
    b = chess.Board("4k3/8/8/3q1p2/4P3/8/8/3QK3 w - - 0 1")
    peao_x_dama = move_order_key(b, chess.Move.from_uci("e4d5"))
    dama_x_dama = move_order_key(b, chess.Move.from_uci("d1d5"))
    peao_x_peao = move_order_key(b, chess.Move.from_uci("e4f5"))
    quieto = move_order_key(b, chess.Move.from_uci("d1d2"))
    assert peao_x_dama > dama_x_dama > peao_x_peao > quieto == 0


def test_ordenacao_aceita_en_passant_e_promocao() -> None:
    ep = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    assert move_order_key(ep, chess.Move.from_uci("e5d6")) > 0
    promo = chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert move_order_key(promo, chess.Move.from_uci("a7a8q")) > move_order_key(
        promo, chess.Move.from_uci("a7a8n")) > 0
