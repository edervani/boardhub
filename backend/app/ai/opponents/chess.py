"""IA do xadrez (doc 07 §4, RNF-002): negamax com poda alfa-beta e aprofundamento iterativo.

É o "fallback" do doc 07 (busca própria sobre python-chess); motor UCI externo (Stockfish) fica
para a Fase 5. Avaliação: material + tabelas de casas simples; ordenação MVV-LVA; quiescência só
com capturas; extensão de xeque no horizonte. Nível 1 é aleatório com preferência por capturas.
Toda aleatoriedade vem do `random.Random` injetado. Níveis 2–5 têm limite de tempo: se a busca
estoura o tempo, vale a última profundidade completa.
"""

import random
import time

import chess

from app.game_engines.chess import State

INF = 10**9
MATE = 100_000
MAX_EXTENSION_PLY = 30
QUIESCENCE_DEPTH = 4
CAPTURE_BIAS = 0.7  # nível 1: chance de escolher entre as capturas, quando houver
ENDGAME_MATERIAL = 2600  # soma de peças (sem peões/reis) dos dois lados
# nível: (profundidade máxima, tempo máximo em segundos, margem de ruído em centipeões)
LEVELS: dict[int, tuple[int, float | None, int]] = {
    1: (0, None, 0),
    2: (2, 0.3, 25),
    3: (3, 1.0, 10),
    4: (4, 2.0, 0),
    5: (5, 3.0, 0),
}

VALUE: dict[int, int] = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
                         chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}
ORDER_VALUE: dict[int, int] = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                               chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 10}

# Tabelas "simplified evaluation function": vistas das brancas, da 8ª fileira (a8..h8) à 1ª.
PAWN_TABLE = (
    0, 0, 0, 0, 0, 0, 0, 0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
    5, 5, 10, 25, 25, 10, 5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, -5, -10, 0, 0, -10, -5, 5,
    5, 10, 10, -20, -20, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
)
KNIGHT_TABLE = (
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
)
BISHOP_TABLE = (
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
)
ROOK_TABLE = (
    0, 0, 0, 0, 0, 0, 0, 0,
    5, 10, 10, 10, 10, 10, 10, 5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    0, 0, 0, 5, 5, 0, 0, 0,
)
QUEEN_TABLE = (
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -5, 0, 5, 5, 5, 5, 0, -5,
    0, 0, 5, 5, 5, 5, 0, -5,
    -10, 5, 5, 5, 5, 5, 0, -10,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20,
)
KING_TABLE = (
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    20, 20, 0, 0, 0, 0, 20, 20,
    20, 30, 10, 0, 0, 10, 30, 20,
)
KING_ENDGAME_TABLE = (
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
)
TABLES: dict[int, tuple[int, ...]] = {
    chess.PAWN: PAWN_TABLE, chess.KNIGHT: KNIGHT_TABLE, chess.BISHOP: BISHOP_TABLE,
    chess.ROOK: ROOK_TABLE, chess.QUEEN: QUEEN_TABLE, chess.KING: KING_TABLE,
}


class _SearchTimeoutError(Exception):
    pass


class _Clock:
    """Controla o tempo. Só dispara depois de `arm()`, para que a profundidade 1 sempre termine."""

    def __init__(self, limit: float | None) -> None:
        self.limit = limit
        self.deadline = 0.0
        self.armed = False
        self.nodes = 0

    def arm(self) -> None:
        if self.limit is not None:
            self.armed = True

    def start(self) -> None:
        if self.limit is not None:
            self.deadline = time.perf_counter() + self.limit

    def tick(self) -> None:
        self.nodes += 1
        if not self.armed or self.nodes % 64:
            return
        if time.perf_counter() > self.deadline:
            raise _SearchTimeoutError


def evaluate(board: chess.Board) -> int:
    """Material e posição, do ponto de vista de quem joga."""
    pieces = board.piece_map()
    material = sum(VALUE[p.piece_type] for p in pieces.values()
                   if p.piece_type not in (chess.PAWN, chess.KING))
    endgame = material <= ENDGAME_MATERIAL
    score = 0
    for square, piece in pieces.items():
        kind = piece.piece_type
        table = KING_ENDGAME_TABLE if kind == chess.KING and endgame else TABLES[kind]
        if piece.color == chess.WHITE:
            score += VALUE[kind] + table[square ^ 56]
        else:
            score -= VALUE[kind] + table[square]
    return score if board.turn == chess.WHITE else -score


