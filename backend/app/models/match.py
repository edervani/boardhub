"""Partidas, jogadores e lances (doc 05 §2). `matches.state` é a fonte da verdade."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, new_id, utcnow

MODES = ("local", "ai", "online_casual", "online_ranked")
STATUSES = ("waiting", "in_progress", "finished", "aborted", "annulled")
RESULTS = ("p1_win", "p2_win", "draw")
END_REASONS = (
    "normal", "resign", "abandon", "agreement", "repetition", "fifty_move", "stalemate",
    "timeout", "annulled", "kings_only",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Match(CreatedAt, Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint(_in("mode", MODES), name="mode"),
        CheckConstraint(_in("status", STATUSES), name="status"),
        CheckConstraint(f"result IS NULL OR {_in('result', RESULTS)}", name="result"),
        CheckConstraint(
            f"end_reason IS NULL OR {_in('end_reason', END_REASONS)}", name="end_reason"
        ),
        CheckConstraint("ai_level IS NULL OR ai_level BETWEEN 1 AND 5", name="ai_level"),
        CheckConstraint(
            "invite_creator_seat IS NULL OR invite_creator_seat IN (1, 2)",
            name="invite_creator_seat",
        ),
        UniqueConstraint("invite_code_hash"),
        Index("ix_matches_status_game_id", "status", "game_id"),
        Index("ix_matches_updated_at", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ply: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[str | None] = mapped_column(String(8))
    end_reason: Mapped[str | None] = mapped_column(String(16))
    rules_version: Mapped[str] = mapped_column(String(24))
    ai_level: Mapped[int | None] = mapped_column(SmallInteger)
    ai_seed: Mapped[int | None] = mapped_column(Integer)  # reprodutibilidade da IA (doc 07)
    # Sala por convite (RF-011): só o HMAC do código é guardado; NULL nos demais modos.
    invite_code_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Assento escolhido pelo criador; NULL = sorteio quando o segundo jogador entra.
    invite_creator_seat: Mapped[int | None] = mapped_column(SmallInteger)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MatchPlayer(Base):
    __tablename__ = "match_players"
    __table_args__ = (
        CheckConstraint("seat IN (1, 2)", name="seat"),
        CheckConstraint("NOT (is_ai AND user_id IS NOT NULL)", name="ai_without_user"),
        Index("ix_match_players_user_id_match_id", "user_id", "match_id"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    seat: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    # SET NULL preserva a partida do oponente após exclusão de conta (RF-030).
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    removed_account: Mapped[bool] = mapped_column(Boolean, default=False)
    # Presença (RF-014): NULL = conectado; preenchido = desconectado desde esse instante.
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchMove(Base):
    __tablename__ = "match_moves"
    __table_args__ = (
        # Idempotência: o mesmo `client_move_id` nunca grava dois lances (RF-013).
        UniqueConstraint("match_id", "client_move_id"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    ply: Mapped[int] = mapped_column(Integer, primary_key=True)
    seat: Mapped[int] = mapped_column(SmallInteger)
    move: Mapped[str] = mapped_column(String(64))
    client_move_id: Mapped[uuid.UUID] = mapped_column()
    state_after_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


DRAW_OFFER_STATUSES = ("pending", "accepted", "declined", "expired")


class DrawOffer(Base):
    """Oferta de empate por acordo (RF-015). Só uma `pending` por partida."""

    __tablename__ = "draw_offers"
    __table_args__ = (
        CheckConstraint("by_seat IN (1, 2)", name="by_seat"),
        CheckConstraint(_in("status", DRAW_OFFER_STATUSES), name="status"),
        Index("ix_draw_offers_match_id_status", "match_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    by_seat: Mapped[int] = mapped_column(SmallInteger)
    at_ply: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(8), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QueueEntry(Base):
    """Fila de pareamento (RF-012): uma entrada por usuário; some ao parear ou sair."""

    __tablename__ = "matchmaking_queue"
    __table_args__ = (Index("ix_matchmaking_queue_game_id_enqueued_at", "game_id", "enqueued_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Atualizado a cada consulta do cliente; entradas sem consulta recente são ignoradas.
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Preenchido quando outro jogador pareou com este; o cliente consome na próxima consulta.
    matched_match_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("matches.id", ondelete="SET NULL")
    )
