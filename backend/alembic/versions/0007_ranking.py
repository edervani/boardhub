"""Ranking Elo por jogo (Fase 5, RF-019, RF-021): ratings, histórico e fila ranqueada.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "ratings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(16), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("games_played", sa.Integer(), nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.CheckConstraint("rating >= 0", name=op.f("ck_ratings_rating_nonnegative")),
        sa.CheckConstraint("games_played >= 0", name=op.f("ck_ratings_games_played_nonnegative")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ratings_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], name=op.f("fk_ratings_game_id_games")),
        sa.PrimaryKeyConstraint("user_id", "game_id", name=op.f("pk_ratings")),
    )
    op.create_index("ix_ratings_game_id_rating", "ratings", ["game_id", "rating"])

    op.create_table(
        "rating_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(16), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("before", sa.Integer(), nullable=False),
        sa.Column("after", sa.Integer(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_rating_history_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name=op.f("fk_rating_history_game_id_games")
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_rating_history_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rating_history")),
        sa.UniqueConstraint("user_id", "match_id", name=op.f("uq_rating_history_user_id")),
    )
    op.create_index(
        "ix_rating_history_user_id_game_id_created_at", "rating_history",
        ["user_id", "game_id", "created_at"],
    )

    op.add_column("match_players", sa.Column("rating_before", sa.Integer(), nullable=True))
    op.add_column("match_players", sa.Column("rating_after", sa.Integer(), nullable=True))
    op.add_column(
        "matchmaking_queue",
        sa.Column("ranked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # P-21: damas só entram no ranking depois de resolvida a conferência de regras (P-16).
    op.execute("UPDATE games SET ranked_enabled = true WHERE id = 'chess'")


def downgrade() -> None:
    op.execute("UPDATE games SET ranked_enabled = false")
    op.drop_column("matchmaking_queue", "ranked")
    op.drop_column("match_players", "rating_after")
    op.drop_column("match_players", "rating_before")
    op.drop_index("ix_rating_history_user_id_game_id_created_at", table_name="rating_history")
    op.drop_table("rating_history")
    op.drop_index("ix_ratings_game_id_rating", table_name="ratings")
    op.drop_table("ratings")
