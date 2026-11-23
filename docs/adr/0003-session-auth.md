# ADR 0003: Server-side sessions in HttpOnly cookies, same-origin API

- Status: Accepted (2026-11-17)

## Decision

- Opaque random session tokens in an `HttpOnly; SameSite=Lax` cookie; the server stores SHA-256 hashes in
  `user_sessions`, with absolute and idle expiry.
- A per-session CSRF token, readable by the SPA via a separate cookie, must be echoed in `X-CSRF-Token` on unsafe
  methods. Its hash is bound to the session. Origin allow-listing adds defense in depth.
- The browser calls the API through the Next.js origin (`/api/v1` rewrite), so cookies are first-party and CORS
  is not needed in normal use.
- Login requires a verified email.

## Alternatives rejected

JWT access/refresh tokens in local storage (XSS exposure, hard revocation); JWT in cookies (revocation still needs
server state, so no benefit here).

## Consequences

Instant revocation (logout, password change, suspension) and a simple security model. Each request does one
indexed session lookup.
