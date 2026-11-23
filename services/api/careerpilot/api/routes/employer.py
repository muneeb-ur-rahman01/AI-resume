"""Employer endpoints: companies, verification, jobs and applicant management.
All company-scoped data passes through services.companies.require_member (tenant isolation)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from careerpilot.api import schemas as s
from careerpilot.api.deps import employer_user
from careerpilot.api.routes.candidate import file_response
from careerpilot.api.serializers import job_summary
from careerpilot.db import get_db
from careerpilot.errors import NotFound
from careerpilot.models import (
    Application,
    ApplicationStatus,
    CandidateProfile,
    Company,
    CompanyVerificationRecord,
    Interview,
    Job,
    JobStatus,
    Resume,
    User,
)
from careerpilot.security.urls import validate_public_http_url
from careerpilot.services import applications as app_service
from careerpilot.services import companies as company_service
from careerpilot.services import jobs as job_service
from careerpilot.services.audit import audit

router = APIRouter(prefix="/employer", tags=["employer"])


# -------------------------------------------------------------------------------------------- companies
@router.post("/companies", response_model=s.MyCompanyOut, status_code=201)
def create_company(
    body: s.CompanyIn, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> s.MyCompanyOut:
    website = validate_public_http_url(body.website, field="website") if body.website else None
    company = company_service.create_company(
        db,
        user,
        name=body.name,
        website=website,
        email_domain=body.email_domain,
        description=body.description,
        industry=body.industry,
        size_range=body.size_range,
        headquarters=body.headquarters,
    )
    return s.MyCompanyOut(**s.CompanyOut.model_validate(company).model_dump(), my_role="owner")


@router.get("/companies", response_model=list[s.MyCompanyOut])
def my_companies(user: User = Depends(employer_user), db: Session = Depends(get_db)) -> list[s.MyCompanyOut]:
    return [
        s.MyCompanyOut(**s.CompanyOut.model_validate(c).model_dump(), my_role=m.role.value)
        for c, m in company_service.user_companies(db, user.id)
    ]


@router.patch("/companies/{company_id}", response_model=s.CompanyOut)
def update_company(
    company_id: uuid.UUID, body: s.CompanyPatchIn, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> s.CompanyOut:
    company_service.require_member(db, user, company_id, write=True)
    company = db.get(Company, company_id)
    assert company is not None
    data = body.model_dump(exclude_unset=True)
    if data.get("website"):
        data["website"] = validate_public_http_url(data["website"], field="website")
    for k, v in data.items():
        setattr(company, k, v)
    audit(
        db,
        "company.updated",
        actor_id=user.id,
        target_type="company",
        target_id=company.id,
        metadata={"fields": sorted(data)},
    )
    db.commit()
    return s.CompanyOut.model_validate(company)


@router.post("/companies/{company_id}/verification", response_model=s.VerificationOut, status_code=201)
def request_verification(
    company_id: uuid.UUID,
    body: s.VerificationRequestIn,
    user: User = Depends(employer_user),
    db: Session = Depends(get_db),
) -> s.VerificationOut:
    return s.VerificationOut.model_validate(
        company_service.request_verification(db, user, company_id, body.evidence_note)
    )


@router.get("/companies/{company_id}/verification", response_model=list[s.VerificationOut])
def verification_history(
    company_id: uuid.UUID, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> list[s.VerificationOut]:
    company_service.require_member(db, user, company_id)
    rows = db.scalars(
        select(CompanyVerificationRecord)
        .where(CompanyVerificationRecord.company_id == company_id)
        .order_by(CompanyVerificationRecord.created_at.desc())
    ).all()
    return [s.VerificationOut.model_validate(r) for r in rows]


@router.get("/companies/{company_id}/analytics")
def company_analytics(
    company_id: uuid.UUID, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    company_service.require_member(db, user, company_id)
    jobs_by_status = db.execute(
        select(Job.status, func.count()).where(Job.company_id == company_id).group_by(Job.status)
    )
    apps_by_status = db.execute(
        select(Application.status, func.count())
        .where(Application.company_id == company_id)
        .group_by(Application.status)
    )
    return {
        "jobs": {str(getattr(r[0], "value", r[0])): r[1] for r in jobs_by_status},
        "applications": {str(getattr(r[0], "value", r[0])): r[1] for r in apps_by_status},
    }


# ------------------------------------------------------------------------------------------------- jobs
def _job_values(body: s.JobIn) -> dict[str, object]:
    data = body.model_dump(exclude={"expected_version"})
    if data.get("external_apply_url"):
        data["external_apply_url"] = validate_public_http_url(data["external_apply_url"], field="external_apply_url")
    return data


@router.get("/companies/{company_id}/jobs", response_model=list[s.EmployerJobRow])
def company_jobs(
    company_id: uuid.UUID, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> list[s.EmployerJobRow]:
    company_service.require_member(db, user, company_id)
    counts: dict[uuid.UUID, int] = {
        r[0]: r[1]
        for r in db.execute(
            select(Application.job_id, func.count())
            .where(Application.company_id == company_id)
            .group_by(Application.job_id)
        )
    }
    jobs = db.scalars(select(Job).where(Job.company_id == company_id).order_by(Job.created_at.desc())).unique().all()
    return [
        s.EmployerJobRow(**job_summary(j).model_dump(), application_count=counts.get(j.id, 0), created_at=j.created_at)
        for j in jobs
    ]


@router.post("/companies/{company_id}/jobs", response_model=s.JobOut, status_code=201)
def create_job(
    company_id: uuid.UUID, body: s.JobIn, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> s.JobOut:
    return s.JobOut.model_validate(job_service.create_job(db, user, company_id, _job_values(body)))


@router.post("/jobs/parse")
def parse_job(
    body: s.ParseJobIn, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    from careerpilot.security import rate_limit as rl

    rl.get_rate_limiter().hit(rl.AI_GENERATION, str(user.id))
    return job_service.parse_description(db, user, body.text)


@router.get("/jobs/{job_id}", response_model=s.JobOut)
def get_job(job_id: uuid.UUID, user: User = Depends(employer_user), db: Session = Depends(get_db)) -> s.JobOut:
    return s.JobOut.model_validate(job_service.get_company_job(db, user, job_id))


@router.put("/jobs/{job_id}", response_model=s.JobOut)
def update_job(
    job_id: uuid.UUID, body: s.JobPatchIn, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> s.JobOut:
    return s.JobOut.model_validate(job_service.update_job(db, user, job_id, _job_values(body), body.expected_version))


@router.post("/jobs/{job_id}/status", response_model=s.JobOut)
def change_job_status(
    job_id: uuid.UUID, body: s.JobStatusIn, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> s.JobOut:
    return s.JobOut.model_validate(job_service.transition_job(db, user, job_id, JobStatus(body.status)))


# ----------------------------------------------------------------------------------------- applicants
def _row(db: Session, app: Application) -> s.EmployerApplicationRow:
    cand = db.get(User, app.candidate_user_id)
    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == app.candidate_user_id))
    rel = app.relevance_snapshot or {}
    return s.EmployerApplicationRow(
        id=app.id,
        status=app.status.value,
        submitted_at=app.submitted_at,
        first_viewed_at=app.first_viewed_at,
        candidate_name=cand.full_name if cand else "Deleted user",
        candidate_headline=profile.headline if profile else None,
        relevance_score=rel.get("score"),
        eligibility=rel.get("eligibility"),
    )


@router.get("/jobs/{job_id}/applications", response_model=s.Page[s.EmployerApplicationRow])
def job_applications(
    job_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: str | None = Query(default=None, max_length=30),
    user: User = Depends(employer_user),
    db: Session = Depends(get_db),
) -> s.Page[s.EmployerApplicationRow]:
    job = job_service.get_company_job(db, user, job_id)
    stmt = select(Application).where(Application.job_id == job.id, Application.status != ApplicationStatus.withdrawn)
    if status:
        stmt = stmt.where(Application.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Application.submitted_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return s.Page(items=[_row(db, a) for a in rows], total=total, page=page, page_size=page_size)


def _detail(db: Session, app: Application) -> s.EmployerApplicationDetail:
    job = db.get(Job, app.job_id)
    assert job is not None
    interviews = db.scalars(select(Interview).where(Interview.application_id == app.id)).all()
    snapshot = dict(app.candidate_snapshot or {})
    cand = db.get(User, app.candidate_user_id)
    if cand is not None:
        snapshot["email"] = cand.email  # contact detail shared by applying
    return s.EmployerApplicationDetail(
        **_row(db, app).model_dump(),
        job=job_summary(job),
        candidate=snapshot,
        relevance=app.relevance_snapshot,
        documents=[s.ApplicationDocOut.model_validate(d) for d in app.documents],
        history=[s.EmployerHistoryOut.model_validate(h) for h in app.history],
        interviews=[s.InterviewOut.model_validate(i) for i in interviews],
        has_resume=app.resume_id is not None,
        allowed_transitions=sorted(t.value for t in app_service.EMPLOYER_TRANSITIONS.get(app.status, set())),
    )


@router.get("/applications/{app_id}", response_model=s.EmployerApplicationDetail)
def get_application(
    app_id: uuid.UUID, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> s.EmployerApplicationDetail:
    app = app_service.get_employer_application(db, user, app_id, mark_viewed=True)
    return _detail(db, app)


@router.post("/applications/{app_id}/status", response_model=s.EmployerApplicationDetail)
def update_application_status(
    app_id: uuid.UUID, body: s.ApplicationStatusIn, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> s.EmployerApplicationDetail:
    app = app_service.employer_update_status(db, user, app_id, ApplicationStatus(body.status), body.note)
    return _detail(db, app)


@router.post("/applications/{app_id}/interviews", response_model=s.InterviewOut, status_code=201)
def schedule_interview(
    app_id: uuid.UUID, body: s.InterviewIn, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> s.InterviewOut:
    interview = app_service.schedule_interview(
        db,
        user,
        app_id,
        starts_at=body.starts_at,
        duration_minutes=body.duration_minutes,
        location_or_link=body.location_or_link,
        notes=body.notes,
    )
    return s.InterviewOut.model_validate(interview)


@router.get("/applications/{app_id}/resume")
def application_resume(
    app_id: uuid.UUID, user: User = Depends(employer_user), db: Session = Depends(get_db)
) -> Response:
    app = app_service.get_employer_application(db, user, app_id)
    resume = db.get(Resume, app.resume_id) if app.resume_id else None
    if resume is None:
        raise NotFound("No resume was attached to this application.")
    audit(db, "application.resume_downloaded", actor_id=user.id, target_type="application", target_id=app.id)
    db.commit()
    return file_response(resume)
