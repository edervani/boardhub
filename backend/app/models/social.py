"""Amizades, bloqueios, convites diretos e denúncias (RF-031, RF-032, doc 05 §2)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, new_id

FRIENDSHIP_STATUSES = ("pending", "accepted", "declined")
INVITATION_STATUSES = ("pending", "accepted", "declined", "cancelled")
REPORT_TARGETS = ("user", "match")
REPORT_REASONS = ("offensive_name", "offensive_bio", "cheating", "harassment", "other")
REPORT_STATUSES = ("open", "resolved")
REPORT_ACTIONS = ("warn", "suspend", "archive")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Friendship(CreatedAt, Base):
    """Par de contas. `user_low_id < user_high_id` garante uma linha por par (sem duplicata)."""

    __tablename__ = "friendships"
    __table_args__ = (
        CheckConstraint("user_low_id < user_high_id", name="pair_order"),
        CheckConstraint("requested_by IN (user_low_id, user_high_id)", name="requester_in_pair"),
        CheckConstraint(_in("status", FRIENDSHIP_STATUSES), name="status"),
        UniqueConstraint("user_low_id", "user_high_id"),
        Index("ix_friendships_user_high_id", "user_high_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_low_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user_high_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(8), default="pending")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserBlock(CreatedAt, Base):
    __tablename__ = "user_blocks"
    __table_args__ = (
        CheckConstraint("blocker_id <> blocked_id", name="not_self"),
        UniqueConstraint("blocker_id", "blocked_id"),
        Index("ix_user_blocks_blocked_id", "blocked_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    blocker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    blocked_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class DirectInvitation(CreatedAt, Base):
    """Convite de partida entre amigos: aponta para a sala por convite já existente (RF-011)."""

    __tablename__ = "direct_invitations"
    __table_args__ = (
        CheckConstraint(_in("status", INVITATION_STATUSES), name="status"),
        CheckConstraint("sender_id <> recipient_id", name="not_self"),
        Index("ix_direct_invitations_recipient_id_status", "recipient_id", "status"),
        Index("ix_direct_invitations_sender_id", "sender_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(10), default="pending")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Report(CreatedAt, Base):
    """Denúncia. O denunciante nunca é exposto por nenhuma rota (RF-031, sem retaliação)."""

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(_in("target_type", REPORT_TARGETS), name="target_type"),
        CheckConstraint(_in("reason", REPORT_REASONS), name="reason"),
        CheckConstraint(_in("status", REPORT_STATUSES), name="status"),
        CheckConstraint(
            f"resolution_action IS NULL OR {_in('resolution_action', REPORT_ACTIONS)}",
            name="resolution_action",
        ),
        Index("ix_reports_status_created_at", "status", "created_at"),
        Index("ix_reports_reporter_id_created_at", "reporter_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"))
    # Conta denunciada; a denúncia some junto com a conta (minimização, RF-030).
    target_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    target_type: Mapped[str] = mapped_column(String(8))
    # Partida denunciada (só `target_type = match`); some junto com a partida.
    match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(8), default="open")
    resolution_action: Mapped[str | None] = mapped_column(String(8))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
