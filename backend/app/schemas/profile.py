"""Contratos de perfil, preferências, catálogo e supervisão (RF-006/007/033/034)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import DISPLAY_NAME_RE, Strict

AVATARS = ("default", "torre", "cavalo", "bispo", "peao", "dama")
GAME_IDS = ("tictactoe", "checkers", "chess")
PieceStyle = Literal["infantil", "intermediario", "classico"]


class ProfileOut(BaseModel):
    display_name: str
    avatar_key: str
    bio: str | None
    is_public: bool
    show_in_ranking: bool
    display_name_change_allowed_at: datetime | None


class ProfilePatch(Strict):
    display_name: str | None = None
    avatar_key: Literal["default", "torre", "cavalo", "bispo", "peao", "dama"] | None = None
    bio: str | None = Field(default=None, max_length=160)
    is_public: bool | None = None

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is not None and not DISPLAY_NAME_RE.fullmatch(v.strip()):
            raise ValueError("use de 3 a 24 letras, números, _ ou -")
        return v


class PublicProfileOut(BaseModel):
    display_name: str
    avatar_key: str
    bio: str | None


class PreferencesModel(Strict):
    theme: Literal["light", "dark", "system"] = "system"
    motion: Literal["full", "reduced", "none", "system"] = "system"
    sound: bool = True
    move_confirmation: bool = False
    piece_styles: dict[str, PieceStyle] = Field(default_factory=dict, max_length=3)
    locale: Literal["pt-BR"] = "pt-BR"

    @field_validator("piece_styles")
    @classmethod
    def _games(cls, v: dict[str, PieceStyle]) -> dict[str, PieceStyle]:
        unknown = set(v) - set(GAME_IDS)
        if unknown:
            raise ValueError("jogo desconhecido em piece_styles")
        return v


class GameOut(BaseModel):
    id: str
    name: str
    age_rating: str
    age_rating_label: str
    ranked_enabled: bool


class ChildSettings(BaseModel):
    allow_open_matchmaking: bool
    profile_public: bool
    show_in_ranking: bool
    daily_minutes_limit: int | None


class ChildOut(BaseModel):
    id: uuid.UUID
    display_name: str
    age_band: str
    settings: ChildSettings


class ChildSettingsPatch(Strict):
    model_config = ConfigDict(extra="forbid")

    allow_open_matchmaking: bool | None = None
    profile_public: bool | None = None
    show_in_ranking: bool | None = None
    daily_minutes_limit: int | None = Field(default=None, ge=15, le=600)


class GuardianConfirmIn(Strict):
    token: str = Field(min_length=10, max_length=100)
