# LINKEDIN INTEGRATION REPORT

Baseline: backend `300 passed` / frontend `25 passed` / `tsc --noEmit` clean /
`npm run build` clean at commit `b523cd7d6926d44a1143cbd69d3a111a4b9a14a5`.
Nothing in that baseline is modified or weakened; all changes are additive.

---

## 1. Objective

Give a recruiter the ability to posts a job opening to LinkedIn from the app:
create job → **Post on LinkedIn** → generate a deterministic draft → preview /
edit → (OAuth connect if needed) → confirm → publish → DB-authoritative status
shown on the job row. Posting is **never automatic**. Company-page posting is
explicitly out of scope and not faked.

## 2. What Was Built

- Server-side **authorization-code OAuth** for LinkedIn, per recruiter (new tab
  consent + server callback). This is the project's first server-rendered
  redirect OAuth flow; the Gmail/Calendar `run_local_server` loopback is
  untouched.
- A **LinkedIn API client** in `app/engine/linkedin.py` speaking only the
  current Posts API (`POST /rest/posts`), never `ugcPosts`, with a single
  pinned `LINKEDIN_API_VERSION` constant.
- A **deterministic post generator** (`app/engine/linkedin_post.py`) — no LLM,
  no invented data; missing fields are omitted.
- **DB-authoritative status** machine on `job_postings`
  (`NOT_POSTED / DRAFT / PUBLISHING / PUBLISHED / FAILED`) with atomic
  single-claim semantics, crash/stale recovery, and publish-state preservation
  across job edits.
- Backend endpoints under `/api/integrations/linkedin` and per-job
  preview/publish under `/api/jobs/{job_id}/linkedin/*`, all ownership-checked.
- Frontend: per-row LinkedIn action + editable preview dialog + status chips
  (Posted / Publishing / Failed / —), plus a Settings connect/disconnect section
  and post-OAuth toast handling.
- `tests/test_linkedin.py` (42 tests) and 10 frontend tests — all HTTP mocked,
  never a real LinkedIn post.
- Configuration addendum in `.env.example` and full operator guide in
  `docs/LINKEDIN.md`.

## 3. Architectural Decisions & Separation of Concerns

| Decision | Rationale |
| --- | --- |
| OAuth tokens **per recruiter** in SQLite (`linkedin_connections`) | Recruiter A must never reuse/publish-as Recruiter B; scales with the machine-global `settings.json` Gmail pattern while scoping correctly. |
| Identity **derived server-side** from `GET /v2/userinfo` (`sub`) at connect time | The frontend never supplies the author URN → no post can be forged as someone else. |
| Client config from env (`dotenv`) | Same convention as `GROQ_API_KEY`; no secrets in `data/client_secret.json`, settings store, or code. |
| All LinkedIn I/O isolated in `app/engine/linkedin.py` | Routes are pure controllers; no HTTP-to-LinkedIn leaks into handlers, easy to mock in tests. |
| Public link reuses existing `/apply?jobId=<id>` + `PUBLIC_APP_URL` | No new public surface; the apply page is already unauthenticated and already exposes the id via copy-link. |
| DB is the source of truth, not the frontend | State survives refresh/crash; the UI merely renders it. |

## 4. LinkedIn API: Endpoints, Version, Headers

- **Create post:** `POST https://api.linkedin.com/rest/posts`
  (current API; the deprecated `ugcPosts`/`/v2/ugcPosts` is **not** used).
- **Headers on every post:** `Authorization: Bearer <token>`,
  `Content-Type: application/json`, `X-Restli-Protocol-Version: 2.0.0`,
  `LinkedIn-Version: <YYYYMM>` — version centralized as
  `LINKEDIN_API_VERSION = "202608"` in `app/engine/linkedin.py:58`
  (one place to bump monthly).
- **Success** = `201` with the created post id in the **`x-restli-id`** header
  (e.g. `urn:li:share:...`); the driver builds the recruiter link
  `https://www.linkedin.com/feed/update/<post_id>`.
