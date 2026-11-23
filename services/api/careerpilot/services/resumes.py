"""Resume upload, asynchronous processing pipeline, and candidate review of extracted facts."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from careerpilot.ai.client import run_structured
from careerpilot.ai.heuristics import heuristic_extract
from careerpilot.ai.prompts import RESUME_EXTRACTION_VERSION, RESUME_SYSTEM, resume_prompt
from careerpilot.ai.providers import AIError, LLMRequest
from careerpilot.ai.schemas import RESUME_SCHEMA_VERSION, ResumeExtraction
from careerpilot.ai.skills import get_normalizer
from careerpilot.config import get_settings
from careerpilot.db import session_factory, utcnow
from careerpilot.errors import NotFound, ValidationFailed
from careerpilot.infra.storage import get_storage, new_object_key
from careerpilot.infra.tasks import enqueue, task
from careerpilot.models import (
    CandidateEducation,
    CandidateExperience,
    CandidateSkill,
    Document,
    DocumentKind,
    ExtractedProfileFact,
    FactStatus,
    ProcessingStatus,
    Resume,
    User,
)
from careerpilot.services import documents as docs
from careerpilot.services.audit import audit
from careerpilot.services.consent import has_consent
from careerpilot.services.notifications import notify
from careerpilot.services.profiles import get_profile

logger = logging.getLogger(__name__)


def upload_resume(db: Session, user: User, filename: str, data: bytes, label: str | None) -> Resume:
    validated = docs.validate_upload(filename, data)
    scan_status = docs.scan_for_malware(data)
    key = new_object_key(f"resumes/{user.id}")
    get_storage().put(key, data, validated.mime_type)
    try:
        document = Document(
            owner_id=user.id,
            kind=DocumentKind.resume_original,
            storage_key=key,
            original_filename=validated.safe_filename,
            mime_type=validated.mime_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            scan_status=scan_status,
        )
        db.add(document)
        db.flush()
        has_primary = db.scalar(
            select(func.count()).select_from(Resume).where(Resume.owner_id == user.id, Resume.is_primary.is_(True))
        )
        resume = Resume(
            owner_id=user.id,
            document_id=document.id,
            label=(label or validated.safe_filename)[:120],
            is_primary=not has_primary,
            status=ProcessingStatus.queued,
        )
        db.add(resume)
        audit(
            db,
            "resume.uploaded",
            actor_id=user.id,
            target_type="resume",
            target_id=resume.id,
            metadata={"size_bytes": len(data), "mime_type": validated.mime_type},
        )
        db.commit()
    except Exception:
        db.rollback()
        get_storage().delete(key)  # do not leave orphaned objects
        raise
    enqueue("process_resume", entity_type="resume", entity_id=str(resume.id), resume_id=str(resume.id))
    db.refresh(resume)
    return resume


def _ym_to_date(value: str | None) -> date | None:
    if not value:
        return None
    parts = value.split("-")
    return date(int(parts[0]), int(parts[1]) if len(parts) > 1 else 1, 1)


def _ground(extraction: ResumeExtraction, text: str, db: Session) -> ResumeExtraction:
    """Deterministic post-validation of model output against the source text."""
    normalizer = get_normalizer(db)
    lowered = text.lower()
    grounded_skills = []
    seen: set[str] = set()
    for skill in extraction.skills:
        display, key, _ = normalizer.normalize(skill.name)
        if key in seen:
            continue
        seen.add(key)
        canonical = normalizer.canonicalize(skill.name)
        mentioned = normalizer.mentioned(canonical, text) if canonical else skill.name.lower() in lowered
        if skill.basis == "stated" and not mentioned:
            skill = skill.model_copy(update={"basis": "inferred", "confidence": min(skill.confidence, 0.4)})
        grounded_skills.append(skill.model_copy(update={"name": display}))
    warnings = list(extraction.warnings)
    experiences = []
    for exp in extraction.experiences:
        start, end = _ym_to_date(exp.start), _ym_to_date(exp.end)
        if start and end and end < start:
            warnings.append(f"Dates for '{exp.title}' were inconsistent and were removed.")
            exp = exp.model_copy(update={"start": None, "end": None})
        if start and start > date.today():
            exp = exp.model_copy(update={"start": None})
        experiences.append(exp)
    return extraction.model_copy(update={"skills": grounded_skills, "experiences": experiences, "warnings": warnings})


def _facts_from_extraction(resume: Resume, extraction: ResumeExtraction, method: str) -> list[ExtractedProfileFact]:
    facts: list[ExtractedProfileFact] = []

    def add(
        fact_type: str,
        value: dict[str, Any],
        *,
        quote: str | None,
        section: str,
        confidence: float | None,
        basis: str = "stated",
    ) -> None:
        facts.append(
            ExtractedProfileFact(
                resume_id=resume.id,
                fact_type=fact_type,
                value=value,
                source_text=quote,
                source_section=section,
                confidence=confidence,
                method=method,
                status=FactStatus.stated if basis == "stated" else FactStatus.inferred,
                schema_version=RESUME_SCHEMA_VERSION,
            )
        )

    if extraction.headline:
        add("headline", {"text": extraction.headline}, quote=extraction.headline, section="header", confidence=0.5)
    if extraction.summary:
        add("summary", {"text": extraction.summary}, quote=extraction.summary[:400], section="summary", confidence=0.6)
    for s in extraction.skills:
        add("skill", {"name": s.name}, quote=s.source_quote, section="skills", confidence=s.confidence, basis=s.basis)
    for e in extraction.experiences:
        add(
            "experience",
            e.model_dump(exclude={"source_quote", "confidence"}),
            quote=e.source_quote,
            section="experience",
            confidence=e.confidence,
        )
    for ed in extraction.educations:
        add(
            "education",
            ed.model_dump(exclude={"source_quote", "confidence"}),
            quote=ed.source_quote,
            section="education",
            confidence=ed.confidence,
        )
    for c in extraction.certifications:
        add(
            "certification",
            c.model_dump(exclude={"source_quote"}),
            quote=c.source_quote,
            section="certifications",
            confidence=None,
        )
    return facts


@task("process_resume")
def process_resume(resume_id: str) -> None:
    db = session_factory()()
    try:
        resume = db.get(Resume, uuid.UUID(resume_id))
        if resume is None:
            return
        resume.status = ProcessingStatus.processing
        db.commit()
        try:
            _process(db, resume)
        except docs.ExtractionFailed as exc:
            db.rollback()
            resume = db.get(Resume, uuid.UUID(resume_id))
            assert resume is not None
            resume.status = ProcessingStatus.failed
            resume.status_detail = exc.user_message[:300]
            notify(
                db,
                resume.owner_id,
                kind="resume_processed",
                title="We could not read your resume",
                body=exc.user_message,
                dedupe_key=f"resume_failed:{resume.id}",
                link="/candidate/resumes",
            )
            db.commit()
        except Exception:
            db.rollback()
            resume = db.get(Resume, uuid.UUID(resume_id))
            if resume is not None:
                resume.status = ProcessingStatus.failed
                resume.status_detail = "Processing failed due to a temporary problem. You can retry."
                db.commit()
            raise
    finally:
        db.close()


def _process(db: Session, resume: Resume) -> None:
    s = get_settings()
    data = get_storage().get(resume.document.storage_key)
    text, method, pages = docs.extract_text(data, resume.document.mime_type)
    resume.extracted_text = text
    resume.extraction_method = method
    resume.page_count = pages
    resume.text_char_count = len(text)

    normalizer = get_normalizer(db)
    extraction: ResumeExtraction
    fact_method = "heuristic"
    model_name: str | None = None
    detail = None
    if has_consent(db, resume.owner_id, "ai_processing"):
        clipped = text[: s.llm_max_input_chars]
        try:
            extraction, response = run_structured(
                db,
                LLMRequest(
                    operation="resume_extraction",
                    system=RESUME_SYSTEM,
                    prompt=resume_prompt(clipped),
                    prompt_version=RESUME_EXTRACTION_VERSION,
                    context={"text": clipped},
                ),
                ResumeExtraction,
                user_id=resume.owner_id,
            )
            extraction = _ground(extraction, text, db)
            if len(text) > len(clipped):
                extraction.warnings.append(
                    "The resume was longer than the AI input limit; only the first part was analyzed by AI."
                )
            fact_method, model_name = "llm", response.model
        except AIError as exc:
            logger.warning("resume_ai_extraction_failed_using_heuristics", extra={"error_code": exc.code})
            extraction = heuristic_extract(text, normalizer)
            detail = "AI extraction was unavailable; basic extraction was used. Please review carefully."
    else:
        extraction = heuristic_extract(text, normalizer)
        detail = "Basic extraction was used because AI processing is not enabled in your privacy settings."

    db.query(ExtractedProfileFact).filter(ExtractedProfileFact.resume_id == resume.id).delete()
    for fact in _facts_from_extraction(resume, extraction, fact_method):
        db.add(fact)
    resume.extraction = extraction.model_dump(mode="json")
    resume.schema_version = RESUME_SCHEMA_VERSION
    resume.model_name = model_name or ("heuristic-v1" if fact_method == "heuristic" else None)
    resume.status = ProcessingStatus.completed
    resume.status_detail = detail
    resume.processed_at = utcnow()
    notify(
        db,
        resume.owner_id,
        kind="resume_processed",
        title="Your resume is ready to review",
        body="We extracted information from your resume. Review and confirm it to improve your matches.",
        dedupe_key=f"resume_processed:{resume.id}:{resume.processed_at.isoformat()}",
        link=f"/candidate/resumes/{resume.id}",
    )
    db.commit()


def get_owned_resume(db: Session, user: User, resume_id: uuid.UUID) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.owner_id != user.id or resume.document.deleted_at is not None:
        raise NotFound("Resume not found.")  # same response for "missing" and "not yours" (no IDOR oracle)
    return resume


def retry_processing(db: Session, user: User, resume_id: uuid.UUID) -> Resume:
    resume = get_owned_resume(db, user, resume_id)
    if resume.status not in (ProcessingStatus.failed, ProcessingStatus.completed):
        raise ValidationFailed("The resume is already being processed.", code="invalid_state")
    resume.status = ProcessingStatus.queued
    resume.status_detail = None
    db.commit()
    enqueue("process_resume", entity_type="resume", entity_id=str(resume.id), resume_id=str(resume.id))
    db.refresh(resume)
    return resume


def delete_resume(db: Session, user: User, resume_id: uuid.UUID) -> None:
    resume = get_owned_resume(db, user, resume_id)
    key = resume.document.storage_key
    document = resume.document
    db.delete(resume)
    db.delete(document)
    audit(db, "resume.deleted", actor_id=user.id, target_type="resume", target_id=resume_id)
    db.commit()
    get_storage().delete(key)


def review_facts(
    db: Session,
    user: User,
    resume_id: uuid.UUID,
    accept_ids: list[uuid.UUID],
    reject_ids: list[uuid.UUID],
    overwrite_text_fields: bool = False,
) -> dict[str, int]:
    """Apply candidate decisions. Accepted facts become user-confirmed profile data; existing confirmed
    profile fields are never overwritten unless `overwrite_text_fields` is explicitly requested."""
    resume = get_owned_resume(db, user, resume_id)
    profile = get_profile(db, user.id)
    normalizer = get_normalizer(db)
    facts = {f.id: f for f in resume.facts}
    applied = rejected = skipped = 0
    for fid in reject_ids:
        fact = facts.get(fid)
        if fact is not None:
            fact.status = FactStatus.rejected
            rejected += 1
    existing_skills = {s.name_normalized: s for s in profile.skills}
    for fid in accept_ids:
        fact = facts.get(fid)
        if fact is None or fid in reject_ids:
            continue
        v = fact.value
        if fact.fact_type == "skill":
            display, key, _ = normalizer.normalize(v["name"])
            if key in existing_skills:
                existing_skills[key].status = FactStatus.user_confirmed
            else:
                skill = CandidateSkill(
                    name=display,
                    name_normalized=key,
                    status=FactStatus.user_confirmed,
                    evidence={"resume_id": str(resume.id), "quote": fact.source_text},
                )
                profile.skills.append(skill)
                existing_skills[key] = skill
        elif fact.fact_type == "experience":
            start = _ym_to_date(v.get("start"))
            dup = any(
                e.title.lower() == v["title"].lower()
                and e.company.lower() == v["company"].lower()
                and e.start_date == start
                for e in profile.experiences
            )
            if dup:
                skipped += 1
            else:
                profile.experiences.append(
                    CandidateExperience(
                        title=v["title"],
                        company=v["company"],
                        location=v.get("location"),
                        start_date=start,
                        end_date=_ym_to_date(v.get("end")),
                        is_current=bool(v.get("is_current")),
                        description=v.get("description"),
                        status=FactStatus.user_confirmed,
                        source_resume_id=resume.id,
                    )
                )
        elif fact.fact_type == "education":
            dup = any(
                e.institution.lower() == v["institution"].lower() and e.degree == v.get("degree")
                for e in profile.educations
            )
            if dup:
                skipped += 1
            else:
                profile.educations.append(
                    CandidateEducation(
                        institution=v["institution"],
                        degree=v.get("degree"),
                        field_of_study=v.get("field_of_study"),
                        start_date=_ym_to_date(v.get("start")),
                        end_date=_ym_to_date(v.get("end")),
                        status=FactStatus.user_confirmed,
                        source_resume_id=resume.id,
                    )
                )
        elif fact.fact_type in ("headline", "summary"):
            current = getattr(profile, fact.fact_type)
            if current and not overwrite_text_fields:
                skipped += 1
                continue
            setattr(profile, fact.fact_type, str(v["text"])[: 2000 if fact.fact_type == "summary" else 200])
        else:
            skipped += 1
            continue
        fact.status = FactStatus.user_confirmed
        fact.applied_at = utcnow()
        applied += 1
    audit(
        db,
        "profile.facts_reviewed",
        actor_id=user.id,
        target_type="resume",
        target_id=resume.id,
        metadata={"applied": applied, "rejected": rejected, "skipped": skipped},
    )
    db.commit()
    from careerpilot.services.matching import refresh_candidate_embedding

    refresh_candidate_embedding(db, user.id)
    return {"applied": applied, "rejected": rejected, "skipped": skipped}
