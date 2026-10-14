"""Casos de uso de partidas contra a IA e locais (RF-009, RF-010, RF-013, RF-015, RF-020).

O servidor é a autoridade: o cliente envia somente o lance. Cada mudança de estado ocorre
numa transação com bloqueio de linha da partida (doc 05 §4).
"""

import base64
import binascii
import random
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.mentor.notation import chess_san_moves
from app.core import clock
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.core.ratelimit import limiter
from app.game_engines.base import IllegalMove, InvalidState, state_hash
from app.models import AuditLog, DrawOffer, Match, MatchMove, MatchPlayer, User, UserProfile
from app.models.base import new_id
from app.schemas.matches import MatchOut, MatchPage, MatchSummary, PlayerOut, SeatOut
from app.schemas.ranking import RatingChangeOut
from app.services import catalog_service, rating_service, usage_service
from app.services.events import Event, match_ended
from app.services.game_registry import KITS, GameKit

log = get_logger(__name__)
HOUR = 3600.0
# Motivo do fim no banco para cada motivo do motor; os demais viram "normal".
END_REASON_BY_OUTCOME = {"repetition": "repetition", "kings_only": "kings_only",
                         "stalemate": "stalemate", "fifty_move": "fifty_move"}
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


def load_for_participant(db: Session, user: User, match_id: uuid.UUID,
                          lock: bool = False) -> tuple[Match, list[MatchPlayer]]:
    stmt = select(Match).where(Match.id == match_id)
    match = db.scalar(stmt.with_for_update() if lock else stmt)
    if match is None:
        raise _not_found()
    players = _players(db, match.id)
    if not any(p.user_id == user.id for p in players):
        raise _not_found()  # não participante e inexistente respondem igual (SEC-05)
    return match, players


def is_online(match: Match) -> bool:
    return match.mode.startswith("online")


def _players_out(db: Session, players: list[MatchPlayer]) -> list[PlayerOut]:
    ids = [p.user_id for p in players if p.user_id is not None]
    # Conta em período de exclusão (RF-030) já aparece como removida para o oponente.
    names = dict(db.execute(
        select(UserProfile.user_id, UserProfile.display_name)
        .join(User, User.id == UserProfile.user_id)
        .where(UserProfile.user_id.in_(ids), User.status != "pending_deletion")
    ).tuples().all()) if ids else {}
    grace = timedelta(seconds=get_settings().online_grace_seconds)
    return [PlayerOut(seat=p.seat, display_name=names.get(p.user_id) if p.user_id else None,
                      connected=p.disconnected_at is None,
                      grace_deadline=p.disconnected_at + grace if p.disconnected_at else None)
            for p in players if not p.is_ai]


def _san_moves(match: Match) -> list[str]:
    if match.game_id != "chess":
        return []
    moves = match.state.get("moves")
    return chess_san_moves([str(m) for m in moves]) if isinstance(moves, list) else []


def view(db: Session, match: Match, players: list[MatchPlayer], user: User,
         invite_code: str | None = None) -> MatchOut:
    kit = _kit(match)
    in_progress = match.status == "in_progress"
    state = kit.engine.deserialize(match.state) if in_progress else None
    legal = [str(m) for m in kit.engine.legal_moves(state)] if state is not None else []
    online = is_online(match)
    offer_seat = db.scalar(select(DrawOffer.by_seat).where(
        DrawOffer.match_id == match.id, DrawOffer.status == "pending")) \
        if online and in_progress else None
    return MatchOut(
        players=_players_out(db, players) if online else [],
        invite_code=invite_code,
        invite_expires_at=match.invite_expires_at if match.status == "waiting" else None,
        draw_offer_by_seat=offer_seat,
        id=match.id, game_id=match.game_id, mode=match.mode, status=match.status,
        ply=match.ply, state=match.state,
        to_move_seat=_seat_to_move(match.ply) if in_progress else None,
        legal_moves=legal, result=match.result, end_reason=match.end_reason,
        ai_level=match.ai_level, rules_version=match.rules_version,
        seats=[SeatOut(seat=p.seat, is_ai=p.is_ai, is_you=p.user_id == user.id)
               for p in players],
        rating_changes=[RatingChangeOut(seat=c.seat, before=c.before, after=c.after)
                        for c in rating_service.changes_from_players(players)],
        san_moves=_san_moves(match),
        created_at=match.created_at, finished_at=match.finished_at,
    )


