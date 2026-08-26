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
    <div className="min-h-screen bg-background p-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground">Bias Audit</h1>
          <p className="mt-1 leading-relaxed text-muted-foreground">Fairness analysis of scoring</p>
        </div>

        {loading ? (
          <div className="py-16 text-center text-sm text-muted-foreground">Loading...</div>
        ) : (
          <>
            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-foreground">{flags.length}</div>
                  <div className="mt-1 text-sm leading-relaxed text-muted-foreground">Total Flags</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-destructive-text">{flagged.length}</div>
                  <div className="mt-1 text-sm leading-relaxed text-muted-foreground">Flagged (Δ ≥ 5)</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-warning-text">{avgDelta}</div>
                  <div className="mt-1 text-sm leading-relaxed text-muted-foreground">Average Delta</div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Bias Flags</CardTitle>
              </CardHeader>
              <CardContent>
                {flags.length === 0 ? (
                  <div className="py-12 text-center text-sm text-muted-foreground">No bias flags detected</div>
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
                        let deltaColor = "text-success-text"
                        if (absDelta > 5) deltaColor = "text-destructive-text"
                        else if (absDelta >= 3) deltaColor = "text-warning-text"

                        const session = sessionMap[f.session_id]

                        return (
                          <TableRow key={i}>
                            <TableCell className="font-medium">{session?.candidate_name ?? "—"}</TableCell>
                            <TableCell className="text-muted-foreground">{session?.job_title ?? "—"}</TableCell>
                            <TableCell className="font-mono text-xs">{f.question_id}</TableCell>
                            <TableCell className="text-right">
                              <span className={`inline-flex items-center gap-1 font-semibold ${deltaColor}`}>
                                {delta > 0 ? "▲" : delta < 0 ? "▼" : ""}
                                {delta > 0 ? "+" : ""}{delta}
                              </span>
                            </TableCell>
                            <TableCell className="max-w-xs text-xs leading-relaxed text-muted-foreground">{f.note}</TableCell>
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
