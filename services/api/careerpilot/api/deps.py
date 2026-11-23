"""Request dependencies: authentication, CSRF/origin checks and role-based authorization."""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from careerpilot.config import get_settings
from careerpilot.db import get_db
from careerpilot.errors import Forbidden, Unauthorized
from careerpilot.models import Role, User, UserSession
from careerpilot.security.tokens import tokens_match
from careerpilot.services.auth import resolve_session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def ip_prefix(request: Request) -> str | None:
    """Truncated client IP (IPv4 /24, IPv6 /48) for abuse monitoring without storing full addresses."""
    host = request.client.host if request.client else None
    if not host:
        return None
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return None
    prefix = 24 if addr.version == 4 else 48
    return str(ipaddress.ip_network(f"{host}/{prefix}", strict=False))


def client_key(request: Request) -> str:
    return ip_prefix(request) or "unknown"


def check_origin(request: Request) -> None:
    """Reject cross-site state-changing requests whose Origin is not allow-listed (defense in depth with
    SameSite cookies and the CSRF token)."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if not origin:
        return
    s = get_settings()
    allowed = {o.rstrip("/") for o in s.cors_origins} | {s.frontend_url.rstrip("/")}
    req_origin = f"{request.url.scheme}://{request.url.netloc}"
    parsed = urlparse(origin)
    if origin.rstrip("/") not in allowed and f"{parsed.scheme}://{parsed.netloc}" != req_origin:
        raise Forbidden("Cross-site request blocked.", code="origin_not_allowed")


@dataclass
class AuthContext:
    user: User
    session: UserSession


def get_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    s = get_settings()
    token = request.cookies.get(s.session_cookie_name)
    if not token:
        raise Unauthorized("Sign in to continue.")
    resolved = resolve_session(db, token)
    if resolved is None:
        raise Unauthorized("Your session has expired. Please sign in again.", code="session_expired")
    user, session = resolved
    if request.method not in SAFE_METHODS:
        check_origin(request)
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not tokens_match(csrf, session.csrf_hash):
            raise Forbidden("Missing or invalid CSRF token.", code="csrf_failed")
    return AuthContext(user, session)


def current_user(ctx: AuthContext = Depends(get_auth)) -> User:
    return ctx.user


def require_role(role: Role) -> Callable[..., User]:
    def dependency(ctx: AuthContext = Depends(get_auth)) -> User:
        if not ctx.user.has_role(role):
            raise Forbidden("You do not have permission to access this resource.")
        return ctx.user

    return dependency


candidate_user = require_role(Role.candidate)
employer_user = require_role(Role.employer)
admin_user = require_role(Role.admin)
