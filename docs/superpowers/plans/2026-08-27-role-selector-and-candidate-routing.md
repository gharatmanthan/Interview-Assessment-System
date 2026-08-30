# Role Selector + Candidate Routing Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a role-selector landing screen to the web frontend so both recruiters and candidates can reach their respective flows, and set up frontend testing to verify routing behavior.

**Architecture:** The root route (`/`) currently hard-redirects to `/login` or `/dashboard` with no choice. Replace it with a centered two-card role-selector screen (mirroring the existing desktop `role_select_window.py`). Candidate flow pages already exist and work — no backend changes needed. Add Vitest + React Testing Library to verify routing.

**Tech Stack:** Next.js 14, React 18, Tailwind CSS, Vitest, @testing-library/react, @testing-library/jest-dom

**Spec:** User-reported bug — no role selector on web launch, candidate flow unreachable from entry point.

## Investigation Findings

1. **Root cause**: `frontend/app/page.tsx` unconditionally redirects to `/dashboard` (if `localStorage.username` exists) or `/login` (if not). No role selector exists in the web frontend.
2. **Candidate routes are NOT blocked**: `/candidate/*` pages use individual `sessionStorage` guards that redirect to `/candidate/entry` if state is missing. No global middleware or auth guard exists (`middleware.ts` does not exist).
3. **Candidate flow is complete**: All 5 pages exist (`entry`, `consent`, `device-check`, `interview`, `done`) and backend tests pass. The only gap is the missing entry point.
4. **Desktop has this feature**: `app/ui/role_select_window.py` shows the exact design — two equally-weighted cards with headings and subtitles.
5. **No frontend tests exist**: No test framework, no test files, no test dependencies in `frontend/package.json`.

## Global Constraints

- Use existing design tokens from `globals.css` (primary: `hsl(243 75% 59%)`, card: white, background: `hsl(230 15% 97%)`)
- Use existing UI components (`Card`, `CardContent`, `Button`) from `frontend/components/ui/`
- Follow existing code conventions: `"use client"` directive, `useRouter` from `next/navigation`, Tailwind classes
- Candidate flow remains linear with no dashboard, sidebar, or navigation — by design
- Do NOT modify any backend Python code
- Do NOT modify any existing candidate flow pages (they already work)

---

### Task 1: Build the role-selector landing screen

**Files:**
- Modify: `frontend/app/page.tsx` (replace redirect with role-selector UI)

**Interfaces:**
- Consumes: `Card`, `CardContent` from `@/components/ui/card`; `Button` from `@/components/ui/button`; icons from `lucide-react`
- Produces: Two clickable cards — "I'm a Recruiter" → `/login`, "I'm a Candidate" → `/candidate/entry`

- [ ] **Step 1: Replace root page with role-selector screen**

Replace the entire contents of `frontend/app/page.tsx` with:

