"""Partidas online entre humanos: convite, fila, empate por acordo, abandono e presença.

RF-011, RF-012, RF-014, RF-015. Modo `online_casual`: **não ranqueado** (ranking virá depois).
O servidor decide assentos, turnos e resultados; nada disso vem do cliente (SEC-05, SEC-06).
Cada mudança de estado ocorre com a linha da partida bloqueada (doc 05 §4). Os serviços
devolvem `Event`s; a entrega por WebSocket é responsabilidade de `realtime`.
"""

import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.ratelimit import limiter
from app.models import DrawOffer, Match, MatchMove, MatchPlayer, QueueEntry, User, UserProfile
from app.models.base import new_id
from app.schemas.matches import ActiveMatchOut, MatchOut, QueueStatusOut
from app.services import catalog_service, guardian_service, match_service
from app.services.events import Event, match_ended, match_started
from app.services.game_registry import KITS

HOUR = 3600.0
# Sem I, L, O, 0 e 1 para evitar confusão ao ditar o código.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
ONLINE_MODES = ("online_casual", "online_ranked")
ACTIVE_STATUSES = ("waiting", "in_progress")
# RF-015: propostas de empate só nos jogos com empate por acordo (doc 02) e 1 a cada 10 lances.
DRAW_AGREEMENT_GAMES = frozenset({"checkers", "chess"})
MIN_PLIES_BETWEEN_DRAW_OFFERS = 10
OFFER_AI_AFTER_SECONDS = 60
MISSED_MOVES_LIMIT = 20  # doc 06 §3.6: acima disso envia-se snapshot completo
MAX_ACTIVE_LIST = 50


# ---------- utilidades ----------

