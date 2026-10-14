"""Entrega por WebSocket dos avisos criados numa transação, só depois do commit (RF-028)."""

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.realtime.hub import hub
from app.services.events import Event

_installed = False


def _flush(session: Session) -> None:
    pending: list[Event] = session.info.pop("pending_events", [])
    hub.publish_all(pending)


def _discard(session: Session, *_: Any) -> None:
    session.info.pop("pending_events", None)


def install() -> None:
    global _installed  # noqa: PLW0603
    if _installed:
        return
    event.listen(Session, "after_commit", _flush)
    event.listen(Session, "after_rollback", _discard)
    _installed = True
