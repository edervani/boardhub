"""Ratings Elo por jogo e histórico de variações (doc 05 §2, RF-019)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.game_engines.elo import INITIAL_RATING
from app.models.base import Base, new_id, utcnow


class Rating(Base):
    """Rating atual. Só o servidor grava, na transação que encerra a partida ranqueada."""

    __tablename__ = "ratings"
    __table_args__ = (
        CheckConstraint("rating >= 0", name="rating_nonnegative"),
        CheckConstraint("games_played >= 0", name="games_played_nonnegative"),
        Index("ix_ratings_game_id_rating", "game_id", "rating"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    rating: Mapped[int] = mapped_column(Integer, default=INITIAL_RATING)
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RatingHistory(Base):
    """Trilha auditável: uma linha por (usuário, partida) — o UNIQUE garante idempotência."""

    __tablename__ = "rating_history"
    __table_args__ = (
        UniqueConstraint("user_id", "match_id"),
        Index("ix_rating_history_user_id_game_id_created_at", "user_id", "game_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    before: Mapped[int] = mapped_column(Integer)
    after: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
