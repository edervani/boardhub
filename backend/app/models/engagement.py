"""Conquistas, desafio diário e notificações in-app (RF-026, RF-027, RF-028; DT-023).

As definições de conquistas ficam em arquivo versionado (como o conteúdo da Academy); aqui só
há dados da pessoa. Nenhuma coluna guarda valor monetário. Todas as tabelas dependem de
`users` com exclusão em cascata (RF-030).
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, new_id

NOTIFICATION_KINDS = ("your_turn", "match_ended", "opponent_disconnected", "achievement_earned")


class UserAchievement(Base):
    """Conquista concedida. A chave primária torna a concessão idempotente (CA-026)."""

    __tablename__ = "user_achievements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    achievement_key: Mapped[str] = mapped_column(String(48), primary_key=True)
    definition_version: Mapped[str] = mapped_column(String(16))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DailyChallengeResult(Base):
    """Única tentativa válida da pessoa no desafio de um jogo num dia civil de São Paulo."""

    __tablename__ = "daily_challenge_results"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    exercise_id: Mapped[str] = mapped_column(String(40))
    content_version: Mapped[str] = mapped_column(String(24))
    answer: Mapped[str] = mapped_column(String(64))
    correct: Mapped[bool] = mapped_column(Boolean)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Notification(CreatedAt, Base):
    """Aviso in-app. `dedupe_key` junta avisos repetidos ainda não lidos (um por partida)."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
        Index("uq_notifications_unread_dedupe", "user_id", "dedupe_key", unique=True,
              postgresql_where=text("read_at IS NULL AND dedupe_key IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dedupe_key: Mapped[str | None] = mapped_column(String(80))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreference(Base):
    """Tipo de aviso que a pessoa desativou ou reativou (sem linha = padrão: ativo)."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean)
