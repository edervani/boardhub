"""IA das damas (doc 07 §3): negamax com poda alfa-beta e aprofundamento iterativo.

Diferenças em relação ao doc: sem tabela de transposição (Zobrist) nesta versão; a extensão de
captura (continuar a busca enquanto há captura obrigatória) faz o papel da quiescência.
Níveis 1–3 têm profundidade fixa (determinísticos para uma semente); 4–5 usam limite de tempo.
"""

import random
import time

from app.game_engines.checkers import RC, Move, State, generate, play

INF = 10**6
WIN = 100_000
MAN, KING = 100, 300
MAX_CAPTURE_EXTENSION = 4
# nível: (profundidade máxima, tempo máximo em segundos ou None, margem de ruído)
LEVELS: dict[int, tuple[int, float | None, int]] = {
    1: (1, None, 300),
    2: (2, None, 120),
    3: (4, None, 40),
    4: (8, 1.0, 0),
    5: (12, 2.5, 0),
}
CENTER = [(14 - (abs(2 * r - 7) + abs(2 * c - 7))) // 2 for r, c in RC]


class _SearchTimeoutError(Exception):
    pass


class _Clock:
    def __init__(self, limit: float | None) -> None:
        self.deadline = None if limit is None else time.perf_counter() + limit
        self.nodes = 0

    def tick(self) -> None:
        self.nodes += 1
        if self.deadline is None or self.nodes % 256:
            return
        if time.perf_counter() > self.deadline:
            raise _SearchTimeoutError


def evaluate(board: tuple[str, ...], color: str) -> int:
    """Material, avanço e centro, do ponto de vista de `color`."""
    score = 0
    for i, p in enumerate(board):
        if p == ".":
            continue
        row = RC[i][0]
        if p == "w":
            value = MAN + row * 4 + CENTER[i] * 2
        elif p == "b":
            value = MAN + (7 - row) * 4 + CENTER[i] * 2
        else:
            value = KING + CENTER[i] * 2
        score += value if p.lower() == color else -value
    return score


def _search(board: tuple[str, ...], color: str, depth: int, alpha: int, beta: int, ply: int,
            ext: int, clock: _Clock) -> int:
    clock.tick()
    moves = generate(board, color)
    if not moves:
        return -WIN + ply
    if depth <= 0:
        if moves[0].capture and ext < MAX_CAPTURE_EXTENSION:
            depth, ext = 1, ext + 1  # captura obrigatória: não avaliar no meio da troca
        else:
            return evaluate(board, color)
    other = "b" if color == "w" else "w"
    best = -INF
    for m in moves:
        score = -_search(play(board, m), other, depth - 1, -beta, -alpha, ply + 1, ext, clock)
        if score > best:
            best = score
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def _root_scores(board: tuple[str, ...], color: str, moves: list[Move], depth: int,
                 clock: _Clock) -> dict[int, int]:
    other = "b" if color == "w" else "w"
    return {i: -_search(play(board, m), other, depth - 1, -INF, INF, 1, 0, clock)
            for i, m in enumerate(moves)}


def choose_move(state: State, level: int, rng: random.Random) -> Move:
    if level not in LEVELS:
        raise ValueError("nível inválido")
    board, color = state.squares, state.to_move
    moves = generate(board, color)
    if not moves:
        raise ValueError("partida encerrada")
    if len(moves) == 1:
        return moves[0]
    max_depth, limit, margin = LEVELS[level]
    clock = _Clock(limit)
    scores = {i: 0 for i in range(len(moves))}
    order = list(range(len(moves)))
    for depth in range(1, max_depth + 1):
        try:
            # Melhor lance anterior primeiro: melhora a poda no aprofundamento seguinte.
            ordered = [moves[i] for i in order]
            fresh = _root_scores(board, color, ordered, depth, clock)
            scores = {order[k]: v for k, v in fresh.items()}
        except _SearchTimeoutError:
            break
        order.sort(key=lambda i: -scores[i])
        if max(scores.values()) >= WIN - 100:
            break  # vitória forçada encontrada
        if limit is None and depth >= max_depth:
            break
    best = max(scores.values())
    pool = [i for i, s in scores.items() if s >= best - margin]
    return moves[rng.choice(pool)]
