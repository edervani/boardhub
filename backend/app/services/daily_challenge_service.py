"""Desafio diário (RF-027, DT-023): um exercício da Academy por jogo e por dia.

O exercício é determinístico (data civil de America/Sao_Paulo + jogo, `engagement.daily`), igual
para todas as pessoas, e a correção vem do motor, como na Academy. Vale uma tentativa válida por
jogo e dia. Sem sequência (streak): faltar um dia não tira nada, só há o total acumulado, e o
desafio não altera o domínio dos conceitos da Academy nem o rating.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.academy import grading
from app.core import clock
from app.core.errors import ProblemError
from app.core.ratelimit import limiter
from app.engagement import daily
from app.models import DailyChallengeResult, Game, User
from app.schemas.engagement import (
    DailyAttemptOut,
    DailyChallengeOut,
    DailyChallengesOut,
)
from app.services import academy_service, catalog_service, domain_events, usage_service


def _visible(db: Session, user: User) -> list[Game]:
    return [g for g in catalog_service.visible_games(db, user.age_band) if daily.pool(g.id)]


def _completed_total(db: Session, user: User) -> int:
    return int(db.scalar(select(func.count()).select_from(DailyChallengeResult).where(
        DailyChallengeResult.user_id == user.id)) or 0)


def _results(db: Session, user: User, day: date) -> dict[str, DailyChallengeResult]:
    return {r.game_id: r for r in db.scalars(select(DailyChallengeResult).where(
        DailyChallengeResult.user_id == user.id, DailyChallengeResult.day == day))}


def today(db: Session, user: User) -> DailyChallengesOut:
    now = clock.now()
    day, resets_at = usage_service.local_day(now), usage_service.next_reset(now)
    results = _results(db, user, day)
    challenges: list[DailyChallengeOut] = []
    for game in _visible(db, user):
        ref = daily.pick(game.id, day)
        if ref is None:
            continue
        result = results.get(game.id)
        challenges.append(DailyChallengeOut(
            game_id=game.id, game_name=game.name, day=day, resets_at=resets_at,
            status="answered" if result else "pending",
            correct=result.correct if result else None,
            exercise=academy_service.exercise_view(ref),
            explanation=ref.exercise.explanation if result else None))
    return DailyChallengesOut(day=day, resets_at=resets_at,
                              completed_total=_completed_total(db, user), challenges=challenges)


def submit(db: Session, user: User, game_id: str, answer: str) -> DailyAttemptOut:
    limiter.hit(f"daily-attempt:{user.id}", 30, 60)
    if game_id not in {g.id for g in _visible(db, user)}:
        raise ProblemError(404, "not_found", "Jogo não encontrado")
    now = clock.now()
    day = usage_service.local_day(now)
    ref = daily.pick(game_id, day)
    if ref is None:
        raise ProblemError(404, "not_found", "Sem desafio para este jogo hoje")
    if db.get(DailyChallengeResult, (user.id, game_id, day)) is not None:
        raise ProblemError(409, "daily_already_answered", "Desafio de hoje já respondido",
                           "Volte amanhã para um novo desafio. Você pode treinar na Academy.")
    try:
        graded = grading.grade(ref, answer)
    except grading.InvalidAnswerError as exc:  # resposta inválida não gasta a tentativa do dia
        raise ProblemError(422, "invalid_answer", "Resposta inválida", str(exc)) from exc
    try:
        with db.begin_nested():
            db.add(DailyChallengeResult(
                user_id=user.id, game_id=game_id, day=day, exercise_id=ref.exercise.id,
                content_version=ref.content.content_version, answer=answer,
                correct=graded.correct, completed_at=now))
    except IntegrityError as exc:  # duas requisições ao mesmo tempo: só a primeira vale
        raise ProblemError(409, "daily_already_answered", "Desafio de hoje já respondido") from exc
    domain_events.emit_new(db, domain_events.DAILY_CHALLENGE_COMPLETED, user.id,
                           game_id=game_id, day=day.isoformat(), correct=graded.correct)
    usage_service.touch(db, user, now)  # RF-034: conta no tempo do menor, sem bloquear
    db.commit()
    return DailyAttemptOut(correct=graded.correct, feedback=graded.feedback,
                           explanation=ref.exercise.explanation,
                           completed_total=_completed_total(db, user))

