"""Contratos de autenticação e conta (doc 06 §2)."""

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AgeBand = Literal["under_12", "12_15", "16_17", "18_plus"]
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")
DISPLAY_NAME_RE = re.compile(r"^[\w-]{3,24}$")


def _email(v: str) -> str:
    v = v.strip()
    if len(v) > 254 or not EMAIL_RE.fullmatch(v):
        raise ValueError("e-mail inválido")
    return v


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=512)


class RegisterIn(Strict):
    email: str
    password: str = Field(max_length=128)
    display_name: str
    age_band: AgeBand
    accept_terms_version: str = Field(max_length=32)
    guardian_email: str | None = None

    _check_email = field_validator("email")(_email)

    @field_validator("guardian_email")
    @classmethod
    def _guardian(cls, v: str | None) -> str | None:
        return _email(v) if v else None

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not DISPLAY_NAME_RE.fullmatch(v.strip()):
            raise ValueError("use de 3 a 24 letras, números, _ ou -")
        return v


class TokenIn(Strict):
    token: str = Field(min_length=10, max_length=100)


class LoginIn(Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class ForgotIn(Strict):
    email: str = Field(max_length=254)


class ResetIn(Strict):
    token: str = Field(min_length=10, max_length=100)
    new_password: str = Field(max_length=128)


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    email_verified: bool
    age_band: AgeBand
    role: str
    supervised: bool


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    user_agent_summary: str | None
    current: bool
