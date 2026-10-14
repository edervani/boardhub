"""Relógio injetável: os testes substituem `now` para simular expirações."""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
