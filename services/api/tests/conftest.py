"""Test configuration.

Default tests run against an in-memory SQLite database with the deterministic MOCK AI provider, a
console email sink and local file storage - no network or external services. Tests marked `postgres`
run only when TEST_DATABASE_URL points at a PostgreSQL+pgvector database.
"""

from __future__ import annotations

import io
import os
import re
import tempfile
import uuid
from collections.abc import Iterator

_TMP = tempfile.mkdtemp(prefix="careerpilot-test-")
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": "sqlite:///:memory:",
        "LOCAL_STORAGE_PATH": os.path.join(_TMP, "storage"),
        "LLM_PROVIDER": "mock",
        "EMAIL_PROVIDER": "console",
        "STORAGE_PROVIDER": "local",
        "TASK_MODE": "inline",
        "REDIS_URL": "",
        "FRONTEND_URL": "http://testserver",
        "CORS_ORIGINS": '["http://testserver"]',
    }
)
os.environ.pop("REDIS_URL")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from careerpilot.ai import providers  # noqa: E402
from careerpilot.ai.client import breaker  # noqa: E402
from careerpilot.config import get_settings  # noqa: E402
from careerpilot.db import Base, configure_engine, session_factory  # noqa: E402
from careerpilot.infra import email as email_mod  # noqa: E402
from careerpilot.infra import storage as storage_mod  # noqa: E402
from careerpilot.security.rate_limit import get_rate_limiter  # noqa: E402

PASSWORD = "correct horse battery staple"


# Set TEST_DATABASE_URL (e.g. postgresql+psycopg://...@127.0.0.1:5432/careerpilot_test) to run the whole suite
# against PostgreSQL + pgvector instead of SQLite. The database is wiped between tests.
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(autouse=True)
def _fresh_state() -> Iterator[None]:
    get_settings.cache_clear()
    engine = configure_engine(TEST_DB_URL)
    import careerpilot.models  # noqa: F401

    if engine.dialect.name == "postgresql":
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    email_mod.set_email_provider(email_mod.ConsoleEmailProvider())
    storage_mod.set_storage(None)
    providers.set_providers(None, None)
    breaker.reset()
    get_rate_limiter().clear_memory()
    from careerpilot.ai.skills import invalidate_normalizer_cache

    invalidate_normalizer_cache()
    from careerpilot.cli import seed_skills

    seed_skills()
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db():  # type: ignore[no-untyped-def]
    session = session_factory()()
    yield session
    session.close()


@pytest.fixture
def app():  # type: ignore[no-untyped-def]
    from careerpilot.main import create_app

    return create_app()


def outbox() -> list[email_mod.OutgoingEmail]:
    provider = email_mod.get_email_provider()
    assert isinstance(provider, email_mod.ConsoleEmailProvider)
    return provider.outbox


def last_token(kind: str, to: str) -> str:
    pattern = re.compile(rf"/{kind}\?token=([A-Za-z0-9_\-]+)")
    for msg in reversed(outbox()):
        if msg.to == to and (m := pattern.search(msg.text)):
            return m.group(1)
    raise AssertionError(f"no {kind} email for {to}")


class ApiClient:
    """TestClient wrapper that keeps its own cookie jar and sends the CSRF header automatically."""

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.c = TestClient(app, base_url="http://testserver")
        self.user: dict[str, object] = {}

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        csrf = self.c.cookies.get(get_settings().csrf_cookie_name)
        if csrf:
            headers.setdefault("X-CSRF-Token", csrf)
        return headers

    def get(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.c.get(url, **kw)

    def post(self, url: str, headers: dict[str, str] | None = None, **kw):  # type: ignore[no-untyped-def]
        return self.c.post(url, headers=self._headers(headers), **kw)

    def put(self, url: str, headers: dict[str, str] | None = None, **kw):  # type: ignore[no-untyped-def]
        return self.c.put(url, headers=self._headers(headers), **kw)

    def patch(self, url: str, headers: dict[str, str] | None = None, **kw):  # type: ignore[no-untyped-def]
        return self.c.patch(url, headers=self._headers(headers), **kw)

    def delete(self, url: str, headers: dict[str, str] | None = None, **kw):  # type: ignore[no-untyped-def]
        return self.c.delete(url, headers=self._headers(headers), **kw)


def register_verified(
    app,
    role: str,
    *,
    email: str | None = None,
    name: str = "Test User",  # type: ignore[no-untyped-def]
    consent: bool = True,
) -> ApiClient:
    client = ApiClient(app)
    email = email or f"{role}-{uuid.uuid4().hex[:8]}@example.org"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": name, "role": role, "ai_processing_consent": consent},
    )
    assert r.status_code == 202, r.text
    r = client.post("/api/v1/auth/verify-email", json={"token": last_token("verify-email", email)})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    client.user = r.json() | {"email": email}
    return client


