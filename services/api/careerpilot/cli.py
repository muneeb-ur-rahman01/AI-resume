"""Operational CLI.

python -m careerpilot.cli seed-skills            # load/refresh the skills taxonomy (idempotent)
python -m careerpilot.cli create-admin EMAIL NAME  # prompts for a password; the only way to create admins
"""

from __future__ import annotations

import getpass
import os
import sys

from sqlalchemy import select

from careerpilot.ai.skills import slugify
from careerpilot.ai.taxonomy_data import SKILLS
from careerpilot.db import session_factory, utcnow
from careerpilot.models import Role, SkillTaxonomy, User, UserCredential, UserRole
from careerpilot.security.passwords import hash_password, password_problems


def seed_skills() -> int:
    db = session_factory()()
    added = 0
    try:
        for name, category, aliases in SKILLS:
            slug = slugify(name)
            row = db.scalar(select(SkillTaxonomy).where(SkillTaxonomy.slug == slug))
            if row is None:
                db.add(SkillTaxonomy(canonical_name=name, slug=slug, category=category, aliases=aliases))
                added += 1
            else:
                row.aliases = sorted(set(row.aliases or []) | set(aliases))
        db.commit()
    finally:
        db.close()
    return added


def create_admin(email: str, name: str, password: str) -> None:
    # Same validation as the API's EmailStr, so an admin is never created with an address that cannot sign in.
    from email_validator import EmailNotValidError, validate_email

    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise SystemExit(f"Invalid email address: {exc}") from exc
    problems = password_problems(password, email=email, name=name)
    if problems:
        raise SystemExit("; ".join(problems))
    db = session_factory()()
    try:
        email = email.strip().lower()
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("A user with this email already exists.")
        user = User(email=email, full_name=name, email_verified_at=utcnow())
        user.roles.append(UserRole(role=Role.admin))
        user.credential = UserCredential(password_hash=hash_password(password), password_changed_at=utcnow())
        db.add(user)
        from careerpilot.services.audit import audit

        db.flush()
        audit(db, "admin.created_via_cli", actor_id=None, target_type="user", target_id=user.id)
        db.commit()
    finally:
        db.close()


def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit(__doc__)
    cmd = argv[0]
    if cmd == "seed-skills":
        print(f"Added {seed_skills()} skills.")
    elif cmd == "create-admin" and len(argv) == 3:
        # Non-interactive use (CI, e2e): read the password from an environment variable, never from argv,
        # so it does not appear in shell history or process listings.
        pw = os.environ.get("CAREERPILOT_ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
        if "CAREERPILOT_ADMIN_PASSWORD" not in os.environ and pw != getpass.getpass("Repeat password: "):
            raise SystemExit("Passwords do not match.")
        create_admin(argv[1], argv[2], pw)
        print("Admin created.")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
