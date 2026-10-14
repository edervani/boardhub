"""Tempo de uso por dia, base do limite diário das contas supervisionadas (RF-034)."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailyUsage(Base):
    """Segundos de atividade de um menor em um dia civil de America/Sao_Paulo (DT-021)."""

    __tablename__ = "daily_usage"
    __table_args__ = (CheckConstraint("seconds >= 0", name="seconds"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
