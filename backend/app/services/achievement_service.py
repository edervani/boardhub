"""Conquistas (RF-026, DT-023): concessão idempotente pelo servidor a partir de fatos reais.

O cliente nunca informa nem pede uma conquista. Cada critério é medido no banco (partidas
encerradas, Academy, rating, desafio diário); a chave primária de `user_achievements` garante
que a mesma conquista não seja concedida duas vezes, mesmo com eventos repetidos ou
concorrentes. Conquista é só um distintivo: não há valor monetário, troca nem vantagem.
"""

import uuid

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core import clock
from app.engagement import achievements as definitions
from app.engagement.achievements import Achievement, Criterion
from app.models import (
    DailyChallengeResult,
    ExerciseAttempt,
    Match,
    MatchPlayer,
    Rating,
    SkillProgress,
    User,
    UserAchievement,
)
from app.schemas.engagement import AchievementOut, AchievementsOut, ShowcaseItemOut
from app.services import notification_service
from app.services.domain_events import DomainEvent

ONLINE_MODES = ("online_casual", "online_ranked")


def _finished_matches(uid: uuid.UUID, c: Criterion) -> Select[tuple[int]]:
    stmt = (select(func.count()).select_from(Match)
            .join(MatchPlayer, MatchPlayer.match_id == Match.id)
            .where(MatchPlayer.user_id == uid, MatchPlayer.is_ai.is_(False),
                   Match.status == "finished", Match.mode != "local"))
    if c.game_id is not None:
        stmt = stmt.where(Match.game_id == c.game_id)
    return stmt


def _measure_matches(db: Session, uid: uuid.UUID, c: Criterion) -> int:
    return int(db.scalar(_finished_matches(uid, c)) or 0)


def _measure_wins(db: Session, uid: uuid.UUID, c: Criterion) -> int:
    stmt = _finished_matches(uid, c).where(or_(
        and_(Match.result == "p1_win", MatchPlayer.seat == 1),
        and_(Match.result == "p2_win", MatchPlayer.seat == 2)))
    if c.mode == "ai":
        stmt = stmt.where(Match.mode == "ai")
        if c.min_ai_level is not None:
            stmt = stmt.where(Match.ai_level >= c.min_ai_level)
    elif c.mode == "online":
        stmt = stmt.where(Match.mode.in_(ONLINE_MODES))
    return int(db.scalar(stmt) or 0)


def _rating_row(db: Session, uid: uuid.UUID, c: Criterion) -> Rating | None:
    return db.get(Rating, (uid, c.game_id)) if c.game_id else None


def _measure_ranked_games(db: Session, uid: uuid.UUID, c: Criterion) -> int:
    row = _rating_row(db, uid, c)
    return row.games_played if row else 0


def _measure_rating(db: Session, uid: uuid.UUID, c: Criterion) -> int:
    row = _rating_row(db, uid, c)
    return row.rating if row and row.games_played > 0 else 0


def _measure_exercises(db: Session, uid: uuid.UUID, c: Criterion) -> int:
    stmt = select(func.count(func.distinct(ExerciseAttempt.exercise_id))).where(
        ExerciseAttempt.user_id == uid, ExerciseAttempt.correct.is_(True))
    if c.game_id is not None:
        stmt = stmt.where(ExerciseAttempt.game_id == c.game_id)
    return int(db.scalar(stmt) or 0)


def _measure_concepts(db: Session, uid: uuid.UUID, c: Criterion) -> int:
    stmt = select(func.count()).select_from(SkillProgress).where(
        SkillProgress.user_id == uid, SkillProgress.mastered_at.is_not(None))
    if c.game_id is not None:
        stmt = stmt.where(SkillProgress.game_id == c.game_id)
    return int(db.scalar(stmt) or 0)


def _measure_daily(db: Session, uid: uuid.UUID, c: Criterion) -> int:
    stmt = select(func.count()).select_from(DailyChallengeResult).where(
        DailyChallengeResult.user_id == uid)
    if c.game_id is not None:
        stmt = stmt.where(DailyChallengeResult.game_id == c.game_id)
    return int(db.scalar(stmt) or 0)


_MEASURES = {
    "matches_finished": _measure_matches,
    "wins": _measure_wins,
    "ranked_games": _measure_ranked_games,
    "rating_at_least": _measure_rating,
    "exercises_correct": _measure_exercises,
    "concepts_mastered": _measure_concepts,
    "daily_completed": _measure_daily,
}


def measure(db: Session, user_id: uuid.UUID, criterion: Criterion) -> int:
    return _MEASURES[criterion.type](db, user_id, criterion)


def _earned(db: Session, user_id: uuid.UUID) -> dict[str, UserAchievement]:
    return {r.achievement_key: r for r in db.scalars(
        select(UserAchievement).where(UserAchievement.user_id == user_id))}


def _grant(db: Session, user_id: uuid.UUID, a: Achievement, version: str) -> bool:
    """Concede de forma idempotente; True só para quem de fato a recebeu agora."""
    stmt = pg_insert(UserAchievement).values(
        user_id=user_id, achievement_key=a.key, definition_version=version,
        earned_at=clock.now()).on_conflict_do_nothing().returning(UserAchievement.achievement_key)
    if db.execute(stmt).first() is None:
        return False
    notification_service.notify(db, user_id, "achievement_earned",
                                {"achievement_key": a.key, "title": a.title})
    return True


def evaluate(db: Session, user_id: uuid.UUID, event_kind: str) -> list[str]:
    """Confere as conquistas ligadas ao fato `event_kind`; devolve as chaves recém-concedidas."""
    defs = definitions.load()
    earned = _earned(db, user_id)
    granted: list[str] = []
    for a in defs.achievements:
        if a.key in earned or event_kind not in definitions.TRIGGERS[a.criterion.type]:
            continue
        if measure(db, user_id, a.criterion) >= a.criterion.count \
                and _grant(db, user_id, a, defs.version):
            granted.append(a.key)
    return granted


def on_event(db: Session, event: DomainEvent) -> None:
    evaluate(db, event.user_id, event.kind)


# ---------- leitura ----------

def list_for(db: Session, user: User) -> AchievementsOut:
    defs = definitions.load()
    earned = _earned(db, user.id)
    items: list[AchievementOut] = []
    for a in defs.achievements:
        row = earned.get(a.key)
        target = a.criterion.count
        progress = target if row else min(measure(db, user.id, a.criterion), target)
        items.append(AchievementOut(
            key=a.key, title=a.title, description=a.description, game_id=a.game_id,
            earned=row is not None, earned_at=row.earned_at if row else None,
            progress=progress, target=target))
    return AchievementsOut(definition_version=defs.version, earned_count=len(earned), items=items)


def showcase(db: Session, user_id: uuid.UUID) -> list[ShowcaseItemOut]:
    """Vitrine do perfil público: só o que a pessoa conquistou (nunca o que falta)."""
    out: list[ShowcaseItemOut] = []
    for key, row in sorted(_earned(db, user_id).items(), key=lambda kv: kv[1].earned_at):
        a = definitions.find(key)
        if a is not None:  # definição removida numa versão futura: some da vitrine
            out.append(ShowcaseItemOut(key=key, title=a.title, earned_at=row.earned_at))
    return out
