"""/auth: registration, verification, login/logout, sessions, password reset."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from careerpilot.api import schemas as s
from careerpilot.api.deps import AuthContext, client_key, get_auth, ip_prefix
from careerpilot.config import get_settings
from careerpilot.db import get_db
from careerpilot.errors import NotFound
from careerpilot.models import Role, UserSession
from careerpilot.security import rate_limit as rl
from careerpilot.services import auth as auth_service
from careerpilot.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])
GENERIC_REGISTER = "If this email can be registered, we sent a verification link. Check your inbox."
GENERIC_RESET = "If an account exists for this email, we sent a password reset link."


def _set_cookies(response: Response, token: str, csrf: str) -> None:
    cfg = get_settings()
    max_age = cfg.session_ttl_hours * 3600
    response.set_cookie(
        cfg.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite="lax",
        path="/",
    )
    # Readable by the SPA so it can echo it in the X-CSRF-Token header (double-submit bound to the session).
    response.set_cookie(
        cfg.csrf_cookie_name, csrf, max_age=max_age, httponly=False, secure=cfg.cookie_secure, samesite="lax", path="/"
    )


def _clear_cookies(response: Response) -> None:
    cfg = get_settings()
    response.delete_cookie(cfg.session_cookie_name, path="/")
    response.delete_cookie(cfg.csrf_cookie_name, path="/")


@router.post("/register", status_code=status.HTTP_202_ACCEPTED, response_model=s.Message)
def register(body: s.RegisterIn, request: Request, db: Session = Depends(get_db)) -> s.Message:
    rl.get_rate_limiter().hit(rl.REGISTER_IP, client_key(request))
    auth_service.register(
        db,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        role=Role(body.role),
        ai_processing_consent=body.ai_processing_consent,
    )
    return s.Message(message=GENERIC_REGISTER)


@router.post("/verify-email", response_model=s.Message)
def verify_email(body: s.TokenIn, request: Request, db: Session = Depends(get_db)) -> s.Message:
    rl.get_rate_limiter().hit(rl.VERIFY_EMAIL, client_key(request))
    auth_service.verify_email(db, body.token)
    return s.Message(message="Your email address is verified. You can now sign in.")


@router.post("/resend-verification", status_code=202, response_model=s.Message)
def resend_verification(body: s.EmailIn, request: Request, db: Session = Depends(get_db)) -> s.Message:
    limiter = rl.get_rate_limiter()
    limiter.hit(rl.RESEND_VERIFICATION, client_key(request))
    limiter.hit(rl.RESEND_VERIFICATION, f"email:{body.email.lower()}")
    auth_service.resend_verification(db, body.email)
    return s.Message(message="If the account exists and is unverified, we sent a new link.")


@router.post("/login", response_model=s.MeOut)
def login(body: s.LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> s.MeOut:
    rl.get_rate_limiter().hit(rl.LOGIN_IP, client_key(request))
    issued = auth_service.login(
        db,
        email=body.email,
        password=body.password,
        user_agent=request.headers.get("user-agent"),
        ip_prefix=ip_prefix(request),
    )
    _set_cookies(response, issued.token, issued.csrf_token)
    user = auth_service.resolve_session(db, issued.token)
    assert user is not None
    u = user[0]
    return s.MeOut(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        roles=sorted(u.role_names),
        email_verified=u.email_verified_at is not None,
        csrf_token=issued.csrf_token,
    )


@router.post("/logout", response_model=s.Message)
def logout(response: Response, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> s.Message:
    auth_service.revoke_session(db, ctx.session)
    _clear_cookies(response)
    return s.Message(message="Signed out.")


@router.get("/me", response_model=s.MeOut)
def me(ctx: AuthContext = Depends(get_auth)) -> s.MeOut:
    u = ctx.user
    return s.MeOut(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        roles=sorted(u.role_names),
        email_verified=u.email_verified_at is not None,
    )


@router.get("/sessions", response_model=list[s.SessionOut])
def list_sessions(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> list[s.SessionOut]:
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == ctx.user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_seen_at.desc())
    ).all()
    return [s.SessionOut.model_validate(r).model_copy(update={"current": r.id == ctx.session.id}) for r in rows]


@router.delete("/sessions/{session_id}", response_model=s.Message)
def revoke_session(
    session_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> s.Message:
    target = db.get(UserSession, session_id)
    if target is None or target.user_id != ctx.user.id:
        raise NotFound("Session not found.")
    auth_service.revoke_session(db, target)
    audit(db, "auth.session_revoked", actor_id=ctx.user.id, target_type="session", target_id=session_id)
    db.commit()
    return s.Message(message="Session revoked.")


@router.post("/sessions/revoke-others", response_model=s.Message)
def revoke_others(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> s.Message:
    count = auth_service.revoke_all_sessions(db, ctx.user.id, except_id=ctx.session.id)
    audit(
        db,
        "auth.sessions_revoked",
        actor_id=ctx.user.id,
        target_type="user",
        target_id=ctx.user.id,
        metadata={"count": count},
    )
    db.commit()
    return s.Message(message=f"Signed out {count} other session(s).")


@router.post("/forgot-password", status_code=202, response_model=s.Message)
def forgot_password(body: s.EmailIn, request: Request, db: Session = Depends(get_db)) -> s.Message:
    limiter = rl.get_rate_limiter()
    limiter.hit(rl.PASSWORD_RESET, client_key(request))
    limiter.hit(rl.PASSWORD_RESET, f"email:{body.email.lower()}")
    auth_service.request_password_reset(db, body.email)
    return s.Message(message=GENERIC_RESET)


@router.post("/reset-password", response_model=s.Message)
def reset_password(body: s.ResetPasswordIn, request: Request, db: Session = Depends(get_db)) -> s.Message:
    rl.get_rate_limiter().hit(rl.PASSWORD_RESET, client_key(request))
    auth_service.reset_password(db, body.token, body.new_password)
    return s.Message(message="Your password was reset. Sign in with your new password.")


@router.post("/change-password", response_model=s.Message)
def change_password(
    body: s.ChangePasswordIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> s.Message:
    auth_service.change_password(db, ctx.user, ctx.session, body.current_password, body.new_password)
    return s.Message(message="Password changed. Other sessions were signed out.")
