# Core Pipeline Stabilization Report

## 1. Verdict

```
CORE PIPELINE READY
```

The application pipeline — job creation → public/email application intake →
resume parsing → JD matching → LLM fallback → hard-requirement gating →
threshold decision → candidate + auto-invite → outbox → Gmail delivery →
calendar scheduling → recruiter visibility — is verified end-to-end. Three
reproducible authorization/data-integrity bugs and one reporting bug were
found during verification; all four are fixed, each with a regression test.
Full backend suite: **300 passed** (baseline 296 + 4 new). Frontend: vitest
**25 passed**, `tsc --noEmit` clean, production build clean.

## 2. Scope & method

- Verified every phase by inspection, existing test audit, and — for each bug —
  a reproduction script **before** the fix, followed by a regression test after.
- No changes to LinkedIn, no UI redesign, no unrelated refactoring, no further
  OAuth changes. OAuth cleanup from previous work is present but untouched here.
- Rule enforced throughout: **a processing failure must never surface as
  "passed screening"** or as an accepted candidate. No such silent-pass path
  exists (see §7 residual risks for the one quoted counterfactual, which is
  dead code, not live pipeline).

## 3. How verification was performed

- `python -m pytest -q` — full suite (159.7 s, 1466 warnings, all pre-existing
  deprecation warnings).
- `npx vitest run`, `npx tsc --noEmit`, `npm run build` in `frontend/`.
- Targeted suites after each fix (see §8 for the exact commands).
- Ad-hoc reproduction scripts under a temp directory (not committed) that
  demonstrated each bug before the fix was applied.

## 4. Bugs found & fixed (each reproduced before fixing)

### 4.1 Job takeover via `POST /api/jobs` (Phase 11)
Clients could supply an arbitrary `job_id`. Because `job_postings.job_id` is the
primary key and `save_job_posting` uses `INSERT OR REPLACE` keyed on it, one
recruiter could `POST /api/jobs` with the `job_id` of another recruiter's job
and silently take over/recreate it (ownership is on `created_by`).
**Fix** (`api/routes/jobs.py`): `create_job` now returns **409** when the
supplied `job_id` already exists; unknown ids are honored; blank ids get
`db.generate_job_id()`. The frontend only ever sends `job_id` on PUT
(ownership-checked), never on create (`JobCreateInput = Omit<JobPosting,
"job_id">`), so this guard does not affect the real flow.
**Regression test**: `test_jobs_contract.py::test_create_cannot_hijack_existing_job_via_client_job_id`.

### 4.2 Candidate hijack via `POST /api/candidates` (Phase 11)
`save_candidate` upserts on the `candidate_id` primary key, and the frontend's
candidate creation sends `candidate_id: Date.now().toString()` (client-originated).
`create_candidate` trusted the client id, so recruiter B could submit a
`candidate_id` that already belonged to recruiter A's candidate on a different
job and silently **repoint that candidate** to B's job (with B's name/email).
Repro: A creates candidate `c1` under `job-a`; B creates `job-b` and POSTs
`candidate_id: c1, job_id: job-b` → A's candidate row is overwritten.
**Fix** (`api/routes/candidates.py`): when a row already exists for the
given `candidate_id`, creation returns **409** if its `job_id` differs from the
requested job. Since the job itself was already ownership-403-checked, this
fully blocks the hijack while preserving the same-recruiter same-job upsert
that the frontend relies on.
**Regression test**: `test_security_auth.py::test_create_candidate_cannot_repoint_existing_candidate_to_another_job`.

### 4.3 Application never linked when screening reuses a pre-existing candidate (Phase 7)
If a candidate row already existed for `(email, job)` — e.g. the recruiter
manually pre-invited the person — `_ensure_candidate` returned it immediately,
but never linked the newly screened application
(`application.candidate_id` stayed `None`, and the candidate's
`application_id` stayed unset). The parallel "race adoption" branch *did*
call `update_application_candidate`. Repro confirmed:
`application.candidate_id: None` after a passed screen on a manual pre-invite.
**Fix** (`app/screening/service.py::_ensure_candidate`): the reuse path now
links the application to the reused candidate too, mirroring the adoption
branch. Invites still go out through the same candidate row.
**Regression test**: `test_screening_service.py::test_screen_reuses_preexisting_candidate_and_links_application`.

### 4.4 Wrong status counts in "Check Job" summary and poll log (Phase 9)
`trigger_email_check` and `_background_poll` tallied statuses
`below_threshold` / `invite_send_failed` that `check_for_new_applications`
never emits (its real statuses: `invited`, `not_shortlisted`, `skipped`,
`duplicate`, `error`), so genuine processing errors were shown as "skipped"
in the manual summary and could be reported as successes of the wrong bucket.
**Fix** (`app/engine/email_intake.py`): added `summarize_poll_results()`, which
maps only the emitted statuses and folds `skipped`+`duplicate` together and
`error` into the failed count; wired into `api/routes/email_intake.py` and
`api/main.py`. Frontend only displays the summary string (no parsing) — safe.
**Regression test**: `tests/test_email_intake.py::TestEmailCheckSummary::test_manual_check_counts_emitted_statuses_and_writes_poll_log`.

## 5. Phase-by-phase verification

