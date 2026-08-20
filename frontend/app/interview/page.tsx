"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { api } from "@/lib/api"
import type { InterviewSession, IntegrityFlag } from "@/lib/types"
import {
  Camera,
  Play,
  Square,
  ChevronLeft,
  ChevronRight,
  Activity,
  AlertTriangle,
  Clock,
  Zap,
  Loader2,
  Wifi,
  WifiOff,
} from "lucide-react"

const QUESTIONS = [
  "Tell me about a challenging project you worked on and how you handled it.",
  "Describe a time when you had to learn a new technology quickly.",
  "How do you approach debugging a complex issue?",
  "Explain a technical concept to a non-technical person.",
  "What would you do if you disagreed with a technical decision made by your team?",
]

const CATEGORIES = [
  { value: "behavioral", label: "Behavioral" },
  { value: "technical", label: "Technical" },
  { value: "dsa", label: "DSA" },
  { value: "system_design", label: "System Design" },
  { value: "communication", label: "Communication" },
]

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`
}

function getScoreColor(score: number): string {
  if (score > 70) return "text-green-500"
  if (score >= 40) return "text-amber-500"
  return "text-red-500"
}

function getFlagSeverityBadge(severity: string) {
  switch (severity) {
    case "high":
      return "destructive" as const
    case "medium":
      return "secondary" as const
    default:
      return "outline" as const
  }
}

export default function InterviewPage() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const [session, setSession] = useState<InterviewSession | null>(null)
  const [isRecording, setIsRecording] = useState(false)
  const [currentQuestion, setCurrentQuestion] = useState(0)
  const [transcript, setTranscript] = useState("")
  const [category, setCategory] = useState("behavioral")
  const [integrityFlags, setIntegrityFlags] = useState<IntegrityFlag[]>([])
  const [scoringResult, setScoringResult] = useState<any>(null)
  const [candidateName, setCandidateName] = useState("")
  const [jobTitle, setJobTitle] = useState("")
  const [elapsedTime, setElapsedTime] = useState(0)
  const [wsConnected, setWsConnected] = useState(false)
  const [scoringLoading, setScoringLoading] = useState(false)
  const [cameraActive, setCameraActive] = useState(false)

  const startCamera = useCallback(async () => {
    try {
      if ((window as any).electronAPI?.getSources) {
        const sources = await (window as any).electronAPI.getSources({
          types: ["window", "screen"],
        })
        if (sources.length > 0) {
          const stream = await (navigator.mediaDevices as any).getUserMedia({
            video: { mandatory: { chromeMediaSource: "desktop", chromeMediaSourceId: sources[0].id } },
            audio: false,
          })
          if (videoRef.current) {
            videoRef.current.srcObject = stream
            setCameraActive(true)
          }
          return
        }
      }
    } catch {
      // Fall through to browser fallback
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        setCameraActive(true)
      }
    } catch {
      setCameraActive(false)
    }
  }, [])

  const stopCamera = useCallback(() => {
    if (videoRef.current?.srcObject) {
      const tracks = (videoRef.current.srcObject as MediaStream).getTracks()
      tracks.forEach((t) => t.stop())
      videoRef.current.srcObject = null
    }
    setCameraActive(false)
  }, [])

  const connectWebSocket = useCallback((sessionId: string) => {
    const port = (window as any).__API_PORT__ || 8000
    const ws = new WebSocket(`ws://localhost:${port}/api/ws/integrity/${sessionId}`)
    wsRef.current = ws

    ws.onopen = () => setWsConnected(true)
    ws.onclose = () => setWsConnected(false)
    ws.onerror = () => setWsConnected(false)
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data && data.flags && Array.isArray(data.flags)) {
          if (data.flags.length > 0) {
            setIntegrityFlags((prev) => [...data.flags, ...prev])
          }
        } else if (Array.isArray(data)) {
          setIntegrityFlags(data)
        } else if (data && data.flag_type) {
          setIntegrityFlags((prev) => [data, ...prev])
        }
      } catch {
        // ignore malformed messages
      }
    }
  }, [])

  const disconnectWebSocket = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setWsConnected(false)
  }, [])

  const handleStartSession = async () => {
    if (!candidateName.trim()) return
    const sessionId = crypto.randomUUID()
    try {
      const created = await api.createSession({
        session_id: sessionId,
        candidate_name: candidateName,
        job_title: jobTitle,
      })
      setSession(created)
      setIsRecording(true)
      setElapsedTime(0)
      setIntegrityFlags([])
      setScoringResult(null)
      connectWebSocket(sessionId)
      await startCamera()
    } catch (err) {
      console.error("Failed to create session:", err)
    }
  }

  const handleStopSession = () => {
    setIsRecording(false)
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    disconnectWebSocket()
    stopCamera()
  }

  const handleRunScoring = async () => {
    if (!session || !transcript.trim()) return
    setScoringLoading(true)
    try {
      const result = await api.runScoring({
        session_id: session.session_id,
        question_id: `q${currentQuestion + 1}`,
        category,
        transcript,
      })
      setScoringResult(result)
    } catch (err) {
      console.error("Scoring failed:", err)
    } finally {
      setScoringLoading(false)
    }
  }

  // Timer
  useEffect(() => {
    if (isRecording) {
      timerRef.current = setInterval(() => {
        setElapsedTime((prev) => prev + 1)
      }, 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isRecording])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      handleStopSession()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const flagCount = integrityFlags.length
  const flagBadgeColor =
    flagCount >= 3
      ? "bg-red-500/20 text-red-500 border-red-500/30"
      : flagCount >= 1
        ? "bg-amber-500/20 text-amber-500 border-amber-500/30"
        : "bg-green-500/20 text-green-500 border-green-500/30"

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-[1600px]">
        <div className="grid gap-6 lg:grid-cols-5">
          {/* ===== LEFT COLUMN (main) ===== */}
          <div className="flex flex-col gap-6 lg:col-span-3">
            {/* Page Header */}
            <div className="flex items-center justify-between">
              <h1 className="text-2xl font-bold tracking-tight">Interview Session</h1>
              <Button
                onClick={isRecording ? handleStopSession : handleStartSession}
                variant={isRecording ? "destructive" : "default"}
                disabled={!isRecording && !candidateName.trim()}
                size="lg"
              >
                {isRecording ? (
                  <>
                    <Square className="mr-2 h-4 w-4" /> Stop Session
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" /> Start Session
                  </>
                )}
              </Button>
            </div>

            {/* Webcam Preview */}
            <Card className="overflow-hidden">
              <CardContent className="p-0">
                <div className="relative aspect-video bg-black/90">
                  <video
                    ref={videoRef}
                    autoPlay
                    muted
                    playsInline
                    className={`h-full w-full object-cover ${cameraActive ? "" : "hidden"}`}
                  />
                  {!cameraActive && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground">
                      <Camera className="mb-3 h-16 w-16 opacity-30" />
                      <p className="text-sm">Camera feed will appear here</p>
                    </div>
                  )}
                  <Badge
                    variant={session?.status === "completed" ? "secondary" : "default"}
                    className="absolute right-3 top-3"
                  >
                    {session?.status === "completed" ? "Completed" : isRecording ? "In Progress" : "Idle"}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            {/* Question Navigation */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">
                    Question {currentQuestion + 1} of {QUESTIONS.length}
                  </CardTitle>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() => setCurrentQuestion((p) => Math.max(0, p - 1))}
                      disabled={currentQuestion === 0}
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() => setCurrentQuestion((p) => Math.min(QUESTIONS.length - 1, p + 1))}
                      disabled={currentQuestion === QUESTIONS.length - 1}
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {QUESTIONS[currentQuestion]}
                </p>
              </CardContent>
            </Card>

            {/* Transcript Area */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Transcript</CardTitle>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger className="w-[180px]">
                      <SelectValue placeholder="Category" />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map((c) => (
                        <SelectItem key={c.value} value={c.value}>
                          {c.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </CardHeader>
              <CardContent>
                <textarea
                  className="h-40 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder="Transcript will appear here when audio processing is enabled. You can also paste or type notes here manually."
                  value={transcript}
                  onChange={(e) => setTranscript(e.target.value)}
                />
              </CardContent>
            </Card>
          </div>

          {/* ===== RIGHT COLUMN (sidebar) ===== */}
          <div className="flex flex-col gap-6 lg:col-span-2">
            {/* Integrity Status */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Activity className="h-4 w-4" />
                    Integrity Monitor
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <span
                      className={`h-2 w-2 rounded-full ${wsConnected ? "bg-green-500" : "bg-red-500"}`}
                    />
                    <span className="text-xs text-muted-foreground">
                      {wsConnected ? (
                        <Wifi className="inline h-3 w-3" />
                      ) : (
                        <WifiOff className="inline h-3 w-3" />
                      )}
                    </span>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Flags:</span>
                  <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${flagBadgeColor}`}>
                    {flagCount}
                  </span>
                </div>
                <ScrollArea className="h-48">
                  {integrityFlags.length === 0 ? (
                    <p className="py-8 text-center text-xs text-muted-foreground">
                      No integrity flags detected
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {integrityFlags.map((flag, i) => (
                        <div
                          key={flag.id ?? i}
                          className="flex items-start gap-2 rounded-md border p-2 text-xs"
                        >
                          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
                          <div className="flex-1">
                            <div className="flex items-center gap-1">
                              <Badge variant={getFlagSeverityBadge(flag.severity)} className="text-[10px]">
                                {flag.severity}
                              </Badge>
                              <span className="font-medium">{flag.flag_type}</span>
                            </div>
                            <p className="mt-0.5 text-muted-foreground">{flag.detail}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>

            {/* Session Info */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Session Info</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Candidate Name</label>
                  <Input
                    placeholder="Enter candidate name"
                    value={candidateName}
                    onChange={(e) => setCandidateName(e.target.value)}
                    disabled={isRecording}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Job Title</label>
                  <Input
                    placeholder="Enter job title"
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    disabled={isRecording}
                  />
                </div>
                <div className="flex items-center justify-between border-t pt-4">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Clock className="h-4 w-4" />
                    <span className="text-sm">Elapsed</span>
                  </div>
                  <span className="font-mono text-lg font-semibold tabular-nums">
                    {formatTime(elapsedTime)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Status</span>
                  <Badge variant={isRecording ? "default" : "secondary"}>
                    {session?.status ?? "idle"}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            {/* Scoring */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Scoring</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Button
                  onClick={handleRunScoring}
                  disabled={!transcript.trim() || scoringLoading || !session}
                  className="w-full"
                  variant="outline"
                >
                  {scoringLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Running...
                    </>
                  ) : (
                    <>
                      <Zap className="mr-2 h-4 w-4" /> Run Scoring
                    </>
                  )}
                </Button>

                {scoringResult && (
                  <div className="space-y-3 rounded-md border p-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Score</span>
                      <span className={`text-3xl font-bold tabular-nums ${getScoreColor(scoringResult.score?.score ?? 0)}`}>
                        {scoringResult.score?.score ?? 0}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Confidence</span>
                      <span className="font-medium">
                        {((scoringResult.score?.confidence ?? 0) * 100).toFixed(1)}%
                      </span>
                    </div>
                    {scoringResult.explanation?.summary && (
                      <div className="border-t pt-3">
                        <p className="text-xs font-medium text-muted-foreground">Explanation</p>
                        <p className="mt-1 text-sm">{scoringResult.explanation.summary}</p>
                      </div>
                    )}
                    {scoringResult.fairness?.score_delta !== undefined && (
                      <div className="flex items-center justify-between border-t pt-3 text-sm">
                        <span className="text-muted-foreground">Fairness Delta</span>
                        <span
                          className={
                            Math.abs(scoringResult.fairness.score_delta) > 10
                              ? "text-amber-500 font-medium"
                              : "text-muted-foreground"
                          }
                        >
                          {scoringResult.fairness.score_delta > 0 ? "+" : ""}
                          {scoringResult.fairness.score_delta.toFixed(2)}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
