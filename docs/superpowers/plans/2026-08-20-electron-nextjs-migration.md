# Electron + Next.js + FastAPI Implementation Plan

> **For agentic workers:** Use subagent-driven-development to implement this plan task-by-task.

**Goal:** Replace PySide6 UI with Electron + Next.js + Tailwind + shadcn/ui, wrapping existing Python as FastAPI.

**Architecture:** Electron spawns FastAPI child process, Next.js static export loaded in BrowserWindow, all API calls via fetch() to localhost.

**Tech Stack:** Electron 33, Next.js 14, Tailwind CSS 3.4, shadcn/ui, FastAPI, uvicorn, TypeScript, Python 3

**Spec:** `docs/superpowers/specs/2026-08-20-electron-nextjs-migration-design.md`

## Global Constraints
- Existing `app/` directory: ZERO modifications
- Python additions only in new `api/` directory
- Windows platform primary target
- All API responses JSON via Pydantic models
- Electron spawns FastAPI on random port, waits for /health

---

## Phase 1: Project Scaffolding

### Task 1: Root package.json + workspace config
**Files:** Create `package.json` (root)
- [ ] Create root package.json with workspace scripts for electron/ and frontend/

### Task 2: FastAPI scaffolding
**Files:** Create `api/__init__.py`, `api/main.py`, `api/dependencies.py`, `api/schemas.py`
- [ ] Create `api/__init__.py` (empty)
- [ ] Create `api/main.py` with FastAPI app, CORS, health endpoint, lifespan (init_db)
- [ ] Create `api/schemas.py` with all Pydantic models
- [ ] Update `requirements.txt` to add fastapi, uvicorn[standard], python-multipart, websockets
- [ ] Test: `python -m api.main` starts and responds to /health

### Task 3: FastAPI route modules
**Files:** Create `api/routes/__init__.py`, `api/routes/auth.py`, `api/routes/jobs.py`, `api/routes/candidates.py`, `api/routes/sessions.py`, `api/routes/scoring.py`, `api/routes/reports.py`, `api/routes/integrity.py`, `api/routes/settings.py`, `api/routes/devices.py`
- [ ] Create all route files with endpoint functions calling existing app/ modules
- [ ] Register all routers in api/main.py

### Task 4: Next.js scaffolding
**Files:** Create `frontend/` with Next.js app, tailwind, shadcn
- [ ] Initialize Next.js project in frontend/
- [ ] Configure tailwind.config.ts with custom theme colors
- [ ] Install and configure shadcn/ui (New York style)
- [ ] Install shadcn components: button, card, input, label, select, badge, dialog, table, tabs, slider, switch, separator, scroll-area, sonner, dropdown-menu, avatar, progress

### Task 5: Electron scaffolding
**Files:** Create `electron/main.ts`, `electron/preload.ts`, `electron/package.json`, `electron/forge.config.ts`, `electron/tsconfig.json`
- [ ] Create electron package.json with electron, electron-builder deps
- [ ] Create main.ts: spawn FastAPI, health check, create BrowserWindow
- [ ] Create preload.ts: expose desktopCapturer via contextBridge
- [ ] Create forge.config.ts for build/packaging

---

## Phase 2: Frontend Core Infrastructure

### Task 6: API client + types
**Files:** Create `frontend/lib/api.ts`, `frontend/lib/types.ts`, `frontend/lib/utils.ts`
- [ ] Create TypeScript types matching all Pydantic schemas
- [ ] Create api.ts fetch wrapper with base URL from env or default localhost
- [ ] Create utils.ts with cn() helper and date formatting

### Task 7: Layout + Sidebar + Login page
**Files:** Create `frontend/app/layout.tsx`, `frontend/components/sidebar.tsx`, `frontend/app/login/page.tsx`
- [ ] Root layout with sidebar, Toaster, font setup
- [ ] Sidebar component matching existing nav items (8 items)
- [ ] Login page with card-centered form, tab toggle login/register
- [ ] Auth state management (localStorage token or simple flag)

### Task 8: Dashboard page
**Files:** Create `frontend/app/dashboard/page.tsx`, `frontend/components/stat-card.tsx`
- [ ] Fetch /api/reports/dashboard on mount
- [ ] 5 stat cards: interviews, avg score, bias flags, integrity flags, candidates
- [ ] Job posting list table below

---

## Phase 3: CRUD Pages

### Task 9: Job Postings page
**Files:** Create `frontend/app/jobs/page.tsx`
- [ ] Form: title, description, skills, experience level, department, rounds, time limit, adaptive toggle
- [ ] Competency weight sliders (5 categories, validate sum=100)
- [ ] Existing postings table with Edit/Delete actions
- [ ] Edit populates form, Delete shows confirmation dialog

### Task 10: Candidates page
**Files:** Create `frontend/app/candidates/page.tsx`
- [ ] Candidate list table with status badges
- [ ] Invite dialog (name, email, select job posting)
- [ ] Actions: copy invite code, resend, revoke, attach resume
- [ ] Resume upload triggers parse + match pipeline

### Task 11: Settings page
**Files:** Create `frontend/app/settings/page.tsx`
- [ ] Fetch /api/devices for camera/mic dropdowns
- [ ] Form: camera select, mic select, LLM provider, API key, export dir
- [ ] Save calls PUT /api/settings

---

## Phase 4: Interview & Reports

### Task 12: Interview page
**Files:** Create `frontend/app/interview/page.tsx`
- [ ] Webcam preview via desktopCapturer (Electron) or placeholder
- [ ] Question navigation (Previous/Next)
- [ ] Live transcript display area
- [ ] Integrity status badge with flag count
- [ ] Start/Stop session controls

### Task 13: Reports page
**Files:** Create `frontend/app/reports/page.tsx`, `frontend/components/score-breakdown.tsx`
- [ ] Tabs: Sessions | Comparison
- [ ] Session list with click to view details
- [ ] Score breakdown: competency scores + explanations
- [ ] PDF download button, CSV export button
- [ ] Comparison table ranked by overall score

### Task 14: Bias Audit page
**Files:** Create `frontend/app/bias-audit/page.tsx`
- [ ] Fetch /api/bias/flags
- [ ] Table with candidate name, job, question, score delta, note
- [ ] Delta badges (green for low, amber for medium, red for high)
- [ ] Summary stats at top

### Task 15: Integrity Log page
**Files:** Create `frontend/app/integrity/page.tsx`
- [ ] Fetch /api/integrity/flags
- [ ] Table with candidate, job, flag type, detail, severity, timestamp
- [ ] Severity badges (color-coded)
- [ ] Summary stats at top

---

## Phase 5: Integration & Polish

### Task 16: Electron + FastAPI integration
**Files:** Modify `electron/main.ts`
- [ ] Ensure FastAPI child process spawns correctly
- [ ] Health check polling with timeout
- [ ] Graceful shutdown on app quit
- [ ] Dev mode: load localhost:3000, prod: load file://

### Task 17: Build scripts + final wiring
**Files:** Root `package.json`, `electron-builder.yml`
- [ ] npm scripts: dev, build, start, package
- [ ] electron-builder config for Windows .exe
- [ ] Verify full flow: login → create job → invite candidate → run interview → view reports
