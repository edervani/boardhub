"""Rating Elo por jogo: liquidação ao fim da partida e ranking público (RF-019).

O servidor é a autoridade: o rating só muda aqui, dentro da transação que encerra a partida
ranqueada (quem chama mantém a linha da partida bloqueada e faz o `commit`). A liquidação é
idempotente: `match_players.rating_after` marca "já liquidado" e `rating_history` tem UNIQUE
(usuário, partida). Partidas contra a IA, locais, casuais e anuladas nunca chegam aqui.
"""

import base64
import binascii
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import ProblemError
from app.core.ratelimit import limiter
from app.game_engines import elo
from app.models import Match, MatchPlayer, Rating, RatingHistory, User, UserProfile
from app.schemas.ranking import LeaderboardEntry, LeaderboardPage
from app.services import catalog_service

RANKED_MODE = "online_ranked"
# RF-019: o ranking público só lista quem tem ao menos 10 partidas ranqueadas.
MIN_GAMES_LISTED = 10
MAX_PAGE = 100
MAX_CURSOR = 10_000_000
SCORE_BY_RESULT = {"p1_win": (elo.WIN, elo.LOSS), "p2_win": (elo.LOSS, elo.WIN),
                   "draw": (elo.DRAW, elo.DRAW)}


@dataclass(frozen=True)
class RatingChange:
    seat: int
    before: int
    after: int


def changes_from_players(players: list[MatchPlayer]) -> list[RatingChange]:
    """Variações já gravadas nas linhas dos jogadores (vazio se a partida não foi liquidada)."""
    return [RatingChange(p.seat, p.rating_before, p.rating_after)
            for p in sorted(players, key=lambda p: p.seat)
            if p.rating_before is not None and p.rating_after is not None]


def _lock_ratings(db: Session, game_id: str, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, Rating]:
    """Cria as linhas que faltam e bloqueia as dos dois jogadores em ordem determinística."""
    now = clock.now()
    for uid in sorted(user_ids):
        db.execute(pg_insert(Rating).values(
            user_id=uid, game_id=game_id, rating=elo.INITIAL_RATING, games_played=0,
            updated_at=now).on_conflict_do_nothing())
    rows = db.scalars(
        select(Rating).where(Rating.game_id == game_id, Rating.user_id.in_(user_ids))
        .order_by(Rating.user_id).with_for_update()
        .execution_options(populate_existing=True)).all()
    return {r.user_id: r for r in rows}


def settle(db: Session, match: Match, players: list[MatchPlayer]) -> list[RatingChange]:
    """Atualiza os ratings de uma partida ranqueada encerrada. Seguro para chamar de novo.

    Devolve as variações (vazio quando a partida não conta: outro modo, anulada, sem resultado
    ou com conta removida).
    """
    result = match.result
    if match.mode != RANKED_MODE or match.status != "finished" or result not in SCORE_BY_RESULT:
        return []
    assert result is not None
    humans = [p for p in players if p.user_id is not None and not p.is_ai]
    if len(humans) != 2 or humans[0].user_id == humans[1].user_id:
        return []
    done = changes_from_players(humans)
    if done:  # idempotência: já liquidada
        return done
    by_seat = {p.seat: p for p in humans}
    first, second = by_seat[1], by_seat[2]
    assert first.user_id is not None and second.user_id is not None
    ratings = _lock_ratings(db, match.game_id, [first.user_id, second.user_id])
    r1, r2 = ratings[first.user_id], ratings[second.user_id]
    score1, score2 = SCORE_BY_RESULT[result]
    after1 = elo.new_rating(r1.rating, r2.rating, score1, r1.games_played)
    after2 = elo.new_rating(r2.rating, r1.rating, score2, r2.games_played)
    now = clock.now()
    for player, row, after in ((first, r1, after1), (second, r2, after2)):
        assert player.user_id is not None
        player.rating_before, player.rating_after = row.rating, after
        db.add(RatingHistory(user_id=player.user_id, game_id=match.game_id, match_id=match.id,
                             before=row.rating, after=after, created_at=now))
        row.rating = after
        row.games_played += 1
        row.updated_at = now
    db.flush()
    return changes_from_players(humans)


# ---------- ranking público ----------

def _decode_cursor(cursor: str) -> int:
    try:
        pos = int(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ProblemError(422, "invalid_cursor", "Cursor inválido") from exc
    if not 0 <= pos <= MAX_CURSOR:
        raise ProblemError(422, "invalid_cursor", "Cursor inválido")
    return pos


def _encode_cursor(pos: int) -> str:
    return base64.urlsafe_b64encode(str(pos).encode()).decode().rstrip("=")


def leaderboard(db: Session, age_band: str | None, game_id: str, cursor: str | None,
                limit: int, ip: str) -> LeaderboardPage:
    """Ranking de um jogo. Só entram perfis públicos, ativos, que escolheram aparecer e têm
    partidas suficientes; a resposta traz apenas apelido público e avatar (sem IDs)."""
    limiter.hit(f"ranking:{ip}", 120, 60)
    limit = max(1, min(limit, MAX_PAGE))
    game = next((g for g in catalog_service.visible_games(db, age_band) if g.id == game_id), None)
    if game is None or not game.ranked_enabled:
        raise ProblemError(404, "game_not_found", "Ranking não encontrado")
    name = func.lower(UserProfile.display_name)
    eligible = (
        select(
            Rating.rating, Rating.games_played, UserProfile.display_name, UserProfile.avatar_key,
            func.row_number().over(order_by=(Rating.rating.desc(), name.asc())).label("pos"))
        .join(UserProfile, UserProfile.user_id == Rating.user_id)
        .join(User, User.id == Rating.user_id)
        .where(Rating.game_id == game_id, Rating.games_played >= MIN_GAMES_LISTED,
               UserProfile.is_public.is_(True), UserProfile.show_in_ranking.is_(True),
               User.status == "active")
        .subquery())
    stmt = select(eligible).order_by(eligible.c.pos).limit(limit + 1)
    if cursor:
        stmt = stmt.where(eligible.c.pos > _decode_cursor(cursor))
    rows = db.execute(stmt).all()
    page, more = rows[:limit], len(rows) > limit
    items = [LeaderboardEntry(rank=r.pos, display_name=r.display_name, avatar_key=r.avatar_key,
                              rating=r.rating, games_played=r.games_played) for r in page]
    return LeaderboardPage(game_id=game_id, min_games=MIN_GAMES_LISTED, items=items,
                           next_cursor=_encode_cursor(page[-1].pos) if more else None)
