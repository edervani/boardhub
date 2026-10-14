"""Cadastro, verificação, login, sessões e recuperação de senha (RF-001 a RF-005)."""

import unicodedata
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.core.ratelimit import limiter
from app.core.security import (
    hash_password,
    needs_rehash,
    new_token,
    password_problem,
    token_digest,
    verify_password,
)
from app.models import AuditLog, AuthSession, AuthToken, User, UserPreferences, UserProfile
from app.services.mailer import Mail, Mailer, MailError

log = get_logger(__name__)

HOUR = 3600.0
VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(minutes=30)
GUARDIAN_TTL = timedelta(days=7)
BLOCKED_NAME_PARTS = ("admin", "moderador", "boardhub", "suporte")  # lista mínima; ampliar


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_display_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).strip()


def _invalid_token() -> ProblemError:
    return ProblemError(400, "invalid_token", "Link inválido ou expirado",
                        "Peça um novo link e tente de novo.")


def _issue_token(
    db: Session, user: User, purpose: str, ttl: timedelta, target_email: str | None = None
) -> str:
    raw = new_token()
    db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=token_digest(raw),
                     target_email=target_email, expires_at=clock.now() + ttl))
    return raw


def consume_token(db: Session, raw: str, purpose: str) -> AuthToken:
    tok = db.scalar(
        select(AuthToken)
        .where(AuthToken.token_hash == token_digest(raw), AuthToken.purpose == purpose)
        .with_for_update()
    )
    if tok is None or tok.used_at is not None or tok.expires_at <= clock.now():
        raise _invalid_token()
    tok.used_at = clock.now()
    return tok


def _link(path: str, token: str) -> str:
    return f"{get_settings().frontend_origin}{path}?token={token}"


# ---------- RF-001 / RF-002 ----------

@dataclass(frozen=True)
class Registration:
    email: str
    password: str
    display_name: str
    age_band: str
    accept_terms_version: str
    guardian_email: str | None
    client_ip: str


def register(db: Session, mailer: Mailer, data: Registration) -> None:
    limiter.hit(f"register:ip:{data.client_ip}", 5, HOUR)
    settings = get_settings()
    if data.accept_terms_version != settings.terms_version:
        raise ProblemError(422, "terms_outdated", "Aceite a versão atual dos termos")
    if (problem := password_problem(data.password)) is not None:
        raise ProblemError(422, "weak_password", "Senha recusada", problem)
    email = normalize_email(data.email)
    name = normalize_display_name(data.display_name)
    if any(part in name.lower() for part in BLOCKED_NAME_PARTS):
        raise ProblemError(422, "display_name_not_allowed", "Nome de exibição não permitido")
    guardian = normalize_email(data.guardian_email) if data.guardian_email else None
    if data.age_band == "under_12" and not guardian:
        raise ProblemError(422, "guardian_required", "E-mail do responsável é obrigatório",
                           "Contas de menores de 12 anos precisam da confirmação "
                           "de um responsável.")
    if guardian == email:
        raise ProblemError(422, "guardian_invalid", "O responsável precisa ter outro e-mail")

    taken = db.scalar(select(UserProfile.user_id).where(
        func.lower(UserProfile.display_name) == name.lower()))
    if taken is not None:
        raise ProblemError(409, "display_name_taken", "Nome de exibição em uso",
                           "Escolha outro nome de exibição.")

    if db.scalar(select(User.id).where(User.email == email)) is not None:
        # Antienumeração: mesma resposta de sucesso; o dono do e-mail é avisado.
        _send(mailer, Mail(email, "Tentativa de cadastro no BoardHub",
                           "Alguém tentou criar uma conta com este e-mail, "
                           "que já está cadastrado. "
                           "Se foi você, use 'Esqueci minha senha'. Se não foi, ignore."))
        return

    user = User(email=email, password_hash=hash_password(data.password), age_band=data.age_band,
                terms_version=data.accept_terms_version, role="user", status="active")
    minor = data.age_band != "18_plus"
    # RF-034: menores nascem com configuração protetiva.
    user.profile = UserProfile(display_name=name, is_public=not minor, show_in_ranking=not minor,
                               avatar_key="default")
    user.preferences = UserPreferences(allow_open_matchmaking=not minor, piece_styles={},
                                       theme="system", motion="system", sound=True,
                                       move_confirmation=False, locale="pt-BR")
    db.add(user)
    db.flush()
    verify = _issue_token(db, user, "verify_email", VERIFY_TTL)
    guardian_token = (
        _issue_token(db, user, "guardian_link", GUARDIAN_TTL, guardian) if guardian else None
    )
    db.add(AuditLog(actor_user_id=user.id, action="account_created", target_type="user",
                    target_id=str(user.id), details={"age_band": data.age_band}))
    db.commit()
    log.info("conta criada", extra={"user_ref": str(user.id)[:8], "age_band": data.age_band})

    _send(mailer, Mail(email, "Confirme seu e-mail no BoardHub",
                       f"Para confirmar seu e-mail, abra: {_link('/verificar-email', verify)}\n"
                       "O link vale por 24 horas."))
    if guardian and guardian_token:
        _send(mailer, Mail(guardian, "Pedido de supervisão no BoardHub",
                           f"Uma conta foi criada no BoardHub com o nome {name} e indicou você "
                           "como responsável. Para acompanhar e liberar a conta, abra: "
                           f"{_link('/responsavel/confirmar', guardian_token)}\n"
                           "Se você não reconhece este pedido, ignore este e-mail."))


