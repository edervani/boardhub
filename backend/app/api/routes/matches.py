"""Partidas contra a IA e locais, lances, histórico e motor sem estado (doc 06 §2)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ClientIp, CurrentAuth, DbSession, OptionalAuth
from app.core.ratelimit import limiter
from app.schemas.matches import (
    CreateMatchIn,
    EngineApplyIn,
    EngineApplyOut,
    MatchOut,
    MatchPage,
    MoveIn,
    MoveOut,
)
from app.services import engine_service, match_service

router = APIRouter(tags=["partidas"])


@router.post("/matches", status_code=201)
def create_match(body: CreateMatchIn, auth: CurrentAuth, db: DbSession) -> MatchOut:
    return match_service.create_match(db, auth.user, body.game_id, body.mode, body.ai_level,
                                      body.preferred_seat)


@router.get("/matches/{match_id}")
def get_match(match_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> MatchOut:
    return match_service.get_match(db, auth.user, match_id)


@router.get("/matches/{match_id}/moves")
def moves(match_id: uuid.UUID, auth: CurrentAuth, db: DbSession,
          since_ply: Annotated[int, Query(ge=0, le=10_000)] = 0) -> list[MoveOut]:
    return [MoveOut(ply=m.ply, seat=m.seat, move=m.move, created_at=m.created_at)
            for m in match_service.list_moves(db, auth.user, match_id, since_ply)]


@router.post("/matches/{match_id}/moves")
def submit_move(match_id: uuid.UUID, body: MoveIn, auth: CurrentAuth, db: DbSession) -> MatchOut:
    return match_service.submit_move(db, auth.user, match_id, body.expected_ply, body.move,
                                     body.client_move_id)


@router.post("/matches/{match_id}/resign")
def resign(match_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> MatchOut:
    return match_service.resign(db, auth.user, match_id)


@router.get("/me/matches")
def my_matches(auth: CurrentAuth, db: DbSession,
               game_id: Annotated[str | None, Query(max_length=16)] = None,
               mode: Annotated[str | None, Query(max_length=16)] = None,
               status: Annotated[str | None, Query(max_length=16)] = None,
               cursor: Annotated[str | None, Query(max_length=200)] = None,
               limit: Annotated[int, Query(ge=1, le=100)] = 20) -> MatchPage:
    return match_service.list_matches(db, auth.user, game_id, mode, status, cursor, limit)


@router.post("/engines/{game_id}/apply")
def engine_apply(game_id: str, body: EngineApplyIn, auth: OptionalAuth, db: DbSession,
                 ip: ClientIp) -> EngineApplyOut:
    limiter.hit(f"engine:{ip}", 120, 60)
    return engine_service.apply_stateless(db, auth.user.age_band if auth else None, game_id,
                                          body.state, body.move)
