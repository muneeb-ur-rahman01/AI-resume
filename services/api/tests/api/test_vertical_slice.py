"""End-to-end API journey for the first vertical slice (mock AI provider, inline tasks)."""

from __future__ import annotations

import uuid

from tests.conftest import JOB_PAYLOAD, ApiClient, make_docx, make_pdf, outbox, setup_company_and_job


def _upload(candidate: ApiClient, data: bytes, name: str = "ada-cv.pdf") -> dict:  # type: ignore[type-arg]
    r = candidate.post("/api/v1/candidate/resumes", files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 201, r.text
    return r.json()


def test_full_candidate_employer_journey(candidate, employer, admin) -> None:  # type: ignore[no-untyped-def]
    # 1. Employer: company -> verification -> job -> publish
    _company_id, job_id = setup_company_and_job(employer, admin)

    # 2. Candidate uploads resume; inline task processes it.
    resume = _upload(candidate, make_pdf())
    detail = candidate.get(f"/api/v1/candidate/resumes/{resume['id']}").json()
    assert detail["status"] == "completed", detail
    assert detail["model_name"] == "mock-deterministic-v1"  # clearly labeled mock output
    facts = detail["facts"]
    skill_facts = {f["value"]["name"]: f for f in facts if f["fact_type"] == "skill"}
    assert {"Python", "PostgreSQL", "FastAPI"} <= set(skill_facts)
    assert all(f["status"] in ("stated", "inferred") for f in facts)  # nothing auto-confirmed

    # Profile is unchanged until the candidate confirms.
    assert candidate.get("/api/v1/candidate/profile").json()["skills"] == []

    # 3. Candidate confirms facts (rejects one) and corrects data.
    accept = [
        f["id"]
        for f in facts
        if f["fact_type"] in ("skill", "experience", "education", "summary") and f["value"].get("name") != "Git"
    ]
    reject = [skill_facts["Git"]["id"]]
    r = candidate.post(f"/api/v1/candidate/resumes/{resume['id']}/review", json={"accept": accept, "reject": reject})
    assert r.status_code == 200 and r.json()["applied"] > 5
    profile = candidate.get("/api/v1/candidate/profile").json()
    skill_names = {s["name"] for s in profile["skills"]}
    assert "Python" in skill_names and "Git" not in skill_names
    assert len(profile["experiences"]) == 2 and profile["years_experience"] and profile["years_experience"] > 4
    r = candidate.put(
        "/api/v1/candidate/profile", json={"headline": "Senior Backend Engineer", "location_country": "US"}
    )
    assert r.status_code == 200
    r = candidate.put(
        "/api/v1/candidate/preferences",
        json={
            "desired_titles": ["Backend Engineer"],
            "work_arrangements": ["remote"],
            "min_salary": 130000,
            "salary_currency": "USD",
        },
    )
    assert r.status_code == 200, r.text

    # 4. Recommendations with explanation
    recs = candidate.get("/api/v1/candidate/recommendations").json()
    assert recs["profile_ready"] and recs["items"], recs
    top = recs["items"][0]
    assert top["job"]["id"] == job_id
    match = top["match"]
    assert match["eligibility"] == "eligible"
    assert set(match["explanation"]["matched_required"]) == {"Python", "PostgreSQL", "FastAPI"}
    assert "Terraform" in match["explanation"]["missing_preferred"]
    assert 0 <= match["relevance_score"] <= 100

    # 5. Cover letter generation (grounded) + manual edit
    r = candidate.post(f"/api/v1/candidate/jobs/{job_id}/cover-letters/generate", json={"tone": "professional"})
    assert r.status_code == 201, r.text
    generated = r.json()
    assert "Acme Corp" in generated["content"] and generated["generated_by"] == "mock-deterministic-v1"
    edited = generated["content"] + "\n\nP.S. I also led a team of 40 engineers."
    r = candidate.post(f"/api/v1/candidate/jobs/{job_id}/cover-letters", json={"content": edited})
    assert r.status_code == 201
    draft = r.json()
    assert draft["version_number"] == 2
    assert any(c["type"] == "number" for c in draft["unsupported_claims"])

    # 6. Preview, then candidate-approved submission (idempotent)
    preview = candidate.get(f"/api/v1/candidate/applications/preview?job_id={job_id}").json()
    assert preview["already_applied"] is False and preview["resumes"]
    unconfirmed = candidate.post(
        "/api/v1/candidate/applications",
        json={"job_id": job_id, "resume_id": resume["id"], "confirm": False},
        headers={"Idempotency-Key": "k-unconfirmed-1"},
    )
    assert unconfirmed.status_code == 422
    body = {"job_id": job_id, "resume_id": resume["id"], "cover_letter_draft_id": draft["id"], "confirm": True}
    key = {"Idempotency-Key": f"apply-{uuid.uuid4()}"}
    first = candidate.post("/api/v1/candidate/applications", json=body, headers=key)
    assert first.status_code == 201, first.text
    app_id = first.json()["id"]
    replay = candidate.post("/api/v1/candidate/applications", json=body, headers=key)
    assert replay.status_code == 200 and replay.json()["id"] == app_id
    dup = candidate.post("/api/v1/candidate/applications", json=body, headers={"Idempotency-Key": "another-key-123"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_application"
    assert first.json()["status"] == "submitted"
    assert any("Application submitted" in m.subject for m in outbox())

    # 7. Employer reviews; viewing is recorded; status update notifies candidate
    rows = employer.get(f"/api/v1/employer/jobs/{job_id}/applications").json()
    assert rows["total"] == 1 and rows["items"][0]["candidate_name"] == "Ada Candidate"
    detail = employer.get(f"/api/v1/employer/applications/{app_id}").json()
    assert detail["first_viewed_at"] is not None and detail["has_resume"]
    assert detail["documents"][0]["kind"] == "cover_letter"
    resume_dl = employer.get(f"/api/v1/employer/applications/{app_id}/resume")
    assert resume_dl.status_code == 200 and resume_dl.content.startswith(b"%PDF")
    bad = employer.post(f"/api/v1/employer/applications/{app_id}/status", json={"status": "hired"})
    assert bad.status_code == 409
    ok = employer.post(
        f"/api/v1/employer/applications/{app_id}/status", json={"status": "shortlisted", "note": "Strong backend match"}
    )
    assert ok.status_code == 200 and ok.json()["status"] == "shortlisted"

    # 8. Candidate sees the confirmed status; employer-only note is not exposed
    mine = candidate.get(f"/api/v1/candidate/applications/{app_id}").json()
    assert mine["status"] == "shortlisted"
    assert [h["to_status"] for h in mine["history"]] == ["submitted", "shortlisted"]
    assert "note" not in mine["history"][-1]
    notes = candidate.get("/api/v1/notifications").json()["items"]
    assert any("Application update" in n["title"] for n in notes)

    # 9. Candidate withdraws; export and deletion
    assert candidate.post(f"/api/v1/candidate/applications/{app_id}/withdraw").status_code == 200
    export = candidate.get("/api/v1/privacy/export").json()
    assert export["account"]["full_name"] == "Ada Candidate" and export["applications"]
    r = candidate.post("/api/v1/privacy/delete-account", json={"password": "wrong password value"})
    assert r.status_code == 401
    r = candidate.post("/api/v1/privacy/delete-account", json={"password": "correct horse battery staple"})
    assert r.status_code == 200
    assert candidate.get("/api/v1/auth/me").status_code == 401
    assert employer.get(f"/api/v1/employer/applications/{app_id}").status_code == 404


def test_docx_upload_and_retry(candidate) -> None:  # type: ignore[no-untyped-def]
    resume = _upload(candidate, make_docx(), "cv.docx")
    detail = candidate.get(f"/api/v1/candidate/resumes/{resume['id']}").json()
    assert detail["status"] == "completed" and detail["extraction_method"] == "docx"
    r = candidate.post(f"/api/v1/candidate/resumes/{resume['id']}/retry")
    assert r.status_code == 200 and r.json()["status"] == "completed"


def test_without_ai_consent_uses_basic_extraction_and_blocks_generation(app, employer, admin) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import register_verified

    cand = register_verified(app, "candidate", consent=False)
    resume = _upload(cand, make_pdf())
    detail = cand.get(f"/api/v1/candidate/resumes/{resume['id']}").json()
    assert detail["status"] == "completed" and "privacy settings" in detail["status_detail"]
    assert all(f["method"] == "heuristic" for f in detail["facts"])
    _, job_id = setup_company_and_job(employer, admin)
    cand.post("/api/v1/candidate/skills", json={"name": "Python"})
    r = cand.post(f"/api/v1/candidate/jobs/{job_id}/cover-letters/generate", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "consent_required"


def test_job_search_works_without_ai(employer, admin, app) -> None:  # type: ignore[no-untyped-def]
    setup_company_and_job(employer, admin)
    c = ApiClient(app)
    res = c.get("/api/v1/jobs?q=python&work_arrangement=remote&skill=postgresql").json()
    assert res["total"] == 1 and res["items"][0]["company"]["name"] == "Acme Corp"
    assert c.get("/api/v1/jobs?q=nonexistent-zzz").json()["total"] == 0


def test_unverified_company_cannot_publish(employer) -> None:  # type: ignore[no-untyped-def]
    r = employer.post("/api/v1/employer/companies", json={"name": "Shady LLC"})
    company_id = r.json()["id"]
    job = employer.post(f"/api/v1/employer/companies/{company_id}/jobs", json=JOB_PAYLOAD).json()
    r = employer.post(f"/api/v1/employer/jobs/{job['id']}/status", json={"status": "published"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "company_not_verified"


def test_job_parse_is_advisory_and_not_saved(employer) -> None:  # type: ignore[no-untyped-def]
    text = (
        "Requirements:\n- 5+ years of Python\n- PostgreSQL and Docker\nNice to have:\n- Kubernetes\n"
        "This is a remote, full-time role."
    )
    r = employer.post("/api/v1/employer/jobs/parse", json={"text": text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_mock"] is True
    assert "Python" in body["required_skills"] and "Kubernetes" in body["preferred_skills"]
    assert body["min_experience_years"] == 5 and body["work_arrangement"] == "remote"


def test_external_job_returns_link_instead_of_submitting(candidate, employer, admin) -> None:  # type: ignore[no-untyped-def]
    payload = dict(JOB_PAYLOAD, external_apply_url="https://careers.example.org/apply/123")
    _, job_id = setup_company_and_job(employer, admin, payload)
    r = candidate.post(
        "/api/v1/candidate/applications",
        json={"job_id": job_id, "confirm": True},
        headers={"Idempotency-Key": "external-key-1"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["details"]["external_apply_url"].startswith("https://careers.example.org")


def test_job_lifecycle_transitions(employer, admin) -> None:  # type: ignore[no-untyped-def]
    _, job_id = setup_company_and_job(employer, admin)
    assert employer.post(f"/api/v1/employer/jobs/{job_id}/status", json={"status": "draft"}).status_code == 409
    assert employer.post(f"/api/v1/employer/jobs/{job_id}/status", json={"status": "paused"}).status_code == 200
    job = employer.get(f"/api/v1/employer/jobs/{job_id}").json()
    stale = dict(JOB_PAYLOAD, title="Renamed", expected_version=job["version"] - 1)
    assert employer.put(f"/api/v1/employer/jobs/{job_id}", json=stale).status_code == 409
    fresh = dict(JOB_PAYLOAD, title="Renamed", expected_version=job["version"])
    assert employer.put(f"/api/v1/employer/jobs/{job_id}", json=fresh).status_code == 200
    assert employer.post(f"/api/v1/employer/jobs/{job_id}/status", json={"status": "closed"}).status_code == 200
    assert employer.post(f"/api/v1/employer/jobs/{job_id}/status", json={"status": "published"}).status_code == 409