def _code_digest(code: str) -> bytes:
    """HMAC do código: o espaço de códigos é pequeno, então um hash simples não bastaria."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, b"invite:" + code.encode(), hashlib.sha256).digest()


def normalize_code(raw: str) -> str | None:
    code = re.sub(r"[\s-]", "", raw).upper()
    if len(code) != CODE_LENGTH or any(c not in CODE_ALPHABET for c in code):
        return None
    return code


def _invalid_code() -> ProblemError:
    return ProblemError(404, "invite_not_found", "Código inválido ou expirado")


def _lock_users(db: Session, ids: list[uuid.UUID]) -> None:
    """Serializa operações do mesmo usuário (DT-010); ordem por id evita impasses."""
    db.execute(select(User.id).where(User.id.in_(ids)).order_by(User.id).with_for_update()).all()


def _my_seat(players: list[MatchPlayer], user_id: uuid.UUID) -> int:
    return next(p.seat for p in players if p.user_id == user_id)


def _require_game(db: Session, user: User, game_id: str) -> None:
    visible = {g.id for g in catalog_service.visible_games(db, user.age_band)}
    if game_id not in visible or game_id not in KITS:
        raise ProblemError(404, "game_not_found", "Jogo não encontrado")


def _expire_stale_invites(db: Session, user_id: uuid.UUID) -> None:
    now = clock.now()
    stale = db.scalars(
        select(Match).join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(MatchPlayer.user_id == user_id, Match.status == "waiting",
               Match.invite_expires_at <= now)).all()
    for match in stale:
        match.status = "aborted"
        match.finished_at = now


def _prepare_entry(db: Session, user: User, game_id: str) -> None:
    """Passos comuns a criar convite, entrar por código e entrar na fila (DT-010)."""
    guardian_service.require_online_access(user)
    _lock_users(db, [user.id])
    # Entrar em qualquer partida online tira o usuário da fila (evita estar em duas ao mesmo tempo).
    entry = db.scalar(select(QueueEntry).where(QueueEntry.user_id == user.id).with_for_update())
    if entry is not None:
        db.delete(entry)
        db.flush()
    _expire_stale_invites(db, user.id)
    busy = db.scalar(
        select(Match.id).join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(MatchPlayer.user_id == user.id, Match.game_id == game_id,
               Match.mode.in_(ONLINE_MODES), Match.status.in_(ACTIVE_STATUSES)).limit(1))
    if busy is not None:
        db.commit()  # preserva a limpeza acima
        raise ProblemError(409, "active_online_match", "Você já tem uma partida online deste jogo",
                           "Termine ou cancele a partida atual antes de começar outra.")


def _new_match(game_id: str, status: str, now: datetime) -> Match:
    kit = KITS[game_id]
    return Match(id=new_id(), game_id=game_id, mode="online_casual", status=status,
                 state=kit.engine.serialize(kit.engine.initial_state()), ply=0,
                 rules_version=kit.engine.rules_version,
                 started_at=now if status == "in_progress" else None)


# ---------- convite (RF-011) ----------

def create_invite(db: Session, user: User, game_id: str, preferred_seat: int | None) -> MatchOut:
    limiter.hit(f"match-create:{user.id}", 20, HOUR)
    guardian_service.require_online_access(user)
    _require_game(db, user, game_id)
    _prepare_entry(db, user, game_id)
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    now = clock.now()
    match = _new_match(game_id, "waiting", now)
    match.invite_code_hash = _code_digest(code)
    match.invite_expires_at = now + timedelta(seconds=get_settings().invite_ttl_seconds)
    match.invite_creator_seat = preferred_seat
    db.add(match)
    db.flush()
    player = MatchPlayer(match_id=match.id, seat=preferred_seat or 1, user_id=user.id, is_ai=False)
    db.add(player)
    db.commit()
    # O código só é devolvido aqui; depois disso só o HMAC existe no banco.
    return match_service.view(db, match, [player], user, invite_code=code)


def join_invite(db: Session, user: User, raw_code: str) -> tuple[MatchOut, list[Event]]:
    limiter.hit(f"invite-join:{user.id}", 20, HOUR)
    guardian_service.require_online_access(user)
    code = normalize_code(raw_code)
    match = db.scalar(select(Match).where(Match.invite_code_hash == _code_digest(code))
                      .with_for_update()) if code else None
    if match is None:
        raise _invalid_code()
    players = list(db.scalars(select(MatchPlayer).where(MatchPlayer.match_id == match.id)
                              .order_by(MatchPlayer.seat)))
    if any(p.user_id == user.id for p in players):
        raise ProblemError(403, "own_room", "Esta sala é sua",
                           "Compartilhe o código com outra pessoa para ela entrar.")
    if match.status == "aborted":
        raise _invalid_code()
    if match.status != "waiting":
        raise ProblemError(409, "room_full", "Sala cheia")
    now = clock.now()
    if match.invite_expires_at is None or match.invite_expires_at <= now:
        match.status = "aborted"
        match.finished_at = now
        db.commit()
        raise _invalid_code()
    visible = {g.id for g in catalog_service.visible_games(db, user.age_band)}
    if match.game_id not in visible:
        raise _invalid_code()  # não revela que o código existe para quem não pode jogar
    creator = players[0]
    assert creator.user_id is not None  # sala por convite sempre tem criador humano
    creator_id = creator.user_id
    _lock_users(db, [creator_id, user.id])
    _prepare_entry(db, user, match.game_id)
    creator_seat = match.invite_creator_seat or secrets.choice((1, 2))
    # Reatribui os assentos recriando as linhas (a chave primária inclui o assento).
    db.delete(creator)
    db.flush()
    seated = [
        MatchPlayer(match_id=match.id, seat=creator_seat, user_id=creator_id, is_ai=False,
                    disconnected_at=now),
        MatchPlayer(match_id=match.id, seat=3 - creator_seat, user_id=user.id, is_ai=False,
                    disconnected_at=now),
    ]
    seated.sort(key=lambda p: p.seat)
    db.add_all(seated)
    match.status = "in_progress"
    match.started_at = now
    db.commit()
    events = [match_started(match.id, match.game_id, (creator_id, user.id))]
    return match_service.view(db, match, seated, user), events


def cancel_invite(db: Session, user: User, match_id: uuid.UUID) -> None:
    match, _ = match_service.load_for_participant(db, user, match_id, lock=True)
    if match.mode not in ONLINE_MODES or match.status != "waiting":
        raise ProblemError(409, "not_cancellable",
                           "Só salas aguardando oponente podem ser canceladas")
    match.status = "aborted"
    match.finished_at = clock.now()
    db.commit()


# ---------- fila (RF-012) ----------

def _queue_lock_key(game_id: str) -> int:
    digest = hashlib.sha256(f"queue:{game_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _consume_matched(db: Session, entry: QueueEntry) -> QueueStatusOut:
    out = QueueStatusOut(state="matched", game_id=entry.game_id, match_id=entry.matched_match_id)
    db.delete(entry)
    db.commit()
    return out


def _still_eligible(db: Session, candidate: User, game_id: str) -> bool:
    if candidate.status != "active" or not candidate.preferences.allow_open_matchmaking:
        return False
    if candidate.age_band == "under_12" and candidate.guardian_user_id is None:
        return False
    visible = {g.id for g in catalog_service.visible_games(db, candidate.age_band)}
    busy = db.scalar(
        select(Match.id).join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(MatchPlayer.user_id == candidate.id, Match.game_id == game_id,
               Match.mode.in_(ONLINE_MODES), Match.status.in_(ACTIVE_STATUSES)).limit(1))
    return game_id in visible and busy is None


def enter_queue(db: Session, user: User, game_id: str) -> tuple[QueueStatusOut, list[Event]]:
    limiter.hit(f"queue:{user.id}", 30, HOUR)
    if not user.preferences.allow_open_matchmaking:
        raise ProblemError(403, "open_matchmaking_disabled", "Partidas abertas desativadas",
                           "O responsável por esta conta não liberou o pareamento aberto.")
    guardian_service.require_online_access(user)
    _require_game(db, user, game_id)
    _lock_users(db, [user.id])
    mine = db.scalar(select(QueueEntry).where(QueueEntry.user_id == user.id).with_for_update())
    if mine is not None and mine.matched_match_id is not None:
        return _consume_matched(db, mine), []
    if mine is not None and mine.game_id == game_id:
        mine.last_seen_at = clock.now()
        db.commit()
        return queue_status(db, user), []
    _prepare_entry(db, user, game_id)  # sai da fila de outro jogo, confere DT-010
    # Um jogo por vez: quem chega depois enxerga as entradas já confirmadas (sem perder pares).
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _queue_lock_key(game_id)})
    now = clock.now()
    cutoff = now - timedelta(seconds=get_settings().queue_stale_seconds)
    for _ in range(5):
        cand = db.scalar(
            select(QueueEntry).where(
                QueueEntry.game_id == game_id, QueueEntry.user_id != user.id,
                QueueEntry.matched_match_id.is_(None), QueueEntry.last_seen_at > cutoff)
            .order_by(QueueEntry.enqueued_at).limit(1).with_for_update(skip_locked=True))
        if cand is None:
            break
        cand_user = db.get(User, cand.user_id)
        if cand_user is None or not _still_eligible(db, cand_user, game_id):
            db.delete(cand)
            db.flush()
            continue
        first, second = secrets.SystemRandom().sample([user.id, cand.user_id], 2)
        match = _new_match(game_id, "in_progress", now)
        db.add(match)
        db.flush()
        db.add_all([MatchPlayer(match_id=match.id, seat=1, user_id=first, is_ai=False,
                                disconnected_at=now),
                    MatchPlayer(match_id=match.id, seat=2, user_id=second, is_ai=False,
                                disconnected_at=now)])
        cand.matched_match_id = match.id  # o outro jogador consome na próxima consulta
        db.commit()
        out = QueueStatusOut(state="matched", game_id=game_id, match_id=match.id)
        return out, [match_started(match.id, game_id, (first, second))]
    db.add(QueueEntry(user_id=user.id, game_id=game_id, enqueued_at=now, last_seen_at=now))
    db.commit()
    return QueueStatusOut(state="queued", game_id=game_id), []


def queue_status(db: Session, user: User) -> QueueStatusOut:
    entry = db.scalar(select(QueueEntry).where(QueueEntry.user_id == user.id).with_for_update())
    if entry is None:
        return QueueStatusOut(state="idle")
    if entry.matched_match_id is not None:
        return _consume_matched(db, entry)
    now = clock.now()
    entry.last_seen_at = now
    db.commit()
    waited = max(0, int((now - entry.enqueued_at).total_seconds()))
    return QueueStatusOut(state="queued", game_id=entry.game_id, waited_seconds=waited,
                          offer_ai=waited >= OFFER_AI_AFTER_SECONDS)


def leave_queue(db: Session, user: User) -> None:
    entry = db.scalar(select(QueueEntry).where(QueueEntry.user_id == user.id).with_for_update())
    if entry is None:
        return
    if entry.matched_match_id is not None:
        raise ProblemError(409, "already_matched", "Você já foi pareado",
                           "A partida já começou; abra-a na lista de partidas em andamento.")
    db.delete(entry)
    db.commit()


# ---------- empate por acordo e abandono (RF-015, RF-014) ----------

def _active_online(match: Match) -> None:
    if match.mode not in ONLINE_MODES:
        raise ProblemError(422, "not_online_match", "Esta ação vale só para partidas online")
    if match.status == "waiting":
        raise ProblemError(409, "match_not_started", "A partida ainda não começou")
    if match.status != "in_progress":
        raise ProblemError(409, "match_finished", "A partida já terminou")


def _pending_offer(db: Session, match_id: uuid.UUID) -> DrawOffer | None:
    return db.scalar(select(DrawOffer).where(DrawOffer.match_id == match_id,
                                             DrawOffer.status == "pending"))


def offer_draw(db: Session, user: User, match_id: uuid.UUID) -> tuple[MatchOut, list[Event]]:
    limiter.hit(f"online-cmd:{user.id}", 120, 60)
    match, players = match_service.load_for_participant(db, user, match_id, lock=True)
    _active_online(match)
    seat = _my_seat(players, user.id)
    if match.game_id not in DRAW_AGREEMENT_GAMES:
        raise ProblemError(422, "draw_not_available", "Este jogo não tem empate por acordo")
    if _pending_offer(db, match.id) is not None:
        raise ProblemError(409, "draw_offer_pending", "Já existe uma proposta de empate em aberto")
    last = db.scalar(select(DrawOffer).where(DrawOffer.match_id == match.id,
                                             DrawOffer.by_seat == seat)
                     .order_by(DrawOffer.at_ply.desc(), DrawOffer.created_at.desc()).limit(1))
    if last is not None and match.ply - last.at_ply < MIN_PLIES_BETWEEN_DRAW_OFFERS:
        wait = MIN_PLIES_BETWEEN_DRAW_OFFERS - (match.ply - last.at_ply)
        raise ProblemError(429, "draw_offer_limited", "Você já propôs empate há pouco",
                           f"Aguarde mais {wait} meio-lance(s) para propor de novo.")
    db.add(DrawOffer(match_id=match.id, by_seat=seat, at_ply=match.ply, status="pending",
                     created_at=clock.now()))
    db.commit()
    event = Event("draw_offered", {"match_id": str(match.id), "by_seat": seat},
                  match_id=match.id)
    return match_service.view(db, match, players, user), [event]


def respond_draw(db: Session, user: User, match_id: uuid.UUID,
                 accept: bool) -> tuple[MatchOut, list[Event]]:
    limiter.hit(f"online-cmd:{user.id}", 120, 60)
    match, players = match_service.load_for_participant(db, user, match_id, lock=True)
    _active_online(match)
    seat = _my_seat(players, user.id)
    offer = _pending_offer(db, match.id)
    if offer is None or offer.by_seat == seat:
        raise ProblemError(409, "no_draw_offer", "Não há proposta de empate para responder")
    offer.responded_at = clock.now()
    if accept:
        offer.status = "accepted"
        match_service.finish_with_winner(match, None, "agreement")
        events = [match_ended(match.id, match.result, match.end_reason, match.ply)]
    else:
        offer.status = "declined"
        events = [Event("draw_declined", {"match_id": str(match.id), "by_seat": seat,
                                          "reason": "declined"}, match_id=match.id)]
    db.commit()
    return match_service.view(db, match, players, user), events


def _last_activity(db: Session, match: Match) -> datetime:
    last = db.scalar(select(MatchMove.created_at).where(MatchMove.match_id == match.id)
                     .order_by(MatchMove.ply.desc()).limit(1))
    return last or match.started_at or match.created_at


def claim_abandon(db: Session, user: User, match_id: uuid.UUID) -> tuple[MatchOut, list[Event]]:
    """O oponente que está na vez há tempo demais (desconectado ou parado) perde por abandono."""
    limiter.hit(f"online-cmd:{user.id}", 120, 60)
    match, players = match_service.load_for_participant(db, user, match_id, lock=True)
    _active_online(match)
    seat = _my_seat(players, user.id)
    to_move = 1 if match.ply % 2 == 0 else 2
    if to_move == seat:
        raise ProblemError(409, "too_early", "Ainda é a sua vez",
                           "Só é possível reivindicar quando o adversário deve jogar.")
    opponent = next(p for p in players if p.seat == to_move)
    settings = get_settings()
    now = clock.now()
    last = _last_activity(db, match)
    if opponent.disconnected_at is not None:
        # A tolerância só conta no turno do desconectado (RF-014).
        since = max(opponent.disconnected_at, last)
        limit = settings.online_grace_seconds
    else:
        since, limit = last, settings.online_inactivity_seconds
    elapsed = (now - since).total_seconds()
    if elapsed < limit:
        raise ProblemError(409, "too_early", "Ainda é cedo para reivindicar",
                           f"Aguarde mais {int(limit - elapsed) + 1} segundo(s).")
    match_service.finish_with_winner(match, seat, "abandon")
    db.commit()
    events = [match_ended(match.id, match.result, match.end_reason, match.ply)]
    return match_service.view(db, match, players, user), events


# ---------- presença e retomada (RF-014) ----------

def _connection_event(match: Match, player: MatchPlayer) -> Event:
    grace = timedelta(seconds=get_settings().online_grace_seconds)
    deadline = player.disconnected_at + grace if player.disconnected_at else None
    return Event("player_connection", {
        "match_id": str(match.id), "seat": player.seat, "connected": deadline is None,
        "grace_deadline": deadline.isoformat() if deadline else None}, match_id=match.id)


def mark_connected(db: Session, user: User, match_id: uuid.UUID) -> list[Event]:
    match, players = match_service.load_for_participant(db, user, match_id, lock=True)
    mine = next(p for p in players if p.user_id == user.id)
    if match.status != "in_progress" or mine.disconnected_at is None:
        db.rollback()
        return []
    mine.disconnected_at = None
    db.commit()
    return [_connection_event(match, mine)]


def mark_disconnected(db: Session, user_id: uuid.UUID, match_id: uuid.UUID) -> list[Event]:
    match = db.scalar(select(Match).where(Match.id == match_id).with_for_update())
    if match is None or match.status != "in_progress":
        db.rollback()
        return []
    mine = db.scalar(select(MatchPlayer).where(MatchPlayer.match_id == match_id,
                                               MatchPlayer.user_id == user_id))
    if mine is None or mine.disconnected_at is not None:
        db.rollback()
        return []
    mine.disconnected_at = clock.now()
    db.commit()
    return [_connection_event(match, mine)]


@dataclass
class Snapshot:
    view: MatchOut
    your_seat: int
    missed_moves: list[dict[str, Any]]


def snapshot(db: Session, user: User, match_id: uuid.UUID, last_known_ply: int) -> Snapshot:
    """Estado oficial para (re)entrar numa partida, com os lances perdidos se forem poucos."""
    match, players = match_service.load_for_participant(db, user, match_id)
    missed: list[dict[str, Any]] = []
    if 0 <= last_known_ply < match.ply <= last_known_ply + MISSED_MOVES_LIMIT:
        rows = db.scalars(select(MatchMove).where(
            MatchMove.match_id == match.id, MatchMove.ply >= last_known_ply)
            .order_by(MatchMove.ply))
        missed = [{"ply": m.ply, "seat": m.seat, "move": m.move} for m in rows]
    return Snapshot(match_service.view(db, match, players, user), _my_seat(players, user.id),
                    missed)


# ---------- lobby (RF-008) ----------

def active_matches(db: Session, user: User) -> list[ActiveMatchOut]:
    _expire_stale_invites(db, user.id)
    db.commit()
    rows = db.execute(
        select(Match, MatchPlayer.seat).join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(MatchPlayer.user_id == user.id, Match.status.in_(ACTIVE_STATUSES))
        .order_by(Match.created_at.desc(), Match.id.desc()).limit(MAX_ACTIVE_LIST)).all()
    ids = [m.id for m, _ in rows if m.mode in ONLINE_MODES]
    opponents: dict[uuid.UUID, str] = {}
    if ids:
        pairs = db.execute(
            select(MatchPlayer.match_id, UserProfile.display_name)
            .join(UserProfile, UserProfile.user_id == MatchPlayer.user_id)
            .join(User, User.id == MatchPlayer.user_id)
            .where(MatchPlayer.match_id.in_(ids), MatchPlayer.user_id != user.id,
                   User.status != "pending_deletion")).tuples().all()
        opponents = dict(pairs)
    out: list[ActiveMatchOut] = []
    seen: set[uuid.UUID] = set()
    for match, seat in rows:
        if match.id in seen:  # partida local: o mesmo usuário ocupa os dois assentos
            continue
        seen.add(match.id)
        in_progress = match.status == "in_progress"
        to_move = 1 if match.ply % 2 == 0 else 2
        out.append(ActiveMatchOut(
            id=match.id, game_id=match.game_id, mode=match.mode, status=match.status,
            ply=match.ply, your_seat=seat,
            your_turn=in_progress and (match.mode == "local" or to_move == seat),
            opponent_name=opponents.get(match.id),
            invite_expires_at=match.invite_expires_at if match.status == "waiting" else None,
            created_at=match.created_at))
    return out
