"""Dependências HTTP: sessão do banco, usuário autenticado, IP do cliente."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.db.session import get_session
from app.models import AuthSession, User
from app.services import auth_service

SESSION_COOKIE = "bh_session"
CSRF_COOKIE = "bh_csrf"
CSRF_HEADER = "X-CSRF-Token"

DbSession = Annotated[Session, Depends(get_session)]


def client_ip(request: Request) -> str:
    # Atrás do proxy, o uvicorn deve rodar com --proxy-headers e IPs confiáveis (doc 12 §5).
    return request.client.host if request.client else "desconhecido"


ClientIp = Annotated[str, Depends(client_ip)]


@dataclass
class Auth:
    user: User
    session: AuthSession


def _optional_auth(request: Request, db: DbSession) -> Auth | None:
    sess = auth_service.session_from_cookie(db, request.cookies.get(SESSION_COOKIE))
    if sess is None:
        return None
    user = db.get(User, sess.user_id)
    if user is None or user.status == "suspended":
        return None
    return Auth(user, sess)


def _auth(auth: Annotated[Auth | None, Depends(_optional_auth)]) -> Auth:
    if auth is None:
        raise ProblemError(401, "not_authenticated", "Faça login para continuar")
    return auth


OptionalAuth = Annotated[Auth | None, Depends(_optional_auth)]
CurrentAuth = Annotated[Auth, Depends(_auth)]


def _verified(auth: CurrentAuth) -> Auth:
    if auth.user.email_verified_at is None:
        raise ProblemError(403, "email_not_verified", "Confirme seu e-mail para continuar")
    return auth


VerifiedAuth = Annotated[Auth, Depends(_verified)]
