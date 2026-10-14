"""Identidade, catálogo de jogos e auditoria (Fase 1).

Revision ID: 0001
Revises:
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("email_verified_at", TZ, nullable=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("age_band", sa.String(16), nullable=False),
        sa.Column("guardian_user_id", sa.Uuid(), nullable=True),
        sa.Column("deletion_requested_at", TZ, nullable=True),
        sa.Column("terms_version", sa.String(32), nullable=False),
        sa.Column("last_login_at", TZ, nullable=True),
        sa.Column("updated_at", TZ, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.CheckConstraint("role IN ('user', 'moderator', 'admin')", name=op.f("ck_users_role")),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'pending_deletion')", name=op.f("ck_users_status")
        ),
        sa.CheckConstraint(
            "age_band IN ('under_12', '12_15', '16_17', '18_plus')", name=op.f("ck_users_age_band")
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lower")),
        sa.ForeignKeyConstraint(
            ["guardian_user_id"], ["users.id"], ondelete="SET NULL",
            name=op.f("fk_users_guardian_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(24), nullable=False),
        sa.Column("avatar_key", sa.String(32), nullable=False),
        sa.Column("bio", sa.String(160), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("show_in_ranking", sa.Boolean(), nullable=False),
        sa.Column("display_name_changed_at", TZ, nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name=op.f("fk_user_profiles_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profiles")),
    )
    op.create_index(
        "uq_user_profiles_display_name_lower",
        "user_profiles",
        [sa.text("lower(display_name)")],
        unique=True,
    )
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("theme", sa.String(8), nullable=False),
        sa.Column("motion", sa.String(8), nullable=False),
        sa.Column("sound", sa.Boolean(), nullable=False),
        sa.Column("move_confirmation", sa.Boolean(), nullable=False),
        sa.Column("piece_styles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False),
        sa.Column("allow_open_matchmaking", sa.Boolean(), nullable=False),
        sa.Column("daily_minutes_limit", sa.Integer(), nullable=True),
        sa.CheckConstraint("theme IN ('light', 'dark', 'system')", name=op.f("ck_user_preferences_theme")),
        sa.CheckConstraint(
            "motion IN ('full', 'reduced', 'none', 'system')", name=op.f("ck_user_preferences_motion")
        ),
        sa.CheckConstraint(
            "daily_minutes_limit IS NULL OR daily_minutes_limit BETWEEN 15 AND 600",
            name=op.f("ck_user_preferences_daily_minutes_limit"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name=op.f("fk_user_preferences_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_preferences")),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("last_seen_at", TZ, nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("revoked_at", TZ, nullable=True),
        sa.Column("user_agent_summary", sa.String(80), nullable=True),
        sa.Column("created_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_sessions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("target_email", sa.String(254), nullable=True),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("used_at", TZ, nullable=True),
        sa.Column("created_at", TZ, nullable=False),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'reset_password', 'guardian_link')",
            name=op.f("ck_auth_tokens_purpose"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_auth_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_tokens_token_hash")),
    )
    op.create_index(op.f("ix_auth_tokens_user_id"), "auth_tokens", ["user_id"])
    games = op.create_table(
        "games",
        sa.Column("id", sa.String(16), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("ranked_enabled", sa.Boolean(), nullable=False),
        sa.Column("rules_version", sa.String(24), nullable=False),
        sa.Column("age_rating", sa.String(2), nullable=True),
        sa.CheckConstraint(
            "age_rating IS NULL OR age_rating IN ('L', '10', '12', '14', '16', '18')",
            name=op.f("ck_games_age_rating"),
        ),
        sa.CheckConstraint(
            "NOT enabled OR age_rating IS NOT NULL", name=op.f("ck_games_enabled_requires_rating")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_games")),
    )
    # Classificação "L" proposta (doc 09 §10, a validar). Jogos são habilitados nas suas fases.
    op.bulk_insert(
        games,
        [
            {"id": "tictactoe", "name": "Jogo da velha", "enabled": False, "ranked_enabled": False,
             "rules_version": "tictactoe-1", "age_rating": "L"},
            {"id": "checkers", "name": "Damas", "enabled": False, "ranked_enabled": False,
             "rules_version": "checkers-br-1", "age_rating": "L"},
            {"id": "chess", "name": "Xadrez", "enabled": False, "ranked_enabled": False,
             "rules_version": "chess-fide-1", "age_rating": "L"},
        ],
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL",
            name=op.f("fk_audit_log_actor_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_actor_user_id"), "audit_log", ["actor_user_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("games")
    op.drop_table("auth_tokens")
    op.drop_table("sessions")
    op.drop_table("user_preferences")
    op.drop_index("uq_user_profiles_display_name_lower", table_name="user_profiles")
    op.drop_table("user_profiles")
    op.drop_table("users")
