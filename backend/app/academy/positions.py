"""Constrói o estado do motor a partir da posição de um exercício.

O estado do xadrez serializado pelo motor exige a lista de lances desde o início; exercícios
partem de uma posição (FEN) arbitrária, então o estado é montado diretamente e usado apenas
em memória (nunca persistido nem passado a `deserialize`).
"""

from typing import Any

import chess

from app.academy.content import ContentError
from app.game_engines.base import InvalidState
from app.game_engines.checkers import PIECES, RC, position_key
from app.game_engines.checkers import State as CheckersState
from app.game_engines.chess import State as ChessState
from app.game_engines.tictactoe import TicTacToeEngine


def build_state(game_id: str, position: dict[str, str]) -> Any:
    try:
        if game_id == "tictactoe":
            return TicTacToeEngine().deserialize(
                {"schema_version": 1, "board": position["board"], "to_move": position["to_move"]})
        if game_id == "checkers":
            squares = tuple(position["squares"])
            to_move = position["to_move"]
            valid = (len(squares) == 32 and set(squares) <= PIECES and to_move in ("w", "b")
                     and all(not (squares[i] == "w" and RC[i][0] == 7
                                  or squares[i] == "b" and RC[i][0] == 0) for i in range(32)))
            if not valid:
                raise ContentError("posição de damas inválida")
            return CheckersState(squares, to_move, 0, (position_key(squares, to_move),))
        board = chess.Board(position["fen"])
        if not board.is_valid():
            raise ContentError("FEN inválido")
        return ChessState((), board)
    except (KeyError, ValueError, InvalidState) as exc:
        raise ContentError(f"posição inválida: {exc}") from exc
