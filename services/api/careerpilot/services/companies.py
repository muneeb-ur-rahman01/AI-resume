"""Companies, membership authorization and employer verification."""

from __future__ import annotations

import re
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerpilot.config import get_settings
from careerpilot.db import utcnow
from careerpilot.errors import Conflict, Forbidden, NotFound, ValidationFailed
from careerpilot.models import (
    Company,
    CompanyMember,
    CompanyVerificationRecord,
    MemberRole,
    User,
    VerificationStatus,
)
from careerpilot.services.audit import audit
from careerpilot.services.notifications import notify

# Free/consumer mailbox domains never count as a company-domain signal.
FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "gmx.com",
    "mail.com",
    "yandex.com",
    "zoho.com",
}
_WRITE_ROLES = {MemberRole.owner, MemberRole.recruiter}


def slugify_company(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:180] or "company"
    return f"{base}-{secrets.token_hex(3)}"


def membership(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> CompanyMember | None:
    return db.scalar(
        select(CompanyMember).where(CompanyMember.user_id == user_id, CompanyMember.company_id == company_id)
    )


def require_member(db: Session, user: User, company_id: uuid.UUID, *, write: bool = False) -> CompanyMember:
    """Authorization gate for all company-scoped data. Non-members get 404 to avoid revealing existence."""
    member = membership(db, user.id, company_id)
    if member is None:
        raise NotFound("Company not found.")
    if write and member.role not in _WRITE_ROLES:
        raise Forbidden("Your company role does not allow this action.")
    return member


def user_companies(db: Session, user_id: uuid.UUID) -> list[tuple[Company, CompanyMember]]:
    rows = db.execute(
        select(Company, CompanyMember)
        .join(CompanyMember, CompanyMember.company_id == Company.id)
        .where(CompanyMember.user_id == user_id)
        .order_by(Company.created_at)
    ).all()
    return [(r[0], r[1]) for r in rows]


def create_company(
    db: Session,
    user: User,
    *,
    name: str,
    website: str | None,
    email_domain: str | None,
    description: str | None,
    industry: str | None,
    size_range: str | None,
    headquarters: str | None,
) -> Company:
    if db.scalar(select(CompanyMember).where(CompanyMember.user_id == user.id, CompanyMember.role == MemberRole.owner)):
        raise Conflict("You already own a company. Team invitations are planned; see KNOWN_LIMITATIONS.")
    domain = (email_domain or "").strip().lower() or None
    if domain and not re.fullmatch(r"(?=.{3,253}$)([a-z0-9-]+\.)+[a-z]{2,}", domain):
        raise ValidationFailed("Email domain is invalid.", details={"field": "email_domain"})
    company = Company(
        name=name.strip(),
        slug=slugify_company(name),
        website=website,
        email_domain=domain,
        description=description,
        industry=industry,
        size_range=size_range,
        headquarters=headquarters,
        created_by_id=user.id,
    )
    company.members.append(CompanyMember(user_id=user.id, role=MemberRole.owner))
    db.add(company)
    db.flush()
    audit(db, "company.created", actor_id=user.id, target_type="company", target_id=company.id)
    db.commit()
    return company


def request_verification(
    db: Session, user: User, company_id: uuid.UUID, evidence_note: str | None
) -> CompanyVerificationRecord:
    member = require_member(db, user, company_id, write=True)
    if member.role != MemberRole.owner:
        raise Forbidden("Only company owners can request verification.")
    company = db.get(Company, company_id)
    assert company is not None
    if company.verification_status in (VerificationStatus.verified, VerificationStatus.pending):
        raise Conflict(f"Company verification is already {company.verification_status.value}.")
    if company.verification_status == VerificationStatus.suspended:
        raise Forbidden("This company is suspended. Contact support.")

    user_domain = user.email.rsplit("@", 1)[-1].lower()
    signals = {
        "requester_email_verified": user.email_verified_at is not None,
        "company_domain": company.email_domain,
        "requester_email_domain_matches": bool(company.email_domain) and user_domain == company.email_domain,
        "requester_uses_free_mailbox": user_domain in FREE_EMAIL_DOMAINS,
        "website_domain_matches": bool(
            company.website and company.email_domain and company.email_domain in (company.website or "").lower()
        ),
    }
    status = VerificationStatus.pending
    method = "manual_review"
    # Domain match is ONE signal; automatic approval is opt-in by configuration and never the default.
    if (
        get_settings().auto_verify_company_domain_match
        and signals["requester_email_domain_matches"]
        and signals["requester_email_verified"]
        and not signals["requester_uses_free_mailbox"]
    ):
        status, method = VerificationStatus.verified, "email_domain_signal"
    record = CompanyVerificationRecord(
        company_id=company.id,
        requested_by_id=user.id,
        status=status,
        method=method,
        signals=signals,
        evidence_note=evidence_note,
    )
    db.add(record)
    company.verification_status = status
    if status == VerificationStatus.verified:
        company.verified_at = utcnow()
    audit(
        db,
        "company.verification_requested",
        actor_id=user.id,
        target_type="company",
        target_id=company.id,
        metadata={"method": method, "status": status.value},
    )
    db.commit()
    return record


def decide_verification(
    db: Session, admin: User, company_id: uuid.UUID, *, approve: bool, reason: str | None
) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise NotFound("Company not found.")
    record = db.scalar(
        select(CompanyVerificationRecord)
        .where(
            CompanyVerificationRecord.company_id == company_id,
            CompanyVerificationRecord.status == VerificationStatus.pending,
        )
        .order_by(CompanyVerificationRecord.created_at.desc())
    )
    if record is None:
        raise Conflict("There is no pending verification request for this company.")
    new_status = VerificationStatus.verified if approve else VerificationStatus.rejected
    record.status = new_status
    record.reviewed_by_id = admin.id
    record.reviewed_at = utcnow()
    record.decision_reason = reason
    company.verification_status = new_status
    company.verified_at = utcnow() if approve else None
    audit(
        db,
        "admin.company_verification_decided",
        actor_id=admin.id,
        target_type="company",
        target_id=company.id,
        metadata={"approved": approve},
    )
    owners = db.scalars(
        select(CompanyMember.user_id).where(
            CompanyMember.company_id == company.id, CompanyMember.role == MemberRole.owner
        )
    ).all()
    for owner_id in owners:
        notify(
            db,
            owner_id,
            kind="company_verification",
            title=f"Company verification {'approved' if approve else 'not approved'}",
            body=(
                f"{company.name} is now verified and can publish jobs."
                if approve
                else f"Verification for {company.name} was not approved. {reason or ''}"
            ).strip(),
            dedupe_key=f"company_verification:{record.id}",
            link="/employer/company",
        )
    db.commit()
    return company
