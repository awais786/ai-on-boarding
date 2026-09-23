# Mautic SSO Discovery Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Post-implementation amendment (2026-09-23):** this plan (including Task
> 4's `requirements.txt`/code blocks below) reflects the state as originally
> executed. Two things changed after all 5 tasks completed, per direct
> instruction, and are NOT reflected below — this document stays as the
> historical record rather than being rewritten:
> - `GitHubClient` is no longer reused from `agents/issue-reconciler/` — it
>   was copied into this package's own `mautic_sso_discovery/github_client.py`
>   (see git history: "Give mautic-sso-discovery its own GitHubClient
>   instead of depending on issue-reconciler"), removing the
>   `-e ../issue-reconciler` line from `requirements.txt` and the
>   `from issue_reconciler.client import GitHubClient` imports shown in
>   Tasks 4 and 5's code below.
> - `claude-agent-sdk==0.1.0` (pinned in Task 1's `requirements.txt` below)
>   was upgraded to the real current release, `claude-agent-sdk==0.2.158` —
>   0.1.0 predates a message type (`rate_limit_event`) the current `claude`
>   CLI sends, which crashed a real `discover` run.
> - `discover.py`'s `ClaudeAgentOptions` in Task 3's code below also predates
>   later hardening: a `hooks=` PreToolUse gate enforcing "search before
>   read", a `--model`/`MAUTIC_DISCOVERY_MODEL`-driven `model` parameter, and
>   `tools=[...]` (a real capability restriction) in place of the
>   `allowed_tools`/`disallowed_tools` pair shown below, once 0.2.158 made
>   that possible. The current source is the source of truth for all of
>   these; this document is not.

**Goal:** Build a Claude Agent SDK program that clones a target repo, traces its
current authentication implementation against a fixed, bundled Moneta SSO
contract, writes a Markdown discovery report + integration plan, and — as a
separate, human-gated phase — drafts and creates GitHub issues from that
report.

**Architecture:** One Python package, `agents/mautic-sso-discovery/`, with two
independent CLI subcommands (`discover`, `propose-issues`) backed by two Agent
SDK sessions. `discover` gets read-only tools (`Read`/`Grep`/`Glob`, no
`Bash`/`Write`/`Edit`) over a repo that plain (non-agentic) Python code has
already cloned and made unwritable at the filesystem level before the agent
session starts. `propose-issues` gets no tools at all — the report text is
pasted directly into its prompt — and only plain Python code (reusing
`GitHubClient` from `agents/issue-reconciler/`) talks to GitHub.

**Tech Stack:** Python 3.12, `claude-agent-sdk` (Python), `anyio`, `requests`
(via the reused `GitHubClient`), `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-22-mautic-sso-discovery-agent-design.md`

## Global Constraints

- The Moneta SSO contract is fixed and bundled into the package as static
  files — never fetched from a `--rules-repo` argument at runtime.
- The target repo is a CLI argument (`--target-repo`), never hardcoded, so
  reusing this for a future app means passing a different URL, not changing
  code.
- The agent session that explores the target repo must never be able to
  modify it: this is enforced by (a) the cloned checkout being made
  unwritable (`chmod`) before the agent session starts, and (b) the session
  never being granted a `Write`, `Edit`, or `Bash` tool.
- No GitHub issue gets created until a human has explicitly run the separate
  `propose-issues` command — `discover` never triggers it.
- Every dependency-injectable seam in this plan (the SDK's `query` function,
  the clone/lock-down functions, `GitHubClient`'s transport) follows the same
  pattern already used in `agents/issue-reconciler/issue_reconciler/client.py`
  (`GitHubClient(..., transport=...)`) — a plain parameter with a real default,
  so tests substitute a fake without needing network or API access.

---

## Task 1: Package scaffold + bundled Moneta contract

**Files:**
- Create: `agents/mautic-sso-discovery/pyproject.toml`
- Create: `agents/mautic-sso-discovery/requirements.txt`
- Create: `agents/mautic-sso-discovery/mautic_sso_discovery/__init__.py`
- Create: `agents/mautic-sso-discovery/mautic_sso_discovery/context.py`
- Create: `agents/mautic-sso-discovery/context/authentication.md`
- Create: `agents/mautic-sso-discovery/context/apps-overview.md`
- Create: `agents/mautic-sso-discovery/context/proxy-auth-middleware-spec.md`
- Test: `agents/mautic-sso-discovery/tests/test_context.py`

**Interfaces:**
- Produces: `load_moneta_contract() -> str` — every later task that builds a
  prompt for the `discover` phase calls this.

- [ ] **Step 1: Create the package files**

`agents/mautic-sso-discovery/pyproject.toml`:

```toml
[project]
name = "mautic-sso-discovery"
version = "0.1.0"
requires-python = ">=3.12"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["mautic_sso_discovery*"]
```

`agents/mautic-sso-discovery/requirements.txt`:

```
# Runtime + test tooling for the discovery agent. Not a dependency of the
# Django project - sdd_django_demo/requirements.txt is unchanged by this.
claude-agent-sdk==0.1.0
anyio==4.7.0
requests==2.34.2
python-dotenv==1.0.1
pytest==9.1.1
ruff==0.16.7
-e ../issue-reconciler
```

`agents/mautic-sso-discovery/mautic_sso_discovery/__init__.py`:

```python
```

(empty file — marks the directory as a package)

- [ ] **Step 2: Write the bundled Moneta contract files, copied verbatim from `awais786/sso-rules-moneta`**

`agents/mautic-sso-discovery/context/authentication.md`:

```markdown
# Authentication — mPass OIDC

How auth works behind Plane (and the rest of the FOSS bundle), what TTLs
apply, and how to verify each layer is healthy without log access.

For the formal contract each app must implement, see [`proxy-auth-contract.md`](./proxy-auth-contract.md) and the specs under [`openspec/specs/`](./openspec/specs/).

---

## The auth chain

```
Browser
  ↓
Traefik  ──ForwardAuth──▶  oauth2-proxy  ──▶  mpass-auth-proxy  ──▶  Cognito (mPass)
  ↓
Plane API  (ProxyAuthMiddleware → Django session)
```

Each layer holds its own session/cookie/token with its own TTL. The chain
silently refreshes upstream tokens every hour so the user never sees a
prompt — until either a layer expires past its absolute lifetime, or
something breaks.

---

## Timings & TTLs

| Setting | Value | What it controls | User-visible? |
|---|---|---|---|
| Refresh interval | **1 hour** | How often the system silently renews tokens. If broken, this is when users get kicked out. | Only if it fails |
| oauth2-proxy session cookie | **7 days** | How long the browser carries an active session | Yes — expiry triggers a redirect through Cognito |
| Cognito refresh token | **5 days** | Max idle gap before a real Cognito login is required | Only after this much inactivity |
| Cognito access/id token | **1 hour** | Real validity of the JWT issued by Cognito | No — refreshed silently |
| App-native access session | **7 days** | Inner-layer fallback. Uniform across apps via `SESSION_COOKIE_MAX_AGE_SECONDS`. | No |
| App-native refresh token (where issued) | **14 days** | Twenty, SurfSense, Outline-as-provider only. Via `SESSION_REFRESH_TOKEN_MAX_AGE_SECONDS`. | No |
| Bridge state TTL | **3 minutes** | How long a user has to complete the Cognito login form | Yes — restart required after this |
| Auth code TTL (one-shot) | **60 seconds** | Internal hand-off between mpass-auth-proxy and oauth2-proxy | No |

### Per-app native sessions

Once Traefik's ForwardAuth admits a request, each app maintains its own
session/cookie/JWT. The bundle's `docker-compose.yml` overrides each
app's native default and wires every access-layer env to a single
`SESSION_COOKIE_MAX_AGE_SECONDS` (default `604800` = 7d), and every
refresh-token env (where the app issues one) to
`SESSION_REFRESH_TOKEN_MAX_AGE_SECONDS` (default `1209600` = 14d). So
the access layer expires together across all apps + oauth2-proxy, but
refresh tokens have their own longer lifetime.

| App | Session mechanism | Wiring | Actual deployed lifetime |
|---|---|---|---|
| Plane | Django session cookie (`sessionid`) | `SESSION_COOKIE_AGE` ← `SESSION_COOKIE_MAX_AGE_SECONDS` (7d). `SESSION_SAVE_EVERY_REQUEST` unset → absolute, not sliding | **7d absolute** |
| Outline | JWT in `accessToken` cookie | Expiry **hardcoded to 7 days** in `server/middlewares/authentication.ts:60`, `server/routes/auth/index.ts:47`, `server/utils/authentication.ts:94` (`addDays(new Date(), 7)`). Patched by [Pressingly/outline PR #8](https://github.com/Pressingly/outline/pull/8) — was `addMonths(3)` upstream. `OAUTH_PROVIDER_ACCESS_TOKEN_LIFETIME` / `OAUTH_PROVIDER_REFRESH_TOKEN_LIFETIME` apply only when Outline acts as OAuth provider for *other* services, not user sessions | **7d absolute** (user-facing accessToken cookie) |
| Penpot | `auth-token` cookie (sliding) | `PENPOT_AUTH_TOKEN_COOKIE_MAX_AGE` ← `SESSION_COOKIE_MAX_AGE_SECONDS` (7d); `PENPOT_AUTH_TOKEN_COOKIE_RENEWAL_MAX_AGE` ← `SESSION_COOKIE_REFRESH_SECONDS` (1h) | **7d idle / unlimited if active** — every 1h of activity resets the cookie to now+7d |
| SurfSense | JWT (access + refresh) | `ACCESS_TOKEN_LIFETIME_SECONDS` ← `SESSION_COOKIE_MAX_AGE_SECONDS` (7d); `REFRESH_TOKEN_LIFETIME_SECONDS` ← `SESSION_REFRESH_TOKEN_MAX_AGE_SECONDS` (14d) | **7d access / 14d refresh** (both absolute, JWT) |
| Twenty | JWT (access + refresh) | `ACCESS_TOKEN_EXPIRES_IN` ← `SESSION_COOKIE_MAX_AGE_SECONDS` (7d); `REFRESH_TOKEN_EXPIRES_IN` ← `SESSION_REFRESH_TOKEN_MAX_AGE_SECONDS` (14d) | **7d access / 14d refresh** (both absolute, JWT) |
| oauth2-proxy | `_oauth2_proxy` cookie | `OAUTH2_PROXY_COOKIE_EXPIRE` ← `SESSION_COOKIE_MAX_AGE_SECONDS` (7d, absolute); `OAUTH2_PROXY_COOKIE_REFRESH` ← `SESSION_COOKIE_REFRESH_SECONDS` (1h sliding refresh) | **7d absolute cookie + 1h sliding refresh** |

Three envs control the whole thing:
- `SESSION_COOKIE_MAX_AGE_SECONDS` (default 604800 = 7d) — access cookies / sessions / access tokens
- `SESSION_REFRESH_TOKEN_MAX_AGE_SECONDS` (default 1209600 = 14d) — refresh tokens, where issued
- `SESSION_COOKIE_REFRESH_SECONDS` (default 3600 = 1h) — sliding refresh interval (oauth2-proxy + Penpot)

**Sliding vs absolute:**
- **Absolute** (expiry fixed from issue time): oauth2-proxy (7d), Plane (7d), Outline (7d, hardcoded via fork patch), SurfSense (7d access / 14d refresh), Twenty (7d access / 14d refresh).
- **Sliding** (expiry resets on activity): Penpot — every 1h of use resets the cookie expiry to `now+7d`, so an active Penpot user stays signed in indefinitely.

If an app-native session expires while the oauth2-proxy cookie is still
valid, the app's proxy-auth middleware silently re-establishes it from
the `X-Auth-Request-Email` header on the next request — the user
notices nothing.

**The load-bearing values:**

- **1 hour** — security boundary. A user disabled in Cognito is kicked out within roughly this window.
- **7 days** — UX boundary. After this, the user is redirected through Cognito (usually silent, sometimes prompted — see below).
- **5 days** — replay-window boundary. A leaked refresh token is replayable for up to this long.

---

## What happens at each boundary

### Every ~1 hour (silent)
oauth2-proxy renews the Cognito access token using the refresh token.
User sees nothing if refresh works. If it fails, the session is dropped
and the user is redirected through Cognito on their next request.

### After 7 days (oauth2-proxy cookie expires)
The cookie is **absolute**, not idle-based — it expires 7 days after
issuance regardless of activity.

When it does:
1. Next request → oauth2-proxy can't find a session → redirect to Cognito
2. **If Cognito's own SSO session is still valid** → silent redirect
   flash, user lands back signed in with a fresh 7-day cookie
3. **If Cognito's SSO session has also expired** → user sees the Cognito
   login form, enters credentials once, gets a fresh 7-day cookie

Most users experience a brief redirect flash, not a password prompt.

The exact "no password prompt" window is controlled by Cognito's
**Authentication flow session duration** (App Client setting in AWS).

### After 5 days (Cognito refresh token expires)
A real Cognito login is required, regardless of any local cookies.
Only affects users who have been idle this long.

---

## Decoupling reminders

These are independent — don't confuse them:

- The **7-day cookie** is set by oauth2-proxy and controls "are you carrying a session in this browser?"
- The **5-day refresh token** is issued by Cognito and controls "can your session keep refreshing?"
- The **1-hour refresh interval** is controlled by `OAUTH2_PROXY_COOKIE_REFRESH` and is the **only** thing protecting against revoked users hanging on with stale sessions.

If anyone changes any of these, the others don't automatically follow.

---

## Stale session on user switch

### What users observe

User A and User B share a browser (laptop, family device, kiosk). A logs in to Plane, clicks **Logout all** on the portal, hands the laptop to B. B logs in to mPass on the portal and opens Plane.

Without the fix, **B is shown A's workspace** on first page load — even though the portal logout looked like it worked. A refresh or two later it self-corrects, but the brief identity mix-up is real.

### Why it happens

The portal's "Logout all" clears one cookie: `_oauth2_proxy` on `.${PLATFORM_DOMAIN}`. That's the cookie oauth2-proxy uses to recognise users at the edge.

Each app **also** sets its own session cookie scoped to its own subdomain (Plane's `sessionid` on `pm.${PLATFORM_DOMAIN}`, Outline's `accessToken` on `docs.${PLATFORM_DOMAIN}`, etc.). The portal cannot reach across subdomains to clear these — browsers do not permit cross-host cookie modification.

So after "Logout all":

- `_oauth2_proxy`: gone ✅
- Plane's `sessionid` for A: still in the browser
- Outline's `accessToken` for A: still in the browser
- (same for the other apps)

When B logs in and visits Plane:

1. New `_oauth2_proxy` for B is set.
2. Browser sends both the new `_oauth2_proxy` (B) **and** the surviving `sessionid` (A's session).
3. Without reconciliation, the app middleware sees a valid Django session and serves the request as A.

### How the fix works

Every app's middleware now compares the upstream identity (proxy header) against its own session's user on every authenticated request:

- Match → keep going (steady state, no DB writes).
- Mismatch → flush the local session, then re-authenticate as the incoming user.

The flush mechanism varies per app (Django `logout()`, throw 401 + cookie clear, `clearCookie`, in-place re-key) but the contract is identical: no path serves the request as the previous user after a mismatch is detected.

### Reference

The formal contract is in [`openspec/specs/proxy-auth-middleware/spec.md`](./openspec/specs/proxy-auth-middleware/spec.md) (Rule 2 "Identity mismatch SHALL flush the existing session immediately"). The per-app implementations are documented in each app's `{app}-security.md` "Post-audit finding — stale session" section.

---

## Where the TTLs are set

| Value | Source |
|---|---|
| 1-hour refresh interval | `OAUTH2_PROXY_COOKIE_REFRESH=1h` (oauth2-proxy env) |
| 7-day oauth2-proxy cookie | `OAUTH2_PROXY_COOKIE_EXPIRE=168h` (oauth2-proxy env) |
| 7-day `expires_in` returned to oauth2-proxy | `SESSION_COOKIE_MAX_AGE_SECONDS=604800` (mpass-auth-proxy env) |
| 14-day app-issued refresh token | `SESSION_REFRESH_TOKEN_MAX_AGE_SECONDS=1209600` (Twenty / SurfSense / Outline-as-provider) |
| 5-day Cognito refresh token | Cognito User Pool → App Client → "Refresh token expiration" (`RefreshTokenValidity`). |
| 1-hour Cognito access/id token | Cognito User Pool → App Client → "Access/ID token expiration" |
| 3-minute bridge state | `BRIDGE_STATE_TTL` in `mpass-auth-proxy/main.py` |
| 60-second auth code | `BRIDGE_CODE_TTL` in `mpass-auth-proxy/main.py` |
| 2-week Plane Django session | `SESSION_COOKIE_AGE` in Django settings |
```

`agents/mautic-sso-discovery/context/apps-overview.md`:

```markdown
# Apps Overview — SSO Integration & Tech Stack

Five apps behind oauth2-proxy + Traefik ForwardAuth. Each app's auth flow, build pattern, and per-app integration shape.

## SSO integration shape

How each app reads `X-Auth-Request-Email` from oauth2-proxy and turns it into an authenticated session.

| App | Where the header is consumed | What it issues |
|-----|------------------------------|----------------|
| Plane | `apps/api/plane/middleware/proxy_auth.py` — Django ProxyAuthMiddleware | Django session cookie (`SESSION_COOKIE_AGE`) |
| Outline | `server/middlewares/authentication.ts` — FORWARDAUTH_SERVICE branch inside the existing auth middleware | JWT cookie (`accessToken`) — fork patch reads `SESSION_TTL_SECONDS` |
| Penpot | `backend/src/app/http/auth_request.clj` — Reitit RPC middleware (header read as fallback after session + access-token) | Penpot auth-token cookie (`PENPOT_AUTH_TOKEN_COOKIE_MAX_AGE`) |
| SurfSense | `surfsense_backend/app/...` — dedicated `GET /auth/jwt/proxy-login` endpoint, cookie handoff (60s short-lived cookies → SPA reads them, stores JWT in localStorage, clears cookies) | JWT (access + refresh), localStorage-stored |
| Twenty | `packages/twenty-server/src/engine/core-modules/auth/controllers/sso-proxy-login.controller.ts` — standalone NestJS controller `GET /auth/sso/proxy-login`, no Passport ceremony | `tokenPair` cookie (access JWT + refresh JWT, JSON-encoded) — Jotai reads it |

## Identity-managed UI gating

When `AUTH_TYPE=SSO`, each app's SPA hides login / password / email-change UI so users can't break their own SSO lookup by changing their email.

| App | Gating mechanism | Surfaces gated |
|-----|------------------|----------------|
| Plane | `MPASS_SSO_ENABLED` env (or per-fork) | login form, signup, email change, password change (per fork's audit) |
| Outline | `env.AUTH_TYPE === 'SSO'` in `app/scenes/Logout.tsx` + auth UI | local auth UI hidden under SSO |
| Penpot | `enable-x-auth-request-headers` flag in `PENPOT_FLAGS` + `request-email-change` RPC gated | email change RPC rejects when external IdP manages identity |
| SurfSense | `NEXT_PUBLIC_FASTAPI_BACKEND_AUTH_TYPE: SSO` env read by SPA | sign-in / sign-up forms hidden, redirect to /auth/jwt/proxy-login |
| Twenty | `useIsSsoEnabled` hook (`window._env_.AUTH_TYPE === 'SSO'`) | SignInUp form, PasswordReset, change-password button (`useCanChangePassword`), EmailField (read-only), Toggle2FA, TOTP setup page (Navigate redirect) |

## Bypass routers (Traefik)

Each app has `*-bypass` / `*-public` / `*-static` routers at `priority=20+` that skip ForwardAuth. Restricted to static / health / webhooks / admin-bootstrap / out-of-band-sync only — never user data or mutations.

## Logout

All 5 apps use the **1-layer logout** shape since 2026-04-17 — clear app session, navigate to portal host. No oauth2-proxy `/sign_out` hop (not available with current Cognito app client).

The portal-host prefix is driven by the **required** `SMB_NAME` env var (no default — the SPA must crash loudly if unset rather than redirect to the wrong host).

```js
const smbName = process.env.SMB_NAME.trim();
const portalHost = window.location.hostname.replace(/^[^.]*\./, `${smbName}.`);
window.location.href = `${window.location.protocol}//${portalHost}/`;
```

## Rules / lessons for any new SSO ForwardAuth integration

Cross-app rules distilled from the full audit cascade — apply when adding a new app to the bundle:

1. **Never use SQL `LIKE`/`ILIKE` against user-supplied values without escaping `%` and `_`.** Prefer exact match (`=`) for identity lookups.
2. **Don't trust proxy-injected identity headers based on topology alone.** `AUTH_TYPE=SSO` env flag + "deploy correctly behind the proxy" is fragile on its own.
3. **A loose email-shape regex (`/^[^\s@]+@[^\s@]+\.[^\s@]+$/`) is not validation.** It accepts `%@%.%`, `'; DROP--`, and most metacharacters.
4. **First-user-becomes-admin auto-provisioning is a footgun in any path that doesn't already require admin approval.**
5. **Synthesized identity emails (`<sub>@<default-domain>`) are fine but pick a deployment-unique domain.**
6. **Backend gating must mirror frontend gating when SSO is the only authentication path.** Hiding password-reset / signup / 2FA-enrollment in the UI is not sufficient if the underlying GraphQL/REST endpoints still execute.
7. **`User.disabled` / `isActive` / equivalent must be enforced in the SSO path explicitly.** A deactivation must not be undone by simply logging in again.
8. **Bearer JWT handoff amplifies topology-trust fragility.** A session cookie tied to the response host gets re-checked per-request; a bearer JWT is portable across hosts and lives for its TTL.
9. **PKCE and `nonce` are not substitutes.** PKCE binds code↔verifier; `nonce` binds authorization-request↔id_token. You need both whenever id_tokens travel in URLs.
10. **Documentation-vs-code drift on kill switches.** When a design doc describes an enable flag that doesn't exist in the code, verify which way the implicit default fails.
```

`agents/mautic-sso-discovery/context/proxy-auth-middleware-spec.md`:

```markdown
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
```

`agents/mautic-sso-discovery/mautic_sso_discovery/context.py`:

```python
"""Loads the bundled, fixed Moneta SSO contract into one string for the
discovery agent's system prompt. These files are static copies from
awais786/sso-rules-moneta (see
docs/superpowers/specs/2026-09-22-mautic-sso-discovery-agent-design.md) -
not fetched at runtime, since the contract is fixed for every discovery run
regardless of which target repo is being investigated.
"""
from __future__ import annotations

from pathlib import Path

_CONTEXT_DIR = Path(__file__).resolve().parent.parent / "context"
_CONTEXT_FILES = ["authentication.md", "apps-overview.md", "proxy-auth-middleware-spec.md"]


def load_moneta_contract() -> str:
    sections = [f"## Source: {name}\n\n{(_CONTEXT_DIR / name).read_text()}" for name in _CONTEXT_FILES]
    return "\n\n---\n\n".join(sections)
```

- [ ] **Step 2: Write the failing test**

`agents/mautic-sso-discovery/tests/test_context.py`:

```python
from __future__ import annotations

from mautic_sso_discovery.context import load_moneta_contract


def test_load_moneta_contract_includes_all_sources():
    contract = load_moneta_contract()
    assert "Source: authentication.md" in contract
    assert "Source: apps-overview.md" in contract
    assert "Source: proxy-auth-middleware-spec.md" in contract


def test_load_moneta_contract_sections_are_substantial():
    contract = load_moneta_contract()
    sections = contract.split("---")
    assert len(sections) == 3
    assert all(len(section.strip()) > 200 for section in sections)
```

- [ ] **Step 3: Install and run the tests to verify they pass**

```bash
cd agents/mautic-sso-discovery
python3 -m venv .venv && source .venv/bin/activate
pip install -e . -r requirements.txt
pytest tests/test_context.py -v
```

Expected: both tests PASS (this test has no external dependency, so it should pass immediately once the files above exist — if it doesn't, the context files or `context.py` have a path or naming mismatch).

- [ ] **Step 4: Commit**

```bash
git add agents/mautic-sso-discovery/
git commit -m "Scaffold mautic-sso-discovery package with bundled Moneta contract"
```

---

## Task 2: Clone + write-lockdown

**Files:**
- Create: `agents/mautic-sso-discovery/mautic_sso_discovery/cloning.py`
- Test: `agents/mautic-sso-discovery/tests/test_cloning.py`

**Interfaces:**
- Produces: `clone_repo(url: str, dest: Path, *, runner: Runner = ...) -> None` and
  `lock_down(path: Path) -> None` — both consumed by Task 3's `run_discover`.

- [ ] **Step 1: Write the failing tests**

`agents/mautic-sso-discovery/tests/test_cloning.py`:

```python
from __future__ import annotations

import os

import pytest

from mautic_sso_discovery.cloning import clone_repo, lock_down

pytestmark = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses file permission bits, making this test meaningless",
)


def test_clone_repo_invokes_git_clone_with_depth_1(tmp_path):
    calls = []
    dest = tmp_path / "target"

    clone_repo("https://example.com/some/repo.git", dest, runner=calls.append)

    assert calls == [["git", "clone", "--depth", "1", "https://example.com/some/repo.git", str(dest)]]


def test_lock_down_blocks_writes_to_existing_files(tmp_path):
    target = tmp_path / "cloned"
    nested_file = target / "sub" / "file.txt"
    nested_file.parent.mkdir(parents=True)
    nested_file.write_text("original")

    lock_down(target)

    with pytest.raises(PermissionError):
        nested_file.write_text("tampered")


def test_lock_down_blocks_new_file_creation(tmp_path):
    target = tmp_path / "cloned"
    target.mkdir()
    (target / "existing.txt").write_text("x")

    lock_down(target)

    with pytest.raises(PermissionError):
        (target / "new.txt").write_text("nope")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd agents/mautic-sso-discovery
pytest tests/test_cloning.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'mautic_sso_discovery.cloning'`

- [ ] **Step 3: Write the implementation**

`agents/mautic-sso-discovery/mautic_sso_discovery/cloning.py`:

```python
"""Deterministic clone + write-lockdown for the target repo under
discovery. This is plain Python, not the agent's own tool call - cloning a
repo has exactly one correct way to do it, so there's no judgment for the
model to add. Doing it before the agent session starts means the lockdown
below is airtight: the agent's session never sees the directory in a
writable state, independent of which tools it's later granted.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Callable

Runner = Callable[[list[str]], None]


def _default_runner(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def clone_repo(url: str, dest: Path, *, runner: Runner = _default_runner) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    runner(["git", "clone", "--depth", "1", url, str(dest)])


def lock_down(path: Path) -> None:
    """Strips write permission from every file and directory under path,
    bottom-up (files and subdirectories before their parent, so a parent's
    write bit isn't removed before its children are reachable).
    """
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            _strip_write(Path(root) / name)
        for name in dirs:
            _strip_write(Path(root) / name)
    _strip_write(path)


def _strip_write(target: Path) -> None:
    current_mode = target.stat().st_mode
    target.chmod(current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cloning.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add agents/mautic-sso-discovery/mautic_sso_discovery/cloning.py agents/mautic-sso-discovery/tests/test_cloning.py
git commit -m "Add deterministic clone + write-lockdown for the target repo"
```

---

## Task 3: Discover phase (Agent SDK session, read-only)

**Files:**
- Create: `agents/mautic-sso-discovery/mautic_sso_discovery/discover.py`
- Test: `agents/mautic-sso-discovery/tests/test_discover.py`

**Interfaces:**
- Consumes: `load_moneta_contract() -> str` (Task 1), `clone_repo(url, dest, *, runner=...) -> None`
  and `lock_down(path) -> None` (Task 2).
- Produces: `run_discover(target_repo_url: str, out_path: Path, workdir: Path, *,
  query_impl=query, clone_impl=clone_repo, lock_down_impl=lock_down) -> None` —
  consumed by Task 5's CLI.

- [ ] **Step 1: Write the failing tests**

`agents/mautic-sso-discovery/tests/test_discover.py`:

```python
from __future__ import annotations

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock

from mautic_sso_discovery.discover import build_system_prompt, build_task_prompt, run_discover


def test_build_system_prompt_includes_contract_and_tool_rules():
    prompt = build_system_prompt()
    assert "Source: authentication.md" in prompt
    assert "ASSUMPTION" in prompt
    assert "UNKNOWN" in prompt
    assert "Write/Edit/Bash" in prompt


def test_build_task_prompt_lists_all_required_sections():
    prompt = build_task_prompt("https://example.com/repo")
    for heading in [
        "Authentication today",
        "Login flow",
        "Logout flow",
        "Users",
        "Sessions",
        "Roles/permissions/RBAC",
        "Existing OAuth/OIDC",
        "Extension points",
        "Gap analysis",
        "Proposed SSO integration architecture",
        "Implementation and test plan",
    ]:
        assert heading in prompt


async def _fake_query(*, prompt, options):
    yield AssistantMessage(content=[TextBlock(text="exploring the repo...")], model="test")
    yield AssistantMessage(content=[TextBlock(text="# Discovery Report\n\nfinal content")], model="test")


def test_run_discover_clones_locks_down_and_writes_final_report_text(tmp_path):
    calls = {}

    def fake_clone(url, dest):
        calls["cloned"] = (url, dest)
        dest.mkdir(parents=True)

    def fake_lock_down(path):
        calls["locked"] = path

    out_path = tmp_path / "report.md"

    run_discover(
        "https://example.com/repo",
        out_path,
        tmp_path,
        query_impl=_fake_query,
        clone_impl=fake_clone,
        lock_down_impl=fake_lock_down,
    )

    assert out_path.read_text() == "# Discovery Report\n\nfinal content"
    assert calls["cloned"] == ("https://example.com/repo", tmp_path / "target-repo")
    assert calls["locked"] == tmp_path / "target-repo"


def test_run_discover_raises_on_empty_final_report(tmp_path):
    async def empty_query(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text="")], model="test")

    with pytest.raises(RuntimeError, match="no final report"):
        run_discover(
            "https://example.com/repo",
            tmp_path / "report.md",
            tmp_path,
            query_impl=empty_query,
            clone_impl=lambda url, dest: dest.mkdir(parents=True),
            lock_down_impl=lambda path: None,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_discover.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'mautic_sso_discovery.discover'`

- [ ] **Step 3: Write the implementation**

`agents/mautic-sso-discovery/mautic_sso_discovery/discover.py`:

```python
"""Phase 1 (`discover`): explores an already-cloned, already-locked-down
target repo with a Claude Agent SDK session and writes a Markdown
discovery report + SSO integration plan. The session has no Write/Edit/Bash
tool - Read/Grep/Glob only - so even if the write-lockdown in cloning.py
were somehow bypassed, the model still has no tool capable of writing to
the checkout. The report itself is written by this module's own code from
the session's final text, not by a tool call the model makes.
"""
from __future__ import annotations

import functools
from pathlib import Path

import anyio
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from mautic_sso_discovery.cloning import clone_repo, lock_down
from mautic_sso_discovery.context import load_moneta_contract

_REQUIRED_TASK_SECTIONS = [
    "Authentication today",
    "Login flow",
    "Logout flow",
    "Users",
    "Sessions",
    "Roles/permissions/RBAC",
    "Existing OAuth/OIDC",
    "Extension points",
    "Gap analysis",
    "Proposed SSO integration architecture",
    "Implementation and test plan",
]


def build_system_prompt() -> str:
    return (
        "You are a security-and-architecture discovery agent. You are auditing "
        "a target codebase's current authentication implementation against a "
        "fixed SSO contract (given below) that the target app must eventually "
        "satisfy.\n\n"
        "Rules:\n"
        "- Every non-trivial claim about the target codebase MUST cite an exact "
        "file path and line number/range from the checkout at your current "
        "working directory.\n"
        "- Anything you cannot verify by reading the code MUST be labeled "
        "`ASSUMPTION` or `UNKNOWN` - never stated as fact.\n"
        "- You must not attempt to modify the target checkout. You have no "
        "Write/Edit/Bash tools; only Read, Grep, and Glob.\n"
        "- Do all exploration first. Your FINAL message must contain nothing "
        "but the complete Markdown report, and nothing else - no preamble, no "
        "'here is the report'.\n\n"
        "The fixed SSO contract you are comparing against:\n\n"
        f"{load_moneta_contract()}"
    )


def build_task_prompt(target_repo_url: str) -> str:
    numbered = "\n".join(f"{i + 1}. {section}" for i, section in enumerate(_REQUIRED_TASK_SECTIONS))
    return (
        f"The target repository ({target_repo_url}) is checked out read-only at "
        "your current working directory. Investigate it and write a Markdown "
        f"report with exactly these sections, in this order:\n\n{numbered}\n\n"
        "For sections 1-8, trace the real code (using Read/Grep/Glob) rather "
        "than assuming based on framework conventions. Section 9 (Gap "
        "analysis) must explicitly compare sections 1-8 against the fixed SSO "
        "contract above. Section 10 must propose a concrete SSO integration "
        "architecture (auth flow, claims/identity mapping, user/role "
        "provisioning, logout, session handling, security considerations). "
        "Section 11 must be actionable and reference concrete files."
    )


async def _collect_final_report_text(prompt: str, options: ClaudeAgentOptions, *, query_impl) -> str:
    last_text = ""
    async for message in query_impl(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            text = "".join(block.text for block in message.content if isinstance(block, TextBlock))
            if text:
                last_text = text
    return last_text


def run_discover(
    target_repo_url: str,
    out_path: Path,
    workdir: Path,
    *,
    query_impl=query,
    clone_impl=clone_repo,
    lock_down_impl=lock_down,
) -> None:
    clone_dir = workdir / "target-repo"
    clone_impl(target_repo_url, clone_dir)
    lock_down_impl(clone_dir)

    options = ClaudeAgentOptions(
        system_prompt=build_system_prompt(),
        cwd=clone_dir,
        allowed_tools=["Read", "Grep", "Glob"],
        disallowed_tools=["Bash", "Write", "Edit", "NotebookEdit"],
        permission_mode="bypassPermissions",
        max_turns=60,
        model="claude-sonnet-5",
    )

    report = anyio.run(
        functools.partial(
            _collect_final_report_text,
            build_task_prompt(target_repo_url),
            options,
            query_impl=query_impl,
        )
    )

    if not report.strip():
        raise RuntimeError("discovery agent produced no final report text")

    out_path.write_text(report)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_discover.py -v
```

Expected: all PASS. (These tests never call the real `query()` — `query_impl` is
always faked — so they run with no network access and no `ANTHROPIC_API_KEY`.)

- [ ] **Step 5: Commit**

```bash
git add agents/mautic-sso-discovery/mautic_sso_discovery/discover.py agents/mautic-sso-discovery/tests/test_discover.py
git commit -m "Add discover phase: read-only Agent SDK session writes the discovery report"
```

---

## Task 4: propose-issues phase (drafts + creates GitHub issues)

**Files:**
- Create: `agents/mautic-sso-discovery/mautic_sso_discovery/propose_issues.py`
- Create: `agents/mautic-sso-discovery/tests/support.py`
- Test: `agents/mautic-sso-discovery/tests/test_propose_issues.py`

**Interfaces:**
- Consumes: `GitHubClient` from `issue_reconciler.client` (existing, installed via the
  `-e ../issue-reconciler` line in `requirements.txt`).
- Produces: `run_propose_issues(report_path: Path, github_repo: str, client: GitHubClient,
  *, query_impl=query) -> dict[str, str]` — consumed by Task 5's CLI.

- [ ] **Step 1: Write the test support helper**

`agents/mautic-sso-discovery/tests/support.py`:

```python
"""Test-only fake GitHub transport, following the same pattern as
agents/issue-reconciler/tests/support.py - kept as a separate, smaller copy
here since these two agent packages are independently installable and
don't share a test-only module.
"""
from __future__ import annotations

from typing import Any

from issue_reconciler.client import GitHubClient


class FakeResponse:
    def __init__(self, data: Any = None):
        self.status_code = 200
        self.ok = True
        self.reason = ""
        self.headers: dict = {}
        self._body = {"data": data}

    def json(self) -> dict:
        return self._body


def make_sequential_client(responses: list[Any]) -> tuple[GitHubClient, list[dict]]:
    """Returns canned data payloads in call order - use only when the code
    under test issues queries in a known, fixed sequence.
    """
    calls: list[dict] = []
    index = {"i": 0}

    def transport(_url: str, body: dict, _headers: dict):
        calls.append(body)
        data = responses[index["i"]]
        index["i"] += 1
        return FakeResponse(data=data)

    client = GitHubClient("test-token", transport=transport, sleep=lambda _: None)
    return client, calls
```

- [ ] **Step 2: Write the failing tests**

`agents/mautic-sso-discovery/tests/test_propose_issues.py`:

```python
from __future__ import annotations

import json

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock
from support import make_sequential_client

from mautic_sso_discovery.propose_issues import (
    build_propose_prompt,
    create_issues,
    parse_issue_drafts,
    run_propose_issues,
)


def test_build_propose_prompt_requires_json_only_response_and_embeds_report():
    prompt = build_propose_prompt("some report text")
    assert "ONLY a JSON array" in prompt
    assert "some report text" in prompt


def test_parse_issue_drafts_accepts_valid_array():
    raw = json.dumps(
        [
            {"title": "A", "body": "body a", "depends_on": []},
            {"title": "B", "body": "body b", "depends_on": ["A"]},
        ]
    )
    drafts = parse_issue_drafts(raw)
    assert [d["title"] for d in drafts] == ["A", "B"]


def test_parse_issue_drafts_rejects_unknown_dependency():
    raw = json.dumps([{"title": "A", "body": "x", "depends_on": ["Ghost"]}])
    with pytest.raises(ValueError, match="Ghost"):
        parse_issue_drafts(raw)


def test_create_issues_creates_in_dependency_order_and_links_urls():
    client, calls = make_sequential_client(
        [
            {"repository": {"id": "REPO_ID"}},
            {"createIssue": {"issue": {"number": 1, "url": "https://github.com/x/y/issues/1"}}},
            {"createIssue": {"issue": {"number": 2, "url": "https://github.com/x/y/issues/2"}}},
        ]
    )
    drafts = [
        {"title": "A", "body": "body a", "depends_on": []},
        {"title": "B", "body": "body b", "depends_on": ["A"]},
    ]

    urls = create_issues(client, "x", "y", drafts)

    assert urls == {"A": "https://github.com/x/y/issues/1", "B": "https://github.com/x/y/issues/2"}
    assert "https://github.com/x/y/issues/1" in calls[2]["variables"]["body"]


def test_create_issues_raises_on_circular_dependency():
    client, _ = make_sequential_client([{"repository": {"id": "REPO_ID"}}])
    drafts = [
        {"title": "A", "body": "x", "depends_on": ["B"]},
        {"title": "B", "body": "y", "depends_on": ["A"]},
    ]
    with pytest.raises(ValueError, match="circular"):
        create_issues(client, "x", "y", drafts)


def test_run_propose_issues_end_to_end(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n\n## Implementation and test plan\n...")

    async def fake_query(*, prompt, options):
        yield AssistantMessage(
            content=[TextBlock(text=json.dumps([{"title": "A", "body": "b", "depends_on": []}]))],
            model="test",
        )

    client, _ = make_sequential_client(
        [
            {"repository": {"id": "REPO_ID"}},
            {"createIssue": {"issue": {"number": 1, "url": "https://github.com/x/y/issues/1"}}},
        ]
    )

    urls = run_propose_issues(report_path, "x/y", client, query_impl=fake_query)

    assert urls == {"A": "https://github.com/x/y/issues/1"}
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_propose_issues.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'mautic_sso_discovery.propose_issues'`

- [ ] **Step 4: Write the implementation**

`agents/mautic-sso-discovery/mautic_sso_discovery/propose_issues.py`:

```python
"""Phase 2 (`propose-issues`): a separate, human-gated invocation. Drafting
(what issues to create) is the model's job; creating them is plain code
that reuses GitHubClient from agents/issue-reconciler/, so a bad draft is a
JSON value to review, not a live API call to debug. The report text is
pasted directly into the prompt rather than read via a tool, so this
session needs zero tools at all - simpler and strictly safer than granting
a scoped Read tool for one file.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import TypedDict

import anyio
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from issue_reconciler.client import GitHubClient

_REPO_ID_QUERY = "query RepoId($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { id } }"
_CREATE_ISSUE = (
    "mutation CreateIssue($repositoryId: ID!, $title: String!, $body: String!) "
    "{ createIssue(input: { repositoryId: $repositoryId, title: $title, body: $body }) "
    "{ issue { number url } } }"
)


class IssueDraft(TypedDict):
    title: str
    body: str
    depends_on: list[str]


def build_propose_prompt(report_text: str) -> str:
    return (
        "Below is a completed SSO discovery report for a target codebase. "
        "Break its 'Implementation and test plan' section into small, "
        "independently scoped GitHub issues. Each issue must be small enough "
        "to review in one pull request.\n\n"
        "Respond with ONLY a JSON array (no prose, no code fences) where each "
        "element has exactly these keys:\n"
        '- "title": short imperative summary\n'
        '- "body": Markdown body including Scope, Affected files, Acceptance '
        "criteria, and Tests sections, each referencing concrete files named "
        "in the report\n"
        '- "depends_on": a list of the exact "title" strings of other issues '
        "in this same array that must land first, or an empty list\n\n"
        f"--- REPORT ---\n{report_text}"
    )


async def _collect_final_report_text(prompt: str, options: ClaudeAgentOptions, *, query_impl) -> str:
    last_text = ""
    async for message in query_impl(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            text = "".join(block.text for block in message.content if isinstance(block, TextBlock))
            if text:
                last_text = text
    return last_text


def parse_issue_drafts(raw_json: str) -> list[IssueDraft]:
    drafts = json.loads(raw_json)
    if not isinstance(drafts, list):
        raise ValueError("expected a JSON array of issue drafts")
    titles = {d["title"] for d in drafts}
    for draft in drafts:
        unknown = set(draft.get("depends_on", [])) - titles
        if unknown:
            raise ValueError(f"issue {draft['title']!r} depends on unknown title(s): {unknown}")
    return drafts


def create_issues(client: GitHubClient, owner: str, name: str, drafts: list[IssueDraft]) -> dict[str, str]:
    """Creates each issue in dependency order (a draft with no unmet
    dependency first), appending a note of already-created dependency URLs
    into the body, since GitHub issues can't cross-link to a dependency
    that doesn't exist yet at draft time. Returns {title: issue_url}.
    """
    repository_id = client.query(_REPO_ID_QUERY, {"owner": owner, "name": name})["repository"]["id"]

    remaining = list(drafts)
    created_urls: dict[str, str] = {}
    while remaining:
        ready = [d for d in remaining if all(dep in created_urls for dep in d.get("depends_on", []))]
        if not ready:
            raise ValueError("circular dependency among issue drafts")
        for draft in ready:
            body = draft["body"]
            if draft.get("depends_on"):
                deps_line = ", ".join(f"{created_urls[dep]} ({dep})" for dep in draft["depends_on"])
                body = f"{body}\n\n---\nDepends on: {deps_line}"
            result = client.query(
                _CREATE_ISSUE,
                {"repositoryId": repository_id, "title": draft["title"], "body": body},
            )
            created_urls[draft["title"]] = result["createIssue"]["issue"]["url"]
            remaining.remove(draft)
    return created_urls


def run_propose_issues(
    report_path: Path,
    github_repo: str,
    client: GitHubClient,
    *,
    query_impl=query,
) -> dict[str, str]:
    owner, name = github_repo.split("/", 1)
    report_text = report_path.read_text()

    options = ClaudeAgentOptions(
        allowed_tools=[],
        disallowed_tools=["Bash", "Write", "Edit", "NotebookEdit", "Read", "Grep", "Glob"],
        permission_mode="bypassPermissions",
        max_turns=5,
        model="claude-sonnet-5",
    )

    raw = anyio.run(
        functools.partial(
            _collect_final_report_text,
            build_propose_prompt(report_text),
            options,
            query_impl=query_impl,
        )
    )
    drafts = parse_issue_drafts(raw)
    return create_issues(client, owner, name, drafts)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_propose_issues.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add agents/mautic-sso-discovery/mautic_sso_discovery/propose_issues.py agents/mautic-sso-discovery/tests/support.py agents/mautic-sso-discovery/tests/test_propose_issues.py
git commit -m "Add propose-issues phase: draft issues from the report, create via GitHubClient"
```

---

## Task 5: CLI entrypoint + README

**Files:**
- Create: `agents/mautic-sso-discovery/mautic_sso_discovery/__main__.py`
- Create: `agents/mautic-sso-discovery/README.md`
- Test: `agents/mautic-sso-discovery/tests/test_main.py`

**Interfaces:**
- Consumes: `run_discover` (Task 3), `run_propose_issues` (Task 4), `GitHubClient` (reused).

- [ ] **Step 1: Write the failing tests**

`agents/mautic-sso-discovery/tests/test_main.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from mautic_sso_discovery.__main__ import main


def test_discover_requires_target_repo_and_out(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "discover"])
    with pytest.raises(SystemExit):
        main()


def test_propose_issues_requires_report_and_github_repo(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "propose-issues"])
    with pytest.raises(SystemExit):
        main()


def test_discover_dispatches_to_run_discover(monkeypatch, tmp_path):
    called = {}

    def fake_run_discover(target_repo, out_path, workdir):
        called["args"] = (target_repo, out_path)

    monkeypatch.setattr("mautic_sso_discovery.__main__.run_discover", fake_run_discover)
    out_path = tmp_path / "r.md"
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "discover", "--target-repo", "https://x", "--out", str(out_path)],
    )

    assert main() == 0
    assert called["args"] == ("https://x", out_path)