```tsx
"use client"

import { useRouter } from "next/navigation"
import { Card, CardContent } from "@/components/ui/card"
import { Briefcase, Code } from "lucide-react"

export default function Home() {
  const router = useRouter()

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
      <div className="mb-10 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground font-bold text-xl">
          IQ
        </div>
        <h1 className="mt-4 text-3xl font-bold text-foreground">InterviewIQ</h1>
        <p className="mt-2 text-sm text-muted-foreground">Who is using this device?</p>
      </div>

      <div className="grid w-full max-w-lg grid-cols-1 gap-6 sm:grid-cols-2">
        <button
          onClick={() => router.push("/login")}
          className="group"
        >
          <Card className="h-full rounded-2xl border-border transition-all hover:border-primary hover:shadow-md">
            <CardContent className="flex flex-col items-center justify-center p-8 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                <Briefcase className="h-7 w-7" />
              </div>
              <h2 className="text-lg font-bold text-foreground">I'm a Recruiter</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Create job postings, invite candidates, and review reports
              </p>
            </CardContent>
          </Card>
        </button>

        <button
          onClick={() => router.push("/candidate/entry")}
          className="group"
        >
          <Card className="h-full rounded-2xl border-border transition-all hover:border-primary hover:shadow-md">
            <CardContent className="flex flex-col items-center justify-center p-8 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                <Code className="h-7 w-7" />
              </div>
              <h2 className="text-lg font-bold text-foreground">I'm a Candidate</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Enter your invite code to start your interview
              </p>
            </CardContent>
          </Card>
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add `/` to NO_SIDEBAR_ROUTES in app-layout**

In `frontend/components/app-layout.tsx`, the `NO_SIDEBAR_ROUTES` array already contains `"/"` — verify this is present. It is at line 7: `const NO_SIDEBAR_ROUTES = ["/login", "/"]`. No change needed.

- [ ] **Step 3: Verify the build compiles**

Run: `npm run build` in `frontend/`
Expected: Build succeeds with no errors.

- [ ] **Step 4: Manual verification checklist**

- [ ] Navigate to `http://localhost:3000` — role-selector screen appears with two cards
- [ ] "I'm a Recruiter" card navigates to `/login` — existing login form renders
- [ ] "I'm a Candidate" card navigates to `/candidate/entry` — invite code entry renders
- [ ] No sidebar visible on role-selector screen
- [ ] Recruiter login → dashboard flow still works exactly as before
- [ ] Candidate entry → consent → device-check → interview → done flow still works

- [ ] **Step 5: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: add role-selector landing screen at root route"
```

---

### Task 2: Set up Vitest + React Testing Library for frontend

**Files:**
- Modify: `frontend/package.json` (add test dependencies and script)
- Create: `frontend/vitest.config.ts`
- Create: `frontend/tsconfig.test.json`

**Interfaces:**
- Consumes: existing `frontend/tsconfig.json`, `frontend/tailwind.config.ts`
- Produces: runnable `npm test` command in `frontend/`

- [ ] **Step 1: Install test dependencies**

Run in `frontend/`:
```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 2: Add test script to package.json**

Add to `frontend/package.json` scripts:
```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 3: Create vitest.config.ts**

Create `frontend/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config"
import path from "path"

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
  },
})
```

- [ ] **Step 4: Create vitest.setup.ts**

Create `frontend/vitest.setup.ts`:
```ts
import "@testing-library/jest-dom/vitest"
```

- [ ] **Step 5: Verify test runner works**

Run: `npm test` in `frontend/`
Expected: Vitest runs, finds 0 tests, exits cleanly (no errors).

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/vitest.setup.ts
git commit -m "chore: add vitest + react testing library for frontend tests"
```

---

### Task 3: Write role-selector and candidate routing tests

**Files:**
- Create: `frontend/app/__tests__/page.test.tsx` (role-selector root page tests)
- Create: `frontend/app/candidate/__tests__/candidate-flow.test.tsx` (candidate flow guard tests)

**Interfaces:**
- Consumes: Vitest setup from Task 2, existing page components
- Produces: passing test suite covering role selector rendering, navigation, and candidate flow guards

- [ ] **Step 1: Create root page test file**

Create `frontend/app/__tests__/page.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

const push = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}))

import Home from "../page"

describe("Root page (role selector)", () => {
  beforeEach(() => {
    push.mockClear()
  })

  it("renders the role selector with both options", () => {
    render(<Home />)

    expect(screen.getByText("InterviewIQ")).toBeInTheDocument()
    expect(screen.getByText("Who is using this device?")).toBeInTheDocument()
    expect(screen.getByText("I'm a Recruiter")).toBeInTheDocument()
    expect(screen.getByText("I'm a Candidate")).toBeInTheDocument()
  })

  it("renders subtitles for both cards", () => {
    render(<Home />)

    expect(screen.getByText(/Create job postings/)).toBeInTheDocument()
    expect(screen.getByText(/Enter your invite code/)).toBeInTheDocument()
  })

  it("navigates to /login when Recruiter card is clicked", async () => {
    const user = userEvent.setup()
    render(<Home />)

    await user.click(screen.getByText("I'm a Recruiter"))

    expect(push).toHaveBeenCalledWith("/login")
  })

  it("navigates to /candidate/entry when Candidate card is clicked", async () => {
    const user = userEvent.setup()
    render(<Home />)

    await user.click(screen.getByText("I'm a Candidate"))

    expect(push).toHaveBeenCalledWith("/candidate/entry")
  })

  it("does NOT render a login form (no username/password fields)", () => {
    render(<Home />)

    expect(screen.queryByLabelText(/username/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run root page tests**

Run: `npm test -- app/__tests__/page.test.tsx` in `frontend/`
Expected: All 5 tests PASS.

- [ ] **Step 3: Create candidate flow guard test file**

Create `frontend/app/candidate/__tests__/candidate-flow.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"

