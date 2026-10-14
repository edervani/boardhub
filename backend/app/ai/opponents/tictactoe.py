"""IA do jogo da velha em 5 níveis (doc 07 §2). Aleatoriedade vem de `random.Random` injetado."""

import random
from functools import cache

from app.game_engines.tictactoe import LINES, State, TicTacToeEngine, winner_of

ENGINE = TicTacToeEngine()
SUBOPTIMAL_CHANCE_L4 = 0.25
LEVELS = (1, 2, 3, 4, 5)


@cache
def _value(board: str, to_move: str) -> int:
    """Valor do ponto de vista de X: +1 vitória de X, 0 empate, -1 vitória de O."""
    if (w := winner_of(board)) is not None:
        return 1 if w == "X" else -1
    if "_" not in board:
        return 0
    nxt = "O" if to_move == "X" else "X"
    values = [_value(board[:i] + to_move + board[i + 1:], nxt)
              for i, c in enumerate(board) if c == "_"]
    return max(values) if to_move == "X" else min(values)


def _scored(state: State) -> dict[int, int]:
    """Valor (para quem joga: maior é melhor) de cada lance legal."""
    nxt = "O" if state.to_move == "X" else "X"
    sign = 1 if state.to_move == "X" else -1
    return {m: sign * _value(state.board[:m] + state.to_move + state.board[m + 1:], nxt)
            for m in ENGINE.legal_moves(state)}


def _completing(state: State, player: str) -> list[int]:
    """Lances que completam uma linha para `player` (considerando que ele jogue agora)."""
    out = []
    for a, b, c in LINES:
        cells = [state.board[a], state.board[b], state.board[c]]
        if cells.count(player) == 2 and cells.count("_") == 1:
            out.append((a, b, c)[cells.index("_")])
    return out


def choose_move(state: State, level: int, rng: random.Random) -> int:
    if level not in LEVELS:
        raise ValueError("nível inválido")
    legal = ENGINE.legal_moves(state)
    if not legal:
        raise ValueError("partida encerrada")
    me = state.to_move
    opponent = "O" if me == "X" else "X"
    if level in (2, 3) and (win := _completing(state, me)):
        return win[0]
    if level == 3 and (block := _completing(state, opponent)):
        return block[0]
    if level <= 3:
        return rng.choice(legal)
    scores = _scored(state)
    best_score = max(scores.values())
    best = [m for m, s in scores.items() if s == best_score]
    worse = [m for m, s in scores.items() if s < best_score]
    if level == 4 and worse and rng.random() < SUBOPTIMAL_CHANCE_L4:
        return rng.choice(worse)
    return best[0]
