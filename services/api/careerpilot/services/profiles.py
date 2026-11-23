"""Candidate profile helpers: confirmed facts, experience calculation, embedding text."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from careerpilot.errors import NotFound
from careerpilot.models import (
    CandidateExperience,
    CandidatePreferences,
    CandidateProfile,
    FactStatus,
    User,
)

_USABLE = {FactStatus.user_confirmed}


def get_profile(db: Session, user_id: uuid.UUID) -> CandidateProfile:
    profile = db.scalar(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user_id)
        .options(
            selectinload(CandidateProfile.skills),
            selectinload(CandidateProfile.experiences),
            selectinload(CandidateProfile.educations),
            selectinload(CandidateProfile.preferences),
        )
    )
    if profile is None:
        raise NotFound("Candidate profile not found.")
    if profile.preferences is None:
        profile.preferences = CandidatePreferences()
        db.flush()
    return profile


def compute_years_experience(experiences: list[CandidateExperience], today: date | None = None) -> float | None:
    """Total non-overlapping months across confirmed roles with a start date, in years (1 decimal)."""
    today = today or date.today()
    intervals: list[tuple[date, date]] = []
    for exp in experiences:
        if exp.status not in _USABLE or exp.start_date is None:
            continue
        end = today if (exp.is_current or exp.end_date is None) else exp.end_date
        if end < exp.start_date:
            continue
        intervals.append((exp.start_date, min(end, today)))
    if not intervals:
        return None
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    days = sum((e - s).days for s, e in merged)
    return round(days / 365.25, 1)


def years_experience(profile: CandidateProfile) -> float | None:
    if profile.years_experience_confirmed is not None:
        return profile.years_experience_confirmed
    return compute_years_experience(profile.experiences)


def confirmed_skills(profile: CandidateProfile) -> list[str]:
    return sorted({s.name for s in profile.skills if s.status in _USABLE})


def candidate_facts(profile: CandidateProfile, user: User) -> dict[str, Any]:
    """Confirmed candidate facts only. This is the ONLY candidate data given to generation prompts."""
    return {
        "name": user.full_name,
        "headline": profile.headline,
        "summary": profile.summary,
        "location": ", ".join(p for p in [profile.location_city, profile.location_country] if p) or None,
        "years_experience": years_experience(profile),
        "skills": confirmed_skills(profile),
        "experiences": [
            {
                "title": e.title,
                "company": e.company,
                "start": e.start_date,
                "end": e.end_date,
                "is_current": e.is_current,
                "description": (e.description or "")[:800],
            }
            for e in profile.experiences
            if e.status in _USABLE
        ],
        "educations": [
            {"institution": e.institution, "degree": e.degree, "field_of_study": e.field_of_study, "end": e.end_date}
            for e in profile.educations
            if e.status in _USABLE
        ],
    }


def profile_embedding_text(profile: CandidateProfile) -> str:
    prefs = profile.preferences
    parts = [profile.headline or "", profile.summary or "", " ".join(confirmed_skills(profile))]
    parts += [f"{e.title} {e.description or ''}" for e in profile.experiences if e.status in _USABLE]
    if prefs:
        parts.append(" ".join(prefs.desired_titles or []))
    return "\n".join(p for p in parts if p).strip()


def profile_completeness(profile: CandidateProfile) -> dict[str, Any]:
    checks = {
        "headline": bool(profile.headline),
        "skills": len(confirmed_skills(profile)) >= 3,
        "experience": any(e.status in _USABLE for e in profile.experiences),
        "preferences": bool(
            profile.preferences and (profile.preferences.desired_titles or profile.preferences.work_arrangements)
        ),
        "location": bool(profile.location_country),
    }
    return {"checks": checks, "percent": round(100 * sum(checks.values()) / len(checks))}
