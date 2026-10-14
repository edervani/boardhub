"""Habilita as damas (Fase 3): lances longos e novo motivo de fim de partida.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = ("normal", "resign", "abandon", "agreement", "repetition", "fifty_move", "stalemate",
       "timeout", "annulled")
NEW = (*OLD, "kings_only")


def _in(values: tuple[str, ...]) -> str:
    return "end_reason IS NULL OR end_reason IN (" + ", ".join(repr(v) for v in values) + ")"


def upgrade() -> None:
    # Capturas em cadeia podem ter até 12 casas ("15x24x31x..."): 16 caracteres não bastam.
    op.alter_column("match_moves", "move", existing_type=sa.String(16), type_=sa.String(64))
    op.drop_constraint(op.f("ck_matches_end_reason"), "matches", type_="check")
    op.create_check_constraint(op.f("ck_matches_end_reason"), "matches", _in(NEW))
    op.execute("UPDATE games SET enabled = true WHERE id = 'checkers'")


def downgrade() -> None:
    op.execute("DELETE FROM matches WHERE game_id = 'checkers'")
    op.execute("UPDATE games SET enabled = false WHERE id = 'checkers'")
    op.execute("UPDATE matches SET end_reason = 'normal' WHERE end_reason = 'kings_only'")
    op.drop_constraint(op.f("ck_matches_end_reason"), "matches", type_="check")
    op.create_check_constraint(op.f("ck_matches_end_reason"), "matches", _in(OLD))
    op.alter_column("match_moves", "move", existing_type=sa.String(64), type_=sa.String(16))
