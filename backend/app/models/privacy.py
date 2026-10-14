"""Exportação de dados pessoais (RF-029, doc 05 §2 `data_export_requests`)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, new_id

EXPORT_STATUSES = ("ready",)


class DataExportRequest(CreatedAt, Base):
    """Pedido de exportação. O arquivo JSON fica em `payload` até `expires_at` (DT-019)."""

    __tablename__ = "data_export_requests"
    __table_args__ = (
        CheckConstraint("status IN ('ready')", name="status"),
        Index("ix_data_export_requests_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    # Titular dos dados; a exportação some junto com a conta.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Quem pediu (o próprio titular ou o responsável vinculado); só ele baixa o arquivo.
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(8), default="ready")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
