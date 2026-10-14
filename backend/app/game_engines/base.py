"""Contrato comum dos motores (doc 04 §7). Sem I/O, sem aleatoriedade não injetada."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol


class IllegalMove(Exception):
    """Lance ilegal ou texto de lance inválido; a mensagem nunca ecoa dados sensíveis."""


class InvalidState(Exception):
    """Estado serializado inconsistente. A partida deve ser abortada, nunca 'consertada'."""


@dataclass(frozen=True)
class Outcome:
    """`winner` é o símbolo do vencedor; None com `reason == "draw"` é empate."""

    winner: str | None
    reason: str


class GameEngine[State, Move](Protocol):
    game_id: str
    rules_version: str

    def initial_state(self) -> State: ...
    def legal_moves(self, state: State) -> list[Move]: ...
    def apply(self, state: State, move: Move) -> State: ...
    def outcome(self, state: State) -> Outcome | None: ...
    def serialize(self, state: State) -> dict[str, Any]: ...
    def deserialize(self, data: dict[str, Any]) -> State: ...
    def parse_move(self, raw: str) -> Move: ...


def state_hash(serialized: dict[str, Any]) -> str:
    """Hash do JSON canônico (chaves ordenadas), usado em `state_after_hash` (doc 07 §5)."""
    canonical = json.dumps(serialized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
