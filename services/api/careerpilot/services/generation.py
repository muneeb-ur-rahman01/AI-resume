"""Cover-letter generation with deterministic factuality checks.

The model only receives confirmed candidate facts. After generation, the output is checked for
unsupported claims (skills not in the confirmed profile, numbers/years/percentages not present in the
source facts, employer names that are not in the candidate's history). Flags are shown to the candidate,
who must review and approve before anything is submitted.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from careerpilot.ai.client import run_structured
from careerpilot.ai.prompts import COVER_LETTER_SYSTEM, COVER_LETTER_VERSION, cover_letter_prompt
from careerpilot.ai.providers import AIError, LLMRequest
from careerpilot.ai.schemas import CoverLetterOutput
from careerpilot.ai.skills import get_normalizer
from careerpilot.errors import ServiceUnavailable, ValidationFailed
from careerpilot.models import CoverLetterDraft, Job, SkillRequirement, User
from careerpilot.security import rate_limit as rl
from careerpilot.services.consent import has_consent
from careerpilot.services.profiles import candidate_facts, get_profile

_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|\+|k\b|years?|yrs?|x\b|million|thousand)?", re.I)
_CAPITALIZED_AFTER_AT = re.compile(r"\b(?:at|with|for|joined)\s+([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,3})")


def job_context(job: Job) -> dict[str, Any]:
    return {
        "title": job.title,
        "company": job.company.name if job.company else None,
        "required_skills": [s.name for s in job.skills if s.requirement == SkillRequirement.required],
        "preferred_skills": [s.name for s in job.skills if s.requirement == SkillRequirement.preferred],
        "description": job.description[:3000],
    }


def find_unsupported_claims(
    text: str, facts: dict[str, Any], job: dict[str, Any], db: Session | None = None
) -> list[dict[str, str]]:
    normalizer = get_normalizer(db)
    claims: list[dict[str, str]] = []
    confirmed = {s.lower() for s in facts.get("skills", [])}
    facts_blob = json.dumps(facts, default=str).lower()
    for match in normalizer.find_in_text(text):
        if match.canonical.lower() not in confirmed:
            claims.append(
                {
                    "type": "skill",
                    "text": match.matched_text,
                    "reason": f"'{match.canonical}' is not in your confirmed skills.",
                }
            )
    for m in _NUMBER.finditer(text):
        token = m.group(0).strip()
        digits = re.sub(r"[^\d.]", "", token)
        if not digits or (len(digits) == 4 and digits.startswith(("19", "20"))):
            continue  # skip years like 2021 that appear as dates
        if digits not in facts_blob:
            claims.append(
                {"type": "number", "text": token, "reason": "This number does not appear in your confirmed profile."}
            )
    known_orgs = {str(e.get("company", "")).lower() for e in facts.get("experiences", [])}
    known_orgs |= {str(e.get("institution", "")).lower() for e in facts.get("educations", [])}
    known_orgs.add(str(job.get("company") or "").lower())
    for m in _CAPITALIZED_AFTER_AT.finditer(text):
        org = m.group(1).strip().rstrip(".")
        known = org.lower() in known_orgs or any(org.lower() in k or k in org.lower() for k in known_orgs if k)
        generic = normalizer.canonicalize(org) is not None or org.split()[0] in {"I", "My", "Your", "The"}
        if not known and not generic:
            claims.append(
                {
                    "type": "organization",
                    "text": org,
                    "reason": "This organization is not in your confirmed experience or education.",
                }
            )
    # de-duplicate
    seen: set[tuple[str, str]] = set()
    unique = []
    for c in claims:
        key = (c["type"], c["text"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def generate_cover_letter(db: Session, user: User, job: Job, tone: str = "professional") -> CoverLetterDraft:
    if tone not in {"professional", "warm", "concise"}:
        raise ValidationFailed("Unsupported tone.")
    if not has_consent(db, user.id, "ai_processing"):
        raise ValidationFailed(
            "AI generation requires AI-processing consent in your privacy settings. "
            "You can still write a cover letter yourself.",
            code="consent_required",
        )
    rl.get_rate_limiter().hit(rl.AI_GENERATION, str(user.id))
    profile = get_profile(db, user.id)
    facts = candidate_facts(profile, user)
    if not facts["skills"] and not facts["experiences"]:
        raise ValidationFailed(
            "Confirm some skills or experience in your profile before generating.", code="profile_incomplete"
        )
    jctx = job_context(job)
    try:
        output, response = run_structured(
            db,
            LLMRequest(
                operation="cover_letter",
                system=COVER_LETTER_SYSTEM,
                prompt=cover_letter_prompt(facts, jctx, tone),
                prompt_version=COVER_LETTER_VERSION,
                context={"candidate_facts": facts, "job": jctx},
            ),
            CoverLetterOutput,
            user_id=user.id,
        )
    except AIError as exc:
        db.commit()
        raise ServiceUnavailable(
            "Cover letter generation is unavailable right now. You can write one yourself.", code="ai_unavailable"
        ) from exc
    return save_draft(
        db,
        user,
        job.id,
        output.letter,
        generated_by=response.model,
        prompt_version=COVER_LETTER_VERSION,
        facts=facts,
        jctx=jctx,
    )


def save_draft(
    db: Session,
    user: User,
    job_id: uuid.UUID,
    content: str,
    *,
    generated_by: str | None,
    prompt_version: str | None,
    facts: dict[str, Any] | None = None,
    jctx: dict[str, Any] | None = None,
) -> CoverLetterDraft:
    content = content.strip()
    if not 50 <= len(content) <= 6000:
        raise ValidationFailed("Cover letters must be between 50 and 6000 characters.")
    if facts is None or jctx is None:
        job = db.get(Job, job_id)
        assert job is not None
        facts, jctx = candidate_facts(get_profile(db, user.id), user), job_context(job)
    latest = (
        db.scalar(
            select(func.max(CoverLetterDraft.version_number)).where(
                CoverLetterDraft.owner_id == user.id, CoverLetterDraft.job_id == job_id
            )
        )
        or 0
    )
    draft = CoverLetterDraft(
        owner_id=user.id,
        job_id=job_id,
        version_number=latest + 1,
        content=content,
        generated_by=generated_by,
        prompt_version=prompt_version,
        unsupported_claims=find_unsupported_claims(content, facts, jctx, db),
    )
    db.add(draft)
    db.commit()
    return draft
