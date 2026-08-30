# Public "Apply Now" Portal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Gmail-polling assumption with a public "Apply Now" portal as the primary application intake method, while keeping Gmail polling as a secondary path.

**Architecture:** The Gmail pipeline (`app/engine/email_intake.py`) was never tested against real Gmail — all tests use mocks, no `data/client_secret.json` exists, and the background poller never runs. LinkedIn/Naukri/Indeed provide no self-serve API for third-party application intake. The correct architecture is a company-hosted public application form. The new portal reuses the existing resume parser + JD matcher + candidate creation + invite-email pipeline. Shared processing logic is extracted from `email_intake.py` into a common module.

**Tech Stack:** FastAPI, Next.js 14, React 18, Tailwind CSS, SQLite, Vitest + @testing-library/react

**Spec:** Candidates visit a public `/apply/{jobId}` URL, upload their resume, and get screened. Qualified candidates receive an invite code and interview link. Recruiters get a "Copy Application Link" button on the Jobs page. Gmail pipeline stays as secondary (manual forwarding/referrals), not deleted.

## Investigation Findings

1. **Gmail pipeline is unverified**: `email_intake.py` creates `Credentials` with empty `client_id`/`client_secret` (line 50-51), no OAuth token refresh will work. Tests are all mocks.
2. **Shared processing logic** (lines 284-349 of `email_intake.py`): parse resume → match JD → check threshold → create Candidate → generate invite code → send invite email. This exact logic is needed by both Gmail intake and the new portal.
3. **`Candidate.source` field** already exists: values `"manual"` (default) and `"email_auto"`. Needs `"apply_portal"` added.
4. **SQLite schema** already has `source`, `screening_status`, `invite_email_sent` columns via `_migrate_email_intake_columns()` — no migration needed.
5. **Frontend `candidates/page.tsx`** has `sourceConfig` map (line 31-34) that needs `"apply_portal"` entry.
6. **No auth guard** on candidate-facing routes — the public apply page doesn't need authentication.
7. **Existing API client** (`frontend/lib/api.ts`) already has `requestForm()` for file uploads.

## Global Constraints

- Use existing design tokens from `globals.css` (primary: `hsl(243 75% 59%)`, card: white, background: `hsl(230 15% 97%)`)
- Use existing UI components from `frontend/components/ui/`
- Follow existing code conventions: `"use client"` for client components, Tailwind classes, existing folder structure
- Public apply page is unauthenticated (no login required)
- Gmail pipeline stays as-is (secondary path), only refactor shared logic out
- Do NOT modify existing candidate flow pages (`/candidate/*`)
- Do NOT delete or disable Gmail intake functionality

---

### Task 1: Extract shared processing logic into `app/engine/application_processor.py`

**Files:**
- Create: `app/engine/application_processor.py`
- Modify: `app/engine/email_intake.py` (refactor to call shared function)

**Interfaces:**
- Consumes: `app.engine.resume_parser.parse_resume`, `app.engine.jd_matcher.match_resume_to_jd`, `app.core.db`, `app.core.models.Candidate`, `app.engine.email_intake.compose_invite_email`
- Produces: `process_application()` function callable by both email intake and public apply endpoint

- [ ] **Step 1: Create `app/engine/application_processor.py` with `process_application()`**

This function extracts the core processing logic from `email_intake.py` lines 284-349. It takes a resume file path, job_id, applicant name, applicant email, and source string. It returns a result dict with `candidate_id`, `match_score`, `screening_status`, `status`, `invite_code`, `invite_email_sent`.

