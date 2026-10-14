"""Rotas de autenticação (RF-001 a RF-005)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    ClientIp,
    CurrentAuth,
    DbSession,
)
from app.core.config import get_settings
from app.core.security import new_token
from app.models import User
from app.schemas.auth import (
    ForgotIn,
    LoginIn,
    MeOut,
    RegisterIn,
    ResetIn,
    SessionOut,
    TokenIn,
)
from app.services import auth_service
from app.services.mailer import Mailer, get_mailer

router = APIRouter(prefix="/auth", tags=["auth"])
MailerDep = Annotated[Mailer, Depends(get_mailer)]


def me_out(user: User) -> MeOut:
    return MeOut.model_validate({
        "id": user.id, "email": user.email, "display_name": user.profile.display_name,
        "email_verified": user.email_verified_at is not None, "age_band": user.age_band,
        "role": user.role, "supervised": user.guardian_user_id is not None,
    })


def _set_cookies(response: Response, session_token: str) -> None:
    s = get_settings()
    max_age = s.session_absolute_days * 86400
    response.set_cookie(SESSION_COOKIE, session_token, max_age=max_age, httponly=True,
                        secure=s.cookie_secure, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, new_token(), max_age=max_age, httponly=False,
                        secure=s.cookie_secure, samesite="lax", path="/")


def _clear_cookies(response: Response) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: DbSession, mailer: MailerDep, ip: ClientIp) -> dict[str, str]:
    auth_service.register(db, mailer, auth_service.Registration(
        email=body.email, password=body.password, display_name=body.display_name,
        age_band=body.age_band, accept_terms_version=body.accept_terms_version,
        guardian_email=body.guardian_email, client_ip=ip))
    return {"status": "Verifique seu e-mail para confirmar a conta."}


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(body: TokenIn, db: DbSession, ip: ClientIp) -> None:
    auth_service.verify_email(db, body.token, ip)


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
def resend(auth: CurrentAuth, db: DbSession, mailer: MailerDep) -> None:
    auth_service.resend_verification(db, mailer, auth.user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DbSession,
          ip: ClientIp) -> MeOut:
    user, token = auth_service.login(db, body.email, body.password, ip,
                                     request.headers.get("user-agent"))
    _set_cookies(response, token)
    return me_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(auth: CurrentAuth, db: DbSession, response: Response) -> None:
    auth_service.logout(db, auth.session)
    _clear_cookies(response)


@router.get("/sessions")
def sessions(auth: CurrentAuth, db: DbSession) -> list[SessionOut]:
    return [SessionOut(id=s.id, created_at=s.created_at, last_seen_at=s.last_seen_at,
                       user_agent_summary=s.user_agent_summary, current=s.id == auth.session.id)
            for s in auth_service.list_sessions(db, auth.user.id)]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke(session_id: uuid.UUID, auth: CurrentAuth, db: DbSession) -> None:
    auth_service.revoke_session(db, auth.user.id, session_id)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
def forgot(body: ForgotIn, db: DbSession, mailer: MailerDep, ip: ClientIp) -> dict[str, str]:
    auth_service.forgot_password(db, mailer, body.email, ip)
    return {"status": "Se o e-mail estiver cadastrado, enviaremos um link."}


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset(body: ResetIn, db: DbSession, mailer: MailerDep, ip: ClientIp) -> None:
    auth_service.reset_password(db, mailer, body.token, body.new_password, ip)
