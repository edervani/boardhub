"""Envio de e-mails transacionais (RF-002, RF-005, RF-034)."""

import json
import os
import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    body: str


class MailError(Exception):
    """Falha de entrega; o chamador decide como responder."""


class Mailer(Protocol):
    def send(self, mail: Mail) -> None: ...


class SmtpMailer:
    def send(self, mail: Mail) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.mail_from, mail.to, mail.subject
        msg.set_content(mail.body)
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
                if s.smtp_user:
                    smtp.starttls()
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            log.warning("falha ao enviar e-mail", extra={"error_type": type(exc).__name__})
            raise MailError from exc


class FileMailer:
    """Grava cada mensagem como uma linha JSON em MAIL_FILE_PATH (só testes locais, DT-022).

    Substitui o Mailpit no modo nativo do Windows: o arquivo traz o link de verificação, por isso
    a configuração só o aceita em development/test. O log registra apenas que houve gravação.
    """

    def send(self, mail: Mail) -> None:
        path = Path(get_settings().mail_file_path)
        record = {"ts": datetime.now(UTC).isoformat(), "to": mail.to,
                  "subject": mail.subject, "body": mail.body}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8", newline="\n") as out:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            log.warning("falha ao gravar e-mail de teste", extra={"error_type": type(exc).__name__})
            raise MailError from exc
        log.info("e-mail de teste gravado em arquivo")


def get_mailer() -> Mailer:
    if get_settings().mail_backend == "file":
        return FileMailer()
    return SmtpMailer()
