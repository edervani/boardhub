"""Estatísticas do próprio usuário por jogo (RF-021).

A fonte da verdade é `matches`/`match_players`: tudo é recontado a cada consulta (sem agregado
que possa divergir). Partidas locais não entram (o mesmo usuário ocupa os dois assentos);
partidas anuladas ou abortadas não têm resultado e ficam de fora. O rating vem de `ratings`.
"""

from typing import Literal, cast

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.game_engines import elo
from app.models import Match, MatchPlayer, Rating, RatingHistory, User
from app.schemas.ranking import GameStats, ModeStats, RatingInfo, RatingPoint, StatsOut, StreakOut
from app.services import catalog_service
from app.services.rating_service import MIN_GAMES_LISTED

STAT_MODES: tuple[Literal["ai", "online_casual", "online_ranked"], ...] = (
    "ai", "online_casual", "online_ranked")
STREAK_LOOKBACK = 100
HISTORY_POINTS = 30

Outcome = Literal["win", "loss", "draw"]


def _outcome() -> ColumnElement[str]:
    """Resultado do ponto de vista do assento do usuário."""
    mine_won = ((Match.result == "p1_win") & (MatchPlayer.seat == 1)) \
        | ((Match.result == "p2_win") & (MatchPlayer.seat == 2))
    return case((Match.result == "draw", "draw"), (mine_won, "win"), else_="loss")


def _finished_by(user: User) -> list[ColumnElement[bool]]:
    return [MatchPlayer.user_id == user.id, MatchPlayer.is_ai.is_(False),
            Match.status == "finished", Match.result.is_not(None), Match.mode.in_(STAT_MODES)]


def _rate(wins: int, played: int) -> float | None:
    return round(wins / played, 4) if played else None


def _streak(outcomes: list[str]) -> StreakOut:
    """`outcomes` do mais recente para o mais antigo."""
    if not outcomes:
        return StreakOut(kind="none", length=0)
    length = 1
    while length < len(outcomes) and outcomes[length] == outcomes[0]:
        length += 1
    return StreakOut(kind=cast(Outcome, outcomes[0]), length=length)


def _counts(db: Session, user: User, game_ids: list[str]) -> dict[str, dict[str, dict[str, int]]]:
    outcome = _outcome().label("outcome")
    rows = db.execute(
        select(Match.game_id, Match.mode, outcome, func.count().label("n"))
        .select_from(Match).join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(*_finished_by(user), Match.game_id.in_(game_ids))
        .group_by(Match.game_id, Match.mode, outcome)).all()
    out: dict[str, dict[str, dict[str, int]]] = {}
    for game_id, mode, result, n in rows:
        out.setdefault(game_id, {}).setdefault(mode, {})[result] = n
    return out


def _recent_outcomes(db: Session, user: User, game_id: str) -> list[str]:
    rows = db.scalars(
        select(_outcome()).select_from(Match)
        .join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(*_finished_by(user), Match.game_id == game_id)
        .order_by(Match.finished_at.desc(), Match.id.desc()).limit(STREAK_LOOKBACK))
    return [str(r) for r in rows]


def _rating_info(db: Session, user: User, game_id: str) -> RatingInfo:
    row = db.get(Rating, (user.id, game_id))
    rating, played = (row.rating, row.games_played) if row else (elo.INITIAL_RATING, 0)
    history = db.scalars(
        select(RatingHistory).where(RatingHistory.user_id == user.id,
                                    RatingHistory.game_id == game_id)
        .order_by(RatingHistory.created_at.desc(), RatingHistory.id.desc())
        .limit(HISTORY_POINTS)).all()
    profile = user.profile
    listed = (user.status == "active" and profile.is_public and profile.show_in_ranking
              and played >= MIN_GAMES_LISTED)
    return RatingInfo(
        rating=rating, games_played=played, provisional=played < elo.PROVISIONAL_GAMES,
        listed=listed, games_until_listed=max(0, MIN_GAMES_LISTED - played),
        history=[RatingPoint(match_id=h.match_id, created_at=h.created_at, before=h.before,
                             after=h.after, delta=h.after - h.before)
                 for h in reversed(history)])


def my_stats(db: Session, user: User, game_id: str | None) -> StatsOut:
    games = catalog_service.visible_games(db, user.age_band)
    if game_id is not None:
        games = [g for g in games if g.id == game_id]
        if not games:
            raise ProblemError(404, "game_not_found", "Jogo não encontrado")
    counts = _counts(db, user, [g.id for g in games])
    out: list[GameStats] = []
    for game in games:
        by_mode: list[ModeStats] = []
        for mode in STAT_MODES:
            c = counts.get(game.id, {}).get(mode, {})
            wins, losses, draws = c.get("win", 0), c.get("loss", 0), c.get("draw", 0)
            if wins + losses + draws:
                by_mode.append(ModeStats(mode=mode, played=wins + losses + draws, wins=wins,
                                         losses=losses, draws=draws,
                                         win_rate=_rate(wins, wins + losses + draws)))
        wins = sum(m.wins for m in by_mode)
        losses = sum(m.losses for m in by_mode)
        draws = sum(m.draws for m in by_mode)
        played = wins + losses + draws
        out.append(GameStats(
            game_id=game.id, name=game.name, played=played, wins=wins, losses=losses,
            draws=draws, win_rate=_rate(wins, played), by_mode=by_mode,
            streak=_streak(_recent_outcomes(db, user, game.id)),
            rating=_rating_info(db, user, game.id) if game.ranked_enabled else None))
    return StatsOut(games=out)