```python
"""
Shared application processing pipeline — reusable by both the Gmail
email intake and the public Apply Now portal.

Extracts the core logic: parse resume → match JD → check threshold →
create Candidate → generate invite code → send invite email.
"""
import logging
import secrets
from pathlib import Path

from app.core import db
from app.core.models import Candidate
from app.engine.resume_parser import parse_resume
from app.engine.jd_matcher import match_resume_to_jd
from app.engine.email_intake import compose_invite_email

logger = logging.getLogger(__name__)

RESUME_DIR = Path(__file__).parent.parent.parent / "data" / "resumes"


def process_application(
    resume_path: str,
    job_id: str,
    applicant_name: str,
    applicant_email: str,
    source: str = "manual",
    send_invite: bool = True,
    frontend_url: str = "",
) -> dict:
    """
    Process a job application: parse resume, match against JD, screen,
    create candidate record, optionally send invite email.

    Args:
        resume_path: Path to the saved resume file on disk.
        job_id: Job posting ID to match against.
        applicant_name: Name from the application form or email.
        applicant_email: Email from the application form or email.
        source: "manual", "email_auto", or "apply_portal".
        send_invite: Whether to send an invite email (True for email pipeline,
                     False for portal where candidate sees result immediately).
        frontend_url: Frontend base URL for invite link (remote mode only).

    Returns:
        dict with keys: candidate_id, match_score, screening_status,
        status, invite_code, invite_email_sent, error (None on success).
    """
    job = db.get_job_posting(job_id)
    if not job:
        return {"error": f"Job {job_id} not found"}

    try:
        resume_data = parse_resume(resume_path)
    except Exception as e:
        logger.warning("Resume parse failed for %s: %s", applicant_email, e)
        return {"error": f"Resume parsing failed: {e}"}

    match_result = match_resume_to_jd(resume_data, job["description"])
    match_score = match_result.get("match_score", 0.0)
    threshold = job.get("screening_threshold", 60.0)

    candidate_id = f"{source}-{secrets.token_hex(8)}"
    code = secrets.token_urlsafe(6)

    if match_score >= threshold:
        screening_status = "passed_threshold"
        status = "invited"
    else:
        screening_status = "below_threshold"
        status = "invited"

    candidate = Candidate(
        candidate_id=candidate_id,
        job_id=job_id,
        name=applicant_name or "Unknown Applicant",
        email=applicant_email or "",
        invite_code=code,
        status=status,
        source=source,
        screening_status=screening_status,
        invite_email_sent=False,
    )
    db.save_candidate(candidate)
    db.save_candidate_resume(
        candidate_id,
        resume_path,
        resume_data.get("skills", []),
        resume_data.get("experience_years"),
        match_score,
        match_result.get("matched_skills", []),
        match_result.get("missing_skills", []),
    )

    invite_email_sent = False
    if send_invite and match_score >= threshold:
        try:
            from app.core.settings_store import load_settings
            settings = load_settings()
            url = frontend_url or (
                settings.get("remote_api_url", "")
                if settings.get("backend_mode") == "remote"
                else ""
            )
            email_msg = compose_invite_email(
                {"name": candidate.name, "email": candidate.email},
                {"title": job["title"]},
                code,
                url,
            )
            email_msg["to"] = candidate.email
            email_msg["from"] = settings.get("gmail_user", "")
            import base64
            from app.engine.email_intake import get_gmail_service
            service = get_gmail_service()
            if service:
                raw = base64.urlsafe_b64encode(email_msg.as_bytes()).decode()
                service.users().messages().send(
                    userId="me", body={"raw": raw}
                ).execute()
                db.update_candidate_invite_email_sent(candidate_id, True)
                invite_email_sent = True
        except Exception as e:
            logger.error("Failed to send invite email to %s: %s", applicant_email, e)

    return {
        "candidate_id": candidate_id,
        "match_score": match_score,
        "screening_status": screening_status,
        "status": status,
        "invite_code": code,
        "invite_email_sent": invite_email_sent,
        "matched_skills": match_result.get("matched_skills", []),
        "missing_skills": match_result.get("missing_skills", []),
        "error": None,
    }
```

- [ ] **Step 2: Refactor `email_intake.py` to use `process_application()`**

Replace lines 284-349 in `check_for_new_applications()` (the inner loop body after attachment download) with a call to `process_application()`. Keep Gmail-specific logic (message listing, attachment download, marking as read) in `email_intake.py`.

The refactored loop body becomes approximately:
```python
# After downloading file_data and saving resume_path...
result = process_application(
    resume_path=str(resume_path),
    job_id=job_id,
    applicant_name=sender_name or "Unknown Applicant",
    applicant_email=sender_email or "",
    source="email_auto",
    send_invite=True,
    frontend_url=frontend_url,
)
if result.get("error"):
    results.append({"message_id": message_id, "status": "skipped", "reason": result["error"]})
else:
    results.append({
        "message_id": message_id,
        "status": result["status"] if result["invite_email_sent"] else "invite_send_failed",
        "candidate_id": result["candidate_id"],
        "match_score": result["match_score"],
    })
```

