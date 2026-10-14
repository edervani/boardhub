"""Denúncias e moderação (RF-031, DT-022).

- O denunciante nunca aparece em nenhuma resposta nem em e-mail ao denunciado: a moderação
  vê o conteúdo, não quem denunciou (sem retaliação).
- Toda ação de moderação grava `audit_log` na mesma transação (SEC-11).
- Suspensão revoga as sessões, tira a conta da fila, encerra partidas online abertas e
  cancela convites; o login passa a responder 403 (`auth_service.login`).
- Hierarquia: moderador age sobre contas comuns; administrador, também sobre moderadores;
  ninguém age sobre si nem sobre papel igual ou superior.
"""

import re
import unicodedata
import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.core.ratelimit import limiter
from app.models import AuditLog, MatchPlayer, Report, User, UserProfile
from app.schemas.social import (
    ReportCreatedOut,
    ReportIn,
    ReportQueueItem,
    ReportQueueOut,
    ResolveReportIn,
)
from app.services import auth_service, privacy_service, social_service
from app.services.events import Event
from app.services.mailer import Mail, Mailer, MailError

log = get_logger(__name__)
DAY = 86400.0
HOUR = 3600.0
REPORTS_PER_DAY = 10
STAFF_ACTIONS_PER_HOUR = 120
ROLE_RANK = {"user": 0, "moderator": 1, "admin": 2}
STAFF_ROLES = ("moderator", "admin")
MAX_NOTE = 500
_CONTROL = re.compile(r"[<>]")
_SPACES = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def sanitize_note(raw: str | None, limit: int = MAX_NOTE) -> str | None:
    """Texto livre como texto puro: NFKC, sem caracteres de controle/formatação nem `<` `>`,
    espaços colapsados e tamanho limitado. O frontend ainda o renderiza como texto (SEC-09)."""
    if raw is None:
        return None
    text = unicodedata.normalize("NFKC", raw)
    text = "".join(ch if ch == "\n" or unicodedata.category(ch)[0] != "C" else " "
                   for ch in text)
    text = _CONTROL.sub("", text)
    text = "\n".join(_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text).strip()
    return text[:limit].strip() or None


def require_staff(user: User) -> None:
    """Papel conferido no servidor; usuário comum recebe 403 (CA-031)."""
    if user.role not in STAFF_ROLES:
        raise ProblemError(403, "forbidden", "Acesso restrito à moderação")


# ---------- denúncia ----------

def _report_target(db: Session, reporter: User, body: ReportIn) -> tuple[User, uuid.UUID | None]:
    if body.target_type == "user":
        try:
            target = social_service.find_by_display_name(db, reporter, body.target_id)
        except ProblemError as exc:
            if exc.status == 404 and body.target_id.strip().lower() == \
                    reporter.profile.display_name.lower():
                raise ProblemError(422, "cannot_report_self", "Você não pode se denunciar") \
                    from exc
            raise
        return target, None
    try:
        match_id = uuid.UUID(body.target_id)
    except ValueError as exc:
        raise ProblemError(404, "not_found", "Partida não encontrada") from exc
    players = list(db.scalars(select(MatchPlayer).where(MatchPlayer.match_id == match_id)))
    if not any(p.user_id == reporter.id for p in players):
        raise ProblemError(404, "not_found", "Partida não encontrada")  # IDOR (SEC-05)
    others = [p.user_id for p in players if p.user_id is not None and p.user_id != reporter.id]
    target = db.get(User, others[0]) if others else None
    if target is None:
        raise ProblemError(422, "no_human_opponent", "Não há outra pessoa para denunciar",
                           "Esta partida não teve outro jogador humano.")
    return target, match_id


