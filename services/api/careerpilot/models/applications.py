"""Applications, submitted documents, status history, interviews, idempotency keys."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerpilot.db import Base, JSONType, TimestampMixin, UUIDPk


class ApplicationStatus(enum.StrEnum):
    draft = "draft"
    pending_approval = "pending_approval"
    queued = "queued"
    submitted = "submitted"
    submission_failed = "submission_failed"
    shortlisted = "shortlisted"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"
    hired = "hired"


class Application(UUIDPk, TimestampMixin, Base):
    __tablename__ = "applications"
    # One active application per candidate per job (duplicates prevented in DB, not just in code).
    __table_args__ = (UniqueConstraint("candidate_user_id", "job_id"),)

    candidate_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    status: Mapped[ApplicationStatus] = mapped_column(Enum(ApplicationStatus, native_enum=False, length=30), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when an authorized employer member first opened the application on this platform.
    first_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType)  # profile as approved at submission
    relevance_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    candidate_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    documents: Mapped[list[ApplicationDocument]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    history: Mapped[list[ApplicationStatusHistory]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationStatusHistory.created_at"
    )


class ApplicationDocument(UUIDPk, TimestampMixin, Base):
    __tablename__ = "application_documents"

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # cover_letter|resume_text
    content: Mapped[str] = mapped_column(Text)
    generated_by: Mapped[str | None] = mapped_column(String(100))  # model name, or null if hand-written
    unsupported_claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    application: Mapped[Application] = relationship(back_populates="documents")


class ApplicationStatusHistory(UUIDPk, TimestampMixin, Base):
    __tablename__ = "application_status_history"

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_type: Mapped[str] = mapped_column(String(20))  # candidate|employer|system|admin
    note: Mapped[str | None] = mapped_column(Text)  # visible to employer only
    application: Mapped[Application] = relationship(back_populates="history")


class CoverLetterDraft(UUIDPk, TimestampMixin, Base):
    """Versioned, candidate-editable cover letter draft for a job (before submission)."""

    __tablename__ = "cover_letter_drafts"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    generated_by: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(60))
    unsupported_claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)


class Interview(UUIDPk, TimestampMixin, Base):
    __tablename__ = "interviews"

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    scheduled_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(default=45)
    location_or_link: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")


class IdempotencyKey(UUIDPk, TimestampMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "scope", "key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(60))
    key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[uuid.UUID | None] = mapped_column()
