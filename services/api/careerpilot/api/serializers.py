"""ORM -> API DTO conversion helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerpilot.api import schemas as s
from careerpilot.models import Application, CandidateProfile, Interview, Job, Resume, User
from careerpilot.services.matching import ALGORITHM_VERSION, MatchResult
from careerpilot.services.profiles import profile_completeness, years_experience


def profile_out(profile: CandidateProfile, user: User) -> s.ProfileOut:
    return s.ProfileOut(
        full_name=user.full_name,
        email=user.email,
        headline=profile.headline,
        summary=profile.summary,
        location_city=profile.location_city,
        location_country=profile.location_country,
        phone=profile.phone,
        links=list(profile.links or []),
        years_experience=years_experience(profile),
        years_experience_confirmed=profile.years_experience_confirmed,
        onboarding_completed=profile.onboarding_completed,
        skills=[s.SkillOut.model_validate(x) for x in sorted(profile.skills, key=lambda k: k.name.lower())],
        experiences=[s.ExperienceOut.model_validate(x) for x in profile.experiences],
        educations=[s.EducationOut.model_validate(x) for x in profile.educations],
        preferences=s.PreferencesIO.model_validate(profile.preferences) if profile.preferences else None,
        completeness=profile_completeness(profile),
    )


def resume_out(r: Resume) -> s.ResumeOut:
    return s.ResumeOut(
        id=r.id,
        label=r.label,
        is_primary=r.is_primary,
        status=r.status.value,
        status_detail=r.status_detail,
        filename=r.document.original_filename,
        mime_type=r.document.mime_type,
        size_bytes=r.document.size_bytes,
        extraction_method=r.extraction_method,
        model_name=r.model_name,
        page_count=r.page_count,
        created_at=r.created_at,
        processed_at=r.processed_at,
    )


def resume_detail_out(r: Resume) -> s.ResumeDetailOut:
    base = resume_out(r).model_dump()
    return s.ResumeDetailOut(
        **base,
        facts=[s.FactOut.model_validate(f) for f in r.facts],
        warnings=list((r.extraction or {}).get("warnings", [])),
    )


def match_out(m: MatchResult) -> s.MatchOut:
    return s.MatchOut(
        relevance_score=m.score,
        eligibility=m.eligibility,
        components=m.components,
        explanation=m.explanation,
        algorithm_version=ALGORITHM_VERSION,
    )


def job_summary(job: Job) -> s.JobSummaryOut:
    return s.JobSummaryOut.model_validate(job)


def application_out(db: Session, app: Application) -> s.ApplicationOut:
    job = db.get(Job, app.job_id)
    assert job is not None
    resume = db.get(Resume, app.resume_id) if app.resume_id else None
    interviews = db.scalars(
        select(Interview).where(Interview.application_id == app.id).order_by(Interview.starts_at)
    ).all()
    return s.ApplicationOut(
        id=app.id,
        status=app.status.value,
        submitted_at=app.submitted_at,
        created_at=app.created_at,
        job=job_summary(job),
        history=[s.HistoryOut.model_validate(h) for h in app.history],
        documents=[s.ApplicationDocOut.model_validate(d) for d in app.documents],
        interviews=[s.InterviewOut.model_validate(i) for i in interviews],
        resume_label=resume.label if resume else None,
    )
