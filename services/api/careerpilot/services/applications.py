"""Candidate-approved application submission, status state machines and employer review."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from careerpilot.db import utcnow
from careerpilot.errors import AppError, Conflict, NotFound, ValidationFailed
from careerpilot.models import (
    Application,
    ApplicationDocument,
    ApplicationStatus,
    ApplicationStatusHistory,
    CompanyMember,
    CoverLetterDraft,
    IdempotencyKey,
    Interview,
    Job,
    ProcessingStatus,
    Resume,
    User,
)
from careerpilot.services.audit import audit
from careerpilot.services.companies import require_member
from careerpilot.services.generation import find_unsupported_claims, job_context
from careerpilot.services.jobs import get_public_job
from careerpilot.services.matching import explain_job, record_event
from careerpilot.services.notifications import notify
from careerpilot.services.profiles import candidate_facts, get_profile

S = ApplicationStatus
EMPLOYER_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    S.submitted: {S.shortlisted, S.interview, S.rejected},
    S.shortlisted: {S.interview, S.offer, S.rejected},
    S.interview: {S.offer, S.rejected},
    S.offer: {S.hired, S.rejected},
}
CANDIDATE_WITHDRAWABLE = {S.submitted, S.shortlisted, S.interview, S.offer}
STATUS_LABELS = {
    S.submitted: "Submitted",
    S.shortlisted: "Shortlisted",
    S.interview: "Interview",
    S.offer: "Offer",
    S.rejected: "Not selected",
    S.withdrawn: "Withdrawn",
    S.hired: "Hired",
}


class ExternalApplication(AppError):
    status_code = 409
    code = "external_application_required"


def preview(db: Session, user: User, job_id: uuid.UUID) -> dict[str, Any]:
    job = get_public_job(db, job_id)
    profile = get_profile(db, user.id)
    resumes = list(
        db.scalars(
            select(Resume)
            .where(Resume.owner_id == user.id, Resume.status == ProcessingStatus.completed)
            .order_by(Resume.is_primary.desc(), Resume.created_at.desc())
        )
    )
    draft = db.scalar(
        select(CoverLetterDraft)
        .where(CoverLetterDraft.owner_id == user.id, CoverLetterDraft.job_id == job.id)
        .order_by(CoverLetterDraft.version_number.desc())
        .limit(1)
    )
    existing = db.scalar(
        select(Application).where(Application.candidate_user_id == user.id, Application.job_id == job.id)
    )
    match = explain_job(db, user, job)
    return {
        "job": job,
        "facts": candidate_facts(profile, user),
        "resumes": resumes,
        "cover_letter_draft": draft,
        "match": match,
        "already_applied": existing is not None,
        "external_apply_url": job.external_apply_url,
    }


def _request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def submit(
    db: Session,
    user: User,
    *,
    job_id: uuid.UUID,
    resume_id: uuid.UUID | None,
    cover_letter: str | None,
    cover_letter_draft_id: uuid.UUID | None,
    confirmed: bool,
    idempotency_key: str,
) -> tuple[Application, bool]:
    """Returns (application, created). Re-sending the same request with the same Idempotency-Key returns
    the original application instead of creating a duplicate."""
    if not confirmed:
        raise ValidationFailed(
            "You must review and confirm the application before it is submitted.", code="confirmation_required"
        )
    if not (8 <= len(idempotency_key) <= 100):
        raise ValidationFailed("A valid Idempotency-Key header is required.", code="idempotency_key_required")
    payload = {
        "job_id": str(job_id),
        "resume_id": str(resume_id),
        "cover_letter": cover_letter,
        "draft": str(cover_letter_draft_id),
    }
    req_hash = _request_hash(payload)
    prior = db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user.id,
            IdempotencyKey.scope == "application_submit",
            IdempotencyKey.key == idempotency_key,
        )
    )
    if prior is not None:
        if prior.request_hash != req_hash:
            raise Conflict(
                "This Idempotency-Key was already used for a different request.", code="idempotency_key_reused"
            )
        app = db.get(Application, prior.resource_id) if prior.resource_id else None
        if app is not None:
            return app, False

    job = get_public_job(db, job_id)
    if job.external_apply_url:
        raise ExternalApplication(
            "This employer accepts applications on their own site.",
            details={"external_apply_url": job.external_apply_url},
        )
    if db.scalar(select(Application.id).where(Application.candidate_user_id == user.id, Application.job_id == job.id)):
        raise Conflict("You have already applied to this job.", code="duplicate_application")
    resume = None
    if resume_id is not None:
        resume = db.get(Resume, resume_id)
        if resume is None or resume.owner_id != user.id:
            raise NotFound("Resume not found.")
        if resume.status != ProcessingStatus.completed:
            raise ValidationFailed("The selected resume is still processing.", code="resume_not_ready")

    letter_text = cover_letter
    generated_by = None
    if cover_letter_draft_id is not None:
        draft = db.get(CoverLetterDraft, cover_letter_draft_id)
        if draft is None or draft.owner_id != user.id or draft.job_id != job.id:
            raise NotFound("Cover letter draft not found.")
        letter_text = letter_text or draft.content
        generated_by = draft.generated_by
    if letter_text is not None and not (50 <= len(letter_text.strip()) <= 6000):
        raise ValidationFailed("Cover letters must be between 50 and 6000 characters.")

    profile = get_profile(db, user.id)
    facts = candidate_facts(profile, user)
    match = explain_job(db, user, job)
    now = utcnow()
    app = Application(
        candidate_user_id=user.id,
        job_id=job.id,
        company_id=job.company_id,
        resume_id=resume.id if resume else None,
        status=S.submitted,
        submitted_at=now,
        candidate_approved_at=now,
        candidate_snapshot=json.loads(json.dumps(facts, default=str)),
        relevance_snapshot={"score": match.score, "eligibility": match.eligibility, "explanation": match.explanation},
    )
    app.history.append(
        ApplicationStatusHistory(
            from_status=None,
            to_status=S.submitted.value,
            actor_user_id=user.id,
            actor_type="candidate",
            note="Candidate reviewed and approved the application.",
        )
    )
    if letter_text:
        app.documents.append(
            ApplicationDocument(
                kind="cover_letter",
                content=letter_text.strip(),
                generated_by=generated_by,
                unsupported_claims=find_unsupported_claims(letter_text, facts, job_context(job), db),
            )
        )
    db.add(app)
    try:
        db.flush()
        db.add(
            IdempotencyKey(
                user_id=user.id,
                scope="application_submit",
                key=idempotency_key,
                request_hash=req_hash,
                resource_id=app.id,
            )
        )
        db.flush()
    except IntegrityError as exc:
        db.rollback()  # concurrent duplicate (same job or same key)
        raise Conflict("You have already applied to this job.", code="duplicate_application") from exc
    audit(
        db,
        "application.submitted",
        actor_id=user.id,
        target_type="application",
        target_id=app.id,
        metadata={"job_id": str(job.id)},
    )
    notify(
        db,
        user.id,
        kind="application_submitted",
        title=f"Application submitted: {job.title}",
        body=f"Your application to {job.company.name} was submitted on CareerPilot. The employer can now "
        "review it. You will be notified when they update its status.",
        dedupe_key=f"app_submitted:{app.id}",
        link=f"/candidate/applications/{app.id}",
    )
    member_ids = db.scalars(select(CompanyMember.user_id).where(CompanyMember.company_id == job.company_id)).all()
    for mid in member_ids:
        notify(
            db,
            mid,
            kind="new_application",
            title=f"New application for {job.title}",
            body="A candidate applied to your job.",
            dedupe_key=f"new_app:{app.id}",
            link=f"/employer/applications/{app.id}",
        )
    db.commit()
    record_event(db, user, job.id, "apply")
    return app, True


def get_candidate_application(db: Session, user: User, app_id: uuid.UUID) -> Application:
    app = db.get(Application, app_id)
    if app is None or app.candidate_user_id != user.id:
        raise NotFound("Application not found.")
    return app


def withdraw(db: Session, user: User, app_id: uuid.UUID) -> Application:
    app = get_candidate_application(db, user, app_id)
    if app.status not in CANDIDATE_WITHDRAWABLE:
        raise Conflict(f"An application that is {app.status.value} cannot be withdrawn.", code="invalid_transition")
    _change(db, app, S.withdrawn, user, "candidate", None)
    db.commit()
    return app


def _change(
    db: Session, app: Application, to: ApplicationStatus, actor: User, actor_type: str, note: str | None
) -> None:
    previous = app.status
    app.status = to
    app.history.append(
        ApplicationStatusHistory(
            from_status=previous.value, to_status=to.value, actor_user_id=actor.id, actor_type=actor_type, note=note
        )
    )
    audit(
        db,
        "application.status_changed",
        actor_id=actor.id,
        target_type="application",
        target_id=app.id,
        metadata={"from": previous.value, "to": to.value, "actor_type": actor_type},
    )


def get_employer_application(
    db: Session, user: User, app_id: uuid.UUID, *, write: bool = False, mark_viewed: bool = False
) -> Application:
    app = db.get(Application, app_id)
    if app is None:
        raise NotFound("Application not found.")
    require_member(db, user, app.company_id, write=write)  # 404 for other companies
    if mark_viewed and app.first_viewed_at is None:
        app.first_viewed_at = utcnow()
        audit(db, "application.viewed", actor_id=user.id, target_type="application", target_id=app.id)
        db.commit()
    return app


def employer_update_status(
    db: Session, user: User, app_id: uuid.UUID, to: ApplicationStatus, note: str | None
) -> Application:
    app = get_employer_application(db, user, app_id, write=True)
    if to not in EMPLOYER_TRANSITIONS.get(app.status, set()):
        raise Conflict(
            f"Cannot change an application from {app.status.value} to {to.value}.", code="invalid_transition"
        )
    _change(db, app, to, user, "employer", note)
    job = db.get(Job, app.job_id)
    assert job is not None
    notify(
        db,
        app.candidate_user_id,
        kind="application_status",
        title=f"Application update: {job.title}",
        body=f"{job.company.name} updated your application status to: {STATUS_LABELS.get(to, to.value)}.",
        dedupe_key=f"app_status:{app.id}:{to.value}",
        link=f"/candidate/applications/{app.id}",
    )
    db.commit()
    if to in (S.interview, S.offer, S.hired):
        candidate = db.get(User, app.candidate_user_id)
        if candidate is not None:
            record_event(
                db, candidate, app.job_id, {"interview": "interview", "offer": "offer", "hired": "hire"}[to.value]
            )
    return app


def schedule_interview(
    db: Session,
    user: User,
    app_id: uuid.UUID,
    *,
    starts_at: datetime,
    duration_minutes: int,
    location_or_link: str | None,
    notes: str | None,
) -> Interview:
    app = get_employer_application(db, user, app_id, write=True)
    if app.status not in (S.submitted, S.shortlisted, S.interview):
        raise Conflict("Interviews can only be scheduled for active applications.", code="invalid_state")
    if starts_at <= utcnow():
        raise ValidationFailed("Interview time must be in the future.")
    interview = Interview(
        application_id=app.id,
        scheduled_by_id=user.id,
        starts_at=starts_at,
        duration_minutes=duration_minutes,
        location_or_link=location_or_link,
        notes=notes,
    )
    db.add(interview)
    if app.status != S.interview:
        _change(db, app, S.interview, user, "employer", "Interview scheduled")
    job = db.get(Job, app.job_id)
    assert job is not None
    notify(
        db,
        app.candidate_user_id,
        kind="application_status",
        title=f"Interview scheduled: {job.title}",
        body=f"{job.company.name} scheduled an interview for {starts_at.isoformat()} ({duration_minutes} minutes).",
        dedupe_key=f"interview:{interview.id}",
        link=f"/candidate/applications/{app.id}",
    )
    db.commit()
    return interview
