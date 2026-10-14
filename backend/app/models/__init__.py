"""Modelos ORM (doc 05). Importar aqui garante o registro no metadata usado pelo Alembic."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.catalog import Game
from app.models.identity import AuthSession, AuthToken, User, UserPreferences, UserProfile
from app.models.match import DrawOffer, Match, MatchMove, MatchPlayer, QueueEntry

__all__ = [
    "AuditLog",
    "AuthSession",
    "AuthToken",
    "Base",
    "DrawOffer",
    "Game",
    "Match",
    "MatchMove",
    "MatchPlayer",
    "QueueEntry",
    "User",
    "UserPreferences",
    "UserProfile",
]
