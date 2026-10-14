"""Mensagens do WebSocket (doc 06 §3): cliente → servidor validadas por Pydantic estrito.

Nenhuma mensagem aceita `user_id`, `seat`, `result` ou `state` (SEC-05, SEC-06): campos
desconhecidos são rejeitados por `extra="forbid"`.
"""

import uuid
from typing import Annotated, Any, Literal

from pydantic import Field, StrictBool, StrictInt, TypeAdapter

from app.schemas.auth import Strict
from app.services.events import Event


class MatchRef(Strict):
    match_id: uuid.UUID


class JoinPayload(Strict):
    match_id: uuid.UUID
    last_known_ply: StrictInt = Field(default=0, ge=0, le=10_000)


class MovePayload(Strict):
    match_id: uuid.UUID
    expected_ply: StrictInt = Field(ge=0, le=10_000)
    move: str = Field(min_length=1, max_length=64)
    client_move_id: uuid.UUID


class DrawResponsePayload(Strict):
    match_id: uuid.UUID
    accept: StrictBool


class JoinMatch(Strict):
    type: Literal["join_match"]
    id: uuid.UUID
    payload: JoinPayload


class LeaveMatch(Strict):
    type: Literal["leave_match"]
    id: uuid.UUID
    payload: MatchRef


class SubmitMove(Strict):
    type: Literal["submit_move"]
    id: uuid.UUID
    payload: MovePayload


class Resign(Strict):
    type: Literal["resign"]
    id: uuid.UUID
    payload: MatchRef


class OfferDraw(Strict):
    type: Literal["offer_draw"]
    id: uuid.UUID
    payload: MatchRef


class RespondDraw(Strict):
    type: Literal["respond_draw"]
    id: uuid.UUID
    payload: DrawResponsePayload


class ClaimAbandon(Strict):
    type: Literal["claim_abandon"]
    id: uuid.UUID
    payload: MatchRef


class Pong(Strict):
    type: Literal["pong"]
    id: uuid.UUID | None = None


ClientMessage = Annotated[
    JoinMatch | LeaveMatch | SubmitMove | Resign | OfferDraw | RespondDraw | ClaimAbandon | Pong,
    Field(discriminator="type"),
]
_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(raw: str) -> ClientMessage:
    """Levanta `pydantic.ValidationError` para JSON inválido, tipo desconhecido ou campo extra."""
    return _adapter.validate_json(raw)


# ---------- servidor → cliente ----------

def to_message(event: Event, reply_to: str | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"type": event.type, "payload": event.payload}
    if event.seq is not None:
        message["seq"] = event.seq
    if reply_to is not None:
        message["reply_to"] = reply_to
    return message


def error_message(code: str, title: str, *, reply_to: str | None = None, status: int | None = None,
                  detail: str | None = None, current_ply: int | None = None,
                  retry_after: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": title}
    if detail:
        payload["detail"] = detail
    if status is not None:
        payload["status"] = status
    if current_ply is not None:
        payload["current_ply"] = current_ply
    if retry_after is not None:
        payload["retry_after"] = retry_after
    message: dict[str, Any] = {"type": "error", "payload": payload}
    if reply_to is not None:
        message["reply_to"] = reply_to
    return message


def reply_message(type_: str, payload: dict[str, Any], reply_to: str) -> dict[str, Any]:
    return {"type": type_, "payload": payload, "reply_to": reply_to}
