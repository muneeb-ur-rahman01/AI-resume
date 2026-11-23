"""Hybrid, explainable candidate-job matching.

Stages (see docs/AI_ARCHITECTURE.md):
  A. Eligibility from explicit hard constraints only (missing data never becomes a failure).
  B. Representations: confirmed candidate facts + structured job requirements + versioned embeddings.
  C. Retrieval: SQL filters (published/active jobs) UNION skill-overlap SQL UNION vector similarity
     (pgvector on PostgreSQL; in-Python cosine on SQLite test databases).
  D. Ranking: weighted, normalized components with documented INITIAL, UNCALIBRATED weights.
  E. Explanation: deterministic, grounded in the actual job and candidate data.
  F. Feedback: consented recommendation events for offline evaluation only.

The relevance score is a heuristic ordering signal. It is NOT a probability of being hired.
Protected characteristics are never inputs.
"""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import bindparam, select
from sqlalchemy.orm import Session

from careerpilot.ai.providers import AIError, get_embedding_provider
from careerpilot.config import get_settings
from careerpilot.db import Vector
from careerpilot.models import (
    Application,
    CandidateProfile,
    Embedding,
    Job,
    JobRecommendation,
    JobSkill,
    RecommendationEvent,
    SkillRequirement,
    User,
    WorkArrangement,
)
from careerpilot.services.consent import has_consent
from careerpilot.services.profiles import get_profile, profile_embedding_text, years_experience

ALGORITHM_VERSION = "rules-v1"

# Initial weights chosen by product judgment, NOT calibrated on outcome data. Re-calibrate with the
# offline evaluation suite (docs/AI_EVALUATION.md) before treating them as meaningful.
WEIGHTS: dict[str, float] = {
    "required_skills": 0.30,
    "preferred_skills": 0.10,
    "experience": 0.15,
    "semantic": 0.15,
    "title": 0.10,
    "location": 0.10,
    "salary": 0.05,
    "employment_type": 0.05,
}
_STOP = {
    "senior",
    "junior",
    "lead",
    "principal",
    "staff",
    "the",
    "and",
    "of",
    "for",
    "a",
    "an",
    "i",
    "ii",
    "iii",
    "mid",
    "level",
    "sr",
    "jr",
    "to",
    "in",
    "with",
    "remote",
    "hybrid",
}


@dataclass
class CandidateView:
    user_id: uuid.UUID
    skills: dict[str, str]  # normalized -> display
    years: float | None
    titles: list[str]
    city: str | None
    country: str | None
    willing_to_relocate: bool | None
    work_arrangements: list[str]
    employment_types: list[str]
    min_salary: int | None
    salary_currency: str | None
    vector: list[float] | None = None


@dataclass
class MatchResult:
    job_id: uuid.UUID
    score: int
    eligibility: str
    components: dict[str, Any]
    explanation: dict[str, Any]
    coverage: float = 0.0
    hard_conflicts: list[str] = field(default_factory=list)


def candidate_view(db: Session, user_id: uuid.UUID) -> CandidateView:
    profile = get_profile(db, user_id)
    return _view_from_profile(db, profile)


