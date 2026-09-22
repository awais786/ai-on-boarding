# proxy-auth-middleware — capability spec

Per-app middleware that converts oauth2-proxy's `X-Auth-Request-*` headers into a native authenticated request. Applies to every app behind Traefik ForwardAuth in the FOSS bundle.

## Requirements

### Requirement: Bypass paths SHALL short-circuit before any auth processing

Configured bypass prefixes MUST be honoured at the very top of request handling. No header read, no session check, no logout, no login. Bypass paths have their own auth (god-mode local credentials, instance-admin permissions).

### Requirement: Authenticated sessions with matching or absent proxy identity SHALL short-circuit

If `request.user.is_authenticated` is true and either the proxy header is absent OR its normalised value equals the session user's normalised email, the middleware MUST return the response unchanged. No logout, no new session, no DB write.

Header absence is NOT a logout signal — the X-Auth-Request-* headers are only set on traffic that flowed through Traefik → oauth2-proxy. Absent header means a trusted internal path (celery workers, OPTIONS preflight, direct backend hits at 127.0.0.1, Django test client, etc.).

The comparison MUST apply the same normalisation (lowercase + strip) to **both** sides — the header value AND the session user's email — that the DB lookup uses. Normalising only one side has the same effect as not normalising at all: every case-variant header (e.g. from a Cognito identity claim) falsely registers as a mismatch and kicks the cookie-authed request back to ForwardAuth on every request.

### Requirement: Identity mismatch SHALL flush the existing session immediately

If `request.user.is_authenticated` is true AND the proxy header asserts a non-empty identity that differs from the session user's normalised email, the middleware MUST call the framework's session-flush (session invalidation / logout) BEFORE attempting to resolve or authenticate the incoming user.

The flush MUST happen before any subsequent bail-out path can fire (e.g. the incoming user being marked inactive, or an unresolvable upstream identity). The mismatch flush MUST fire even when the upstream identity cannot be resolved to a local user record (unknown email, auto-register disabled, or a database lookup that returns nil for any other reason) — the upstream header is positive proof that the identity has changed; the absence of a local profile to re-key to does NOT make it safe to keep serving the previous user. The response MUST also expire the browser's local session cookie, not just clear in-flight state, so the next request cannot resurrect the previous user via the surviving cookie alone.

### Requirement: Unauthenticated requests with a valid proxy identity SHALL auto-provision and log in

When no session is present (or after a mismatch flush) and the proxy header carries a non-empty normalised identity, the middleware MUST:

1. Resolve the user via exact-match DB lookup on the normalised email.
2. If the user does not exist, create it with an unusable/random password, mark it as having a verified email, and create any associated profile row.
3. If the resolved user is inactive/disabled, pass through unauthenticated without establishing a session.
4. Otherwise, establish the session for that user.

DB lookup MUST use exact equality, not pattern matching. Wildcards in the proxy header (`%`, `_`) MUST be treated as literal characters in the lookup.

### Requirement: Email normalisation SHALL be applied uniformly

The same normalisation function (lowercase + strip whitespace) MUST be applied to:

1. The proxy header value before any comparison or DB lookup.
2. The session user's `email` field when computing the match comparison.
3. The persisted `User.email` column (canonical lowercase enforced at write).

This prevents case-variant or whitespace-padded headers from creating duplicate users or evading the match short-circuit.

### Requirement: Concurrent creation races SHALL fall back to read

A race between two requests for the same first-time email MAY trigger a uniqueness-constraint error on create. The middleware MUST catch this and re-attempt a plain lookup by email. If the user still does not exist, the original exception MUST be re-raised (do not silently swallow).

### Requirement: email-shape detection on header values SHALL avoid polynomial-backtracking regex

When the middleware decides whether a header value is already email-shaped (and therefore safe to use directly) versus a bare username that needs synthesis against a default email domain, the check MUST NOT use an unanchored or repetition-heavy regex. The standard "email-shape" pattern `^[^\s@]+@[^\s@]+\.[^\s@]+$` is polynomial-backtrack-vulnerable on adversarial input. The middleware MUST use an `indexOf`-based check (or its language equivalent) that runs in O(n).
