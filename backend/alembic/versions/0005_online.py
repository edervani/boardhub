"""Partidas online entre humanos (Fase 2c): convites, fila, ofertas de empate e presença.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("matches", sa.Column("invite_code_hash", sa.LargeBinary(32), nullable=True))
    op.add_column("matches", sa.Column("invite_expires_at", TZ, nullable=True))
    op.add_column("matches", sa.Column("invite_creator_seat", sa.SmallInteger(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_matches_invite_code_hash"), "matches", ["invite_code_hash"]
    )
    op.create_check_constraint(
        op.f("ck_matches_invite_creator_seat"), "matches",
        "invite_creator_seat IS NULL OR invite_creator_seat IN (1, 2)",
    )
    op.add_column("match_players", sa.Column("disconnected_at", TZ, nullable=True))

    op.create_table(
        "draw_offers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("by_seat", sa.SmallInteger(), nullable=False),
        sa.Column("at_ply", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("responded_at", TZ, nullable=True),
        sa.CheckConstraint("by_seat IN (1, 2)", name=op.f("ck_draw_offers_by_seat")),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'expired')",
            name=op.f("ck_draw_offers_status"),
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_draw_offers_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_draw_offers")),
    )
    op.create_index("ix_draw_offers_match_id_status", "draw_offers", ["match_id", "status"])

    op.create_table(
        "matchmaking_queue",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(16), nullable=False),
        sa.Column("enqueued_at", TZ, nullable=False),
        sa.Column("last_seen_at", TZ, nullable=False),
        sa.Column("matched_match_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_matchmaking_queue_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name=op.f("fk_matchmaking_queue_game_id_games")
        ),
        sa.ForeignKeyConstraint(
            ["matched_match_id"], ["matches.id"],
            name=op.f("fk_matchmaking_queue_matched_match_id_matches"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_matchmaking_queue")),
    )
    op.create_index(
        "ix_matchmaking_queue_game_id_enqueued_at", "matchmaking_queue", ["game_id", "enqueued_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_matchmaking_queue_game_id_enqueued_at", table_name="matchmaking_queue")
    op.drop_table("matchmaking_queue")
    op.drop_index("ix_draw_offers_match_id_status", table_name="draw_offers")
    op.drop_table("draw_offers")
    op.drop_column("match_players", "disconnected_at")
    op.drop_constraint(op.f("ck_matches_invite_creator_seat"), "matches", type_="check")
    op.drop_constraint(op.f("uq_matches_invite_code_hash"), "matches", type_="unique")
    op.drop_column("matches", "invite_creator_seat")
    op.drop_column("matches", "invite_expires_at")
    op.drop_column("matches", "invite_code_hash")
