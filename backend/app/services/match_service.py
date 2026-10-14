"""Casos de uso de partidas contra a IA e locais (RF-009, RF-010, RF-013, RF-015, RF-020).

O servidor é a autoridade: o cliente envia somente o lance. Cada mudança de estado ocorre
numa transação com bloqueio de linha da partida (doc 05 §4).
"""

import base64
import binascii
import random
import secrets
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.core.ratelimit import limiter
from app.game_engines.base import IllegalMove, InvalidState, state_hash
from app.models import AuditLog, Match, MatchMove, MatchPlayer, User
from app.models.base import new_id
from app.schemas.matches import MatchOut, MatchPage, MatchSummary, SeatOut
from app.services import catalog_service
from app.services.game_registry import KITS, GameKit

log = get_logger(__name__)
HOUR = 3600.0
MAX_PAGE = 100


def _not_found() -> ProblemError:
    return ProblemError(404, "not_found", "Partida não encontrada")


def _seat_to_move(ply: int) -> int:
    return 1 if ply % 2 == 0 else 2


def _kit(match: Match) -> GameKit:
    return KITS[match.game_id]


# ---------- leitura ----------

def _players(db: Session, match_id: uuid.UUID) -> list[MatchPlayer]:
    return list(db.scalars(select(MatchPlayer).where(MatchPlayer.match_id == match_id)
                           .order_by(MatchPlayer.seat)))


def _load_for_participant(db: Session, user: User, match_id: uuid.UUID,
                          lock: bool = False) -> tuple[Match, list[MatchPlayer]]:
    stmt = select(Match).where(Match.id == match_id)
    match = db.scalar(stmt.with_for_update() if lock else stmt)
    if match is None:
        raise _not_found()
    players = _players(db, match.id)
    if not any(p.user_id == user.id for p in players):
        raise _not_found()  # não participante e inexistente respondem igual (SEC-05)
    return match, players


def view(match: Match, players: list[MatchPlayer], user: User) -> MatchOut:
    kit = _kit(match)
    in_progress = match.status == "in_progress"
    state = kit.engine.deserialize(match.state) if in_progress else None
    legal = [str(m) for m in kit.engine.legal_moves(state)] if state is not None else []
    return MatchOut(
        id=match.id, game_id=match.game_id, mode=match.mode, status=match.status,
        ply=match.ply, state=match.state,
        to_move_seat=_seat_to_move(match.ply) if in_progress else None,
        legal_moves=legal, result=match.result, end_reason=match.end_reason,
        ai_level=match.ai_level, rules_version=match.rules_version,
        seats=[SeatOut(seat=p.seat, is_ai=p.is_ai, is_you=p.user_id == user.id)
               for p in players],
        created_at=match.created_at, finished_at=match.finished_at,
    )


def get_match(db: Session, user: User, match_id: uuid.UUID) -> MatchOut:
    match, players = _load_for_participant(db, user, match_id)
    return view(match, players, user)


def list_moves(db: Session, user: User, match_id: uuid.UUID, since_ply: int) -> list[MatchMove]:
    match, _ = _load_for_participant(db, user, match_id)
    return list(db.scalars(select(MatchMove).where(
        MatchMove.match_id == match.id, MatchMove.ply >= since_ply).order_by(MatchMove.ply)))


# ---------- criação ----------

def create_match(db: Session, user: User, game_id: str, mode: str, ai_level: int | None,
                 preferred_seat: int | None) -> MatchOut:
    limiter.hit(f"match-create:{user.id}", 20, HOUR)
    visible = {g.id for g in catalog_service.visible_games(db, user.age_band)}
    kit = KITS.get(game_id)
    if game_id not in visible or kit is None:
        raise ProblemError(404, "game_not_found", "Jogo não encontrado")
    state = kit.engine.serialize(kit.engine.initial_state())
    now = clock.now()
    match = Match(id=new_id(), game_id=game_id, mode=mode, status="in_progress", state=state,
                  ply=0, rules_version=kit.engine.rules_version, ai_level=ai_level,
                  ai_seed=secrets.randbelow(2**31) if mode == "ai" else None, started_at=now)
    db.add(match)
    db.flush()
    seat = preferred_seat or 1
    if mode == "ai":
        players = [MatchPlayer(match_id=match.id, seat=seat, user_id=user.id, is_ai=False),
                   MatchPlayer(match_id=match.id, seat=3 - seat, user_id=None, is_ai=True)]
    else:
        players = [MatchPlayer(match_id=match.id, seat=s, user_id=user.id, is_ai=False)
                   for s in (1, 2)]
    db.add_all(players)
    db.flush()
    _play_ai_turn_if_due(db, match, players, kit)
    db.commit()
    return view(match, players, user)


# ---------- lances ----------

def _finish(match: Match, kit: GameKit, winner: str | None, reason: str) -> None:
    match.status = "finished"
    match.finished_at = clock.now()
    match.end_reason = reason
    if winner is None:
        match.result = "draw"
    else:
        match.result = "p1_win" if winner == kit.symbols[0] else "p2_win"


