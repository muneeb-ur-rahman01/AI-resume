"""Public job search (works without AI), job detail, abuse reports, notifications and privacy."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from careerpilot.api import schemas as s
from careerpilot.api.deps import AuthContext, current_user, get_auth
from careerpilot.api.serializers import job_summary
from careerpilot.db import get_db, utcnow
from careerpilot.errors import NotFound
from careerpilot.models import Job, Notification, Report, User
from careerpilot.security import rate_limit as rl
from careerpilot.services import privacy
from careerpilot.services.audit import audit
from careerpilot.services.consent import current_consents, has_consent, record_consent
from careerpilot.services.jobs import get_public_job, public_jobs_query
from careerpilot.services.notifications import get_preferences

router = APIRouter(tags=["jobs", "notifications", "privacy"])


@router.get("/jobs", response_model=s.Page[s.JobSummaryOut])
def search_jobs(
    q: str | None = Query(default=None, max_length=100),
    employment_type: s.EMPLOYMENT_TYPES | None = None,
    work_arrangement: s.ARRANGEMENTS | None = None,
    country: str | None = Query(default=None, pattern=r"^[A-Za-z]{2}$"),
    skill: str | None = Query(default=None, max_length=120),
    min_salary: int | None = Query(default=None, ge=0),
    sort: Literal["newest", "salary"] = "newest",
    page: int = Query(1, ge=1, le=500),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> s.Page[s.JobSummaryOut]:
    stmt = public_jobs_query(
        q=q,
        employment_type=employment_type,
        work_arrangement=work_arrangement,
        country=country,
        skill=skill,
        min_salary=min_salary,
    )
    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(Job.id).subquery())) or 0
    order = Job.salary_max.desc().nulls_last() if sort == "salary" else Job.published_at.desc()
    rows = db.scalars(stmt.order_by(order, Job.id).offset((page - 1) * page_size).limit(page_size)).unique().all()
    return s.Page(items=[job_summary(j) for j in rows], total=total, page=page, page_size=page_size)


@router.get("/jobs/{job_id}", response_model=s.JobOut)
def job_detail(job_id: uuid.UUID, db: Session = Depends(get_db)) -> s.JobOut:
    return s.JobOut.model_validate(get_public_job(db, job_id))


@router.post("/jobs/{job_id}/reports", status_code=201, response_model=s.Message)
def report_job(
    job_id: uuid.UUID, body: s.ReportIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> s.Message:
    rl.get_rate_limiter().hit(rl.SENSITIVE, f"report:{user.id}")
    if db.get(Job, job_id) is None:
        raise NotFound("Job not found.")
    db.add(Report(reporter_id=user.id, target_type="job", target_id=job_id, reason=body.reason, details=body.details))
    audit(db, "report.created", actor_id=user.id, target_type="job", target_id=job_id, metadata={"reason": body.reason})
    db.commit()
    return s.Message(message="Thank you. Our moderators will review this job.")


# -------------------------------------------------------------------------------------- notifications
@router.get("/notifications", response_model=s.Page[s.NotificationOut])
def list_notifications(
    unread_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> s.Page[s.NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return s.Page(
        items=[s.NotificationOut.model_validate(n) for n in rows], total=total, page=page, page_size=page_size
    )


@router.post("/notifications/{notification_id}/read", response_model=s.Message)
def mark_read(
    notification_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> s.Message:
    note = db.get(Notification, notification_id)
    if note is None or note.user_id != user.id:
        raise NotFound("Notification not found.")
    note.read_at = note.read_at or utcnow()
    db.commit()
    return s.Message(message="ok")


@router.post("/notifications/read-all", response_model=s.Message)
def mark_all_read(user: User = Depends(current_user), db: Session = Depends(get_db)) -> s.Message:
    for note in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))):
        note.read_at = utcnow()
    db.commit()
    return s.Message(message="ok")


@router.get("/notifications/preferences", response_model=s.NotificationPrefsIO)
def get_notification_prefs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> s.NotificationPrefsIO:
    pref = get_preferences(db, user.id)
    db.commit()
    return s.NotificationPrefsIO.model_validate(pref)


@router.put("/notifications/preferences", response_model=s.NotificationPrefsIO)
def set_notification_prefs(
    body: s.NotificationPrefsIO, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> s.NotificationPrefsIO:
    pref = get_preferences(db, user.id)
    for k, v in body.model_dump().items():
        setattr(pref, k, v)
    db.commit()
    return s.NotificationPrefsIO.model_validate(pref)


# --------------------------------------------------------------------------------------------- privacy
@router.get("/privacy/consents", response_model=s.ConsentsIO)
def get_consents(user: User = Depends(current_user), db: Session = Depends(get_db)) -> s.ConsentsIO:
    return s.ConsentsIO(**current_consents(db, user.id))


@router.put("/privacy/consents", response_model=s.ConsentsIO)
def set_consents(body: s.ConsentsIO, user: User = Depends(current_user), db: Session = Depends(get_db)) -> s.ConsentsIO:
    for consent_type, granted in body.model_dump().items():
        if has_consent(db, user.id, consent_type) != granted:
            record_consent(db, user.id, consent_type, granted)
            audit(
                db,
                "privacy.consent_changed",
                actor_id=user.id,
                target_type="user",
                target_id=user.id,
                metadata={"consent_type": consent_type, "granted": granted},
            )
    db.commit()
    return s.ConsentsIO(**current_consents(db, user.id))


@router.get("/privacy/export")
def export_data(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    rl.get_rate_limiter().hit(rl.SENSITIVE, f"export:{user.id}")
    return privacy.export_user_data(db, user)


@router.post("/privacy/delete-account", response_model=s.Message)
def delete_account(
    body: s.PasswordConfirmIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> s.Message:
    req = privacy.delete_account(db, ctx.user, body.password)
    return s.Message(message=f"Your account was deleted (request {req.id}, status {req.status}).")
