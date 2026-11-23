"""Consent checks. Latest consent record per type wins; absence means not granted."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerpilot.models import ConsentRecord

CONSENT_TYPES = {
    "ai_processing": "Process my resume and profile with the configured AI provider",
    "recommendation_tracking": "Record recommendation interactions to evaluate and improve matching",
}
POLICY_VERSION = "2026-11-01"


def has_consent(db: Session, user_id: uuid.UUID, consent_type: str) -> bool:
    record = db.scalar(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user_id, ConsentRecord.consent_type == consent_type)
        .order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc())
        .limit(1)
    )
    return bool(record and record.granted)


def record_consent(
    db: Session, user_id: uuid.UUID, consent_type: str, granted: bool, source: str = "settings"
) -> ConsentRecord:
    if consent_type not in CONSENT_TYPES:
        raise ValueError("unknown consent type")
    rec = ConsentRecord(
        user_id=user_id, consent_type=consent_type, granted=granted, policy_version=POLICY_VERSION, source=source
    )
    db.add(rec)
    return rec


def current_consents(db: Session, user_id: uuid.UUID) -> dict[str, bool]:
    return {ct: has_consent(db, user_id, ct) for ct in CONSENT_TYPES}
