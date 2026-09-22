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
