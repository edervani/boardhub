"""Notificações in-app (RF-028, DT-023).

Só avisos funcionais do próprio jogo: vez de jogar, partida encerrada, oponente desconectado e
conquista. Não há e-mail nem push aqui (e-mail segue só transacional, RF-028), nenhum aviso de
"volte a jogar", contagem regressiva ou pressão. Cada tipo pode ser desativado pela pessoa.
Avisos repetidos de uma mesma partida, ainda não lidos, viram um só (`dedupe_key`).
"""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import ProblemError
from app.models import Notification, NotificationPreference, User
from app.models.base import new_id
from app.models.engagement import NOTIFICATION_KINDS
from app.schemas.engagement import (
    NotificationListOut,
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferencesOut,
)
from app.services import domain_events
from app.services.domain_events import DomainEvent
from app.services.events import Event

MAX_LIST = 50
READ_RETENTION = timedelta(days=30)
ANY_RETENTION = timedelta(days=90)
GAME_NAMES = {"tictactoe": "Jogo da velha", "checkers": "Damas", "chess": "Xadrez"}
KIND_LABELS = {
    "your_turn": "Vez de jogar numa partida online",
    "match_ended": "Partida online encerrada",
    "opponent_disconnected": "Oponente desconectado",
    "achievement_earned": "Nova conquista",
}
# Avisos que valem só enquanto a pessoa não agiu na partida (somem ao jogar ou ao terminar).
MATCH_BOUND = ("your_turn", "opponent_disconnected")
_OUTCOME_TEXT = {"win": "você venceu", "loss": "você perdeu", "draw": "empate"}


def render(kind: str, payload: dict[str, Any]) -> tuple[str, str]:
    """Título e texto em pt-BR, montados no servidor a partir de dados controlados por ele."""
    game = GAME_NAMES.get(str(payload.get("game_id")), "a partida")
    if kind == "your_turn":
        return "Sua vez de jogar", f"Seu oponente jogou. É a sua vez em {game}."
    if kind == "match_ended":
        outcome = _OUTCOME_TEXT.get(str(payload.get("outcome")), "partida encerrada")
        return "Partida encerrada", f"A partida de {game} terminou: {outcome}."
    if kind == "opponent_disconnected":
        return ("Oponente desconectado",
                f"Seu oponente saiu da partida de {game}. Ele pode voltar dentro do prazo.")
    if kind == "achievement_earned":
        return "Nova conquista", str(payload.get("title", "Conquista"))
    return "Aviso", ""


def _out(n: Notification) -> NotificationOut:
    title, body = render(n.kind, n.payload)
    return NotificationOut(id=n.id, kind=n.kind, title=title, body=body, created_at=n.created_at,
                           read=n.read_at is not None, payload=n.payload)


# ---------- criação ----------

def is_enabled(db: Session, user_id: uuid.UUID, kind: str) -> bool:
    row = db.get(NotificationPreference, (user_id, kind))
    return True if row is None else row.enabled


def notify(db: Session, user_id: uuid.UUID, kind: str, payload: dict[str, Any],
           dedupe_key: str | None = None) -> bool:
    """Cria o aviso (se o tipo estiver ativo) e agenda a entrega por WebSocket após o commit."""
    if kind not in NOTIFICATION_KINDS or not is_enabled(db, user_id, kind):
        return False
    now = clock.now()
    stmt = pg_insert(Notification).values(
        id=new_id(), user_id=user_id, kind=kind, payload=payload, dedupe_key=dedupe_key,
        created_at=now)
    if dedupe_key is not None:
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "dedupe_key"],
            index_where=(Notification.read_at.is_(None) & Notification.dedupe_key.is_not(None)),
            set_={"payload": payload, "created_at": now})
    row = db.execute(stmt.returning(Notification.id)).scalar_one()
    title, body = render(kind, payload)
    db.info.setdefault("pending_events", []).append(Event(
        "notification",
        {"id": str(row), "kind": kind, "title": title, "body": body,
         "created_at": now.isoformat()},
        user_ids=(user_id,)))
    return True


