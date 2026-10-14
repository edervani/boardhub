"""Tempo de uso diário e limite das contas supervisionadas (RF-034, DT-021).

O servidor é a autoridade: o tempo vem do relógio injetável (`clock.now`) e nunca do cliente.
Só contas de menores são medidas (minimização de dados, LGPD art. 6º, III); adultos não
geram registro. O dia civil é o de America/Sao_Paulo, o mesmo do desafio diário (RF-027).
"""

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.models import DailyUsage, User

# Intervalo máximo entre duas atividades para contar como tempo contínuo de jogo.
# Pausas maiores não contam (a pessoa saiu); a primeira atividade de uma sessão vale zero.
IDLE_GAP_SECONDS = 300


@lru_cache
def _zone() -> tzinfo:
    try:
        return ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:  # sem base de fusos no sistema: o Brasil não usa horário de verão
        return timezone(timedelta(hours=-3))


def local_day(now: datetime) -> date:
    return now.astimezone(_zone()).date()


def next_reset(now: datetime) -> datetime:
    """Próxima meia-noite local (quando o tempo de hoje deixa de valer), em UTC."""
    tomorrow = local_day(now) + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=_zone()).astimezone(UTC)


@dataclass(frozen=True)
class UsageToday:
    used_seconds: int
    limit_seconds: int | None
    resets_at: datetime

    @property
    def exhausted(self) -> bool:
        return self.limit_seconds is not None and self.used_seconds >= self.limit_seconds


def touch(db: Session, user: User, now: datetime | None = None) -> None:
    """Registra uma atividade (lance, tentativa da Academy, início de partida).

    Soma ao dia local o intervalo desde a atividade anterior quando ele é de até
    `IDLE_GAP_SECONDS`. A primeira atividade do dia não herda tempo do dia anterior.
    Deve ser chamada dentro da transação da ação; não faz commit.
    """
    if not user.is_minor:
        return
    now = now or clock.now()
    day = local_day(now)
    db.execute(pg_insert(DailyUsage).values(
        user_id=user.id, day=day, seconds=0, last_activity_at=now,
    ).on_conflict_do_nothing(index_elements=["user_id", "day"]))
    row = db.scalar(select(DailyUsage).where(DailyUsage.user_id == user.id, DailyUsage.day == day)
                    .with_for_update().execution_options(populate_existing=True))
    assert row is not None
    gap = (now - row.last_activity_at).total_seconds()
    if 0 < gap <= IDLE_GAP_SECONDS:
        row.seconds += int(gap)
    if now > row.last_activity_at:
        row.last_activity_at = now


def usage_today(db: Session, user: User, now: datetime | None = None) -> UsageToday:
    now = now or clock.now()
    row = db.get(DailyUsage, (user.id, local_day(now)), populate_existing=True)
    limit = user.preferences.daily_minutes_limit
    return UsageToday(used_seconds=row.seconds if row else 0,
                      limit_seconds=limit * 60 if limit is not None else None,
                      resets_at=next_reset(now))


def is_exhausted(db: Session, user: User) -> bool:
    return usage_today(db, user).exhausted


def limit_error(usage: UsageToday, now: datetime) -> ProblemError:
    retry = max(1, math.ceil((usage.resets_at - now).total_seconds()))
    return ProblemError(
        429, "daily_limit_reached", "Limite diário de tempo atingido",
        "Você já usou o tempo de jogo de hoje definido pelo seu responsável. "
        "Volte amanhã, depois da meia-noite (horário de Brasília).",
        {"Retry-After": str(retry)})


def require_within_limit(db: Session, user: User) -> None:
    """Bloqueia a criação de partidas, convites e entradas na fila quando o limite acabou."""
    now = clock.now()
    usage = usage_today(db, user, now)
    if usage.exhausted:
        raise limit_error(usage, now)


def require_within_limit_for_move(db: Session, user: User) -> None:
    """Lance em partida já iniciada: RF-034 deixa terminar; a chave é a pendência P-23."""
    if get_settings().daily_limit_blocks_moves:
        require_within_limit(db, user)
