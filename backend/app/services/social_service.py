"""Amizades, bloqueios e convites diretos entre amigos (RF-032, DT-022).

Regras de proteção (ECA Digital, doc 09 §10), aplicadas sempre no servidor:
- sem chat livre: a interação social é só pedir amizade e convidar para partida;
- conta de menor só usa o social com responsável vinculado que liberou o contato
  (`allow_open_matchmaking`, a mesma chave de partidas com desconhecidos, RF-034);
- menor e adulto nunca se tornam amigos (P-24); a recusa é igual a "conta inexistente";
- bloqueio e conta alheia respondem 404, nunca revelando quem bloqueou quem (SEC-05).
"""

import unicodedata
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core import clock
from app.core.errors import ProblemError
from app.core.ratelimit import limiter
from app.models import (
    DirectInvitation,
    Friendship,
    Match,
    MatchPlayer,
    User,
    UserBlock,
    UserProfile,
)
from app.schemas.matches import MatchOut
from app.schemas.social import (
    BlockOut,
    DirectInvitationOut,
    FriendOut,
    FriendRequestOut,
    FriendRequestsOut,
    PersonOut,
)
from app.services import online_service
from app.services.events import Event

DAY = 86400.0
HOUR = 3600.0
REQUEST_COOLDOWN = timedelta(days=7)  # depois de recusado, o mesmo autor espera para repetir
MAX_PENDING_OUT = 30


def _not_found() -> ProblemError:
    return ProblemError(404, "user_not_found", "Pessoa não encontrada")


def _friendship_not_found() -> ProblemError:
    return ProblemError(404, "friendship_not_found", "Amizade não encontrada")


def _invitation_not_found() -> ProblemError:
    return ProblemError(404, "invitation_not_found", "Convite não encontrado ou expirado")


def _pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if a.int < b.int else (b, a)


def _person(profile: UserProfile) -> PersonOut:
    return PersonOut(display_name=profile.display_name, avatar_key=profile.avatar_key)


# ---------- regras de contato (ECA) ----------

def social_ready(user: User) -> bool:
    """Adulto sempre; menor só com responsável vinculado que liberou o contato."""
    if not user.is_minor:
        return True
    return user.guardian_user_id is not None and user.preferences.allow_open_matchmaking


def require_social_ready(user: User) -> None:
    if not social_ready(user):
        raise ProblemError(403, "supervision_required", "Ação restrita ao responsável",
                           "Peça ao responsável para liberar o contato com amigos no painel "
                           "do responsável.")


def pair_allowed(a: User, b: User) -> bool:
    """Menor só se relaciona com menor, e só quando os dois estão liberados (P-24)."""
    return a.is_minor == b.is_minor and social_ready(a) and social_ready(b)


def is_blocked_between(db: Session, a: uuid.UUID, b: uuid.UUID) -> bool:
    found = db.scalar(select(UserBlock.id).where(
        or_((UserBlock.blocker_id == a) & (UserBlock.blocked_id == b),
            (UserBlock.blocker_id == b) & (UserBlock.blocked_id == a))).limit(1))
    return found is not None


# ---------- localizar pessoa pelo apelido ----------

def _knows(db: Session, me: uuid.UUID, other: uuid.UUID) -> bool:
    low, high = _pair(me, other)
    friend = db.scalar(select(Friendship.id).where(
        Friendship.user_low_id == low, Friendship.user_high_id == high).limit(1))
    if friend is not None:
        return True
    theirs = aliased(MatchPlayer)
    shared = db.scalar(
        select(MatchPlayer.match_id).join(theirs, theirs.match_id == MatchPlayer.match_id)
        .where(MatchPlayer.user_id == me, theirs.user_id == other).limit(1))
    return shared is not None


