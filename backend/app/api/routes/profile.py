"""Perfil, preferências, perfil público, catálogo e supervisão (RF-006/007/033/034)."""

import re
import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentAuth, DbSession, OptionalAuth, VerifiedAuth
from app.core.errors import ProblemError
from app.models import User
from app.schemas.profile import (
    ChildOut,
    ChildSettings,
    ChildSettingsPatch,
    GameOut,
    GuardianConfirmIn,
    PreferencesModel,
    ProfileOut,
    ProfilePatch,
    PublicProfileOut,
)
from app.services import catalog_service, guardian_service, privacy_service, profile_service

router = APIRouter(tags=["perfil"])
NAME_RE = re.compile(r"^[\w-]{3,24}$")


def _profile_out(user: User) -> ProfileOut:
    p = user.profile
    return ProfileOut(display_name=p.display_name, avatar_key=p.avatar_key, bio=p.bio,
                      is_public=p.is_public, show_in_ranking=p.show_in_ranking,
                      display_name_change_allowed_at=profile_service.name_change_allowed_at(p))


def _child_out(child: User) -> ChildOut:
    return ChildOut(
        id=child.id, display_name=child.profile.display_name, age_band=child.age_band,
        settings=ChildSettings(
            allow_open_matchmaking=child.preferences.allow_open_matchmaking,
            profile_public=child.profile.is_public,
            show_in_ranking=child.profile.show_in_ranking,
            daily_minutes_limit=child.preferences.daily_minutes_limit),
        deletion_scheduled_for=privacy_service.deletion_scheduled_for(child))


@router.get("/me/profile")
def get_profile(auth: CurrentAuth) -> ProfileOut:
    return _profile_out(auth.user)


@router.patch("/me/profile")
def patch_profile(body: ProfilePatch, auth: CurrentAuth, db: DbSession) -> ProfileOut:
    profile_service.update_profile(db, auth.user, body)
    return _profile_out(auth.user)


@router.get("/me/preferences")
def get_preferences(auth: CurrentAuth) -> PreferencesModel:
    return PreferencesModel.model_validate(auth.user.preferences, from_attributes=True)


@router.put("/me/preferences")
def put_preferences(body: PreferencesModel, auth: CurrentAuth, db: DbSession) -> PreferencesModel:
    prefs = profile_service.update_preferences(db, auth.user, body)
    return PreferencesModel.model_validate(prefs, from_attributes=True)


@router.get("/users/{display_name}")
def public_profile(display_name: str, db: DbSession) -> PublicProfileOut:
    if not NAME_RE.fullmatch(display_name):
        raise ProblemError(404, "not_found", "Perfil não encontrado")
    p = profile_service.public_profile(db, display_name)
    return PublicProfileOut(display_name=p.display_name, avatar_key=p.avatar_key, bio=p.bio)


@router.get("/games")
def games(auth: OptionalAuth, db: DbSession) -> list[GameOut]:
    band = auth.user.age_band if auth else None
    return [GameOut(id=g.id, name=g.name, age_rating=str(g.age_rating),
                    age_rating_label=catalog_service.RATING_LABEL[str(g.age_rating)],
                    ranked_enabled=g.ranked_enabled)
            for g in catalog_service.visible_games(db, band)]


@router.post("/guardian/links/confirm")
def confirm_link(body: GuardianConfirmIn, auth: VerifiedAuth, db: DbSession) -> ChildOut:
    return _child_out(guardian_service.confirm_link(db, auth.user, body.token))


@router.get("/guardian/children")
def children(auth: VerifiedAuth, db: DbSession) -> list[ChildOut]:
    return [_child_out(c) for c in guardian_service.list_children(db, auth.user)]


@router.put("/guardian/children/{child_id}/settings")
def child_settings(child_id: uuid.UUID, body: ChildSettingsPatch, auth: VerifiedAuth,
                   db: DbSession) -> ChildOut:
    return _child_out(guardian_service.update_settings(db, auth.user, child_id, body))


@router.delete("/guardian/children/{child_id}/link", status_code=status.HTTP_204_NO_CONTENT)
def unlink(child_id: uuid.UUID, auth: VerifiedAuth, db: DbSession) -> Response:
    guardian_service.unlink(db, auth.user, child_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
