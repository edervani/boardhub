"""Amizades, bloqueios, convites diretos e denúncias (RF-031, RF-032).

Não há chat livre (ECA, doc 09 §10). Nenhuma rota aceita `user_id` do cliente: pessoas são
identificadas pelo apelido público e relações por ids opacos (SEC-05).
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Response, status

from app.api.deps import DbSession, VerifiedAuth
from app.realtime.hub import hub
from app.schemas.matches import MatchOut
from app.schemas.social import (
    BlockIn,
    BlockOut,
    DirectInvitationOut,
    DirectInviteIn,
    FriendOut,
    FriendRequestIn,
    FriendRequestOut,
    FriendRequestsOut,
    ReportCreatedOut,
    ReportIn,
)
from app.services import moderation_service, social_service

router = APIRouter(tags=["social"])
NO_CONTENT = status.HTTP_204_NO_CONTENT


@router.post("/reports", status_code=201)
def create_report(body: ReportIn, auth: VerifiedAuth, db: DbSession) -> ReportCreatedOut:
    return moderation_service.create_report(db, auth.user, body)


@router.get("/friends")
def friends(auth: VerifiedAuth, db: DbSession) -> list[FriendOut]:
    return social_service.list_friends(db, auth.user)


@router.get("/friends/requests")
def friend_requests(auth: VerifiedAuth, db: DbSession) -> FriendRequestsOut:
    return social_service.list_requests(db, auth.user)


@router.post("/friends/requests", status_code=201)
def request_friendship(body: FriendRequestIn, auth: VerifiedAuth,
                       db: DbSession) -> FriendRequestOut:
    return social_service.request_friendship(db, auth.user, body.display_name)


@router.post("/friends/requests/{friendship_id}/accept")
def accept_request(friendship_id: uuid.UUID, auth: VerifiedAuth, db: DbSession) -> FriendOut:
    return social_service.accept_request(db, auth.user, friendship_id)


@router.post("/friends/requests/{friendship_id}/decline", status_code=NO_CONTENT)
def decline_request(friendship_id: uuid.UUID, auth: VerifiedAuth, db: DbSession) -> Response:
    social_service.decline_request(db, auth.user, friendship_id)
    return Response(status_code=NO_CONTENT)


@router.delete("/friends/{friendship_id}", status_code=NO_CONTENT)
def remove_friend(friendship_id: uuid.UUID, auth: VerifiedAuth, db: DbSession) -> Response:
    social_service.remove_friendship(db, auth.user, friendship_id)
    return Response(status_code=NO_CONTENT)


@router.get("/blocks")
def blocks(auth: VerifiedAuth, db: DbSession) -> list[BlockOut]:
    return social_service.list_blocks(db, auth.user)


@router.post("/blocks", status_code=201)
def block(body: BlockIn, auth: VerifiedAuth, db: DbSession) -> BlockOut:
    return social_service.block_user(db, auth.user, body.display_name)


@router.delete("/blocks/{block_id}", status_code=NO_CONTENT)
def unblock(block_id: uuid.UUID, auth: VerifiedAuth, db: DbSession) -> Response:
    social_service.unblock(db, auth.user, block_id)
    return Response(status_code=NO_CONTENT)


@router.post("/friends/{friendship_id}/invitations", status_code=201)
def send_invitation(friendship_id: uuid.UUID, body: DirectInviteIn, auth: VerifiedAuth,
                    db: DbSession) -> DirectInvitationOut:
    return social_service.send_invitation(db, auth.user, friendship_id, body.game_id)


@router.get("/invitations")
def invitations(auth: VerifiedAuth, db: DbSession,
                box: Literal["received", "sent"] = "received") -> list[DirectInvitationOut]:
    return social_service.list_invitations(db, auth.user, box)


@router.post("/invitations/{invitation_id}/accept")
def accept_invitation(invitation_id: uuid.UUID, auth: VerifiedAuth, db: DbSession) -> MatchOut:
    out, events = social_service.accept_invitation(db, auth.user, invitation_id)
    hub.publish_all(events)
    return out


@router.post("/invitations/{invitation_id}/decline", status_code=NO_CONTENT)
def decline_invitation(invitation_id: uuid.UUID, auth: VerifiedAuth, db: DbSession) -> Response:
    social_service.decline_invitation(db, auth.user, invitation_id)
    return Response(status_code=NO_CONTENT)


@router.post("/invitations/{invitation_id}/cancel", status_code=NO_CONTENT)
def cancel_invitation(invitation_id: uuid.UUID, auth: VerifiedAuth, db: DbSession) -> Response:
    social_service.cancel_invitation(db, auth.user, invitation_id)
    return Response(status_code=NO_CONTENT)
