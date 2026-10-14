"""Eventos de domínio produzidos pelos casos de uso e difundidos pela camada de tempo real.

Os serviços apenas descrevem *o que* aconteceu; quem entrega (WebSocket) fica em `realtime`
(doc 04 §5). Por isso este módulo não importa nada de rede.
"""

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any]
    # Número de sequência monotônico por partida (= ply quando ligado a um lance).
    seq: int | None = None
    # Sala da partida (todos os conectados a ela) e/ou usuários específicos.
    match_id: uuid.UUID | None = None
    user_ids: tuple[uuid.UUID, ...] = ()


def match_ended(match_id: uuid.UUID, result: str | None, end_reason: str | None,
                ply: int) -> Event:
    return Event("match_ended", {"match_id": str(match_id), "result": result,
                                 "end_reason": end_reason, "ply": ply},
                 seq=ply, match_id=match_id)


def match_started(match_id: uuid.UUID, game_id: str,
                  user_ids: tuple[uuid.UUID, ...]) -> Event:
    """Avisa os dois jogadores (mesmo sem estarem na sala) que a partida começou."""
    return Event("match_started", {"match_id": str(match_id), "game_id": game_id},
                 match_id=match_id, user_ids=user_ids)
