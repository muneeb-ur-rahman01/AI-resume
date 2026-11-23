"""Data export and account deletion."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerpilot.db import utcnow
from careerpilot.infra.storage import get_storage
from careerpilot.models import (
    Application,
    ConsentRecord,
    CoverLetterDraft,
    DataDeletionRequest,
    Document,
    Notification,
    Resume,
    User,
)
from careerpilot.services.audit import audit
from careerpilot.services.auth import reauthenticate


def export_user_data(db: Session, user: User) -> dict[str, Any]:
    from careerpilot.models import CandidateProfile
    from careerpilot.services.profiles import candidate_facts, get_profile

    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    data: dict[str, Any] = {
        "exported_at": utcnow().isoformat(),
        "account": {
            "email": user.email,
            "full_name": user.full_name,
            "roles": sorted(user.role_names),
            "created_at": user.created_at.isoformat(),
            "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
        },
    }
    if profile is not None:
        p = get_profile(db, user.id)
        data["profile"] = candidate_facts(p, user)
        prefs = p.preferences
        data["preferences"] = (
            {
                "desired_titles": prefs.desired_titles,
                "employment_types": prefs.employment_types,
                "work_arrangements": prefs.work_arrangements,
                "preferred_locations": prefs.preferred_locations,
                "willing_to_relocate": prefs.willing_to_relocate,
                "min_salary": prefs.min_salary,
                "salary_currency": prefs.salary_currency,
            }
            if prefs
            else None
        )
    data["resumes"] = [
        {
            "id": str(r.id),
            "label": r.label,
            "status": r.status.value,
            "uploaded_at": r.created_at.isoformat(),
            "extracted_text": r.extracted_text,
            "extraction": r.extraction,
        }
        for r in db.scalars(select(Resume).where(Resume.owner_id == user.id))
    ]
    data["applications"] = [
        {
            "id": str(a.id),
            "job_id": str(a.job_id),
            "status": a.status.value,
            "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
            "documents": [{"kind": d.kind, "content": d.content} for d in a.documents],
            "history": [{"to": h.to_status, "at": h.created_at.isoformat()} for h in a.history],
        }
        for a in db.scalars(select(Application).where(Application.candidate_user_id == user.id))
    ]
    data["cover_letter_drafts"] = [
        {"job_id": str(d.job_id), "version": d.version_number, "content": d.content}
        for d in db.scalars(select(CoverLetterDraft).where(CoverLetterDraft.owner_id == user.id))
    ]
    data["consents"] = [
        {
            "type": c.consent_type,
            "granted": c.granted,
            "policy_version": c.policy_version,
            "at": c.created_at.isoformat(),
        }
        for c in db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user.id))
    ]
    data["notifications"] = [
        {"title": n.title, "body": n.body, "at": n.created_at.isoformat()}
        for n in db.scalars(select(Notification).where(Notification.user_id == user.id))
    ]
    audit(db, "privacy.export", actor_id=user.id, target_type="user", target_id=user.id)
    db.commit()
    return data


def delete_account(db: Session, user: User, password: str) -> DataDeletionRequest:
    """Permanently delete the account and personal data. Stored files are removed from object storage;
    database rows cascade from the user. Audit events keep only the opaque user id."""
    reauthenticate(db, user, password)
    request = DataDeletionRequest(user_id=user.id, status="processing")
    db.add(request)
    db.commit()

    keys = list(db.scalars(select(Document.storage_key).where(Document.owner_id == user.id)))
    storage = get_storage()
    failed = 0
    for key in keys:
        try:
            storage.delete(key)
        except Exception:
            failed += 1
    user_id = user.id
    applications = len(list(db.scalars(select(Application.id).where(Application.candidate_user_id == user_id))))
    db.delete(user)
    audit(
        db,
        "privacy.account_deleted",
        actor_id=user_id,
        target_type="user",
        target_id=user_id,
        metadata={"files_deleted": len(keys) - failed, "file_delete_failures": failed},
    )
    request.status = "completed" if failed == 0 else "failed"
    request.completed_at = utcnow()
    request.summary = {"files": len(keys), "file_delete_failures": failed, "applications": applications}
    db.commit()
    return request
