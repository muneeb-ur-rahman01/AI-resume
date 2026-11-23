"""URL validation helpers: safe user-supplied links and SSRF-resistant outbound destination checks."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from careerpilot.errors import ValidationFailed


def validate_public_http_url(url: str, *, field: str = "url") -> str:
    """Validate a URL that will be displayed as a link (not fetched by the server)."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValidationFailed(f"{field} must be an http(s) URL.", details={"field": field})
    if parsed.username or parsed.password:
        raise ValidationFailed(f"{field} must not contain credentials.", details={"field": field})
    if len(url) > 500:
        raise ValidationFailed(f"{field} is too long.", details={"field": field})
    return url.strip()


def is_private_address(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True  # unresolvable: treat as unsafe
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        ):
            return True
    return False


def assert_safe_outbound_url(url: str, *, allowed_hosts: set[str] | None = None) -> str:
    """Guard for any server-side fetch: https only, optional host allowlist, no private/internal ranges.

    Callers must also disable redirects (or re-check every hop) when fetching.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValidationFailed("Only https URLs are allowed.")
    host = parsed.hostname.lower()
    if allowed_hosts is not None and host not in allowed_hosts:
        raise ValidationFailed("Destination host is not allowed.")
    if is_private_address(host):
        raise ValidationFailed("Destination resolves to a private or internal address.")
    return url


def safe_relative_redirect(path: str | None, default: str = "/") -> str:
    """Only allow same-site relative redirects such as `/dashboard` (blocks `//evil.com` and schemes)."""
    if not path or not path.startswith("/") or path.startswith("//") or "\\" in path:
        return default
    return path