- [ ] **Step 3: Verify existing email intake tests still pass**

Run: `pytest tests/test_email_intake.py -v`

The mocks in `test_email_intake.py` patch `parse_resume`, `match_resume_to_jd`, and `db` functions — since `process_application()` calls the same underlying functions, the existing tests should pass with minimal or no changes. If `compose_invite_email` import path changes, update the mock target.

---

### Task 2: Backend public apply endpoint + public job details

**Files:**
- Create: `api/routes/public_apply.py`
- Modify: `api/main.py` (register new router)
- Modify: `app/core/models.py` (extend `Candidate.source` docstring)
- Modify: `api/schemas.py` (add `PublicJobResponse`, `ApplyRequest`)

**Interfaces:**
- Consumes: `app.engine.application_processor.process_application`, `app.core.db`
- Produces: `POST /api/public/apply/{job_id}` and `GET /api/public/jobs/{job_id}` endpoints

- [ ] **Step 1: Add schemas to `api/schemas.py`**

```python
class PublicJobResponse(BaseModel):
    job_id: str
    title: str
    description: str
    required_skills: list[str]
    experience_level: str
    department: str

class ApplyRequest(BaseModel):
    name: str
    email: str

class ApplyResponse(BaseModel):
    success: bool
    candidate_id: str
    match_score: float
    screening_status: str
    invite_code: str
    message: str
```

- [ ] **Step 2: Create `api/routes/public_apply.py`**

```python
"""
Public application intake — no authentication required.

Candidates visit /apply/{jobId}, upload their resume, and this endpoint
processes it through the shared screening pipeline.
"""
import secrets
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile, HTTPException

from app.core import db
from api.schemas import PublicJobResponse, ApplyResponse
from app.engine.application_processor import process_application

router = APIRouter()

RESUME_DIR = Path(__file__).parent.parent.parent / "data" / "resumes"


@router.get("/jobs/{job_id}", response_model=PublicJobResponse)
def get_public_job(job_id: str):
    """Return minimal job details for the public apply page (no auth required)."""
    job = db.get_job_posting(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found")
    return PublicJobResponse(
        job_id=job["job_id"],
        title=job["title"],
        description=job["description"],
        required_skills=job["required_skills"],
        experience_level=job["experience_level"],
        department=job["department"],
    )


@router.post("/apply/{job_id}", response_model=ApplyResponse)
async def apply_for_job(
    job_id: str,
    name: str = Form(...),
    email: str = Form(...),
    resume: UploadFile = File(...),
):
    """
    Submit a job application. Uploads resume, runs screening pipeline,
    creates candidate record. No authentication required.
    """
    job = db.get_job_posting(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found")

    # Validate file type
    allowed_types = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    }
    content_type = resume.content_type or ""
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Please upload PDF, DOCX, or TXT.",
        )

    # Save resume to disk
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(resume.filename or "resume.pdf").suffix or ".pdf"
    filename = f"apply-{job_id}-{secrets.token_hex(8)}{ext}"
    resume_path = RESUME_DIR / filename
    file_data = await resume.read()
    resume_path.write_bytes(file_data)

    # Process through shared pipeline
    result = process_application(
        resume_path=str(resume_path),
        job_id=job_id,
        applicant_name=name,
        applicant_email=email,
        source="apply_portal",
        send_invite=False,  # Portal shows result directly; invite sent later by recruiter
    )

    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])

    return ApplyResponse(
        success=True,
        candidate_id=result["candidate_id"],
        match_score=result["match_score"],
        screening_status=result["screening_status"],
        invite_code=result["invite_code"],
        message=(
            "Application received! You've been shortlisted for an interview."
            if result["screening_status"] == "passed_threshold"
            else "Application received. We'll review your application and get back to you."
        ),
    )
```

- [ ] **Step 3: Register router in `api/main.py`**

Add import and include_router:
```python
from api.routes import ... public_apply
...
app.include_router(public_apply.router, prefix="/api/public", tags=["public-apply"])
```

Place it alongside the other public/unauthenticated routes (near `candidate_flow`).