def create_report(db: Session, reporter: User, body: ReportIn) -> ReportCreatedOut:
    limiter.hit(f"report:{reporter.id}", REPORTS_PER_DAY, DAY)
    if body.target_type == "match" and body.reason in ("offensive_name", "offensive_bio"):
        raise ProblemError(422, "reason_not_applicable", "Motivo inválido para partida",
                           "Para nome ou bio ofensivos, denuncie a pessoa pelo perfil.")
    target, match_id = _report_target(db, reporter, body)
    duplicate = db.scalar(select(Report.id).where(
        Report.reporter_id == reporter.id, Report.target_user_id == target.id,
        Report.target_type == body.target_type, Report.reason == body.reason,
        Report.status == "open",
        Report.match_id.is_(match_id) if match_id is None else Report.match_id == match_id,
    ).limit(1))
    if duplicate is not None:
        raise ProblemError(409, "already_reported", "Você já denunciou isto",
                           "A denúncia anterior ainda está em análise.")
    report = Report(reporter_id=reporter.id, target_user_id=target.id,
                    target_type=body.target_type, match_id=match_id, reason=body.reason,
                    note=sanitize_note(body.note), status="open", created_at=clock.now())
    db.add(report)
    db.commit()
    log.info("denúncia registrada", extra={"report_ref": str(report.id)[:8]})
    return ReportCreatedOut(id=report.id, status=report.status, created_at=report.created_at)


# ---------- fila de moderação ----------

def list_reports(db: Session, staff: User, status: str, limit: int,
                 offset: int) -> ReportQueueOut:
    limiter.hit(f"staff:{staff.id}", STAFF_ACTIONS_PER_HOUR * 10, HOUR)
    require_staff(staff)
    where = [] if status == "all" else [Report.status == status]
    total = db.scalar(select(func.count()).select_from(Report).where(*where)) or 0
    order = Report.created_at.asc() if status == "open" else Report.created_at.desc()
    rows = db.execute(_queue_select().where(*where).order_by(order, Report.id)
                      .limit(limit).offset(offset)).all()
    return ReportQueueOut(items=_items(db, list(rows)), total=total)


def _queue_select() -> Select[Any]:
    return (select(Report, UserProfile.display_name, UserProfile.bio, User.status)
            .join(User, User.id == Report.target_user_id)
            .join(UserProfile, UserProfile.user_id == User.id))


def item_for(db: Session, report: Report) -> ReportQueueItem:
    rows = db.execute(_queue_select().where(Report.id == report.id)).all()
    return _items(db, list(rows))[0]


def _items(db: Session, rows: list[Any]) -> list[ReportQueueItem]:
    ids = {r.target_user_id for r, *_ in rows}
    open_counts: dict[uuid.UUID, int] = {}
    if ids:
        open_counts = {uid: n for uid, n in db.execute(
            select(Report.target_user_id, func.count()).where(
                Report.status == "open", Report.target_user_id.in_(ids))
            .group_by(Report.target_user_id)).all()}
    return [ReportQueueItem(
        id=r.id, status=r.status, target_type=r.target_type, reason=r.reason, note=r.note,
        created_at=r.created_at, target_user_id=r.target_user_id, target_display_name=name,
        target_bio=bio, target_status=ustatus, match_id=r.match_id,
        open_reports_on_target=open_counts.get(r.target_user_id, 0),
        resolution_action=r.resolution_action, resolved_at=r.resolved_at,
    ) for r, name, bio, ustatus in rows]


def _notify(mailer: Mailer, to: str, subject: str, body: str) -> None:
    try:
        mailer.send(Mail(to, subject, body))
    except MailError:
        log.warning("aviso de moderação não enviado")  # a ação já foi registrada


def _require_can_act(staff: User, target: User) -> None:
    if target.id == staff.id or ROLE_RANK[staff.role] <= ROLE_RANK[target.role]:
        raise ProblemError(403, "insufficient_role", "Sem permissão sobre esta conta")


def _audit(db: Session, staff: User, action: str, target: User,
           details: dict[str, Any]) -> None:
    db.add(AuditLog(actor_user_id=staff.id, action=action, target_type="user",
                    target_id=str(target.id), details=details))


def _suspend(db: Session, staff: User, target: User, report_id: uuid.UUID | None,
             reason: str | None) -> list[Event]:
    _require_can_act(staff, target)
    if target.status != "active":
        raise ProblemError(409, "not_suspendable", "A conta não está ativa",
                           "Só contas ativas podem ser suspensas.")
    target.status = "suspended"
    auth_service.revoke_all_sessions(db, target.id)
    events = privacy_service.leave_open_matches(db, target)
    social_service.cancel_all_for(db, target.id)
    _audit(db, staff, "user_suspended", target,
           {"report_id": str(report_id) if report_id else None, "reason": reason})
    return events