- **Identity:** `GET https://api.linkedin.com/v2/userinfo` (OpenID Connect).
  Member author URN = `urn:li:person:{sub}`.
- OAuth: standard authorization-code endpoints
  (`/oauth/v2/authorization`, `/oauth/v2/accessToken`).

## 5. OAuth Flow & Security Controls

Flow: `GET /connect` (recruiter auth) → returns `authorization_url` →
new tab consent → LinkedIn redirects to `GET /callback` → validate → store →
`302 /settings?linkedin=connected`.

- CSRF **state**: generated server-side (`secrets.token_urlsafe(32)`),
  recorded in `linkedin_oauth_states` bound to the recruiter, **single-use**
  (atomic `UPDATE ... WHERE used_at IS NULL` claim) and **TTL-bounded** (10 min).
- **Redirect-URI match**: the callback refuses when the stored `redirect_uri`
  differs from the configured value (mitigates open-redirect / token-theft).
- **Token hygiene**: access/refresh tokens are never returned to the frontend
  (`/status` returns identity only), never logged (`LinkedInError` messages are
  token-free), and deleted on **Disconnect**.
- OAuth failure → safe 302 to `?linkedin=failed&reason=denied`; bad/expired/
  replayed state → `400`. No secrets appear in any response.

## 6. Publication State Machine & Idempotency

- Status transitions are **atomic SQL**: `try_claim_linkedin_publish` flips
  `NOT_POSTED|DRAFT|FAILED → PUBLISHING` in one `UPDATE`; losers get `409` and
  **the LinkedIn API is only ever called by the winning claim** → one post per
  claim under double-click and concurrent retry.
- Success → `PUBLISHED` + `post_id` + `post_url` + `posted_at` + author URN.
- Definitive API rejection → `FAILED` + safe `last_error` (retry allowed).
- **Timeout** → stays `PUBLISHING` + `502` with "verify on LinkedIn before
  retrying": LinkedIn offers no idempotency key, so exactly-once cannot be
  guaranteed across a lost response — the claim auto-expires after **90 s** and
  a documented, deliberate re-publish is then permitted.
- `PUBLISHED` rows **refuse republish** (`409`); editing a job does **not** wipe
  its LinkedIn state (`save_job_posting` preserves the columns).

## 7. Backend API Surface

| Method | Endpoint | Auth | Behavior |
| --- | --- | --- | --- |
| GET | `/api/integrations/linkedin/status` | Recruiter | `{connected, member_name, member_email, connected_at, member_author_urn}` — no tokens |
| GET | `/api/integrations/linkedin/connect` | Recruiter | `{authorization_url}`; records single-use state |
| GET | `/api/integrations/linkedin/callback` | Public | OAuth return; validates, stores, redirects to settings |
| POST | `/api/integrations/linkedin/disconnect` | Recruiter | Removes connection |
| POST | `/api/jobs/{job_id}/linkedin/preview` | Owner (403) | Draft + public URL + status + connected; offline |
| POST | `/api/jobs/{job_id}/linkedin/publish` | Owner (403) | Publish/retry; 404 missing job, 409 state guards, 502 safe errors |

Job ownership (`_owns_job` → `db.job_owned_by`) guards every per-job op.
Content is validated server-side (non-blank, ≤ 3000 chars).

## 8. Post Generation & Public Apply Link

- `generate_linkedin_post(job, url)` emits only **present** fields (title,
  experience level, department, required-skills bullets, description snippet)
  plus the apply link and sanitized hashtags; deterministic and ≤ 3000 chars.
- The apply link is the existing public portal
  `<PUBLIC_APP_URL>/apply?jobId=<job_id>` (`PUBLIC_APP_URL` env, default
  `http://localhost:3000`); it points to the frontend origin, never the backend
  API origin.

## 9. Frontend UX

- **Job Postings row:** LinkedIn icon (title reflects state); status column with
  Posted (link out), Publishing (spinner), Failed (hover shows last error),
  or —. No automatic retry loop anywhere.
