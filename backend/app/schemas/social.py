"""Contratos de amizades, bloqueios, convites diretos, denúncias e moderação (RF-031/032).

Nenhum contrato expõe e-mail, id de conta alheia ou o autor de uma denúncia: contas são
identificadas pelo apelido público e por ids de relação (amizade, bloqueio, convite).
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import Strict

ReportReason = Literal["offensive_name", "offensive_bio", "cheating", "harassment", "other"]
ModerationAction = Literal["warn", "suspend", "archive"]


# ---------- amizades e bloqueios ----------

class FriendRequestIn(Strict):
    display_name: str = Field(min_length=3, max_length=24)


class PersonOut(BaseModel):
    display_name: str
    avatar_key: str


class FriendOut(PersonOut):
    friendship_id: uuid.UUID
    since: datetime


class FriendRequestOut(PersonOut):
    friendship_id: uuid.UUID
    created_at: datetime


class FriendRequestsOut(BaseModel):
    incoming: list[FriendRequestOut]
    outgoing: list[FriendRequestOut]


class BlockIn(Strict):
    display_name: str = Field(min_length=3, max_length=24)


class BlockOut(PersonOut):
    block_id: uuid.UUID
    created_at: datetime


# ---------- convites diretos ----------

class DirectInviteIn(Strict):
    game_id: Literal["tictactoe", "checkers", "chess"]


class DirectInvitationOut(BaseModel):
    id: uuid.UUID
    game_id: str
    status: str
    created_at: datetime
    expires_at: datetime | None
    match_id: uuid.UUID | None = None  # só para quem enviou
    other: PersonOut  # quem enviou (caixa recebida) ou quem recebeu (caixa enviada)


# ---------- denúncias ----------

class ReportIn(Strict):
    # `user`: apelido público; `match`: id de uma partida da qual o denunciante participou.
    target_type: Literal["user", "match"]
    target_id: str = Field(min_length=1, max_length=64)
    reason: ReportReason
    note: str | None = Field(default=None, max_length=500)


class ReportCreatedOut(BaseModel):
    id: uuid.UUID
    status: str
    created_at: datetime


class ReportQueueItem(BaseModel):
    """Visão da moderação. Não traz o denunciante (SEC-05, RF-031)."""

    id: uuid.UUID
    status: str
    target_type: str
    reason: str
    note: str | None
    created_at: datetime
    target_user_id: uuid.UUID
    target_display_name: str | None
    target_bio: str | None
    target_status: str
    match_id: uuid.UUID | None
    open_reports_on_target: int
    resolution_action: str | None
    resolved_at: datetime | None


class ReportQueueOut(BaseModel):
    items: list[ReportQueueItem]
    total: int


class ResolveReportIn(Strict):
    action: ModerationAction
    # Oculta o conteúdo denunciado: apaga a bio e, se o motivo for o nome, troca o apelido.
    hide_content: bool = False
    note: str | None = Field(default=None, max_length=200)


class SuspendIn(Strict):
    reason: str = Field(min_length=3, max_length=200)


class ModerationResultOut(BaseModel):
    user_id: uuid.UUID
    status: str
