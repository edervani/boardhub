"""Correção determinística de exercícios (RF-023, doc 08 §5).

Quem decide se a resposta está certa é o motor: o conteúdo declara um *objetivo* ("vencer agora",
"evitar a derrota", "dar xeque"…) e o objetivo é avaliado sobre o estado real. Só o objetivo
`listed` usa uma lista de lances escrita à mão, e os testes a conferem contra a avaliação do
motor. Nenhuma função aqui revela a solução na mensagem de erro.
"""

from dataclasses import dataclass
from typing import Any

import chess

from app.academy.content import Exercise, ExerciseRef
from app.academy.positions import build_state
from app.ai.mentor import evaluation
from app.ai.mentor.evaluation import ENGINES
from app.ai.mentor.notation import PIECE_NAMES, display_move, ttt_cell
from app.game_engines.base import IllegalMove


class InvalidAnswerError(Exception):
    """A resposta não é um lance legal (ou não é uma alternativa) deste exercício."""


@dataclass(frozen=True)
class Grade:
    correct: bool
    feedback: str


def exercise_state(ref: ExerciseRef) -> Any:
    assert ref.exercise.position is not None
    return build_state(ref.content.game_id, ref.exercise.position)


def legal_moves(ref: ExerciseRef) -> list[str]:
    engine = ENGINES[ref.content.game_id]
    return [str(m) for m in engine.legal_moves(exercise_state(ref))]


def _kings(squares: tuple[str, ...], color: str) -> int:
    return sum(1 for p in squares if p == color.upper())


def _opponent_win(game_id: str, state: Any) -> str | None:
    """Um lance do adversário que vence a partida logo em seguida, se existir."""
    engine = ENGINES[game_id]
    opponent = state.to_move
    for reply in engine.legal_moves(state):
        outcome = engine.outcome(engine.apply(state, reply))
        if outcome is not None and outcome.winner == opponent:
            return str(reply)
    return None


def _free_capture(state: Any, move: chess.Move) -> bool:
    board: chess.Board = state.board
    if not board.is_capture(move):
        return False
    after = board.copy(stack=False)
    after.push(move)
    return not any(after.is_capture(reply) and reply.to_square == move.to_square
                   for reply in after.legal_moves)


def _judge_move(ex: Exercise, game_id: str, state: Any, move_str: str) -> Grade:
    engine = ENGINES[game_id]
    try:
        move = engine.parse_move(move_str)
        new_state = engine.apply(state, move)
    except IllegalMove as exc:
        raise InvalidAnswerError(str(exc)) from exc
    goal = ex.goal
    mover = state.to_move
    if goal == "win_now":
        outcome = engine.outcome(new_state)
        ok = outcome is not None and outcome.winner == mover
        return Grade(ok, "Muito bem!" if ok else
                       "Esse lance é legal, mas não encerra a partida a seu favor agora.")
    if goal == "block_loss":
        outcome = engine.outcome(new_state)
        if outcome is not None and outcome.winner == mover:
            return Grade(True, "Muito bem!")
        refutation = _opponent_win(game_id, new_state)
        if refutation is None:
            return Grade(True, "Muito bem!")
        shown = display_move(game_id, new_state, refutation)
        return Grade(False, f"Depois desse lance, o adversário vence com {shown}.")
    if goal == "optimal":
        scores = evaluation.move_scores(game_id, state)
        ok = scores[str(move)] == max(scores.values())
        return Grade(ok, "Muito bem!" if ok else
                       "Esse lance é legal, mas existe um lance melhor nesta posição.")
    if goal == "promote":
        ok = _kings(new_state.squares, mover) > _kings(state.squares, mover)
        return Grade(ok, "Muito bem!" if ok else "Esse lance não promove nenhuma pedra.")
    if goal == "give_check":
        ok = bool(state.board.gives_check(move))
        return Grade(ok, "Muito bem!" if ok else "Esse lance não dá xeque.")
    if goal == "free_capture":
        ok = _free_capture(state, move)
        return Grade(ok, "Muito bem!" if ok else
                       "Esse lance não ganha uma peça de graça: ou não captura, ou a peça "
                       "capturada pode ser recapturada.")
    ok = str(move) in ex.accepted  # goal == "listed"
    return Grade(ok, "Muito bem!" if ok else "Esse não é o lance pedido neste exercício.")


def grade(ref: ExerciseRef, answer: str) -> Grade:
    """Corrige uma resposta. Levanta `InvalidAnswerError` se ela não for uma resposta válida."""
    ex = ref.exercise
    if ex.type == "rule_quiz":
        if answer not in {o.id for o in ex.options}:
            raise InvalidAnswerError("alternativa inexistente")
        ok = answer == ex.correct_option
        return Grade(ok, "Isso mesmo!" if ok else
                     "Essa alternativa não está correta. Releia o resumo da lição.")
    verdict = _judge_move(ex, ref.content.game_id, exercise_state(ref), answer)
    return Grade(verdict.correct, verdict.feedback)


def correct_moves(ref: ExerciseRef) -> list[str]:
    """Todos os lances legais que o motor considera corretos (solução calculada, não escrita)."""
    ex = ref.exercise
    if ex.type != "best_move":
        return []
    game_id = ref.content.game_id
    state = exercise_state(ref)
    scores = evaluation.move_scores(game_id, state) if ex.goal == "optimal" else None
    out = []
    for move in ENGINES[game_id].legal_moves(state):
        if scores is not None:
            if scores[str(move)] == max(scores.values()):
                out.append(str(move))
        elif _judge_move(ex, game_id, state, str(move)).correct:
            out.append(str(move))
    return out


# ------------------------------------------------------------------ dicas (doc 08 §5)

HINT_LEVELS = (1, 2, 3)


def hint_text(ref: ExerciseRef, level: int) -> str:
    """Nível 1: região; nível 2: peça a mover; nível 3: explicação do conceito."""
    if level not in HINT_LEVELS:
        raise ValueError("nível de dica inválido")
    ex = ref.exercise
    concept = ref.content.concept(ref.concept_key)
    if level == 3:
        return concept.summary
    if ex.type == "rule_quiz":
        if level == 1:
            return "Elimine as alternativas que contradizem o resumo da lição."
        wrong = next(o for o in ex.options if o.id != ex.correct_option)
        return f"A alternativa «{wrong.text}» não está correta."
    game_id = ref.content.game_id
    solutions = correct_moves(ref)
    first = solutions[0]
    state = exercise_state(ref)
    if game_id == "tictactoe":
        cell = int(first)
        return (f"Observe a linha {cell // 3 + 1}." if level == 1
                else f"Jogue na {ttt_cell(cell)}.")
    if game_id == "checkers":
        origin = int(first.replace("x", "-").split("-")[0])
        if level == 1:
            half = "de cima (casas 1 a 16)" if origin <= 16 else "de baixo (casas 17 a 32)"
            return f"A peça que deve se mover está na metade {half} do tabuleiro."
        return f"Mova a peça da casa {origin}."
    if level == 1:
        return f"O lance termina na coluna {first[2]}."
    piece = state.board.piece_at(chess.parse_square(first[:2]))
    name = PIECE_NAMES[piece.piece_type] if piece else "peça"
    article = "a" if name in ("torre", "dama") else "o"
    return f"Mova {article} {name} que está em {first[:2]}."
