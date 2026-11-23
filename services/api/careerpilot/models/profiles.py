"""Candidate profile, preferences, experience, education, skills, skills taxonomy."""

from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import Any

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerpilot.db import Base, JSONType, TimestampMixin, UUIDPk


class FactStatus(enum.StrEnum):
    """Provenance status of a profile fact."""

    stated = "stated"  # explicitly stated in a source document
    inferred = "inferred"  # derived by AI/heuristics, not explicitly stated
    user_confirmed = "user_confirmed"  # confirmed or entered by the candidate
    rejected = "rejected"  # candidate rejected the suggestion


class SkillTaxonomy(UUIDPk, TimestampMixin, Base):
    __tablename__ = "skills_taxonomy"

    canonical_name: Mapped[str] = mapped_column(String(120), unique=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(60))
    aliases: Mapped[list[str]] = mapped_column(JSONType, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)


class CandidateProfile(UUIDPk, TimestampMixin, Base):
    __tablename__ = "candidate_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    headline: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    location_city: Mapped[str | None] = mapped_column(String(120))
    location_country: Mapped[str | None] = mapped_column(String(2))  # ISO-3166 alpha-2
    phone: Mapped[str | None] = mapped_column(String(40))
    links: Mapped[list[str]] = mapped_column(JSONType, default=list)
    # Years of relevant experience as confirmed by the candidate (overrides computed value when set).
    years_experience_confirmed: Mapped[float | None] = mapped_column()
    onboarding_completed: Mapped[bool] = mapped_column(default=False)

    experiences: Mapped[list[CandidateExperience]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="CandidateExperience.start_date.desc()"
    )
    educations: Mapped[list[CandidateEducation]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    skills: Mapped[list[CandidateSkill]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    preferences: Mapped[CandidatePreferences | None] = relationship(
        back_populates="profile", cascade="all, delete-orphan", uselist=False
    )


class CandidatePreferences(UUIDPk, TimestampMixin, Base):
    __tablename__ = "candidate_preferences"

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), unique=True)
    desired_titles: Mapped[list[str]] = mapped_column(JSONType, default=list)
    employment_types: Mapped[list[str]] = mapped_column(JSONType, default=list)
    work_arrangements: Mapped[list[str]] = mapped_column(JSONType, default=list)
    preferred_locations: Mapped[list[str]] = mapped_column(JSONType, default=list)
    willing_to_relocate: Mapped[bool | None] = mapped_column()
    min_salary: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    available_from: Mapped[date | None] = mapped_column(Date)
    profile: Mapped[CandidateProfile] = relationship(back_populates="preferences")


class CandidateExperience(UUIDPk, TimestampMixin, Base):
    __tablename__ = "candidate_experiences"

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)  # NULL with is_current = ongoing
    is_current: Mapped[bool] = mapped_column(default=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FactStatus] = mapped_column(
        Enum(FactStatus, native_enum=False, length=20), default=FactStatus.user_confirmed
    )
    source_resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    profile: Mapped[CandidateProfile] = relationship(back_populates="experiences")


class CandidateEducation(UUIDPk, TimestampMixin, Base):
    __tablename__ = "candidate_educations"

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    institution: Mapped[str] = mapped_column(String(200))
    degree: Mapped[str | None] = mapped_column(String(200))
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[FactStatus] = mapped_column(
        Enum(FactStatus, native_enum=False, length=20), default=FactStatus.user_confirmed
    )
    source_resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    profile: Mapped[CandidateProfile] = relationship(back_populates="educations")


class CandidateSkill(UUIDPk, TimestampMixin, Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("profile_id", "name_normalized"),)

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skills_taxonomy.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))
    name_normalized: Mapped[str] = mapped_column(String(120), index=True)
    years: Mapped[float | None] = mapped_column()
    status: Mapped[FactStatus] = mapped_column(
        Enum(FactStatus, native_enum=False, length=20), default=FactStatus.user_confirmed
    )
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    profile: Mapped[CandidateProfile] = relationship(back_populates="skills")
