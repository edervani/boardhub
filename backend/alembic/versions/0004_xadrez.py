"""Habilita o xadrez (Fase 4). UCI cabe em `match_moves.move` (64) e os motivos de fim já existem.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A classificação indicativa é obrigatória para habilitar (CA-033); mantém a já definida.
    op.execute("UPDATE games SET age_rating = 'L' WHERE id = 'chess' AND age_rating IS NULL")
    op.execute("UPDATE games SET enabled = true WHERE id = 'chess'")


def downgrade() -> None:
    op.execute("DELETE FROM matches WHERE game_id = 'chess'")
    op.execute("UPDATE games SET enabled = false WHERE id = 'chess'")
