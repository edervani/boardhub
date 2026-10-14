"""Amizades, bloqueios, convites diretos e denúncias (RF-031, RF-032).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def _fk(table: str, col: str, ref: str, ondelete: str,
        nullable: bool = False) -> list[sa.SchemaItem]:
    return [
        sa.Column(col, sa.Uuid(), nullable=nullable),
        sa.ForeignKeyConstraint([col], [f"{ref}.id"], name=op.f(f"fk_{table}_{col}_{ref}"),
                                ondelete=ondelete),
    ]


def _table(name: str, *items: list[sa.SchemaItem] | sa.SchemaItem) -> None:
    flat: list[sa.SchemaItem] = []
    for item in items:
        flat.extend(item if isinstance(item, list) else [item])
    op.create_table(name, *flat)


def upgrade() -> None:
    _table(
        "friendships",
        sa.Column("id", sa.Uuid(), nullable=False),
        _fk("friendships", "user_low_id", "users", "CASCADE"),
        _fk("friendships", "user_high_id", "users", "CASCADE"),
        _fk("friendships", "requested_by", "users", "CASCADE"),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.CheckConstraint("user_low_id < user_high_id", name=op.f("ck_friendships_pair_order")),
        sa.CheckConstraint("requested_by IN (user_low_id, user_high_id)",
                           name=op.f("ck_friendships_requester_in_pair")),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'declined')",
                           name=op.f("ck_friendships_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_friendships")),
        sa.UniqueConstraint("user_low_id", "user_high_id",
                            name=op.f("uq_friendships_user_low_id")),
    )
    op.create_index("ix_friendships_user_high_id", "friendships", ["user_high_id"])

    _table(
        "user_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        _fk("user_blocks", "blocker_id", "users", "CASCADE"),
        _fk("user_blocks", "blocked_id", "users", "CASCADE"),
        _created_at(),
        sa.CheckConstraint("blocker_id <> blocked_id", name=op.f("ck_user_blocks_not_self")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_blocks")),
        sa.UniqueConstraint("blocker_id", "blocked_id", name=op.f("uq_user_blocks_blocker_id")),
    )
    op.create_index("ix_user_blocks_blocked_id", "user_blocks", ["blocked_id"])

    _table(
        "direct_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        _fk("direct_invitations", "match_id", "matches", "CASCADE"),
        _fk("direct_invitations", "sender_id", "users", "CASCADE"),
        _fk("direct_invitations", "recipient_id", "users", "CASCADE"),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'declined', 'cancelled')",
                           name=op.f("ck_direct_invitations_status")),
        sa.CheckConstraint("sender_id <> recipient_id",
                           name=op.f("ck_direct_invitations_not_self")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_direct_invitations")),
    )
    op.create_index("ix_direct_invitations_recipient_id_status", "direct_invitations",
                    ["recipient_id", "status"])
    op.create_index("ix_direct_invitations_sender_id", "direct_invitations", ["sender_id"])

    _table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        _fk("reports", "reporter_id", "users", "SET NULL", nullable=True),
        _fk("reports", "target_user_id", "users", "CASCADE"),
        sa.Column("target_type", sa.String(8), nullable=False),
        _fk("reports", "match_id", "matches", "CASCADE", nullable=True),
        sa.Column("reason", sa.String(16), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("resolution_action", sa.String(8), nullable=True),
        _fk("reports", "resolved_by", "users", "SET NULL", nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.CheckConstraint("target_type IN ('user', 'match')",
                           name=op.f("ck_reports_target_type")),
        sa.CheckConstraint(
            "reason IN ('offensive_name', 'offensive_bio', 'cheating', 'harassment', 'other')",
            name=op.f("ck_reports_reason")),
        sa.CheckConstraint("status IN ('open', 'resolved')", name=op.f("ck_reports_status")),
        sa.CheckConstraint(
            "resolution_action IS NULL OR resolution_action IN ('warn', 'suspend', 'archive')",
            name=op.f("ck_reports_resolution_action")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )
    op.create_index("ix_reports_status_created_at", "reports", ["status", "created_at"])
    op.create_index("ix_reports_reporter_id_created_at", "reports",
                    ["reporter_id", "created_at"])


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("direct_invitations")
    op.drop_table("user_blocks")
    op.drop_table("friendships")