def get_match(db: Session, user: User, match_id: uuid.UUID) -> MatchOut:
    match, players = load_for_participant(db, user, match_id)
    return view(db, match, players, user)


def list_moves(db: Session, user: User, match_id: uuid.UUID, since_ply: int) -> list[MatchMove]:
    match, _ = load_for_participant(db, user, match_id)
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
    usage_service.require_within_limit(db, user)  # RF-034: limite diário esgotado
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
    players.sort(key=lambda p: p.seat)
    db.add_all(players)
    db.flush()
    _play_ai_turn_if_due(db, match, players, kit)
    usage_service.touch(db, user, now)
    db.commit()
    return view(db, match, players, user)


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
            client_move_id: uuid.UUID) -> str:
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
                     state_after_hash=bytes.fromhex(state_hash(serialized)),
                     created_at=clock.now()))
    match.state = serialized
    match.ply += 1
    if (outcome := kit.engine.outcome(new_state)) is not None:
        _finish(match, kit, outcome.winner, END_REASON_BY_OUTCOME.get(outcome.reason, "normal"))
    db.flush()
    return str(move)


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


class StaleStateError(ProblemError):
    """`expected_ply` antigo; carrega o lance atual para o cliente se ressincronizar."""

    def __init__(self, current_ply: int) -> None:
        super().__init__(409, "stale_state", "Estado desatualizado",
                         f"A partida está no lance {current_ply}. Atualize e tente de novo.")
        self.current_ply = current_ply


@dataclass
class MoveResult:
    view: MatchOut
    # Eventos novos a difundir para a sala da partida (vazio em reenvio idempotente).
    events: list[Event]
    # Em reenvio idempotente: o `move_applied` já gravado, só para quem reenviou.
    duplicate: Event | None = None


def move_applied(match: Match, seat: int, move: str) -> Event:
    """Evento de lance aplicado; `ply` é o total de meio-lances após ele (= `seq`).

    Leva também os lances legais de quem joga agora: o cliente não tem motor de regras.
    """
    in_progress = match.status == "in_progress"
    kit = _kit(match)
    legal = [str(m) for m in kit.engine.legal_moves(kit.engine.deserialize(match.state))] \
        if in_progress else []
    next_seat = _seat_to_move(match.ply) if in_progress else None
    payload: dict[str, Any] = {"match_id": str(match.id), "ply": match.ply, "seat": seat,
                               "move": move, "state": match.state, "next_seat": next_seat,
                               "legal_moves": legal}
    san = _san_moves(match)
    if san:  # xadrez: o cliente exibe o lance na notação escolhida (RF-007) sem motor próprio
        payload["san"] = san[-1]
    return Event("move_applied", payload, seq=match.ply, match_id=match.id)


def _expire_draw_offers_on_move(db: Session, match: Match, mover_seat: int) -> list[Event]:
    """Jogar é recusar a proposta de empate feita pelo adversário (RF-015)."""
    offers = db.scalars(select(DrawOffer).where(
        DrawOffer.match_id == match.id, DrawOffer.status == "pending",
        DrawOffer.by_seat != mover_seat)).all()
    for offer in offers:
        offer.status = "expired"
        offer.responded_at = clock.now()
    if not offers:
        return []
    return [Event("draw_declined", {"match_id": str(match.id), "by_seat": mover_seat,
                                    "reason": "moved"}, match_id=match.id)]


