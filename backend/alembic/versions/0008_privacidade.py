"""Direitos do titular: exportação de dados e exclusão de conta (Fase 7, RF-029/RF-030).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
# A 0007 (ranking) ainda não está em main; ao mesclá-la, trocar para "0007".
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("deletion_by_guardian", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )
    op.alter_column("users", "deletion_by_guardian", server_default=None)
    op.create_table(
        "data_export_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.CheckConstraint("status IN ('ready')", name=op.f("ck_data_export_requests_status")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_data_export_requests_user_id_users"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"],
                                name=op.f("fk_data_export_requests_requested_by_user_id_users"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_export_requests")),
    )
    op.create_index("ix_data_export_requests_user_id_created_at", "data_export_requests",
                    ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_data_export_requests_user_id_created_at",
                  table_name="data_export_requests")
    op.drop_table("data_export_requests")
    op.drop_column("users", "deletion_by_guardian")