# ---------- leitura ----------

def unread_count(db: Session, user: User) -> int:
    return int(db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))) or 0)


def list_notifications(db: Session, user: User, unread_only: bool,
                       limit: int) -> NotificationListOut:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.created_at.desc(), Notification.id)
                      .limit(max(1, min(limit, MAX_LIST))))
    return NotificationListOut(items=[_out(n) for n in rows], unread_count=unread_count(db, user))


def mark_read(db: Session, user: User, notification_id: uuid.UUID) -> None:
    n = db.scalar(select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user.id))
    if n is None:  # IDOR: aviso de outra pessoa responde igual a inexistente
        raise ProblemError(404, "not_found", "Notificação não encontrada")
    if n.read_at is None:
        n.read_at = clock.now()
        db.commit()


def mark_all_read(db: Session, user: User) -> None:
    db.execute(update(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=clock.now()))
    db.commit()


def clear_match_notices(db: Session, user_id: uuid.UUID, match_id: str) -> None:
    """A pessoa agiu na partida: os avisos pendentes dela deixam de fazer sentido."""
    db.execute(update(Notification).where(
        Notification.user_id == user_id, Notification.read_at.is_(None),
        Notification.dedupe_key.in_([f"{k}:{match_id}" for k in MATCH_BOUND]))
        .values(read_at=clock.now()))


# ---------- preferências ----------

def get_preferences(db: Session, user: User) -> NotificationPreferencesOut:
    rows = {p.kind: p.enabled for p in db.scalars(
        select(NotificationPreference).where(NotificationPreference.user_id == user.id))}
    return NotificationPreferencesOut(kinds=[
        NotificationPreferenceOut(kind=k, label=KIND_LABELS[k], enabled=rows.get(k, True))
        for k in NOTIFICATION_KINDS])


def update_preferences(db: Session, user: User,
                       changes: dict[str, bool]) -> NotificationPreferencesOut:
    unknown = set(changes) - set(NOTIFICATION_KINDS)
    if unknown:
        raise ProblemError(422, "unknown_notification_kind", "Tipo de aviso desconhecido")
    for kind, enabled in changes.items():
        stmt = pg_insert(NotificationPreference).values(
            user_id=user.id, kind=kind, enabled=enabled)
        db.execute(stmt.on_conflict_do_update(
            index_elements=["user_id", "kind"], set_={"enabled": enabled}))
    db.commit()
    return get_preferences(db, user)


# ---------- retenção (doc 13 §5) ----------

def purge_old(db: Session) -> int:
    now = clock.now()
    result = db.execute(delete(Notification).where(
        (Notification.read_at <= now - READ_RETENTION)
        | (Notification.created_at <= now - ANY_RETENTION)))
    db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


# ---------- reação aos fatos do jogo ----------

def _opponent(event: DomainEvent) -> uuid.UUID | None:
    raw = event.data.get("opponent_user_id")
    return raw if isinstance(raw, uuid.UUID) else None


def on_event(db: Session, event: DomainEvent) -> None:
    match_id = str(event.data.get("match_id", ""))
    game_id = event.data.get("game_id")
    opponent = _opponent(event)
    if event.kind == domain_events.MOVE_PLAYED and opponent is not None:
        clear_match_notices(db, event.user_id, match_id)  # quem jogou já viu a partida
        notify(db, opponent, "your_turn", {"match_id": match_id, "game_id": game_id},
               dedupe_key=f"your_turn:{match_id}")
    elif event.kind == domain_events.PLAYER_DISCONNECTED and opponent is not None:
        notify(db, opponent, "opponent_disconnected", {"match_id": match_id, "game_id": game_id},
               dedupe_key=f"opponent_disconnected:{match_id}")
    elif event.kind == domain_events.MATCH_FINISHED and event.data.get("online"):
        clear_match_notices(db, event.user_id, match_id)
        if event.data.get("actor_user_id") != event.user_id:  # quem encerrou já sabe
            notify(db, event.user_id, "match_ended",
                   {"match_id": match_id, "game_id": game_id, "outcome": event.data.get("outcome")})
