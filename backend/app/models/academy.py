"""BoardHub Academy: tentativas, domínio por conceito, dicas, avaliação inicial e análises.

O conteúdo (lições e exercícios) fica em arquivos versionados (DT-018); aqui só há dados da
pessoa. Todas as tabelas dependem de `users` com exclusão em cascata (RF-030).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, new_id, utcnow

SKILL_STATUSES = ("not_started", "in_practice", "mastered", "in_review")


class ExerciseAttempt(CreatedAt, Base):
    """Evidência para o domínio (doc 05). Imutável: nunca é atualizada."""

    __tablename__ = "exercise_attempts"
    __table_args__ = (
        CheckConstraint("hint_level BETWEEN 0 AND 3", name="hint_level"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="duration_ms"),
        Index("ix_exercise_attempts_user_id_game_id_concept_key", "user_id", "game_id",
              "concept_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    exercise_id: Mapped[str] = mapped_column(String(40))
    concept_key: Mapped[str] = mapped_column(String(40))
    content_version: Mapped[str] = mapped_column(String(24))
    answer: Mapped[str] = mapped_column(String(64))
    correct: Mapped[bool] = mapped_column(Boolean)
    hint_level: Mapped[int] = mapped_column(SmallInteger)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class SkillProgress(Base):
    __tablename__ = "user_skill_progress"
    __table_args__ = (
        CheckConstraint("status IN ('not_started', 'in_practice', 'mastered', 'in_review')",
                        name="status"),
        CheckConstraint("mastery >= 0 AND mastery <= 1", name="mastery"),
        CheckConstraint("review_stage BETWEEN 0 AND 3", name="review_stage"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    concept_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    mastery: Mapped[float] = mapped_column(Double, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="not_started")
    review_stage: Mapped[int] = mapped_column(SmallInteger, default=0)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mastered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ExerciseHint(Base):
    """Maior nível de dica já revelado ao usuário num exercício ainda não respondido.

    O servidor, e não o cliente, decide quantas dicas contam contra o ganho de domínio.
    """

    __tablename__ = "exercise_hints"
    __table_args__ = (CheckConstraint("level BETWEEN 1 AND 3", name="level"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    level: Mapped[int] = mapped_column(SmallInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PlacementResult(Base):
    """Última avaliação inicial concluída por jogo (refazer só após 30 dias)."""

    __tablename__ = "academy_placements"
    __table_args__ = (
        CheckConstraint("suggested_ai_level BETWEEN 1 AND 5", name="suggested_ai_level"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    declared: Mapped[str] = mapped_column(String(16))
    suggested_ai_level: Mapped[int] = mapped_column(SmallInteger)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MatchAnalysis(CreatedAt, Base):
    """Cache da análise do Mentor por (partida, usuário): evita repetir o custo (doc 08 §8)."""

    __tablename__ = "match_analyses"

    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    engine_version: Mapped[str] = mapped_column(String(32))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
