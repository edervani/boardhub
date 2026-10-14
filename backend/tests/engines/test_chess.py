"""RF-018 / CA-018 — motor de xadrez (T-018): integração com python-chess, fim de jogo,
serialização e validação de estado."""

import copy
from collections.abc import Callable
from typing import Any

import chess
import pytest

from app.game_engines.base import IllegalMove, InvalidState, Outcome, state_hash
from app.game_engines.chess import MAX_PLIES, ChessEngine, State

E = ChessEngine()
KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"


def play(*ucis: str) -> State:
    """Joga lances UCI a partir da posição inicial, validando cada um pelo motor."""
    s = E.initial_state()
    for u in ucis:
        s = E.apply(s, E.parse_move(u))
    return s


def from_fen(fen: str) -> State:
    """Posição arbitrária só para testar o fim de jogo (não é serializável: sem lances)."""
    return State((), chess.Board(fen))


def ucis(s: State) -> set[str]:
    return {m.uci() for m in E.legal_moves(s)}


def perft(board: chess.Board, depth: int) -> int:
    if depth == 0:
        return 1
    total = 0
    for m in list(board.legal_moves):
        board.push(m)
        total += perft(board, depth - 1)
        board.pop()
    return total


def perft_engine(s: State, depth: int) -> int:
    if depth == 0:
        return 1
    return sum(perft_engine(E.apply(s, m), depth - 1) for m in E.legal_moves(s))


# ---------- posição inicial e perft ----------

def test_identificacao_do_motor() -> None:
    assert (E.game_id, E.rules_version) == ("chess", "chess-fide-1")


def test_posicao_inicial() -> None:
    s = E.initial_state()
    assert s.to_move == "w" and s.moves == ()
    assert len(ucis(s)) == 20
    assert {"e2e4", "g1f3", "b1c3"} <= ucis(s)
    assert E.outcome(s) is None


def test_perft_posicao_inicial_pelo_motor() -> None:
    s = E.initial_state()
    assert [perft_engine(s, d) for d in (1, 2)] == [20, 400]


def test_perft_posicao_inicial_ate_profundidade_3() -> None:
    board = chess.Board()
    assert [perft(board, d) for d in (1, 2, 3)] == [20, 400, 8902]


def test_perft_kiwipete() -> None:
    board = chess.Board(KIWIPETE)
    assert [perft(board, d) for d in (1, 2)] == [48, 2039]


# ---------- fim de jogo ----------

def test_mate_do_fool() -> None:
    s = play("f2f3", "e7e5", "g2g4", "d8h4")
    assert E.outcome(s) == Outcome("b", "checkmate")
    assert E.legal_moves(s) == []


def test_mate_do_pastor() -> None:
    s = play("e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7")
    assert E.outcome(s) == Outcome("w", "checkmate")


def test_nao_ha_lance_depois_do_fim() -> None:
    s = play("f2f3", "e7e5", "g2g4", "d8h4")
    with pytest.raises(IllegalMove):
        E.apply(s, E.parse_move("a2a3"))


def test_afogamento_em_10_lances() -> None:
    """Posição famosa de afogamento de Sam Loyd (10 lances)."""
    s = play("e2e3", "a7a5", "d1h5", "a8a6", "h5a5", "h7h5", "h2h4", "a6h6", "a5c7", "f7f6",
             "c7d7", "e8f7", "d7b7", "d8d3", "b7b8", "d3h7", "b8c8", "f7g6", "c8e6")
    assert E.outcome(s) == Outcome(None, "stalemate")
    assert E.legal_moves(s) == []


@pytest.mark.parametrize("fen", [
    "8/8/8/4k3/8/8/8/4K3 w - - 0 1",        # rei contra rei
    "8/8/8/4k3/8/8/8/3NK3 w - - 0 1",       # rei e cavalo contra rei
    "8/8/8/4k3/8/8/8/3BK3 w - - 0 1",       # rei e bispo contra rei
    "8/8/8/4kb2/8/8/8/3BK3 w - - 0 1",      # bispos de mesma cor
])
def test_material_insuficiente(fen: str) -> None:
    assert E.outcome(from_fen(fen)) == Outcome(None, "insufficient_material")


@pytest.mark.parametrize("fen", [
    "8/8/8/4k3/8/8/8/3RK3 w - - 0 1",       # torre
    "8/8/8/4k3/8/8/4P3/4K3 w - - 0 1",      # peão
    "8/8/8/4k3/8/8/8/2NNK3 w - - 0 1",      # dois cavalos: mate é possível em teoria
])
def test_material_suficiente_nao_encerra(fen: str) -> None:
    assert E.outcome(from_fen(fen)) is None


