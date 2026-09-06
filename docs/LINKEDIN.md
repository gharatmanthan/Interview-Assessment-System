# LinkedIn Integration (Member Posting)

Recruiters can post a job opening to their own LinkedIn feed directly from the
**Job Postings** page. This document covers setup, the OAuth flow, what the
integration can and cannot do, and the manual verification checklist.

## What it does

1. Recruiter clicks **Post on LinkedIn** on a job row. A deterministic draft is
   generated from the job itself (title, experience level, department, skills,
   description snippet) plus the **public application link**.
2. The draft is **editable** in the preview dialog; the recruiter confirms.
3. If no LinkedIn account is linked yet, the recruiter is sent to **Settings →
   LinkedIn Integration → Connect LinkedIn**, which opens LinkedIn consent in a
   new tab (server-side authorization-code flow).
4. On confirm, the backend publishes the text post to the **recruiter's own
   profile** via the current LinkedIn Posts API (`POST /rest/posts`), stores the
   post URL/status, and the job row shows **Posted** with a link to the live post.

Posting is **never automatic** — there is no auto-publish. Every post requires a
recruiter decision.

## Prerequisites / app setup

1. Go to <https://www.linkedin.com/developers/apps> → **Create app**.
2. In **Products**, add:
   - **Sign In with LinkedIn using OpenID Connect** (provides `openid profile
     email` — used to resolve the authenticated member identity)
   - **Share on LinkedIn** (provides `w_member_social` — used to create posts)
3. Under **Auth**, register the redirect URI **exactly** (no trailing slash):
   ```
   <YOUR_BACKEND_ORIGIN>/api/integrations/linkedin/callback
   ```
   For the local Electron setup this is the FastAPI sidecar origin, e.g.
   `http://localhost:8000/api/integrations/linkedin/callback`.
4. Copy `.env.example` → `.env` and set:

   | Variable                  | Meaning                                                        |
   | ------------------------- | -------------------------------------------------------------- |
   | `LINKEDIN_CLIENT_ID`      | LinkedIn app client id                                          |
   | `LINKEDIN_CLIENT_SECRET`  | LinkedIn app client secret (never commit)                       |
   | `LINKEDIN_REDIRECT_URI`   | Must equal the registered redirect URI exactly                  |
   | `PUBLIC_APP_URL`          | Public origin serving `/apply` and `/settings` (default `http://localhost:3000`) |

   `LINKEDIN_*` values are read by the backend from the environment via dotenv,
   in the same file that holds `GROQ_API_KEY`. Never hardcode a secret in code.

## Permissions / scopes

- Required scopes: `openid profile email w_member_social`.
- The member author URN (`urn:li:person:<id>`) is **derived server-side** from
  the OpenID `sub` returned by `GET /v2/userinfo` at connect time. The frontend
  never supplies it.
- Tokens are stored **per recruiter** in SQLite (`linkedin_connections`), the
  same convention as the machine-wide Gmail/Calendar tokens: **plaintext at
  rest**. They are never sent to the frontend, never logged, and are deleted on
  **Disconnect**.
- This integration does **not** use the deprecated `ugcPosts` API. It targets
  `POST https://api.linkedin.com/rest/posts` with the `LinkedIn-Version` header,
  encoded as a single constant in `app/engine/linkedin.py`
  (`LINKEDIN_API_VERSION`).

## Company page (organization) posting — NOT implemented

Posting to a Company/Organization page would require the
**`w_organization_social`** product scope, roles on the target organization
(`ADMINISTRATOR` or `DIRECT_SPONSORED_CONTENT_POSTER`), and a separate
organization/URN resolution flow. None of that is implemented or faked: the
integration is **member-profile posting only** by explicit design. Posts are
published with the recruiter's personal profile as author.

## OAuth flow (server-side, CSRF-protected)

- `GET /api/integrations/linkedin/connect` (recruiter-auth) returns
  `authorization_url`. It generates a **single-use, TTL-bounded (10 min) state
  token** stored in `linkedin_oauth_states`, tied to the recruiter.
- `GET /api/integrations/linkedin/callback` (public) validates that the state is
  **unused, unexpired**, and that the redirect URI matches the configured value,
  exchanges the code, resolves the member identity, stores the connection
  (upsert keyed by recruiter username), and 302-redirects to
  `<PUBLIC_APP_URL>/settings?linkedin=connected` (or `...=failed`).
