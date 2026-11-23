"""Jobs and job skills."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerpilot.db import Base, JSONType, TimestampMixin, UUIDPk


class JobStatus(enum.StrEnum):
    draft = "draft"
    pending_review = "pending_review"
    published = "published"
    paused = "paused"
    closed = "closed"
    archived = "archived"


class EmploymentType(enum.StrEnum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    internship = "internship"
    temporary = "temporary"


class WorkArrangement(enum.StrEnum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"


class SkillRequirement(enum.StrEnum):
    required = "required"
    preferred = "preferred"


class Job(UUIDPk, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max", name="salary_range"),
        CheckConstraint(
            "min_experience_years IS NULL OR max_experience_years IS NULL OR "
            "min_experience_years <= max_experience_years",
            name="experience_range",
        ),
        CheckConstraint("openings >= 1", name="openings_positive"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    responsibilities: Mapped[list[str]] = mapped_column(JSONType, default=list)
    benefits: Mapped[list[str]] = mapped_column(JSONType, default=list)
    min_experience_years: Mapped[float | None] = mapped_column()
    max_experience_years: Mapped[float | None] = mapped_column()
    education_requirement: Mapped[str | None] = mapped_column(String(300))
    employment_type: Mapped[EmploymentType] = mapped_column(Enum(EmploymentType, native_enum=False, length=20))
    work_arrangement: Mapped[WorkArrangement] = mapped_column(Enum(WorkArrangement, native_enum=False, length=20))
    location_city: Mapped[str | None] = mapped_column(String(120))
    location_country: Mapped[str | None] = mapped_column(String(2))
    timezone: Mapped[str | None] = mapped_column(String(64))
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    application_deadline: Mapped[date | None] = mapped_column(Date)
    openings: Mapped[int] = mapped_column(Integer, default=1)
    # If set, applications happen on an external site; the platform only links to it.
    external_apply_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=20), default=JobStatus.draft, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic concurrency guard

    skills: Mapped[list[JobSkill]] = relationship(back_populates="job", cascade="all, delete-orphan", lazy="selectin")
    company = relationship("Company", lazy="joined")


class JobSkill(UUIDPk, TimestampMixin, Base):
    __tablename__ = "job_skills"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skills_taxonomy.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))
    name_normalized: Mapped[str] = mapped_column(String(120), index=True)
    requirement: Mapped[SkillRequirement] = mapped_column(Enum(SkillRequirement, native_enum=False, length=20))
    min_years: Mapped[float | None] = mapped_column()
    job: Mapped[Job] = relationship(back_populates="skills")


Index("ix_jobs_status_published", Job.status, Job.published_at)
Index("ix_jobs_search", Job.status, Job.employment_type, Job.work_arrangement, Job.location_country)