def find_by_display_name(db: Session, me: User, raw: str) -> User:
    """Conta ativa com este apelido que `me` pode enxergar: perfil público, amigo ou
    alguém com quem já dividiu uma partida. Qualquer outro caso é 404 igual (SEC-02)."""
    name = unicodedata.normalize("NFKC", raw).strip()
    row = db.execute(
        select(User, UserProfile).join(UserProfile, UserProfile.user_id == User.id)
        .where(func.lower(UserProfile.display_name) == name.lower(),
               User.status == "active", User.id != me.id)).first()
    if row is None:
        raise _not_found()
    target, profile = row
    if not profile.is_public and not _knows(db, me.id, target.id):
        raise _not_found()
    return target


# ---------- pedidos de amizade ----------

def _friendship(db: Session, a: uuid.UUID, b: uuid.UUID, lock: bool = False) -> Friendship | None:
    low, high = _pair(a, b)
    stmt = select(Friendship).where(Friendship.user_low_id == low,
                                    Friendship.user_high_id == high)
    return db.scalar(stmt.with_for_update() if lock else stmt)


def _other_id(f: Friendship, me: uuid.UUID) -> uuid.UUID:
    return f.user_high_id if f.user_low_id == me else f.user_low_id


def request_friendship(db: Session, me: User, display_name: str) -> FriendRequestOut:
    limiter.hit(f"friend-request:{me.id}", 20, DAY)
    require_social_ready(me)
    target = find_by_display_name(db, me, display_name)
    if is_blocked_between(db, me.id, target.id) or not pair_allowed(me, target):
        raise _not_found()
    now = clock.now()
    low, high = _pair(me.id, target.id)
    db.execute(select(User.id).where(User.id.in_([low, high])).order_by(User.id).with_for_update())
    existing = _friendship(db, me.id, target.id, lock=True)
    if existing is None:
        pending_out = db.scalar(select(func.count()).select_from(Friendship).where(
            Friendship.requested_by == me.id, Friendship.status == "pending")) or 0
        if pending_out >= MAX_PENDING_OUT:
            raise ProblemError(429, "too_many_pending_requests", "Pedidos pendentes demais",
                               "Aguarde respostas antes de enviar novos pedidos.")
        existing = Friendship(user_low_id=low, user_high_id=high, requested_by=me.id,
                              status="pending", created_at=now)
        db.add(existing)
    elif existing.status == "accepted":
        raise ProblemError(409, "already_friends", "Vocês já são amigos")
    elif existing.status == "pending":
        if existing.requested_by == me.id:
            raise ProblemError(409, "request_pending", "Pedido já enviado")
        existing.status = "accepted"  # o outro lado já tinha pedido: os dois querem
        existing.responded_at = now
    else:  # declined
        if (existing.requested_by == me.id and existing.responded_at is not None
                and existing.responded_at + REQUEST_COOLDOWN > now):
            retry = int((existing.responded_at + REQUEST_COOLDOWN - now).total_seconds()) + 1
            raise ProblemError(409, "request_cooldown", "Aguarde para pedir de novo",
                               "Você poderá enviar outro pedido em alguns dias.",
                               {"Retry-After": str(retry)})
        existing.status, existing.requested_by = "pending", me.id
        existing.responded_at = None
        existing.created_at = now
    db.commit()
    return FriendRequestOut(friendship_id=existing.id, display_name=target.profile.display_name,
                            avatar_key=target.profile.avatar_key, created_at=existing.created_at)


def _load_for_member(db: Session, me: User, friendship_id: uuid.UUID,
                     lock: bool = True) -> Friendship:
    stmt = select(Friendship).where(Friendship.id == friendship_id)
    f = db.scalar(stmt.with_for_update() if lock else stmt)
    if f is None or me.id not in (f.user_low_id, f.user_high_id):
        raise _friendship_not_found()  # alheia e inexistente respondem igual
    return f


def _other_user(db: Session, f: Friendship, me: User) -> User:
    other = db.get(User, _other_id(f, me.id))
    if other is None or other.status != "active":
        raise _friendship_not_found()
    return other