def _send(mailer: Mailer, mail: Mail) -> None:
    try:
        mailer.send(mail)
    except MailError as exc:
        raise ProblemError(
            503, "email_unavailable", "Não foi possível enviar o e-mail agora",
            "Sua solicitação foi registrada. Tente reenviar em alguns minutos.",
        ) from exc


def verify_email(db: Session, raw_token: str, client_ip: str) -> None:
    limiter.hit(f"verify:ip:{client_ip}", 10, HOUR)
    tok = consume_token(db, raw_token, "verify_email")
    user = db.get(User, tok.user_id)
    if user is None:
        raise _invalid_token()
    user.email_verified_at = user.email_verified_at or clock.now()
    db.commit()


def resend_verification(db: Session, mailer: Mailer, user: User) -> None:
    limiter.hit(f"resend:user:{user.id}", 3, HOUR)
    if user.email_verified_at is not None:
        return
    raw = _issue_token(db, user, "verify_email", VERIFY_TTL)
    db.commit()
    _send(mailer, Mail(user.email, "Confirme seu e-mail no BoardHub",
                       f"Para confirmar seu e-mail, abra: {_link('/verificar-email', raw)}"))


# ---------- RF-003 / RF-004 ----------

def _bad_credentials() -> ProblemError:
    return ProblemError(401, "invalid_credentials", "E-mail ou senha incorretos")