const push = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}))

describe("Candidate flow guards", () => {
  beforeEach(() => {
    push.mockClear()
    sessionStorage.clear()
  })

  it("candidate entry page renders without any auth/session state", async () => {
    const { default: CandidateEntryPage } = await import("../entry/page")
    render(<CandidateEntryPage />)

    expect(screen.getByText("Welcome")).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/e\.g\. abc123/i)).toBeInTheDocument()
  })

  it("candidate consent page redirects to entry when no sessionStorage data", async () => {
    const { default: CandidateConsentPage } = await import("../consent/page")
    render(<CandidateConsentPage />)

    // Should redirect to /candidate/entry (push called with that path)
    // The component returns null while redirecting, so we check push was called
    expect(push).toHaveBeenCalledWith("/candidate/entry")
  })

  it("candidate device-check page redirects to entry when no sessionStorage data", async () => {
    const { default: CandidateDeviceCheckPage } = await import("../device-check/page")
    render(<CandidateDeviceCheckPage />)

    expect(push).toHaveBeenCalledWith("/candidate/entry")
  })

  it("candidate interview page redirects to entry when no sessionStorage data", async () => {
    const { default: CandidateInterviewPage } = await import("../interview/page")
    render(<CandidateInterviewPage />)

    expect(push).toHaveBeenCalledWith("/candidate/entry")
  })

  it("candidate done page renders the completion message", async () => {
    const { default: CandidateDonePage } = await import("../done/page")
    render(<CandidateDonePage />)

    expect(screen.getByText("Interview Complete")).toBeInTheDocument()
  })
})
```

- [ ] **Step 4: Run candidate flow tests**

Run: `npm test -- candidate/__tests__/candidate-flow.test.tsx` in `frontend/`
Expected: All 5 tests PASS. The guard tests confirm that navigating to consent/device-check/interview without sessionStorage data causes a redirect to `/candidate/entry`.

- [ ] **Step 5: Run full test suite**

Run: `npm test` in `frontend/`
Expected: All tests PASS (10 total: 5 root page + 5 candidate flow).

- [ ] **Step 6: Commit**

```bash
git add frontend/app/__tests__/ frontend/app/candidate/__tests__/
git commit -m "test: add role-selector and candidate routing guard tests"
```

---

## Acceptance Criteria Verification

After all tasks are complete:

1. **Role-selector visible at launch**: Navigating to `/` shows two cards ("I'm a Recruiter" / "I'm a Candidate"), not a login form or redirect.
2. **Recruiter path works**: Clicking "I'm a Recruiter" → `/login` → sign in → `/dashboard` with sidebar — identical to before.
3. **Candidate path works**: Clicking "I'm a Candidate" → `/candidate/entry` → consent → device-check → interview → done — no recruiter credentials needed.
4. **No candidate dashboard**: Confirmed by design — candidates get a linear flow, no navigation/sidebar.
5. **Candidate guards work**: Direct navigation to `/candidate/consent`, `/candidate/device-check`, or `/candidate/interview` without prior steps redirects to `/candidate/entry`.
6. **Recruiter flow zero regressions**: All existing recruiter pages and sidebar navigation unaffected.
7. **Tests pass**: Frontend test suite (10 tests) passes. Backend test suite (unchanged) continues to pass.
