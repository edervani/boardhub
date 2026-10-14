"""Limite diário de tempo (RF-034) e preferência de notação de lances (RF-007).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_usage",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("seconds >= 0", name=op.f("ck_daily_usage_seconds")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_daily_usage_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "day", name=op.f("pk_daily_usage")),
    )
    op.add_column(
        "user_preferences",
        sa.Column("move_notation", sa.String(16), nullable=False,
                  server_default="algebraic_pt"),
    )
    op.alter_column("user_preferences", "move_notation", server_default=None)
    op.create_check_constraint(
        op.f("ck_user_preferences_move_notation"), "user_preferences",
        "move_notation IN ('algebraic_pt', 'san', 'uci')")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_user_preferences_move_notation"), "user_preferences",
                       type_="check")
    op.drop_column("user_preferences", "move_notation")
    op.drop_table("daily_usage")
