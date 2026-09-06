"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { isValidEmail } from "@/lib/email"
import type { Candidate, JobPosting } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Copy, RefreshCw, Upload, Trash2, Loader2, Users, Mail, AlertTriangle, Info } from "lucide-react"
import { EmptyState } from "@/components/empty-state"

const statusConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" }> = {
  invited: { label: "Invited", variant: "default" },
  in_progress: { label: "In Progress", variant: "warning" },
  completed: { label: "Completed", variant: "success" },
  expired: { label: "Expired", variant: "outline" },
}

const sourceConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" }> = {
  manual: { label: "Manual", variant: "outline" },
  email_auto: { label: "Auto (Email)", variant: "default" },
  apply_portal: { label: "Apply Portal", variant: "secondary" },
}

const screeningConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" }> = {
  pending: { label: "Pending", variant: "outline" },
  passed_threshold: { label: "Passed", variant: "success" },
  below_threshold: { label: "Below Threshold", variant: "warning" },
}

function modeStatusLabel(status: string): string {
  switch (status) {
    case "SHORTLISTED": return "Shortlisted"
    case "CONFIRMED": return "Confirmed"
    case "INVITED": return "Invited"
    case "COMPLETED": return "Completed"
    case "PROMOTED": return "Promoted to Mode 1"
    case "NOT_PROMOTED": return "Not promoted"
    default: return status
  }
}

function promotionBadgeTone(status: string): string {
  switch (status) {
    case "PROMOTED": return "text-success-text"
    case "NOT_PROMOTED": return "text-muted-foreground"
    default: return "text-muted-foreground"
  }
}

