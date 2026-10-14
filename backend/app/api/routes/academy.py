"""BoardHub Academy e análise pós-partida (RF-022 a RF-025, doc 06 §2)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentAuth, DbSession
from app.schemas.academy import (
    AnalysisOut,
    AttemptIn,
    AttemptOut,
    ExerciseOut,
    HintIn,
    HintOut,
    LessonsOut,
    PlacementIn,
    PlacementOut,
    ProgressOut,
    TrackOut,
)
from app.services import academy_service, analysis_service

router = APIRouter(tags=["academy"])


@router.get("/academy/tracks")
def tracks(auth: CurrentAuth, db: DbSession) -> list[TrackOut]:
    return academy_service.list_tracks(db, auth.user)


@router.get("/academy/progress")
def progress(auth: CurrentAuth, db: DbSession,
             game_id: Annotated[str | None, Query(max_length=16)] = None) -> ProgressOut:
    return academy_service.get_progress(db, auth.user, game_id)


@router.get("/academy/exercises/{exercise_id}")
def get_exercise(exercise_id: str, auth: CurrentAuth, db: DbSession) -> ExerciseOut:
    return academy_service.get_exercise(db, auth.user, exercise_id)


@router.post("/academy/exercises/{exercise_id}/hints")
def reveal_hint(exercise_id: str, body: HintIn, auth: CurrentAuth, db: DbSession) -> HintOut:
    return academy_service.reveal_hint(db, auth.user, exercise_id, body.level)


@router.post("/academy/exercises/{exercise_id}/attempts")
def submit_attempt(exercise_id: str, body: AttemptIn, auth: CurrentAuth,
                   db: DbSession) -> AttemptOut:
    return academy_service.submit_attempt(db, auth.user, exercise_id, body.answer,
                                          body.duration_ms)


@router.get("/academy/{game_id}/lessons")
def lessons(game_id: str, auth: CurrentAuth, db: DbSession) -> LessonsOut:
    return academy_service.get_lessons(db, auth.user, game_id)


@router.post("/academy/{game_id}/placement")
def placement(game_id: str, body: PlacementIn, auth: CurrentAuth, db: DbSession) -> PlacementOut:
    return academy_service.placement_step(
        db, auth.user, game_id, body.declared, [(a.exercise_id, a.answer) for a in body.answers])


@router.get("/matches/{match_id}/analysis")
def analysis(match_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> AnalysisOut:
    return analysis_service.get_analysis(db, auth.user, match_id)
