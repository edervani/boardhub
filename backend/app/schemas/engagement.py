"""Contratos de conquistas, desafio diário e notificações (doc 06 §2, RF-026–028)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.academy import ExerciseOut
from app.schemas.auth import Strict

# ---------- conquistas ----------


class AchievementOut(BaseModel):
    key: str
    title: str
    description: str
    game_id: str | None
    earned: bool
    earned_at: datetime | None
    progress: int  # medido pelo servidor, limitado ao alvo
    target: int


class AchievementsOut(BaseModel):
    definition_version: str
    earned_count: int
    items: list[AchievementOut]


class ShowcaseItemOut(BaseModel):
    key: str
    title: str
    earned_at: datetime


# ---------- desafio diário ----------


class DailyChallengeOut(BaseModel):
    game_id: str
    game_name: str
    day: date
    resets_at: datetime
    status: str  # pending | answered
    correct: bool | None
    exercise: ExerciseOut
    explanation: str | None  # só depois de responder


class DailyChallengesOut(BaseModel):
    day: date
    resets_at: datetime
    completed_total: int  # total acumulado: faltar um dia nunca zera nada
    challenges: list[DailyChallengeOut]


class DailyAttemptIn(Strict):
    answer: str = Field(min_length=1, max_length=64)


class DailyAttemptOut(BaseModel):
    correct: bool
    feedback: str
    explanation: str | None
    completed_total: int


# ---------- notificações ----------


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    created_at: datetime
    read: bool
    payload: dict[str, Any]


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    unread_count: int


class NotificationPreferenceOut(BaseModel):
    kind: str
    label: str
    enabled: bool


class NotificationPreferencesOut(BaseModel):
    kinds: list[NotificationPreferenceOut]


class NotificationPreferencesIn(Strict):
    kinds: dict[str, bool] = Field(min_length=1, max_length=8)