def login(db: Session, email: str, password: str, client_ip: str,
          user_agent: str | None) -> tuple[User, str]:
    email = normalize_email(email)
    fail_key = f"login-fail:{email}:{client_ip}"
    if limiter.count(fail_key, 15 * 60) >= 5:
        limiter.hit(fail_key, 5, 15 * 60)  # levanta 429
    user = db.scalar(select(User).where(User.email == email))
    if not verify_password(user.password_hash if user else None, password) or user is None:
        limiter.hit(fail_key, 1_000_000, 15 * 60)  # só registra a falha
        raise _bad_credentials()
    if user.status == "suspended":
        raise ProblemError(403, "account_suspended", "Conta suspensa",
                           "Entre em contato com o suporte.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    raw = new_token()
    now = clock.now()
    db.add(AuthSession(user_id=user.id, token_hash=token_digest(raw), last_seen_at=now,
                       expires_at=now + timedelta(days=get_settings().session_absolute_days),
                       user_agent_summary=summarize_user_agent(user_agent)))
    user.last_login_at = now
    db.commit()
    return user, raw


def summarize_user_agent(ua: str | None) -> str | None:
    """Só navegador e sistema, nunca a string completa (doc 05)."""
    if not ua:
        return None
    browser = next((b for b in ("Edg", "Firefox", "Chrome", "Safari") if b in ua), "Outro")
    system = next((s for s in ("Android", "iPhone", "iPad", "Windows", "Mac OS", "Linux")
                   if s in ua), "Outro")
    return f"{'Edge' if browser == 'Edg' else browser} / {system}"


def session_from_cookie(db: Session, raw: str | None) -> AuthSession | None:
    if not raw:
        return None
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(raw)))
    now = clock.now()
    idle = timedelta(days=get_settings().session_idle_days)
    if sess is None or sess.revoked_at is not None or sess.expires_at <= now \
            or sess.last_seen_at + idle <= now:
        return None
    if now - sess.last_seen_at > timedelta(minutes=5):
        sess.last_seen_at = now
        db.commit()
    return sess


def logout(db: Session, sess: AuthSession) -> None:
    sess.revoked_at = clock.now()
    db.commit()


def list_sessions(db: Session, user_id: uuid.UUID) -> list[AuthSession]:
    now = clock.now()
    return list(db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None),
               AuthSession.expires_at > now)
        .order_by(AuthSession.last_seen_at.desc())
    ))


def revoke_session(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
    sess = db.get(AuthSession, session_id)
    if sess is None or sess.user_id != user_id or sess.revoked_at is not None:
        raise ProblemError(404, "not_found", "Sessão não encontrada")
    sess.revoked_at = clock.now()
    db.commit()


def revoke_all_sessions(
    db: Session, user_id: uuid.UUID, except_id: uuid.UUID | None = None
) -> None:
    stmt = update(AuthSession).where(AuthSession.user_id == user_id,
                                     AuthSession.revoked_at.is_(None))
    if except_id is not None:
        stmt = stmt.where(AuthSession.id != except_id)
    db.execute(stmt.values(revoked_at=clock.now()))


# ---------- RF-005 ----------

def forgot_password(db: Session, mailer: Mailer, email: str, client_ip: str) -> None:
    email = normalize_email(email)
    limiter.hit(f"forgot:ip:{client_ip}", 3, HOUR)
    limiter.hit(f"forgot:email:{email}", 3, HOUR)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or user.status != "active":
        return  # mesma resposta para todos (antienumeração)
    raw = _issue_token(db, user, "reset_password", RESET_TTL)
    db.commit()
    try:
        mailer.send(Mail(email, "Redefinição de senha do BoardHub",
                         f"Para criar uma nova senha, abra: {_link('/nova-senha', raw)}\n"
                         "O link vale por 30 minutos. Se não foi você, ignore."))
    except MailError:
        log.warning("e-mail de redefinição não enviado")  # resposta continua idêntica


def reset_password(db: Session, mailer: Mailer, raw_token: str, new_password: str,
                   client_ip: str) -> None:
    limiter.hit(f"reset:ip:{client_ip}", 10, HOUR)
    if (problem := password_problem(new_password)) is not None:
        raise ProblemError(422, "weak_password", "Senha recusada", problem)
    tok = consume_token(db, raw_token, "reset_password")
    user = db.get(User, tok.user_id)
    if user is None:
        raise _invalid_token()
    user.password_hash = hash_password(new_password)
    revoke_all_sessions(db, user.id)
    db.add(AuditLog(actor_user_id=user.id, action="password_reset", target_type="user",
                    target_id=str(user.id), details={}))
    db.commit()
    try:
        mailer.send(Mail(user.email, "Sua senha do BoardHub foi alterada",
                         "Sua senha foi alterada e todas as sessões foram encerradas. "
                         "Se não foi você, redefina a senha imediatamente."))
    except MailError:
        log.warning("aviso de troca de senha não enviado")

