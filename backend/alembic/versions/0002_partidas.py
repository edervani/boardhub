"""Partidas, jogadores e lances; habilita o jogo da velha (Fase 2b).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(8), nullable=True),
        sa.Column("end_reason", sa.String(16), nullable=True),
        sa.Column("rules_version", sa.String(24), nullable=False),
        sa.Column("ai_level", sa.SmallInteger(), nullable=True),
        sa.Column("ai_seed", sa.Integer(), nullable=True),
        sa.Column("started_at", TZ, nullable=True),
        sa.Column("finished_at", TZ, nullable=True),
        sa.Column("updated_at", TZ, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.CheckConstraint(
            "mode IN ('local', 'ai', 'online_casual', 'online_ranked')",
            name=op.f("ck_matches_mode"),
        ),
        sa.CheckConstraint(
            "status IN ('waiting', 'in_progress', 'finished', 'aborted', 'annulled')",
            name=op.f("ck_matches_status"),
        ),
        sa.CheckConstraint(
            "result IS NULL OR result IN ('p1_win', 'p2_win', 'draw')",
            name=op.f("ck_matches_result"),
        ),
        sa.CheckConstraint(
            "end_reason IS NULL OR end_reason IN ('normal', 'resign', 'abandon', 'agreement', "
            "'repetition', 'fifty_move', 'stalemate', 'timeout', 'annulled')",
            name=op.f("ck_matches_end_reason"),
        ),
        sa.CheckConstraint(
            "ai_level IS NULL OR ai_level BETWEEN 1 AND 5", name=op.f("ck_matches_ai_level")
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], name=op.f("fk_matches_game_id_games")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matches")),
    )
    op.create_index("ix_matches_status_game_id", "matches", ["status", "game_id"])
    op.create_index("ix_matches_updated_at", "matches", ["updated_at"])

    op.create_table(
        "match_players",
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("seat", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("is_ai", sa.Boolean(), nullable=False),
        sa.Column("removed_account", sa.Boolean(), nullable=False),
        sa.CheckConstraint("seat IN (1, 2)", name=op.f("ck_match_players_seat")),
        sa.CheckConstraint(
            "NOT (is_ai AND user_id IS NOT NULL)", name=op.f("ck_match_players_ai_without_user")
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_match_players_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_match_players_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("match_id", "seat", name=op.f("pk_match_players")),
    )
    op.create_index("ix_match_players_user_id_match_id", "match_players", ["user_id", "match_id"])

    op.create_table(
        "match_moves",
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("seat", sa.SmallInteger(), nullable=False),
        sa.Column("move", sa.String(16), nullable=False),
        sa.Column("client_move_id", sa.Uuid(), nullable=False),
        sa.Column("state_after_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_match_moves_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("match_id", "ply", name=op.f("pk_match_moves")),
        sa.UniqueConstraint("match_id", "client_move_id", name=op.f("uq_match_moves_match_id")),
    )
    # Motor, IA e testes do jogo da velha existem; os demais jogos seguem desabilitados.
    op.execute("UPDATE games SET enabled = true WHERE id = 'tictactoe'")


def downgrade() -> None:
    op.execute("UPDATE games SET enabled = false WHERE id = 'tictactoe'")
    op.drop_table("match_moves")
    op.drop_index("ix_match_players_user_id_match_id", table_name="match_players")
    op.drop_table("match_players")
    op.drop_index("ix_matches_updated_at", table_name="matches")
    op.drop_index("ix_matches_status_game_id", table_name="matches")
    op.drop_table("matches")
