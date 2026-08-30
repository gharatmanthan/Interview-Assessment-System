"use client"

import { useEffect, useState, useCallback } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { ScheduledInterview } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { Loader2, RefreshCw, CalendarClock } from "lucide-react"
import { EmptyState } from "@/components/empty-state"

function formatLocal(iso?: string): string {
  if (!iso) return "—"
  try {
    const d = new Date(iso + (iso.endsWith("Z") ? "" : "Z"))
    return d.toLocaleString(undefined, {
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return iso
  }
}

export default function SchedulingPage() {
  const [items, setItems] = useState<ScheduledInterview[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await api.getScheduledInterviews()
      setItems(list)
    } catch (err: any) {
      setError(err.message || "Failed to load scheduled interviews")
      toast.error("Failed to load scheduled interviews")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Scheduled Interviews</h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Interviews automatically booked into the recruiter&apos;s availability.
            </p>
          </div>
          <Button variant="outline" onClick={fetchData} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-3 w-3 animate-spin" /> : <RefreshCw className="mr-2 h-3 w-3" />}
            Refresh
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CalendarClock className="h-5 w-5 text-primary" /> Upcoming Bookings
            </CardTitle>
            <CardDescription>
              Shortlisted candidates who passed the screening threshold and were auto-scheduled.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-16 text-muted-foreground">
                <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading...
              </div>
            ) : error ? (
              <div className="text-center py-10">
                <p className="text-sm text-destructive">{error}</p>
                <Button variant="outline" className="mt-4" onClick={fetchData}>Retry</Button>
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                icon={CalendarClock}
                title="No scheduled interviews yet"
                description="When a candidate passes the screening threshold, they'll automatically be booked into a free slot on the recruiter's Google Calendar."
              />
            ) : (
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Candidate</TableHead>
                      <TableHead>Job</TableHead>
                      <TableHead>Scheduled</TableHead>
                      <TableHead>Duration</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item) => (
                      <TableRow key={item.id ?? item.candidate_id}>
                        <TableCell>
                          <div className="font-medium text-foreground">{item.candidate_name ?? item.candidate_id}</div>
                          <div className="text-xs text-muted-foreground">{item.candidate_email}</div>
                        </TableCell>
                        <TableCell>{item.job_title ?? item.job_id}</TableCell>
                        <TableCell>{formatLocal(item.scheduled_at)}</TableCell>
                        <TableCell>{item.duration_minutes} min</TableCell>
                        <TableCell>
                          <Badge variant={item.status === "scheduled" ? "default" : "outline"}>
                            {item.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
