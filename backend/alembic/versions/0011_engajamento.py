"""Conquistas, desafio diário e notificações in-app (RF-026, RF-027, RF-028).

Revision ID: 0011
Revises: 0009
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_achievements",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("achievement_key", sa.String(48), nullable=False),
        sa.Column("definition_version", sa.String(16), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_user_achievements_user_id_users"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "achievement_key", name=op.f("pk_user_achievements")),
    )
    op.create_table(
        "daily_challenge_results",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("exercise_id", sa.String(40), nullable=False),
        sa.Column("content_version", sa.String(24), nullable=False),
        sa.Column("answer", sa.String(64), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_daily_challenge_results_user_id_users"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"],
                                name=op.f("fk_daily_challenge_results_game_id_games")),
        sa.PrimaryKeyConstraint("user_id", "game_id", "day",
                                name=op.f("pk_daily_challenge_results")),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dedupe_key", sa.String(80), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_notifications_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(op.f("ix_notifications_user_id_created_at"), "notifications",
                    ["user_id", "created_at"])
    op.create_index(op.f("uq_notifications_unread_dedupe"), "notifications",
                    ["user_id", "dedupe_key"], unique=True,
                    postgresql_where=sa.text("read_at IS NULL AND dedupe_key IS NOT NULL"))
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_notification_preferences_user_id_users"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "kind", name=op.f("pk_notification_preferences")),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_index(op.f("uq_notifications_unread_dedupe"), table_name="notifications",
                  postgresql_where=sa.text("read_at IS NULL AND dedupe_key IS NOT NULL"))
    op.drop_index(op.f("ix_notifications_user_id_created_at"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("daily_challenge_results")
    op.drop_table("user_achievements")
