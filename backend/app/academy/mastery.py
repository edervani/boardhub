"""Domínio de conceitos e revisão espaçada (RF-025, doc 08 §6). Funções puras, sem banco.

Pendência P-18: o doc 08 propõe alfa = 0,25 "a calibrar", mas com 0,25 cinco acertos seguidos
dão apenas 0,763 e nunca chegariam a 0,8, o que contradiz CA-025 ("5 acertos em 3 exercícios
em 2 dias concedem domínio"). Usa-se 0,30 (cinco acertos ⇒ 0,832) até o responsável decidir.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

ALPHA = 0.30
MASTERY_THRESHOLD = 0.8
MIN_CORRECT_ATTEMPTS = 5
MIN_DISTINCT_EXERCISES = 3
MIN_DISTINCT_DAYS = 2
REVIEW_INTERVALS_DAYS = (3, 7, 21, 60)

NOT_STARTED = "not_started"
IN_PRACTICE = "in_practice"
MASTERED = "mastered"
IN_REVIEW = "in_review"
STATUSES = (NOT_STARTED, IN_PRACTICE, MASTERED, IN_REVIEW)


@dataclass(frozen=True)
class Evidence:
    """Tentativas corretas do usuário no conceito, já incluindo a atual."""

    correct_attempts: int
    distinct_exercises: int
    distinct_days: int


@dataclass(frozen=True)
class Progress:
    mastery: float = 0.0
    status: str = NOT_STARTED
    review_stage: int = 0
    next_review_at: datetime | None = None
    mastered_at: datetime | None = None


def reward(correct: bool, hint_level: int) -> float:
    """1 sem dica; 0,6 com a dica 1; 0,3 com as dicas 2 e 3; 0 se errou."""
    if not correct:
        return 0.0
    return {0: 1.0, 1: 0.6}.get(hint_level, 0.3)


def next_mastery(old: float, correct: bool, hint_level: int) -> float:
    value = old + ALPHA * (reward(correct, hint_level) - old)
    return round(min(1.0, max(0.0, value)), 4)


def meets_mastery(mastery: float, evidence: Evidence) -> bool:
    """Uma resposta isolada nunca concede domínio (doc 08 §6)."""
    return (mastery >= MASTERY_THRESHOLD
            and evidence.correct_attempts >= MIN_CORRECT_ATTEMPTS
            and evidence.distinct_exercises >= MIN_DISTINCT_EXERCISES
            and evidence.distinct_days >= MIN_DISTINCT_DAYS)


def review_due(progress: Progress, now: datetime) -> bool:
    return (progress.status == MASTERED and progress.next_review_at is not None
            and now >= progress.next_review_at)


def _schedule(stage: int, now: datetime) -> datetime:
    return now + timedelta(days=REVIEW_INTERVALS_DAYS[stage])


def apply_attempt(progress: Progress, *, correct: bool, hint_level: int, evidence: Evidence,
                  now: datetime) -> Progress:
    mastery = next_mastery(progress.mastery, correct, hint_level)
    updated = replace(progress, mastery=mastery)
    if progress.status == MASTERED:
        if not review_due(progress, now):
            return updated
        if correct:
            stage = min(progress.review_stage + 1, len(REVIEW_INTERVALS_DAYS) - 1)
            return replace(updated, review_stage=stage, next_review_at=_schedule(stage, now))
        # Erro numa revisão devida: o conceito volta a "em revisão" e o intervalo reinicia.
        return replace(updated, status=IN_REVIEW, review_stage=0, next_review_at=None)
    if progress.status == IN_REVIEW:
        if correct:
            return replace(updated, status=MASTERED, review_stage=0,
                           next_review_at=_schedule(0, now))
        return updated
    if meets_mastery(mastery, evidence):
        return replace(updated, status=MASTERED, review_stage=0,
                       next_review_at=_schedule(0, now), mastered_at=now)
    return replace(updated, status=IN_PRACTICE)
