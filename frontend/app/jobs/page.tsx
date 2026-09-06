"use client"

import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { JobPosting, PollLogEntry, LinkedInPreview } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Slider } from "@/components/ui/slider"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog"
import { Pencil, Trash2, Plus, Briefcase, Mail, Loader2, History, Info, Link, Check, Linkedin, ExternalLink, RefreshCw, Share2 } from "lucide-react"
import { SkillTagInput } from "@/components/skill-tag-input"
import { EmptyState } from "@/components/empty-state"
import InterviewStrategyDialog from "@/components/interview-strategy-dialog"

const COMPETENCY_KEYS = [
  "dsa",
  "system_design",
  "communication",
  "domain_knowledge",
  "problem_solving",
] as const

const COMPETENCY_LABELS: Record<string, string> = {
  dsa: "DSA",
  system_design: "System Design",
  communication: "Communication",
  domain_knowledge: "Domain Knowledge",
  problem_solving: "Problem Solving",
}

const EXPERIENCE_LEVELS = ["Fresher", "Junior", "Mid", "Senior"]
const DEPARTMENTS = ["Software/CS", "Data/ML", "Electronics", "Mechanical", "Civil", "Other"]

const EMPTY_WEIGHTS: Record<string, number> = {
  dsa: 20,
  system_design: 20,
  communication: 20,
  domain_knowledge: 20,
  problem_solving: 20,
}

const MAX_LINKEDIN_CHARS = 3000