def _hide_content(db: Session, staff: User, target: User, report: Report) -> dict[str, Any]:
    profile = target.profile
    changed: dict[str, Any] = {}
    if profile.bio:
        profile.bio = None
        changed["bio_cleared"] = True
    if report.reason == "offensive_name":
        profile.display_name = f"jogador-{target.id.hex[:8]}"
        profile.display_name_changed_at = clock.now()
        changed["display_name_reset"] = True
    return changed


def resolve_report(db: Session, mailer: Mailer, staff: User, report_id: uuid.UUID,
                   body: ResolveReportIn) -> tuple[Report, list[Event]]:
    limiter.hit(f"staff:{staff.id}", STAFF_ACTIONS_PER_HOUR, HOUR)
    require_staff(staff)
    report = db.scalar(select(Report).where(Report.id == report_id).with_for_update())
    if report is None:
        raise ProblemError(404, "not_found", "Denúncia não encontrada")
    if report.status != "open":
        raise ProblemError(409, "already_resolved", "Denúncia já resolvida")
    target = db.get(User, report.target_user_id)
    if target is None:  # a conta foi removida: a denúncia some junto (cascata)
        raise ProblemError(404, "not_found", "Denúncia não encontrada")
    events: list[Event] = []
    hidden: dict[str, Any] = {}
    if body.action in ("warn", "suspend"):
        _require_can_act(staff, target)
    if body.hide_content:
        _require_can_act(staff, target)
        hidden = _hide_content(db, staff, target, report)
    if body.action == "suspend":
        events = _suspend(db, staff, target, report.id, sanitize_note(body.note, 200))
    report.status, report.resolution_action = "resolved", body.action
    report.resolved_by, report.resolved_at = staff.id, clock.now()
    _audit(db, staff, "report_resolved", target, {
        "report_id": str(report.id), "action": body.action, "reason": report.reason,
        "hide_content": hidden, "note": sanitize_note(body.note, 200)})
    db.commit()
    if body.action == "warn":
        _notify(mailer, target.email, "Aviso sobre sua conta no BoardHub",
                "Sua conta recebeu uma advertência por conduta que não segue as regras de "
                "convivência do BoardHub. Novas ocorrências podem levar à suspensão.")
    elif body.action == "suspend":
        _notify(mailer, target.email, "Sua conta no BoardHub foi suspensa",
                "Sua conta foi suspensa por não seguir as regras de convivência do BoardHub. "
                "Para pedir revisão, entre em contato com o suporte.")
    return report, events


def suspend_user(db: Session, mailer: Mailer, staff: User, user_id: uuid.UUID,
                 reason: str) -> tuple[User, list[Event]]:
    limiter.hit(f"staff:{staff.id}", STAFF_ACTIONS_PER_HOUR, HOUR)
    require_staff(staff)
    target = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if target is None:
        raise ProblemError(404, "not_found", "Conta não encontrada")
    events = _suspend(db, staff, target, None, sanitize_note(reason, 200))
    db.commit()
    _notify(mailer, target.email, "Sua conta no BoardHub foi suspensa",
            "Sua conta foi suspensa por não seguir as regras de convivência do BoardHub. "
            "Para pedir revisão, entre em contato com o suporte.")
    return target, events


def reinstate_user(db: Session, staff: User, user_id: uuid.UUID) -> User:
    limiter.hit(f"staff:{staff.id}", STAFF_ACTIONS_PER_HOUR, HOUR)
    require_staff(staff)
    target = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if target is None:
        raise ProblemError(404, "not_found", "Conta não encontrada")
    _require_can_act(staff, target)
    if target.status != "suspended":
        raise ProblemError(409, "not_suspended", "A conta não está suspensa")
    target.status = "active"
    _audit(db, staff, "user_reinstated", target, {})
    db.commit()
    return target

