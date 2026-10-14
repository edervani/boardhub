"""Direitos do titular: exportação e exclusão de conta, próprios e do menor supervisionado.

RF-029, RF-030 e RF-034. O titular vem sempre da sessão (ou do vínculo de responsável);
nenhum `user_id` é aceito do cliente (SEC-05).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import AccountAuth, DbSession, VerifiedAuth
from app.api.routes.auth import _clear_cookies
from app.models import DataExportRequest, User
from app.realtime.hub import hub
from app.schemas.privacy import DeleteAccountIn, DeletionOut, ExportOut
from app.services import guardian_service, privacy_service
from app.services.mailer import Mailer, get_mailer

router = APIRouter(tags=["privacidade"])
MailerDep = Annotated[Mailer, Depends(get_mailer)]


def _export_out(e: DataExportRequest) -> ExportOut:
    return ExportOut(id=e.id, status=e.status, created_at=e.created_at, expires_at=e.expires_at)


def _download(e: DataExportRequest) -> JSONResponse:
    filename = f"boardhub-dados-{e.created_at:%Y%m%d}.json"
    return JSONResponse(e.payload, headers={
        "Content-Disposition": f'attachment; filename="{filename}"'})


# ---------- o próprio titular ----------

@router.post("/me/export", status_code=status.HTTP_202_ACCEPTED)
def request_export(auth: AccountAuth, db: DbSession) -> ExportOut:
    return _export_out(privacy_service.request_export(db, auth.user, auth.user))


@router.get("/me/export")
def list_exports(auth: AccountAuth, db: DbSession) -> list[ExportOut]:
    return [_export_out(e) for e in privacy_service.list_exports(db, auth.user, auth.user.id)]


@router.get("/me/export/{export_id}")
def download_export(export_id: uuid.UUID, auth: AccountAuth, db: DbSession) -> JSONResponse:
    return _download(privacy_service.get_export(db, auth.user, export_id, auth.user.id))


@router.post("/me/delete", status_code=status.HTTP_202_ACCEPTED)
def request_delete(body: DeleteAccountIn, auth: AccountAuth, db: DbSession, mailer: MailerDep,
                   response: Response) -> DeletionOut:
    scheduled, events = privacy_service.request_deletion(
        db, mailer, auth.user, auth.user, body.password)
    hub.publish_all(events)
    _clear_cookies(response)  # todas as sessões, inclusive esta, já foram revogadas
    return DeletionOut(scheduled_for=scheduled)


@router.post("/me/delete/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_delete(auth: AccountAuth, db: DbSession, mailer: MailerDep) -> Response:
    privacy_service.cancel_deletion(db, mailer, auth.user, auth.user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- responsável legal pelo menor vinculado (RF-034) ----------

def _child(db: DbSession, auth: VerifiedAuth, child_id: uuid.UUID) -> User:
    return guardian_service.supervised_child(db, auth.user, child_id)


@router.post("/guardian/children/{child_id}/export", status_code=status.HTTP_202_ACCEPTED)
def child_request_export(child_id: uuid.UUID, auth: VerifiedAuth, db: DbSession) -> ExportOut:
    child = _child(db, auth, child_id)
    return _export_out(privacy_service.request_export(db, child, auth.user))


@router.get("/guardian/children/{child_id}/export")
def child_list_exports(child_id: uuid.UUID, auth: VerifiedAuth, db: DbSession) -> list[ExportOut]:
    child = _child(db, auth, child_id)
    return [_export_out(e) for e in privacy_service.list_exports(db, auth.user, child.id)]


@router.get("/guardian/children/{child_id}/export/{export_id}")
def child_download_export(child_id: uuid.UUID, export_id: uuid.UUID, auth: VerifiedAuth,
                          db: DbSession) -> JSONResponse:
    child = _child(db, auth, child_id)
    return _download(privacy_service.get_export(db, auth.user, export_id, child.id))


@router.post("/guardian/children/{child_id}/delete", status_code=status.HTTP_202_ACCEPTED)
def child_request_delete(child_id: uuid.UUID, body: DeleteAccountIn, auth: VerifiedAuth,
                         db: DbSession, mailer: MailerDep) -> DeletionOut:
    child = _child(db, auth, child_id)
    scheduled, events = privacy_service.request_deletion(
        db, mailer, child, auth.user, body.password)
    hub.publish_all(events)
    return DeletionOut(scheduled_for=scheduled)


@router.post("/guardian/children/{child_id}/delete/cancel",
             status_code=status.HTTP_204_NO_CONTENT)
def child_cancel_delete(child_id: uuid.UUID, auth: VerifiedAuth, db: DbSession,
                        mailer: MailerDep) -> Response:
    child = _child(db, auth, child_id)
    privacy_service.cancel_deletion(db, mailer, child, auth.user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
