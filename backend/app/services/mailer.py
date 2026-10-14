"""Envio de e-mails transacionais (RF-002, RF-005, RF-034)."""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
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


def get_mailer() -> Mailer:
    return SmtpMailer()
