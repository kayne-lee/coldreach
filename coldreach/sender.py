"""Build plain-text messages, send them over SMTP, and keep a log of what went out."""

from __future__ import annotations

import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from . import config
from .drafts import Draft


def build_message(draft: Draft, profile: dict) -> EmailMessage:
    """Plain text only. No HTML, no tracking pixel, no attachment: all three hurt replies."""
    sender = profile["from_email"]
    message = EmailMessage()
    message["From"] = formataddr((profile["signature"].strip().splitlines()[0], sender))
    message["To"] = formataddr((f"{draft.first_name} {draft.last_name}".strip(), draft.to))
    message["Subject"] = draft.subject
    message["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    if draft.in_reply_to:
        message["In-Reply-To"] = draft.in_reply_to
        message["References"] = draft.in_reply_to
    message.set_content(draft.body + "\n")
    return message


class Mailer:
    def __enter__(self) -> "Mailer":
        host = config.env("SMTP_HOST")
        self.smtp = smtplib.SMTP(host, int(config.env("SMTP_PORT", "587")), timeout=30)
        self.smtp.starttls(context=ssl.create_default_context())
        self.smtp.login(config.env("SMTP_USER"), config.env("SMTP_PASSWORD"))
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.smtp.quit()
        except smtplib.SMTPException:
            pass

    def send(self, message: EmailMessage) -> None:
        self.smtp.send_message(message)


def load_log() -> list[dict]:
    return config.read_json(config.SENT_LOG, [])


def already_emailed() -> set[str]:
    return {entry["email"] for entry in load_log()}


def record(draft: Draft, message: EmailMessage | None, kind: str) -> None:
    """message is None when the email was sent by another tool (CSV export)."""
    log = load_log()
    log.append(
        {
            "email": draft.to,
            "first_name": draft.first_name,
            "last_name": draft.last_name,
            "title": draft.title,
            "company": draft.company,
            "track": draft.track,
            "target": draft.target,
            "subject": draft.subject,
            "kind": kind,
            "message_id": message["Message-ID"] if message else None,
            "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "replied": False,
        }
    )
    config.write_json(config.SENT_LOG, log)


def mark_replied(email: str) -> int:
    log = load_log()
    hits = [entry for entry in log if entry["email"] == email.lower()]
    for entry in hits:
        entry["replied"] = True
    config.write_json(config.SENT_LOG, log)
    return len(hits)