def _view_from_profile(db: Session, profile: CandidateProfile) -> CandidateView:
    from careerpilot.models import FactStatus

    prefs = profile.preferences
    skills = {s.name_normalized: s.name for s in profile.skills if s.status == FactStatus.user_confirmed}
    titles = list(prefs.desired_titles if prefs else []) + [
        e.title for e in profile.experiences if e.status == FactStatus.user_confirmed
    ]
    emb = db.scalar(
        select(Embedding).where(
            Embedding.owner_type == "candidate",
            Embedding.owner_id == profile.user_id,
            Embedding.model == get_embedding_provider().model,
        )
    )
    return CandidateView(
        user_id=profile.user_id,
        skills=skills,
        years=years_experience(profile),
        titles=titles,
        city=profile.location_city,
        country=profile.location_country,
        willing_to_relocate=prefs.willing_to_relocate if prefs else None,
        work_arrangements=list(prefs.work_arrangements if prefs else []),
        employment_types=list(prefs.employment_types if prefs else []),
        min_salary=prefs.min_salary if prefs else None,
        salary_currency=prefs.salary_currency if prefs else None,
        vector=emb.vector if emb else None,
    )


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9+#.]+", text.lower()) if t not in _STOP and len(t) > 1}


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def evaluate(c: CandidateView, job: Job, *, job_vector: list[float] | None = None) -> MatchResult:
    comp: dict[str, dict[str, Any]] = {}
    conflicts: list[str] = []
    prefs_notes: list[str] = []

    required = [s for s in job.skills if s.requirement == SkillRequirement.required]
    preferred = [s for s in job.skills if s.requirement == SkillRequirement.preferred]
    matched_req = [s.name for s in required if s.name_normalized in c.skills]
    missing_req = [s.name for s in required if s.name_normalized not in c.skills]
    matched_pref = [s.name for s in preferred if s.name_normalized in c.skills]
    missing_pref = [s.name for s in preferred if s.name_normalized not in c.skills]
    comp["required_skills"] = {
        "score": len(matched_req) / len(required) if required else None,
        "detail": f"{len(matched_req)} of {len(required)} required skills",
    }
    comp["preferred_skills"] = {
        "score": len(matched_pref) / len(preferred) if preferred else None,
        "detail": f"{len(matched_pref)} of {len(preferred)} preferred skills",
    }

    # Experience
    exp_text: str
    if job.min_experience_years is None:
        comp["experience"] = {"score": None, "detail": "No experience requirement stated"}
        exp_text = "The job does not state an experience requirement."
    elif c.years is None:
        comp["experience"] = {"score": None, "detail": "Your experience could not be determined"}
        exp_text = (
            f"The job asks for {job.min_experience_years:g}+ years; add dated roles to your profile "
            "so this can be compared."
        )
    else:
        need = job.min_experience_years
        if c.years >= need:
            score = 1.0
            exp_text = f"You have about {c.years:g} years of experience; the job asks for {need:g}+."
            if job.max_experience_years is not None and c.years > job.max_experience_years:
                score = 0.9
                exp_text += f" The stated range tops out at {job.max_experience_years:g} years."
        else:
            score = max(0.0, 1 - (need - c.years) / max(need, 1.0))
            exp_text = f"You have about {c.years:g} years of experience; the job asks for {need:g}+."
        comp["experience"] = {"score": score, "detail": exp_text}

    # Semantic similarity (embedding cosine, clamped to [0, 1])
    if c.vector is not None and job_vector is not None:
        comp["semantic"] = {
            "score": max(0.0, min(1.0, cosine(c.vector, job_vector))),
            "detail": "Text similarity between your profile and the job",
        }
    else:
        comp["semantic"] = {"score": None, "detail": "Embedding not available"}

    # Title / job family
    job_tokens = _tokens(job.title)
    if c.titles and job_tokens:
        best = max(len(job_tokens & _tokens(t)) / len(job_tokens) for t in c.titles)
        comp["title"] = {"score": best, "detail": "Similarity of the job title to your roles and target titles"}
    else:
        comp["title"] = {"score": None, "detail": "No titles to compare"}

    # Location / work arrangement
    arrangement = (
        job.work_arrangement.value if isinstance(job.work_arrangement, WorkArrangement) else str(job.work_arrangement)
    )
    loc_score: float | None
    if arrangement == "remote":
        loc_score = 1.0
        loc_detail = "Remote role"
    elif c.country is None:
        loc_score, loc_detail = None, "Add your location to compare"
    elif job.location_country and c.country.upper() == job.location_country.upper():
        same_city = bool(c.city and job.location_city and c.city.lower() == job.location_city.lower())
        loc_score = 1.0 if same_city or not job.location_city else 0.7
        loc_detail = f"{arrangement.title()} role in {job.location_city or job.location_country}"
    elif c.willing_to_relocate:
        loc_score, loc_detail = 0.6, "Requires relocation, which you indicated you are open to"
    elif c.willing_to_relocate is False:
        loc_score, loc_detail = 0.0, "Requires relocation, which you indicated you are not open to"
        conflicts.append("location")
    else:
        loc_score, loc_detail = 0.4, "Located in another country; relocation preference not set"
    if c.work_arrangements and arrangement not in c.work_arrangements:
        prefs_notes.append(f"The job is {arrangement}, which is not among your preferred work arrangements.")
        loc_score = min(loc_score, 0.3) if loc_score is not None else 0.3
    comp["location"] = {"score": loc_score, "detail": loc_detail}

    # Salary (no currency conversion: different currencies are "unknown", not a mismatch)
    if (
        c.min_salary
        and job.salary_max
        and job.salary_currency
        and c.salary_currency
        and job.salary_currency == c.salary_currency
    ):
        sal = 1.0 if job.salary_max >= c.min_salary else job.salary_max / c.min_salary
        comp["salary"] = {
            "score": sal,
            "detail": f"Up to {job.salary_max:,} {job.salary_currency} vs your "
            f"minimum {c.min_salary:,} {c.salary_currency}",
        }
        if sal < 1.0:
            prefs_notes.append("The maximum salary is below your stated minimum.")
    else:
        comp["salary"] = {"score": None, "detail": "Salary not comparable (missing or different currency)"}

    etype = job.employment_type.value if hasattr(job.employment_type, "value") else str(job.employment_type)
    if c.employment_types:
        ok = etype in c.employment_types
        comp["employment_type"] = {"score": 1.0 if ok else 0.0, "detail": etype.replace("_", " ")}
        if not ok:
            prefs_notes.append(f"The job is {etype.replace('_', ' ')}, which is not among your preferred types.")
    else:
        comp["employment_type"] = {"score": None, "detail": "No employment type preference"}

    known = {k: v for k, v in comp.items() if v["score"] is not None}
    total_w = sum(WEIGHTS[k] for k in known)
    raw = sum(WEIGHTS[k] * v["score"] for k, v in known.items()) / total_w if total_w else 0.0
    for k, v in comp.items():
        v["weight"] = WEIGHTS[k]
        if v["score"] is not None:
            v["score"] = round(v["score"], 3)

    # Eligibility (explicit hard conflicts only)
    if conflicts:
        eligibility = "ineligible"
    elif not c.skills and c.years is None:
        eligibility = "insufficient_information"
    elif not missing_req and (
        job.min_experience_years is None
        or (comp["experience"]["score"] is not None and comp["experience"]["score"] >= 0.9)
    ):
        eligibility = "eligible"
    else:
        eligibility = "potentially_eligible"

    score = round(raw * 100)
    summary_bits = []
    if required:
        summary_bits.append(f"You match {len(matched_req)} of {len(required)} required skills")
    if preferred:
        summary_bits.append(f"{len(matched_pref)} of {len(preferred)} preferred skills")
    explanation = {
        "summary": (", ".join(summary_bits) + ".") if summary_bits else "This job lists no specific skills.",
        "matched_required": matched_req,
        "missing_required": missing_req,
        "matched_preferred": matched_pref,
        "missing_preferred": missing_pref,
        "experience": exp_text,
        "preferences": prefs_notes,
        "data_coverage": round(total_w, 2),
        "disclaimer": (
            "Relevance score is a heuristic ranking signal based on your confirmed profile. It is not "
            "a prediction of hiring outcome. Skills marked missing were not found in your confirmed "
            "profile; you may still have them."
        ),
    }
    return MatchResult(
        job_id=job.id,
        score=score,
        eligibility=eligibility,
        components=comp,
        explanation=explanation,
        coverage=total_w,
        hard_conflicts=conflicts,
    )


