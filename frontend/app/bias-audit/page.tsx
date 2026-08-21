"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import type { FairnessFlag, InterviewSession } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

export default function BiasAuditPage() {
  const [flags, setFlags] = useState<FairnessFlag[]>([])
  const [sessions, setSessions] = useState<InterviewSession[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.getBiasFlags(), api.getSessions()])
      .then(([f, s]) => { setFlags(f); setSessions(s) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const sessionMap = Object.fromEntries(sessions.map((s) => [s.session_id, s]))
  const flagged = flags.filter((f) => Math.abs(f.score_delta) >= 5)
  const avgDelta = flags.length > 0
    ? (flags.reduce((sum, f) => sum + Math.abs(f.score_delta), 0) / flags.length).toFixed(1)
    : "0"

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900">Bias Audit</h1>
          <p className="mt-1 text-slate-500">Fairness analysis of scoring</p>
        </div>

        {loading ? (
          <div className="py-16 text-center text-sm text-slate-400">Loading...</div>
        ) : (
          <>
            {/* Summary Stats */}
            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-slate-900">{flags.length}</div>
                  <div className="mt-1 text-sm text-slate-500">Total Flags</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-red-600">{flagged.length}</div>
                  <div className="mt-1 text-sm text-slate-500">Flagged (Δ ≥ 5)</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-amber-600">{avgDelta}</div>
                  <div className="mt-1 text-sm text-slate-500">Average Delta</div>
                </CardContent>
              </Card>
            </div>

            {/* Flags Table */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Bias Flags</CardTitle>
              </CardHeader>
              <CardContent>
                {flags.length === 0 ? (
                  <div className="py-12 text-center text-sm text-slate-400">No bias flags detected</div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Candidate</TableHead>
                        <TableHead>Job</TableHead>
                        <TableHead>Question ID</TableHead>
                        <TableHead className="text-right">Score Delta</TableHead>
                        <TableHead>Note</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {flags.map((f, i) => {
                        const delta = f.score_delta
                        const absDelta = Math.abs(delta)
                        let deltaColor = "text-emerald-600"
                        if (absDelta > 5) deltaColor = "text-red-600"
                        else if (absDelta >= 3) deltaColor = "text-amber-600"

                        const session = sessionMap[f.session_id]

                        return (
                          <TableRow key={i}>
                            <TableCell className="font-medium">{session?.candidate_name ?? "—"}</TableCell>
                            <TableCell className="text-slate-500">{session?.job_title ?? "—"}</TableCell>
                            <TableCell className="font-mono text-xs">{f.question_id}</TableCell>
                            <TableCell className="text-right">
                              <span className={`inline-flex items-center gap-1 font-semibold ${deltaColor}`}>
                                {delta > 0 ? "▲" : delta < 0 ? "▼" : ""}
                                {delta > 0 ? "+" : ""}{delta}
                              </span>
                            </TableCell>
                            <TableCell className="max-w-xs text-xs text-slate-600">{f.note}</TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  )
}
