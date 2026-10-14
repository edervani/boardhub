"""Direitos do titular: exportação de dados (RF-029) e exclusão de conta (RF-030).

Decisões em DT-020. A exportação reúne só dados do titular: nunca hash de senha, tokens,
e-mail ou apelido de outras pessoas. A exclusão tem carência de 14 dias; ao final, os dados
pessoais são apagados e partidas com outro humano permanecem, com o jogador removido
pseudonimizado (`removed_account`), para preservar o histórico do oponente.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.core.ratelimit import limiter
from app.core.security import verify_password
from app.models import (
    AuditLog,
    AuthSession,
    DailyUsage,
    DataExportRequest,
    ExerciseAttempt,
    ExerciseHint,
    Match,
    MatchAnalysis,
    MatchMove,
    MatchPlayer,
    PlacementResult,
    QueueEntry,
    Rating,
    RatingHistory,
    SkillProgress,
    User,
)
from app.services import auth_service, match_service
from app.services.events import Event, match_ended
from app.services.mailer import Mail, Mailer, MailError

log = get_logger(__name__)

DELETION_GRACE = timedelta(days=14)  # RF-030 (período de arrependimento)
EXPORT_TTL = timedelta(days=7)  # RF-029
EXPORT_INTERVAL = timedelta(hours=24)  # RF-029: 1 pedido por 24 h por titular
DELETE_ATTEMPTS_PER_DAY = 3  # doc 06
EXPORT_SCHEMA_VERSION = 1
MATCH_BATCH = 200


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# ---------- exportação (RF-029) ----------

def _account_section(user: User) -> dict[str, Any]:
    return {
        "email": user.email, "email_verified_at": _iso(user.email_verified_at),
        "age_band": user.age_band, "status": user.status, "role": user.role,
        "terms_version": user.terms_version, "supervised": user.guardian_user_id is not None,
        "created_at": _iso(user.created_at), "last_login_at": _iso(user.last_login_at),
    }


def _profile_section(user: User) -> dict[str, Any]:
    p, prefs = user.profile, user.preferences
    return {
        "display_name": p.display_name, "avatar_key": p.avatar_key, "bio": p.bio,
        "is_public": p.is_public, "show_in_ranking": p.show_in_ranking,
        "display_name_changed_at": _iso(p.display_name_changed_at),
        "preferences": {
            "theme": prefs.theme, "motion": prefs.motion, "sound": prefs.sound,
            "move_confirmation": prefs.move_confirmation, "move_notation": prefs.move_notation,
            "piece_styles": prefs.piece_styles,
            "locale": prefs.locale, "allow_open_matchmaking": prefs.allow_open_matchmaking,
            "daily_minutes_limit": prefs.daily_minutes_limit,
        },
    }


def _usage_section(db: Session, user: User) -> list[dict[str, Any]]:
    rows = db.scalars(select(DailyUsage).where(DailyUsage.user_id == user.id)
                      .order_by(DailyUsage.day))
    return [{"day": d.day.isoformat(), "seconds": d.seconds} for d in rows]


def _sessions_section(db: Session, user: User) -> list[dict[str, Any]]:
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)
                      .order_by(AuthSession.created_at))
    return [{"created_at": _iso(s.created_at), "last_seen_at": _iso(s.last_seen_at),
             "expires_at": _iso(s.expires_at), "revoked_at": _iso(s.revoked_at),
             "user_agent_summary": s.user_agent_summary} for s in rows]


def _opponent_kind(match: Match, players: list[MatchPlayer], uid: uuid.UUID) -> str:
    """Só o tipo do oponente: identidade de outra pessoa não faz parte dos dados do titular."""
    if match.mode == "local":
        return "local"
    others = [p for p in players if p.user_id != uid]
    if any(p.is_ai for p in others):
        return "ai"
    if any(p.removed_account for p in others):
        return "removed_account"
    return "human" if others else "none"


def _matches_section(db: Session, user: User) -> list[dict[str, Any]]:
    ids = list(db.scalars(
        select(Match.id).join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(MatchPlayer.user_id == user.id).group_by(Match.id, Match.created_at)
        .order_by(Match.created_at, Match.id)))
    out: list[dict[str, Any]] = []
    for start in range(0, len(ids), MATCH_BATCH):
        batch = ids[start:start + MATCH_BATCH]
        matches = {m.id: m for m in db.scalars(select(Match).where(Match.id.in_(batch)))}
        players: dict[uuid.UUID, list[MatchPlayer]] = {}
        for p in db.scalars(select(MatchPlayer).where(MatchPlayer.match_id.in_(batch))):
            players.setdefault(p.match_id, []).append(p)
        moves: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for mv in db.scalars(select(MatchMove).where(MatchMove.match_id.in_(batch))
                             .order_by(MatchMove.match_id, MatchMove.ply)):
            moves.setdefault(mv.match_id, []).append(
                {"ply": mv.ply, "seat": mv.seat, "move": mv.move,
                 "created_at": _iso(mv.created_at)})
        for mid in batch:
            m, ps = matches[mid], players.get(mid, [])
            out.append({
                "id": str(m.id), "game_id": m.game_id, "mode": m.mode, "status": m.status,
                "result": m.result, "end_reason": m.end_reason, "rules_version": m.rules_version,
                "ai_level": m.ai_level, "created_at": _iso(m.created_at),
                "started_at": _iso(m.started_at), "finished_at": _iso(m.finished_at),
                "your_seats": sorted(p.seat for p in ps if p.user_id == user.id),
                "opponent": _opponent_kind(m, ps, user.id), "moves": moves.get(mid, []),
            })
    return out


def _academy_section(db: Session, user: User) -> dict[str, Any]:
    attempts = db.scalars(select(ExerciseAttempt).where(ExerciseAttempt.user_id == user.id)
                          .order_by(ExerciseAttempt.created_at, ExerciseAttempt.id))
    progress = db.scalars(select(SkillProgress).where(SkillProgress.user_id == user.id)
                          .order_by(SkillProgress.game_id, SkillProgress.concept_key))
    placements = db.scalars(select(PlacementResult).where(PlacementResult.user_id == user.id)
                            .order_by(PlacementResult.game_id))
    hints = db.scalars(select(ExerciseHint).where(ExerciseHint.user_id == user.id)
                       .order_by(ExerciseHint.exercise_id))
    analyses = db.scalars(select(MatchAnalysis).where(MatchAnalysis.user_id == user.id)
                          .order_by(MatchAnalysis.created_at, MatchAnalysis.match_id))
    return {
        "attempts": [{
            "game_id": a.game_id, "exercise_id": a.exercise_id, "concept_key": a.concept_key,
            "content_version": a.content_version, "answer": a.answer, "correct": a.correct,
            "hint_level": a.hint_level, "duration_ms": a.duration_ms,
            "created_at": _iso(a.created_at)} for a in attempts],
        "skill_progress": [{
            "game_id": s.game_id, "concept_key": s.concept_key, "mastery": s.mastery,
            "status": s.status, "review_stage": s.review_stage,
            "next_review_at": _iso(s.next_review_at), "mastered_at": _iso(s.mastered_at),
            "updated_at": _iso(s.updated_at)} for s in progress],
        "placements": [{
            "game_id": p.game_id, "declared": p.declared,
            "suggested_ai_level": p.suggested_ai_level,
            "completed_at": _iso(p.completed_at)} for p in placements],
        "hints_revealed": [{"exercise_id": h.exercise_id, "level": h.level,
                            "updated_at": _iso(h.updated_at)} for h in hints],
        "match_analyses": [{
            "match_id": str(a.match_id), "engine_version": a.engine_version,
            "created_at": _iso(a.created_at), "result": a.result} for a in analyses],
    }


def _ratings_section(db: Session, user: User) -> dict[str, Any]:
    ratings = db.scalars(select(Rating).where(Rating.user_id == user.id)
                         .order_by(Rating.game_id))
    history = db.scalars(select(RatingHistory).where(RatingHistory.user_id == user.id)
                         .order_by(RatingHistory.created_at, RatingHistory.id))
    return {
        "current": [{"game_id": r.game_id, "rating": r.rating, "games_played": r.games_played,
                     "updated_at": _iso(r.updated_at)} for r in ratings],
        "history": [{"game_id": h.game_id, "match_id": str(h.match_id), "before": h.before,
                     "after": h.after, "created_at": _iso(h.created_at)} for h in history],
    }


def _audit_section(db: Session, user: User) -> list[dict[str, Any]]:
    """Eventos sobre a própria conta; o autor de ações de terceiros não é revelado."""
    rows = db.scalars(select(AuditLog).where(
        ((AuditLog.target_type == "user") & (AuditLog.target_id == str(user.id)))
        | ((AuditLog.actor_user_id == user.id) & (AuditLog.target_type != "user"))
    ).order_by(AuditLog.created_at, AuditLog.id))
    return [{"action": r.action, "created_at": _iso(r.created_at), "details": r.details}
            for r in rows]


def build_export(db: Session, user: User) -> dict[str, Any]:
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "generated_at": clock.now().isoformat(),
        "account": _account_section(user),
        "profile": _profile_section(user),
        "sessions": _sessions_section(db, user),
        "daily_usage": _usage_section(db, user),
        "matches": _matches_section(db, user),
        "academy": _academy_section(db, user),
        "ratings": _ratings_section(db, user),
        "audit_events": _audit_section(db, user),
    }


def request_export(db: Session, subject: User, requester: User) -> DataExportRequest:
    """Gera a exportação de `subject`. `requester` é ele mesmo ou o responsável vinculado."""
    now = clock.now()
    db.execute(select(User.id).where(User.id == subject.id).with_for_update())  # serializa
    last = db.scalar(select(func.max(DataExportRequest.created_at))
                     .where(DataExportRequest.user_id == subject.id))
    if last is not None and last + EXPORT_INTERVAL > now:
        retry = int((last + EXPORT_INTERVAL - now).total_seconds()) + 1
        db.rollback()
        raise ProblemError(429, "export_rate_limited", "Exportação já solicitada",
                           "Só é possível pedir uma exportação a cada 24 horas.",
                           {"Retry-After": str(retry)})
    export = DataExportRequest(user_id=subject.id, requested_by_user_id=requester.id,
                               status="ready", created_at=now, expires_at=now + EXPORT_TTL,
                               payload=build_export(db, subject))
    db.add(export)
    db.flush()
    db.add(AuditLog(actor_user_id=requester.id, action="data_export_requested",
                    target_type="user", target_id=str(subject.id),
                    details={"export_id": str(export.id),
                             "by_guardian": requester.id != subject.id}))
    db.commit()
    return export


def list_exports(db: Session, requester: User, subject_id: uuid.UUID) -> list[DataExportRequest]:
    return list(db.scalars(
        select(DataExportRequest).where(
            DataExportRequest.user_id == subject_id,
            DataExportRequest.requested_by_user_id == requester.id,
            DataExportRequest.expires_at > clock.now())
        .order_by(DataExportRequest.created_at.desc())))


def get_export(db: Session, requester: User, export_id: uuid.UUID,
               subject_id: uuid.UUID | None = None) -> DataExportRequest:
    export = db.get(DataExportRequest, export_id)
    if export is None or export.requested_by_user_id != requester.id \
            or (subject_id is not None and export.user_id != subject_id):
        raise ProblemError(404, "not_found", "Exportação não encontrada")  # IDOR: sempre 404
    if export.expires_at <= clock.now():
        raise ProblemError(410, "export_expired", "Exportação expirada",
                           "Peça uma nova exportação.")
    return export


def purge_expired_exports(db: Session) -> int:
    result = db.execute(delete(DataExportRequest)
                        .where(DataExportRequest.expires_at <= clock.now()))
    db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


# ---------- exclusão (RF-030) ----------

def deletion_scheduled_for(user: User) -> datetime | None:
    if user.status != "pending_deletion" or user.deletion_requested_at is None:
        return None
    return user.deletion_requested_at + DELETION_GRACE


def _notify(mailer: Mailer, to: str, subject: str, body: str) -> None:
    try:
        mailer.send(Mail(to, subject, body))
    except MailError:
        log.warning("aviso de exclusão de conta não enviado")  # o pedido já foi registrado


def leave_open_matches(db: Session, user: User) -> list[Event]:
    """Tira a pessoa da fila e encerra o que dependia dela, sem deixar o oponente esperando."""
    db.execute(delete(QueueEntry).where(QueueEntry.user_id == user.id))
    events: list[Event] = []
    matches = db.scalars(
        select(Match).join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(MatchPlayer.user_id == user.id, Match.mode.in_(("online_casual", "online_ranked")),
               Match.status.in_(("waiting", "in_progress")))
        .order_by(Match.id).with_for_update()).unique().all()
    for match in matches:
        if match.status == "waiting":
            match.status = "aborted"
            match.finished_at = clock.now()
            continue
        seat = db.scalar(select(MatchPlayer.seat).where(
            MatchPlayer.match_id == match.id, MatchPlayer.user_id == user.id))
        match_service.finish_with_winner(match, 3 - seat if seat else None, "resign")
        events.append(match_ended(match.id, match.result, match.end_reason, match.ply))
    return events


def request_deletion(db: Session, mailer: Mailer, subject: User, actor: User,
                     password: str) -> tuple[datetime, list[Event]]:
    """Agenda a exclusão de `subject`, confirmada com a senha de `actor` (ele ou o responsável)."""
    limiter.hit(f"delete:user:{actor.id}", DELETE_ATTEMPTS_PER_DAY, 86400)
    if not verify_password(actor.password_hash, password):
        raise ProblemError(401, "invalid_credentials", "Senha incorreta",
                           "Confirme a exclusão com a senha da conta.")
    by_guardian = actor.id != subject.id
    db.execute(select(User.id).where(User.id == subject.id).with_for_update())
    db.refresh(subject)
    if subject.status == "pending_deletion":
        db.rollback()
        raise ProblemError(409, "already_pending", "A exclusão já foi solicitada")
    now = clock.now()
    subject.status = "pending_deletion"
    subject.deletion_requested_at = now
    subject.deletion_by_guardian = by_guardian
    auth_service.revoke_all_sessions(db, subject.id)
    events = leave_open_matches(db, subject)
    scheduled = now + DELETION_GRACE
    db.add(AuditLog(actor_user_id=actor.id, action="account_deletion_requested",
                    target_type="user", target_id=str(subject.id),
                    details={"by_guardian": by_guardian, "scheduled_for": scheduled.isoformat()}))
    guardian = db.get(User, subject.guardian_user_id) if subject.guardian_user_id else None
    db.commit()

    when = f"{scheduled:%d/%m/%Y}"
    _notify(mailer, subject.email, "Exclusão de conta do BoardHub solicitada",
            f"A exclusão da conta foi solicitada e será concluída em {when}. Até lá, entre com a "
            "senha e escolha 'Cancelar exclusão' para manter a conta. Depois dessa data os "
            "dados pessoais são apagados e não podem ser recuperados.")
    if guardian is not None and not by_guardian:
        _notify(mailer, guardian.email, "Exclusão de conta supervisionada solicitada",
                f"A conta supervisionada de {subject.profile.display_name} pediu exclusão, "
                f"prevista para {when}.")
    return scheduled, events


def cancel_deletion(db: Session, mailer: Mailer, subject: User, actor: User) -> None:
    limiter.hit(f"delete-cancel:user:{actor.id}", 10, 3600)
    db.execute(select(User.id).where(User.id == subject.id).with_for_update())
    db.refresh(subject)
    if subject.status != "pending_deletion":
        db.rollback()
        raise ProblemError(409, "not_pending", "Não há exclusão em andamento")
    by_guardian = actor.id != subject.id
    if by_guardian != subject.deletion_by_guardian:
        # Cada pedido só é desfeito por quem o fez (o responsável não cancela a decisão do
        # menor, e o menor não cancela a do responsável).
        db.rollback()
        raise ProblemError(403, "cancel_not_allowed", "Você não pode cancelar esta exclusão",
                           "Apenas quem pediu a exclusão pode cancelá-la.")
    subject.status = "active"
    subject.deletion_requested_at = None
    subject.deletion_by_guardian = False
    db.add(AuditLog(actor_user_id=actor.id, action="account_deletion_cancelled",
                    target_type="user", target_id=str(subject.id),
                    details={"by_guardian": by_guardian}))
    db.commit()
    _notify(mailer, subject.email, "Exclusão de conta do BoardHub cancelada",
            "A exclusão da conta foi cancelada e ela voltou ao normal.")


def _restore_protective_defaults(db: Session, guardian_id: uuid.UUID) -> None:
    """Responsável removido: contas supervisionadas voltam ao padrão protetivo (RF-034)."""
    for child in db.scalars(select(User).where(User.guardian_user_id == guardian_id)):
        child.profile.is_public = False
        child.profile.show_in_ranking = False
        child.preferences.allow_open_matchmaking = False
        child.preferences.daily_minutes_limit = None


def _erase(db: Session, user: User) -> None:
    uid = user.id
    ids = list(db.scalars(select(MatchPlayer.match_id).where(MatchPlayer.user_id == uid)))
    drop: list[uuid.UUID] = []
    keep: list[uuid.UUID] = []
    for mid in ids:
        players = list(db.scalars(select(MatchPlayer).where(MatchPlayer.match_id == mid)))
        others = [p for p in players if p.user_id is not None and p.user_id != uid]
        (keep if others else drop).append(mid)  # sem outro humano, a partida só era desta conta
    if drop:
        db.execute(delete(Match).where(Match.id.in_(drop)))  # lances, ofertas, análises: cascata
    if keep:
        open_matches = db.scalars(select(Match).where(
            Match.id.in_(keep), Match.status.in_(("waiting", "in_progress")))
            .order_by(Match.id).with_for_update())
        for match in open_matches:
            mine = db.scalar(select(MatchPlayer.seat).where(
                MatchPlayer.match_id == match.id, MatchPlayer.user_id == uid))
            if match.status == "in_progress" and mine:
                match_service.finish_with_winner(match, 3 - mine, "abandon")
            else:
                match.status = "aborted"
                match.finished_at = clock.now()
        db.execute(update(MatchPlayer)
                   .where(MatchPlayer.user_id == uid, MatchPlayer.match_id.in_(keep))
                   .values(user_id=None, removed_account=True, disconnected_at=None))
    _restore_protective_defaults(db, uid)
    db.flush()
    db.delete(user)  # perfil, preferências, sessões, tokens, progresso e exportações: cascata
    db.add(AuditLog(actor_user_id=None, action="account_deleted", target_type="user",
                    target_id=str(uid), details={}))  # registro mínimo, sem dados pessoais
    db.commit()


def purge_due_deletions(db: Session) -> tuple[int, int]:
    """Conclui as exclusões vencidas: (concluídas, falhas). Uma falha não trava as demais."""
    cutoff = clock.now() - DELETION_GRACE
    ids = list(db.scalars(select(User.id).where(
        User.status == "pending_deletion", User.deletion_requested_at <= cutoff)
        .order_by(User.deletion_requested_at)))
    done = failed = 0
    for uid in ids:
        user = db.get(User, uid)
        if user is None:
            continue
        try:
            _erase(db, user)
            done += 1
        except Exception as exc:  # noqa: BLE001 - registrado e refletido no código de saída
            db.rollback()
            failed += 1
            log.error("falha ao concluir exclusão de conta", extra={
                "user_ref": str(uid)[:8], "error_type": type(exc).__name__})
    return done, failed
