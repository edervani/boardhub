"""BoardHub Academy: tentativas, domínio, dicas, avaliação inicial e cache de análises (Fase 6).

O conteúdo das lições fica em arquivos versionados (DT-017); estas tabelas guardam só dados da
pessoa e são apagadas em cascata com a conta.

Revision ID: 0006
Revises: 0004
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
# Se a migração 0005 (partidas online) for mesclada antes, trocar para "0005" ao rebasear.
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "exercise_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(16), nullable=False),
        sa.Column("exercise_id", sa.String(40), nullable=False),
        sa.Column("concept_key", sa.String(40), nullable=False),
        sa.Column("content_version", sa.String(24), nullable=False),
        sa.Column("answer", sa.String(64), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("hint_level", sa.SmallInteger(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", TZ, nullable=False),
        sa.CheckConstraint("hint_level BETWEEN 0 AND 3", name=op.f("ck_exercise_attempts_hint_level")),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0",
                           name=op.f("ck_exercise_attempts_duration_ms")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_exercise_attempts_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"],
                                name=op.f("fk_exercise_attempts_game_id_games")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercise_attempts")),
    )
    op.create_index("ix_exercise_attempts_user_id_game_id_concept_key", "exercise_attempts",
                    ["user_id", "game_id", "concept_key"])

    op.create_table(
        "user_skill_progress",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(16), nullable=False),
        sa.Column("concept_key", sa.String(40), nullable=False),
        sa.Column("mastery", sa.Double(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("review_stage", sa.SmallInteger(), nullable=False),
        sa.Column("next_review_at", TZ, nullable=True),
        sa.Column("mastered_at", TZ, nullable=True),
        sa.Column("updated_at", TZ, nullable=False),
        sa.CheckConstraint("status IN ('not_started', 'in_practice', 'mastered', 'in_review')",
                           name=op.f("ck_user_skill_progress_status")),
        sa.CheckConstraint("mastery >= 0 AND mastery <= 1",
                           name=op.f("ck_user_skill_progress_mastery")),
        sa.CheckConstraint("review_stage BETWEEN 0 AND 3",
                           name=op.f("ck_user_skill_progress_review_stage")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_user_skill_progress_user_id_users"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"],
                                name=op.f("fk_user_skill_progress_game_id_games")),
        sa.PrimaryKeyConstraint("user_id", "game_id", "concept_key",
                                name=op.f("pk_user_skill_progress")),
    )

    op.create_table(
        "exercise_hints",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.String(40), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.CheckConstraint("level BETWEEN 1 AND 3", name=op.f("ck_exercise_hints_level")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_exercise_hints_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "exercise_id", name=op.f("pk_exercise_hints")),
    )

    op.create_table(
        "academy_placements",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.String(16), nullable=False),
        sa.Column("declared", sa.String(16), nullable=False),
        sa.Column("suggested_ai_level", sa.SmallInteger(), nullable=False),
        sa.Column("completed_at", TZ, nullable=False),
        sa.CheckConstraint("suggested_ai_level BETWEEN 1 AND 5",
                           name=op.f("ck_academy_placements_suggested_ai_level")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_academy_placements_user_id_users"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"],
                                name=op.f("fk_academy_placements_game_id_games")),
        sa.PrimaryKeyConstraint("user_id", "game_id", name=op.f("pk_academy_placements")),
    )

    op.create_table(
        "match_analyses",
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("engine_version", sa.String(32), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"],
                                name=op.f("fk_match_analyses_match_id_matches"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_match_analyses_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("match_id", "user_id", name=op.f("pk_match_analyses")),
    )


def downgrade() -> None:
    op.drop_table("match_analyses")
    op.drop_table("academy_placements")
    op.drop_table("exercise_hints")
    op.drop_table("user_skill_progress")
    op.drop_index("ix_exercise_attempts_user_id_game_id_concept_key",
                  table_name="exercise_attempts")
    op.drop_table("exercise_attempts")
