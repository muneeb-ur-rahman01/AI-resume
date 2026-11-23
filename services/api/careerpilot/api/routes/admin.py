"""Administrator endpoints. Every mutating action is audited. Admin accounts are created only via the CLI."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from careerpilot.ai.skills import invalidate_normalizer_cache, slugify
from careerpilot.api import schemas as s
from careerpilot.api.deps import admin_user
from careerpilot.db import get_db, utcnow
from careerpilot.errors import Conflict, NotFound, ValidationFailed
from careerpilot.infra.tasks import enqueue
from careerpilot.models import (
    AIUsageRecord,
    AuditEvent,
    BackgroundTask,
    Company,
    CompanyVerificationRecord,
    Job,
    JobStatus,
    ModerationAction,
    Report,
    Role,
    SkillTaxonomy,
    User,
    UserStatus,
    VerificationStatus,
)
from careerpilot.services import companies as company_service
from careerpilot.services.audit import audit
from careerpilot.services.auth import revoke_all_sessions

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/companies", response_model=list[dict])
def companies(
    status: str | None = Query(default="pending", max_length=20),
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Company).order_by(Company.created_at.desc()).limit(200)
    if status:
        stmt = stmt.where(Company.verification_status == status)
    out = []
    for c in db.scalars(stmt):
        latest = db.scalar(
            select(CompanyVerificationRecord)
            .where(CompanyVerificationRecord.company_id == c.id)
            .order_by(CompanyVerificationRecord.created_at.desc())
            .limit(1)
        )
        out.append(
            {
                "company": s.CompanyOut.model_validate(c).model_dump(mode="json"),
                "latest_request": s.VerificationOut.model_validate(latest).model_dump(mode="json") if latest else None,
            }
        )
    return out


@router.post("/companies/{company_id}/verification", response_model=s.CompanyOut)
def decide_company(
    company_id: uuid.UUID, body: s.AdminDecisionIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> s.CompanyOut:
    return s.CompanyOut.model_validate(
        company_service.decide_verification(db, admin, company_id, approve=body.approve, reason=body.reason)
    )


@router.post("/companies/{company_id}/suspend", response_model=s.CompanyOut)
def suspend_company(
    company_id: uuid.UUID, body: s.AdminReasonIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> s.CompanyOut:
    company = db.get(Company, company_id)
    if company is None:
        raise NotFound("Company not found.")
    company.verification_status = VerificationStatus.suspended
    for job in db.scalars(select(Job).where(Job.company_id == company.id, Job.status == JobStatus.published)):
        job.status = JobStatus.paused
    db.add(
        ModerationAction(
            admin_id=admin.id, target_type="company", target_id=company.id, action="suspend", reason=body.reason
        )
    )
    audit(db, "admin.company_suspended", actor_id=admin.id, target_type="company", target_id=company.id)
    db.commit()
    return s.CompanyOut.model_validate(company)


@router.get("/users", response_model=s.Page[s.AdminUserOut])
def users(
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> s.Page[s.AdminUserOut]:
    stmt = select(User)
    if q:
        stmt = stmt.where(
            func.lower(User.email).like(f"%{q.lower()}%") | func.lower(User.full_name).like(f"%{q.lower()}%")
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return s.Page(
        items=[
            s.AdminUserOut(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                roles=sorted(u.role_names),
                status=u.status.value,
                email_verified=u.email_verified_at is not None,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
            )
            for u in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/users/{user_id}/suspend", response_model=s.Message)
def suspend_user(
    user_id: uuid.UUID, body: s.AdminReasonIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> s.Message:
    target = db.get(User, user_id)
    if target is None:
        raise NotFound("User not found.")
    if target.id == admin.id or target.has_role(Role.admin):
        raise Conflict("Administrators cannot be suspended through this endpoint.")
    target.status = UserStatus.suspended
    revoked = revoke_all_sessions(db, target.id)
    db.add(
        ModerationAction(
            admin_id=admin.id, target_type="user", target_id=target.id, action="suspend", reason=body.reason
        )
    )
    audit(
        db,
        "admin.user_suspended",
        actor_id=admin.id,
        target_type="user",
        target_id=target.id,
        metadata={"sessions_revoked": revoked},
    )
    db.commit()
    return s.Message(message="User suspended and signed out.")


@router.post("/users/{user_id}/reinstate", response_model=s.Message)
def reinstate_user(
    user_id: uuid.UUID, body: s.AdminReasonIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> s.Message:
    target = db.get(User, user_id)
    if target is None or target.status != UserStatus.suspended:
        raise NotFound("Suspended user not found.")
    target.status = UserStatus.active
    db.add(
        ModerationAction(
            admin_id=admin.id, target_type="user", target_id=target.id, action="reinstate", reason=body.reason
        )
    )
    audit(db, "admin.user_reinstated", actor_id=admin.id, target_type="user", target_id=target.id)
    db.commit()
    return s.Message(message="User reinstated.")


@router.get("/audit-events", response_model=s.Page[s.AuditOut])
def audit_events(
    action: str | None = Query(default=None, max_length=80),
    actor_user_id: uuid.UUID | None = None,
    target_id: str | None = Query(default=None, max_length=64),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> s.Page[s.AuditOut]:
    stmt = select(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action.like(f"{action}%"))
    if actor_user_id:
        stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
    if target_id:
        stmt = stmt.where(AuditEvent.target_id == target_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return s.Page(items=[s.AuditOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/reports", response_model=list[s.ReportOut])
def reports(
    status: str = Query(default="open", max_length=20), admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> list[s.ReportOut]:
    rows = db.scalars(select(Report).where(Report.status == status).order_by(Report.created_at.desc()).limit(200))
    return [s.ReportOut.model_validate(r) for r in rows]


@router.post("/reports/{report_id}/resolve", response_model=s.ReportOut)
def resolve_report(
    report_id: uuid.UUID, body: s.ResolveReportIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> s.ReportOut:
    report = db.get(Report, report_id)
    if report is None or report.status != "open":
        raise NotFound("Open report not found.")
    if body.action in ("pause_job", "close_job"):
        if report.target_type != "job":
            raise ValidationFailed("This action applies to job reports only.")
        job = db.get(Job, report.target_id)
        if job is None:
            raise NotFound("Job not found.")
        if job.status in (JobStatus.published, JobStatus.paused, JobStatus.pending_review):
            job.status = JobStatus.paused if body.action == "pause_job" else JobStatus.closed
            if job.status == JobStatus.closed:
                job.closed_at = utcnow()
    report.status = "dismissed" if body.action == "dismiss" else "actioned"
    db.add(
        ModerationAction(
            admin_id=admin.id,
            report_id=report.id,
            target_type=report.target_type,
            target_id=report.target_id,
            action=body.action,
            reason=body.reason,
        )
    )
    audit(
        db,
        "admin.report_resolved",
        actor_id=admin.id,
        target_type="report",
        target_id=report.id,
        metadata={"action": body.action},
    )
    db.commit()
    return s.ReportOut.model_validate(report)


@router.get("/tasks", response_model=list[s.TaskOut])
def tasks(
    status: str = Query(default="failed", max_length=20),
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> list[s.TaskOut]:
    rows = db.scalars(
        select(BackgroundTask)
        .where(BackgroundTask.status == status)
        .order_by(BackgroundTask.created_at.desc())
        .limit(200)
    )
    return [s.TaskOut.model_validate(r) for r in rows]


@router.post("/tasks/{task_id}/retry", response_model=s.Message)
def retry_task(task_id: uuid.UUID, admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> s.Message:
    record = db.get(BackgroundTask, task_id)
    if record is None or record.status != "failed":
        raise NotFound("Failed task not found.")
    if record.name != "process_resume" or not record.entity_id:
        raise ValidationFailed("This task type cannot be retried from the admin console.")
    audit(db, "admin.task_retried", actor_id=admin.id, target_type="task", target_id=record.id)
    db.commit()
    enqueue("process_resume", entity_type="resume", entity_id=record.entity_id, resume_id=record.entity_id)
    return s.Message(message="Task re-queued.")


@router.get("/metrics")
def metrics(admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict[str, object]:
    since = utcnow() - timedelta(days=7)
    usage = db.execute(
        select(
            AIUsageRecord.operation,
            AIUsageRecord.success,
            func.count(),
            func.sum(AIUsageRecord.estimated_cost_usd),
            func.avg(AIUsageRecord.latency_ms),
        )
        .where(AIUsageRecord.created_at >= since)
        .group_by(AIUsageRecord.operation, AIUsageRecord.success)
    ).all()
    return {
        "window_days": 7,
        "users": db.scalar(select(func.count()).select_from(User)),
        "published_jobs": db.scalar(select(func.count()).select_from(Job).where(Job.status == JobStatus.published)),
        "failed_tasks": db.scalar(
            select(func.count()).select_from(BackgroundTask).where(BackgroundTask.status == "failed")
        ),
        "open_reports": db.scalar(select(func.count()).select_from(Report).where(Report.status == "open")),
        "pending_verifications": db.scalar(
            select(func.count()).select_from(Company).where(Company.verification_status == VerificationStatus.pending)
        ),
        "ai_usage": [
            {
                "operation": r[0],
                "success": r[1],
                "calls": r[2],
                "estimated_cost_usd": round(r[3] or 0, 4),
                "avg_latency_ms": int(r[4] or 0),
            }
            for r in usage
        ],
    }


@router.get("/skills", response_model=list[s.SkillTaxonomyOut])
def list_skills(admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[s.SkillTaxonomyOut]:
    return [
        s.SkillTaxonomyOut.model_validate(x)
        for x in db.scalars(select(SkillTaxonomy).order_by(SkillTaxonomy.category, SkillTaxonomy.canonical_name))
    ]


@router.post("/skills", response_model=s.SkillTaxonomyOut, status_code=201)
def add_skill(
    body: s.SkillTaxonomyIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> s.SkillTaxonomyOut:
    slug = slugify(body.canonical_name)
    if db.scalar(select(SkillTaxonomy).where(SkillTaxonomy.slug == slug)):
        raise Conflict("This skill already exists.")
    skill = SkillTaxonomy(
        canonical_name=body.canonical_name,
        slug=slug,
        category=body.category,
        aliases=[a.strip() for a in body.aliases if a.strip()],
    )
    db.add(skill)
    audit(db, "admin.skill_added", actor_id=admin.id, target_type="skill", target_id=slug)
    db.commit()
    invalidate_normalizer_cache()
    return s.SkillTaxonomyOut.model_validate(skill)
