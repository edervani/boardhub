"""Perfil e preferências do próprio usuário; perfil público (RF-006, RF-007)."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import ProblemError
from app.models import User, UserPreferences, UserProfile
from app.schemas.profile import PreferencesModel, ProfilePatch
from app.services.auth_service import BLOCKED_NAME_PARTS, normalize_display_name

NAME_CHANGE_INTERVAL = timedelta(days=30)


def name_change_allowed_at(profile: UserProfile) -> datetime | None:
    if profile.display_name_changed_at is None:
        return None
    return profile.display_name_changed_at + NAME_CHANGE_INTERVAL


def _taken(db: Session, name: str, user: User) -> bool:
    other = db.scalar(select(UserProfile.user_id).where(
        func.lower(UserProfile.display_name) == name.lower(),
        UserProfile.user_id != user.id))
    return other is not None


def _change_name(db: Session, user: User, raw: str) -> None:
    profile = user.profile
    name = normalize_display_name(raw)
    if name == profile.display_name:
        return
    if any(part in name.lower() for part in BLOCKED_NAME_PARTS):
        raise ProblemError(422, "display_name_not_allowed", "Nome de exibição não permitido")
    allowed_at = name_change_allowed_at(profile)
    if allowed_at is not None and clock.now() < allowed_at:
        raise ProblemError(422, "display_name_change_limited",
                           "O nome só pode ser alterado a cada 30 dias",
                           f"Próxima alteração permitida a partir de {allowed_at:%d/%m/%Y}.")
    if _taken(db, name, user):
        raise ProblemError(409, "display_name_taken", "Nome de exibição em uso")
    profile.display_name = name
    profile.display_name_changed_at = clock.now()


def update_profile(db: Session, user: User, patch: ProfilePatch) -> UserProfile:
    profile = user.profile
    fields = patch.model_fields_set
    if "is_public" in fields and patch.is_public and user.is_minor:
        # RF-034: menores só ficam públicos por decisão do responsável.
        raise ProblemError(403, "supervision_required", "Ação restrita ao responsável",
                           "O perfil de menores só pode ser tornado público pelo responsável.")
    if "show_in_ranking" in fields and patch.show_in_ranking and user.is_minor:
        raise ProblemError(403, "supervision_required", "Ação restrita ao responsável",
                           "Só o responsável pode incluir o menor no ranking público.")
    if patch.show_in_ranking and not (profile.is_public if patch.is_public is None
                                      else patch.is_public):
        raise ProblemError(422, "ranking_requires_public_profile",
                           "Para aparecer no ranking o perfil precisa ser público")
    if patch.display_name is not None:
        _change_name(db, user, patch.display_name)
    if patch.avatar_key is not None:
        profile.avatar_key = patch.avatar_key
    if "bio" in fields:
        profile.bio = (patch.bio or "").strip() or None
    if patch.is_public is not None:
        profile.is_public = patch.is_public
        if not patch.is_public:
            profile.show_in_ranking = False
    if patch.show_in_ranking is not None and patch.is_public is not False:
        profile.show_in_ranking = patch.show_in_ranking
    try:
        db.commit()
    except IntegrityError as exc:  # corrida na unicidade do nome
        db.rollback()
        raise ProblemError(409, "display_name_taken", "Nome de exibição em uso") from exc
    return profile


def public_profile(db: Session, display_name: str) -> UserProfile:
    """Perfil privado, suspenso ou inexistente respondem igual (404)."""
    row = db.scalar(
        select(UserProfile).join(User, User.id == UserProfile.user_id).where(
            func.lower(UserProfile.display_name) == display_name.lower(),
            UserProfile.is_public.is_(True),
            User.status == "active"))
    if row is None:
        raise ProblemError(404, "not_found", "Perfil não encontrado")
    return row


def update_preferences(db: Session, user: User, data: PreferencesModel) -> UserPreferences:
    prefs = user.preferences
    prefs.theme = data.theme
    prefs.motion = data.motion
    prefs.sound = data.sound
    prefs.move_confirmation = data.move_confirmation
    prefs.piece_styles = dict(data.piece_styles)  # novo dict: JSONB não detecta mutação
    prefs.locale = data.locale
    db.commit()
    return prefs
