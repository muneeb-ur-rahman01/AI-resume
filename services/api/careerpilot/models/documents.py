"""Stored documents (metadata only - binaries live in object storage), resumes and extracted facts."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerpilot.db import Base, JSONType, TimestampMixin, UUIDPk
from careerpilot.models.profiles import FactStatus


class DocumentKind(enum.StrEnum):
    resume_original = "resume_original"
    resume_tailored = "resume_tailored"
    cover_letter = "cover_letter"


class ProcessingStatus(enum.StrEnum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Document(UUIDPk, TimestampMixin, Base):
    __tablename__ = "documents"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[DocumentKind] = mapped_column(Enum(DocumentKind, native_enum=False, length=30))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)  # random, never the user's filename
    original_filename: Mapped[str] = mapped_column(String(255))  # sanitized, display only
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    scan_status: Mapped[str] = mapped_column(String(20), default="not_scanned")  # not_scanned|clean|infected
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Resume(UUIDPk, TimestampMixin, Base):
    """An uploaded original resume. The original document is immutable."""

    __tablename__ = "resumes"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    is_primary: Mapped[bool] = mapped_column(default=False)
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, native_enum=False, length=20), default=ProcessingStatus.queued, index=True
    )
    status_detail: Mapped[str | None] = mapped_column(String(300))  # safe, user-facing message
    extraction_method: Mapped[str | None] = mapped_column(String(40))  # native_pdf|docx|ocr
    page_count: Mapped[int | None] = mapped_column(Integer)
    text_char_count: Mapped[int | None] = mapped_column(Integer)
    extracted_text: Mapped[str | None] = mapped_column(Text)  # normalized plain text; deleted with resume
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # validated ResumeExtraction JSON
    schema_version: Mapped[str | None] = mapped_column(String(20))
    model_name: Mapped[str | None] = mapped_column(String(100))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document = relationship("Document", lazy="joined")
    facts: Mapped[list[ExtractedProfileFact]] = relationship(back_populates="resume", cascade="all, delete-orphan")


class ResumeVersion(UUIDPk, TimestampMixin, Base):
    """A tailored, candidate-editable version derived from an original resume (stored as text)."""

    __tablename__ = "resume_versions"

    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    version_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    unsupported_claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractedProfileFact(UUIDPk, TimestampMixin, Base):
    """Field-level provenance for AI/heuristic extraction. Facts are suggestions until the candidate
    confirms them; they never silently overwrite confirmed profile data."""

    __tablename__ = "extracted_profile_facts"

    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    fact_type: Mapped[str] = mapped_column(String(40))  # skill|experience|education|headline|summary|location
    value: Mapped[dict[str, Any]] = mapped_column(JSONType)
    source_text: Mapped[str | None] = mapped_column(Text)
    source_section: Mapped[str | None] = mapped_column(String(60))
    confidence: Mapped[float | None] = mapped_column()
    method: Mapped[str] = mapped_column(String(40))  # llm|taxonomy_match|heuristic
    status: Mapped[FactStatus] = mapped_column(Enum(FactStatus, native_enum=False, length=20))
    schema_version: Mapped[str] = mapped_column(String(20))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resume: Mapped[Resume] = relationship(back_populates="facts")