def test_propose_issues_dispatches_to_run_propose_issues(monkeypatch, tmp_path):
    called = {}

    def fake_run_propose_issues(report_path, github_repo, client):
        called["args"] = (report_path, github_repo)
        return {"A": "https://github.com/x/y/issues/1"}

    monkeypatch.setattr("mautic_sso_discovery.__main__.run_propose_issues", fake_run_propose_issues)
    monkeypatch.setattr("mautic_sso_discovery.__main__.GitHubClient", lambda token: "fake-client")
    monkeypatch.setenv("BOARD_TOKEN", "t")
    report_path = tmp_path / "report.md"
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "propose-issues", "--report", str(report_path), "--github-repo", "x/y"],
    )

    assert main() == 0
    assert called["args"] == (report_path, "x/y")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_main.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'mautic_sso_discovery.__main__'`

- [ ] **Step 3: Write the implementation**

`agents/mautic-sso-discovery/mautic_sso_discovery/__main__.py`:

```python
"""Entrypoints:
`python -m mautic_sso_discovery discover --target-repo <url> --out <path>`
`python -m mautic_sso_discovery propose-issues --report <path> --github-repo <owner>/<name>`

Local dev only: ANTHROPIC_API_KEY/BOARD_TOKEN come from real environment
secrets in CI; .env is a no-op there (the file doesn't exist).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from issue_reconciler.client import GitHubClient

from mautic_sso_discovery.discover import run_discover
from mautic_sso_discovery.propose_issues import run_propose_issues

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _discover(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory() as workdir:
        run_discover(args.target_repo, Path(args.out), Path(workdir))
    print(f"discovery report written to {args.out}")
    return 0


def _propose_issues(args: argparse.Namespace) -> int:
    client = GitHubClient(os.environ["BOARD_TOKEN"])
    urls = run_propose_issues(Path(args.report), args.github_repo, client)
    for title, url in urls.items():
        print(f"{title}: {url}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="mautic_sso_discovery")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover")
    discover_parser.add_argument("--target-repo", required=True)
    discover_parser.add_argument("--out", required=True)
    discover_parser.set_defaults(func=_discover)

    propose_parser = subparsers.add_parser("propose-issues")
    propose_parser.add_argument("--report", required=True)
    propose_parser.add_argument("--github-repo", required=True)
    propose_parser.set_defaults(func=_propose_issues)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

`agents/mautic-sso-discovery/README.md`:

```markdown
# mautic-sso-discovery

Claude Agent SDK program for [issue #82](https://github.com/awais786/ai-on-boarding/issues/82):
investigates a target codebase's current authentication against the fixed
Moneta SSO contract (bundled in `context/`), and writes a Markdown discovery
report + integration plan. Never modifies the target repo — the clone is
made unwritable before the agent session starts, and the session is never
granted a Write/Edit/Bash tool.

## Setup

```bash
cd agents/mautic-sso-discovery
python3 -m venv .venv && source .venv/bin/activate
pip install -e . -r requirements.txt
```

Requires `ANTHROPIC_API_KEY` in the environment (or a `.env` file next to
this README, for local dev only — never committed).

## Usage

**Phase 1 — discovery (writes a local report, touches nothing on GitHub):**

```bash
python -m mautic_sso_discovery discover \
  --target-repo https://github.com/pressingly/mautic \
  --out ./mautic-discovery-report.md
```

Read the report. Only once you're satisfied with it, run phase 2.

**Phase 2 — propose issues (requires `BOARD_TOKEN`, a GitHub PAT with repo
write access; creates real issues):**

```bash
python -m mautic_sso_discovery propose-issues \
  --report ./mautic-discovery-report.md \
  --github-repo awais786/ai-on-boarding
```

## Tests

```bash
pytest -v
```

All tests fake the Agent SDK's `query()` and GitHub's transport — no
`ANTHROPIC_API_KEY` or `BOARD_TOKEN` needed to run the suite.
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_main.py -v
```

Expected: all PASS

- [ ] **Step 5: Run the full test suite**

```bash
pytest -v
```

Expected: every test in `agents/mautic-sso-discovery/tests/` PASSes.

- [ ] **Step 6: Commit**

```bash
git add agents/mautic-sso-discovery/mautic_sso_discovery/__main__.py agents/mautic-sso-discovery/README.md agents/mautic-sso-discovery/tests/test_main.py
git commit -m "Add CLI entrypoint and README for mautic-sso-discovery"
```

---

## Manual verification (not automated — needs real credentials)

Once all five tasks are committed, do one real end-to-end run before
considering this done:

```bash
cd agents/mautic-sso-discovery
export ANTHROPIC_API_KEY=...  # real key
python -m mautic_sso_discovery discover \
  --target-repo https://github.com/pressingly/mautic \
  --out ./mautic-discovery-report.md
```

Read the resulting report and confirm:
- Every major claim cites a real `file:line` you can open and verify.
- Nothing in `pressingly/mautic`'s working tree changed (`git status` inside
  the temp clone would show nothing — the clone is deleted with the temp dir
  anyway, but you can add a `breakpoint()` before cleanup once to check).
- Assumptions/unknowns are clearly marked, not stated as fact.

Only after that manual read should `propose-issues` be run for real, with a
`BOARD_TOKEN` scoped to `awais786/ai-on-boarding`.