def move_order_key(board: chess.Board, move: chess.Move) -> int:
    """MVV-LVA: maior vítima primeiro, menor atacante primeiro; promoções logo depois."""
    key = 0
    if board.is_capture(move):
        victim = board.piece_type_at(move.to_square) or chess.PAWN  # en passant: casa vazia
        attacker = board.piece_type_at(move.from_square) or chess.PAWN
        key += 1000 + 100 * ORDER_VALUE[victim] - ORDER_VALUE[attacker]
    if move.promotion:
        key += 800 + ORDER_VALUE[move.promotion]
    return key


def ordered(board: chess.Board, moves: list[chess.Move]) -> list[chess.Move]:
    return sorted(moves, key=lambda m: -move_order_key(board, m))


def _quiesce(board: chess.Board, alpha: int, beta: int, qdepth: int, clock: _Clock) -> int:
    clock.tick()
    stand = evaluate(board)
    if stand >= beta or qdepth <= 0:
        return stand
    best = stand
    alpha = max(alpha, stand)
    for move in ordered(board, list(board.generate_legal_captures())):
        board.push(move)
        score = -_quiesce(board, -beta, -alpha, qdepth - 1, clock)
        board.pop()
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def _negamax(board: chess.Board, depth: int, alpha: int, beta: int, ply: int,
             clock: _Clock) -> int:
    clock.tick()
    if board.halfmove_clock >= 100:
        return 0
    if depth <= 0:
        if board.is_check() and ply < MAX_EXTENSION_PLY:
            depth = 1  # não parar no meio de um xeque
        else:
            return _quiesce(board, alpha, beta, QUIESCENCE_DEPTH, clock)
    moves = list(board.legal_moves)
    if not moves:
        return -MATE + ply if board.is_check() else 0
    best = -INF
    for move in ordered(board, moves):
        board.push(move)
        score = -_negamax(board, depth - 1, -beta, -alpha, ply + 1, clock)
        board.pop()
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def _root_scores(board: chess.Board, order: list[chess.Move], depth: int, margin: int,
                 clock: _Clock) -> dict[chess.Move, int]:
    """Pontua cada lance da raiz. Lances que ficam abaixo de `melhor - margem` recebem apenas um
    limite superior (a janela os corta); os que ficam dentro da margem têm valor exato."""
    scores: dict[chess.Move, int] = {}
    best = -INF
    for move in order:
        floor = max(-INF, best - margin - 1)
        board.push(move)
        score = -_negamax(board, depth - 1, -INF, -floor, 1, clock)
        board.pop()
        scores[move] = score
        best = max(best, score)
    return scores


def _level_one(board: chess.Board, moves: list[chess.Move], rng: random.Random) -> chess.Move:
    captures = [m for m in moves if board.is_capture(m)]
    if captures and rng.random() < CAPTURE_BIAS:
        return rng.choice(captures)
    return rng.choice(moves)


def choose_move(state: State, level: int, rng: random.Random) -> str:
    """Devolve o lance escolhido em UCI. Levanta ValueError para nível ou posição inválidos."""
    if level not in LEVELS:
        raise ValueError("nível inválido")
    moves = sorted(state.board.legal_moves, key=lambda m: m.uci())
    if not moves:
        raise ValueError("partida encerrada")
    if level == 1:
        return _level_one(state.board, moves, rng).uci()
    if len(moves) == 1:
        return moves[0].uci()
    max_depth, limit, margin = LEVELS[level]
    # A busca não usa repetição; a cópia é descartada se o tempo estourar no meio de um lance.
    board = state.board.copy(stack=False)
    clock = _Clock(limit)
    clock.start()
    order = ordered(board, moves)
    scores: dict[chess.Move, int] = {}
    for depth in range(1, max_depth + 1):
        try:
            scores = _root_scores(board, order, depth, margin, clock)
        except _SearchTimeoutError:
            break
        clock.arm()
        order = sorted(order, key=lambda m: -scores[m])  # melhor primeiro: mais poda
        if max(scores.values()) >= MATE - 100:
            break  # mate forçado encontrado
    best = max(scores.values())
    pool = [m for m in moves if scores[m] >= best - margin]
    return rng.choice(pool).uci()
