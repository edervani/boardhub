"""Jogo da velha clássico (doc 07 §2). Estado imutável; X começa."""

from dataclasses import dataclass
from typing import Any

from app.game_engines.base import IllegalMove, InvalidState, Outcome

LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class State:
    board: str  # 9 caracteres de "X", "O" ou "_"; índice 0 = canto superior esquerdo
    to_move: str


def winner_of(board: str) -> str | None:
    for a, b, c in LINES:
        if board[a] != "_" and board[a] == board[b] == board[c]:
            return board[a]
    return None


class TicTacToeEngine:
    game_id = "tictactoe"
    rules_version = "tictactoe-1"

    def initial_state(self) -> State:
        return State("_" * 9, "X")

    def legal_moves(self, state: State) -> list[int]:
        if self.outcome(state) is not None:
            return []
        return [i for i, c in enumerate(state.board) if c == "_"]

    def apply(self, state: State, move: int) -> State:
        if self.outcome(state) is not None:
            raise IllegalMove("a partida já terminou")
        if not 0 <= move <= 8 or state.board[move] != "_":
            raise IllegalMove("casa indisponível")
        board = state.board[:move] + state.to_move + state.board[move + 1:]
        return State(board, "O" if state.to_move == "X" else "X")

    def outcome(self, state: State) -> Outcome | None:
        if (w := winner_of(state.board)) is not None:
            return Outcome(w, "line")
        if "_" not in state.board:
            return Outcome(None, "draw")
        return None

    def serialize(self, state: State) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "board": state.board, "to_move": state.to_move}

    def deserialize(self, data: dict[str, Any]) -> State:
        board, to_move = data.get("board"), data.get("to_move")
        if data.get("schema_version") != SCHEMA_VERSION or not isinstance(board, str):
            raise InvalidState("versão ou tabuleiro inválido")
        if len(board) != 9 or set(board) - set("XO_") or to_move not in ("X", "O"):
            raise InvalidState("tabuleiro inválido")
        x, o = board.count("X"), board.count("O")
        if x - o not in (0, 1) or to_move != ("O" if x > o else "X"):
            raise InvalidState("contagem de peças inconsistente")
        wins = {winner_of(board)} - {None}
        if (wins == {"X"} and x == o) or (wins == {"O"} and x > o):
            raise InvalidState("vencedor inconsistente com a vez")
        return State(board, str(to_move))

    def parse_move(self, raw: str) -> int:
        if not (len(raw) == 1 and raw in "012345678"):
            raise IllegalMove("lance deve ser um número de 0 a 8")
        return int(raw)