- [ ] **Step 4: Extend `Candidate.source` docstring in `app/core/models.py`**

Update line 101:
```python
source: str = "manual"  # "manual" | "email_auto" | "apply_portal"
```

- [ ] **Step 5: Add `"apply_portal"` to frontend `sourceConfig` in `frontend/app/candidates/page.tsx`**

At line 33, add:
```typescript
apply_portal: { label: "Apply Portal", variant: "secondary" },
```

- [ ] **Step 6: Write backend tests**

Create `tests/test_public_apply.py` with tests:
- `test_get_public_job_returns_job_details` — GET returns 200 with job title, description, skills
- `test_get_public_job_404_for_missing` — GET returns 404 for nonexistent job_id
- `test_apply_creates_candidate_with_portal_source` — POST with valid resume creates candidate with `source="apply_portal"`
- `test_apply_returns_screening_result` — POST returns match_score and screening_status
- `test_apply_404_for_missing_job` — POST returns 404 for nonexistent job_id
- `test_apply_rejects_invalid_file_type` — POST with .exe file returns 400

Use the existing test pattern from `tests/test_email_intake.py`: create a FastAPI TestClient, mock `parse_resume` and `match_resume_to_jd` to avoid real LLM calls.

---

### Task 3: Public apply page (Frontend)

**Files:**
- Create: `frontend/app/apply/[jobId]/page.tsx`

**Interfaces:**
- Consumes: `GET /api/public/jobs/{jobId}`, `POST /api/public/apply/{jobId}` (multipart form)
- Produces: Public-facing application form with resume upload

- [ ] **Step 1: Create `frontend/app/apply/[jobId]/page.tsx`**

This is a standalone public page (no sidebar, no auth). It fetches job details on mount, shows a form with name, email, and resume upload, submits via multipart POST, and shows the screening result.

Key UI elements:
- Job title and description header
- Required skills as badges
- Name and email inputs
- Resume file upload (PDF/DOCX/TXT)
- Submit button with loading state
- Success/failure result card showing screening status and invite code (if passed)

