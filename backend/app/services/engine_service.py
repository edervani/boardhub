"""Validação de lance sem persistência para partida local de visitante (RF-009, DT-007)."""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.game_engines.base import IllegalMove, InvalidState
from app.schemas.matches import EngineApplyOut, OutcomeOut
from app.services import catalog_service
from app.services.game_registry import KITS

MAX_STATE_BYTES = 8 * 1024


def apply_stateless(db: Session, age_band: str | None, game_id: str, state: dict[str, Any],
                    move_raw: str) -> EngineApplyOut:
    visible = {g.id for g in catalog_service.visible_games(db, age_band)}
    kit = KITS.get(game_id)
    if game_id not in visible or kit is None:
        raise ProblemError(404, "game_not_found", "Jogo não encontrado")
    if len(json.dumps(state)) > MAX_STATE_BYTES:
        raise ProblemError(422, "state_too_large", "Estado grande demais")
    engine = kit.engine
    try:
        current = engine.deserialize(state)
        new = engine.apply(current, engine.parse_move(move_raw))
    except InvalidState as exc:
        raise ProblemError(422, "invalid_state", "Estado inválido") from exc
    except IllegalMove as exc:
        raise ProblemError(422, "illegal_move", "Jogada ilegal", str(exc)) from exc
    out = engine.outcome(new)
    return EngineApplyOut(
        state=engine.serialize(new),
        outcome=OutcomeOut(winner=out.winner, reason=out.reason) if out else None,
        legal_moves=[str(m) for m in engine.legal_moves(new)],
    )
