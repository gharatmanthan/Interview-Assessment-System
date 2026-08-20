"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { api } from "@/lib/api"
import type { DashboardStats, JobPosting } from "@/lib/types"
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
} from "lucide-react"

export default function DashboardPage() {
  const router = useRouter()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [jobs, setJobs] = useState<JobPosting[]>([])
  const [loading, setLoading] = useState(true)
  const [username, setUsername] = useState<string | null>(null)

  useEffect(() => {
    setUsername(localStorage.getItem("username"))
  }, [])

  useEffect(() => {
    async function load() {
      try {
        const [s, j] = await Promise.all([api.getDashboardStats(), api.getJobs()])
        setStats(s)
        setJobs(j)
      } catch (err) {
        console.error("Failed to load dashboard:", err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-slate-400 text-sm">Loading dashboard...</p>
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
      iconBg: "bg-blue-100",
      iconColor: "text-blue-600",
      alert: false,
    },
    {
      label: "Avg Score",
      value: (stats?.avg_explainability_score ?? 0).toFixed(1),
      icon: TrendingUp,
      iconBg: "bg-emerald-100",
      iconColor: "text-emerald-600",
      alert: false,
    },
    {
      label: "Bias Flags",
      value: stats?.bias_flags_raised ?? 0,
      icon: Shield,
      iconBg: "bg-amber-100",
      iconColor: "text-amber-600",
      alert: (stats?.bias_flags_raised ?? 0) > 0,
    },
    {
      label: "Integrity Flags",
      value: stats?.integrity_flags ?? 0,
      icon: AlertTriangle,
      iconBg: "bg-red-100",
      iconColor: "text-red-600",
      alert: (stats?.integrity_flags ?? 0) > 0,
    },
    {
      label: "Candidates",
      value: totalCandidates,
      icon: Users,
      iconBg: "bg-purple-100",
      iconColor: "text-purple-600",
      alert: false,
    },
  ]

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">
          Welcome back{username ? `, ${username}` : ""}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {statCards.map((card) => (
          <Card key={card.label} className="rounded-xl border bg-white p-6">
            <CardContent className="p-0 flex flex-col gap-3">
              <div className={`flex h-10 w-10 items-center justify-center rounded-full ${card.iconBg}`}>
                <card.icon className={`h-5 w-5 ${card.iconColor}`} />
              </div>
              <div>
                <p className={`text-2xl font-bold ${card.alert ? card.iconColor : "text-slate-900"}`}>
                  {card.value}
                </p>
                <p className="text-sm text-slate-500">{card.label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {stats && Object.keys(stats.candidates_by_status).length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Candidate Status</h2>
          <div className="grid grid-cols-3 gap-4">
            {[
              { key: "invited", label: "Invited", color: "text-blue-600" },
              { key: "in_progress", label: "In Progress", color: "text-amber-600" },
              { key: "completed", label: "Completed", color: "text-green-600" },
            ].map(({ key, label, color }) => (
              <Card key={key} className="rounded-xl border bg-white p-4">
                <CardContent className="p-0">
                  <p className="text-sm text-slate-500">{label}</p>
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
    </div>
  )
}