function emptyForm(): Omit<JobPosting, "job_id"> {
  return {
    title: "",
    description: "",
    required_skills: [],
    experience_level: "Mid",
    department: "",
    num_rounds: 5,
    time_limit_seconds: 300,
    adaptive_difficulty: true,
    competency_weights: { ...EMPTY_WEIGHTS },
    screening_threshold: 60,
    application_gmail_label: "",
  }
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobPosting[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(emptyForm())
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<JobPosting | null>(null)
  const [gmailConnected, setGmailConnected] = useState(false)
  const [checkingJob, setCheckingJob] = useState<string | null>(null)
  const [pollLogs, setPollLogs] = useState<PollLogEntry[]>([])
  const [showPollLogs, setShowPollLogs] = useState(false)
  const [backendMode, setBackendMode] = useState<string>("local")
  const [copiedJobId, setCopiedJobId] = useState<string | null>(null)
  const [linkedinConnected, setLinkedinConnected] = useState(false)
  const [linkedinJob, setLinkedinJob] = useState<JobPosting | null>(null)
  const [preview, setPreview] = useState<LinkedInPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [editingContent, setEditingContent] = useState("")
  const [strategyTarget, setStrategyTarget] = useState<JobPosting | null>(null)

  async function fetchJobs() {
    try {
      const data = await api.getJobs()
      setJobs(data)
      setError(null)
    } catch (err: any) {
      setError(err.message || "Failed to load jobs")
      toast.error(err.message || "Failed to load jobs")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchJobs()
    api.getGmailStatus().then((s) => setGmailConnected(s.connected)).catch(() => {})
    api.getSettings().then((s) => setBackendMode((s as any).backend_mode || "local")).catch(() => {})
    api.getPollLogs().then((r) => setPollLogs(r.logs)).catch(() => {})
    api.getLinkedinStatus().then((s) => setLinkedinConnected(s.connected)).catch(() => {})
  }, [])

  const weightSum = Object.values(form.competency_weights).reduce((a, b) => a + b, 0)
  const weightsValid = weightSum === 100

  function openCreate() {
    setForm(emptyForm())
    setEditing(false)
    setEditingId(null)
    setShowForm(true)
  }

  function openEdit(job: JobPosting) {
    setForm({
      title: job.title,
      description: job.description,
      required_skills: [...job.required_skills],
      experience_level: job.experience_level,
      department: job.department,
      num_rounds: job.num_rounds,
      time_limit_seconds: job.time_limit_seconds,
      adaptive_difficulty: job.adaptive_difficulty,
      competency_weights: { ...job.competency_weights },
      screening_threshold: job.screening_threshold,
      application_gmail_label: job.application_gmail_label,
    })
    setEditing(true)
    setEditingId(job.job_id)
    setShowForm(true)
  }

  function cancelForm() {
    setShowForm(false)
    setEditing(false)
    setEditingId(null)
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!weightsValid) {
      toast.error("Competency weights must sum to 100")
      return
    }
    try {
      if (editing && editingId) {
        await api.updateJob(editingId, { job_id: editingId, ...form } as JobPosting)
        toast.success("Job posting updated")
      } else {
        await api.createJob(form)
        toast.success("Job posting created")
      }
      cancelForm()
      await fetchJobs()
    } catch (err: any) {
      toast.error(err.message || "Failed to save")
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await api.deleteJob(deleteTarget.job_id)
      toast.success("Job posting deleted")
      setDeleteTarget(null)
      await fetchJobs()
    } catch (err: any) {
      toast.error(err.message || "Failed to delete")
    }
  }

  async function handleCheckApplications(jobId: string, jobTitle: string) {
    if (!gmailConnected) {
      toast.error("Gmail not connected. Go to Settings → Email Integration to connect.")
      return
    }
    setCheckingJob(jobId)
    try {
      const result = await api.checkEmailApplications(jobId)
      toast.success(result.summary || `Checked applications for ${jobTitle}`)
      api.getPollLogs().then((r) => setPollLogs(r.logs)).catch(() => {})
    } catch (err: any) {
      toast.error(err.message || "Failed to check applications")
    } finally {
      setCheckingJob(null)
    }
  }

  async function handleCopyApplicationLink(jobId: string) {
    if (!jobId || jobId.trim() === "") {
      toast.error("Unable to create application link: job ID is missing.")
      return
    }
    // Public application origin: NEXT_PUBLIC_APP_URL is the source of truth in
    // production. Fall back to the current window origin only in development so
    // a copied link is never incorrectly built from a machine-local origin that
    // external candidates cannot reach.
    const appBase = process.env.NEXT_PUBLIC_APP_URL?.replace(/\/+$/, "") || window.location.origin
    const url = `${appBase}/apply?jobId=${encodeURIComponent(jobId)}`
    await navigator.clipboard.writeText(url)
    setCopiedJobId(jobId)
    toast.success("Application link copied to clipboard")
    setTimeout(() => setCopiedJobId(null), 2000)
  }

  async function openLinkedin(job: JobPosting) {
    if (job.linkedin_post_status === "PUBLISHED" && job.linkedin_post_url) {
      window.open(job.linkedin_post_url, "_blank", "noopener,noreferrer")
      return
    }
    if (job.linkedin_post_status === "PUBLISHING") {
      toast.info("A LinkedIn post is already being published for this job.")
      return
    }
    setLinkedinJob(job)
    setPreview(null)
    setEditingContent("")
    setPreviewLoading(true)
    try {
      const p = await api.getLinkedinPreview(job.job_id)
      setPreview(p)
      setEditingContent(p.content)
      setLinkedinConnected(p.connected)
    } catch (err: any) {
      toast.error(err.message || "Failed to prepare the post")
    } finally {
      setPreviewLoading(false)
    }
  }

  async function handlePublish() {
    if (!linkedinJob || !preview) return
    const content = editingContent.trim()
    if (!content) {
      toast.error("Post content must not be empty")
      return
    }
    if (content.length > MAX_LINKEDIN_CHARS) {
      toast.error(`Post content must be at most ${MAX_LINKEDIN_CHARS} characters`)
      return
    }
    setPublishing(true)
    try {
      const res = await api.publishLinkedinPost(linkedinJob.job_id, content)
      toast.success("Posted to LinkedIn")
      await fetchJobs()
      setLinkedinJob(null)
      setPreview(null)
      if (res.post_url) window.open(res.post_url, "_blank", "noopener,noreferrer")
    } catch (err: any) {
      const msg = err?.message || "Failed to post"
      toast.error(msg)
      if (/verify/i.test(msg)) {
        toast.info("Check LinkedIn to confirm the post, then retry if it is missing.")
      }
      await fetchJobs()
    } finally {
      setPublishing(false)
    }
  }

  function interviewStrategyBadge(job: JobPosting) {
    const confirmed = job.strategy_confirmed
    const strategy = job.interview_strategy || job.recommended_strategy
    const label =
      strategy === "MODE_1_ONLY" ? "Mode 1 Only"
      : strategy === "MODE_2_THEN_MODE_1" ? "Mode 2 → Mode 1"
      : "Automatic"
    return (
      <button
        type="button"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground hover:underline"
        onClick={() => setStrategyTarget(job)}
        title="Configure interview strategy"
      >
        <Share2 className="h-3.5 w-3.5" />
        <span>{confirmed ? label : strategy ? `Rec: ${label}` : "Set strategy"}</span>
        {confirmed && <Check className="h-3 w-3 text-success-text" />}
      </button>
    )
  }

  function linkedinStatusBadge(job: JobPosting) {
    const status = job.linkedin_post_status || "NOT_POSTED"
    if (status === "PUBLISHED") {
      return (
        <a
          className="inline-flex items-center gap-1 text-xs font-medium text-success-text hover:underline"
          href={job.linkedin_post_url || undefined}
          target="_blank"
          rel="noopener noreferrer"
        >
          <Check className="h-3.5 w-3.5" /> Posted
        </a>
      )
    }
    if (status === "PUBLISHING") {
      return (
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Publishing
        </span>
      )
    }
    if (status === "FAILED") {
      return (
        <span
          className="inline-flex items-center gap-1 text-xs font-medium text-destructive"
          title={job.linkedin_last_error || "LinkedIn rejected the post"}
        >
          <RefreshCw className="h-3.5 w-3.5" /> Failed
        </span>
      )
    }
    return <span className="text-xs text-muted-foreground">—</span>
  }

  function updateWeight(key: string, value: number) {
    setForm((prev) => ({
      ...prev,
      competency_weights: { ...prev.competency_weights, [key]: value },
    }))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-muted-foreground text-sm">Loading jobs...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <p className="text-sm text-destructive">{error}</p>
        <Button variant="outline" onClick={fetchJobs}>Retry</Button>
      </div>
    )
  }

  return (
    <div className="space-y-6 px-8 py-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Job Postings</h1>
        <p className="text-sm leading-relaxed text-muted-foreground mt-1">
          Manage interview job postings and competency weightings
        </p>
      </div>

      {showForm && (
        <Card className="rounded-xl">
          <CardHeader>
            <CardTitle className="text-lg">
              {editing ? "Edit Job Posting" : "Create Job Posting"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSave} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="title">Title</Label>
                  <Input id="title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Senior Backend Engineer" />
                </div>
                <div className="space-y-2">
                  <Label>Department</Label>
                  <Select value={form.department} onValueChange={(val) => setForm({ ...form, department: val })}>
                    <SelectTrigger><SelectValue placeholder="Select department" /></SelectTrigger>
                    <SelectContent>
                      {DEPARTMENTS.map((dept) => (<SelectItem key={dept} value={dept}>{dept}</SelectItem>))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="description">Description</Label>
                  <textarea
                    id="description" required rows={8} value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    placeholder="Job description..."
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label>Required Skills</Label>
                  <SkillTagInput value={form.required_skills} onChange={(skills) => setForm({ ...form, required_skills: skills })} placeholder="Type a skill and press Enter..." />
                  <p className="text-xs text-muted-foreground">Press Enter or comma to add a skill</p>
                </div>
                <div className="space-y-2">
                  <Label>Experience Level</Label>
                  <Select value={form.experience_level} onValueChange={(val) => setForm({ ...form, experience_level: val })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {EXPERIENCE_LEVELS.map((level) => (<SelectItem key={level} value={level}>{level}</SelectItem>))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rounds">Number of Rounds</Label>
                  <Input id="rounds" type="number" min={1} max={5} required value={form.num_rounds}
                    onChange={(e) => { const val = parseInt(e.target.value) || 1; setForm({ ...form, num_rounds: Math.min(5, Math.max(1, val)) }) }} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="timeLimit">Time Limit per Question (seconds)</Label>
                  <Input id="timeLimit" type="number" min={30} max={600} required value={form.time_limit_seconds}
                    onChange={(e) => { const val = parseInt(e.target.value) || 300; setForm({ ...form, time_limit_seconds: Math.min(600, Math.max(30, val)) }) }} />
                </div>
                <div className="space-y-2 flex items-center gap-3 pt-6">
                  <Switch checked={form.adaptive_difficulty} onCheckedChange={(val) => setForm({ ...form, adaptive_difficulty: val })} />
                  <Label className="cursor-pointer">Adaptive Difficulty</Label>
                </div>
                <p className="ml-12 text-xs text-muted-foreground">
                  Question difficulty increases if the candidate answers well, decreases if they struggle.
                </p>
                <div className="space-y-2">
                  <Label htmlFor="threshold">Screening Threshold (0-100)</Label>
                  <Input id="threshold" type="number" min={0} max={100} value={form.screening_threshold}
                    onChange={(e) => { const val = parseFloat(e.target.value) || 0; setForm({ ...form, screening_threshold: Math.min(100, Math.max(0, val)) }) }} />
                  <p className="text-xs text-muted-foreground">
                    Email applicants scoring below this threshold are recorded but not invited.
                  </p>
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="gmail-label">Gmail Application Label</Label>
                  <Input id="gmail-label" value={form.application_gmail_label} onChange={(e) => setForm({ ...form, application_gmail_label: e.target.value })} placeholder="e.g. Applications/Senior-Backend" />
                  <p className="text-xs text-muted-foreground">
                    Gmail label to watch for incoming applications. Leave empty to disable email intake for this job.
                  </p>
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label className="text-base font-semibold">Competency Weight Sliders</Label>
                  <span className={`text-sm font-medium ${weightsValid ? "text-success-text" : "text-destructive-text"}`}>
                    Total: {weightSum}%
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
                  {COMPETENCY_KEYS.map((key) => (
                    <div key={key} className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label className="text-sm">{COMPETENCY_LABELS[key]}</Label>
                        <span className="text-sm font-medium text-foreground">{form.competency_weights[key] ?? 0}%</span>
                      </div>
                      <Slider min={0} max={100} step={5} value={[form.competency_weights[key] ?? 0]} onValueChange={(val) => updateWeight(key, val[0])} />
                    </div>
                  ))}
                </div>
                {!weightsValid && (
                  <p className="text-xs text-destructive">
                    Competency weights must sum to 100%. Currently at {weightSum}%.
                  </p>
                )}
              </div>

              <div className="flex gap-3 pt-2">
                <Button type="submit" disabled={!weightsValid}>Save Job Posting</Button>
                <Button type="button" variant="outline" onClick={cancelForm}>Cancel</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card className="rounded-xl">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Job Postings</CardTitle>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4 mr-1.5" /> Add Job Posting
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {jobs.length === 0 ? (
            <EmptyState icon={Briefcase} title="No job postings" description="Create your first job posting to start inviting candidates." action={{ label: "Create Job Posting", onClick: openCreate }} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Department</TableHead>
                  <TableHead>Experience Level</TableHead>
                  <TableHead>Skills</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Interview Strategy</TableHead>
                  <TableHead>LinkedIn</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.job_id}>
                    <TableCell className="font-medium">{job.title}</TableCell>
                    <TableCell>{job.department}</TableCell>
                    <TableCell>{job.experience_level}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {job.required_skills.slice(0, 3).map((skill) => (<Badge key={skill} variant="secondary" className="text-xs">{skill}</Badge>))}
                        {job.required_skills.length > 3 && (<Badge variant="outline" className="text-xs">+{job.required_skills.length - 3}</Badge>)}
                      </div>
                    </TableCell>
                    <TableCell>{job.created_at ? new Date(job.created_at).toLocaleDateString() : "—"}</TableCell>
                    <TableCell>{interviewStrategyBadge(job)}</TableCell>
                    <TableCell>{linkedinStatusBadge(job)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title={
                            job.linkedin_post_status === "PUBLISHED"
                              ? "Open LinkedIn post"
                              : "Post this job on LinkedIn"
                          }
                          onClick={() => openLinkedin(job)}
                        >
                          {previewLoading && linkedinJob?.job_id === job.job_id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Linkedin className="h-4 w-4" />
                          )}
                        </Button>
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
                        {job.application_gmail_label && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            title={gmailConnected ? "Check for new applications" : "Gmail not connected — go to Settings"}
                            disabled={checkingJob === job.job_id}
                            onClick={() => handleCheckApplications(job.job_id, job.title)}
                          >
                            {checkingJob === job.job_id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Mail className="h-4 w-4" />
                            )}
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(job)}><Pencil className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10" onClick={() => setDeleteTarget(job)}><Trash2 className="h-4 w-4" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {backendMode === "local" && (
        <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
          <Info className="h-4 w-4 mt-0.5 shrink-0" />
          <p>
            Auto-check runs every 10 min when connected to a remote server. In local mode, use the <Mail className="inline h-3 w-3" /> button above to check manually.
          </p>
        </div>
      )}

      {pollLogs.length > 0 && (
        <Card className="rounded-xl">
          <CardHeader className="flex flex-row items-center justify-between cursor-pointer" onClick={() => setShowPollLogs(!showPollLogs)}>
            <CardTitle className="text-lg flex items-center gap-2">
              <History className="h-4 w-4" /> Recent Application Checks
            </CardTitle>
            <span className="text-xs text-muted-foreground">{showPollLogs ? "Collapse" : "Expand"}</span>
          </CardHeader>
          {showPollLogs && (
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>Job</TableHead>
                    <TableHead>Mode</TableHead>
                    <TableHead className="text-right">Checked</TableHead>
                    <TableHead className="text-right">Invited</TableHead>
                    <TableHead className="text-right">Below</TableHead>
                    <TableHead className="text-right">Skipped</TableHead>
                    <TableHead className="text-right">Failed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pollLogs.map((log) => (
                    <TableRow key={log.id}>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(log.run_at).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-sm">{log.job_title}</TableCell>
                      <TableCell>
                        <Badge variant={log.mode === "auto" ? "default" : "secondary"} className="text-xs">
                          {log.mode}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right text-sm">{log.total_checked}</TableCell>
                      <TableCell className="text-right text-sm text-success-text">{log.invited}</TableCell>
                      <TableCell className="text-right text-sm text-warning-text">{log.below_threshold}</TableCell>
                      <TableCell className="text-right text-sm text-muted-foreground">{log.skipped}</TableCell>
                      <TableCell className="text-right text-sm text-destructive-text">{log.failed}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          )}
        </Card>
      )}

      <Dialog open={!!deleteTarget} onOpenChange={(open) => { if (!open) setDeleteTarget(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Job Posting</DialogTitle>
            <DialogDescription>Are you sure you want to delete &quot;{deleteTarget?.title}&quot;? This action cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!linkedinJob} onOpenChange={(open) => { if (!open) { setLinkedinJob(null); setPreview(null) } }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Linkedin className="h-5 w-5" /> Post on LinkedIn
              {linkedinJob && linkedinJob.linkedin_post_status === "FAILED" && (
                <Badge variant="destructive" className="text-xs">Retry after failure</Badge>
              )}
            </DialogTitle>
            <DialogDescription>
              Review and edit the draft before publishing to your LinkedIn feed.
            </DialogDescription>
          </DialogHeader>

          {previewLoading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !preview ? null : (
            <div className="space-y-4">
              <textarea
                value={editingContent}
                onChange={(e) => setEditingContent(e.target.value)}
                rows={12}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
              <div className={`text-xs ${editingContent.length > MAX_LINKEDIN_CHARS ? "text-destructive" : "text-muted-foreground"}`}>
                {editingContent.length}/{MAX_LINKEDIN_CHARS} characters
              </div>
              <div className="flex items-center justify-between rounded-md border border-border bg-muted/50 px-3 py-2">
                <span className="text-xs text-muted-foreground">Public application link</span>
                <a className="text-xs font-medium text-primary hover:underline" href={preview.public_url} target="_blank" rel="noopener noreferrer">
                  {preview.public_url}
                </a>
              </div>
            </div>
          )}

          <DialogFooter className="items-center">
            {!preview && !previewLoading ? null : (
              <div className="flex w-full items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  {!linkedinConnected ? (
                    <span className="text-xs text-muted-foreground">
                      No LinkedIn account connected.{" "}
                      <a className="font-medium text-primary underline" href="/settings">
                        Connect in Settings
                      </a>
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Check className="h-3.5 w-3.5 text-success-text" /> Will post as your LinkedIn profile
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" onClick={() => { setLinkedinJob(null); setPreview(null) }}>
                    Cancel
                  </Button>
                  <Button
                    onClick={handlePublish}
                    disabled={!linkedinConnected || publishing || !editingContent.trim() || editingContent.length > MAX_LINKEDIN_CHARS}
                  >
                    {publishing ? <><Loader2 className="h-4 w-4 animate-spin mr-1.5" /> Publishing</> : (
                      <><ExternalLink className="h-4 w-4 mr-1.5" /> Publish to LinkedIn</>
                    )}
                  </Button>
                </div>
              </div>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <InterviewStrategyDialog
        jobId={strategyTarget?.job_id ?? ""}
        jobTitle={strategyTarget?.title ?? ""}
        open={!!strategyTarget}
        onOpenChange={(open) => { if (!open) setStrategyTarget(null) }}
        onConfirmed={() => fetchJobs()}
      />
    </div>
  )
}
