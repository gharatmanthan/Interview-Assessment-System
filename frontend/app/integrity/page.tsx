"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { formatDate } from "@/lib/utils"
import type { IntegrityFlag } from "@/lib/types"
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

function severityBadge(severity: string) {
  if (severity === "high") return <Badge className="bg-red-100 text-red-700 border-red-200">high</Badge>
  if (severity === "medium") return <Badge className="bg-amber-100 text-amber-700 border-amber-200">medium</Badge>
  return <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">low</Badge>
}

function formatFlagType(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function IntegrityPage() {
  const [flags, setFlags] = useState<IntegrityFlag[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getIntegrityFlags()
      .then(setFlags)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const highCount = flags.filter((f) => f.severity === "high").length
  const mediumCount = flags.filter((f) => f.severity === "medium").length
  const uniqueSessions = new Set(flags.map((f) => f.session_id)).size

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900">Integrity Log</h1>
          <p className="mt-1 text-slate-500">Security and cheating detection</p>
        </div>

        {loading ? (
          <div className="py-16 text-center text-sm text-slate-400">Loading...</div>
        ) : (
          <>
            {/* Summary Stats */}
            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-4">
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-slate-900">{flags.length}</div>
                  <div className="mt-1 text-sm text-slate-500">Total Flags</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-red-600">{highCount}</div>
                  <div className="mt-1 text-sm text-slate-500">High Severity</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-amber-600">{mediumCount}</div>
                  <div className="mt-1 text-sm text-slate-500">Medium Severity</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="text-3xl font-bold text-slate-900">{uniqueSessions}</div>
                  <div className="mt-1 text-sm text-slate-500">Sessions Affected</div>
                </CardContent>
              </Card>
            </div>

            {/* Flags Table */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Integrity Flags</CardTitle>
              </CardHeader>
              <CardContent>
                {flags.length === 0 ? (
                  <div className="py-12 text-center text-sm text-slate-400">
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
                          <TableCell className="text-slate-500">{f.job_title ?? "—"}</TableCell>
                          <TableCell>{formatFlagType(f.flag_type)}</TableCell>
                          <TableCell className="max-w-xs text-xs text-slate-600">{f.detail}</TableCell>
                          <TableCell>{severityBadge(f.severity)}</TableCell>
                          <TableCell className="text-xs text-slate-500">{formatDate(f.timestamp)}</TableCell>
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
