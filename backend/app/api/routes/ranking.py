"""Ranking público por jogo e estatísticas do próprio usuário (RF-019, RF-021)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ClientIp, CurrentAuth, DbSession, OptionalAuth
from app.schemas.ranking import LeaderboardPage, StatsOut
from app.services import rating_service, stats_service

router = APIRouter(tags=["ranking"])


@router.get("/ranking/{game_id}")
def leaderboard(game_id: str, auth: OptionalAuth, db: DbSession, ip: ClientIp,
                cursor: Annotated[str | None, Query(max_length=64)] = None,
                limit: Annotated[int, Query(ge=1, le=100)] = 20) -> LeaderboardPage:
    band = auth.user.age_band if auth else None
    return rating_service.leaderboard(db, band, game_id[:16], cursor, limit, ip)


@router.get("/me/stats")
def my_stats(auth: CurrentAuth, db: DbSession,
             game_id: Annotated[str | None, Query(max_length=16)] = None) -> StatsOut:
    return stats_service.my_stats(db, auth.user, game_id)