def _record(db: Session, match: Match, kit: GameKit, move_raw: str,
            client_move_id: uuid.UUID) -> None:
    """Valida e aplica um lance. Levanta IllegalMove; aborta a partida se o estado for inválido."""
    try:
        state = kit.engine.deserialize(match.state)
    except InvalidState:
        match.status = "aborted"
        match.finished_at = clock.now()
        db.add(AuditLog(actor_user_id=None, action="match_aborted", target_type="match",
                        target_id=str(match.id), details={"reason": "invalid_state"}))
        db.commit()
        log.error("estado de partida inválido", extra={"match_ref": str(match.id)[:8]})
        raise ProblemError(409, "match_aborted", "Esta partida foi encerrada por um erro") from None
    move = kit.engine.parse_move(move_raw)
    new_state = kit.engine.apply(state, move)
    serialized = kit.engine.serialize(new_state)
    db.add(MatchMove(match_id=match.id, ply=match.ply, seat=_seat_to_move(match.ply),
                     move=str(move), client_move_id=client_move_id,
                     state_after_hash=bytes.fromhex(state_hash(serialized))))
    match.state = serialized
    match.ply += 1
    if (outcome := kit.engine.outcome(new_state)) is not None:
        _finish(match, kit, outcome.winner, "normal")
    db.flush()


def _play_ai_turn_if_due(db: Session, match: Match, players: list[MatchPlayer],
                         kit: GameKit) -> None:
    if match.mode != "ai" or match.status != "in_progress" or match.ai_level is None:
        return
    seat = _seat_to_move(match.ply)
    if not any(p.seat == seat and p.is_ai for p in players):
        return
    state = kit.engine.deserialize(match.state)
    rng = random.Random(f"{match.ai_seed}:{match.ply}")  # noqa: S311 - IA de jogo, não segurança
    move = kit.choose_ai_move(state, match.ai_level, rng)
    _record(db, match, kit, str(move), uuid.uuid4())


def submit_move(db: Session, user: User, match_id: uuid.UUID, expected_ply: int,
                move_raw: str, client_move_id: uuid.UUID) -> MatchOut:
    limiter.hit(f"move:{user.id}", 120, 60)
    match, players = _load_for_participant(db, user, match_id, lock=True)
    repeated = db.scalar(select(MatchMove.ply).where(
        MatchMove.match_id == match.id, MatchMove.client_move_id == client_move_id))
    if repeated is not None:
        return view(match, players, user)  # reenvio idempotente: nada é gravado de novo
    if match.status != "in_progress":
        raise ProblemError(409, "match_finished", "A partida já terminou")
    if expected_ply != match.ply:
        raise ProblemError(409, "stale_state", "Estado desatualizado",
                           f"A partida está no lance {match.ply}. Atualize e tente de novo.")
    seat = _seat_to_move(match.ply)
    if not any(p.seat == seat and p.user_id == user.id for p in players):
        raise ProblemError(403, "not_your_turn", "Não é a sua vez")
    kit = _kit(match)
    try:
        _record(db, match, kit, move_raw, client_move_id)
    except IllegalMove as exc:
        db.rollback()
        raise ProblemError(422, "illegal_move", "Jogada ilegal", str(exc)) from exc
    _play_ai_turn_if_due(db, match, players, kit)
    db.commit()
    return view(match, players, user)


def resign(db: Session, user: User, match_id: uuid.UUID) -> MatchOut:
    match, players = _load_for_participant(db, user, match_id, lock=True)
    if match.status != "in_progress":
        raise ProblemError(409, "match_finished", "A partida já terminou")
    if match.mode == "local":
        loser = _seat_to_move(match.ply)
    else:
        loser = next(p.seat for p in players if p.user_id == user.id)
    match.status = "finished"
    match.finished_at = clock.now()
    match.end_reason = "resign"
    match.result = "p2_win" if loser == 1 else "p1_win"
    db.commit()
    return view(match, players, user)


# ---------- histórico ----------

def _encode_cursor(created_at: datetime, match_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{match_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, ident = raw.split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(ident)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ProblemError(422, "invalid_cursor", "Cursor inválido") from exc


def list_matches(db: Session, user: User, game_id: str | None, mode: str | None,
                 status: str | None, cursor: str | None, limit: int) -> MatchPage:
    limit = max(1, min(limit, MAX_PAGE))
    mine = select(MatchPlayer.match_id).where(MatchPlayer.user_id == user.id)
    stmt = select(Match).where(Match.id.in_(mine))
    if game_id:
        stmt = stmt.where(Match.game_id == game_id)
    if mode:
        stmt = stmt.where(Match.mode == mode)
    if status:
        stmt = stmt.where(Match.status == status)
    if cursor:
        ts, ident = _decode_cursor(cursor)
        stmt = stmt.where((Match.created_at < ts) | ((Match.created_at == ts) & (Match.id < ident)))
    rows = list(db.scalars(stmt.order_by(Match.created_at.desc(), Match.id.desc())
                           .limit(limit + 1)))
    page, more = rows[:limit], len(rows) > limit
    items = [MatchSummary(id=m.id, game_id=m.game_id, mode=m.mode, status=m.status,
                          result=m.result, ply=m.ply, created_at=m.created_at,
                          finished_at=m.finished_at) for m in page]
    return MatchPage(items=items,
                     next_cursor=_encode_cursor(page[-1].created_at, page[-1].id) if more else None)
