# WORKFLOW VERIFICATION — CURRENT

**Date:** 2026-09-01
**Mode:** READ-ONLY audit. No product code / tests / config were modified. The only write is this document.

---

## VERDICT: **NOT READY**

One **P1** finding remains: the "completed interview cannot be reopened" guarantee (the flagship
F-01 property) is **only enforced at `start-session` and `validate-code`**. A candidate who holds a
still-valid interview token (4h lifetime) can re-enter a *completed* interview through the
`consent` endpoint, flip their own recruiter-visible status back to `in_progress`, overwrite
recorded answers (which re-scores them), and re-complete the session (resetting `completed_at`).
Confirmed end-to-end against a live server. Everything else in the 3→9, 11→13, 16→17 runtime
matrix passes (146/146 runtime checks, 0 failures).

---

## Method / Environment

- Backend booted in isolation: `INTERVIEWIQ_DATA_DIR=…temp\opencode\interviewiq_audit\data` (seeded),
  `uvicorn api.main:app` on `127.0.0.1:8091`, single fresh DB per full run.
- One driver script (`run_audit.py`) wipes the data dir, spawns the server and all phase scripts in
  one process tree (child processes are killed between shell calls, so a single tree is mandatory).
- Checks are runtime API calls against the live server; DB assertions via warm sqlite queries; STT
  via a real TTS-generated speech fixture (faster-whisper base cached locally, fully offline).

## Runtime results (fresh clean run, 2026-09-01)

| Phase | Scope | Result |
|---|---|---|
| 2 | Checked-in suites still pass | PASS (backend 422, frontend 35, `tsc --noEmit` clean) |
| 3 | Recruiter workflow + authz matrix | **49 PASS / 0 FAIL** (incl. cross-recruiter 403 on job/candidate write+read, list isolation, 401 token classes, 409 candidate-id-reuse) |
| 4 | Public apply + ATS screening | **PASS**: strong resume → ATS 100.0 (skills 100 / semantic 100), `invite_pending`; duplicate → 409; weak → rejected 0.0, no candidate row; funnel/leak checks pass |
| 5 | Email / notification outbox | **PASS**: shortlist email enqueued (`interview_invite`, explicit subject, candidate recipient, invite code embedded), stays `pending` when Gmail absent (failure isolation), rejected candidate gets none, resend rotates code |
| 6 | Invite auth | **PASS**: code→token, invalid code refused, interview token rejected on recruiter routes (401) |
| 7 | Mode 2 interview (screened candidate) | **PASS (24 checks)**: consent→authoritative session, question lock immutable (API==DB), answers scored + transcripts stored + progress/resume, complete blocked until 3/3, `completed_at` stamped |
| 8 | P2 reopen regression | **PASS on the covered surface**: `start-session` on completed → 409, state unchanged, no new session, `validate-code` refuses completed candidate. **BUT incomplete — see P1** |
| 9 | Answer scoring | **PASS**: range, duplicate-submit idempotent (1 score row), non-locked question 403, cross-candidate 403, missing token 401, recruiter-as-candidate 401 |
| 10 | STT | **PASS**: real speech transcribed (5/5 word overlap), persisted; garbage audio handled (500, logged) |
| 11 | Mode 1 live (WebSocket) | **PASS (14 checks)**: candidate/recruiter roles, role-lock (candidate ask_question rejected), question broadcast, transcript relay, end→both `completed`, 4403/4401 auth matrix, session persisted `completed` |
| 12 | Media / integrity | **PASS (16 checks)**: sign ownership + traversal + bad-sig 403s, recording upload saved, cross-session upload 403, empty live-frame 400, flag batch saved, cross-session flag 403, recruiter sees flags |
| 13 | Reports | **PASS**: dashboard aggregate, candidate report (overall + 3 scores + 3 explanations), compare, CSV (header+data), valid PDF, recruiter B denied on all 4 surfaces |
| 14–15 | Frontend pages | PASS (checked-in): PHASE15 completion report on file; frontend suite 35 passed / 8 files; `tsc --noEmit` clean. Not re-run in this audit |
| 16 | Security matrix | **PASS (8 checks)**: expired/tampered/malformed recruiter + expired interview token → 401, no crash; cross-recruiter 403s; session-list isolation |
| 17 | DB consistency | **PASS (12 checks)**: 3/3 sessions completed, `job_id`/`session_id` resolution, score uniqueness, explanations 1:1, transcripts ≥ scored answers, applications=2, candidates=3, invite consumed exactly once (`consumed_at`), recruiter-B flag isolation |
| 18–19 | Electron / startup | PARTIAL (static+verified pieces): `electron/main.ts` + preload + integrity present **and built** (`electron/dist/main.js` on disk, package.json `main` matches); backend startup (`python -m uvicorn api.main:app`) verified live many times; desktop launcher not executed headlessly |

