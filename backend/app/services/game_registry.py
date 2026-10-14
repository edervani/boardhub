"""Associa cada jogo habilitado ao seu motor e à sua IA (doc 04 §5)."""

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.ai.opponents import checkers as checkers_ai
from app.ai.opponents import tictactoe as tictactoe_ai
from app.game_engines.base import GameEngine
from app.game_engines.checkers import CheckersEngine
from app.game_engines.tictactoe import TicTacToeEngine


@dataclass(frozen=True)
class GameKit:
    engine: GameEngine[Any, Any]
    choose_ai_move: Callable[[Any, int, random.Random], Any]
    # Símbolo do vencedor para cada assento: (assento 1, assento 2).
    symbols: tuple[str, str]


KITS: dict[str, GameKit] = {
    "tictactoe": GameKit(TicTacToeEngine(), tictactoe_ai.choose_move, ("X", "O")),
    "checkers": GameKit(CheckersEngine(), checkers_ai.choose_move, ("w", "b")),
}
