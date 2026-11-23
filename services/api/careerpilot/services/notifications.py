"""In-app notifications with optional email, deduplicated per event and respecting preferences."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerpilot.infra.email import OutgoingEmail, get_email_provider
from careerpilot.models import Notification, NotificationPreference, User

EMAIL_PREF_BY_KIND = {
    "application_status": "email_application_updates",
    "application_submitted": "email_application_updates",
    "resume_processed": "email_processing_updates",
    "new_application": "email_application_updates",
    "company_verification": None,  # always sent (account-relevant)
}


def get_preferences(db: Session, user_id: uuid.UUID) -> NotificationPreference:
    pref = db.scalar(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
    if pref is None:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref)
        db.flush()
    return pref


def notify(
    db: Session,
    user_id: uuid.UUID,
    *,
    kind: str,
    title: str,
    body: str,
    dedupe_key: str,
    link: str | None = None,
    send_email: bool = True,
) -> Notification | None:
    """Create a notification once per dedupe_key. Email is attempted only if preferences allow;
    `email_status` records the real outcome of the provider call."""
    existing = db.scalar(
        select(Notification).where(Notification.user_id == user_id, Notification.dedupe_key == dedupe_key)
    )
    if existing is not None:
        return None
    note = Notification(user_id=user_id, kind=kind, title=title, body=body, link=link, dedupe_key=dedupe_key)
    db.add(note)
    db.flush()

    user = db.get(User, user_id)
    pref_field = EMAIL_PREF_BY_KIND.get(kind)
    allowed = send_email and user is not None and user.email_verified_at is not None
    if allowed and pref_field:
        allowed = bool(getattr(get_preferences(db, user_id), pref_field))
    if allowed and user is not None:
        ok = get_email_provider().send(OutgoingEmail(to=user.email, subject=title, text=f"{body}\n"))
        note.email_status = "sent" if ok else "failed"
    else:
        note.email_status = "skipped"
    return note
