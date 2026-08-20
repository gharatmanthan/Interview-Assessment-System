"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { api } from "@/lib/api"
import { formatDate } from "@/lib/utils"
import type { InterviewSession, CandidateReport, ComparisonRow, JobPosting } from "@/lib/types"
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Separator } from "@/components/ui/separator"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { FileText } from "lucide-react"
import { EmptyState } from "@/components/empty-state"

function scoreColor(score: number): string {
  if (score >= 75) return "text-emerald-600"
  if (score >= 50) return "text-amber-600"
  return "text-red-600"
}

function scoreBarColor(score: number): string {
  if (score >= 75) return "bg-emerald-500"
  if (score >= 50) return "bg-amber-500"
  return "bg-red-500"
}

function statusVariant(s: string): "default" | "secondary" | "destructive" | "outline" {
  if (s === "completed") return "default"
  if (s === "in_progress") return "secondary"
  if (s === "failed") return "destructive"
  return "outline"
}

function medalBadge(rank: number) {
  if (rank === 1) return <Badge className="bg-yellow-400 text-yellow-900 border-yellow-500">Gold</Badge>
  if (rank === 2) return <Badge className="bg-slate-300 text-slate-700 border-slate-400">Silver</Badge>
  if (rank === 3) return <Badge className="bg-amber-600 text-amber-50 border-amber-700">Bronze</Badge>
  return null
}

const BASE_URL = "http://localhost:8000"