- `POST /api/integrations/linkedin/disconnect` removes the recruiter's
  connection (tokens included).
- The Gmail/Calendar OAuth loopback (`run_local_server`) is untouched.

## Publication contract (post-once, DB-authoritative)

Publication state lives on `job_postings` (status `NOT_POSTED` / `DRAFT` /
`PUBLISHING` / `PUBLISHED` / `FAILED`). It is the single source of truth:

- A **`PUBLISHED`** job refuses republish (`409`).
- The first publish **atomically claims** the job (`NOT_POSTED|DRAFT|FAILED` →
  `PUBLISHING`) — concurrent/double-click publishes get `409` and the LinkedIn
  API is called **at most once** per claim.
- A **definitive API rejection** (4xx / 5xx) marks the job `FAILED` with a safe,
  recruiter-readable error and the row still shows **Retry**.
- A **transport timeout** leaves the job in `PUBLISHING` and returns `502`: the
  post may have been accepted. The UI tells the recruiter to verify on LinkedIn
  before retrying. A timed-out claim **expires after 90 s**, after which retry
  is permitted (this is the honest description of the exactly-once limitation:
  there is no LinkedIn idempotency key).
- Editing a job does **not** clear its LinkedIn state (`save_job_posting`
  preserves the published columns).

## Manual test checklist

With real credentials, against the running app:

1. Set the four env vars above and restart the backend/frontend.
2. **Settings** shows *Connect LinkedIn*. Click **Connect LinkedIn** → a LinkedIn
   consent tab opens → approve with a test account.
3. Return to Settings: status shows *Connected as <name> (<email>)* and the
   member URN. Verify **no token/secret text appears anywhere** in the UI or
   network tab.
4. Create a job → Job Postings → **Post on LinkedIn**. The preview shows a
   deterministic draft containing the title/skills and the public
   `<PUBLIC_APP_URL>/apply?jobId=<id>` link. Edit it. The character counter caps
   at 3000.
5. **Publish** → success toast → post link opens on LinkedIn. The row now shows
   *Posted* linking to the live post.
6. Click **Post on LinkedIn** again on the same job → the live post opens; the
   publish call is refused (`409`).
7. Force a 4xx/5xx (e.g. revoke the token in dev); publish → row shows *Failed*
   with a readable reason; **Retry** after reconnecting works.
8. **Disconnect** in Settings → connection removed; publishing now asks to
   reconnect; no stale token remains in `linkedin_connections`.
9. Open the cell on the [Phone]/[Browser]: the `/apply` link is publicly
   reachable without recruiter auth.

Do **not** run the automated checks against a real account: the backend test
suite (`tests/test_linkedin.py`) mocks the HTTP surface and never touches a real
post.

## Endpoint index

| Method | Endpoint                                       | Auth      | Purpose                                  |
| ------ | ---------------------------------------------- | --------- | ---------------------------------------- |
| GET    | `/api/integrations/linkedin/status`            | Recruiter | Connection/metadata (no tokens)          |
| GET    | `/api/integrations/linkedin/connect`           | Recruiter | Start OAuth; returns consent URL         |
| GET    | `/api/integrations/linkedin/callback`          | Public    | OAuth return; validates + stores tokens  |
| POST   | `/api/integrations/linkedin/disconnect`        | Recruiter | Remove the recruiter's connection        |
| POST   | `/api/jobs/{job_id}/linkedin/preview`          | Owner     | Deterministic draft + public URL + state |
| POST   | `/api/jobs/{job_id}/linkedin/publish`          | Owner     | Publish/retry the editable commentary    |

## Known limitations (honest)

- Member-profile posting only; no company page posting (see above).
- LinkedIn does not provide an idempotency key for post creation; the backend
  guarantees at-most-once **per claim**, not exactly-once across crashes/timeouts.
- Tokens are stored plaintext at rest (same convention as the existing
  Gmail/Calendar tokens), per-recruiter scoped.
- The LinkedIn API version header is pinned in one constant
  (`LINKEDIN_API_VERSION = "202608"`); if LinkedIn rejects posts with a version
  error, update that single value.