def accept_request(db: Session, me: User, friendship_id: uuid.UUID) -> FriendOut:
    limiter.hit(f"friend-respond:{me.id}", 60, HOUR)
    f = _load_for_member(db, me, friendship_id)
    if f.status != "pending" or f.requested_by == me.id:
        raise _friendship_not_found()
    require_social_ready(me)
    other = _other_user(db, f, me)
    if is_blocked_between(db, me.id, other.id) or not pair_allowed(me, other):
        raise _friendship_not_found()
    now = clock.now()
    f.status, f.responded_at = "accepted", now
    db.commit()
    return FriendOut(friendship_id=f.id, display_name=other.profile.display_name,
                     avatar_key=other.profile.avatar_key, since=now)


def decline_request(db: Session, me: User, friendship_id: uuid.UUID) -> None:
    limiter.hit(f"friend-respond:{me.id}", 60, HOUR)
    f = _load_for_member(db, me, friendship_id)
    if f.status != "pending" or f.requested_by == me.id:
        raise _friendship_not_found()
    f.status, f.responded_at = "declined", clock.now()
    db.commit()


def remove_friendship(db: Session, me: User, friendship_id: uuid.UUID) -> None:
    """Desfaz amizade ou cancela pedido próprio. Pedido recebido se recusa por `decline`."""
    f = _load_for_member(db, me, friendship_id)
    if f.status == "declined" or (f.status == "pending" and f.requested_by != me.id):
        raise _friendship_not_found()
    _cancel_invitations_between(db, me.id, _other_id(f, me.id))
    db.delete(f)
    db.commit()


def list_friends(db: Session, me: User) -> list[FriendOut]:
    other_id = func.coalesce(func.nullif(Friendship.user_low_id, me.id),
                             Friendship.user_high_id)
    rows = db.execute(
        select(Friendship, UserProfile)
        .join(User, User.id == other_id)
        .join(UserProfile, UserProfile.user_id == User.id)
        .where(Friendship.status == "accepted", User.status == "active",
               or_(Friendship.user_low_id == me.id, Friendship.user_high_id == me.id))
        .order_by(func.lower(UserProfile.display_name))).all()
    return [FriendOut(friendship_id=f.id, display_name=p.display_name, avatar_key=p.avatar_key,
                      since=f.responded_at or f.created_at) for f, p in rows]


def list_requests(db: Session, me: User) -> FriendRequestsOut:
    other_id = func.coalesce(func.nullif(Friendship.user_low_id, me.id),
                             Friendship.user_high_id)
    rows = db.execute(
        select(Friendship, UserProfile)
        .join(User, User.id == other_id)
        .join(UserProfile, UserProfile.user_id == User.id)
        .where(Friendship.status == "pending", User.status == "active",
               or_(Friendship.user_low_id == me.id, Friendship.user_high_id == me.id))
        .order_by(Friendship.created_at)).all()
    incoming: list[FriendRequestOut] = []
    outgoing: list[FriendRequestOut] = []
    for f, p in rows:
        item = FriendRequestOut(friendship_id=f.id, display_name=p.display_name,
                                avatar_key=p.avatar_key, created_at=f.created_at)
        (outgoing if f.requested_by == me.id else incoming).append(item)
    return FriendRequestsOut(incoming=incoming, outgoing=outgoing)


# ---------- bloqueio ----------

def block_user(db: Session, me: User, display_name: str) -> BlockOut:
    limiter.hit(f"block:{me.id}", 30, HOUR)
    target = find_by_display_name(db, me, display_name)
    block = db.scalar(select(UserBlock).where(UserBlock.blocker_id == me.id,
                                              UserBlock.blocked_id == target.id))
    if block is None:
        block = UserBlock(blocker_id=me.id, blocked_id=target.id, created_at=clock.now())
        db.add(block)
    _cancel_invitations_between(db, me.id, target.id)
    low, high = _pair(me.id, target.id)
    db.execute(delete(Friendship).where(Friendship.user_low_id == low,
                                        Friendship.user_high_id == high))
    db.commit()
    return BlockOut(block_id=block.id, display_name=target.profile.display_name,
                    avatar_key=target.profile.avatar_key, created_at=block.created_at)


