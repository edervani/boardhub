"""Supervisão parental e configurações protetivas (RF-034)."""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.models import AuditLog, User
from app.schemas.profile import ChildSettingsPatch
from app.services.auth_service import consume_token, normalize_email

log = get_logger(__name__)
UNCONFIRMED_UNDER_12_TTL = timedelta(days=7)


def _require_adult(guardian: User) -> None:
    if guardian.age_band != "18_plus":
        raise ProblemError(422, "guardian_must_be_adult",
                           "O responsável precisa ter 18 anos ou mais")


def confirm_link(db: Session, guardian: User, raw_token: str) -> User:
    _require_adult(guardian)
    tok = consume_token(db, raw_token, "guardian_link")
    # Só a conta com o e-mail convidado pode confirmar o vínculo.
    if tok.target_email != normalize_email(guardian.email):
        db.rollback()
        raise ProblemError(400, "invalid_token", "Link inválido ou expirado",
                           "Peça um novo link e tente de novo.")
    child = db.get(User, tok.user_id)
    if child is None or child.id == guardian.id:
        db.rollback()
        raise ProblemError(400, "invalid_token", "Link inválido ou expirado")
    child.guardian_user_id = guardian.id
    db.add(AuditLog(actor_user_id=guardian.id, action="guardian_link_confirmed",
                    target_type="user", target_id=str(child.id), details={}))
    db.commit()
    return child


def list_children(db: Session, guardian: User) -> list[User]:
    _require_adult(guardian)
    return list(db.scalars(select(User).where(User.guardian_user_id == guardian.id)
                           .order_by(User.created_at)))


def _child(db: Session, guardian: User, child_id: uuid.UUID) -> User:
    _require_adult(guardian)
    child = db.scalar(select(User).where(User.id == child_id,
                                         User.guardian_user_id == guardian.id))
    if child is None:  # não vinculado e inexistente respondem igual (IDOR)
        raise ProblemError(404, "not_found", "Conta supervisionada não encontrada")
    return child


def update_settings(db: Session, guardian: User, child_id: uuid.UUID,
                    patch: ChildSettingsPatch) -> User:
    child = _child(db, guardian, child_id)
    profile, prefs = child.profile, child.preferences
    current = {
        "allow_open_matchmaking": prefs.allow_open_matchmaking,
        "profile_public": profile.is_public,
        "show_in_ranking": profile.show_in_ranking,
        "daily_minutes_limit": prefs.daily_minutes_limit,
    }
    new = {k: getattr(patch, k) for k in patch.model_fields_set}
    if new.get("show_in_ranking") and not new.get("profile_public", profile.is_public):
        raise ProblemError(422, "ranking_requires_public_profile",
                           "Para aparecer no ranking o perfil precisa ser público")
    if new.get("profile_public") is False:
        new["show_in_ranking"] = False
    changes = {k: {"from": current[k], "to": v} for k, v in new.items() if current[k] != v}
    if "allow_open_matchmaking" in new:
        prefs.allow_open_matchmaking = bool(new["allow_open_matchmaking"])
    if "daily_minutes_limit" in new:
        prefs.daily_minutes_limit = new["daily_minutes_limit"]
    if "profile_public" in new:
        profile.is_public = bool(new["profile_public"])
    if "show_in_ranking" in new:
        profile.show_in_ranking = bool(new["show_in_ranking"])
    if changes:
        db.add(AuditLog(actor_user_id=guardian.id, action="guardian_settings_changed",
                        target_type="user", target_id=str(child.id), details=changes))
    db.commit()
    return child


def unlink(db: Session, guardian: User, child_id: uuid.UUID) -> None:
    """Desvincular devolve a conta ao padrão protetivo."""
    child = _child(db, guardian, child_id)
    child.guardian_user_id = None
    child.profile.is_public = False
    child.profile.show_in_ranking = False
    child.preferences.allow_open_matchmaking = False
    child.preferences.daily_minutes_limit = None
    db.add(AuditLog(actor_user_id=guardian.id, action="guardian_unlinked",
                    target_type="user", target_id=str(child.id), details={}))
    db.commit()


def require_online_access(user: User) -> None:
    """Menor de 12 sem responsável confirmado não acessa partidas online."""
    if user.age_band == "under_12" and user.guardian_user_id is None:
        raise ProblemError(403, "guardian_pending", "Aguardando confirmação do responsável",
                           "Peça ao responsável para confirmar o convite enviado por e-mail.")


def purge_unconfirmed_under_12(db: Session) -> int:
    """Remove cadastros de menores de 12 sem confirmação em 7 dias, sem reter dados."""
    cutoff = clock.now() - UNCONFIRMED_UNDER_12_TTL
    users = db.scalars(select(User).where(
        User.age_band == "under_12", User.guardian_user_id.is_(None),
        User.created_at < cutoff)).all()
    for user in users:
        db.delete(user)
    db.commit()
    log.info("cadastros de menores sem confirmação removidos", extra={"count": len(users)})
    return len(users)
