"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
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
import { Copy, RefreshCw, Upload, Trash2, Loader2 } from "lucide-react"

const statusConfig: Record<string, { label: string; className: string }> = {
  invited: { label: "Invited", className: "bg-blue-100 text-blue-700 border-blue-200" },
  in_progress: { label: "In Progress", className: "bg-amber-100 text-amber-700 border-amber-200" },
  completed: { label: "Completed", className: "bg-green-100 text-green-700 border-green-200" },
  expired: { label: "Expired", className: "bg-gray-100 text-gray-600 border-gray-200" },
}

export default function CandidatesPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [jobs, setJobs] = useState<JobPosting[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteForm, setInviteForm] = useState({ name: "", email: "", job_id: "" })
  const [inviteLoading, setInviteLoading] = useState(false)
  const [inviteResumeFile, setInviteResumeFile] = useState<File | null>(null)
  const [createdCandidate, setCreatedCandidate] = useState<Candidate | null>(null)

  const [revokeTarget, setRevokeTarget] = useState<Candidate | null>(null)
  const [revokeLoading, setRevokeLoading] = useState(false)

  const [uploadingId, setUploadingId] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [cands, jobList] = await Promise.all([api.getCandidates(), api.getJobs()])
      setCandidates(cands)
      setJobs(jobList)
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

  return (
    <div className="min-h-screen bg-bg-custom p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Candidates</h1>
            <p className="text-sm text-slate-500">Manage interview candidates</p>
          </div>
          <Button onClick={() => setInviteOpen(true)}>Invite Candidate</Button>
        </div>

        <Card className="bg-white">
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center p-12">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                <span className="ml-2 text-sm text-slate-500">Loading candidates...</span>
              </div>
            ) : error ? (
              <div className="p-12 text-center">
                <p className="text-sm text-red-500">{error}</p>
                <Button variant="outline" className="mt-4" onClick={fetchData}>Retry</Button>
              </div>
            ) : candidates.length === 0 ? (
              <div className="p-12 text-center">
                <p className="text-sm text-slate-500">No candidates yet. Invite one to get started.</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Job</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Invite Code</TableHead>
                    <TableHead>Match Score</TableHead>
                    <TableHead>Skills</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {candidates.map((c) => (
                    <CandidateRow
                      key={c.candidate_id}
                      candidate={c}
                      jobTitle={getJobTitle(c.job_id)}
                      uploadingId={uploadingId}
                      onCopyCode={handleCopyCode}
                      onResend={handleResend}
                      onFileSelect={handleFileSelect}
                      onRevoke={setRevokeTarget}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Resume Detail Cards */}
        {!loading && candidates.some((c) => c.resume_path) && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-slate-900">Resume Matches</h2>
            {candidates.filter((c) => c.resume_path).map((c) => (
              <Card key={c.candidate_id} className="bg-white">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">{c.name}</CardTitle>
                  <CardDescription>{getJobTitle(c.job_id)}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {c.matched_skills.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-slate-500">Matched Skills</p>
                      <div className="flex flex-wrap gap-1.5">
                        {c.matched_skills.map((skill) => (
                          <Badge key={skill} className="bg-green-100 text-green-700 border-green-200">
                            {skill}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {c.missing_skills.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-slate-500">Missing Skills</p>
                      <div className="flex flex-wrap gap-1.5">
                        {c.missing_skills.map((skill) => (
                          <Badge key={skill} variant="outline" className="border-red-200 text-red-600">
                            {skill}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {c.match_score != null && (
                    <div>
                      <div className="mb-1 flex items-center justify-between">
                        <p className="text-xs font-medium text-slate-500">Match Score</p>
                        <span className="text-xs font-semibold text-slate-700">
                          {Math.round(c.match_score * 100)}%
                        </span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${Math.round(c.match_score * 100)}%` }}
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

      {/* Invite Dialog */}
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
                  <p className="text-xs text-slate-400">PDF, DOCX, or TXT — drives JD-match scoring</p>
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

      {/* Revoke Confirmation Dialog */}
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
}

function CandidateRow({
  candidate: c,
  jobTitle,
  uploadingId,
  onCopyCode,
  onResend,
  onFileSelect,
  onRevoke,
}: CandidateRowProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const isUploading = uploadingId === c.candidate_id
  const status = statusConfig[c.status] ?? { label: c.status, className: "bg-gray-100 text-gray-600" }

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
      <TableCell className="text-slate-500">{c.email}</TableCell>
      <TableCell>{jobTitle}</TableCell>
      <TableCell>
        <Badge variant="outline" className={status.className}>{status.label}</Badge>
      </TableCell>
      <TableCell>
        <code className="rounded bg-slate-100 px-2 py-0.5 text-xs font-mono text-slate-700">
          {c.invite_code}
        </code>
      </TableCell>
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
      <TableCell>
        <div className="flex items-center justify-end gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            title="Copy invite code"
            onClick={() => onCopyCode(c.invite_code)}
          >
            <Copy className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            title="Resend invite"
            onClick={() => onResend(c)}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            accept=".pdf,.docx,.txt"
            onChange={handleFileChange}
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            title="Attach resume"
            disabled={isUploading}
            onClick={() => fileInputRef.current?.click()}
          >
            {isUploading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-red-500 hover:text-red-600"
            title="Revoke candidate"
            onClick={() => onRevoke(c)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}
