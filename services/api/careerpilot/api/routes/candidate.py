"""Candidate-facing endpoints. Every query is scoped to the authenticated candidate."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from careerpilot.ai.skills import get_normalizer
from careerpilot.api import schemas as s
from careerpilot.api.deps import candidate_user
from careerpilot.api.serializers import (
    application_out,
    job_summary,
    match_out,
    profile_out,
    resume_detail_out,
    resume_out,
)
from careerpilot.config import get_settings
from careerpilot.db import get_db
from careerpilot.errors import NotFound, ValidationFailed
from careerpilot.infra.storage import get_storage
from careerpilot.models import (
    Application,
    CandidateEducation,
    CandidateExperience,
    CandidateSkill,
    CoverLetterDraft,
    FactStatus,
    Job,
    Resume,
    SavedJob,
    User,
)
from careerpilot.security import rate_limit as rl
from careerpilot.security.urls import validate_public_http_url
from careerpilot.services import applications as app_service
from careerpilot.services import generation, matching
from careerpilot.services import resumes as resume_service
from careerpilot.services.jobs import get_public_job
from careerpilot.services.profiles import get_profile

router = APIRouter(prefix="/candidate", tags=["candidate"])


def _refresh(db: Session, user: User) -> None:
    matching.refresh_candidate_embedding(db, user.id)


# ---------------------------------------------------------------------------------------------- profile
@router.get("/profile", response_model=s.ProfileOut)
def get_my_profile(user: User = Depends(candidate_user), db: Session = Depends(get_db)) -> s.ProfileOut:
    profile = get_profile(db, user.id)
    db.commit()
    return profile_out(profile, user)


@router.put("/profile", response_model=s.ProfileOut)
def update_profile(
    body: s.ProfileIn, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ProfileOut:
    profile = get_profile(db, user.id)
    data = body.model_dump(exclude_unset=True)
    if "links" in data:
        data["links"] = [validate_public_http_url(u, field="links") for u in data["links"]]
    for key, value in data.items():
        if key == "onboarding_completed" and value is None:
            continue
        setattr(profile, key, value)
    db.commit()
    _refresh(db, user)
    return profile_out(get_profile(db, user.id), user)


@router.put("/preferences", response_model=s.ProfileOut)
def update_preferences(
    body: s.PreferencesIO, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ProfileOut:
    profile = get_profile(db, user.id)
    if body.min_salary is not None and not body.salary_currency:
        raise ValidationFailed("salary_currency is required with min_salary.")
    assert profile.preferences is not None
    for key, value in body.model_dump().items():
        setattr(profile.preferences, key, value)
    db.commit()
    _refresh(db, user)
    return profile_out(get_profile(db, user.id), user)


@router.post("/skills", response_model=s.ProfileOut, status_code=201)
def add_skill(body: s.SkillIn, user: User = Depends(candidate_user), db: Session = Depends(get_db)) -> s.ProfileOut:
    profile = get_profile(db, user.id)
    display, key, _ = get_normalizer(db).normalize(body.name)
    existing = next((x for x in profile.skills if x.name_normalized == key), None)
    if existing:
        existing.status, existing.years = FactStatus.user_confirmed, body.years
    else:
        profile.skills.append(
            CandidateSkill(name=display, name_normalized=key, years=body.years, status=FactStatus.user_confirmed)
        )
    db.commit()
    _refresh(db, user)
    return profile_out(get_profile(db, user.id), user)


@router.delete("/skills/{skill_id}", response_model=s.ProfileOut)
def delete_skill(
    skill_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ProfileOut:
    profile = get_profile(db, user.id)
    skill = next((x for x in profile.skills if x.id == skill_id), None)
    if skill is None:
        raise NotFound("Skill not found.")
    profile.skills.remove(skill)
    db.commit()
    _refresh(db, user)
    return profile_out(get_profile(db, user.id), user)


@router.post("/experiences", response_model=s.ProfileOut, status_code=201)
def add_experience(
    body: s.ExperienceIn, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ProfileOut:
    profile = get_profile(db, user.id)
    profile.experiences.append(CandidateExperience(**body.model_dump(), status=FactStatus.user_confirmed))
    db.commit()
    _refresh(db, user)
    return profile_out(get_profile(db, user.id), user)


@router.put("/experiences/{exp_id}", response_model=s.ProfileOut)
def update_experience(
    exp_id: uuid.UUID, body: s.ExperienceIn, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ProfileOut:
    profile = get_profile(db, user.id)
    exp = next((x for x in profile.experiences if x.id == exp_id), None)
    if exp is None:
        raise NotFound("Experience not found.")
    for key, value in body.model_dump().items():
        setattr(exp, key, value)
    exp.status = FactStatus.user_confirmed
    db.commit()
    _refresh(db, user)
    return profile_out(get_profile(db, user.id), user)


@router.delete("/experiences/{exp_id}", response_model=s.ProfileOut)
def delete_experience(
    exp_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ProfileOut:
    profile = get_profile(db, user.id)
    exp = next((x for x in profile.experiences if x.id == exp_id), None)
    if exp is None:
        raise NotFound("Experience not found.")
    profile.experiences.remove(exp)
    db.commit()
    _refresh(db, user)
    return profile_out(get_profile(db, user.id), user)


@router.post("/educations", response_model=s.ProfileOut, status_code=201)
def add_education(
    body: s.EducationIn, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ProfileOut:
    profile = get_profile(db, user.id)
    profile.educations.append(CandidateEducation(**body.model_dump(), status=FactStatus.user_confirmed))
    db.commit()
    return profile_out(get_profile(db, user.id), user)


@router.delete("/educations/{edu_id}", response_model=s.ProfileOut)
def delete_education(
    edu_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ProfileOut:
    profile = get_profile(db, user.id)
    edu = next((x for x in profile.educations if x.id == edu_id), None)
    if edu is None:
        raise NotFound("Education not found.")
    profile.educations.remove(edu)
    db.commit()
    return profile_out(get_profile(db, user.id), user)


# ---------------------------------------------------------------------------------------------- resumes
@router.post("/resumes", response_model=s.ResumeOut, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    label: str | None = Form(default=None, max_length=120),
    user: User = Depends(candidate_user),
    db: Session = Depends(get_db),
) -> s.ResumeOut:
    rl.get_rate_limiter().hit(rl.UPLOAD, str(user.id))
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)  # bounded read: never load more than limit+1 bytes
    resume = resume_service.upload_resume(db, user, file.filename or "resume", data, label)
    return resume_out(resume)


@router.get("/resumes", response_model=list[s.ResumeOut])
def list_resumes(user: User = Depends(candidate_user), db: Session = Depends(get_db)) -> list[s.ResumeOut]:
    rows = db.scalars(select(Resume).where(Resume.owner_id == user.id).order_by(Resume.created_at.desc())).all()
    return [resume_out(r) for r in rows]


@router.get("/resumes/{resume_id}", response_model=s.ResumeDetailOut)
def get_resume(
    resume_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ResumeDetailOut:
    return resume_detail_out(resume_service.get_owned_resume(db, user, resume_id))


@router.patch("/resumes/{resume_id}", response_model=s.ResumeOut)
def patch_resume(
    resume_id: uuid.UUID, body: s.ResumePatchIn, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ResumeOut:
    resume = resume_service.get_owned_resume(db, user, resume_id)
    if body.label is not None:
        resume.label = body.label
    if body.is_primary:
        for other in db.scalars(select(Resume).where(Resume.owner_id == user.id, Resume.id != resume.id)):
            other.is_primary = False
        resume.is_primary = True
    db.commit()
    return resume_out(resume)


@router.post("/resumes/{resume_id}/retry", response_model=s.ResumeOut)
def retry_resume(
    resume_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ResumeOut:
    return resume_out(resume_service.retry_processing(db, user, resume_id))


@router.post("/resumes/{resume_id}/review", response_model=dict[str, int])
def review_resume(
    resume_id: uuid.UUID, body: s.ReviewFactsIn, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> dict[str, int]:
    return resume_service.review_facts(db, user, resume_id, body.accept, body.reject, body.overwrite_text_fields)


@router.delete("/resumes/{resume_id}", status_code=204)
def delete_resume(
    resume_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> Response:
    resume_service.delete_resume(db, user, resume_id)
    return Response(status_code=204)


@router.get("/resumes/{resume_id}/download")
def download_resume(
    resume_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> Response:
    resume = resume_service.get_owned_resume(db, user, resume_id)
    return file_response(resume)


def file_response(resume: Resume) -> Response:
    storage = get_storage()
    url = storage.signed_url(resume.document.storage_key, resume.document.original_filename)
    if url:
        return Response(status_code=307, headers={"Location": url, "Cache-Control": "no-store"})
    data = storage.get(resume.document.storage_key)
    return Response(
        content=data,
        media_type=resume.document.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{resume.document.original_filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ------------------------------------------------------------------------------------- recommendations
@router.get("/recommendations", response_model=s.RecommendationsOut)
def recommendations(
    include_ineligible: bool = False,
    limit: int = Query(default=20, ge=1, le=50),
    user: User = Depends(candidate_user),
    db: Session = Depends(get_db),
) -> s.RecommendationsOut:
    result = matching.recommend(db, user, limit=limit, include_ineligible=include_ineligible)
    return s.RecommendationsOut(
        items=[s.RecommendationOut(job=job_summary(i["job"]), match=match_out(i["result"])) for i in result["items"]],
        profile_ready=result["profile_ready"],
        hidden_ineligible=result["hidden_ineligible"],
        algorithm_version=result["algorithm_version"],
    )


@router.get("/jobs/{job_id}/match", response_model=s.MatchOut)
def job_match(job_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)) -> s.MatchOut:
    job = get_public_job(db, job_id)
    return match_out(matching.explain_job(db, user, job))


@router.post("/recommendation-events", response_model=dict[str, bool])
def recommendation_event(
    body: s.EventIn, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> dict[str, bool]:
    return {"recorded": matching.record_event(db, user, body.job_id, body.event_type)}


@router.get("/saved-jobs", response_model=list[s.JobSummaryOut])
def saved_jobs(user: User = Depends(candidate_user), db: Session = Depends(get_db)) -> list[s.JobSummaryOut]:
    jobs = (
        db.scalars(
            select(Job)
            .join(SavedJob, SavedJob.job_id == Job.id)
            .where(SavedJob.user_id == user.id)
            .order_by(SavedJob.created_at.desc())
        )
        .unique()
        .all()
    )
    return [job_summary(j) for j in jobs]


@router.put("/saved-jobs/{job_id}", status_code=204)
def save_job(job_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)) -> Response:
    get_public_job(db, job_id)
    if not db.scalar(select(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id)):
        db.add(SavedJob(user_id=user.id, job_id=job_id))
        db.commit()
        matching.record_event(db, user, job_id, "save")
    return Response(status_code=204)


@router.delete("/saved-jobs/{job_id}", status_code=204)
def unsave_job(job_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)) -> Response:
    row = db.scalar(select(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id))
    if row:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------------------------- cover letters
@router.get("/jobs/{job_id}/cover-letters", response_model=list[s.CoverLetterOut])
def list_cover_letters(
    job_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> list[s.CoverLetterOut]:
    rows = db.scalars(
        select(CoverLetterDraft)
        .where(CoverLetterDraft.owner_id == user.id, CoverLetterDraft.job_id == job_id)
        .order_by(CoverLetterDraft.version_number.desc())
    ).all()
    return [s.CoverLetterOut.model_validate(r) for r in rows]


@router.post("/jobs/{job_id}/cover-letters/generate", response_model=s.CoverLetterOut, status_code=201)
def generate_cover_letter(
    job_id: uuid.UUID,
    body: s.CoverLetterGenerateIn,
    user: User = Depends(candidate_user),
    db: Session = Depends(get_db),
) -> s.CoverLetterOut:
    job = get_public_job(db, job_id)
    return s.CoverLetterOut.model_validate(generation.generate_cover_letter(db, user, job, body.tone))


@router.post("/jobs/{job_id}/cover-letters", response_model=s.CoverLetterOut, status_code=201)
def save_cover_letter(
    job_id: uuid.UUID, body: s.CoverLetterSaveIn, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.CoverLetterOut:
    get_public_job(db, job_id)
    draft = generation.save_draft(db, user, job_id, body.content, generated_by=None, prompt_version=None)
    return s.CoverLetterOut.model_validate(draft)


# --------------------------------------------------------------------------------------- applications
@router.get("/applications/preview")
def application_preview(
    job_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    p = app_service.preview(db, user, job_id)
    draft = p["cover_letter_draft"]
    return {
        "job": s.JobOut.model_validate(p["job"]).model_dump(mode="json"),
        "facts": p["facts"],
        "resumes": [resume_out(r).model_dump(mode="json") for r in p["resumes"]],
        "cover_letter_draft": s.CoverLetterOut.model_validate(draft).model_dump(mode="json") if draft else None,
        "match": match_out(p["match"]).model_dump(mode="json"),
        "already_applied": p["already_applied"],
        "external_apply_url": p["external_apply_url"],
    }


@router.post("/applications", response_model=s.ApplicationOut, status_code=201)
def submit_application(
    body: s.ApplicationSubmitIn,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=100),
    user: User = Depends(candidate_user),
    db: Session = Depends(get_db),
) -> s.ApplicationOut:
    app, created = app_service.submit(
        db,
        user,
        job_id=body.job_id,
        resume_id=body.resume_id,
        cover_letter=body.cover_letter,
        cover_letter_draft_id=body.cover_letter_draft_id,
        confirmed=body.confirm,
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return application_out(db, app)


@router.get("/applications", response_model=s.Page[s.ApplicationOut])
def list_applications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status", max_length=30),
    user: User = Depends(candidate_user),
    db: Session = Depends(get_db),
) -> s.Page[s.ApplicationOut]:
    stmt = select(Application).where(Application.candidate_user_id == user.id)
    if status_filter:
        stmt = stmt.where(Application.status == status_filter)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Application.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return s.Page(items=[application_out(db, a) for a in rows], total=total, page=page, page_size=page_size)


@router.get("/applications/{app_id}", response_model=s.ApplicationOut)
def get_application(
    app_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ApplicationOut:
    return application_out(db, app_service.get_candidate_application(db, user, app_id))


@router.post("/applications/{app_id}/withdraw", response_model=s.ApplicationOut)
def withdraw_application(
    app_id: uuid.UUID, user: User = Depends(candidate_user), db: Session = Depends(get_db)
) -> s.ApplicationOut:
    app = app_service.withdraw(db, user, app_id)
    return application_out(db, app)
