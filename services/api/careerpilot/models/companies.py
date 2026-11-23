"""Companies, membership and employer verification."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerpilot.db import Base, JSONType, TimestampMixin, UUIDPk


class VerificationStatus(enum.StrEnum):
    unverified = "unverified"
    pending = "pending"
    verified = "verified"
    rejected = "rejected"
    suspended = "suspended"


class MemberRole(enum.StrEnum):
    owner = "owner"
    recruiter = "recruiter"
    viewer = "viewer"


class Company(UUIDPk, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(300))
    email_domain: Mapped[str | None] = mapped_column(String(253), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(120))
    size_range: Mapped[str | None] = mapped_column(String(40))
    headquarters: Mapped[str | None] = mapped_column(String(200))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False, length=20), default=VerificationStatus.unverified, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    members: Mapped[list[CompanyMember]] = relationship(back_populates="company", cascade="all, delete-orphan")


class CompanyMember(UUIDPk, TimestampMixin, Base):
    __tablename__ = "company_members"
    __table_args__ = (UniqueConstraint("company_id", "user_id"),)

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[MemberRole] = mapped_column(Enum(MemberRole, native_enum=False, length=20))
    company: Mapped[Company] = relationship(back_populates="members")


class CompanyVerificationRecord(UUIDPk, TimestampMixin, Base):
    """One verification request / decision. `signals` stores non-secret evidence such as domain match."""

    __tablename__ = "company_verification_records"

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, native_enum=False, length=20))
    method: Mapped[str] = mapped_column(String(40))  # email_domain_signal | manual_review
    signals: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    evidence_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
