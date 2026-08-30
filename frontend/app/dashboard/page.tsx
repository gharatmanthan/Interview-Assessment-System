"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { api } from "@/lib/api"
import type { DashboardStats, JobPosting, JobPipelineStat } from "@/lib/types"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Video,
  TrendingUp,
  Shield,
  AlertTriangle,
  Users,
  Briefcase,
  FileText,
  MailWarning,
} from "lucide-react"
import { EmptyState } from "@/components/empty-state"

export default function DashboardPage() {
  const router = useRouter()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [pipeline, setPipeline] = useState<JobPipelineStat[]>([])
  const [jobs, setJobs] = useState<JobPosting[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [username, setUsername] = useState<string | null>(null)

  useEffect(() => {
    setUsername(localStorage.getItem("username"))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, p, j] = await Promise.all([api.getDashboardStats(), api.getApplicationStats(), api.getJobs()])
      setStats(s)
      setPipeline(p.jobs ?? [])
      setJobs(j)
    } catch (err: any) {
      setError(err.message || "Failed to load dashboard")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-muted-foreground text-sm">Loading dashboard...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <p className="text-sm text-destructive">{error}</p>
        <Button variant="outline" onClick={load}>Retry</Button>
      </div>
    )
  }

  const pipeTotal =
    pipeline.reduce((s, j) => s + j.applications, 0) +
    pipeline.reduce((s, j) => s + j.interviews_completed, 0)

  const total = stats
    ? (stats.interviews_conducted ?? 0) +
      Object.values(stats.candidates_by_status).reduce((a, b) => a + b, 0)
    : 0

  if (total === 0 && pipeTotal === 0 && !loading) {
    return (
      <div className="mt-12">
        <EmptyState
          icon={Briefcase}
          title="Welcome to InterviewIQ"
          description="Get started by creating your first job posting."
          action={{ label: "Create Job Posting", onClick: () => router.push("/jobs") }}
        />
      </div>
    )
  }

  const totalCandidates = stats
    ? Object.values(stats.candidates_by_status).reduce((a, b) => a + b, 0)
    : 0

  const statCards = [
    {
      label: "Total Interviews",
      value: stats?.interviews_conducted ?? 0,
      icon: Video,
      iconBg: "bg-primary/10",
      iconColor: "text-primary",
      alert: false,
    },
    {
      label: "Avg Score",
      value: (stats?.avg_explainability_score ?? 0).toFixed(1),
      icon: TrendingUp,
      iconBg: "bg-success-bg",
      iconColor: "text-success-text",
      alert: false,
    },
    {
      label: "Bias Flags",
      value: stats?.bias_flags_raised ?? 0,
      icon: Shield,
      iconBg: "bg-warning-bg",
      iconColor: "text-warning-text",
      alert: (stats?.bias_flags_raised ?? 0) > 0,
    },
    {
      label: "Integrity Flags",
      value: stats?.integrity_flags ?? 0,
      icon: AlertTriangle,
      iconBg: "bg-destructive-bg",
      iconColor: "text-destructive-text",
      alert: (stats?.integrity_flags ?? 0) > 0,
    },
    {
      label: "Candidates",
      value: totalCandidates,
      icon: Users,
      iconBg: "bg-muted",
      iconColor: "text-foreground",
      alert: false,
    },
  ]

  return (
    <div className="space-y-8 px-8 py-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-sm leading-relaxed text-muted-foreground mt-1">
          Welcome back{username ? `, ${username}` : ""}
        </p>
      </div>

      <div className="rounded-xl border bg-card p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <FileText className="h-4 w-4 text-primary" /> Screening Pipeline
            </h2>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Applicants by stage across all of your job postings
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => router.push("/applications")}>
            View applications
          </Button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Applications", value: pipeline.reduce((s, j) => s + j.applications, 0), tone: "text-foreground" as const },
            { label: "Shortlisted", value: pipeline.reduce((s, j) => s + j.shortlisted, 0), tone: "text-emerald-600" as const },
            { label: "Invites Sent", value: pipeline.reduce((s, j) => s + j.invites_sent, 0), tone: "text-foreground" as const },
            { label: "Interviews Completed", value: pipeline.reduce((s, j) => s + j.interviews_completed, 0), tone: "text-primary" as const },
          ].map(({ label, value, tone }) => (
            <div key={label} className="rounded-lg border border-border bg-background/50 px-4 py-3">
              <p className={`text-2xl font-bold ${tone}`}>{value}</p>
              <p className="text-[11px] text-muted-foreground">{label}</p>
            </div>
          ))}
        </div>
        {(pipeline.reduce((s, j) => s + j.screening_pending, 0) > 0 ||
          pipeline.reduce((s, j) => s + j.manual_review, 0) > 0 ||
          pipeline.reduce((s, j) => s + j.email_failures, 0) > 0) && (
          <div className="mt-3 flex flex-wrap gap-2">
            {pipeline.reduce((s, j) => s + j.screening_pending, 0) > 0 && (
              <Badge variant="secondary" className="text-xs">Pending screening: {pipeline.reduce((s, j) => s + j.screening_pending, 0)}</Badge>
            )}
            {pipeline.reduce((s, j) => s + j.manual_review, 0) > 0 && (
              <Badge variant="warning" className="text-xs">Manual review: {pipeline.reduce((s, j) => s + j.manual_review, 0)}</Badge>
            )}
            {pipeline.reduce((s, j) => s + j.email_failures, 0) > 0 && (
              <Badge variant="destructive" className="text-xs flex items-center gap-1">
                <MailWarning className="h-3 w-3" /> Email failures: {pipeline.reduce((s, j) => s + j.email_failures, 0)}
              </Badge>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {statCards.map((card) => (
          <Card key={card.label} className="rounded-xl p-6">
            <CardContent className="p-0 flex flex-col gap-3">
              <div className={`flex h-10 w-10 items-center justify-center rounded-full ${card.iconBg}`}>
                <card.icon className={`h-5 w-5 ${card.iconColor}`} />
              </div>
              <div>
                <p className={`text-2xl font-bold ${card.alert ? card.iconColor : "text-foreground"}`}>
                  {card.value}
                </p>
                <p className="text-sm leading-relaxed text-muted-foreground">{card.label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {stats && Object.keys(stats.candidates_by_status).length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-foreground mb-4">Candidate Status</h2>
          <div className="grid grid-cols-3 gap-4">
            {[
              { key: "invited", label: "Invited", color: "text-primary" },
              { key: "in_progress", label: "In Progress", color: "text-warning-text" },
              { key: "completed", label: "Completed", color: "text-success-text" },
            ].map(({ key, label, color }) => (
              <Card key={key} className="rounded-xl p-4">
                <CardContent className="p-0">
                  <p className="text-sm leading-relaxed text-muted-foreground">{label}</p>
                  <p className={`text-2xl font-bold mt-1 ${color}`}>
                    {stats.candidates_by_status[key] ?? 0}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold text-foreground mb-4">Job Postings</h2>
        {jobs.length === 0 ? (
          <Card className="rounded-xl">
            <CardContent className="py-12 text-center">
              <Briefcase className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
              <p className="text-sm leading-relaxed text-muted-foreground">No job postings yet</p>
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
                className="rounded-xl p-5 cursor-pointer transition-colors hover:border-primary/30 hover:bg-primary/5"
                onClick={() => router.push("/jobs")}
              >
                <CardContent className="p-0 space-y-2">
                  <h3 className="font-semibold text-foreground">{job.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{job.department}</p>
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
    </div>
  )
}
