"""Damas brasileiras (doc 07 §3, DT-006).

Conferido no regulamento de damas dos Jogos Fenae Mais 2025 (docs/16 P-26): 8×8, 12 peças,
captura obrigatória, lei da maioria, dama voadora, promoção só quando o lance TERMINA na última
fileira, peças capturadas só saem ao fim do lance, empate por acordo e após 20 lances só com damas.

Não confirmado na fonte (P-26): vitória por bloqueio, repetição tripla (o regulamento não a
trata), se os 20 lances são por lado. Não implementado: empate em 5 lances nos finais de damas
(art. 24 b–f do regulamento).

Numeração PDN: 1–4 na fileira de fundo das pretas e 29–32 na das brancas; brancas sobem.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from app.game_engines.base import IllegalMove, InvalidState, Outcome

SCHEMA_VERSION = 1
KINGS_ONLY_LIMIT_PLIES = 40  # 20 lances de cada lado só com damas, sem captura (doc 07)
REPETITION_LIMIT = 3
PIECES = frozenset("wWbB.")
DIRS = ((1, 1), (1, -1), (-1, 1), (-1, -1))  # (dfileira, dcoluna); fileira 0 = fundo das brancas
FORWARD = {"w": (0, 1), "b": (2, 3)}

# --- geometria (índice 0..31 = casa 1..32) ---
RC: list[tuple[int, int]] = []
_INDEX: dict[tuple[int, int], int] = {}
for _r in range(7, -1, -1):
    for _c in range(8):
        if (_r + _c) % 2 == 0:
            _INDEX[(_r, _c)] = len(RC)
            RC.append((_r, _c))


def _ray(i: int, d: tuple[int, int]) -> tuple[int, ...]:
    r, c = RC[i]
    out = []
    r, c = r + d[0], c + d[1]
    while (r, c) in _INDEX:
        out.append(_INDEX[(r, c)])
        r, c = r + d[0], c + d[1]
    return tuple(out)


RAYS: list[tuple[tuple[int, ...], ...]] = [tuple(_ray(i, d) for d in DIRS) for i in range(32)]
CROWN_ROW = {"w": 7, "b": 0}


@dataclass(frozen=True)
class Move:
    path: tuple[int, ...]  # casas 1..32: origem e cada pouso
    capture: bool
    captured: tuple[int, ...] = field(default=(), compare=False)

    def __str__(self) -> str:
        return ("x" if self.capture else "-").join(str(s) for s in self.path)


@dataclass(frozen=True)
class State:
    squares: tuple[str, ...]  # 32 casas: "w","b" pedras, "W","B" damas, "." vazia
    to_move: str  # "w" | "b"
    kings_only_plies: int
    history: tuple[str, ...]  # chaves das posições desde o último lance irreversível


def position_key(squares: tuple[str, ...] | list[str], to_move: str) -> str:
    return hashlib.sha256(("".join(squares) + to_move).encode()).hexdigest()[:16]


def initial_squares() -> tuple[str, ...]:
    return tuple("b" if i < 12 else "w" if i >= 20 else "." for i in range(32))


# --- geração de lances (funções puras sobre o tabuleiro, usadas também pela IA) ---

def _captures(board: tuple[str, ...], origin: int) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    piece = board[origin]
    color, is_king = piece.lower(), piece.isupper()
    b = list(board)
    b[origin] = "."  # a peça que se move deixa a casa de origem
    results: list[tuple[tuple[int, ...], tuple[int, ...]]] = []

    def dfs(pos: int, path: tuple[int, ...], taken: tuple[int, ...]) -> None:
        found = False
        for ray in RAYS[pos]:
            if is_king:
                k = 0
                while k < len(ray) and b[ray[k]] == ".":
                    k += 1
                if k == len(ray):
                    continue
                target = ray[k]
                if b[target].lower() == color or target in taken:
                    continue  # própria peça ou peça já capturada (obstáculo)
                j = k + 1
                while j < len(ray) and b[ray[j]] == ".":
                    found = True
                    dfs(ray[j], (*path, ray[j]), (*taken, target))
                    j += 1
            else:
                if len(ray) < 2:
                    continue
                target, land = ray[0], ray[1]
                if b[target] == "." or b[target].lower() == color or target in taken:
                    continue
                if b[land] != ".":
                    continue
                found = True
                dfs(land, (*path, land), (*taken, target))
        if not found and taken:
            results.append((path, taken))

    dfs(origin, (origin,), ())
    return results


def generate(board: tuple[str, ...], color: str) -> list[Move]:
    """Lances legais: captura obrigatória e lei da maioria."""
    caps: list[Move] = []
    for i, p in enumerate(board):
        if p != "." and p.lower() == color:
            for path, taken in _captures(board, i):
                caps.append(Move(tuple(s + 1 for s in path), True, tuple(s + 1 for s in taken)))
    if caps:
        most = max(len(m.captured) for m in caps)
        return [m for m in caps if len(m.captured) == most]
    moves: list[Move] = []
    for i, p in enumerate(board):
        if p == "." or p.lower() != color:
            continue
        for d in (range(4) if p.isupper() else FORWARD[color]):
            for sq in RAYS[i][d]:
                if board[sq] != ".":
                    break
                moves.append(Move((i + 1, sq + 1), False))
                if not p.isupper():
                    break
    return moves


def play(board: tuple[str, ...], move: Move) -> tuple[str, ...]:
    """Aplica um lance já validado e devolve o novo tabuleiro."""
    b = list(board)
    origin, dest = move.path[0] - 1, move.path[-1] - 1
    piece = b[origin]
    b[origin] = "."
    for sq in move.captured:
        b[sq - 1] = "."
    if piece.islower() and RC[dest][0] == CROWN_ROW[piece]:
        piece = piece.upper()
    b[dest] = piece
    return tuple(b)


class CheckersEngine:
    game_id = "checkers"
    rules_version = "checkers-br-1"

    def initial_state(self) -> State:
        sq = initial_squares()
        return State(sq, "w", 0, (position_key(sq, "w"),))

    def legal_moves(self, state: State) -> list[Move]:
        if self.outcome(state) is not None:
            return []
        return generate(state.squares, state.to_move)

    def apply(self, state: State, move: Move) -> State:
        legal = self.legal_moves(state)
        match = next((m for m in legal if m.path == move.path and m.capture == move.capture), None)
        if match is None:
            if legal and legal[0].capture and not move.capture:
                raise IllegalMove("captura obrigatória")
            if legal and legal[0].capture:
                raise IllegalMove("lei da maioria: escolha a sequência que captura mais peças")
            raise IllegalMove("lance ilegal")
        piece = state.squares[match.path[0] - 1]
        board = play(state.squares, match)
        nxt = "b" if state.to_move == "w" else "w"
        history: tuple[str, ...]
        if match.capture or piece.islower():
            plies, history = 0, (position_key(board, nxt),)
        else:
            plies = state.kings_only_plies + 1
            history = (*state.history, position_key(board, nxt))
        return State(board, nxt, plies, history)

    def outcome(self, state: State) -> Outcome | None:
        if not generate(state.squares, state.to_move):
            return Outcome("b" if state.to_move == "w" else "w", "no_moves")
        if state.history.count(state.history[-1]) >= REPETITION_LIMIT:
            return Outcome(None, "repetition")
        if state.kings_only_plies >= KINGS_ONLY_LIMIT_PLIES:
            return Outcome(None, "kings_only")
        return None

    def serialize(self, state: State) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "squares": list(state.squares),
                "to_move": state.to_move, "halfmove_kings_only": state.kings_only_plies,
                "position_history": list(state.history)}

    def deserialize(self, data: dict[str, Any]) -> State:
        squares, to_move = data.get("squares"), data.get("to_move")
        plies, history = data.get("halfmove_kings_only"), data.get("position_history")
        if data.get("schema_version") != SCHEMA_VERSION:
            raise InvalidState("versão inválida")
        if not (isinstance(squares, list) and len(squares) == 32
                and all(isinstance(s, str) and s in PIECES for s in squares)):
            raise InvalidState("tabuleiro inválido")
        if to_move not in ("w", "b"):
            raise InvalidState("vez inválida")
        if not (isinstance(plies, int) and not isinstance(plies, bool)
                and 0 <= plies <= KINGS_ONLY_LIMIT_PLIES):
            raise InvalidState("contador inválido")
        if not (isinstance(history, list) and 1 <= len(history) <= KINGS_ONLY_LIMIT_PLIES + 1
                and all(isinstance(h, str) and re.fullmatch(r"[0-9a-f]{16}", h) for h in history)):
            raise InvalidState("histórico inválido")
        board = tuple(str(s) for s in squares)
        if history[-1] != position_key(board, str(to_move)):
            raise InvalidState("histórico inconsistente com a posição")
        for color in "wb":
            if sum(1 for p in board if p.lower() == color) > 12:
                raise InvalidState("peças demais")
        if any(board[i] == "w" and RC[i][0] == 7 or board[i] == "b" and RC[i][0] == 0
               for i in range(32)):
            raise InvalidState("pedra na fileira de promoção")
        return State(board, str(to_move), plies, tuple(history))

    def parse_move(self, raw: str) -> Move:
        if not re.fullmatch(r"[0-9]{1,2}(-[0-9]{1,2}|(x[0-9]{1,2})+)", raw):
            raise IllegalMove("use o formato 11-15 ou 15x24x31")
        capture = "x" in raw
        path = tuple(int(s) for s in re.split(r"[-x]", raw))
        if any(not 1 <= s <= 32 for s in path):
            raise IllegalMove("casas vão de 1 a 32")
        return Move(path, capture)
