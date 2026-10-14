"""Contratos do ranking público e das estatísticas do usuário (RF-019, RF-021)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class LeaderboardEntry(BaseModel):
    """Só dados públicos: posição, apelido, avatar, rating e partidas (nunca ID ou e-mail)."""

    rank: int
    display_name: str
    avatar_key: str
    rating: int
    games_played: int


class LeaderboardPage(BaseModel):
    game_id: str
    min_games: int
    items: list[LeaderboardEntry]
    next_cursor: str | None


class RatingChangeOut(BaseModel):
    seat: int
    before: int
    after: int


class ModeStats(BaseModel):
    mode: Literal["ai", "online_casual", "online_ranked"]
    played: int
    wins: int
    losses: int
    draws: int
    win_rate: float | None


class StreakOut(BaseModel):
    kind: Literal["win", "loss", "draw", "none"]
    length: int


class RatingPoint(BaseModel):
    match_id: uuid.UUID
    created_at: datetime
    before: int
    after: int
    delta: int


class RatingInfo(BaseModel):
    rating: int
    games_played: int
    provisional: bool
    # Aparece no ranking público? (perfil público + escolha de aparecer + partidas suficientes)
    listed: bool
    games_until_listed: int
    history: list[RatingPoint]


class GameStats(BaseModel):
    game_id: str
    name: str
    played: int
    wins: int
    losses: int
    draws: int
    win_rate: float | None
    by_mode: list[ModeStats]
    streak: StreakOut
    rating: RatingInfo | None


class StatsOut(BaseModel):
    games: list[GameStats]
