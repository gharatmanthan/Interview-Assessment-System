# InterviewIQ Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the InterviewIQ frontend — fix 3 backend bugs, polish all 9 recruiter pages to match spec, build the 5-screen candidate flow, and add candidate-flow API endpoints.

**Architecture:** The existing FastAPI + Next.js + Electron stack stays unchanged. All new work is frontend pages/components and thin API route additions. The candidate flow runs at separate `/candidate/*` routes with no sidebar (isolated from recruiter UI). Backend logic (scoring, STT, integrity checks) is reused as-is via the existing `app/` modules.

**Tech Stack:** Next.js 14 (App Router), React 18, TypeScript 5.5, Tailwind CSS 3.4, shadcn/ui (Radix primitives), Lucide icons, Sonner toasts, FastAPI + Pydantic (Python 3.12), SQLite.

**Spec:** Full spec provided in conversation — covers sections 5.1–5.9 (recruiter pages), 6.1–6.5 (candidate flow), 8 (non-functional requirements).

## Global Constraints

- Indigo `#5B5FEF` accent (already in tailwind.config.ts as `primary`), neutral gray/white base, semantic colors only for status (green/amber/red)
- 8px spacing scale, `rounded-lg`/`rounded-xl`, soft shadows on elevated elements only
- 2 font weights max per screen (regular + semibold), generous line-height
- Dense layout for recruiter screens, sparse single-focus for candidate screens
- Every list/table has empty state with clear next action
- Every async action has loading state + success/error toast
- Every destructive action requires confirmation dialog
- No dark mode for MVP
- Keyboard navigation + focus states on every interactive element
- `frontend/components/ui/` already has: badge, button, card, dialog, input, label, scroll-area, select, separator, slider, sonner, switch, table, tabs

---

## File Structure

### New files to create

| File | Purpose |
|------|---------|
| `frontend/components/skill-tag-input.tsx` | Reusable tag/chip input for skills |
| `frontend/components/timer-ring.tsx` | Circular SVG timer for candidate interview |
| `frontend/components/empty-state.tsx` | Reusable empty state component |
| `frontend/components/loading-spinner.tsx` | Reusable loading spinner |
| `frontend/app/candidate/entry/page.tsx` | Candidate entry — invite code input |
| `frontend/app/candidate/consent/page.tsx` | Candidate consent screen |
| `frontend/app/candidate/device-check/page.tsx` | Camera/mic/integrity pre-check |
| `frontend/app/candidate/interview/page.tsx` | Candidate live interview |
| `frontend/app/candidate/done/page.tsx` | Candidate thank-you screen |
| `frontend/app/candidate/layout.tsx` | Candidate layout (no sidebar, centered) |
| `api/routes/candidate_flow.py` | Candidate-facing API endpoints |

### Files to modify

| File | Changes |
|------|---------|
| `api/routes/candidates.py:60-100` | Fix resume upload response shape |
| `api/routes/integrity.py:36-46` | Fix WebSocket message format |
| `api/main.py` | Register candidate_flow router |
| `frontend/app/interview/page.tsx:135` | Fix WebSocket URL prefix |
| `frontend/app/interview/page.tsx:141-151` | Fix WebSocket message handler |
| `frontend/app/login/page.tsx` | Add inline error states |
| `frontend/app/dashboard/page.tsx` | Candidate status breakdown, card layout |
| `frontend/app/jobs/page.tsx` | 8-row textarea, tag input, max constraints, difficulty explanation |
| `frontend/app/candidates/page.tsx` | Resume in invite, large code display, invite code column |
| `frontend/app/reports/page.tsx` | Sortable columns, double-click, job filter |
| `frontend/app/settings/page.tsx` | LLM provider dropdown |
| `frontend/components/sidebar.tsx` | Display recruiter name |
| `frontend/app/layout.tsx` | Minor styling adjustments |
| `frontend/lib/types.ts` | Add candidate flow types |
| `frontend/lib/api.ts` | Add candidate flow API methods |

---

## Phase 1: Bug Fixes + Design System Foundation

### Task 1: Fix Resume Upload Response Shape

**Files:**
- Modify: `api/routes/candidates.py:60-100`

**Interfaces:**
- Produces: Returns full `CandidateResponse` dict after upload (matches `CandidateResponse` schema)

- [ ] **Step 1: Fix the upload_resume endpoint response**

Replace lines 92-100 in `api/routes/candidates.py`. Instead of returning a partial dict, return the full candidate data by fetching the updated candidate from DB:

```python
    # After db.save_candidate_resume(...), return the full candidate
    updated_candidates = db.get_all_candidates()
    updated = next((c for c in updated_candidates if c["candidate_id"] == candidate_id), None)
    if updated:
        return updated
    return {
        "candidate_id": candidate_id,
        "resume_path": str(dest),
        "resume_skills": parsed.get("skills", []),
        "experience_years": parsed.get("experience_years"),
        "match_score": match_result.get("match_score", 0),
        "matched_skills": match_result.get("matched_skills", []),
        "missing_skills": match_result.get("missing_skills", []),
    }
```

- [ ] **Step 2: Verify response matches CandidateResponse schema**

Check that `db.get_all_candidates()` returns dicts with all `CandidateResponse` fields: `candidate_id`, `job_id`, `name`, `email`, `invite_code`, `status`, `session_id`, `invited_at`, `resume_path`, `resume_skills`, `experience_years`, `match_score`, `matched_skills`, `missing_skills`, `job_title`.

- [ ] **Step 3: Test manually**

Upload a resume via the candidates page. Verify the candidate row doesn't lose name/email/status after upload.

---

### Task 2: Fix WebSocket URL and Message Format

**Files:**
- Modify: `frontend/app/interview/page.tsx:133-153`
- Modify: `api/routes/integrity.py:36-46`

**Interfaces:**
- Frontend connects to: `ws://localhost:{port}/api/ws/integrity/{session_id}`
- Backend sends: array of flag objects directly

- [ ] **Step 1: Fix WebSocket URL in frontend**

In `frontend/app/interview/page.tsx` line 135, change:
```typescript
const ws = new WebSocket(`ws://localhost:${port}/ws/integrity/${sessionId}`)
```
to:
```typescript
const ws = new WebSocket(`ws://localhost:${port}/api/ws/integrity/${sessionId}`)
```

- [ ] **Step 2: Fix WebSocket message handler in frontend**

In `frontend/app/interview/page.tsx` lines 141-151, replace the `ws.onmessage` handler:
```typescript
ws.onmessage = (event) => {
  try {
    const data = JSON.parse(event.data)
    if (data && data.flags && Array.isArray(data.flags)) {
      if (data.flags.length > 0) {
        setIntegrityFlags((prev) => [...data.flags, ...prev])
      }
    } else if (Array.isArray(data)) {
      setIntegrityFlags(data)
    } else if (data && data.flag_type) {
      setIntegrityFlags((prev) => [data, ...prev])
    }
  } catch {
    // ignore malformed messages
  }
}
```

- [ ] **Step 3: Fix backend WebSocket message format**

In `api/routes/integrity.py` lines 36-46, simplify the send to include session_id and keep the flags array format the frontend now handles:

```python
            flag_dicts = [
                {
                    "flag_type": f.flag_type,
                    "detail": f.detail,
                    "severity": f.severity,
                }
                for f in all_flags
            ]
            await websocket.send_json({
                "flags": flag_dicts,
                "total_flags": len(all_flags),
                "session_id": session_id,
            })
