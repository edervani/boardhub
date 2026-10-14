"""Catálogo de jogos (doc 05 §2, RF-033)."""

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Faixas da classificação indicativa brasileira.
AGE_RATINGS = ("L", "10", "12", "14", "16", "18")


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint(
            "age_rating IS NULL OR age_rating IN ('L', '10', '12', '14', '16', '18')",
            name="age_rating",
        ),
        # RF-033: jogo sem classificação não pode ser habilitado.
        CheckConstraint("NOT enabled OR age_rating IS NOT NULL", name="enabled_requires_rating"),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ranked_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rules_version: Mapped[str] = mapped_column(String(24))
    age_rating: Mapped[str | None] = mapped_column(String(2))
