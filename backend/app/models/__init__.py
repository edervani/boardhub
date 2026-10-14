"""Modelos ORM (doc 05). Importar aqui garante o registro no metadata usado pelo Alembic."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.catalog import Game
from app.models.identity import AuthSession, AuthToken, User, UserPreferences, UserProfile
from app.models.match import Match, MatchMove, MatchPlayer

__all__ = [
    "AuditLog",
    "AuthSession",
    "AuthToken",
    "Base",
    "Game",
    "Match",
    "MatchMove",
    "MatchPlayer",
    "User",
    "UserPreferences",
    "UserProfile",
]