def test_quintupla_repeticao_e_automatica_so_na_quinta() -> None:
    ciclo = ["g1f3", "g8f6", "f3g1", "f6g8"]
    s = E.initial_state()
    for volta in range(4):
        for u in ciclo:
            assert E.outcome(s) is None, f"volta {volta}"
            s = E.apply(s, E.parse_move(u))
    assert E.outcome(s) == Outcome(None, "repetition")  # posição inicial pela 5ª vez
    assert E.legal_moves(s) == []


def test_tripla_repeticao_nao_encerra_sem_reivindicacao() -> None:
    s = E.initial_state()
    for u in ["g1f3", "g8f6", "f3g1", "f6g8"] * 2:
        s = E.apply(s, E.parse_move(u))
    assert s.board.is_repetition(3)
    assert E.outcome(s) is None


def test_75_lances_sem_captura_nem_peao_e_automatico() -> None:
    s = from_fen("8/8/8/4k3/8/8/8/R3K3 w - - 148 100")
    s = E.apply(s, E.parse_move("a1a2"))
    assert E.outcome(s) is None  # 149 meios-lances
    s = E.apply(s, E.parse_move("e5e4"))
    assert E.outcome(s) == Outcome(None, "fifty_move")  # 150 meios-lances


def test_50_lances_nao_encerra_sem_reivindicacao() -> None:
    s = from_fen("8/8/8/4k3/8/8/8/R3K3 w - - 100 80")
    assert E.outcome(s) is None


def test_mate_vale_mais_que_75_lances() -> None:
    s = from_fen("7k/5Q2/6K1/8/8/8/8/8 w - - 149 90")
    s = E.apply(s, E.parse_move("f7g7"))
    assert E.outcome(s) == Outcome("w", "checkmate")


def test_limite_de_lances_encerra_empatado() -> None:
    s = State(("e2e4",) * MAX_PLIES, chess.Board())
    assert E.outcome(s) == Outcome(None, "ply_limit")


# ---------- lances especiais ----------

def test_roque_curto_move_rei_e_torre() -> None:
    s = play("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6")
    assert "e1g1" in ucis(s)
    s = E.apply(s, E.parse_move("e1g1"))
    assert s.board.piece_at(chess.G1) == chess.Piece(chess.KING, chess.WHITE)
    assert s.board.piece_at(chess.F1) == chess.Piece(chess.ROOK, chess.WHITE)
    assert not s.board.has_castling_rights(chess.WHITE)


def test_roque_ilegal_com_pecas_no_caminho() -> None:
    assert "e1g1" not in ucis(E.initial_state())
    with pytest.raises(IllegalMove):
        E.apply(E.initial_state(), E.parse_move("e1g1"))


def test_roque_perdido_depois_de_mover_o_rei() -> None:
    s = play("e2e4", "e7e5", "e1e2", "b8c6", "e2e1", "g8f6", "g1f3", "f8c5")
    assert "e1g1" not in ucis(s)


def test_en_passant_captura_o_peao_ao_lado() -> None:
    s = play("e2e4", "a7a6", "e4e5", "d7d5")
    assert "e5d6" in ucis(s)
    s = E.apply(s, E.parse_move("e5d6"))
    assert s.board.piece_at(chess.D6) == chess.Piece(chess.PAWN, chess.WHITE)
    assert s.board.piece_at(chess.D5) is None


def test_en_passant_so_vale_no_lance_seguinte() -> None:
    s = play("e2e4", "a7a6", "e4e5", "d7d5", "b1c3", "a6a5")
    assert "e5d6" not in ucis(s)


def test_promocao_exige_a_peca_e_aceita_subpromocao() -> None:
    s = play("h2h4", "g7g5", "h4g5", "h7h6", "g5h6", "f7f6", "h6h7", "e7e6")
    legais = ucis(s)
    assert {"h7g8q", "h7g8r", "h7g8b", "h7g8n"} <= legais
    assert "h7g8" not in legais
    with pytest.raises(IllegalMove):
        E.apply(s, E.parse_move("h7g8"))
    promovido = E.apply(s, E.parse_move("h7g8n"))
    assert promovido.board.piece_at(chess.G8) == chess.Piece(chess.KNIGHT, chess.WHITE)


def test_nao_pode_deixar_o_rei_em_xeque() -> None:
    s = play("e2e3", "f7f6", "d1h5")  # xeque pela diagonal h5-e8
    assert s.board.is_check()
    assert "g7g6" in ucis(s)
    assert "a7a6" not in ucis(s)  # não resolve o xeque
    with pytest.raises(IllegalMove):
        E.apply(s, E.parse_move("a7a6"))


# ---------- texto do lance ----------

@pytest.mark.parametrize("raw", [
    "", "e2", "e2e", "e2e4q1", "E2E4", "e2-e4", "e9e4", "i2e4", "e7e8k", "e7e8Q", "0000",
    "e2e4 ", " e2e4", "e2e4\n", "ｅ2e4", "e2e4\x00", "Nf3", "O-O", "a1a1",
])
def test_texto_de_lance_invalido(raw: str) -> None:
    with pytest.raises(IllegalMove):
        E.parse_move(raw)