def submit_move_result(db: Session, user: User, match_id: uuid.UUID, expected_ply: int,
                       move_raw: str, client_move_id: uuid.UUID) -> MoveResult:
    limiter.hit(f"move:{user.id}", 120, 60)
    match, players = load_for_participant(db, user, match_id, lock=True)
    repeated = db.scalar(select(MatchMove).where(
        MatchMove.match_id == match.id, MatchMove.client_move_id == client_move_id))
    if repeated is not None:  # reenvio idempotente: nada é gravado de novo
        dup = move_applied(match, repeated.seat, repeated.move)
        dup.payload["duplicate"] = True
        return MoveResult(view(db, match, players, user), [], dup if is_online(match) else None)
    if match.status == "waiting":
        raise ProblemError(409, "match_not_started", "A partida ainda não começou")
    if match.status != "in_progress":
        raise ProblemError(409, "match_finished", "A partida já terminou")
    usage_service.require_within_limit_for_move(db, user)
    if expected_ply != match.ply:
        raise StaleStateError(match.ply)
    seat = _seat_to_move(match.ply)
    if not any(p.seat == seat and p.user_id == user.id for p in players):
        raise ProblemError(403, "not_your_turn", "Não é a sua vez")
    kit = _kit(match)
    try:
        move_text = _record(db, match, kit, move_raw, client_move_id)
    except IllegalMove as exc:
        db.rollback()
        raise ProblemError(422, "illegal_move", "Jogada ilegal", str(exc)) from exc
    events: list[Event] = []
    if is_online(match):
        events.append(move_applied(match, seat, move_text))
        events.extend(_expire_draw_offers_on_move(db, match, seat))
        if match.status == "finished":
            events.append(finish_event(db, match, players))
    _play_ai_turn_if_due(db, match, players, kit)
    usage_service.touch(db, user)
    db.commit()
    return MoveResult(view(db, match, players, user), events)


def submit_move(db: Session, user: User, match_id: uuid.UUID, expected_ply: int,
                move_raw: str, client_move_id: uuid.UUID) -> MatchOut:
    return submit_move_result(db, user, match_id, expected_ply, move_raw, client_move_id).view


# RF-015: desistência/abandono antes do 2º lance de cada lado (4 meios-lances) anula a partida
# ranqueada (antiabuso); a partida anulada não altera rating.
RANKED_MIN_PLIES = 4


def finish_with_winner(match: Match, winner_seat: int | None, reason: str) -> None:
    """Encerra uma partida por motivo externo ao motor (desistência, abandono, acordo)."""
    match.finished_at = clock.now()
    if match.mode == "online_ranked" and reason in ("resign", "abandon") \
            and match.ply < RANKED_MIN_PLIES:
        match.status = "annulled"
        match.end_reason = "annulled"
        match.result = None
        return
    match.status = "finished"
    match.end_reason = reason
    match.result = "draw" if winner_seat is None else ("p1_win" if winner_seat == 1 else "p2_win")


def finish_event(db: Session, match: Match, players: list[MatchPlayer]) -> Event:
    """Liquida o rating (se a partida for ranqueada e válida) e descreve o fim da partida.

    Deve ser chamado na mesma transação que encerrou a partida, antes do `commit`.
    """
    changes = rating_service.settle(db, match, players)
    return match_ended(match.id, match.result, match.end_reason, match.ply,
                       [{"seat": c.seat, "before": c.before, "after": c.after}
                        for c in changes])


def resign_result(db: Session, user: User, match_id: uuid.UUID) -> tuple[MatchOut, list[Event]]:
    limiter.hit(f"online-cmd:{user.id}", 120, 60)
    match, players = load_for_participant(db, user, match_id, lock=True)
    if match.status == "waiting":
        raise ProblemError(409, "match_not_started", "A partida ainda não começou")
    if match.status != "in_progress":
        raise ProblemError(409, "match_finished", "A partida já terminou")
    if match.mode == "local":
        loser = _seat_to_move(match.ply)
    else:
        loser = next(p.seat for p in players if p.user_id == user.id)
    finish_with_winner(match, 3 - loser, "resign")
    events = [finish_event(db, match, players)] if is_online(match) else []
    db.commit()
    return view(db, match, players, user), events


def resign(db: Session, user: User, match_id: uuid.UUID) -> MatchOut:
    return resign_result(db, user, match_id)[0]


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
