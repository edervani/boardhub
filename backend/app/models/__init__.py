"""Modelos ORM (doc 05). Importar aqui garante o registro no metadata usado pelo Alembic."""

from app.models.academy import (
    ExerciseAttempt,
    ExerciseHint,
    MatchAnalysis,
    PlacementResult,
    SkillProgress,
)
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.catalog import Game
from app.models.engagement import (
    DailyChallengeResult,
    Notification,
    NotificationPreference,
    UserAchievement,
)
from app.models.identity import AuthSession, AuthToken, User, UserPreferences, UserProfile
from app.models.match import DrawOffer, Match, MatchMove, MatchPlayer, QueueEntry
from app.models.privacy import DataExportRequest
from app.models.rating import Rating, RatingHistory
from app.models.social import DirectInvitation, Friendship, Report, UserBlock
from app.models.usage import DailyUsage

__all__ = [
    "AuditLog",
    "AuthSession",
    "AuthToken",
    "Base",
    "DailyChallengeResult",
    "DailyUsage",
    "DataExportRequest",
    "DirectInvitation",
    "DrawOffer",
    "ExerciseAttempt",
    "ExerciseHint",
    "Friendship",
    "Game",
    "Match",
    "MatchAnalysis",
    "MatchMove",
    "MatchPlayer",
    "Notification",
    "NotificationPreference",
    "PlacementResult",
    "QueueEntry",
    "Rating",
    "RatingHistory",
    "Report",
    "SkillProgress",
    "User",
    "UserAchievement",
    "UserBlock",
    "UserPreferences",
    "UserProfile",
]
