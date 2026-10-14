"""Catálogo de jogos filtrado pela classificação indicativa (RF-033)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Game

RATING_MIN_AGE = {"L": 0, "10": 10, "12": 12, "14": 14, "16": 16, "18": 18}
RATING_LABEL = {"L": "Livre", "10": "10 anos", "12": "12 anos", "14": "14 anos",
                "16": "16 anos", "18": "18 anos"}
# Idade mínima garantida de cada faixa autodeclarada (conservador: limite inferior).
BAND_MIN_AGE = {"under_12": 0, "12_15": 12, "16_17": 16, "18_plus": 18}


def visible_games(db: Session, age_band: str | None) -> list[Game]:
    """Visitante (sem faixa) vê somente jogos Livres."""
    limit = BAND_MIN_AGE.get(age_band, 0) if age_band else 0
    games = db.scalars(select(Game).where(Game.enabled.is_(True)).order_by(Game.id)).all()
    return [g for g in games if g.age_rating and RATING_MIN_AGE[g.age_rating] <= limit]
