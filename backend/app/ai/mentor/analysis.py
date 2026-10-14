"""Mentor pós-partida (RF-024, doc 08 §7): reexecuta os lances e aponta até 3 momentos críticos.

Cada afirmação vem do motor: lance melhor e pontuação (`evaluation`), resposta do adversário e
o que ela captura. O texto é montado por modelos fixos em português (`explain`); a IA generativa,
se existir, só reformula esse texto (ver `llm.provider`). Análise rasa e declarada como tal:
material e mates dentro do horizonte de busca, sem Stockfish.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import chess

from app.ai.mentor import evaluation as ev
from app.ai.mentor.evaluation import ENGINES, Budget, BudgetExceededError
from app.ai.mentor.notation import (
    PIECE_WITH_ARTICLE,
    describe_position,
    display_move,
)
from app.game_engines.tictactoe import LINES

ENGINE_VERSION = "mentor-1"
MAX_MOMENTS = 3
NODE_BUDGET = {"tictactoe": 10**9, "checkers": 300_000, "chess": 120_000}
SEVERITY_RANK = {"inaccuracy": 1, "mistake": 2, "blunder": 3}
# Limiares (doc 08 §7): xadrez em centipeões; damas em centésimos de pedra.
CHESS_THRESHOLDS = ((300, "blunder"), (100, "mistake"), (50, "inaccuracy"))
CHECKERS_THRESHOLDS = ((300, "blunder"), (100, "mistake"))


@dataclass(frozen=True)
class Moment:
    ply: int  # índice (0 = primeiro lance da partida) do lance jogado
    seat: int
    severity: str
    kind: str  # missed_win | allowed_loss | lost_material | lost_position
    loss: int
    played: str
    played_label: str
    best: str
    best_label: str
    reply: str | None
    reply_label: str | None
    reason: str  # win | check | capture | block | avoids_loss | keeps
    reason_detail: str | None  # ex.: «o cavalo em e5» ou «2 peças»
    reply_detail: str | None  # o que a resposta do adversário captura
    reply_is_win: bool
    concept_key: str
    position: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GameAnalysis:
    moments: list[Moment]
    analyzed_moves: int
    user_moves: int
    truncated: bool
    counts: dict[str, int]


# ------------------------------------------------------------------ classificação

def classify(game_id: str, best_score: int, played_score: int) -> tuple[str, str] | None:
    """(gravidade, tipo) ou `None` se o lance não é um momento crítico."""
    if game_id == "tictactoe":
        if played_score <= -ev.TTT_WIN and best_score > -ev.TTT_WIN:
            return "blunder", "lost_position"
        return None
    if ev.is_forced_win(game_id, best_score) and not ev.is_forced_win(game_id, played_score):
        return "blunder", "missed_win"
    if ev.is_forced_loss(game_id, played_score) and not ev.is_forced_loss(game_id, best_score):
        return "blunder", "allowed_loss"
    loss = best_score - played_score
    for limit, severity in (CHESS_THRESHOLDS if game_id == "chess" else CHECKERS_THRESHOLDS):
        if loss >= limit:
            return severity, "lost_material"
    return None


def _concept(game_id: str, kind: str, reason: str, reply_capture: bool) -> str:
    if game_id == "tictactoe":
        return {"win": "tt.win_in_one", "block": "tt.block"}.get(reason, "tt.fork")
    if game_id == "checkers":
        if reason == "capture":
            return "ck.majority_rule"
        return "ck.mandatory_capture" if reply_capture else "ck.exchanges"
    if kind in ("missed_win", "allowed_loss") or reason == "win":
        return "ch.mate_in_one"
    if reason == "check":
        return "ch.check"
    return "ch.hanging_pieces"


# --------------------------------------------------------------------- detectores

def _ttt_blocks(state: Any, best: int) -> bool:
    """O melhor lance ocupa a casa em que o adversário completaria uma linha?"""
    opponent = "O" if state.to_move == "X" else "X"
    for a, b, c in LINES:
        cells = [state.board[a], state.board[b], state.board[c]]
        if cells.count(opponent) == 2 and cells.count("_") == 1:
            if (a, b, c)[cells.index("_")] == best:
                return True
    return False


def _best_reason(game_id: str, state: Any, best: str, kind: str) -> tuple[str, str | None]:
    engine = ENGINES[game_id]
    move = engine.parse_move(best)
    after = engine.apply(state, move)
    outcome = engine.outcome(after)
    if outcome is not None and outcome.winner == state.to_move:
        return "win", None
    if game_id == "tictactoe":
        return ("block", None) if _ttt_blocks(state, int(best)) else (
            "avoids_loss" if kind == "lost_position" else "keeps", None)
    if kind == "allowed_loss":
        return "avoids_loss", None
    if game_id == "checkers":
        full = next(m for m in engine.legal_moves(state) if m.path == move.path)
        if full.capture:
            n = len(full.captured)
            return "capture", f"{n} {'peça' if n == 1 else 'peças'}"
        return "keeps", None
    board: chess.Board = state.board
    if board.is_capture(move):
        victim = board.piece_at(move.to_square)
        if victim is None:  # en passant: a vítima é o peão
            return "capture", f"o peão em {chess.square_name(move.to_square)}"
        return "capture", f"{PIECE_WITH_ARTICLE[victim.piece_type]} em " \
                          f"{chess.square_name(move.to_square)}"
    if board.gives_check(move):
        return "check", None
    return "keeps", None


def _reply_capture(game_id: str, state_after: Any, reply: str) -> str | None:
    """O que a resposta do adversário captura, em texto, ou `None`."""
    engine = ENGINES[game_id]
    move = engine.parse_move(reply)
    if game_id == "checkers":
        full = next(m for m in engine.legal_moves(state_after) if m.path == move.path)
        if not full.capture:
            return None
        n = len(full.captured)
        return f"{n} {'peça' if n == 1 else 'peças'}"
    if game_id == "chess":
        board: chess.Board = state_after.board
        if not board.is_capture(move):
            return None
        victim = board.piece_at(move.to_square)
        square = chess.square_name(move.to_square)
        return f"o peão em {square}" if victim is None else (
            f"{PIECE_WITH_ARTICLE[victim.piece_type]} em {square}")
    return None


# ---------------------------------------------------------------------- análise

def _moment(game_id: str, ply: int, seat: int, state: Any, played: str, best: ev.Scored,
            played_score: int, budget: Budget) -> Moment | None:
    verdict = classify(game_id, best.score, played_score)
    if verdict is None:
        return None
    severity, kind = verdict
    engine = ENGINES[game_id]
    after = engine.apply(state, engine.parse_move(played))
    reply: str | None = None
    reply_label: str | None = None
    reply_detail: str | None = None
    reply_is_win = False
    if engine.outcome(after) is None:
        top = ev.best_move(game_id, after, budget)
        if top is not None:
            reply = top.move
            reply_label = display_move(game_id, after, reply)
            reply_detail = _reply_capture(game_id, after, reply)
            outcome = engine.outcome(engine.apply(after, engine.parse_move(reply)))
            reply_is_win = outcome is not None and outcome.winner == after.to_move
    reason, detail = _best_reason(game_id, state, best.move, kind)
    return Moment(
        ply=ply, seat=seat, severity=severity, kind=kind, loss=best.score - played_score,
        played=played, played_label=display_move(game_id, state, played),
        best=best.move, best_label=display_move(game_id, state, best.move),
        reply=reply, reply_label=reply_label, reason=reason, reason_detail=detail,
        reply_detail=reply_detail, reply_is_win=reply_is_win,
        concept_key=_concept(game_id, kind, reason, reply_detail is not None),
        position=describe_position(game_id, state),
    )


def analyze_game(game_id: str, moves: Sequence[str], user_seats: frozenset[int],
                 node_budget: int | None = None) -> GameAnalysis:
    """Reexecuta `moves` desde a posição inicial e avalia os lances dos assentos do usuário."""
    engine = ENGINES[game_id]
    budget = Budget(NODE_BUDGET[game_id] if node_budget is None else node_budget)
    state = engine.initial_state()
    flagged: list[Moment] = []
    analyzed = user_moves = 0
    truncated = False
    for ply, raw in enumerate(moves):
        seat = 1 if ply % 2 == 0 else 2
        if seat in user_seats:
            user_moves += 1
            if not truncated:
                try:
                    best = ev.best_move(game_id, state, budget)
                    if best is not None:
                        score = best.score if best.move == str(engine.parse_move(raw)) else \
                            ev.played_score(game_id, state, raw, budget)
                        analyzed += 1
                        moment = _moment(game_id, ply, seat, state, raw, best, score, budget)
                        if moment is not None:
                            flagged.append(moment)
                except BudgetExceededError:
                    truncated = True
        state = engine.apply(state, engine.parse_move(raw))
    counts = {s: sum(1 for m in flagged if m.severity == s) for s in SEVERITY_RANK}
    top = sorted(flagged, key=lambda m: (-SEVERITY_RANK[m.severity], -m.loss, m.ply))[:MAX_MOMENTS]
    return GameAnalysis(sorted(top, key=lambda m: m.ply), analyzed, user_moves, truncated, counts)


# ------------------------------------------------------------------------ texto

def move_number(game_id: str, ply: int) -> int:
    """Número do lance mostrado ao usuário: jogada a jogada na velha, lance completo no resto."""
    return ply + 1 if game_id == "tictactoe" else ply // 2 + 1


def _units(game_id: str, loss: int) -> str:
    n = max(1, round(loss / 100))
    if game_id == "checkers":
        return f"{n} {'pedra' if n == 1 else 'pedras'}"
    return f"{n} {'peão' if n == 1 else 'peões'} de valor"


_REASONS = {
    "win": "vencia a partida na hora",
    "check": "dava xeque",
    "block": "bloqueava a vitória do adversário",
    "avoids_loss": "evitava a derrota",
    "keeps": "mantinha a posição sem entregar material",
}


def explain(game_id: str, m: Moment) -> str:
    """Texto determinístico em português; cada lance ou casa citado vem do motor."""
    parts = [f"No lance {move_number(game_id, m.ply)}, você jogou {m.played_label}."]
    if m.kind == "missed_win":
        parts.append("Com esse lance, você deixou escapar uma vitória que o motor encontrou.")
    elif m.kind in ("allowed_loss", "lost_position"):
        if m.reply_label is not None:
            what = (f"vencer com {m.reply_label}" if m.reply_is_win
                    else f"forçar a vitória começando por {m.reply_label}")
            parts.append(f"Depois dele, o adversário podia {what}.")
        else:
            parts.append("Depois dele, o adversário passou a ter uma vitória forçada.")
    elif m.reply_label is not None and m.reply_detail is not None:
        parts.append(f"Depois dele, o adversário podia capturar {m.reply_detail} com "
                     f"{m.reply_label}, e a análise indica {_units(game_id, m.loss)} a menos "
                     "para você do que na melhor opção.")
    else:
        parts.append(f"Segundo a análise do motor, esse lance deixa você com "
                     f"{_units(game_id, m.loss)} a menos do que a melhor opção.")
    if m.reason == "capture":
        reason = f"capturava {m.reason_detail}"
    elif m.reason == "win" and game_id == "chess":
        reason = "dava xeque-mate"
    else:
        reason = _REASONS[m.reason]
    parts.append(f"Uma opção melhor era {m.best_label}, que {reason}.")
    return " ".join(parts)
