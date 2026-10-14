"""Moderação (RF-031): fila de denúncias e suspensão. Só `moderator` e `admin`; toda ação
grava `audit_log` (SEC-11)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, StaffAuth
from app.realtime.hub import hub
from app.schemas.social import (
    ModerationResultOut,
    ReportQueueItem,
    ReportQueueOut,
    ResolveReportIn,
    SuspendIn,
)
from app.services import moderation_service
from app.services.mailer import Mailer, get_mailer

router = APIRouter(prefix="/admin", tags=["moderação"])
MailerDep = Annotated[Mailer, Depends(get_mailer)]


@router.get("/reports")
def list_reports(auth: StaffAuth, db: DbSession,
                 status: Literal["open", "resolved", "all"] = "open",
                 limit: Annotated[int, Query(ge=1, le=100)] = 50,
                 offset: Annotated[int, Query(ge=0, le=10000)] = 0) -> ReportQueueOut:
    return moderation_service.list_reports(db, auth.user, status, limit, offset)


@router.post("/reports/{report_id}/resolve")
def resolve_report(report_id: uuid.UUID, body: ResolveReportIn, auth: StaffAuth,
                   db: DbSession, mailer: MailerDep) -> ReportQueueItem:
    report, events = moderation_service.resolve_report(db, mailer, auth.user, report_id, body)
    hub.publish_all(events)
    return moderation_service.item_for(db, report)


@router.post("/users/{user_id}/suspend")
def suspend_user(user_id: uuid.UUID, body: SuspendIn, auth: StaffAuth, db: DbSession,
                 mailer: MailerDep) -> ModerationResultOut:
    user, events = moderation_service.suspend_user(db, mailer, auth.user, user_id, body.reason)
    hub.publish_all(events)
    return ModerationResultOut(user_id=user.id, status=user.status)


@router.post("/users/{user_id}/reinstate")
def reinstate_user(user_id: uuid.UUID, auth: StaffAuth, db: DbSession) -> ModerationResultOut:
    user = moderation_service.reinstate_user(db, auth.user, user_id)
    return ModerationResultOut(user_id=user.id, status=user.status)
