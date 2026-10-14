"""Conquistas, desafio diário e notificações in-app (RF-026, RF-027, RF-028; doc 06 §2)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentAuth, DbSession
from app.schemas.engagement import (
    AchievementsOut,
    DailyAttemptIn,
    DailyAttemptOut,
    DailyChallengesOut,
    NotificationListOut,
    NotificationPreferencesIn,
    NotificationPreferencesOut,
)
from app.services import (
    achievement_service,
    daily_challenge_service,
    notification_service,
)

router = APIRouter(tags=["engajamento"])
NO_CONTENT = status.HTTP_204_NO_CONTENT


@router.get("/me/achievements")
def achievements(auth: CurrentAuth, db: DbSession) -> AchievementsOut:
    return achievement_service.list_for(db, auth.user)


@router.get("/daily-challenge")
def daily_challenge(auth: CurrentAuth, db: DbSession) -> DailyChallengesOut:
    return daily_challenge_service.today(db, auth.user)


@router.post("/daily-challenge/{game_id}/attempt")
def daily_attempt(game_id: str, body: DailyAttemptIn, auth: CurrentAuth,
                  db: DbSession) -> DailyAttemptOut:
    return daily_challenge_service.submit(db, auth.user, game_id, body.answer)


@router.get("/me/notifications")
def notifications(auth: CurrentAuth, db: DbSession, unread_only: bool = False,
                  limit: Annotated[int, Query(ge=1, le=50)] = 20) -> NotificationListOut:
    return notification_service.list_notifications(db, auth.user, unread_only, limit)


@router.post("/me/notifications/read-all", status_code=NO_CONTENT)
def read_all(auth: CurrentAuth, db: DbSession) -> Response:
    notification_service.mark_all_read(db, auth.user)
    return Response(status_code=NO_CONTENT)


@router.post("/me/notifications/{notification_id}/read", status_code=NO_CONTENT)
def read_one(notification_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> Response:
    notification_service.mark_read(db, auth.user, notification_id)
    return Response(status_code=NO_CONTENT)


@router.get("/me/notification-preferences")
def get_prefs(auth: CurrentAuth, db: DbSession) -> NotificationPreferencesOut:
    return notification_service.get_preferences(db, auth.user)


@router.put("/me/notification-preferences")
def put_prefs(body: NotificationPreferencesIn, auth: CurrentAuth,
              db: DbSession) -> NotificationPreferencesOut:
    return notification_service.update_preferences(db, auth.user, body.kinds)