- **Preview dialog:** editable textarea, 3000-char counter, public-link display,
  "Publish" disabled until connected + non-blank + within limit; failure toasts
  the safe server message and, on timeout, tells the recruiter to verify on
  LinkedIn first.
- **Settings → LinkedIn Integration:** Connect (opens consent in new tab with
  "return to this app" guidance), identity-only display (author URN, name,
  email), refresh, Disconnect. Handles `?linkedin=connected|failed` query from
  the OAuth redirect with toasts and URL cleanup.

## 10. Automated Testing Coverage

`tests/test_linkedin.py` — **42 tests**, all LinkedIn HTTP mocked (no real post):
status (disconnected / connected / per-recruiter / no-token-leak), connect
(authorization URL + state persistence / not-configured → 503), callback (happy
path stores connection / OAuth-deny redirect / bad state / replay / expired /
redirect-URI mismatch / exchange failure), disconnect, preview (offline +
deterministic + owner 403 + 404 + published-state reflection), publish (success
with backend-derived author / not connected / already-published refuses second
API call / parametrized 401-403-429-5xx → FAILED / timeout stays PUBLISHING then
fresh-block then stale-recovery / owner / 404 / blank & oversized content / not
configured / edit preserves published state), and engine unit tests
(posts request headers + `x-restli-id` parsing / errors / timeout, token
exchange, userinfo 403, determinism & missing-field omission).

Frontend — **10 tests** (`jobs/__tests__/linkedin-post.test.tsx`,
`settings/__tests__/linkedin-settings.test.tsx`, mock `@/lib/api`): preview+
publish edited content (posts the right URL), connect-prompt gating, failure
toast, open-live-post for PUBLISHED, timeout "verify" info toast, Failed badge,
connect button/new-tab open, misconfiguration surfacing, connected display with
no credential leakage, disconnect.

## 11. Regression Verification

- Backend suite: **342 passed** (baseline 300 + 42 new) — `pytest -q`.
- Frontend suite: **35 passed** (baseline 25 + 10 new) — `vitest run`.
- `npx tsc --noEmit`: **clean**; `npm run build`: **clean**.
- No existing test modified to pass (the only pre-existing test edit is adding
  the required `getLinkedinStatus` stub to the copy-link mock object, required
  because the page now renders a new API surface). No Gmail/Calendar OAuth,
  screening, candidate, scheduling, or public apply logic was changed.

## 12. Company Page (Organization) Posting — Status

**NOT IMPLEMENTED (deliberately).** Posting to a Company page requires the
`w_organization_social` scope, explicit roles on the target organization
(`ADMINISTRATOR` / `DIRECT_SPONSORED_CONTENT_POSTER`), and a separate
organization-URN resolution. The integration is **member-profile posting only**;
it does not fake, guess, or impersonate an organization author.

## 13. Known Limitations & Risks

- Exactly-once is guaranteed per claim, **not** across transport timeouts
  (no LinkedIn idempotency key) — handled with the PUBLISHING + verify +
  stale-reclaim model documented above.
- Tokens are stored **plaintext at rest** in SQLite per recruiter (same
  convention as the pre-existing Gmail/Calendar tokens) — documented in
  `docs/LINKEDIN.md`.
- `LINKEDIN_API_VERSION` is pinned (`"202608"`); LinkedIn may require a bump —
  a single-tiered constant update.
- Refresh tokens only apply when LinkedIn grants them to approved partners; the
  connection keeps the access token and the UI shows status from the DB.
- Public apply link assumes `PUBLIC_APP_URL` is set in deployment; defaults to
  the local dev origin.

## 14. Verdict

**LINKEDIN MEMBER POSTING READY** — the recruiter flow
(connect → generate → preview/edit → publish → status) is implemented, tested,
and safe by the criteria of the specification. Organization/company-page posting
remains **NOT AVAILABLE** by design and is not claimed.