| # | Phase | Verdict | Evidence |
|---|-------|---------|----------|
| 1 | Pipeline mapping | OK | Canonical flow traced (see §6) |
| 2 | Baseline suite | OK | 296 passed before this session's fixes |
| 3 | Intake / public apply, corrupt resumes (Edge A) | OK | `test_public_apply.py` — store-first 202, corrupt/invalid resume never passes screening |
| 4 | JD matching + hard-requirement gating (Edge B) | OK | `test_public_apply.py`, `test_screening_business_rules.py` — hard gates independent of ATS; high score still fails a missed gate |
| 5 | LLM path | OK | `test_llm_path.py` — JSON fenced/preamble parsing, timeout→retry→heuristic, 4xx-no-retry/5xx-retry, no-key→heuristic |
| 6 | Threshold → reject / manual_review (Edge C) | OK | `test_screening_business_rules.py` — spectrum, threshold boundary, screening-disabled → manual_review, `screening_disabled` event |
| 7 | Candidate + invite creation/reuse | FIXED (4.3) | reuse/link regression test + invite-to-existing-candidate test |
| 8 | Outbox + invite send idempotency | OK | `test_email_intake.py`, `test_screening_service.py` — retry caps, stale-`sending` reclaim, Gmail-down non-blocking, INSERT OR IGNORE |
| 9 | Poll summary counts (Check Job) | FIXED (4.4) | new summary + poll-log regression test |
| 10 | Scheduling | OK | `test_scheduling.py` — `allocate_next_slot` idempotency, no double-book on error |
| 11 | Authorization (own jobs/candidates) | FIXED (4.1, 4.2) | 409 regression tests; cross-recruiter shortlists empty; 403 on foreign job |
| 12 | Rescreen visibility flip | OK | flip test — declined candidate hidden, row retained, admin ops intact |
| 13 | Pipeline visibility / stats | OK | `test_pipeline_visibility.py`, e2e smoke — recruit shortlist == passed shortlist |
| 14 | Regression coverage for all fixes | OK | 4 new tests (all assembled in §8) |
| 15 | Final E2E + full suite | OK | `test_e2e_smoke.py` full-flow; suite 300 passed |

## 6. Verified canonical flow

`POST /api/jobs` (owned) → `POST /api/public/apply/:job_id` or email
intake → `create_public_application_row` / `create_application_and_queue`
(store-first 202) → queue → worker daemon `run_screening_jobs` →
`screen_application`: parse (PDF/TXT/DOCX) → heuristic `match_resume_to_jd` →
(skills ∪ required ∨ LLM) → component scores → hard-requirement gating →
`decide()` (`>= threshold` → qualified; `[threshold-10, threshold)` →
manual_review; below → rejected; `ats_score=None` → manual_review) → result
UPSERT → `_ensure_candidate` (one candidate per `(email, job)`) →
`_ensure_interview_invite` (invite reuse, never resent) → outbox
`INSERT OR IGNORE` → `send_pending_notifications` → Gmail + `allocate_next_slot`
(idempotent). Workers are daemon threads from the FastAPI lifespan and are
disabled by `INTERVIEWIQ_DISABLE_WORKERS=1` in tests; Gmail auto-poll
(`_background_poll`) runs every 10 min in remote mode.

## 7. Residual risks / accepted limitations (NOT fixed — out of scope)

- **Dead legacy code**: `app/engine/application_processor.py` is not on the
  runtime path, but contains a latent bug (below-threshold → `status="invited"`).
  Only referenced by `test_scheduling.py`. Left untouched; recommend deletion.
- Heuristic `match_resume_to_jd` returns `0.0` when a job's JD contains no
  recognizable `COMMON_SKILLS` and the resume has none either → valid candidates
  can be rejected. This fails safe (reject, never silent-pass) but under-matches
  skill-light JDs.
- A 15-minute stale-`sending` reclaim window in outbox send can, in theory,
  re-send a genuinely delivered invite (capped at 3 attempts). Acknowledged risk.
- Email auto-intake does not check `job.is_active`; relies on the job being
  discoverable by label.
- Public apply trusts client `content_type` (renamed-file DoS only; malformed
  files fail cleanly with an `error` result, never a pass).
- `check_for_new_applications` screens inline (synchronous) — slow for large
  batches but non-crashing (per-message try/except).
- OAuth cleanup from the prior session remains uncommitted and unchanged.

## 8. Changed files & verification commands

Fix locations (all uncommitted):
- `api/routes/jobs.py` — 409 guard in `create_job` (4.1)
- `api/routes/candidates.py` — 409 cross-job guard in `create_candidate` (4.2)
- `app/screening/service.py` — application↔candidate link on reuse (4.3)
- `app/engine/email_intake.py`, `api/routes/email_intake.py`, `api/main.py` — `summarize_poll_results` (4.4)

Regression tests:
- `tests/test_jobs_contract.py` — job takeover
- `tests/test_security_auth.py` — candidate hijack
- `tests/test_screening_service.py` — candidate reuse/link
- `tests/test_email_intake.py` — summary + poll log (file structure repaired while auditing)

Commands run:
```
python -m pytest tests/test_email_intake.py -q                                  # 7 passed
python -m pytest tests/test_screening_service.py -q                             # 18 passed
python -m pytest tests/test_security_auth.py -q                                 # 17 passed
python -m pytest tests/test_jobs_contract.py -q                                 # 6 passed
python -m pytest -q                                                             # 300 passed
npx vitest run                                                                  # 25 passed
npx tsc --noEmit                                                                # clean
npm run build                                                                   # clean
```

## 9. Conclusion

Every phase of the core pipeline is verified; the four discovered defects are
fixed with full reproduction evidence and regression coverage; nothing was
changed in the frontend, and no functioning code path can report a failed
screening as a pass.

```
CORE PIPELINE READY
```