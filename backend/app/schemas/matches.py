"""Contratos de partidas e do endpoint de motor sem estado (doc 06 §2)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.auth import Strict
from app.schemas.ranking import RatingChangeOut


class CreateMatchIn(Strict):
    game_id: str = Field(max_length=16)
    mode: Literal["ai", "local", "online_casual", "online_ranked"]
    ai_level: int | None = Field(default=None, ge=1, le=5)
    preferred_seat: Literal[1, 2] | None = None

    @model_validator(mode="after")
    def _coerent(self) -> "CreateMatchIn":
        if self.mode == "ai" and self.ai_level is None:
            raise ValueError("ai_level é obrigatório contra a IA")
        if self.mode == "local" and (self.ai_level is not None or self.preferred_seat):
            raise ValueError("ai_level e preferred_seat não se aplicam à partida local")
        if self.mode in ("online_casual", "online_ranked") and self.ai_level is not None:
            raise ValueError("ai_level não se aplica à partida online")
        return self


class MoveIn(Strict):
    expected_ply: int = Field(ge=0, le=10_000)
    move: str = Field(min_length=1, max_length=64)
    client_move_id: uuid.UUID


class SeatOut(BaseModel):
    seat: int
    is_ai: bool
    is_you: bool


class PlayerOut(BaseModel):
    """Identificação e presença de um jogador humano de partida online."""

    seat: int
    display_name: str | None
    connected: bool
    grace_deadline: datetime | None = None


class MatchOut(BaseModel):
    id: uuid.UUID
    game_id: str
    mode: str
    status: str
    ply: int
    state: dict[str, Any]
    to_move_seat: int | None
    legal_moves: list[str]
    result: str | None
    end_reason: str | None
    ai_level: int | None
    rules_version: str
    seats: list[SeatOut]
    created_at: datetime
    finished_at: datetime | None
    # Somente partidas online. `invite_code` é devolvido uma única vez, na criação.
    players: list[PlayerOut] = []
    invite_code: str | None = None
    invite_expires_at: datetime | None = None
    draw_offer_by_seat: int | None = None
    # Partida ranqueada encerrada e liquidada: rating de cada assento antes e depois (RF-019).
    rating_changes: list[RatingChangeOut] = []


class MoveOut(BaseModel):
    ply: int
    seat: int
    move: str
    created_at: datetime


class MatchSummary(BaseModel):
    id: uuid.UUID
    game_id: str
    mode: str
    status: str
    result: str | None
    ply: int
    created_at: datetime
    finished_at: datetime | None


class MatchPage(BaseModel):
    items: list[MatchSummary]
    next_cursor: str | None


class JoinIn(Strict):
    invite_code: str = Field(min_length=1, max_length=32)


class DrawResponseIn(Strict):
    accept: bool


class QueueIn(Strict):
    game_id: str = Field(max_length=16)
    ranked: bool = False


class QueueStatusOut(BaseModel):
    state: Literal["idle", "queued", "matched"]
    game_id: str | None = None
    waited_seconds: int = 0
    # RF-012: após 60 s o cliente oferece jogar contra a IA.
    offer_ai: bool = False
    match_id: uuid.UUID | None = None
    ranked: bool = False
    # Janela de rating (±) usada agora no pareamento ranqueado (RF-012).
    rating_window: int | None = None


class ActiveMatchOut(BaseModel):
    id: uuid.UUID
    game_id: str
    mode: str
    status: str
    ply: int
    your_seat: int | None
    your_turn: bool
    opponent_name: str | None
    invite_expires_at: datetime | None
    created_at: datetime


class EngineApplyIn(Strict):
    state: dict[str, Any]
    move: str = Field(min_length=1, max_length=64)


class OutcomeOut(BaseModel):
    winner: str | None
    reason: str


class EngineApplyOut(BaseModel):
    state: dict[str, Any]
    outcome: OutcomeOut | None
    legal_moves: list[str]