# ------------------------------------------------------------------------------------------ embeddings
def _upsert_embedding(db: Session, owner_type: str, owner_id: uuid.UUID, text: str) -> None:
    provider = get_embedding_provider()
    content_hash = hashlib.sha256(f"{provider.model}:{text}".encode()).hexdigest()
    existing = db.scalar(
        select(Embedding).where(
            Embedding.owner_type == owner_type, Embedding.owner_id == owner_id, Embedding.model == provider.model
        )
    )
    if existing is not None and existing.content_hash == content_hash:
        return
    if not text.strip():
        if existing is not None:
            db.delete(existing)
            db.commit()
        return
    try:
        vector = provider.embed([text[:8000]])[0]
    except AIError:
        return  # retrieval falls back to SQL + skill overlap; will retry on next change
    if existing is None:
        db.add(
            Embedding(
                owner_type=owner_type,
                owner_id=owner_id,
                model=provider.model,
                dimensions=len(vector),
                content_hash=content_hash,
                vector=vector,
            )
        )
    else:
        existing.vector, existing.content_hash, existing.dimensions = vector, content_hash, len(vector)
    db.commit()


def refresh_candidate_embedding(db: Session, user_id: uuid.UUID) -> None:
    # External embedding providers receive profile text, so they require AI-processing consent.
    if get_settings().embedding_provider != "hashing" and not has_consent(db, user_id, "ai_processing"):
        return
    profile = get_profile(db, user_id)
    _upsert_embedding(db, "candidate", user_id, profile_embedding_text(profile))


