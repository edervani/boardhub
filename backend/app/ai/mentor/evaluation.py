"""Avaliação determinística de lances (doc 08 §1 e §7). Sem motor externo e sem aleatoriedade.

Escala (sempre do ponto de vista de quem joga; maior é melhor):
- jogo da velha: solução exata, +1000 vitória, 0 empate, -1000 derrota;
- damas: material em centésimos de pedra (pedra 100, dama 300) por busca de profundidade fixa
  com extensão de captura; vitória/derrota por ±10000 menos a profundidade;
- xadrez: material em centipeões (valores de `ai.opponents.chess`) por busca de profundidade fixa
  com quiescência de capturas; mate por ±100000 menos a profundidade.

É uma análise rasa e honesta: só afirma o que a busca calculou (material e mates dentro do
horizonte). Não é um substituto de Stockfish (doc 08, DT-005).
"""

from dataclasses import dataclass
from functools import cache
from typing import Any

import chess

from app.ai.opponents.chess import VALUE, ordered
from app.game_engines.base import IllegalMove
from app.game_engines.checkers import CheckersEngine, Move, generate, play
from app.game_engines.chess import ChessEngine
from app.game_engines.tictactoe import State as TttState
from app.game_engines.tictactoe import TicTacToeEngine, winner_of

TTT_WIN = 1000
CHECKERS_WIN = 10_000
CHESS_MATE = 100_000
MATE_BAND = 100  # |pontuação| >= vitória - banda ⇒ mate/vitória forçada dentro do horizonte

CHECKERS_DEPTH = 4
CHECKERS_EXTENSION = 4
CHESS_DEPTH = 2
CHESS_QUIESCENCE = 4
CHESS_CHECK_EXTENSION_PLY = 12
MAN, KING = 100, 300

ENGINES: dict[str, Any] = {
    "tictactoe": TicTacToeEngine(),
    "checkers": CheckersEngine(),
    "chess": ChessEngine(),
}


class BudgetExceededError(Exception):
    """O orçamento de nós da análise acabou; o chamador decide o que fazer com o resto."""


class Budget:
    def __init__(self, nodes: int) -> None:
        self.left = nodes

    def spend(self) -> None:
        self.left -= 1
        if self.left < 0:
            raise BudgetExceededError


UNLIMITED = 10**12


@dataclass(frozen=True)
class Scored:
    move: str
    score: int


def is_forced_win(game_id: str, score: int) -> bool:
    return score >= _win(game_id) - MATE_BAND


def is_forced_loss(game_id: str, score: int) -> bool:
    return score <= -_win(game_id) + MATE_BAND


def _win(game_id: str) -> int:
    return {"tictactoe": TTT_WIN, "checkers": CHECKERS_WIN, "chess": CHESS_MATE}[game_id]


# ---------------------------------------------------------------- jogo da velha

@cache
def _ttt_value(board: str, to_move: str) -> int:
    """Valor do ponto de vista de X: +1, 0, -1."""
    if (w := winner_of(board)) is not None:
        return 1 if w == "X" else -1
    if "_" not in board:
        return 0
    nxt = "O" if to_move == "X" else "X"
    values = [_ttt_value(board[:i] + to_move + board[i + 1:], nxt)
              for i, c in enumerate(board) if c == "_"]
    return max(values) if to_move == "X" else min(values)


def _ttt_scores(state: TttState) -> dict[str, int]:
    nxt = "O" if state.to_move == "X" else "X"
    sign = 1 if state.to_move == "X" else -1
    return {str(i): sign * TTT_WIN * _ttt_value(
        state.board[:i] + state.to_move + state.board[i + 1:], nxt)
        for i, c in enumerate(state.board) if c == "_"}


# ---------------------------------------------------------------------- damas

def _ck_material(board: tuple[str, ...], color: str) -> int:
    score = 0
    for p in board:
        if p == ".":
            continue
        value = KING if p.isupper() else MAN
        score += value if p.lower() == color else -value
    return score


def _ck_search(board: tuple[str, ...], color: str, depth: int, alpha: int, beta: int,
               ply: int, ext: int, budget: Budget) -> int:
    budget.spend()
    moves = generate(board, color)
    if not moves:
        return -CHECKERS_WIN + ply
    if depth <= 0:
        if moves[0].capture and ext < CHECKERS_EXTENSION:
            depth, ext = 1, ext + 1  # captura obrigatória: não avaliar no meio da troca
        else:
            return _ck_material(board, color)
    other = "b" if color == "w" else "w"
    best = -CHECKERS_WIN * 2
    for m in moves:
        score = -_ck_search(play(board, m), other, depth - 1, -beta, -alpha, ply + 1, ext, budget)
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def _ck_moves(state: Any) -> list[Move]:
    return list(generate(state.squares, state.to_move))


