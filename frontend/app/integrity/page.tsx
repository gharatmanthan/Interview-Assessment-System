"use client"

import { useEffect, useState, useCallback } from "react"
import { api } from "@/lib/api"
import { formatDate } from "@/lib/utils"
import type { IntegrityFlag } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

function severityBadge(severity: string) {
  if (severity === "high") return <Badge variant="destructive">high</Badge>
  if (severity === "medium") return <Badge variant="warning">medium</Badge>
  return <Badge variant="success">low</Badge>
}

function formatFlagType(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function IntegrityPage() {
  const [flags, setFlags] = useState<IntegrityFlag[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setFlags(await api.getIntegrityFlags())
    } catch (err: any) {
      setError(err.message || "Failed to load integrity flags")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const highCount = flags.filter((f) => f.severity === "high").length
  const mediumCount = flags.filter((f) => f.severity === "medium").length
  const uniqueSessions = new Set(flags.map((f) => f.session_id)).size

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground">Integrity Log</h1>
          <p className="mt-1 leading-relaxed text-muted-foreground">Security and cheating detection</p>
        </div>

        {loading ? (
          <div className="py-16 text-center text-sm text-muted-foreground">Loading...</div>
        ) : error ? (
          <div className="py-16 text-center">
            <p className="text-sm text-destructive">{error}</p>
            <Button variant="outline" className="mt-4" onClick={load}>Retry</Button>
          </div>
        ) : (
          <>
            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-4">
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-foreground">{flags.length}</div>
                  <div className="mt-1 text-sm leading-relaxed text-muted-foreground">Total Flags</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-destructive-text">{highCount}</div>
                  <div className="mt-1 text-sm leading-relaxed text-muted-foreground">High Severity</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-warning-text">{mediumCount}</div>
                  <div className="mt-1 text-sm leading-relaxed text-muted-foreground">Medium Severity</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-foreground">{uniqueSessions}</div>
                  <div className="mt-1 text-sm leading-relaxed text-muted-foreground">Sessions Affected</div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Integrity Flags</CardTitle>
              </CardHeader>
              <CardContent>
                {flags.length === 0 ? (
                  <div className="py-12 text-center text-sm text-muted-foreground">
                    No integrity flags recorded
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Candidate</TableHead>
                        <TableHead>Job</TableHead>
                        <TableHead>Flag Type</TableHead>
                        <TableHead>Detail</TableHead>
                        <TableHead>Severity</TableHead>
                        <TableHead>Timestamp</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {flags.map((f, i) => (
                        <TableRow key={f.id ?? i}>
                          <TableCell className="font-medium">{f.candidate_name ?? "—"}</TableCell>
                          <TableCell className="text-muted-foreground">{f.job_title ?? "—"}</TableCell>
                          <TableCell>{formatFlagType(f.flag_type)}</TableCell>
                          <TableCell className="max-w-xs text-xs leading-relaxed text-muted-foreground">{f.detail}</TableCell>
                          <TableCell>{severityBadge(f.severity)}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{formatDate(f.timestamp)}</TableCell>
                        </TableRow>
                      ))}
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
