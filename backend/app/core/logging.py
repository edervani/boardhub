"""Logs JSON estruturados e sanitizados (SEC-12, RNF-013, doc 13 §1)."""

import contextvars
import json
import logging
import re
import uuid
from typing import Any

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

SENSITIVE_KEYS = re.compile(r"pass|token|secret|cookie|authorization|csrf|email", re.IGNORECASE)
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9])[A-Za-z0-9.-]*")
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}


def new_request_id() -> str:
    rid = uuid.uuid4().hex
    _request_id.set(rid)
    return rid


def current_request_id() -> str | None:
    return _request_id.get()


def mask_email(text: str) -> str:
    return EMAIL_RE.sub(r"\1***@\2***", text)


def _clean(key: str, value: Any) -> Any:
    if SENSITIVE_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, str):
        return mask_email(value)
    if isinstance(value, dict):
        return {k: _clean(str(k), v) for k, v in value.items()}
    return value


class SanitizingFilter(logging.Filter):
    """Mascara e-mails na mensagem e remove campos extras sensíveis antes de qualquer handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_email(str(record.getMessage()))
        record.args = None
        for key in [k for k in vars(record) if k not in _RESERVED]:
            setattr(record, key, _clean(key, getattr(record, key)))
        record.request_id = current_request_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _RESERVED})
        return json.dumps(payload, ensure_ascii=False, default=str)


_filter = SanitizingFilter()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"boardhub.{name}")
    if _filter not in logger.filters:
        logger.addFilter(_filter)
    return logger


def configure_logging(level: str) -> None:
    root = logging.getLogger("boardhub")
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.setLevel(level)