def _ck_exact(state: Any, move: Move, budget: Budget) -> int:
    other = "b" if state.to_move == "w" else "w"
    return -_ck_search(play(state.squares, move), other, CHECKERS_DEPTH - 1,
                       -CHECKERS_WIN * 2, CHECKERS_WIN * 2, 1, 0, budget)


# --------------------------------------------------------------------- xadrez

def _ch_material(board: chess.Board) -> int:
    score = 0
    for piece in board.piece_map().values():
        value = VALUE[piece.piece_type]
        score += value if piece.color == board.turn else -value
    return score


def _ch_quiesce(board: chess.Board, alpha: int, beta: int, qdepth: int, budget: Budget) -> int:
    budget.spend()
    stand = _ch_material(board)
    if stand >= beta or qdepth <= 0:
        return stand
    best = stand
    alpha = max(alpha, stand)
    for move in ordered(board, list(board.generate_legal_captures())):
        board.push(move)
        score = -_ch_quiesce(board, -beta, -alpha, qdepth - 1, budget)
        board.pop()
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def _ch_search(board: chess.Board, depth: int, alpha: int, beta: int, ply: int,
               budget: Budget) -> int:
    budget.spend()
    if depth <= 0:
        if board.is_check() and ply < CHESS_CHECK_EXTENSION_PLY:
            depth = 1  # não parar no meio de um xeque
        else:
            return _ch_quiesce(board, alpha, beta, CHESS_QUIESCENCE, budget)
    moves = list(board.legal_moves)
    if not moves:
        return -CHESS_MATE + ply if board.is_check() else 0
    if board.is_insufficient_material():
        return 0
    best = -CHESS_MATE * 2
    for move in ordered(board, moves):
        board.push(move)
        score = -_ch_search(board, depth - 1, -beta, -alpha, ply + 1, budget)
        board.pop()
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def _ch_exact(board: chess.Board, move: chess.Move, budget: Budget) -> int:
    board.push(move)
    try:
        return -_ch_search(board, CHESS_DEPTH - 1, -CHESS_MATE * 2, CHESS_MATE * 2, 1, budget)
    finally:
        board.pop()


# ----------------------------------------------------------------- interface

def _chess_board(state: Any) -> chess.Board:
    board: chess.Board = state.board.copy(stack=False)  # a busca não usa repetição
    return board


def move_scores(game_id: str, state: Any, budget: Budget | None = None) -> dict[str, int]:
    """Pontuação exata de cada lance legal (do ponto de vista de quem joga)."""
    budget = budget or Budget(UNLIMITED)
    if game_id == "tictactoe":
        return _ttt_scores(state)
    if game_id == "checkers":
        return {str(m): _ck_exact(state, m, budget) for m in _ck_moves(state)}
    board = _chess_board(state)
    return {m.uci(): _ch_exact(board, m, budget) for m in ordered(board, list(board.legal_moves))}


def best_move(game_id: str, state: Any, budget: Budget | None = None) -> Scored | None:
    """Melhor lance e sua pontuação exata. Em empate de pontuação vale o primeiro na ordem
    estável do motor (determinístico). `None` se não houver lance."""
    budget = budget or Budget(UNLIMITED)
    if game_id == "tictactoe":
        scores = _ttt_scores(state)
        if not scores:
            return None
        top = max(scores.values())
        return Scored(min((m for m, s in scores.items() if s == top), key=int), top)
    if game_id == "checkers":
        moves = _ck_moves(state)
        other = "b" if state.to_move == "w" else "w"
        best: Scored | None = None
        alpha = -CHECKERS_WIN * 2
        for m in moves:
            score = -_ck_search(play(state.squares, m), other, CHECKERS_DEPTH - 1,
                                -CHECKERS_WIN * 2, -alpha, 1, 0, budget)
            if best is None or score > best.score:
                best = Scored(str(m), score)
                alpha = score
        return best
    board = _chess_board(state)
    best = None
    alpha = -CHESS_MATE * 2
    for cm in ordered(board, sorted(board.legal_moves, key=lambda x: x.uci())):
        board.push(cm)
        score = -_ch_search(board, CHESS_DEPTH - 1, -CHESS_MATE * 2, -alpha, 1, budget)
        board.pop()
        if best is None or score > best.score:
            best = Scored(cm.uci(), score)
            alpha = score
    return best


def played_score(game_id: str, state: Any, move_str: str, budget: Budget | None = None) -> int:
    """Pontuação exata de um lance legal."""
    budget = budget or Budget(UNLIMITED)
    if game_id == "tictactoe":
        return _ttt_scores(state)[move_str]
    engine = ENGINES[game_id]
    move = engine.parse_move(move_str)
    if game_id == "checkers":
        full = next((m for m in _ck_moves(state)
                     if m.path == move.path and m.capture == move.capture), None)
        if full is None:
            raise IllegalMove("lance ilegal")
        return _ck_exact(state, full, budget)
    if move not in state.board.legal_moves:
        raise IllegalMove("lance ilegal")
    return _ch_exact(_chess_board(state), move, budget)