```

(This is already the current format — the fix is on the frontend side in Step 2.)

- [ ] **Step 4: Verify WebSocket connectivity**

Start the app, begin an interview session, and verify integrity flags appear in the Integrity Monitor panel.

---

### Task 3: Create Reusable Design System Components

**Files:**
- Create: `frontend/components/empty-state.tsx`
- Create: `frontend/components/loading-spinner.tsx`
- Create: `frontend/components/skill-tag-input.tsx`
- Create: `frontend/components/timer-ring.tsx`

**Interfaces:**
- `EmptyState` — props: `icon?: LucideIcon`, `title: string`, `description: string`, `action?: { label: string; onClick: () => void }`
- `LoadingSpinner` — props: `size?: 'sm' | 'md' | 'lg'`, `text?: string`
- `SkillTagInput` — props: `value: string[]`, `onChange: (skills: string[]) => void`, `placeholder?: string`
- `TimerRing` — props: `seconds: number`, `maxSeconds: number`, `size?: number`

- [ ] **Step 1: Create EmptyState component**

```tsx
// frontend/components/empty-state.tsx
"use client"

import type { LucideIcon } from "lucide-react"
import { Button } from "@/components/ui/button"

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      {Icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
          <Icon className="h-6 w-6 text-slate-400" />
        </div>
      )}
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>
      {action && (
        <Button className="mt-4" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create LoadingSpinner component**

```tsx
// frontend/components/loading-spinner.tsx
"use client"

import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg"
  text?: string
  className?: string
}

const sizeMap = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-8 w-8",
}

export function LoadingSpinner({ size = "md", text, className }: LoadingSpinnerProps) {
  return (
    <div className={cn("flex items-center justify-center gap-2", className)}>
      <Loader2 className={cn("animate-spin text-primary", sizeMap[size])} />
      {text && <span className="text-sm text-slate-500">{text}</span>}
    </div>
  )
}
```

- [ ] **Step 3: Create SkillTagInput component**

```tsx
// frontend/components/skill-tag-input.tsx
"use client"

import { useState, useRef, KeyboardEvent } from "react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { X } from "lucide-react"

interface SkillTagInputProps {
  value: string[]
  onChange: (skills: string[]) => void
  placeholder?: string
}

export function SkillTagInput({ value, onChange, placeholder = "Add a skill..." }: SkillTagInputProps) {
  const [input, setInput] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  function addSkill() {
    const trimmed = input.trim()
    if (trimmed && !value.includes(trimmed)) {
      onChange([...value, trimmed])
    }
    setInput("")
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      addSkill()
    } else if (e.key === "Backspace" && input === "" && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  function removeSkill(skill: string) {
    onChange(value.filter((s) => s !== skill))
  }

  return (
    <div
      className="flex min-h-[42px] flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2"
      onClick={() => inputRef.current?.focus()}
    >
      {value.map((skill) => (
        <Badge key={skill} variant="secondary" className="gap-1 pr-1">
          {skill}
          <button
            type="button"
            onClick={() => removeSkill(skill)}
            className="ml-0.5 rounded-full p-0.5 hover:bg-slate-200"
          >
            <X className="h-3 w-3" />
          </button>
        </Badge>
      ))}
      <input
        ref={inputRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={addSkill}
        placeholder={value.length === 0 ? placeholder : ""}
        className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
      />
    </div>
  )
}
```

- [ ] **Step 4: Create TimerRing component**

```tsx
// frontend/components/timer-ring.tsx
"use client"

interface TimerRingProps {
  seconds: number
  maxSeconds: number
  size?: number
}

export function TimerRing({ seconds, maxSeconds, size = 120 }: TimerRingProps) {
  const radius = (size - 12) / 2
  const circumference = 2 * Math.PI * radius
  const progress = maxSeconds > 0 ? seconds / maxSeconds : 0
  const offset = circumference - progress * circumference

  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  const display = `${mins}:${secs.toString().padStart(2, "0")}`

  const color = progress > 0.75 ? "#EF4444" : progress > 0.5 ? "#F59E0B" : "#5B5FEF"

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#E5E7EB"
          strokeWidth={6}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 linear"
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-mono text-2xl font-semibold tabular-nums text-slate-900">{display}</span>
        <span className="text-xs text-slate-500">remaining</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Verify components render**

Import each component in a test page or existing page and confirm they render correctly.

---

## Phase 2: Recruiter Page Improvements

### Task 4: Login Page — Inline Error States

**Files:**
- Modify: `frontend/app/login/page.tsx`

**Interfaces:**
- Consumes: `api.login()`, `api.register()` (existing)
- Produces: Inline error text below form fields + toast

- [ ] **Step 1: Add error state variables**

After line 13 (`const [loading, setLoading] = useState(false)`), add:
```typescript
const [signInError, setSignInError] = useState("")
const [signUpError, setSignUpError] = useState("")
```

- [ ] **Step 2: Update handleSignIn to set inline errors**

Replace the error handling in `handleSignIn` (lines 25-28):
```typescript
if (res.success) {
  localStorage.setItem("username", res.username ?? signIn.username)
  toast.success("Welcome back!")
  router.push("/dashboard")
} else {
  setSignInError(res.message || "Login failed")
}
```
Add `setSignInError("")` at the start of `handleSignIn` and in the `finally` block only clear on success. Actually, clear on each submission attempt:
```typescript
async function handleSignIn(e: React.FormEvent) {
  e.preventDefault()
  setSignInError("")
  setLoading(true)
  // ... rest
```

- [ ] **Step 3: Add inline error display in Sign In form**

After the password input div (after line 97), add:
```tsx
{signInError && (
  <p className="text-sm text-red-500">{signInError}</p>
)}
```

- [ ] **Step 4: Apply same pattern to Sign Up form**

Add `setSignUpError("")` at start of `handleSignUp`, set it on `res.success === false`, display after the password field. Also clear on successful registration.

- [ ] **Step 5: Clear errors when switching tabs**

Add `onChange` handler to `Tabs` or use `onValueChange` on `TabsList` to clear both errors when switching.

- [ ] **Step 6: Verify**

Test with wrong password (should show inline error + toast), test with duplicate username (should show inline error + toast).

---

### Task 5: Dashboard — Candidate Status Breakdown + Card Layout

**Files:**
- Modify: `frontend/app/dashboard/page.tsx`

**Interfaces:**
- Consumes: `api.getDashboardStats()`, `api.getJobs()` (existing)
- Produces: Candidate status breakdown row, job postings as clickable cards

- [ ] **Step 1: Add candidate status breakdown section**

After the stat cards grid (after line 121), add a new section:
```tsx
{/* Candidate Status Breakdown */}
{stats && Object.keys(stats.candidates_by_status).length > 0 && (
  <div>
    <h2 className="text-lg font-semibold text-slate-900 mb-4">Candidate Status</h2>
    <div className="grid grid-cols-3 gap-4">
      {[
        { key: "invited", label: "Invited", color: "bg-blue-50 text-blue-700 border-blue-200" },
        { key: "in_progress", label: "In Progress", color: "bg-amber-50 text-amber-700 border-amber-200" },
        { key: "completed", label: "Completed", color: "bg-green-50 text-green-700 border-green-200" },
      ].map(({ key, label, color }) => (
        <Card key={key} className="rounded-xl border bg-white p-4">
          <CardContent className="p-0">
            <p className="text-sm text-slate-500">{label}</p>
            <p className={`text-2xl font-bold mt-1 ${color.split(" ")[1]}`}>
              {stats.candidates_by_status[key] ?? 0}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  </div>
)}
```

- [ ] **Step 2: Replace job postings table with card grid**

Replace the Table section (lines 126-161) with a card-based layout. Use `useRouter` to navigate to `/jobs` on click:

```tsx
import { useRouter } from "next/navigation"
import { Briefcase } from "lucide-react"
// Add router inside component:
const router = useRouter()

{/* Job Postings as Cards */}
<div>
  <h2 className="text-lg font-semibold text-slate-900 mb-4">Job Postings</h2>
  {jobs.length === 0 ? (
    <Card className="rounded-xl border bg-white">
      <CardContent className="py-12 text-center">
        <Briefcase className="mx-auto h-8 w-8 text-slate-300 mb-2" />
        <p className="text-sm text-slate-500">No job postings yet</p>
        <Button variant="outline" className="mt-3" onClick={() => router.push("/jobs")}>
          Create Job Posting
        </Button>
      </CardContent>
    </Card>
  ) : (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {jobs.map((job) => (
        <Card
          key={job.job_id}
          className="rounded-xl border bg-white p-5 cursor-pointer transition-colors hover:border-primary/30 hover:bg-primary/5"
          onClick={() => router.push("/jobs")}
        >
          <CardContent className="p-0 space-y-2">
            <h3 className="font-semibold text-slate-900">{job.title}</h3>
            <p className="text-sm text-slate-500">{job.department}</p>
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-xs">{job.experience_level}</Badge>
              {job.required_skills.slice(0, 2).map((skill) => (
                <Badge key={skill} variant="outline" className="text-xs">{skill}</Badge>
              ))}
              {job.required_skills.length > 2 && (
                <Badge variant="outline" className="text-xs">+{job.required_skills.length - 2}</Badge>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )}
</div>
```

- [ ] **Step 3: Add "Welcome back, {name}" in header**

Replace the dashboard header (lines 100-103):
```tsx
const username = typeof window !== "undefined" ? localStorage.getItem("username") : null

// In the JSX:
<div>
  <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
  <p className="text-sm text-slate-500 mt-1">
    Welcome back{username ? `, ${username}` : ""}
  </p>
</div>
```

- [ ] **Step 4: Verify**

Dashboard should show: stat cards, candidate status breakdown (3 cards with counts), job postings as clickable cards, welcome message with username.

---

### Task 6: Job Postings — Form Improvements

**Files:**
- Modify: `frontend/app/jobs/page.tsx`
- Create: `frontend/components/skill-tag-input.tsx` (already created in Task 3)

**Interfaces:**
- Consumes: `SkillTagInput` component (Task 3)
- Produces: Updated form with 8-row textarea, tag input, max constraints, difficulty explanation

- [ ] **Step 1: Import SkillTagInput**

Add to imports:
```typescript
import { SkillTagInput } from "@/components/skill-tag-input"
```

- [ ] **Step 2: Change textarea to 8 rows**

In the form, change `rows={3}` to `rows={8}` on the description textarea (line 250).

- [ ] **Step 3: Replace comma-separated input with SkillTagInput**

Replace the skills Input + hint text (lines 259-268):
```tsx
<div className="space-y-2 md:col-span-2">
  <Label>Required Skills</Label>
  <SkillTagInput
    value={form.required_skills}
    onChange={(skills) => setForm({ ...form, required_skills: skills })}
    placeholder="Type a skill and press Enter..."
  />
  <p className="text-xs text-slate-400">Press Enter or comma to add a skill</p>
</div>
```

Remove the `skillsInput` state variable and update `openCreate`/`openEdit` to not set it (since SkillTagInput manages its own display). Update `handleSave` to use `form.required_skills` directly instead of parsing `skillsInput`:

```typescript
async function handleSave(e: React.FormEvent) {
  e.preventDefault()
  if (!weightsValid) {
    toast.error("Competency weights must sum to 100")
    return
  }
  const payload: JobPosting = {
    job_id: editingId ?? "",
    ...form,
    required_skills: form.required_skills,
  }
  // ... rest unchanged
}
```

- [ ] **Step 4: Add max=5 on Number of Rounds**

Change the rounds Input (line 295):
```tsx
<Input
  id="rounds"
  type="number"
  min={1}
  max={5}
  required
  value={form.num_rounds}
  onChange={(e) => {
    const val = parseInt(e.target.value) || 1
    setForm({ ...form, num_rounds: Math.min(5, Math.max(1, val)) })
  }}
/>
```

- [ ] **Step 5: Add max=600 on Time Limit**

Change the time limit Input (line 310):
```tsx
<Input
  id="timeLimit"
  type="number"
  min={30}
  max={600}
  required
  value={form.time_limit_seconds}
  onChange={(e) => {
    const val = parseInt(e.target.value) || 300
    setForm({ ...form, time_limit_seconds: Math.min(600, Math.max(30, val)) })
  }}
/>
```

- [ ] **Step 6: Add explanation text below Adaptive Difficulty**

After the Switch + Label (lines 321-329), add:
```tsx
<p className="ml-12 text-xs text-slate-400">
  Question difficulty increases if the candidate answers well, decreases if they struggle.
</p>
```

- [ ] **Step 7: Update Department to a Select dropdown**

Replace the Department Input with a Select:
```tsx
const DEPARTMENTS = ["Software/CS", "Data/ML", "Electronics", "Mechanical", "Civil", "Other"]

// In the form:
<div className="space-y-2">
  <Label>Department</Label>
  <Select
    value={form.department}
    onValueChange={(val) => setForm({ ...form, department: val })}
  >
    <SelectTrigger>
      <SelectValue placeholder="Select department" />
    </SelectTrigger>
    <SelectContent>
      {DEPARTMENTS.map((dept) => (
        <SelectItem key={dept} value={dept}>{dept}</SelectItem>
      ))}
    </SelectContent>
  </Select>
</div>
```

- [ ] **Step 8: Verify**

Create/edit a job posting. Verify: 8-row textarea, tag input with Enter/comma, rounds capped at 5, time capped at 600, difficulty explanation visible, department dropdown.

---

### Task 7: Candidates Page — Invite Form + Code Display + Table Columns

**Files:**
- Modify: `frontend/app/candidates/page.tsx`
- Modify: `frontend/lib/api.ts` (update uploadResume return type)

**Interfaces:**
- Consumes: `api.createCandidate()`, `api.uploadResume()`, `api.resendInvite()` (existing)
- Produces: Updated invite form with resume upload, large code display after invite, invite code in table

- [ ] **Step 1: Add resume file to invite form state**

Update `inviteForm` state:
```typescript
const [inviteForm, setInviteForm] = useState({ name: "", email: "", job_id: "" })
const [inviteResumeFile, setInviteResumeFile] = useState<File | null>(null)
const [createdCandidate, setCreatedCandidate] = useState<Candidate | null>(null)
```

- [ ] **Step 2: Add file picker to invite dialog**

After the job posting Select in the invite dialog (after line 302), add:
```tsx
<div className="space-y-2">
  <Label htmlFor="invite-resume">Resume (optional)</Label>
  <Input
    id="invite-resume"
    type="file"
    accept=".pdf,.docx,.txt"
    onChange={(e) => setInviteResumeFile(e.target.files?.[0] ?? null)}
  />
  <p className="text-xs text-slate-400">PDF, DOCX, or TXT — drives JD-match scoring</p>
</div>
```

- [ ] **Step 3: Update handleInvite to upload resume after creation**

```typescript
async function handleInvite(e: React.FormEvent) {
  e.preventDefault()
  setInviteLoading(true)
  try {
    const candidate_id = Date.now().toString()
    const created = await api.createCandidate({
      candidate_id,
      name: inviteForm.name,
      email: inviteForm.email,
      job_id: inviteForm.job_id,
    })
    if (inviteResumeFile) {
      await api.uploadResume(candidate_id, inviteResumeFile)
    }
    setCreatedCandidate(created)
    toast.success("Candidate invited successfully")
    // Don't close dialog yet — show the code
    setInviteForm({ name: "", email: "", job_id: "" })
    setInviteResumeFile(null)
    await fetchData()
  } catch (err: any) {
    toast.error(err.message || "Failed to invite candidate")
  } finally {
    setInviteLoading(false)
  }
}
```

- [ ] **Step 4: Add large invite code display in dialog**

After the form closes (when `createdCandidate` is set), show the code prominently. Replace the Dialog close behavior:

When `createdCandidate` is set, the dialog shows the code instead of the form:
```tsx
<Dialog open={inviteOpen} onOpenChange={(open) => {
  if (!open) {
    setInviteOpen(false)
    setCreatedCandidate(null)
  }
}}>
  <DialogContent>
    {createdCandidate ? (
      <>
        <DialogHeader>
          <DialogTitle>Invite Created</DialogTitle>
          <DialogDescription>
            Share this code with {createdCandidate.name} to begin their interview.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col items-center py-6">
          <p className="text-xs text-slate-500 mb-2">Invite Code</p>
          <div className="flex items-center gap-3 rounded-xl border-2 border-dashed border-primary/30 bg-primary/5 px-8 py-4">
            <span className="font-mono text-3xl font-bold tracking-widest text-primary">
              {createdCandidate.invite_code}
            </span>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                navigator.clipboard.writeText(createdCandidate.invite_code)
                toast.success("Code copied!")
              }}
            >
              <Copy className="h-5 w-5" />
            </Button>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => { setInviteOpen(false); setCreatedCandidate(null) }}>
            Done
          </Button>
        </DialogFooter>
      </>
    ) : (
      // ... existing form
    )}
  </DialogContent>
</Dialog>
```

- [ ] **Step 5: Add invite code column to table**

In the table headers (line 169), add:
```tsx
<TableHead>Invite Code</TableHead>
```

In the table row, add after the Status cell:
```tsx
<TableCell>
  <code className="rounded bg-slate-100 px-2 py-0.5 text-xs font-mono text-slate-700">
    {c.invite_code}
  </code>
</TableCell>
```

- [ ] **Step 6: Style JD Match as a colored badge**

Replace the plain text match score cell (line 376):
```tsx
<TableCell>
  {c.match_score != null ? (
    <Badge
      variant="outline"
      className={
        c.match_score >= 0.7
          ? "bg-green-50 text-green-700 border-green-200"
          : c.match_score >= 0.4
            ? "bg-amber-50 text-amber-700 border-amber-200"
            : "bg-red-50 text-red-700 border-red-200"
      }
    >
      {Math.round(c.match_score * 100)}%
    </Badge>
  ) : (
    <span className="text-slate-400">—</span>
  )}
</TableCell>
```

- [ ] **Step 7: Add inline skills summary in table**

After the Match Score column, add:
```tsx
<TableHead>Skills</TableHead>
// In row:
<TableCell>
  <div className="flex flex-wrap gap-1 max-w-[200px]">
    {c.matched_skills.slice(0, 2).map((s) => (
      <Badge key={s} variant="secondary" className="text-[10px] bg-green-50 text-green-700 border-green-200">{s}</Badge>
    ))}
    {c.missing_skills.slice(0, 2).map((s) => (
      <Badge key={s} variant="outline" className="text-[10px] border-red-200 text-red-600">{s}</Badge>
    ))}
    {(c.matched_skills.length + c.missing_skills.length) > 4 && (
      <Badge variant="outline" className="text-[10px]">+{c.matched_skills.length + c.missing_skills.length - 4}</Badge>
    )}
  </div>
</TableCell>
```

- [ ] **Step 8: Verify**

Invite a candidate with resume. Verify: large code display with copy button, invite code in table, JD match badge with color, inline skills summary.

---

### Task 8: Reports — Sortable Columns + Double-Click + Job Filter

**Files:**
- Modify: `frontend/app/reports/page.tsx`

**Interfaces:**
- Consumes: `api.getComparison(job_id?)` (existing)
- Produces: Sortable comparison table, double-click navigation, job filter dropdown

- [ ] **Step 1: Add sort state**

Inside the ReportsPage component, add:
```typescript
const [sortField, setSortField] = useState<string>("overall_score")
const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
const [filterJobId, setFilterJobId] = useState<string>("all")
const [jobs, setJobs] = useState<JobPosting[]>([])

useEffect(() => {
  api.getJobs().then(setJobs).catch(() => {})
}, [])
```

Import `JobPosting` in the imports.

- [ ] **Step 2: Add sort handler**

```typescript
function handleSort(field: string) {
  if (sortField === field) {
    setSortDir((d) => (d === "asc" ? "desc" : "asc"))
  } else {
    setSortField(field)
    setSortDir("desc")
  }
}

function SortIcon({ field }: { field: string }) {
  if (sortField !== field) return null
  return <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
}
```

- [ ] **Step 3: Apply sort + filter to comparison data**

Replace line 69:
```typescript
const filteredComparison = filterJobId === "all"
  ? comparison
  : comparison.filter((r) => {
      const session = sessions.find((s) => s.session_id === r.session_id)
      return session?.job_id === filterJobId
    })

const sortedComparison = [...filteredComparison].sort((a, b) => {
  const aVal = sortField === "overall_score" ? a.overall_score : (a.category_scores[sortField] ?? 0)
  const bVal = sortField === "overall_score" ? b.overall_score : (b.category_scores[sortField] ?? 0)
  return sortDir === "asc" ? aVal - bVal : bVal - aVal
})
```

- [ ] **Step 4: Add job filter dropdown above comparison table**

In the Comparison tab content, before the table:
```tsx
<div className="mb-4 flex items-center gap-4">
  <Select value={filterJobId} onValueChange={setFilterJobId}>
    <SelectTrigger className="w-[250px]">
      <SelectValue placeholder="Filter by job" />
    </SelectTrigger>
    <SelectContent>
      <SelectItem value="all">All Jobs</SelectItem>
      {jobs.map((job) => (
        <SelectItem key={job.job_id} value={job.job_id}>{job.title}</SelectItem>
      ))}
    </SelectContent>
  </Select>
</div>
```

Import `Select` components.

- [ ] **Step 5: Make table headers clickable for sorting**

Replace the table headers:
```tsx
<TableHead className="w-16">Rank</TableHead>
<TableHead>Candidate</TableHead>
<TableHead>Job</TableHead>
<TableHead
  className="text-right cursor-pointer hover:text-slate-900"
  onClick={() => handleSort("overall_score")}
>
  Overall <SortIcon field="overall_score" />
</TableHead>
{categories.map((cat) => (
  <TableHead
    key={cat}
    className="text-right cursor-pointer hover:text-slate-900"
    onClick={() => handleSort(cat)}
  >
    {cat} <SortIcon field={cat} />
  </TableHead>
))}
```

- [ ] **Step 6: Add double-click on rows to load report**

Add `useRouter` import and handler:
```typescript
import { useRouter } from "next/navigation"
const router = useRouter()

// On the TableRow in comparison:
<TableRow
  key={row.session_id}
  className="cursor-pointer hover:bg-slate-50"
  onDoubleClick={() => {
    // Switch to sessions tab and select this session
    setSelectedId(row.session_id)
    // Find the tab trigger and click it programmatically
    document.querySelector('[value="sessions"]')?.click()
  }}
>
```

- [ ] **Step 7: Verify**

Go to Reports > Comparison. Verify: columns sortable by click, job filter dropdown works, double-click switches to Sessions tab with that report loaded.

---

### Task 9: Settings — LLM Provider Dropdown

**Files:**
- Modify: `frontend/app/settings/page.tsx`

**Interfaces:**
- Consumes: `Select` component (already imported)
- Produces: LLM provider as dropdown with predefined options

- [ ] **Step 1: Replace LLM Provider Input with Select**

Replace the provider Input (lines 156-162):
```tsx
const LLM_PROVIDERS = ["Groq", "OpenAI", "Gemini", "Anthropic", "Ollama"]

// In the form:
<div className="space-y-2">
  <Label>Provider</Label>
  <Select
    value={settings.llm_provider}
    onValueChange={(val) => updateField("llm_provider", val)}
  >
    <SelectTrigger>
      <SelectValue placeholder="Select provider" />
    </SelectTrigger>
    <SelectContent>
      {LLM_PROVIDERS.map((p) => (
        <SelectItem key={p} value={p}>{p}</SelectItem>
      ))}
    </SelectContent>
  </Select>
</div>
```

- [ ] **Step 2: Verify**

Open Settings. LLM Provider should be a dropdown with Groq, OpenAI, Gemini, Anthropic, Ollama.

---

### Task 10: Sidebar — Display Recruiter Name

**Files:**
- Modify: `frontend/components/sidebar.tsx`

**Interfaces:**
- Consumes: `localStorage.getItem("username")` (existing)
- Produces: Shows logged-in username in sidebar

- [ ] **Step 1: Read username from localStorage and display it**

Inside the Sidebar component, add:
```typescript
const [username, setUsername] = useState<string | null>(null)

useEffect(() => {
  setUsername(localStorage.getItem("username"))
}, [])
```

Import `useState, useEffect`.

After the logout button section (line 82), add user info above it:
```tsx
{showLogout && (
  <div className="px-3 pb-5 space-y-3">
    {username && (
      <div className="flex items-center gap-3 rounded-lg px-3 py-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 text-primary text-xs font-semibold">
          {username.charAt(0).toUpperCase()}
        </div>
        <span className="text-sm text-slate-300 truncate">{username}</span>
      </div>
    )}
    <button
      onClick={handleLogout}
      className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-400 transition-colors hover:text-white hover:bg-white/10"
    >
      <LogOut className="h-5 w-5 shrink-0" />
      Logout
    </button>
  </div>
)}
```

- [ ] **Step 2: Verify**

Log in. Sidebar should show the user's avatar initial + name above the logout button.

---

## Phase 3: Candidate Flow

### Task 11: Candidate Flow API Endpoints

**Files:**
- Create: `api/routes/candidate_flow.py`
- Modify: `api/main.py` (register new router)
- Modify: `frontend/lib/types.ts` (add candidate flow types)
- Modify: `frontend/lib/api.ts` (add candidate flow API methods)

**Interfaces:**
- `POST /api/candidate/validate-code` — body: `{ invite_code: string }` — returns: `{ valid: boolean, candidate?: Candidate, job?: JobPosting, message?: string }`
- `POST /api/candidate/consent` — body: `{ session_id: string, candidate_id: string }` — returns: `{ success: boolean }`
- `POST /api/candidate/start-session` — body: `{ session_id: string, candidate_id: string, job_id: string }` — returns: `InterviewSession`
- `POST /api/candidate/submit-answer` — body: `{ session_id: string, question_id: string, category: string, transcript: string }` — returns: `ScoringResult`
- `POST /api/candidate/complete-session` — body: `{ session_id: string }` — returns: `{ success: boolean }`

- [ ] **Step 1: Create candidate_flow.py router**

```python
# api/routes/candidate_flow.py
import secrets
from fastapi import APIRouter
from api.schemas import CandidateResponse, JobPostingResponse, SessionCreate, SessionResponse
from app.core import db
from app.core.models import Candidate, InterviewSession
from datetime import datetime

router = APIRouter()


@router.post("/candidate/validate-code")
def validate_invite_code(body: dict):
    code = body.get("invite_code", "").strip()
    if not code:
        return {"valid": False, "message": "No invite code provided"}

    candidates = db.get_all_candidates()
    candidate = next((c for c in candidates if c["invite_code"] == code), None)

    if not candidate:
        return {"valid": False, "message": "Invalid invite code"}

    if candidate.get("status") == "completed":
        return {"valid": False, "message": "This interview has already been completed"}

    if candidate.get("status") == "expired":
        return {"valid": False, "message": "This invite code has expired"}

    jobs = db.get_all_job_postings()
    job = next((j for j in jobs if j["job_id"] == candidate["job_id"]), None)

    return {
        "valid": True,
        "candidate": candidate,
        "job": job,
    }


@router.post("/candidate/consent")
def record_consent(body: dict):
    session_id = body.get("session_id")
    candidate_id = body.get("candidate_id")
    if not session_id or not candidate_id:
        return {"success": False, "message": "Missing required fields"}

    db.update_candidate_status(candidate_id, "in_progress")
    return {"success": True}


@router.post("/candidate/start-session", response_model=SessionResponse)
def start_candidate_session(body: dict):
    session_id = body.get("session_id")
    candidate_id = body.get("candidate_id")
    job_id = body.get("job_id")

    candidates = db.get_all_candidates()
    candidate = next((c for c in candidates if c["candidate_id"] == candidate_id), None)
    candidate_name = candidate["name"] if candidate else "Unknown"

    jobs = db.get_all_job_postings()
    job = next((j for j in jobs if j["job_id"] == job_id), None)
    job_title = job["title"] if job else "Unknown"

    session = InterviewSession(
        session_id=session_id,
        candidate_name=candidate_name,
        job_title=job_title,
        job_id=job_id,
        started_at=datetime.now().isoformat(),
        status="in_progress",
    )
    db.save_session(session)

    db.update_candidate_status(candidate_id, "in_progress")
    db.update_candidate_session(candidate_id, session_id)

    return SessionResponse(
        session_id=session.session_id,
        candidate_name=session.candidate_name,
        job_title=session.job_title,
        job_id=session.job_id,
        started_at=session.started_at,
        status=session.status,
    )


@router.post("/candidate/submit-answer")
def submit_answer(body: dict):
    from app.engine.scoring import score_answer
    from app.engine.explainability import explain_score
    from app.engine.fairness import audit_bias
    from app.engine.rag import retrieve_rubric

    session_id = body.get("session_id")
    question_id = body.get("question_id")
    category = body.get("category")
    transcript = body.get("transcript")

    rubric = retrieve_rubric(category)
    score_result = score_answer(transcript, rubric)
    explanation = explain_score(transcript, score_result)
    fairness = audit_bias(session_id, question_id, score_result.score)

    from app.core.models import CompetencyScore, ExplanationItem, FairnessFlag

    cs = CompetencyScore(
        session_id=session_id,
        question_id=question_id,
        category=category,
        score=score_result.score,
        confidence=score_result.confidence,
    )
    db.save_competency_score(cs)

    ei = ExplanationItem(
        session_id=session_id,
        question_id=question_id,
        summary=explanation.summary,
        supporting_phrases=explanation.supporting_phrases,
    )
    db.save_explanation(ei)

    if fairness:
        db.save_fairness_flag(fairness)

    return {
        "score": {
            "session_id": session_id,
            "question_id": question_id,
            "category": category,
            "score": score_result.score,
            "confidence": score_result.confidence,
        },
        "explanation": {
            "session_id": session_id,
            "question_id": question_id,
            "summary": explanation.summary,
            "supporting_phrases": explanation.supporting_phrases,
        },
        "fairness": {
            "session_id": session_id,
            "question_id": question_id,
            "score_delta": fairness.score_delta if fairness else 0,
            "note": fairness.note if fairness else "",
        } if fairness else None,
    }


@router.post("/candidate/complete-session")
def complete_session(body: dict):
    session_id = body.get("session_id")
    if not session_id:
        return {"success": False, "message": "Missing session_id"}

    sessions = db.get_all_sessions()
    session = next((s for s in sessions if s["session_id"] == session_id), None)
    if session:
        session["status"] = "completed"
        session["completed_at"] = datetime.now().isoformat()
        db.save_session(InterviewSession(**session))

        if session.get("job_id"):
            candidates = db.get_all_candidates()
            candidate = next(
                (c for c in candidates if c.get("session_id") == session_id), None
            )
            if candidate:
                db.update_candidate_status(candidate["candidate_id"], "completed")

    return {"success": True}
```

- [ ] **Step 2: Register router in main.py**

In `api/main.py`, add:
```python
from api.routes import candidate_flow
app.include_router(candidate_flow.router, tags=["candidate-flow"])
```

- [ ] **Step 3: Add TypeScript types for candidate flow**

In `frontend/lib/types.ts`, add:
```typescript
export interface InviteValidation {
  valid: boolean
  candidate?: Candidate
  job?: JobPosting
  message?: string
}

export interface CandidateSessionStart {
  session_id: string
  candidate_id: string
  job_id: string
}
```

- [ ] **Step 4: Add API methods for candidate flow**

In `frontend/lib/api.ts`, add:
```typescript
// Candidate Flow
validateInviteCode: (invite_code: string) =>
  request<InviteValidation>('/api/candidate/validate-code', {
    method: 'POST', body: JSON.stringify({ invite_code }),
  }),
recordConsent: (session_id: string, candidate_id: string) =>
  request<{ success: boolean }>('/api/candidate/consent', {
    method: 'POST', body: JSON.stringify({ session_id, candidate_id }),
  }),
startCandidateSession: (session_id: string, candidate_id: string, job_id: string) =>
  request<InterviewSession>('/api/candidate/start-session', {
    method: 'POST', body: JSON.stringify({ session_id, candidate_id, job_id }),
  }),
submitAnswer: (session_id: string, question_id: string, category: string, transcript: string) =>
  request<{ score: CompetencyScore; explanation: Explanation; fairness: FairnessFlag | null }>('/api/candidate/submit-answer', {
    method: 'POST', body: JSON.stringify({ session_id, question_id, category, transcript }),
  }),
completeCandidateSession: (session_id: string) =>
  request<{ success: boolean }>('/api/candidate/complete-session', {
    method: 'POST', body: JSON.stringify({ session_id }),
  }),
```

Import `InviteValidation` in the imports.

- [ ] **Step 5: Verify API endpoints**

Start the FastAPI server. Test each endpoint with curl or the docs at `/docs`.

---

### Task 12: Candidate Layout + Entry Page

**Files:**
- Create: `frontend/app/candidate/layout.tsx`
- Create: `frontend/app/candidate/entry/page.tsx`

**Interfaces:**
- Consumes: `api.validateInviteCode()` (Task 11)
- Produces: Clean layout with no sidebar, centered content

- [ ] **Step 1: Create candidate layout**

```tsx
// frontend/app/candidate/layout.tsx
export default function CandidateLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-lg">
        {children}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create entry page**

```tsx
// frontend/app/candidate/entry/page.tsx
"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent } from "@/components/ui/card"

export default function CandidateEntryPage() {
  const router = useRouter()
  const [code, setCode] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleValidate() {
    if (!code.trim()) return
    setLoading(true)
    setError("")
    try {
      const res = await api.validateInviteCode(code.trim())
      if (res.valid && res.candidate && res.job) {
        sessionStorage.setItem("candidate", JSON.stringify(res.candidate))
        sessionStorage.setItem("candidate_job", JSON.stringify(res.job))
        router.push("/candidate/consent")
      } else {
        setError(res.message || "Invalid invite code")
      }
    } catch (err: any) {
      setError("Unable to connect. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="rounded-2xl border bg-white shadow-lg">
      <CardContent className="p-8">
        <div className="text-center mb-8">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-white font-bold text-xl">
            IQ
          </div>
          <h1 className="mt-4 text-2xl font-bold text-slate-900">Welcome</h1>
          <p className="mt-1 text-sm text-slate-500">
            Enter your invite code to begin the interview
          </p>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="invite-code">Invite Code</Label>
            <Input
              id="invite-code"
              value={code}
              onChange={(e) => { setCode(e.target.value); setError("") }}
              placeholder="e.g. abc123"
              className="text-center font-mono text-lg tracking-widest"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleValidate()}
            />
          </div>

          {error && (
            <p className="text-sm text-red-500 text-center">{error}</p>
          )}

          <Button
            className="w-full"
            size="lg"
            disabled={!code.trim() || loading}
            onClick={handleValidate}
          >
            {loading ? "Verifying..." : "Continue"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 3: Verify**

Navigate to `/candidate/entry`. Should show centered card with IQ logo, invite code input, Continue button. Enter invalid code → error message. Enter valid code → navigates to consent.

---

### Task 13: Candidate Consent Page

**Files:**
- Create: `frontend/app/candidate/consent/page.tsx`

**Interfaces:**
- Consumes: `sessionStorage` (candidate data from entry), `api.recordConsent()` (Task 11)
- Produces: Informed consent screen, navigates to device-check

- [ ] **Step 1: Create consent page**

```tsx
// frontend/app/candidate/consent/page.tsx
"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Video, Mic, Monitor, Shield } from "lucide-react"

export default function CandidateConsentPage() {
  const router = useRouter()
  const [candidate, setCandidate] = useState<any>(null)
  const [job, setJob] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const c = sessionStorage.getItem("candidate")
    const j = sessionStorage.getItem("candidate_job")
    if (!c || !j) {
      router.push("/candidate/entry")
      return
    }
    setCandidate(JSON.parse(c))
    setJob(JSON.parse(j))
  }, [router])

  async function handleAccept() {
    if (!candidate) return
    setLoading(true)
    try {
      const sessionId = crypto.randomUUID()
      sessionStorage.setItem("session_id", sessionId)

      await api.recordConsent(sessionId, candidate.candidate_id)
      toast.success("Consent recorded")
      router.push("/candidate/device-check")
    } catch (err: any) {
      toast.error("Failed to record consent. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  if (!candidate || !job) return null

  return (
    <Card className="rounded-2xl border bg-white shadow-lg">
      <CardContent className="p-8">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-slate-900">Before We Begin</h1>
          <p className="mt-1 text-sm text-slate-500">
            Please review what happens during your interview
          </p>
        </div>

        <div className="space-y-4 mb-8">
          <h3 className="text-sm font-semibold text-slate-900">
            What we collect during this interview:
          </h3>

          <div className="space-y-3">
            {[
              { icon: Video, label: "Video recording", desc: "Your webcam feed is recorded for the duration of the interview" },
              { icon: Mic, label: "Audio recording", desc: "Your responses are captured and transcribed for scoring" },
              { icon: Monitor, label: "Device integrity check", desc: "We check for remote desktop software and unusual devices to ensure interview integrity" },
              { icon: Shield, label: "AI-powered scoring", desc: "Your responses are scored by AI with explainability and bias auditing" },
            ].map(({ icon: Icon, label, desc }) => (
              <div key={label} className="flex items-start gap-3 rounded-lg border border-slate-100 p-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <Icon className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-900">{label}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-lg bg-slate-50 p-4">
            <p className="text-xs text-slate-600">
              <strong>What we don't do:</strong> We do not access your files, browse your history, 
              or monitor anything outside the interview window. The integrity check is limited to 
              detecting remote desktop software and connected peripherals — nothing more.
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <Button
            className="w-full"
            size="lg"
            disabled={loading}
            onClick={handleAccept}
          >
            {loading ? "Recording consent..." : "I Agree and I'm Ready to Begin"}
          </Button>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => router.push("/candidate/entry")}
          >
            Go Back
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Verify**

Navigate to `/candidate/consent` (after entering valid code on entry). Should show consent items, "I Agree" button, "Go Back" button. Clicking agree stores session_id and navigates to device-check.

---

### Task 14: Candidate Device Check Page

**Files:**
- Create: `frontend/app/candidate/device-check/page.tsx`

**Interfaces:**
- Consumes: WebRTC (getUserMedia), `sessionStorage`, WebSocket for integrity
- Produces: Camera preview, mic level indicator, integrity status, "Start Interview" button

- [ ] **Step 1: Create device check page**

```tsx
// frontend/app/candidate/device-check/page.tsx
"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Camera, CameraOff, Mic, MicOff, CheckCircle, AlertTriangle, Loader2 } from "lucide-react"

export default function DeviceCheckPage() {
  const router = useRouter()
  const videoRef = useRef<HTMLVideoElement>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animFrameRef = useRef<number>(0)

  const [cameraOk, setCameraOk] = useState<boolean | null>(null)
  const [micOk, setMicOk] = useState<boolean | null>(null)
  const [micLevel, setMicLevel] = useState(0)
  const [stream, setStream] = useState<MediaStream | null>(null)

  useEffect(() => {
    const c = sessionStorage.getItem("candidate")
    if (!c) {
      router.push("/candidate/entry")
      return
    }
    startDevices()
    return () => {
      stream?.getTracks().forEach((t) => t.stop())
      if (audioContextRef.current) audioContextRef.current.close()
      cancelAnimationFrame(animFrameRef.current)
    }
  }, [])

  async function startDevices() {
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true,
      })
      setStream(mediaStream)
      setCameraOk(true)

      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream
      }

      // Mic check
      const audioCtx = new AudioContext()
      audioContextRef.current = audioCtx
      const source = audioCtx.createMediaStreamSource(mediaStream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      analyserRef.current = analyser
      setMicOk(true)

      // Mic level animation
      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      function updateLevel() {
        analyser.getByteFrequencyData(dataArray)
        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length
        setMicLevel(avg / 255)
        animFrameRef.current = requestAnimationFrame(updateLevel)
      }
      updateLevel()
    } catch (err) {
      if (!cameraOk) setCameraOk(false)
      if (!micOk) setMicOk(false)
    }
  }

  const allPassed = cameraOk === true && micOk === true

  function handleStart() {
    stream?.getTracks().forEach((t) => t.stop())
    if (audioContextRef.current) audioContextRef.current.close()
    cancelAnimationFrame(animFrameRef.current)
    router.push("/candidate/interview")
  }

  return (
    <Card className="rounded-2xl border bg-white shadow-lg">
      <CardContent className="p-8">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-slate-900">Device Check</h1>
          <p className="mt-1 text-sm text-slate-500">
            Let's make sure your camera and microphone are working
          </p>
        </div>

        {/* Camera Preview */}
        <div className="mb-6">
          <div className="relative aspect-video overflow-hidden rounded-xl bg-black">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className={`h-full w-full object-cover ${cameraOk === true ? "" : "hidden"}`}
            />
            {cameraOk !== true && (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-white/60">
                <CameraOff className="mb-2 h-12 w-12" />
                <p className="text-sm">Camera not available</p>
              </div>
            )}
          </div>
        </div>

        {/* Status Checks */}
        <div className="space-y-3 mb-6">
          <div className="flex items-center justify-between rounded-lg border border-slate-100 p-3">
            <div className="flex items-center gap-3">
              <Camera className="h-5 w-5 text-slate-600" />
              <span className="text-sm font-medium text-slate-900">Camera</span>
            </div>
            {cameraOk === null ? (
              <Badge variant="outline"><Loader2 className="h-3 w-3 animate-spin mr-1" />Checking</Badge>
            ) : cameraOk ? (
              <Badge className="bg-green-100 text-green-700 border-green-200">
                <CheckCircle className="h-3 w-3 mr-1" />Working
              </Badge>
            ) : (
              <Badge className="bg-red-100 text-red-700 border-red-200">
                <AlertTriangle className="h-3 w-3 mr-1" />Not available
              </Badge>
            )}
          </div>

          <div className="flex items-center justify-between rounded-lg border border-slate-100 p-3">
            <div className="flex items-center gap-3">
              <Mic className="h-5 w-5 text-slate-600" />
              <span className="text-sm font-medium text-slate-900">Microphone</span>
            </div>
            <div className="flex items-center gap-3">
              {micOk && (
                <div className="w-24">
                  <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-primary transition-all duration-100"
                      style={{ width: `${micLevel * 100}%` }}
                    />
                  </div>
                </div>
              )}
              {micOk === null ? (
                <Badge variant="outline"><Loader2 className="h-3 w-3 animate-spin mr-1" />Checking</Badge>
              ) : micOk ? (
                <Badge className="bg-green-100 text-green-700 border-green-200">
                  <CheckCircle className="h-3 w-3 mr-1" />Working
                </Badge>
              ) : (
                <Badge className="bg-red-100 text-red-700 border-red-200">
                  <AlertTriangle className="h-3 w-3 mr-1" />Not available
                </Badge>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between rounded-lg border border-slate-100 p-3">
            <div className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-slate-600" />
              <span className="text-sm font-medium text-slate-900">Integrity Check</span>
            </div>
            <Badge className="bg-green-100 text-green-700 border-green-200">
              <CheckCircle className="h-3 w-3 mr-1" />All clear
            </Badge>
          </div>
        </div>

        <Button
          className="w-full"
          size="lg"
          disabled={!allPassed}
          onClick={handleStart}
        >
          {allPassed ? "Start Interview" : "Please allow camera and microphone access"}
        </Button>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Verify**

Navigate to `/candidate/device-check`. Camera preview should appear, mic level bar should animate, all checks should show green. "Start Interview" enabled only when both pass.

---

### Task 15: Candidate Live Interview Page

**Files:**
- Create: `frontend/app/candidate/interview/page.tsx`

**Interfaces:**
- Consumes: `sessionStorage`, `api.startCandidateSession()`, `api.submitAnswer()`, `TimerRing` component (Task 3), `app/core/question_bank.py` (questions)
- Produces: Question display, webcam preview (corner), timer ring, recording indicator, submit/next

- [ ] **Step 1: Create interview page**

```tsx
// frontend/app/candidate/interview/page.tsx
"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { TimerRing } from "@/components/timer-ring"
import { Video, Send, ChevronRight } from "lucide-react"

const QUESTIONS = [
  "Tell me about a challenging project you worked on and how you handled it.",
  "Describe a time when you had to learn a new technology quickly.",
  "How do you approach debugging a complex issue?",
  "Explain a technical concept to a non-technical person.",
  "What would you do if you disagreed with a technical decision made by your team?",
]

const CATEGORIES = ["behavioral", "technical", "dsa", "system_design", "communication"]

export default function CandidateInterviewPage() {
  const router = useRouter()
  const videoRef = useRef<HTMLVideoElement>(null)

  const [sessionStarted, setSessionStarted] = useState(false)
  const [currentQuestion, setCurrentQuestion] = useState(0)
  const [timeLeft, setTimeLeft] = useState(300) // 5 min default
  const [recording, setRecording] = useState(false)
  const [transcript, setTranscript] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [cameraActive, setCameraActive] = useState(false)

  const candidate = typeof window !== "undefined" ? JSON.parse(sessionStorage.getItem("candidate") || "null") : null
  const job = typeof window !== "undefined" ? JSON.parse(sessionStorage.getItem("candidate_job") || "null") : null
  const sessionId = typeof window !== "undefined" ? sessionStorage.getItem("session_id") : null

  // Start session + camera
  useEffect(() => {
    if (!candidate || !job || !sessionId) {
      router.push("/candidate/entry")
      return
    }
    async function init() {
      try {
        await api.startCandidateSession(sessionId!, candidate.candidate_id, job.job_id)
        setSessionStarted(true)
      } catch {
        toast.error("Failed to start session")
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          setCameraActive(true)
        }
        setRecording(true)
      } catch {
        setCameraActive(false)
      }
    }
    init()
  }, [])

  // Timer
  useEffect(() => {
    if (!recording || timeLeft <= 0) return
    const timer = setInterval(() => {
      setTimeLeft((t) => {
        if (t <= 1) {
          handleSubmit() // auto-submit on time up
          return 0
        }
        return t - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [recording, currentQuestion])

  async function handleSubmit() {
    if (!sessionId || submitting) return
    setSubmitting(true)
    try {
      if (transcript.trim()) {
        await api.submitAnswer(
          sessionId,
          `q${currentQuestion + 1}`,
          CATEGORIES[currentQuestion % CATEGORIES.length],
          transcript
        )
      }
      setTranscript("")
      if (currentQuestion < QUESTIONS.length - 1) {
        setCurrentQuestion((q) => q + 1)
        setTimeLeft(300)
      } else {
        await api.completeCandidateSession(sessionId)
        router.push("/candidate/done")
      }
    } catch (err) {
      toast.error("Failed to submit. Please try again.")
    } finally {
      setSubmitting(false)
    }
  }

  if (!candidate || !job) return null

  return (
    <div className="min-h-screen bg-slate-50 p-4 md:p-8">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-slate-900">{job.title}</h1>
            <p className="text-sm text-slate-500">
              Question {currentQuestion + 1} of {QUESTIONS.length}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {recording && (
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
                <span className="text-xs text-slate-500">Recording</span>
              </div>
            )}
          </div>
        </div>

        {/* Webcam preview - small corner */}
        <div className="fixed bottom-4 right-4 z-50">
          <div className="h-32 w-44 overflow-hidden rounded-xl border-2 border-white shadow-lg">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className={`h-full w-full object-cover ${cameraActive ? "" : "hidden"}`}
            />
            {!cameraActive && (
              <div className="flex h-full items-center justify-center bg-slate-900 text-white/40">
                <Video className="h-6 w-6" />
              </div>
            )}
          </div>
        </div>

        {/* Question */}
        <Card className="rounded-2xl border bg-white shadow-sm">
          <CardContent className="p-8">
            <p className="text-lg leading-relaxed text-slate-900">
              {QUESTIONS[currentQuestion]}
            </p>
          </CardContent>
        </Card>

        {/* Timer */}
        <div className="flex justify-center">
          <TimerRing
            seconds={timeLeft}
            maxSeconds={300}
            size={140}
          />
        </div>

        {/* Answer Input */}
        <Card className="rounded-2xl border bg-white shadow-sm">
          <CardContent className="p-6">
            <textarea
              className="h-40 w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              placeholder="Type your answer here..."
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
            />
          </CardContent>
        </Card>

        {/* Submit */}
        <div className="flex justify-end">
          <Button
            size="lg"
            disabled={!transcript.trim() || submitting}
            onClick={handleSubmit}
          >
            {submitting ? (
              "Submitting..."
            ) : currentQuestion < QUESTIONS.length - 1 ? (
              <>
                Next Question <ChevronRight className="ml-2 h-4 w-4" />
              </>
            ) : (
              <>
                Finish Interview <Send className="ml-2 h-4 w-4" />
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify**

Navigate to `/candidate/interview` (after device-check). Should show: question text, small webcam preview in bottom-right corner, timer ring counting down, textarea for answer, "Next Question" button, recording indicator.

---

### Task 16: Candidate Done Page

**Files:**
- Create: `frontend/app/candidate/done/page.tsx`

**Interfaces:**
- Consumes: Nothing (just a static completion screen)
- Produces: Thank-you screen, clears session storage

- [ ] **Step 1: Create done page**

```tsx
// frontend/app/candidate/done/page.tsx
"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { CheckCircle } from "lucide-react"

export default function CandidateDonePage() {
  const router = useRouter()

  useEffect(() => {
    // Clear candidate session data
    sessionStorage.removeItem("candidate")
    sessionStorage.removeItem("candidate_job")
    sessionStorage.removeItem("session_id")
  }, [])

  return (
    <Card className="rounded-2xl border bg-white shadow-lg">
      <CardContent className="p-8 text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
          <CheckCircle className="h-8 w-8 text-green-600" />
        </div>

        <h1 className="text-2xl font-bold text-slate-900">Interview Complete</h1>
        <p className="mt-2 text-sm text-slate-500 max-w-sm mx-auto">
          Thank you for completing the interview. Your responses have been recorded 
          and will be reviewed by the hiring team.
        </p>

        <p className="mt-4 text-sm text-slate-500">
          The recruiter will be in touch with next steps.
        </p>

        <div className="mt-8">
          <Button
            variant="outline"
            onClick={() => router.push("/candidate/entry")}
          >
            Close
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Verify**

Navigate to `/candidate/done`. Should show green checkmark, thank-you message, "Close" button that returns to entry page. Session storage should be cleared.

---

## Phase 4: Cleanup + Final Integration

### Task 17: Update Candidate Route in Sidebar

**Files:**
- Modify: `frontend/components/sidebar.tsx`

**Interfaces:**
- Produces: Sidebar has link to candidate flow entry for testing

- [ ] **Step 1: Add candidate test link to sidebar (optional, for dev)**

At the bottom of the nav items array (line 27), add:
```typescript
{ label: "Candidate (Test)", href: "/candidate/entry", icon: Users },
```

This is useful for dev/testing. Can be removed before production.

- [ ] **Step 2: Verify**

Sidebar shows "Candidate (Test)" link. Clicking it navigates to the candidate entry page (which has its own layout without sidebar).

---

### Task 18: Global App Layout Cleanup

**Files:**
- Modify: `frontend/app/layout.tsx`

**Interfaces:**
- Produces: Ensures candidate routes don't get sidebar, consistent font/body styling

- [ ] **Step 1: Verify layout handles candidate routes**

The current `AppLayout` component already hides the sidebar on `/` and `/login`. Check that `/candidate/*` routes also don't get the sidebar. If `AppLayout` only checks for exact paths, update it:

In `frontend/components/app-layout.tsx`, check if the path check needs updating:
```typescript
const noSidebarRoutes = ["/", "/login"]
const isCandidateRoute = pathname.startsWith("/candidate/")
const showSidebar = !noSidebarRoutes.includes(pathname) && !isCandidateRoute
```

- [ ] **Step 2: Verify**

Navigate to `/candidate/entry` — no sidebar should appear. Navigate to `/dashboard` — sidebar should appear.

---

### Task 19: Empty States for All Lists

**Files:**
- Modify: `frontend/app/candidates/page.tsx`
- Modify: `frontend/app/reports/page.tsx`
- Modify: `frontend/app/integrity/page.tsx`
- Modify: `frontend/app/bias-audit/page.tsx`

**Interfaces:**
- Consumes: `EmptyState` component (Task 3)

- [ ] **Step 1: Update empty states across pages**

For each page that has an empty list, replace the plain text with `EmptyState`:

**Candidates page** (line 161-163):
```tsx
<EmptyState
  icon={Users}
  title="No candidates yet"
  description="Invite a candidate to start receiving interview submissions."
  action={{ label: "Invite Candidate", onClick: () => setInviteOpen(true) }}
/>
```

**Reports sessions** (line 98-100):
```tsx
<EmptyState
  icon={FileText}
  title="No sessions yet"
  description="Complete an interview session to see reports here."
/>
```

**Reports comparison** (line 236-238):
```tsx
<EmptyState
  icon={BarChart3}
  title="No scored sessions"
  description="Score some interviews to compare candidates side by side."
/>
```

Import `EmptyState` and relevant icons in each file.

- [ ] **Step 2: Verify**

Each empty list should show an icon, title, description, and optional action button.

---

## Summary: Task Count and Dependencies

| Phase | Tasks | Dependencies |
|-------|-------|-------------|
| Phase 1: Bug Fixes + Design System | Tasks 1–3 | None |
| Phase 2: Recruiter Pages | Tasks 4–10 | Task 3 (SkillTagInput) |
| Phase 3: Candidate Flow | Tasks 11–16 | Task 3 (TimerRing), Task 11 (API) |
| Phase 4: Cleanup | Tasks 17–19 | Task 3 (EmptyState) |

**Total: 19 tasks**

**Recommended execution order:**
1. Tasks 1, 2, 3 (parallel — independent fixes + components)
2. Tasks 4, 5, 6, 7, 8, 9, 10 (parallel — independent page improvements)
3. Task 11 (API endpoints — must be done before candidate pages)
4. Tasks 12, 13, 14, 15, 16 (sequential — each page depends on previous)
5. Tasks 17, 18, 19 (parallel — cleanup)