@pytest.mark.parametrize("raw", ["e2e4", "e7e8q", "a1h8", "h7g8n"])
def test_texto_de_lance_valido_vira_uci(raw: str) -> None:
    assert E.parse_move(raw).uci() == raw


def test_lance_bem_formado_mas_ilegal() -> None:
    with pytest.raises(IllegalMove):
        E.apply(E.initial_state(), E.parse_move("e2e5"))
    with pytest.raises(IllegalMove):
        E.apply(E.initial_state(), E.parse_move("e7e5"))  # peça do adversário


def test_apply_nao_altera_o_estado_anterior() -> None:
    s = E.initial_state()
    E.apply(s, E.parse_move("e2e4"))
    assert s.moves == () and s.board.fen() == chess.STARTING_FEN


# ---------- serialização ----------

def test_serialize_formato_e_roundtrip() -> None:
    s = play("e2e4", "e7e5", "g1f3")
    data = E.serialize(s)
    assert data["schema_version"] == 1
    assert data["moves"] == ["e2e4", "e7e5", "g1f3"]
    assert data["fen"] == s.board.fen()
    back = E.deserialize(data)
    assert back.moves == s.moves and back.board.fen() == s.board.fen()
    assert E.serialize(back) == data
    assert state_hash(E.serialize(back)) == state_hash(data)


def test_roundtrip_preserva_repeticao() -> None:
    s = E.initial_state()
    for u in ["g1f3", "g8f6", "f3g1", "f6g8"] * 4:
        s = E.apply(E.deserialize(E.serialize(s)), E.parse_move(u))
    assert E.outcome(s) == Outcome(None, "repetition")


def test_roundtrip_com_roque_en_passant_e_promocao() -> None:
    s = play("h2h4", "g7g5", "h4g5", "h7h6", "g5h6", "f7f6", "h6h7", "e7e6", "h7g8q")
    assert E.serialize(E.deserialize(E.serialize(s))) == E.serialize(s)
    s = play("e2e4", "a7a6", "e4e5", "d7d5", "e5d6")
    assert E.serialize(E.deserialize(E.serialize(s))) == E.serialize(s)


def valido() -> dict[str, Any]:
    return E.serialize(play("e2e4", "e7e5"))


def _sem(chave: str) -> Callable[[dict[str, Any]], None]:
    return lambda d: d.pop(chave)


ADULTERACOES: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
    ("sem versão", _sem("schema_version")),
    ("versão errada", lambda d: d.update(schema_version=2)),
    ("versão booleana", lambda d: d.update(schema_version=True)),
    ("sem fen", _sem("fen")),
    ("sem lances", _sem("moves")),
    ("fen não é texto", lambda d: d.update(fen=5)),
    ("fen gigante", lambda d: d.update(fen="x" * 500)),
    ("fen de outra posição", lambda d: d.update(fen=chess.STARTING_FEN)),
    ("fen com vez trocada", lambda d: d.update(fen=d["fen"].replace(" w ", " b "))),
    ("lances não é lista", lambda d: d.update(moves="e2e4e7e5")),
    ("lance não é texto", lambda d: d.update(moves=["e2e4", 5])),
    ("lance fora do formato", lambda d: d.update(moves=["e2e4", "E7E5"])),
    ("lance ilegal", lambda d: d.update(moves=["e2e4", "e7e4"])),
    ("lance fora de vez", lambda d: d.update(moves=["e2e4", "d2d4"])),
    ("lance nulo", lambda d: d.update(moves=["e2e4", "0000"])),
    ("lances demais", lambda d: d.update(moves=["g1f3", "g8f6"] * (MAX_PLIES // 2 + 1))),
    ("lance removido", lambda d: d.update(moves=["e2e4"])),
    ("lance extra", lambda d: d.update(moves=[*d["moves"], "g1f3"])),
]


@pytest.mark.parametrize(("nome", "alterar"), ADULTERACOES, ids=[n for n, _ in ADULTERACOES])
def test_estado_adulterado_e_recusado(nome: str, alterar: Callable[[dict[str, Any]], None]) -> None:
    d = copy.deepcopy(valido())
    alterar(d)
    with pytest.raises(InvalidState):
        E.deserialize(d)


def test_estado_no_limite_de_lances_e_aceito() -> None:
    """600 meios-lances válidos cabem; é o teto do tamanho do estado."""
    moves = ["g1f3", "g8f6", "f3g1", "f6g8"] * (MAX_PLIES // 4)
    ref = chess.Board()
    for m in moves:
        ref.push_uci(m)
    data = {"schema_version": 1, "fen": ref.fen(), "moves": moves}
    s = E.deserialize(data)
    assert len(s.moves) == MAX_PLIES and s.board.fen() == ref.fen()