def list_blocks(db: Session, me: User) -> list[BlockOut]:
    rows = db.execute(
        select(UserBlock, UserProfile)
        .join(UserProfile, UserProfile.user_id == UserBlock.blocked_id)
        .where(UserBlock.blocker_id == me.id).order_by(UserBlock.created_at)).all()
    return [BlockOut(block_id=b.id, display_name=p.display_name, avatar_key=p.avatar_key,
                     created_at=b.created_at) for b, p in rows]


def unblock(db: Session, me: User, block_id: uuid.UUID) -> None:
    block = db.get(UserBlock, block_id)
    if block is None or block.blocker_id != me.id:
        raise ProblemError(404, "block_not_found", "Bloqueio não encontrado")
    db.delete(block)
    db.commit()


# ---------- convites diretos ----------

def _abort_waiting(db: Session, match_id: uuid.UUID) -> None:
    match = db.scalar(select(Match).where(Match.id == match_id).with_for_update())
    if match is not None and match.status == "waiting":
        match.status = "aborted"
        match.finished_at = clock.now()


def _close(db: Session, inv: DirectInvitation, status: str) -> None:
    inv.status, inv.responded_at = status, clock.now()
    _abort_waiting(db, inv.match_id)


def _cancel_invitations_between(db: Session, a: uuid.UUID, b: uuid.UUID) -> None:
    pending = db.scalars(select(DirectInvitation).where(
        DirectInvitation.status == "pending",
        or_((DirectInvitation.sender_id == a) & (DirectInvitation.recipient_id == b),
            (DirectInvitation.sender_id == b) & (DirectInvitation.recipient_id == a)))).all()
    for inv in pending:
        _close(db, inv, "cancelled")


def cancel_all_for(db: Session, user_id: uuid.UUID) -> None:
    """Cancela convites pendentes de/para uma conta (suspensão, RF-031). Não faz commit."""
    pending = db.scalars(select(DirectInvitation).where(
        DirectInvitation.status == "pending",
        or_(DirectInvitation.sender_id == user_id,
            DirectInvitation.recipient_id == user_id))).all()
    for inv in pending:
        _close(db, inv, "cancelled")


def _live_until(db: Session, inv: DirectInvitation) -> datetime | None:
    """Validade do convite: a sala ainda aguarda e não expirou. Se não, marca como cancelado."""
    match = db.get(Match, inv.match_id)
    now = clock.now()
    if (match is None or match.status != "waiting" or match.invite_expires_at is None
            or match.invite_expires_at <= now):
        if inv.status == "pending":
            inv.status, inv.responded_at = "cancelled", now
        return None
    return match.invite_expires_at


def _checked_friend(db: Session, me: User, friendship_id: uuid.UUID) -> User:
    f = _load_for_member(db, me, friendship_id, lock=False)
    if f.status != "accepted":
        raise _friendship_not_found()
    other = _other_user(db, f, me)
    if is_blocked_between(db, me.id, other.id) or not pair_allowed(me, other):
        raise _friendship_not_found()
    return other


def send_invitation(db: Session, me: User, friendship_id: uuid.UUID,
                    game_id: str) -> DirectInvitationOut:
    limiter.hit(f"direct-invite:{me.id}", 10, HOUR)
    require_social_ready(me)
    other = _checked_friend(db, me, friendship_id)
    previous = db.scalars(select(DirectInvitation).where(
        DirectInvitation.sender_id == me.id, DirectInvitation.recipient_id == other.id,
        DirectInvitation.status == "pending")).all()
    alive = [inv for inv in previous if _live_until(db, inv) is not None]
    db.commit()  # persiste os convites vencidos marcados acima
    if alive:
        raise ProblemError(409, "invite_already_pending", "Já existe um convite pendente",
                           "Espere a resposta ou cancele o convite anterior.")
    match_out = online_service.create_invite(db, me, game_id, None)  # sala casual (RF-011)
    inv = DirectInvitation(match_id=match_out.id, sender_id=me.id, recipient_id=other.id,
                           status="pending", created_at=clock.now())
    db.add(inv)
    db.commit()
    return DirectInvitationOut(
        id=inv.id, game_id=game_id, status=inv.status, created_at=inv.created_at,
        expires_at=match_out.invite_expires_at, match_id=match_out.id,
        other=_person(other.profile))