@pytest.fixture
def candidate(app) -> ApiClient:  # type: ignore[no-untyped-def]
    return register_verified(app, "candidate", name="Ada Candidate")


@pytest.fixture
def employer(app) -> ApiClient:  # type: ignore[no-untyped-def]
    return register_verified(
        app, "employer", email=f"hr-{uuid.uuid4().hex[:6]}@acme-corp.example", name="Erin Employer"
    )


@pytest.fixture
def admin(app) -> ApiClient:  # type: ignore[no-untyped-def]
    from careerpilot.cli import create_admin

    email = f"admin-{uuid.uuid4().hex[:6]}@example.org"
    create_admin(email, "Admin Person", PASSWORD)
    client = ApiClient(app)
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return client


RESUME_TEXT = """Ada Candidate
Senior Backend Engineer
ada@example.org | +1 555 010 0000

Summary
Backend engineer focused on Python services, PostgreSQL and cloud infrastructure.

Experience
Senior Backend Engineer, Northwind Systems    Jan 2021 - Present
- Built FastAPI services on AWS with PostgreSQL and Redis
- Introduced Docker and Kubernetes based deployments
Software Engineer, Contoso Labs    Jun 2017 - Dec 2020
- Developed Django applications and REST APIs

Education
University of Example
BSc in Computer Science, 2013 - 2017

Skills
Python, FastAPI, Django, PostgreSQL, Redis, Docker, Kubernetes, AWS, Git
"""


def make_pdf(text: str = RESUME_TEXT) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 750
    for line in text.splitlines():
        c.drawString(50, y, line)
        y -= 14
        if y < 50:
            c.showPage()
            y = 750
    c.save()
    return buf.getvalue()


def make_docx(text: str = RESUME_TEXT) -> bytes:
    import docx

    d = docx.Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


JOB_PAYLOAD = {
    "title": "Senior Python Backend Engineer",
    "description": "We are hiring a backend engineer to build Python APIs with FastAPI and PostgreSQL on AWS. "
    "You will own services end to end.",
    "required_skills": [{"name": "Python"}, {"name": "postgres"}, {"name": "FastAPI"}],
    "preferred_skills": [{"name": "Kubernetes"}, {"name": "Terraform"}],
    "min_experience_years": 4,
    "employment_type": "full_time",
    "work_arrangement": "remote",
    "salary_min": 120000,
    "salary_max": 160000,
    "salary_currency": "USD",
}


def setup_company_and_job(employer: ApiClient, admin: ApiClient, job: dict | None = None) -> tuple[str, str]:  # type: ignore[type-arg]
    domain = str(employer.user["email"]).split("@")[1]
    r = employer.post(
        "/api/v1/employer/companies", json={"name": "Acme Corp", "email_domain": domain, "website": f"https://{domain}"}
    )
    assert r.status_code == 201, r.text
    company_id = r.json()["id"]
    r = employer.post(f"/api/v1/employer/companies/{company_id}/verification", json={"evidence_note": "HR lead"})
    assert r.status_code == 201, r.text
    r = admin.post(f"/api/v1/admin/companies/{company_id}/verification", json={"approve": True})
    assert r.status_code == 200, r.text
    r = employer.post(f"/api/v1/employer/companies/{company_id}/jobs", json=job or JOB_PAYLOAD)
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    r = employer.post(f"/api/v1/employer/jobs/{job_id}/status", json={"status": "published"})
    assert r.status_code == 200, r.text
    return company_id, job_id