export default function CandidatesPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [jobs, setJobs] = useState<JobPosting[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [gmailConnected, setGmailConnected] = useState(false)

  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteForm, setInviteForm] = useState({ name: "", email: "", job_id: "" })
  const [inviteLoading, setInviteLoading] = useState(false)
  const [inviteResumeFile, setInviteResumeFile] = useState<File | null>(null)
  const [createdCandidate, setCreatedCandidate] = useState<Candidate | null>(null)

  const [revokeTarget, setRevokeTarget] = useState<Candidate | null>(null)
  const [revokeLoading, setRevokeLoading] = useState(false)

  const [detailTarget, setDetailTarget] = useState<Candidate | null>(null)

  const [uploadingId, setUploadingId] = useState<string | null>(null)
  const [checkingJobs, setCheckingJobs] = useState<Record<string, boolean>>({})

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [cands, jobList] = await Promise.all([api.getCandidates(), api.getJobs()])
      setCandidates(cands)
      setJobs(jobList)
      api.getGmailStatus().then((s) => setGmailConnected(s.connected)).catch(() => {})
    } catch (err: any) {
      setError(err.message || "Failed to load data")
      toast.error("Failed to load candidates")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  function getJobTitle(jobId: string): string {
    return jobs.find((j) => j.job_id === jobId)?.title ?? jobId
  }

  // Default sort: ATS/resume match score descending, unscored rows last.
  const sortedCandidates = candidates
    .map((c) => c)
    .sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1))

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault()
    if (!isValidEmail(inviteForm.email)) {
      toast.error("Please enter a valid email address.")
      return
    }
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
      setInviteForm({ name: "", email: "", job_id: "" })
      setInviteResumeFile(null)
      await fetchData()
    } catch (err: any) {
      toast.error(err.message || "Failed to invite candidate")
    } finally {
      setInviteLoading(false)
    }
  }

  async function handleCopyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      toast.success("Invite code copied to clipboard")
    } catch {
      toast.error("Failed to copy code")
    }
  }

  async function handleResend(candidate: Candidate) {
    try {
      const res = await api.resendInvite(candidate.candidate_id)
      toast.success(`New invite code: ${res.invite_code}`)
    } catch (err: any) {
      toast.error(err.message || "Failed to resend invite")
    }
  }

  async function handleFileSelect(candidateId: string, file: File) {
    setUploadingId(candidateId)
    try {
      const updated = await api.uploadResume(candidateId, file)
      setCandidates((prev) => prev.map((c) => (c.candidate_id === candidateId ? updated : c)))
      const skillSummary = updated.matched_skills.length > 0
        ? `Matched: ${updated.matched_skills.join(", ")}`
        : "No skills matched"
      toast.success(`Resume uploaded — ${skillSummary}`)
    } catch (err: any) {
      toast.error(err.message || "Failed to upload resume")
    } finally {
      setUploadingId(null)
    }
  }

  async function handleRevoke() {
    if (!revokeTarget) return
    setRevokeLoading(true)
    try {
      await api.deleteCandidate(revokeTarget.candidate_id)
      toast.success("Candidate revoked")
      setRevokeTarget(null)
      await fetchData()
    } catch (err: any) {
      toast.error(err.message || "Failed to revoke candidate")
    } finally {
      setRevokeLoading(false)
    }
  }

  async function handleCheckApplications(jobId: string) {
    setCheckingJobs((prev) => ({ ...prev, [jobId]: true }))
    try {
      const result = await api.checkEmailApplications(jobId)
      toast.success(result.summary || "Check complete")
      await fetchData()
    } catch (err: any) {
      toast.error(err.message || "Failed to check applications")
    } finally {
      setCheckingJobs((prev) => ({ ...prev, [jobId]: false }))
    }
  }

  const jobsWithLabels = jobs.filter((j) => j.application_gmail_label)

  return (
    <div className="space-y-6 px-8 py-6">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Candidates</h1>
            <p className="text-sm leading-relaxed text-muted-foreground">Manage interview candidates</p>
          </div>
          <div className="flex items-center gap-2">
            {jobsWithLabels.length > 0 ? (
              jobsWithLabels.map((job) => (
                <Button
                  key={job.job_id}
                  variant="outline"
                  size="sm"
                  onClick={() => handleCheckApplications(job.job_id)}
                  disabled={checkingJobs[job.job_id]}
                >
                  {checkingJobs[job.job_id] ? (
                    <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
                  ) : (
                    <Mail className="h-3 w-3 mr-1.5" />
                  )}
                  Check {job.title}
                </Button>
              ))
            ) : gmailConnected ? (
              <span className="text-xs text-muted-foreground">Set a Gmail label on a job posting to enable auto-check.</span>
            ) : null}
            <Button onClick={() => setInviteOpen(true)}>Invite Candidate</Button>
          </div>
        </div>

        {!gmailConnected && (
          <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
            <Info className="h-4 w-4 mt-0.5 shrink-0" />
            <p>
              Gmail not connected. To auto-import candidates from email, go to <strong>Settings → Email Integration</strong> and connect Gmail. Then set a Gmail label on your job postings.
            </p>
          </div>
        )}

        <Card>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center p-12">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                <span className="ml-2 text-sm text-muted-foreground">Loading candidates...</span>
              </div>
            ) : error ? (
              <div className="p-12 text-center">
                <p className="text-sm text-destructive">{error}</p>
                <Button variant="outline" className="mt-4" onClick={fetchData}>Retry</Button>
              </div>
            ) : candidates.length === 0 ? (
              <EmptyState
                icon={Users}
                title="No candidates"
                description="Invite your first candidate to get started."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Job</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Screening</TableHead>
                    <TableHead>Mode</TableHead>
                    <TableHead>Mode 2 Score</TableHead>
                    <TableHead>Rank</TableHead>
                    <TableHead>Invite Code</TableHead>
                    <TableHead>Match Score</TableHead>
                    <TableHead>Skills</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedCandidates.map((c) => (
                    <CandidateRow
                      key={c.candidate_id}
                      candidate={c}
                      jobTitle={getJobTitle(c.job_id)}
                      uploadingId={uploadingId}
                      onCopyCode={handleCopyCode}
                      onResend={handleResend}
                      onFileSelect={handleFileSelect}
                      onRevoke={setRevokeTarget}
                      onDetail={setDetailTarget}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {!loading && candidates.some((c) => c.resume_path) && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-foreground">Resume Matches</h2>
            {candidates.filter((c) => c.resume_path).map((c) => (
              <Card key={c.candidate_id}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">{c.name}</CardTitle>
                  <CardDescription>{getJobTitle(c.job_id)}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {c.matched_skills.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-muted-foreground">Matched Skills</p>
                      <div className="flex flex-wrap gap-1.5">
                        {c.matched_skills.map((skill) => (
                          <Badge key={skill} variant="success">{skill}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {c.missing_skills.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-muted-foreground">Missing Skills</p>
                      <div className="flex flex-wrap gap-1.5">
                        {c.missing_skills.map((skill) => (
                          <Badge key={skill} variant="destructive">{skill}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {c.match_score != null && (
                    <div>
                      <div className="mb-1 flex items-center justify-between">
                        <p className="text-xs font-medium text-muted-foreground">Match Score</p>
                        <span className="text-xs font-semibold text-foreground">
                          {Math.round(c.match_score)}%
                        </span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${Math.min(100, Math.max(0, c.match_score))}%` }}
                        />
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

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
                <p className="text-xs text-muted-foreground mb-2">Invite Code</p>
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
            <>
              <DialogHeader>
                <DialogTitle>Invite Candidate</DialogTitle>
                <DialogDescription>
                  Send an interview invitation to a new candidate.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={handleInvite} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="invite-name">Name</Label>
                  <Input
                    id="invite-name"
                    placeholder="Full name"
                    required
                    value={inviteForm.name}
                    onChange={(e) => setInviteForm({ ...inviteForm, name: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="invite-email">Email</Label>
                  <Input
                    id="invite-email"
                    type="email"
                    placeholder="candidate@example.com"
                    required
                    value={inviteForm.email}
                    onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Job Posting</Label>
                  <Select
                    required
                    value={inviteForm.job_id}
                    onValueChange={(val) => setInviteForm({ ...inviteForm, job_id: val })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select a job posting" />
                    </SelectTrigger>
                    <SelectContent>
                      {jobs.map((job) => (
                        <SelectItem key={job.job_id} value={job.job_id}>
                          {job.title}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="invite-resume">Resume (optional)</Label>
                  <Input
                    id="invite-resume"
                    type="file"
                    accept=".pdf,.docx,.txt"
                    onChange={(e) => setInviteResumeFile(e.target.files?.[0] ?? null)}
                  />
                  <p className="text-xs text-muted-foreground">PDF, DOCX, or TXT — drives JD-match scoring</p>
                </div>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setInviteOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={inviteLoading || !inviteForm.job_id}>
                    {inviteLoading ? "Inviting..." : "Invite"}
                  </Button>
                </DialogFooter>
              </form>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!revokeTarget} onOpenChange={(open) => { if (!open) setRevokeTarget(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke Candidate</DialogTitle>
            <DialogDescription>
              Are you sure you want to revoke {revokeTarget?.name}? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevokeTarget(null)}>Cancel</Button>
            <Button variant="destructive" disabled={revokeLoading} onClick={handleRevoke}>
              {revokeLoading ? "Revoking..." : "Revoke"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!detailTarget} onOpenChange={(open) => { if (!open) setDetailTarget(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Why shortlisted?</DialogTitle>
            <DialogDescription>
              {detailTarget?.name} · {getJobTitle(detailTarget?.job_id ?? "")}
            </DialogDescription>
          </DialogHeader>
          {detailTarget?.screening_result ? (
            <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
              <div className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/60 px-3 py-2">
                <Badge variant={detailTarget.screening_result.decision === "passed" ? "success" : "warning"}>
                  {detailTarget.screening_result.decision}
                </Badge>
                <span className="text-xs leading-relaxed text-muted-foreground">
                  {detailTarget.screening_result.decision_reason}
                </span>
              </div>

              <ScoreBar label="ATS score (0–100)" value={detailTarget.screening_result.ats_score ?? 0}
                        threshold={detailTarget.screening_result.threshold_used ?? undefined} highlight />
              {(["skills", "experience", "semantic", "education", "keyword"] as const).map((key) => {
                const value = detailTarget.screening_result?.[key === "skills" ? "skills_score"
                  : key === "experience" ? "experience_score"
                  : key === "semantic" ? "semantic_score"
                  : key === "education" ? "education_score"
                  : "keyword_score"] as number | null | undefined
                return <ScoreBar key={key} label={`${key[0].toUpperCase()}${key.slice(1)}`} value={value ?? 0} />
              })}

              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Hard requirements</p>
                {detailTarget.screening_result.hard_requirements_passed ? (
                  <span className="text-xs text-emerald-600">All hard gates cleared</span>
                ) : (
                  <ul className="space-y-1">
                    {detailTarget.screening_result.hard_requirement_failures.map((f) => (
                      <li key={f} className="flex items-start gap-1.5 text-xs text-destructive">
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {f}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {detailTarget.screening_result.matched_skills.length > 0 && (
                  <div>
                    <p className="mb-1 text-xs font-medium text-muted-foreground">Matched skills</p>
                    <div className="flex flex-wrap gap-1.5">
                      {detailTarget.screening_result.matched_skills.map((s) => (
                        <Badge key={s} variant="success" className="text-[10px]">{s}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {detailTarget.screening_result.missing_skills.length > 0 && (
                  <div>
                    <p className="mb-1 text-xs font-medium text-muted-foreground">Missing skills</p>
                    <div className="flex flex-wrap gap-1.5">
                      {detailTarget.screening_result.missing_skills.map((s) => (
                        <Badge key={s} variant="destructive" className="text-[10px]">{s}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <p className="text-sm leading-relaxed text-muted-foreground">
              Invited manually — no automated screening decision was generated for this candidate.
            </p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function ScoreBar({ label, value, threshold, highlight }: { label: string; value: number; threshold?: number; highlight?: boolean }) {
  const pct = Math.min(100, Math.max(0, value))
  const color = !highlight ? "bg-primary" : value >= (threshold ?? 60) ? "bg-emerald-500" : "bg-amber-500"
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <span className="text-xs font-semibold text-foreground">
          {Math.round(value)}{threshold != null ? ` / ${threshold}` : ""}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

interface CandidateRowProps {
  candidate: Candidate
  jobTitle: string
  uploadingId: string | null
  onCopyCode: (code: string) => void
  onResend: (candidate: Candidate) => void
  onFileSelect: (candidateId: string, file: File) => void
  onRevoke: (candidate: Candidate) => void
  onDetail: (candidate: Candidate) => void
}

function CandidateRow({
  candidate: c,
  jobTitle,
  uploadingId,
  onCopyCode,
  onResend,
  onFileSelect,
  onRevoke,
  onDetail,
}: CandidateRowProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const isUploading = uploadingId === c.candidate_id
  const status = statusConfig[c.status] ?? { label: c.status, variant: "outline" as const }
  const source = sourceConfig[c.source] ?? { label: c.source, variant: "outline" as const }
  const screening = screeningConfig[c.screening_status] ?? { label: c.screening_status, variant: "outline" as const }
  const showEmailWarning = c.source === "email_auto" && c.screening_status === "passed_threshold" && !c.invite_email_sent

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) {
      onFileSelect(c.candidate_id, file)
      e.target.value = ""
    }
  }

  return (
    <TableRow>
      <TableCell className="font-medium">{c.name}</TableCell>
      <TableCell className="text-muted-foreground">{c.email}</TableCell>
      <TableCell>{jobTitle}</TableCell>
      <TableCell>
        <Badge variant={status.variant}>{status.label}</Badge>
      </TableCell>
      <TableCell>
        <Badge variant={source.variant}>{source.label}</Badge>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-1.5">
          <Badge variant={screening.variant}>{screening.label}</Badge>
          {showEmailWarning && (
            <span title="Invite email failed to send — use Resend"><AlertTriangle className="h-3.5 w-3.5 text-warning" /></span>
          )}
        </div>
      </TableCell>
      <TableCell>
        {c.interview_mode ? (
          <div className="flex flex-col gap-1">
            <Badge variant={c.interview_mode === "MODE_1" ? "default" : "secondary"} className="w-fit">
              {c.interview_mode.replace("_", " ")}
            </Badge>
            {c.mode_status ? (
              <span className={`text-[10px] ${promotionBadgeTone(c.mode_status)}`}>
                {modeStatusLabel(c.mode_status)}
              </span>
            ) : null}
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        {c.mode2_score != null ? (
          <span className="text-sm tabular-nums text-foreground">{c.mode2_score.toFixed(1)}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        {c.rank != null ? (
          <span className="text-sm font-medium tabular-nums text-foreground">#{c.rank}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        <code className="rounded bg-muted px-2 py-0.5 text-xs font-mono text-foreground">
          {c.invite_code}
        </code>
      </TableCell>
      <TableCell>
        {c.match_score != null ? (
          <Badge
            variant={
              c.match_score >= 70
                ? "success"
                : c.match_score >= 40
                  ? "warning"
                  : "destructive"
            }
          >
            {Math.round(c.match_score)}%
          </Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-1 max-w-[200px]">
          {c.matched_skills.slice(0, 2).map((s) => (
            <Badge key={s} variant="success" className="text-[10px]">{s}</Badge>
          ))}
          {c.missing_skills.slice(0, 2).map((s) => (
            <Badge key={s} variant="destructive" className="text-[10px]">{s}</Badge>
          ))}
          {(c.matched_skills.length + c.missing_skills.length) > 4 && (
            <Badge variant="outline" className="text-[10px]">+{c.matched_skills.length + c.missing_skills.length - 4}</Badge>
          )}
        </div>
      </TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-1">
          {c.screening_result && (
            <Button variant="ghost" size="sm" className="h-8" title="Why shortlisted?" onClick={() => onDetail(c)}>
              <Info className="h-4 w-4 mr-1.5" /> Why
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-8 w-8" title="Copy invite code" onClick={() => onCopyCode(c.invite_code)}>
            <Copy className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" title="Resend invite" onClick={() => onResend(c)}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <input type="file" ref={fileInputRef} className="hidden" accept=".pdf,.docx,.txt" onChange={handleFileChange} />
          <Button variant="ghost" size="icon" className="h-8 w-8" title="Attach resume" disabled={isUploading} onClick={() => fileInputRef.current?.click()}>
            {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" title="Revoke candidate" onClick={() => onRevoke(c)}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}
