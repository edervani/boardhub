"""Xadrez (doc 07 §4, DT-005): regras FIDE delegadas à biblioteca python-chess.

Nenhuma regra é reimplementada aqui. O estado é a lista de lances UCI desde a posição inicial:
ela é necessária para detectar repetição e permite validar o estado ao carregá-lo (os lances são
reexecutados e o FEN gravado precisa coincidir).

Empates automáticos: afogamento, material insuficiente, quíntupla repetição e 75 lances. A repetição
tripla e a regra dos 50 lances (FIDE 9.2 e 9.3) são apenas *reivindicáveis* por quem tem a vez:
`claimable_draw` diz se cabe a reivindicação; quem encerra a partida é o serviço (P-17).
"""

import re
from dataclasses import dataclass
from typing import Any

import chess

from app.game_engines.base import IllegalMove, InvalidState, Outcome

SCHEMA_VERSION = 1
MAX_PLIES = 600  # limite de tamanho do estado; ao atingi-lo a partida termina empatada
UCI_RE = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?")


@dataclass(frozen=True, eq=False)
class State:
    """`board` carrega a pilha de lances (repetição); nunca deve ser alterado depois de criado."""

    moves: tuple[str, ...]
    board: chess.Board

    @property
    def to_move(self) -> str:
        return "w" if self.board.turn == chess.WHITE else "b"


def is_uci(raw: object) -> bool:
    return isinstance(raw, str) and UCI_RE.fullmatch(raw) is not None


class ChessEngine:
    game_id = "chess"
    rules_version = "chess-fide-1"

    def initial_state(self) -> State:
        return State((), chess.Board())

    def legal_moves(self, state: State) -> list[chess.Move]:
        if self.outcome(state) is not None:
            return []
        return list(state.board.legal_moves)

    def apply(self, state: State, move: chess.Move) -> State:
        if self.outcome(state) is not None:
            raise IllegalMove("a partida já terminou")
        if move not in state.board.legal_moves:
            raise IllegalMove("lance ilegal")
        board = state.board.copy()
        board.push(move)
        return State((*state.moves, move.uci()), board)

    def outcome(self, state: State) -> Outcome | None:
        board = state.board
        if board.is_checkmate():
            return Outcome("b" if board.turn == chess.WHITE else "w", "checkmate")
        if board.is_stalemate():
            return Outcome(None, "stalemate")
        if board.is_insufficient_material():
            return Outcome(None, "insufficient_material")
        if board.is_fivefold_repetition():
            return Outcome(None, "repetition")
        if board.is_seventyfive_moves():
            return Outcome(None, "fifty_move")
        if len(state.moves) >= MAX_PLIES:
            return Outcome(None, "ply_limit")
        return None

    def claimable_draw(self, state: State) -> str | None:
        """Motivo ("repetition" ou "fifty_move") que permite a quem tem a vez reivindicar empate.

        Vale para a posição já repetida 3 vezes ou que se repetiria com um lance legal, e para
        50 lances sem captura nem peão (python-chess aplica FIDE 9.2/9.3). `None` se a partida
        já terminou ou não cabe reivindicação.
        """
        if self.outcome(state) is not None:
            return None
        board = state.board
        if board.can_claim_threefold_repetition():
            return "repetition"
        if board.can_claim_fifty_moves():
            return "fifty_move"
        return None

    def serialize(self, state: State) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "fen": state.board.fen(),
                "moves": list(state.moves)}

    def deserialize(self, data: dict[str, Any]) -> State:
        version = data.get("schema_version")
        if type(version) is not int or version != SCHEMA_VERSION:  # bool não vale como versão
            raise InvalidState("versão inválida")
        fen, moves = data.get("fen"), data.get("moves")
        if not isinstance(fen, str) or len(fen) > 100:
            raise InvalidState("FEN inválido")
        if not (isinstance(moves, list) and len(moves) <= MAX_PLIES
                and all(is_uci(m) for m in moves)):
            raise InvalidState("lista de lances inválida")
        board = chess.Board()
        try:
            for raw in moves:
                move = chess.Move.from_uci(raw)
                if move not in board.legal_moves:
                    raise InvalidState("lance ilegal no histórico")
                board.push(move)
        except ValueError:
            raise InvalidState("lance inválido no histórico") from None
        if board.fen() != fen:
            raise InvalidState("FEN inconsistente com os lances")
        return State(tuple(str(m) for m in moves), board)

    def parse_move(self, raw: str) -> chess.Move:
        if not is_uci(raw) or raw[:2] == raw[2:4]:
            raise IllegalMove("use o formato UCI, como e2e4 ou e7e8q")
        try:
            return chess.Move.from_uci(raw)
        except ValueError:
            raise IllegalMove("lance inválido") from None