The page uses `getBaseUrl()` from `@/lib/api` for the public endpoints (no auth header needed). File upload uses native `FormData` + `fetch` (not the existing `requestForm` helper, since it's a different base path).

```tsx
"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Upload, CheckCircle, AlertCircle, Briefcase } from "lucide-react"
import { getBaseUrl } from "@/lib/api"

interface PublicJob {
  job_id: string
  title: string
  description: string
  required_skills: string[]
  experience_level: string
  department: string
}

interface ApplyResult {
  success: boolean
  candidate_id: string
  match_score: number
  screening_status: string
  invite_code: string
  message: string
}

export default function ApplyPage() {
  const params = useParams()
  const jobId = params.jobId as string

  const [job, setJob] = useState<PublicJob | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<ApplyResult | null>(null)

  useEffect(() => {
    async function fetchJob() {
      try {
        const base = await getBaseUrl()
        const res = await fetch(`${base}/api/public/jobs/${jobId}`)
        if (!res.ok) throw new Error("Job not found")
        setJob(await res.json())
      } catch (err: any) {
        setError(err.message || "Failed to load job details")
      } finally {
        setLoading(false)
      }
    }
    fetchJob()
  }, [jobId])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) return
    setSubmitting(true)
    try {
      const base = await getBaseUrl()
      const formData = new FormData()
      formData.append("name", name)
      formData.append("email", email)
      formData.append("resume", file)
      const res = await fetch(`${base}/api/public/apply/${jobId}`, {
        method: "POST",
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || "Application failed")
      }
      setResult(await res.json())
    } catch (err: any) {
      setError(err.message || "Failed to submit application")
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <p className="text-muted-foreground text-sm">Loading job details...</p>
      </div>
    )
  }

  if (error && !job) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <Card className="w-full max-w-md">
          <CardContent className="pt-6 text-center">
            <AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
            <p className="text-lg font-medium text-foreground">Job Not Found</p>
            <p className="text-sm text-muted-foreground mt-1">{error}</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (result) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <Card className="w-full max-w-md">
          <CardContent className="pt-6 text-center">
            <CheckCircle className="h-12 w-12 text-green-600 mx-auto mb-4" />
            <p className="text-lg font-medium text-foreground">Application Submitted</p>
            <p className="text-sm text-muted-foreground mt-1">{result.message}</p>
            {result.screening_status === "passed_threshold" && (
              <div className="mt-4 p-3 rounded-lg bg-muted">
                <p className="text-sm text-muted-foreground">Your invite code:</p>
                <p className="text-lg font-mono font-bold text-foreground">{result.invite_code}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-background px-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <div className="flex items-center gap-2 mb-2">
            <Briefcase className="h-5 w-5 text-primary" />
            <span className="text-sm text-muted-foreground">InterviewIQ</span>
          </div>
          <CardTitle className="text-xl">{job?.title}</CardTitle>
          <p className="text-sm text-muted-foreground">{job?.department} · {job?.experience_level}</p>
        </CardHeader>
        <CardContent>
          <div className="mb-4">
            <p className="text-sm text-muted-foreground mb-2">{job?.description}</p>
            <div className="flex flex-wrap gap-1.5">
              {job?.required_skills.map((skill) => (
                <Badge key={skill} variant="secondary" className="text-xs">{skill}</Badge>
              ))}
            </div>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Full Name</Label>
              <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@example.com" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="resume">Resume (PDF, DOCX, or TXT)</Label>
              <Input id="resume" type="file" required accept=".pdf,.docx,.txt"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
            <Button type="submit" className="w-full" disabled={submitting || !file}>
              {submitting ? "Submitting..." : "Submit Application"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
```

---

### Task 4: Recruiter "Copy Application Link" button on Jobs page

**Files:**
- Modify: `frontend/app/jobs/page.tsx`

**Interfaces:**
- Consumes: Job listing data
- Produces: "Copy Application Link" button per job row

- [ ] **Step 1: Add copy link button to each job row in `frontend/app/jobs/page.tsx`**

In the actions `<TableCell>` (line 366-386), add a "Copy Application Link" button before the existing Mail/Pencil/Trash buttons. The link format is `${window.location.origin}/apply/${job.job_id}`.

Add import: `import { Link, Check } from "lucide-react"` (add to existing lucide-react import on line 23).

Add state: `const [copiedJobId, setCopiedJobId] = useState<string | null>(null)`

Add handler:
```typescript
async function handleCopyApplicationLink(jobId: string) {
  const url = `${window.location.origin}/apply/${jobId}`
  await navigator.clipboard.writeText(url)
  setCopiedJobId(jobId)
  toast.success("Application link copied to clipboard")
  setTimeout(() => setCopiedJobId(null), 2000)
}
```

In the actions cell, add before the Mail button:
```tsx
<Button
  variant="ghost"
  size="icon"
  className="h-8 w-8"
  title="Copy application link"
  onClick={() => handleCopyApplicationLink(job.job_id)}
>
  {copiedJobId === job.job_id ? (
    <Check className="h-4 w-4 text-green-600" />
  ) : (
    <Link className="h-4 w-4" />
  )}
</Button>
```

---

### Task 5: Frontend tests for public apply page

**Files:**
- Create: `frontend/app/apply/__tests__/apply-page.test.tsx`

**Interfaces:**
- Consumes: The new apply page component
- Produces: Test file covering form rendering, submission, error states

- [ ] **Step 1: Create test file**

Tests:
- `renders job details after fetch` — mocks `fetch` to return job data, asserts title and skills appear
- `shows error state for invalid job` — mocks failed fetch, asserts error message
- `submits application with resume` — mocks successful POST, asserts result card with invite code
- `shows validation error for invalid file type` — client-side validation

Use the same test pattern as `frontend/app/__tests__/page.test.tsx` and `frontend/app/candidate/__tests__/candidate-flow.test.tsx`.

---

## Verification Checklist

After all tasks are complete:

1. **Backend tests pass**: `pytest tests/test_public_apply.py tests/test_email_intake.py -v`
2. **Frontend tests pass**: `cd frontend && npx vitest run`
3. **Manual flow works**:
   - Recruiter creates a job → copies application link → shares with candidate
   - Candidate visits `/apply/{jobId}` → uploads resume → sees screening result
   - Candidate appears in recruiter's Candidates list with source "Apply Portal"
   - Gmail intake still works (secondary path, not broken)
4. **No regressions**: Existing email intake tests still pass after refactor
