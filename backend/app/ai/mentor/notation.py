"""Como mostrar lances e posições ao usuário em português (sem inventar nada)."""

from typing import Any

import chess

from app.ai.mentor.evaluation import ENGINES

PIECE_NAMES = {chess.PAWN: "peão", chess.KNIGHT: "cavalo", chess.BISHOP: "bispo",
               chess.ROOK: "torre", chess.QUEEN: "dama", chess.KING: "rei"}
PIECE_WITH_ARTICLE = {chess.PAWN: "o peão", chess.KNIGHT: "o cavalo", chess.BISHOP: "o bispo",
                      chess.ROOK: "a torre", chess.QUEEN: "a dama", chess.KING: "o rei"}


def ttt_cell(index: int) -> str:
    return f"linha {index // 3 + 1}, coluna {index % 3 + 1}"


_PT_LETTERS = str.maketrans({"K": "R", "Q": "D", "R": "T", "N": "C"})


def pt_san(san: str) -> str:
    """Notação algébrica com as letras das peças em português: R, D, T, B, C (peão sem letra)."""
    return san.translate(_PT_LETTERS)


def display_move(game_id: str, state: Any, move_str: str) -> str:
    """Jogo da velha: linha e coluna; damas: notação PDN; xadrez: notação algébrica em português."""
    if game_id == "tictactoe":
        return ttt_cell(int(move_str))
    if game_id == "checkers":
        return move_str
    return pt_san(str(state.board.san(ENGINES["chess"].parse_move(move_str))))


def describe_position(game_id: str, state: Any) -> dict[str, Any]:
    """Posição no formato que os tabuleiros do frontend já consomem (MatchState)."""
    if game_id == "tictactoe":
        return {"board": state.board, "to_move": state.to_move}
    if game_id == "checkers":
        return {"squares": list(state.squares), "to_move": state.to_move}
    return {"fen": state.board.fen(), "to_move": state.to_move}