export default function ReportsPage() {
  const [sessions, setSessions] = useState<InterviewSession[]>([])
  const [comparison, setComparison] = useState<ComparisonRow[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [report, setReport] = useState<CandidateReport | null>(null)
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [loadingComparison, setLoadingComparison] = useState(true)
  const [loadingReport, setLoadingReport] = useState(false)
  const [sortField, setSortField] = useState<string>("overall_score")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
  const [filterJobId, setFilterJobId] = useState<string>("all")
  const [jobs, setJobs] = useState<JobPosting[]>([])
  const router = useRouter()

  useEffect(() => {
    api.getSessions().then(setSessions).catch(() => {}).finally(() => setLoadingSessions(false))
    api.getComparison().then(setComparison).catch(() => {}).finally(() => setLoadingComparison(false))
    api.getJobs().then(setJobs).catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedId) { setReport(null); return }
    setLoadingReport(true)
    api.getCandidateReport(selectedId).then(setReport).catch(() => setReport(null)).finally(() => setLoadingReport(false))
  }, [selectedId])

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
  const categories = sortedComparison.length > 0
    ? Object.keys(sortedComparison[0].category_scores)
    : []

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900">Reports</h1>
          <p className="mt-1 text-slate-500">Interview results and analytics</p>
        </div>

        <Tabs defaultValue="sessions">
          <TabsList className="mb-6">
            <TabsTrigger value="sessions">Sessions</TabsTrigger>
            <TabsTrigger value="comparison">Comparison</TabsTrigger>
          </TabsList>

          <TabsContent value="sessions">
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
              {/* Session list */}
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle className="text-lg">Sessions</CardTitle>
                </CardHeader>
                <CardContent>
                  {loadingSessions ? (
                    <div className="space-y-3 py-4 text-center text-sm text-slate-400">Loading...</div>
                  ) : sessions.length === 0 ? (
                    <EmptyState
                      icon={FileText}
                      title="No reports yet"
                      description="Reports will appear here once candidates complete their interviews."
                    />
                  ) : (
                    <div className="max-h-[600px] space-y-2 overflow-y-auto pr-1">
                      {sessions.map((s) => (
                        <button
                          key={s.session_id}
                          onClick={() => setSelectedId(s.session_id)}
                          className={`w-full rounded-lg border p-3 text-left transition-colors ${
                            selectedId === s.session_id
                              ? "border-primary bg-primary/5"
                              : "border-slate-200 hover:bg-slate-50"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-slate-900">{s.candidate_name}</span>
                            <Badge variant={statusVariant(s.status)}>{s.status}</Badge>
                          </div>
                          <div className="mt-1 text-xs text-slate-500">{s.job_title}</div>
                          <div className="mt-1 text-xs text-slate-400">{formatDate(s.completed_at || s.started_at)}</div>
                        </button>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Session detail */}
              <Card className="lg:col-span-3">
                <CardContent className="pt-6">
                  {!selectedId ? (
                    <div className="flex h-[400px] items-center justify-center text-sm text-slate-400">
                      Select a session to view details
                    </div>
                  ) : loadingReport ? (
                    <div className="flex h-[400px] items-center justify-center text-sm text-slate-400">Loading report...</div>
                  ) : !report ? (
                    <div className="flex h-[400px] items-center justify-center text-sm text-slate-400">No report data</div>
                  ) : (
                    <div className="space-y-6">
                      <div>
                        <h2 className="text-xl font-bold text-slate-900">{report.session.candidate_name}</h2>
                        <p className="text-sm text-slate-500">{report.session.job_title}</p>
                      </div>

                      <div className="flex items-center gap-4">
                        <div className={`text-5xl font-extrabold ${scoreColor(report.overall_score)}`}>
                          {report.overall_score}
                        </div>
                        <div>
                          <div className="text-sm font-medium text-slate-700">Overall Score</div>
                          <div className="text-xs text-slate-400">out of 100</div>
                        </div>
                      </div>

                      <Separator />

                      {/* Competency Breakdown */}
                      <div>
                        <h3 className="mb-3 text-lg font-semibold text-slate-900">Competency Breakdown</h3>
                        <div className="space-y-4">
                          {report.scores.map((score) => {
                            const explanation = report.explanations.find((e) => e.question_id === score.question_id)
                            return (
                              <div key={score.question_id} className="rounded-lg border border-slate-100 p-3">
                                <div className="flex items-center justify-between">
                                  <span className="text-sm font-medium text-slate-800">{score.category}</span>
                                  <span className="text-xs text-slate-500">{score.confidence}% confidence</span>
                                </div>
                                <div className="mt-2 flex items-center gap-3">
                                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                                    <div
                                      className={`h-full rounded-full transition-all ${scoreBarColor(score.score)}`}
                                      style={{ width: `${score.score}%` }}
                                    />
                                  </div>
                                  <span className={`text-sm font-bold ${scoreColor(score.score)}`}>{score.score}</span>
                                </div>
                                {explanation && (
                                  <div className="mt-2">
                                    <p className="text-xs italic text-slate-500">{explanation.summary}</p>
                                    {explanation.supporting_phrases.length > 0 && (
                                      <div className="mt-2 flex flex-wrap gap-1">
                                        {explanation.supporting_phrases.map((phrase, i) => (
                                          <Badge key={i} variant="secondary" className="text-[10px] font-normal">
                                            {phrase}
                                          </Badge>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            )
                          })}
                          {report.scores.length === 0 && (
                            <p className="text-sm text-slate-400">No competency scores available</p>
                          )}
                        </div>
                      </div>

                      <Separator />

                      {/* Integrity Flags */}
                      <div>
                        <h3 className="mb-3 text-lg font-semibold text-slate-900">Integrity Flags</h3>
                        <IntegrityFlagsForSession sessionId={report.session.session_id} />
                      </div>

                      <Separator />

                      {/* Actions */}
                      <div className="flex gap-3">
                        <Button
                          variant="outline"
                          onClick={() => window.open(`${BASE_URL}/api/reports/export/pdf/${report.session.session_id}`, "_blank")}
                        >
                          Download PDF
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => window.open(`${BASE_URL}/api/reports/export/csv`, "_blank")}
                        >
                          Export CSV
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="comparison">
            {loadingComparison ? (
              <div className="py-16 text-center text-sm text-slate-400">Loading comparison data...</div>
            ) : sortedComparison.length === 0 ? (
              <Card>
                <CardContent className="py-16 text-center text-sm text-slate-400">
                  No scored sessions yet
                </CardContent>
              </Card>
            ) : (
              <>
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
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Candidate Comparison</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-16">Rank</TableHead>
                          <TableHead>Candidate</TableHead>
                          <TableHead>Job</TableHead>
                          <TableHead
                            className="text-right cursor-pointer hover:text-slate-900 select-none"
                            onClick={() => handleSort("overall_score")}
                          >
                            Overall <SortIcon field="overall_score" />
                          </TableHead>
                          {categories.map((cat) => (
                            <TableHead
                              key={cat}
                              className="text-right cursor-pointer hover:text-slate-900 select-none"
                              onClick={() => handleSort(cat)}
                            >
                              {cat} <SortIcon field={cat} />
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {sortedComparison.map((row, idx) => (
                          <TableRow
                            key={row.session_id}
                            className="cursor-pointer hover:bg-slate-50"
                            onDoubleClick={() => {
                              setSelectedId(row.session_id)
                              const sessionsTab = document.querySelector('[value="sessions"]') as HTMLElement
                              sessionsTab?.click()
                            }}
                          >
                            <TableCell className="font-medium">
                              <div className="flex items-center gap-2">
                                <span>{idx + 1}</span>
                                {medalBadge(idx + 1)}
                              </div>
                            </TableCell>
                            <TableCell className="font-medium">{row.candidate_name}</TableCell>
                            <TableCell className="text-slate-500">{row.job_title}</TableCell>
                            <TableCell className={`text-right font-bold ${scoreColor(row.overall_score)}`}>
                              {row.overall_score}
                            </TableCell>
                            {categories.map((cat) => (
                              <TableCell key={cat} className={`text-right font-semibold ${scoreColor(row.category_scores[cat] ?? 0)}`}>
                                {row.category_scores[cat] ?? "—"}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

function IntegrityFlagsForSession({ sessionId }: { sessionId: string }) {
  const [flags, setFlags] = useState<{ flag_type: string; detail: string; severity: string }[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getIntegrityFlags()
      .then((all) => setFlags(all.filter((f) => f.session_id === sessionId)))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) return <p className="text-xs text-slate-400">Loading flags...</p>
  if (flags.length === 0) return <p className="text-xs text-slate-400">No integrity flags for this session</p>

  return (
    <div className="space-y-2">
      {flags.map((f, i) => (
        <div key={i} className="flex items-start gap-3 rounded-lg border border-slate-100 p-3">
          <Badge
            variant={f.severity === "high" ? "destructive" : f.severity === "medium" ? "secondary" : "outline"}
            className="mt-0.5 shrink-0"
          >
            {f.severity}
          </Badge>
          <div className="min-w-0">
            <span className="text-sm font-medium text-slate-800">{f.flag_type.replace(/_/g, " ")}</span>
            <p className="mt-0.5 text-xs text-slate-500">{f.detail}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
