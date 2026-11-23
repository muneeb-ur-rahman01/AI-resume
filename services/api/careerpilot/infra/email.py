"""EmailProvider interface with console (development) and SMTP implementations.

`send()` returns True only when the provider accepted the message. Acceptance by an SMTP relay is not
proof of delivery to the recipient's inbox, and the code never claims otherwise.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from careerpilot.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str


class EmailProvider(Protocol):
    name: str

    def send(self, message: OutgoingEmail) -> bool: ...


class ConsoleEmailProvider:
    """DEVELOPMENT ONLY. Prints emails to the log and keeps them in memory (used by tests)."""

    name = "console"

    def __init__(self) -> None:
        self.outbox: list[OutgoingEmail] = []

    def send(self, message: OutgoingEmail) -> bool:
        self.outbox.append(message)
        # Body is logged in development so that verification links can be followed locally.
        logger.info("dev_email_sink", extra={"subject": message.subject, "dev_email_body": message.text})
        return True


class SmtpEmailProvider:
    name = "smtp"

    def send(self, message: OutgoingEmail) -> bool:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = s.email_from
        msg["To"] = message.to
        msg["Subject"] = message.subject
        msg.set_content(message.text)
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
                if s.smtp_starttls:
                    smtp.starttls()
                if s.smtp_username and s.smtp_password:
                    smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
                smtp.send_message(msg)
            return True
        except (smtplib.SMTPException, OSError):
            logger.warning("email_send_failed", extra={"subject": message.subject})
            return False


_provider: EmailProvider | None = None


def get_email_provider() -> EmailProvider:
    global _provider
    if _provider is None:
        _provider = SmtpEmailProvider() if get_settings().email_provider == "smtp" else ConsoleEmailProvider()
    return _provider


def set_email_provider(provider: EmailProvider | None) -> None:
    global _provider
    _provider = provider
