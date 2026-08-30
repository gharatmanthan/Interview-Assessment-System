"use client"

import { useEffect, useState, useCallback } from "react"
import { toast } from "sonner"
import { api, mediaUrl } from "@/lib/api"
import type { ApplicationDetail, JobPosting, JobPipelineStat } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Loader2, FileSearch, ExternalLink, RefreshCw } from "lucide-react"
import { EmptyState } from "@/components/empty-state"

const statusConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" }> = {
  received: { label: "Received", variant: "outline" },
  screening: { label: "Screening", variant: "secondary" },
  passed: { label: "Passed", variant: "success" },
  rejected: { label: "Rejected", variant: "destructive" },
  manual_review: { label: "Manual Review", variant: "warning" },
  candidate_created: { label: "Candidate Created", variant: "success" },
  invite_pending: { label: "Invite Pending", variant: "secondary" },
  invite_sent: { label: "Invite Sent", variant: "default" },
}

const decisionConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" }> = {
  passed: { label: "Passed", variant: "success" },
  manual_review: { label: "Manual Review", variant: "warning" },
  rejected: { label: "Rejected", variant: "destructive" },
}

interface StatCardProps { label: string; value: number; tone?: "default" | "success" | "warning" | "destructive" }

function StatCard({ label, value, tone = "default" }: StatCardProps) {
  const color =
    tone === "success" ? "text-emerald-600" :
    tone === "warning" ? "text-amber-600" :
    tone === "destructive" ? "text-red-600" : "text-foreground"
  return (
    <div className="rounded-lg border bg-card px-3 py-2">
      <div className={`text-xl font-bold ${color}`}>{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  )
}

export default function ApplicationsPage() {
  const [applications, setApplications] = useState<ApplicationDetail[]>([])
  const [jobs, setJobs] = useState<JobPosting[]>([])
  const [pipeline, setPipeline] = useState<JobPipelineStat[]>([])
  const [jobFilter, setJobFilter] = useState<string>("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [res, jobList, stats] = await Promise.all([api.getApplications(), api.getJobs(), api.getApplicationStats()])
      setApplications(res.applications)
      setJobs(jobList)
      setPipeline(stats.jobs)
    } catch (err: any) {
      setError(err.message || "Failed to load data")
      toast.error("Failed to load applications")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  async function openResume(relPath: string) {
    try {
      window.open(await mediaUrl(relPath), "_blank", "noopener,noreferrer")
    } catch (err: any) {
      toast.error(err.message || "Failed to open resume")
    }
  }

  async function rescreen(app: ApplicationDetail) {
    if (!window.confirm(`Re-screen ${app.full_name} against the current job settings? The previous screening result will be replaced by a fresh decision.`)) return
    try {
      await api.rescreenApplication(app.application_id)
      toast.success("Screening re-queued")
      await fetchData()
    } catch (err: any) {
      toast.error(err.message || "Failed to requeue screening")
    }
  }

  function getJobTitle(jobId: string): string {
    return jobs.find((j) => j.job_id === jobId)?.title ?? jobId
  }

  // Default sort: ATS score descending, unscored rows last.
  const visible = [...(jobFilter === "all" ? applications : applications.filter((a) => a.job_id === jobFilter))]
    .sort((a, b) => (b.screening_result?.ats_score ?? -1) - (a.screening_result?.ats_score ?? -1))

  const stats: JobPipelineStat | undefined =
    jobFilter === "all"
      ? {
          job_id: "all",
          title: "All jobs",
          applications: pipeline.reduce((s, j) => s + j.applications, 0),
          screening_pending: pipeline.reduce((s, j) => s + j.screening_pending, 0),
          shortlisted: pipeline.reduce((s, j) => s + j.shortlisted, 0),
          rejected: pipeline.reduce((s, j) => s + j.rejected, 0),
          manual_review: pipeline.reduce((s, j) => s + j.manual_review, 0),
          invites_sent: pipeline.reduce((s, j) => s + j.invites_sent, 0),
          interviews_completed: pipeline.reduce((s, j) => s + j.interviews_completed, 0),
          email_failures: pipeline.reduce((s, j) => s + j.email_failures, 0),
        }
      : pipeline.find((j) => j.job_id === jobFilter)

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Applications</h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Candidate applications, async screening decisions, and delivery status
            </p>
          </div>
          <Select value={jobFilter} onValueChange={setJobFilter}>
            <SelectTrigger className="w-56">
              <SelectValue placeholder="All jobs" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All jobs</SelectItem>
              {jobs.map((job) => (
                <SelectItem key={job.job_id} value={job.job_id}>{job.title}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid grid-cols-8 gap-2">
          <StatCard label="Applications" value={stats?.applications ?? 0} />
          <StatCard label="Pending screening" value={stats?.screening_pending ?? 0} tone="warning" />
          <StatCard label="Shortlisted" value={stats?.shortlisted ?? 0} tone="success" />
          <StatCard label="Rejected" value={stats?.rejected ?? 0} tone="destructive" />
          <StatCard label="Manual review" value={stats?.manual_review ?? 0} tone="warning" />
          <StatCard label="Invites sent" value={stats?.invites_sent ?? 0} />
          <StatCard label="Completed" value={stats?.interviews_completed ?? 0} tone="success" />
          <StatCard label="Email failures" value={stats?.email_failures ?? 0} tone="destructive" />
        </div>

        <Card>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center p-12">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                <span className="ml-2 text-sm text-muted-foreground">Loading applications...</span>
              </div>
            ) : error ? (
              <div className="p-12 text-center">
                <p className="text-sm text-destructive">{error}</p>
                <Button variant="outline" className="mt-4" onClick={fetchData}>Retry</Button>
              </div>
            ) : visible.length === 0 ? (
              <EmptyState
                icon={FileSearch}
                title="No applications"
                description="Applications submitted through the public apply portal will appear here."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Applicant</TableHead>
                    <TableHead>Job</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Screening</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead>Key Signals</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visible.map((app) => {
                    const status = statusConfig[app.status] ?? { label: app.status, variant: "outline" as const }
                    const decision = app.screening_result
                      ? (decisionConfig[app.screening_result.decision] ?? { label: app.screening_result.decision, variant: "outline" as const })
                      : null
                    const score = app.screening_result?.ats_score
                    return (
                      <TableRow key={app.application_id}>
                        <TableCell>
                          <div className="font-medium text-foreground">{app.full_name}</div>
                          <div className="text-xs text-muted-foreground">{app.email}{app.phone ? ` · ${app.phone}` : ""}</div>
                        </TableCell>
                        <TableCell className="text-muted-foreground">{getJobTitle(app.job_id)}</TableCell>
                        <TableCell><Badge variant={status.variant}>{status.label}</Badge></TableCell>
                        <TableCell>
                          {decision ? <Badge variant={decision.variant}>{decision.label}</Badge> : <span className="text-muted-foreground">—</span>}
                        </TableCell>
                        <TableCell>
                          {score != null ? (
                            <Badge variant={score >= 70 ? "success" : score >= 40 ? "warning" : "destructive"}>
                              {Math.round(score)}%
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1 max-w-[240px]">
                            {app.screening_result?.matched_skills.slice(0, 3).map((s) => (
                              <Badge key={s} variant="success" className="text-[10px]">{s}</Badge>
                            ))}
                            {app.screening_result?.hard_requirement_failures.slice(0, 2).map((s) => (
                              <Badge key={s} variant="destructive" className="text-[10px]">{s}</Badge>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center justify-end gap-1">
                            {app.resume_path && (
                              <Button variant="ghost" size="sm" className="h-8" title="Open resume" onClick={() => openResume(app.resume_path)}>
                                <ExternalLink className="h-4 w-4 mr-1.5" /> Resume
                              </Button>
                            )}
                            {app.screening_result && app.screening_status === "completed" && (
                              <Button variant="ghost" size="sm" className="h-8" title="Re-run screening against current job settings" onClick={() => rescreen(app)}>
                                <RefreshCw className="h-4 w-4 mr-1.5" /> Re-screen
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}