def job_embedding_text(job: Job) -> str:
    skills = " ".join(s.name for s in job.skills)
    return f"{job.title}\n{skills}\n{job.description[:4000]}"


def refresh_job_embedding(db: Session, job: Job) -> None:
    _upsert_embedding(db, "job", job.id, job_embedding_text(job))


# ------------------------------------------------------------------------------------------- retrieval
def _retrieve(db: Session, c: CandidateView, pool: int) -> tuple[list[Job], dict[uuid.UUID, list[float]]]:
    from careerpilot.services.jobs import public_jobs_query

    model = get_embedding_provider().model
    excluded = select(Application.job_id).where(Application.candidate_user_id == c.user_id)
    dismissed = select(RecommendationEvent.job_id).where(
        RecommendationEvent.user_id == c.user_id, RecommendationEvent.event_type == "dismiss"
    )
    base = public_jobs_query().where(Job.id.not_in(excluded), Job.id.not_in(dismissed))
    ids: dict[uuid.UUID, None] = {}

    if c.skills:  # lexical/structured channel: jobs sharing any confirmed skill
        lexical = base.where(Job.id.in_(select(JobSkill.job_id).where(JobSkill.name_normalized.in_(list(c.skills)))))
        for job_id in db.scalars(lexical.with_only_columns(Job.id).order_by(Job.published_at.desc()).limit(pool)):
            ids[job_id] = None

    if c.vector is not None:  # semantic channel
        if db.get_bind().dialect.name == "postgresql":
            q = bindparam("q", c.vector, type_=Vector())
            semantic = (
                base.join(
                    Embedding,
                    (Embedding.owner_id == Job.id) & (Embedding.owner_type == "job") & (Embedding.model == model),
                )
                .with_only_columns(Job.id)
                .order_by(Embedding.vector.op("<=>")(q))
                .limit(pool)
            )
            for vec_job_id in db.scalars(semantic):
                ids[vec_job_id] = None
        else:
            rows = list(
                db.execute(
                    base.join(
                        Embedding,
                        (Embedding.owner_id == Job.id) & (Embedding.owner_type == "job") & (Embedding.model == model),
                    )
                    .with_only_columns(Job.id, Embedding.vector)
                    .limit(5000)
                ).all()
            )
            rows.sort(key=lambda r: -cosine(c.vector or [], r[1]))
            for r in rows[:pool]:
                ids[r[0]] = None

    if not ids:  # cold start: most recent published jobs
        for recent_id in db.scalars(base.with_only_columns(Job.id).order_by(Job.published_at.desc()).limit(pool)):
            ids[recent_id] = None

    jobs = list(db.scalars(select(Job).where(Job.id.in_(list(ids)))).unique())
    vectors: dict[uuid.UUID, list[float]] = {
        row[0]: row[1]
        for row in db.execute(
            select(Embedding.owner_id, Embedding.vector).where(
                Embedding.owner_type == "job", Embedding.model == model, Embedding.owner_id.in_(list(ids))
            )
        )
    }
    return jobs, vectors


