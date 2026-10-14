"""Conta, perfil, preferências, sessões e tokens (doc 05 §2)."""

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
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, new_id, utcnow

ROLES = ("user", "moderator", "admin")
STATUSES = ("active", "suspended", "pending_deletion")
AGE_BANDS = ("under_12", "12_15", "16_17", "18_plus")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class User(CreatedAt, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("role", ROLES), name="role"),
        CheckConstraint(_in("status", STATUSES), name="status"),
        CheckConstraint(_in("age_band", AGE_BANDS), name="age_band"),
        CheckConstraint("email = lower(email)", name="email_lower"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    # E-mail normalizado em minúsculas pela aplicação (substitui citext — doc 05).
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[str] = mapped_column(String(16), default="user")
    status: Mapped[str] = mapped_column(String(24), default="active")
    age_band: Mapped[str] = mapped_column(String(16))
    guardian_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # RF-030: exclusão pedida pelo responsável só pode ser cancelada por ele.
    deletion_by_guardian: Mapped[bool] = mapped_column(Boolean, default=False)
    terms_version: Mapped[str] = mapped_column(String(32))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    profile: Mapped["UserProfile"] = relationship(back_populates="user", cascade="all, delete")
    preferences: Mapped["UserPreferences"] = relationship(
        back_populates="user", cascade="all, delete"
    )

    @property
    def is_minor(self) -> bool:
        return self.age_band != "18_plus"


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(24))
    avatar_key: Mapped[str] = mapped_column(String(32), default="default")
    bio: Mapped[str | None] = mapped_column(String(160))
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    show_in_ranking: Mapped[bool] = mapped_column(Boolean, default=True)
    display_name_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="profile")


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint(_in("theme", ("light", "dark", "system")), name="theme"),
        CheckConstraint(_in("motion", ("full", "reduced", "none", "system")), name="motion"),
        CheckConstraint(
            "daily_minutes_limit IS NULL OR daily_minutes_limit BETWEEN 15 AND 600",
            name="daily_minutes_limit",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    theme: Mapped[str] = mapped_column(String(8), default="system")
    motion: Mapped[str] = mapped_column(String(8), default="system")
    sound: Mapped[bool] = mapped_column(Boolean, default=True)
    move_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    piece_styles: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    locale: Mapped[str] = mapped_column(String(8), default="pt-BR")
    # Controles de supervisão (RF-034). Só o responsável altera em contas de menores.
    allow_open_matchmaking: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_minutes_limit: Mapped[int | None] = mapped_column(Integer)

    user: Mapped[User] = relationship(back_populates="preferences")


class AuthSession(CreatedAt, Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent_summary: Mapped[str | None] = mapped_column(String(80))


class AuthToken(CreatedAt, Base):
    __tablename__ = "auth_tokens"
    __table_args__ = (
        CheckConstraint(
            _in("purpose", ("verify_email", "reset_password", "guardian_link")), name="purpose"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(24))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    # Só para guardian_link: e-mail do responsável convidado (dado necessário ao RF-034).
    target_email: Mapped[str | None] = mapped_column(String(254))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Nome de exibição único sem diferenciar maiúsculas (substitui citext — doc 05).
Index(
    "uq_user_profiles_display_name_lower",
    func.lower(UserProfile.display_name),
    unique=True,
)
