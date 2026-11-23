"""Authentication, verification, sessions, CSRF, rate limiting and enumeration protection."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from careerpilot.db import utcnow
from careerpilot.models import EmailVerificationToken, UserSession
from tests.conftest import PASSWORD, ApiClient, last_token, outbox, register_verified


def _register(c: ApiClient, email: str, role: str = "candidate", password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return c.post(
        "/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Pat Doe", "role": role}
    )


def test_register_verify_login_logout(app) -> None:  # type: ignore[no-untyped-def]
    c = ApiClient(app)
    assert _register(c, "pat@example.org").status_code == 202
    r = c.post("/api/v1/auth/login", json={"email": "pat@example.org", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_not_verified"
    token = last_token("verify-email", "pat@example.org")
    assert c.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    # single use
    r = c.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_token"
    r = c.post("/api/v1/auth/login", json={"email": "PAT@example.org", "password": PASSWORD})
    assert r.status_code == 200
    assert "cp_session" in r.cookies and r.json()["roles"] == ["candidate"]
    set_cookie = r.headers.get_list("set-cookie")
    assert any("cp_session" in h and "HttpOnly" in h and "SameSite=lax" in h for h in set_cookie)
    assert c.get("/api/v1/auth/me").status_code == 200
    assert c.post("/api/v1/auth/logout").status_code == 200
    assert c.get("/api/v1/auth/me").status_code == 401


def test_registration_does_not_reveal_existing_accounts(app) -> None:  # type: ignore[no-untyped-def]
    c = ApiClient(app)
    first = _register(c, "dupe@example.org")
    second = _register(c, "dupe@example.org")
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert "sign-up attempt" in outbox()[-1].subject


def test_admin_role_cannot_be_self_assigned(app) -> None:  # type: ignore[no-untyped-def]
    r = _register(ApiClient(app), "evil@example.org", role="admin")
    assert r.status_code == 422


def test_weak_password_rejected(app) -> None:  # type: ignore[no-untyped-def]
    r = _register(ApiClient(app), "weak@example.org", password="password1234")
    assert r.status_code == 422 and "password" in r.json()["error"]["details"]


def test_expired_verification_token(app, db) -> None:  # type: ignore[no-untyped-def]
    c = ApiClient(app)
    _register(c, "late@example.org")
    token = last_token("verify-email", "late@example.org")
    row = db.scalar(select(EmailVerificationToken))
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert c.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
    assert c.post("/api/v1/auth/verify-email", json={"token": "x" * 43}).status_code == 400


def test_login_errors_are_generic_and_lock_out(app) -> None:  # type: ignore[no-untyped-def]
    user = register_verified(app, "candidate", email="lock@example.org")
    c = ApiClient(app)
    unknown = c.post("/api/v1/auth/login", json={"email": "nobody@example.org", "password": "whatever-password"})
    wrong = c.post("/api/v1/auth/login", json={"email": "lock@example.org", "password": "wrong-password-123"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]
    for _ in range(10):
        c.post("/api/v1/auth/login", json={"email": "lock@example.org", "password": "wrong-password-123"})
    locked = c.post("/api/v1/auth/login", json={"email": "lock@example.org", "password": PASSWORD})
    assert locked.status_code == 429
    assert user.get("/api/v1/auth/me").status_code == 200  # existing sessions unaffected


def test_csrf_required_for_state_changes(candidate) -> None:  # type: ignore[no-untyped-def]
    r = candidate.c.put("/api/v1/candidate/profile", json={"headline": "No CSRF"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = candidate.c.put("/api/v1/candidate/profile", json={"headline": "Bad"}, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403
    assert candidate.put("/api/v1/candidate/profile", json={"headline": "With CSRF"}).status_code == 200


def test_cross_origin_state_change_blocked(candidate) -> None:  # type: ignore[no-untyped-def]
    r = candidate.put("/api/v1/candidate/profile", json={"headline": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "origin_not_allowed"


def test_password_reset_flow_single_use_and_revokes_sessions(app) -> None:  # type: ignore[no-untyped-def]
    user = register_verified(app, "candidate", email="reset@example.org")
    c = ApiClient(app)
    assert c.post("/api/v1/auth/forgot-password", json={"email": "reset@example.org"}).status_code == 202
    assert c.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.org"}).status_code == 202
    token = last_token("reset-password", "reset@example.org")
    new_pw = "brand new passphrase 2026"
    assert c.post("/api/v1/auth/reset-password", json={"token": token, "new_password": new_pw}).status_code == 200
    assert c.post("/api/v1/auth/reset-password", json={"token": token, "new_password": new_pw}).status_code == 400
    assert user.get("/api/v1/auth/me").status_code == 401  # old session revoked
    assert c.post("/api/v1/auth/login", json={"email": "reset@example.org", "password": new_pw}).status_code == 200


def test_session_listing_and_revocation(app) -> None:  # type: ignore[no-untyped-def]
    a = register_verified(app, "candidate", email="multi@example.org")
    b = ApiClient(app)
    assert b.post("/api/v1/auth/login", json={"email": "multi@example.org", "password": PASSWORD}).status_code == 200
    sessions = a.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    assert a.post("/api/v1/auth/sessions/revoke-others").status_code == 200
    assert b.get("/api/v1/auth/me").status_code == 401
    assert a.get("/api/v1/auth/me").status_code == 200


def test_rate_limit_on_registration(app) -> None:  # type: ignore[no-untyped-def]
    c = ApiClient(app)
    codes = [_register(c, f"rl{i}@example.org").status_code for i in range(12)]
    assert codes[:10] == [202] * 10 and codes[-1] == 429


def test_session_token_stored_hashed(app, db) -> None:  # type: ignore[no-untyped-def]
    c = register_verified(app, "candidate", email="hash@example.org")
    token = c.c.cookies.get("cp_session")
    stored = db.scalars(select(UserSession.token_hash)).all()
    assert token not in stored and all(len(h) == 64 for h in stored)


def test_error_responses_are_safe(app) -> None:  # type: ignore[no-untyped-def]
    c = ApiClient(app)
    r = c.get("/api/v1/jobs/not-a-uuid")
    body = r.json()
    assert r.status_code == 422 and body["error"]["request_id"]
    assert "Traceback" not in r.text and "sqlalchemy" not in r.text.lower()
    assert r.headers["x-content-type-options"] == "nosniff"
