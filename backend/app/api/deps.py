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


def _resolve(request: Request, db: DbSession) -> Auth | None:
    sess = auth_service.session_from_cookie(db, request.cookies.get(SESSION_COOKIE))
    if sess is None:
        return None
    user = db.get(User, sess.user_id)
    if user is None or user.status == "suspended":
        return None
    return Auth(user, sess)


def _optional_auth(auth: Annotated[Auth | None, Depends(_resolve)]) -> Auth | None:
    # Conta em período de arrependimento (RF-030) é tratada como visitante fora das rotas de conta.
    if auth is not None and auth.user.status == "pending_deletion":
        return None
    return auth


def _account_auth(auth: Annotated[Auth | None, Depends(_resolve)]) -> Auth:
    if auth is None:
        raise ProblemError(401, "not_authenticated", "Faça login para continuar")
    return auth


def _auth(auth: Annotated[Auth, Depends(_account_auth)]) -> Auth:
    if auth.user.status == "pending_deletion":
        raise ProblemError(403, "account_pending_deletion", "Conta em exclusão",
                           "Cancele a exclusão para voltar a usar a conta.")
    return auth


OptionalAuth = Annotated[Auth | None, Depends(_optional_auth)]
# Aceita contas em exclusão: só /me, logout e cancelamento da exclusão (RF-030).
AccountAuth = Annotated[Auth, Depends(_account_auth)]
CurrentAuth = Annotated[Auth, Depends(_auth)]


def _verified(auth: CurrentAuth) -> Auth:
    if auth.user.email_verified_at is None:
        raise ProblemError(403, "email_not_verified", "Confirme seu e-mail para continuar")
    return auth


VerifiedAuth = Annotated[Auth, Depends(_verified)]


def _staff(auth: CurrentAuth) -> Auth:
    # Papel conferido no servidor a cada chamada (SEC-05); a UI esconder botões não é controle.
    if auth.user.role not in ("moderator", "admin"):
        raise ProblemError(403, "forbidden", "Acesso restrito à moderação")
    return auth


StaffAuth = Annotated[Auth, Depends(_staff)]