def recommend(db: Session, user: User, *, limit: int | None = None, include_ineligible: bool = False) -> dict[str, Any]:
    s = get_settings()
    c = candidate_view(db, user.id)
    jobs, vectors = _retrieve(db, c, s.retrieval_candidate_pool)
    results = [evaluate(c, job, job_vector=vectors.get(job.id)) for job in jobs]
    hidden = sum(1 for r in results if r.eligibility == "ineligible")
    if not include_ineligible:
        results = [r for r in results if r.eligibility != "ineligible"]
    results.sort(key=lambda r: (-r.score, str(r.job_id)))
    results = results[: (limit or s.recommendation_limit)]

    existing = {
        r.job_id: r
        for r in db.scalars(
            select(JobRecommendation).where(
                JobRecommendation.candidate_user_id == user.id,
                JobRecommendation.job_id.in_([r.job_id for r in results]),
            )
        )
    }
    for r in results:
        rec = existing.get(r.job_id)
        if rec is None:
            db.add(
                JobRecommendation(
                    candidate_user_id=user.id,
                    job_id=r.job_id,
                    relevance_score=r.score,
                    eligibility=r.eligibility,
                    components=r.components,
                    explanation=r.explanation,
                    algorithm_version=ALGORITHM_VERSION,
                )
            )
        else:
            rec.relevance_score, rec.eligibility = r.score, r.eligibility
            rec.components, rec.explanation, rec.algorithm_version = r.components, r.explanation, ALGORITHM_VERSION
    if has_consent(db, user.id, "recommendation_tracking"):
        for r in results:
            db.add(
                RecommendationEvent(
                    user_id=user.id,
                    job_id=r.job_id,
                    event_type="impression",
                    algorithm_version=ALGORITHM_VERSION,
                    relevance_score=r.score,
                )
            )
    db.commit()
    job_map = {j.id: j for j in jobs}
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "profile_ready": bool(c.skills),
        "hidden_ineligible": hidden,
        "items": [{"job": job_map[r.job_id], "result": r} for r in results],
    }


def explain_job(db: Session, user: User, job: Job) -> MatchResult:
    c = candidate_view(db, user.id)
    vec = db.scalar(
        select(Embedding.vector).where(
            Embedding.owner_type == "job",
            Embedding.owner_id == job.id,
            Embedding.model == get_embedding_provider().model,
        )
    )
    return evaluate(c, job, job_vector=vec)


FEEDBACK_EVENTS = {"click", "save", "dismiss", "apply", "interview", "offer", "hire"}


def record_event(db: Session, user: User, job_id: uuid.UUID, event_type: str) -> bool:
    if event_type not in FEEDBACK_EVENTS:
        raise ValueError("invalid event")
    # Dismissals are a product action (hide the job), so they are stored regardless of tracking consent;
    # all other events are recorded only with recommendation-tracking consent.
    if event_type != "dismiss" and not has_consent(db, user.id, "recommendation_tracking"):
        return False
    rec = db.scalar(
        select(JobRecommendation).where(
            JobRecommendation.candidate_user_id == user.id, JobRecommendation.job_id == job_id
        )
    )
    db.add(
        RecommendationEvent(
            user_id=user.id,
            job_id=job_id,
            event_type=event_type,
            algorithm_version=rec.algorithm_version if rec else None,
            relevance_score=rec.relevance_score if rec else None,
        )
    )
    db.commit()
    return True
