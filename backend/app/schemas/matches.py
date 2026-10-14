"""Contratos de partidas e do endpoint de motor sem estado (doc 06 §2)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.auth import Strict


class CreateMatchIn(Strict):
    game_id: str = Field(max_length=16)
    mode: Literal["ai", "local"]
    ai_level: int | None = Field(default=None, ge=1, le=5)
    preferred_seat: Literal[1, 2] | None = None

    @model_validator(mode="after")
    def _coerent(self) -> "CreateMatchIn":
        if self.mode == "ai" and self.ai_level is None:
            raise ValueError("ai_level é obrigatório contra a IA")
        if self.mode == "local" and (self.ai_level is not None or self.preferred_seat):
            raise ValueError("ai_level e preferred_seat não se aplicam à partida local")
        return self


class MoveIn(Strict):
    expected_ply: int = Field(ge=0, le=10_000)
    move: str = Field(min_length=1, max_length=64)
    client_move_id: uuid.UUID


class SeatOut(BaseModel):
    seat: int
    is_ai: bool
    is_you: bool


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
