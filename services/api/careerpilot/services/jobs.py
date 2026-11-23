"""Job creation, editing, AI-assisted requirement parsing and the publication state machine."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from careerpilot.ai.client import run_structured
from careerpilot.ai.prompts import JOB_EXTRACTION_VERSION, JOB_SYSTEM, job_prompt
from careerpilot.ai.providers import AIError, LLMRequest
from careerpilot.ai.schemas import JobExtraction
from careerpilot.ai.skills import get_normalizer
from careerpilot.config import get_settings
from careerpilot.db import utcnow
from careerpilot.errors import Conflict, Forbidden, NotFound, ServiceUnavailable, ValidationFailed
from careerpilot.models import Company, Job, JobSkill, JobStatus, SkillRequirement, User, VerificationStatus
from careerpilot.services.audit import audit
from careerpilot.services.companies import require_member

# Allowed transitions: from -> {to}
TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.draft: {JobStatus.published, JobStatus.pending_review, JobStatus.archived},
    JobStatus.pending_review: {JobStatus.published, JobStatus.draft},
    JobStatus.published: {JobStatus.paused, JobStatus.closed},
    JobStatus.paused: {JobStatus.published, JobStatus.closed},
    JobStatus.closed: {JobStatus.archived},
    JobStatus.archived: set(),
}
EDITABLE_STATES = {JobStatus.draft, JobStatus.paused, JobStatus.pending_review}


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in TRANSITIONS.get(current, set())


def _set_skills(db: Session, job: Job, required: list[dict[str, Any]], preferred: list[dict[str, Any]]) -> None:
    normalizer = get_normalizer(db)
    job.skills.clear()
    seen: set[str] = set()
    for items, kind in ((required, SkillRequirement.required), (preferred, SkillRequirement.preferred)):
        for item in items:
            display, key, _ = normalizer.normalize(item["name"])
            if not key or key in seen:
                continue
            seen.add(key)
            job.skills.append(
                JobSkill(name=display, name_normalized=key, requirement=kind, min_years=item.get("min_years"))
            )
    if len(job.skills) > 60:
        raise ValidationFailed("A job may list at most 60 skills.")


def create_job(db: Session, user: User, company_id: uuid.UUID, data: dict[str, Any]) -> Job:
    require_member(db, user, company_id, write=True)
    required = data.pop("required_skills", [])
    preferred = data.pop("preferred_skills", [])
    job = Job(company_id=company_id, recruiter_id=user.id, status=JobStatus.draft, **data)
    db.add(job)
    _set_skills(db, job, required, preferred)
    db.flush()
    audit(db, "job.created", actor_id=user.id, target_type="job", target_id=job.id)
    db.commit()
    return job


def get_company_job(db: Session, user: User, job_id: uuid.UUID, *, write: bool = False) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFound("Job not found.")
    require_member(db, user, job.company_id, write=write)  # 404 for non-members
    return job


def update_job(db: Session, user: User, job_id: uuid.UUID, data: dict[str, Any], expected_version: int | None) -> Job:
    job = get_company_job(db, user, job_id, write=True)
    if job.status not in EDITABLE_STATES:
        raise Conflict("Pause the job before editing it.", code="invalid_state")
    if expected_version is not None and expected_version != job.version:
        raise Conflict("This job was changed by someone else. Reload and try again.", code="version_conflict")
    required = data.pop("required_skills", None)
    preferred = data.pop("preferred_skills", None)
    for key, value in data.items():
        setattr(job, key, value)
    if required is not None or preferred is not None:
        _set_skills(db, job, required or [], preferred or [])
    job.version += 1
    audit(db, "job.updated", actor_id=user.id, target_type="job", target_id=job.id)
    db.commit()
    from careerpilot.services.matching import refresh_job_embedding

    refresh_job_embedding(db, job)
    return job


def transition_job(db: Session, user: User, job_id: uuid.UUID, target: JobStatus) -> Job:
    job = get_company_job(db, user, job_id, write=True)
    s = get_settings()
    if target == JobStatus.published and job.status == JobStatus.draft and s.job_moderation_enabled:
        target = JobStatus.pending_review
    if not can_transition(job.status, target):
        raise Conflict(f"A {job.status.value} job cannot be moved to {target.value}.", code="invalid_transition")
    if target == JobStatus.published and job.status == JobStatus.pending_review:
        raise Forbidden("Jobs pending review are published by a moderator.")
    if target == JobStatus.published:
        company = db.get(Company, job.company_id)
        assert company is not None
        if company.verification_status == VerificationStatus.suspended:
            raise Forbidden("This company is suspended.")
        if s.require_verified_company_to_publish and company.verification_status != VerificationStatus.verified:
            raise Forbidden("Your company must be verified before publishing jobs.", code="company_not_verified")
        if not job.skills or len(job.description or "") < 50:
            raise ValidationFailed("Add a description (50+ characters) and at least one skill before publishing.")
        if job.application_deadline and job.application_deadline < date.today():
            raise ValidationFailed("The application deadline is in the past.")
        job.published_at = job.published_at or utcnow()
    if target == JobStatus.closed:
        job.closed_at = utcnow()
    previous = job.status
    job.status = target
    job.version += 1
    audit(
        db,
        "job.status_changed",
        actor_id=user.id,
        target_type="job",
        target_id=job.id,
        metadata={"from": previous.value, "to": target.value},
    )
    db.commit()
    if target == JobStatus.published:
        from careerpilot.services.matching import refresh_job_embedding

        refresh_job_embedding(db, job)
    return job


def parse_description(db: Session, user: User, text: str) -> dict[str, Any]:
    """AI-assisted extraction of requirements for recruiter review. Nothing is saved or published."""
    if len(text) < 50:
        raise ValidationFailed("Paste a longer job description to analyze.")
    try:
        result, response = run_structured(
            db,
            LLMRequest(
                operation="job_extraction",
                system=JOB_SYSTEM,
                prompt=job_prompt(text[: get_settings().llm_max_input_chars]),
                prompt_version=JOB_EXTRACTION_VERSION,
                context={"text": text},
            ),
            JobExtraction,
            user_id=user.id,
        )
    except AIError as exc:
        db.commit()  # keep usage records
        raise ServiceUnavailable(
            "AI analysis is unavailable right now. You can enter requirements manually.", code="ai_unavailable"
        ) from exc
    db.commit()
    normalizer = get_normalizer(db)
    out = result.model_dump()
    out["required_skills"] = [normalizer.normalize(sk)[0] for sk in result.required_skills]
    out["preferred_skills"] = [normalizer.normalize(sk)[0] for sk in result.preferred_skills]
    out["model"] = response.model
    out["is_mock"] = response.provider == "mock"
    return out


def public_jobs_query(
    *,
    q: str | None = None,
    employment_type: str | None = None,
    work_arrangement: str | None = None,
    country: str | None = None,
    skill: str | None = None,
    min_salary: int | None = None,
) -> Select[tuple[Job]]:
    """Published, non-expired jobs from non-suspended companies. Used by search and as the SQL pre-filter
    for recommendations, so structured search keeps working when AI is unavailable."""
    stmt = (
        select(Job)
        .join(Company, Company.id == Job.company_id)
        .where(
            Job.status == JobStatus.published,
            Company.verification_status != VerificationStatus.suspended,
            or_(Job.application_deadline.is_(None), Job.application_deadline >= date.today()),
        )
    )
    if q:
        like = f"%{q.lower()[:100]}%"
        stmt = stmt.where(
            or_(
                func.lower(Job.title).like(like),
                func.lower(Job.description).like(like),
                func.lower(Company.name).like(like),
            )
        )
    if employment_type:
        stmt = stmt.where(Job.employment_type == employment_type)
    if work_arrangement:
        stmt = stmt.where(Job.work_arrangement == work_arrangement)
    if country:
        stmt = stmt.where(or_(Job.location_country == country.upper(), Job.work_arrangement == "remote"))
    if skill:
        key = skill.strip().lower()
        stmt = stmt.where(Job.id.in_(select(JobSkill.job_id).where(JobSkill.name_normalized == key)))
    if min_salary is not None:
        stmt = stmt.where(and_(Job.salary_max.is_not(None), Job.salary_max >= min_salary))
    return stmt


def get_public_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.scalar(public_jobs_query().where(Job.id == job_id))
    if job is None:
        raise NotFound("Job not found or no longer accepting applications.")
    return job