**Total runtime: PASS=146, FAIL=0, INFO=3.**

## Findings

### P1 — Completed interviews remain mutable via `consent` (data-integrity / F-01 bypass)
Repro (live server, fresh completed Mode-2 session `5932a852` for `cand-manual-1`, token valid):

- `POST /api/candidate/consent` with completed candidate's token → `200`, candidate status flipped
  `completed → in_progress` (`candidate_flow.py:206` runs `update_candidate_status(…, "in_progress")`
  with no completed-state check).
- `POST /api/candidate/submit-answer` on the completed session → `200` (new transcript + re-score stored).
- `POST /api/candidate/complete-session` on the completed session → `200`, `completed_at` reset
  `20:13:45 → 20:17:56`.

Only `start-session` (`candidate_flow.py:226`) and `validate-code` guard `completed`; `consent`
(:206), `submit_answer` (:293) and `complete_session` (:375) do not. The regression test added for
the original P1 only exercises `start-session` (409), so it passes while the invariant still leaks.
**Fix direction (for the product owner, not applied):** short-circuit consent/submit/complete on
`session.status == "completed"` (or `candidate.status == "completed"`), same as start-session.

### P2 — LLM scoring frequently falls back to heuristic in this environment
`server.err.log` during runs shows `score_answer[…]: LLM scoring failed (HTTPError: 429…) - falling
back to heuristic`; `scoring.py` catches and falls back (:83-90). Scoring stays valid and idempotent,
but out-of-the-box score "smartness" depends on a Groq key that is being rate-limited (429) in this
environment. Verify key capacity/quota before launch; heuristic fallback is graceful (P2, not P1).

### P3 — Observations (cosmetic / low)
- Mode-1 (WS) sessions finish `status=completed` but `sessions.completed_at` stays NULL
  (`live.py` end_interview does not stamp it) — inconsistent with Mode 2 reporting.
- Funnel `shortlisted` counts *candidate rows*, so a manually-created candidate inflates it (here 2
  with 1 passed application); wording can mislead.
- Shortlist email subject renders `you've been shortlisted … — Senior…` (em dash); the `�` seen in
  console output is a Windows codepage render artifact, not a payload issue.

## Evidence artifacts

- Audit workspace: `C:\Users\athar\AppData\Local\Temp\opencode\interviewiq_audit\`
  (`run_audit.py`, `phase36.py`, `phase78.py`, `phase913.py`, `state.json`, isolated `data/app.db`,
  `server.out/.err.log`, `speech_fixture.wav`).
- Full clean run: phase36 `49 PASS/0`, phase78 `38 PASS/0`, phase913 `59 PASS/0`.
- Bypass probes: `probe_consent.py`, `probe_bypass.py` (consent→100-status flip, submit-answer 200,
  complete-session 200 + `completed_at` reset).
- Repo locations referenced: `api/routes/candidate_flow.py` (:206,:226,:293,:375), `app/engine/scoring.py`
  (:83-91), `app/core/db.py` (:2220-2238).

## Reproduce the audit

```
cd C:\Users\athar\AppData\Local\Temp\opencode\interviewiq_audit
& D:\Majorrrr\interview-assessment-system\venv\Scripts\python.exe -u run_audit.py
```
Then re-run `probe_consent.py` + `probe_bypass.py` (via `run_probe.py`) against the fresh DB to see
the P1 bypass, or add consent/submit/complete assertions to the F-01 regression to watch it fail.