"""Contratos dos direitos do titular (doc 06 §2, RF-029/RF-030)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.auth import Strict


class DeleteAccountIn(Strict):
    # Senha de quem confirma (a própria conta ou, no fluxo do responsável, a do responsável).
    password: str = Field(min_length=1, max_length=128)


class DeletionOut(BaseModel):
    scheduled_for: datetime


class ExportOut(BaseModel):
    id: uuid.UUID
    status: str
    created_at: datetime
    expires_at: datetime
