"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Radio, VideoOff } from "lucide-react"
import { api } from "@/lib/api"
import type { InterviewSession } from "@/lib/types"
import { EmptyState } from "@/components/empty-state"
import { Badge } from "@/components/ui/badge"

const POLL_MS = 2000

interface Feed {
  session_id: string
  candidate_name: string
  job_title: string
}

function LiveFeedTile({ feed }: { feed: Feed }) {
  const [frameUrl, setFrameUrl] = useState<string | null>(null)
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      const url = await api.fetchLiveFrame(feed.session_id)
      if (cancelled) {
        if (url) URL.revokeObjectURL(url)
        return
      }
      if (urlRef.current && urlRef.current !== url) URL.revokeObjectURL(urlRef.current)
      urlRef.current = url
      setFrameUrl(url)
    }

    poll()
    const timer = setInterval(poll, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
      if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    }
  }, [feed.session_id])

  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
      <div className="aspect-video w-full bg-foreground">
        {frameUrl ? (
          <img src={frameUrl} alt={`Live feed for ${feed.candidate_name}`} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-white/50">
            <VideoOff className="h-6 w-6" />
            <span className="text-xs">Waiting for feed&hellip;</span>
          </div>
        )}
      </div>
      <div className="flex items-center justify-between px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">{feed.candidate_name}</p>
          <p className="truncate text-xs leading-relaxed text-muted-foreground">{feed.job_title}</p>
        </div>
        <Badge variant="destructive" className="gap-1.5">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-destructive" />
          Live
        </Badge>
      </div>
    </div>
  )
}

export default function LiveMonitorPage() {
  const [feeds, setFeeds] = useState<Feed[]>([])
  const [loaded, setLoaded] = useState(false)

  const pollSessions = useCallback(async () => {
    try {
      const sessions: InterviewSession[] = await api.getSessions()
      setFeeds(
        sessions
          .filter((s) => s.status === "in_progress")
          .map((s) => ({
            session_id: s.session_id,
            candidate_name: s.candidate_name,
            job_title: s.job_title,
          }))
      )
    } catch {
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    pollSessions()
    const timer = setInterval(pollSessions, POLL_MS)
    return () => clearInterval(timer)
  }, [pollSessions])

  return (
    <div className="px-8 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Live Monitor</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Watch candidates whose interviews are in progress &mdash; snapshots refresh every {POLL_MS / 1000} seconds.
          </p>
        </div>
        {feeds.length > 0 && (
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <Radio className="h-4 w-4 animate-pulse text-destructive" />
            {feeds.length} active interview{feeds.length > 1 ? "s" : ""}
          </span>
        )}
      </div>

      {!loaded ? null : feeds.length === 0 ? (
        <EmptyState
          icon={Radio}
          title="No live interviews right now"
          description="When a candidate starts their interview, their camera snapshot appears here automatically."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {feeds.map((feed) => (
            <LiveFeedTile key={feed.session_id} feed={feed} />
          ))}
        </div>
      )}
    </div>
  )
}
