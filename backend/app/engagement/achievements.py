"""Definições de conquistas como dados versionados (RF-026, DT-023).

O arquivo `content/achievements.json` é a fonte; aqui só se carrega e valida. Os critérios são
um conjunto fechado, medido pelo servidor a partir de fatos reais (partidas, Academy, ranking,
desafio diário). Não existe valor monetário nem item conversível: uma conquista é só um
distintivo com título e descrição.
"""

import json
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.academy.content import GAMES

CONTENT_FILE = Path(__file__).parent / "content" / "achievements.json"

CriterionType = Literal["matches_finished", "wins", "ranked_games", "rating_at_least",
                        "exercises_correct", "concepts_mastered", "daily_completed"]
# Fatos de domínio que podem mudar o valor medido de cada critério.
TRIGGERS: dict[str, tuple[str, ...]] = {
    "matches_finished": ("match_finished",),
    "wins": ("match_finished",),
    "ranked_games": ("match_finished",),
    "rating_at_least": ("match_finished",),
    "exercises_correct": ("exercise_attempted",),
    "concepts_mastered": ("exercise_attempted",),
    "daily_completed": ("daily_challenge_completed",),
}


class AchievementsError(Exception):
    """Definições inválidas: o carregamento falha alto em vez de conceder algo errado."""


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: CriterionType
    count: int = Field(ge=1, le=100_000)  # alvo (para rating_at_least, os pontos)
    game_id: str | None = None
    mode: Literal["ai", "online"] | None = None
    min_ai_level: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def _coherent(self) -> "Criterion":
        if self.game_id is not None and self.game_id not in GAMES:
            raise ValueError(f"jogo desconhecido: {self.game_id}")
        if self.type in ("ranked_games", "rating_at_least") and self.game_id is None:
            raise ValueError("critério de ranking exige game_id")
        if self.type != "wins" and (self.mode is not None or self.min_ai_level is not None):
            raise ValueError("mode e min_ai_level só valem para 'wins'")
        if self.min_ai_level is not None and self.mode != "ai":
            raise ValueError("min_ai_level exige mode 'ai'")
        return self


class Achievement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9_]{3,48}$")
    title: str = Field(min_length=3, max_length=60)
    description: str = Field(min_length=3, max_length=200)
    game_id: str | None = None
    criterion: Criterion


class Definitions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    achievements: list[Achievement]


@cache
def load() -> Definitions:
    try:
        raw: dict[str, Any] = json.loads(CONTENT_FILE.read_text(encoding="utf-8"))
        defs = Definitions.model_validate(raw)
    except (OSError, ValueError) as exc:
        raise AchievementsError(f"achievements.json: {exc}") from exc
    keys = [a.key for a in defs.achievements]
    if len(set(keys)) != len(keys):
        raise AchievementsError("chaves de conquista duplicadas")
    return defs


def find(key: str) -> Achievement | None:
    return next((a for a in load().achievements if a.key == key), None)
