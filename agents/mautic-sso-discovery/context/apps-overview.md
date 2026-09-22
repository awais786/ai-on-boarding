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
