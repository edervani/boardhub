"""Barramento simples de eventos de domínio, síncrono e dentro da transação (RF-026–028).

Quem produz o fato (fim de partida, tentativa da Academy, etc.) apenas chama `emit`; quem
reage (conquistas, notificações) se inscreve com `subscribe`. Os produtores não conhecem os
consumidores. Cada consumidor roda num savepoint: se falhar, o erro é registrado e a operação
principal (o lance, a tentativa) segue intacta. Nada aqui chama rede.
"""

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core import clock
from app.core.logging import get_logger

log = get_logger(__name__)

# Tipos de evento (contrato entre produtores e consumidores).
MATCH_FINISHED = "match_finished"          # um por pessoa humana da partida
MOVE_PLAYED = "move_played"                # lance numa partida online com outro humano
PLAYER_DISCONNECTED = "player_disconnected"  # saída de uma pessoa de partida online em curso
EXERCISE_ATTEMPTED = "exercise_attempted"  # tentativa da Academy
DAILY_CHALLENGE_COMPLETED = "daily_challenge_completed"


@dataclass(frozen=True)
class DomainEvent:
    kind: str
    user_id: uuid.UUID
    data: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: clock.now())


Handler = Callable[[Session, DomainEvent], None]
_handlers: list[Handler] = []


def subscribe(handler: Handler) -> None:
    """Inscrição idempotente (importar o módulo de novo não duplica a reação)."""
    if handler not in _handlers:
        _handlers.append(handler)


def emit(db: Session, event: DomainEvent) -> None:
    """Entrega o evento aos consumidores, na mesma transação e sem propagar falhas deles."""
    for handler in tuple(_handlers):
        try:
            with db.begin_nested():
                handler(db, event)
        except Exception as exc:  # noqa: BLE001 - engajamento nunca derruba o jogo
            log.error("falha ao tratar evento de domínio", extra={
                "event_kind": event.kind, "error_type": type(exc).__name__})


def emit_new(db: Session, kind: str, user_id: uuid.UUID, **data: Any) -> None:
    emit(db, DomainEvent(kind, user_id, data))