def list_invitations(db: Session, me: User, box: str) -> list[DirectInvitationOut]:
    sent = box == "sent"
    me_col = DirectInvitation.sender_id if sent else DirectInvitation.recipient_id
    other_col = DirectInvitation.recipient_id if sent else DirectInvitation.sender_id
    rows = db.execute(
        select(DirectInvitation, UserProfile, Match.game_id)
        .join(UserProfile, UserProfile.user_id == other_col)
        .join(Match, Match.id == DirectInvitation.match_id)
        .join(User, User.id == other_col)
        .where(me_col == me.id, DirectInvitation.status == "pending", User.status == "active")
        .order_by(DirectInvitation.created_at.desc()).limit(50)).all()
    out: list[DirectInvitationOut] = []
    for inv, profile, game_id in rows:
        expires = _live_until(db, inv)
        if expires is None:
            continue
        out.append(DirectInvitationOut(
            id=inv.id, game_id=game_id, status=inv.status, created_at=inv.created_at,
            expires_at=expires, match_id=inv.match_id if sent else None,
            other=_person(profile)))
    db.commit()  # grava os convites vencidos que foram marcados
    return out


def _pending_invitation(db: Session, me: User, invitation_id: uuid.UUID, *,
                        as_sender: bool) -> DirectInvitation:
    inv = db.scalar(select(DirectInvitation).where(DirectInvitation.id == invitation_id)
                    .with_for_update())
    if inv is None or inv.status != "pending":
        raise _invitation_not_found()
    owner = inv.sender_id if as_sender else inv.recipient_id
    if owner != me.id:
        raise _invitation_not_found()  # alheio e inexistente respondem igual
    return inv


def accept_invitation(db: Session, me: User,
                      invitation_id: uuid.UUID) -> tuple[MatchOut, list[Event]]:
    inv = _pending_invitation(db, me, invitation_id, as_sender=False)
    require_social_ready(me)
    sender = db.get(User, inv.sender_id)
    low, high = _pair(inv.sender_id, me.id)
    friendship = db.scalar(select(Friendship).where(
        Friendship.user_low_id == low, Friendship.user_high_id == high,
        Friendship.status == "accepted"))
    if (sender is None or sender.status != "active" or friendship is None
            or is_blocked_between(db, me.id, sender.id) or not pair_allowed(me, sender)
            or _live_until(db, inv) is None):
        if inv.status == "pending":
            _close(db, inv, "cancelled")
        db.commit()
        raise _invitation_not_found()
    match_id = inv.match_id
    try:
        out, events = online_service.join_direct(db, me, match_id)
    except ProblemError as exc:
        if exc.status == 404:  # a sala sumiu: o convite não vale mais
            db.rollback()
            stale = _pending_invitation(db, me, invitation_id, as_sender=False)
            stale.status, stale.responded_at = "cancelled", clock.now()
            db.commit()
            raise _invitation_not_found() from exc
        raise
    done = db.get(DirectInvitation, invitation_id)
    if done is not None:
        done.status, done.responded_at = "accepted", clock.now()
        db.commit()
    return out, events


def decline_invitation(db: Session, me: User, invitation_id: uuid.UUID) -> None:
    _close(db, _pending_invitation(db, me, invitation_id, as_sender=False), "declined")
    db.commit()


def cancel_invitation(db: Session, me: User, invitation_id: uuid.UUID) -> None:
    _close(db, _pending_invitation(db, me, invitation_id, as_sender=True), "cancelled")
    db.commit()
