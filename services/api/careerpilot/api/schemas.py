"""Public API contracts (request/response DTOs). ORM models are never exposed directly."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

T = TypeVar("T")

CURRENCY = Field(default=None, pattern=r"^[A-Z]{3}$")
COUNTRY = Field(default=None, pattern=r"^[A-Z]{2}$")


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Message(BaseModel):
    message: str


# ------------------------------------------------------------------------------------------------ auth
class RegisterIn(In):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    full_name: str = Field(min_length=1, max_length=200)
    role: Literal["candidate", "employer"]
    ai_processing_consent: bool = False


class LoginIn(In):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenIn(In):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(In):
    email: EmailStr


class ResetPasswordIn(In):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(In):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class PasswordConfirmIn(In):
    password: str = Field(min_length=1, max_length=256)


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    roles: list[str]
    email_verified: bool
    csrf_token: str | None = None


class SessionOut(Out):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_prefix: str | None
    current: bool = False


# ------------------------------------------------------------------------------------------- candidate
class SkillOut(Out):
    id: uuid.UUID
    name: str
    years: float | None
    status: str


class SkillIn(In):
    name: str = Field(min_length=1, max_length=120)
    years: float | None = Field(default=None, ge=0, le=60)


class ExperienceIn(In):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    description: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _dates(self) -> ExperienceIn:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be after start_date")
        if self.start_date and self.start_date > date.today():
            raise ValueError("start_date cannot be in the future")
        if self.is_current:
            self.end_date = None
        return self


class ExperienceOut(Out):
    id: uuid.UUID
    title: str
    company: str
    location: str | None
    start_date: date | None
    end_date: date | None
    is_current: bool
    description: str | None
    status: str


class EducationIn(In):
    institution: str = Field(min_length=1, max_length=200)
    degree: str | None = Field(default=None, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _dates(self) -> EducationIn:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class EducationOut(Out):
    id: uuid.UUID
    institution: str
    degree: str | None
    field_of_study: str | None
    start_date: date | None
    end_date: date | None
    status: str


EMPLOYMENT_TYPES = Literal["full_time", "part_time", "contract", "internship", "temporary"]
ARRANGEMENTS = Literal["onsite", "hybrid", "remote"]


class PreferencesIO(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    desired_titles: list[str] = Field(default_factory=list, max_length=10)
    employment_types: list[EMPLOYMENT_TYPES] = Field(default_factory=list)
    work_arrangements: list[ARRANGEMENTS] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list, max_length=10)
    willing_to_relocate: bool | None = None
    min_salary: int | None = Field(default=None, ge=0, le=100_000_000)
    salary_currency: str | None = CURRENCY
    available_from: date | None = None

    @field_validator("desired_titles", "preferred_locations")
    @classmethod
    def _short(cls, v: list[str]) -> list[str]:
        return [s.strip()[:120] for s in v if s.strip()]


class ProfileIn(In):
    headline: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    location_city: str | None = Field(default=None, max_length=120)
    location_country: str | None = COUNTRY
    phone: str | None = Field(default=None, max_length=40, pattern=r"^[+0-9 ()\-]{6,40}$")
    links: list[str] = Field(default_factory=list, max_length=5)
    years_experience_confirmed: float | None = Field(default=None, ge=0, le=60)
    onboarding_completed: bool | None = None


class ProfileOut(BaseModel):
    full_name: str
    email: str
    headline: str | None
    summary: str | None
    location_city: str | None
    location_country: str | None
    phone: str | None
    links: list[str]
    years_experience: float | None
    years_experience_confirmed: float | None
    onboarding_completed: bool
    skills: list[SkillOut]
    experiences: list[ExperienceOut]
    educations: list[EducationOut]
    preferences: PreferencesIO | None
    completeness: dict[str, Any]


# ---------------------------------------------------------------------------------------------- resumes
class FactOut(Out):
    id: uuid.UUID
    fact_type: str
    value: dict[str, Any]
    source_text: str | None
    source_section: str | None
    confidence: float | None
    method: str
    status: str
    schema_version: str
    created_at: datetime


class ResumeOut(BaseModel):
    id: uuid.UUID
    label: str
    is_primary: bool
    status: str
    status_detail: str | None
    filename: str
    mime_type: str
    size_bytes: int
    extraction_method: str | None
    model_name: str | None
    page_count: int | None
    created_at: datetime
    processed_at: datetime | None


class ResumeDetailOut(ResumeOut):
    facts: list[FactOut]
    warnings: list[str]


class ReviewFactsIn(In):
    accept: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    reject: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    overwrite_text_fields: bool = False


class ResumePatchIn(In):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    is_primary: bool | None = None


# ------------------------------------------------------------------------------------------- companies
class CompanyIn(In):
    name: str = Field(min_length=2, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    email_domain: str | None = Field(default=None, max_length=253)
    description: str | None = Field(default=None, max_length=5000)
    industry: str | None = Field(default=None, max_length=120)
    size_range: Literal["1-10", "11-50", "51-200", "201-1000", "1001-5000", "5000+"] | None = None
    headquarters: str | None = Field(default=None, max_length=200)


class CompanyPatchIn(In):
    website: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    industry: str | None = Field(default=None, max_length=120)
    size_range: Literal["1-10", "11-50", "51-200", "201-1000", "1001-5000", "5000+"] | None = None
    headquarters: str | None = Field(default=None, max_length=200)


class CompanyOut(Out):
    id: uuid.UUID
    name: str
    slug: str
    website: str | None
    email_domain: str | None
    description: str | None
    industry: str | None
    size_range: str | None
    headquarters: str | None
    verification_status: str
    verified_at: datetime | None
    created_at: datetime


class MyCompanyOut(CompanyOut):
    my_role: str


class VerificationRequestIn(In):
    evidence_note: str | None = Field(default=None, max_length=2000)


class VerificationOut(Out):
    id: uuid.UUID
    status: str
    method: str
    signals: dict[str, Any]
    evidence_note: str | None
    decision_reason: str | None
    created_at: datetime
    reviewed_at: datetime | None


# ------------------------------------------------------------------------------------------------ jobs
class JobSkillIn(In):
    name: str = Field(min_length=1, max_length=120)
    min_years: float | None = Field(default=None, ge=0, le=40)


class JobIn(In):
    title: str = Field(min_length=2, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    description: str = Field(min_length=20, max_length=20000)
    responsibilities: list[str] = Field(default_factory=list, max_length=30)
    benefits: list[str] = Field(default_factory=list, max_length=30)
    required_skills: list[JobSkillIn] = Field(default_factory=list, max_length=40)
    preferred_skills: list[JobSkillIn] = Field(default_factory=list, max_length=40)
    min_experience_years: float | None = Field(default=None, ge=0, le=40)
    max_experience_years: float | None = Field(default=None, ge=0, le=50)
    education_requirement: str | None = Field(default=None, max_length=300)
    employment_type: EMPLOYMENT_TYPES
    work_arrangement: ARRANGEMENTS
    location_city: str | None = Field(default=None, max_length=120)
    location_country: str | None = COUNTRY
    timezone: str | None = Field(default=None, max_length=64)
    salary_min: int | None = Field(default=None, ge=0, le=100_000_000)
    salary_max: int | None = Field(default=None, ge=0, le=100_000_000)
    salary_currency: str | None = CURRENCY
    application_deadline: date | None = None
    openings: int = Field(default=1, ge=1, le=1000)
    external_apply_url: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _ranges(self) -> JobIn:
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("salary_min must not exceed salary_max")
        if (self.salary_min is not None or self.salary_max is not None) and not self.salary_currency:
            raise ValueError("salary_currency is required when a salary is given")
        if (
            self.min_experience_years is not None
            and self.max_experience_years is not None
            and self.min_experience_years > self.max_experience_years
        ):
            raise ValueError("min_experience_years must not exceed max_experience_years")
        if self.work_arrangement != "remote" and not self.location_country:
            raise ValueError("location_country is required for onsite and hybrid jobs")
        if self.application_deadline and self.application_deadline < date.today():
            raise ValueError("application_deadline cannot be in the past")
        return self


class JobPatchIn(JobIn):
    expected_version: int | None = None


class JobStatusIn(In):
    status: Literal["published", "paused", "closed", "archived", "draft"]


class ParseJobIn(In):
    text: str = Field(min_length=50, max_length=20000)


class CompanyBrief(Out):
    id: uuid.UUID
    name: str
    verification_status: str


class JobSkillOut(Out):
    name: str
    requirement: str
    min_years: float | None


class JobOut(Out):
    id: uuid.UUID
    title: str
    department: str | None
    description: str
    responsibilities: list[str]
    benefits: list[str]
    min_experience_years: float | None
    max_experience_years: float | None
    education_requirement: str | None
    employment_type: str
    work_arrangement: str
    location_city: str | None
    location_country: str | None
    timezone: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    application_deadline: date | None
    openings: int
    external_apply_url: str | None
    status: str
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
    skills: list[JobSkillOut]
    company: CompanyBrief


class JobSummaryOut(Out):
    id: uuid.UUID
    title: str
    employment_type: str
    work_arrangement: str
    location_city: str | None
    location_country: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    status: str
    published_at: datetime | None
    application_deadline: date | None
    company: CompanyBrief


class EmployerJobRow(JobSummaryOut):
    application_count: int = 0
    created_at: datetime


class ReportIn(In):
    reason: Literal["fraud", "discriminatory", "misleading", "abusive", "other"]
    details: str | None = Field(default=None, max_length=2000)


# ------------------------------------------------------------------------------------------- matching
class MatchOut(BaseModel):
    relevance_score: int
    eligibility: str
    components: dict[str, Any]
    explanation: dict[str, Any]
    algorithm_version: str


class RecommendationOut(BaseModel):
    job: JobSummaryOut
    match: MatchOut


class RecommendationsOut(BaseModel):
    items: list[RecommendationOut]
    profile_ready: bool
    hidden_ineligible: int
    algorithm_version: str


class EventIn(In):
    job_id: uuid.UUID
    event_type: Literal["click", "save", "dismiss"]


# --------------------------------------------------------------------------------------- applications
class CoverLetterGenerateIn(In):
    tone: Literal["professional", "warm", "concise"] = "professional"


class CoverLetterSaveIn(In):
    content: str = Field(min_length=50, max_length=6000)


class CoverLetterOut(Out):
    id: uuid.UUID
    job_id: uuid.UUID
    version_number: int
    content: str
    generated_by: str | None
    unsupported_claims: list[dict[str, Any]]
    created_at: datetime


class ApplicationSubmitIn(In):
    job_id: uuid.UUID
    resume_id: uuid.UUID | None = None
    cover_letter_draft_id: uuid.UUID | None = None
    cover_letter: str | None = Field(default=None, max_length=6000)
    confirm: bool


class HistoryOut(Out):
    from_status: str | None
    to_status: str
    actor_type: str
    created_at: datetime


class InterviewOut(Out):
    id: uuid.UUID
    starts_at: datetime
    duration_minutes: int
    location_or_link: str | None
    status: str


class ApplicationDocOut(Out):
    kind: str
    content: str
    generated_by: str | None
    unsupported_claims: list[dict[str, Any]]


class ApplicationOut(BaseModel):
    id: uuid.UUID
    status: str
    submitted_at: datetime | None
    created_at: datetime
    job: JobSummaryOut
    history: list[HistoryOut]
    documents: list[ApplicationDocOut]
    interviews: list[InterviewOut]
    resume_label: str | None


class EmployerHistoryOut(HistoryOut):
    note: str | None


class EmployerApplicationRow(BaseModel):
    id: uuid.UUID
    status: str
    submitted_at: datetime | None
    first_viewed_at: datetime | None
    candidate_name: str
    candidate_headline: str | None
    relevance_score: int | None
    eligibility: str | None


class EmployerApplicationDetail(EmployerApplicationRow):
    job: JobSummaryOut
    candidate: dict[str, Any]
    relevance: dict[str, Any] | None
    documents: list[ApplicationDocOut]
    history: list[EmployerHistoryOut]
    interviews: list[InterviewOut]
    has_resume: bool
    allowed_transitions: list[str]


class ApplicationStatusIn(In):
    status: Literal["shortlisted", "interview", "offer", "rejected", "hired"]
    note: str | None = Field(default=None, max_length=2000)


class InterviewIn(In):
    starts_at: datetime
    duration_minutes: int = Field(default=45, ge=15, le=480)
    location_or_link: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


# ----------------------------------------------------------------------------------------------- misc
class NotificationOut(Out):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str | None
    read_at: datetime | None
    created_at: datetime
    email_status: str


class NotificationPrefsIO(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    email_application_updates: bool
    email_recommendations: bool
    email_processing_updates: bool


class ConsentsIO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ai_processing: bool
    recommendation_tracking: bool


class AuditOut(Out):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    event_metadata: dict[str, Any]
    request_id: str | None
    created_at: datetime


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    roles: list[str]
    status: str
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None


class AdminDecisionIn(In):
    approve: bool
    reason: str | None = Field(default=None, max_length=2000)


class AdminReasonIn(In):
    reason: str = Field(min_length=3, max_length=2000)


class ReportOut(Out):
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reason: str
    details: str | None
    status: str
    created_at: datetime


class ResolveReportIn(In):
    action: Literal["dismiss", "pause_job", "close_job"]
    reason: str = Field(min_length=3, max_length=2000)


class TaskOut(Out):
    id: uuid.UUID
    name: str
    entity_type: str | None
    entity_id: str | None
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    finished_at: datetime | None


class SkillTaxonomyIn(In):
    canonical_name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class SkillTaxonomyOut(Out):
    id: uuid.UUID
    canonical_name: str
    category: str
    aliases: list[str]
    is_active: bool
