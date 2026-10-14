"""Partidas contra a IA e locais, lances, histórico e motor sem estado (doc 06 §2)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import ClientIp, CurrentAuth, DbSession, OptionalAuth, VerifiedAuth
from app.core.ratelimit import limiter
from app.realtime.hub import hub
from app.schemas.matches import (
    ActiveMatchOut,
    CreateMatchIn,
    DrawResponseIn,
    EngineApplyIn,
    EngineApplyOut,
    JoinIn,
    MatchOut,
    MatchPage,
    MoveIn,
    MoveOut,
    QueueIn,
    QueueStatusOut,
)
from app.services import engine_service, match_service, online_service

router = APIRouter(tags=["partidas"])


@router.post("/matches", status_code=201)
def create_match(body: CreateMatchIn, auth: CurrentAuth, db: DbSession) -> MatchOut:
    if body.mode in ("online_casual", "online_ranked"):  # convite: código só aparece aqui (RF-011)
        return online_service.create_invite(db, auth.user, body.game_id, body.preferred_seat,
                                            body.mode)
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
    result = match_service.submit_move_result(db, auth.user, match_id, body.expected_ply,
                                              body.move, body.client_move_id)
    hub.publish_all(result.events)
    return result.view


@router.post("/matches/{match_id}/resign")
def resign(match_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> MatchOut:
    out, events = match_service.resign_result(db, auth.user, match_id)
    hub.publish_all(events)
    return out


@router.post("/matches/{match_id}/claim-draw")
def claim_draw(match_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> MatchOut:
    out, events = match_service.claim_draw_result(db, auth.user, match_id)
    hub.publish_all(events)
    return out


@router.post("/matches/join")
def join_match(body: JoinIn, auth: CurrentAuth, db: DbSession) -> MatchOut:
    out, events = online_service.join_invite(db, auth.user, body.invite_code)
    hub.publish_all(events)
    return out


@router.post("/matches/{match_id}/cancel", status_code=204)
def cancel_invite(match_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> None:
    online_service.cancel_invite(db, auth.user, match_id)


@router.post("/matches/{match_id}/draw-offer")
def draw_offer(match_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> MatchOut:
    out, events = online_service.offer_draw(db, auth.user, match_id)
    hub.publish_all(events)
    return out


@router.post("/matches/{match_id}/draw-response")
def draw_response(match_id: uuid.UUID, body: DrawResponseIn, auth: CurrentAuth,
                  db: DbSession) -> MatchOut:
    out, events = online_service.respond_draw(db, auth.user, match_id, body.accept)
    hub.publish_all(events)
    return out


@router.post("/matches/{match_id}/claim-abandon")
def claim_abandon(match_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> MatchOut:
    out, events = online_service.claim_abandon(db, auth.user, match_id)
    hub.publish_all(events)
    return out


@router.post("/matchmaking/queue", status_code=202)
def enter_queue(body: QueueIn, response: Response, auth: VerifiedAuth,
                db: DbSession) -> QueueStatusOut:
    out, events = online_service.enter_queue(db, auth.user, body.game_id, body.ranked)
    hub.publish_all(events)
    if out.state == "matched":
        response.status_code = 200
    return out


@router.get("/matchmaking/queue")
def queue_status(auth: CurrentAuth, db: DbSession) -> QueueStatusOut:
    out, events = online_service.queue_status(db, auth.user)  # a fila ranqueada pareia aqui
    hub.publish_all(events)
    return out


@router.delete("/matchmaking/queue", status_code=204)
def leave_queue(auth: CurrentAuth, db: DbSession) -> None:
    online_service.leave_queue(db, auth.user)


@router.get("/me/active-matches")
def active_matches(auth: CurrentAuth, db: DbSession) -> list[ActiveMatchOut]:
    return online_service.active_matches(db, auth.user)


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
