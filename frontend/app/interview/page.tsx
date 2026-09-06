"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { toast } from "sonner"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { api, getBaseUrl, getAuthToken } from "@/lib/api"
import { connectRecruiterLive } from "@/lib/live"
import type { InterviewSession, IntegrityFlag, Candidate, QuestionItem, LiveServerMessage, InterviewStatusResponse } from "@/lib/types"
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
  Sparkles,
  RotateCcw,
  Lock,
  MessageSquarePlus,
  CircleStop,
  User,
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
  if (score > 70) return "text-success"
  if (score >= 40) return "text-warning"
  return "text-destructive"
}

function getFlagSeverityBadge(severity: string) {
  switch (severity) {
    case "high":
      return "destructive" as const
    case "medium":
      return "warning" as const
    default:
      return "outline" as const
  }
}

type ScoringResult = Awaited<ReturnType<typeof api.runScoring>>

export default function InterviewPage() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const integrityPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [session, setSession] = useState<InterviewSession | null>(null)
  const [isRecording, setIsRecording] = useState(false)
  const [currentQuestion, setCurrentQuestion] = useState(0)
  const [transcript, setTranscript] = useState("")
  const [category, setCategory] = useState("behavioral")
  const [integrityFlags, setIntegrityFlags] = useState<IntegrityFlag[]>([])
  const [scoringResult, setScoringResult] = useState<ScoringResult | null>(null)
  const [jobTitle, setJobTitle] = useState("")
  const [elapsedTime, setElapsedTime] = useState(0)
  const [wsConnected, setWsConnected] = useState(false)
  const [scoringLoading, setScoringLoading] = useState(false)
  const [cameraActive, setCameraActive] = useState(false)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [selectedCandidateId, setSelectedCandidateId] = useState("")
  const [candidatesLoading, setCandidatesLoading] = useState(false)

  // Phase 3B: MODE 2 self-serve interview status for the selected candidate.
  const [interviewStatus, setInterviewStatus] = useState<InterviewStatusResponse | null>(null)

  const interviewStatusLabel = (s: string | undefined) =>
    ({ not_ready: "Not prepared", ready: "Ready", in_progress: "In progress", completed: "Completed" }[s ?? ""] ?? "—")

  const [preparedQuestions, setPreparedQuestions] = useState<QuestionItem[]>([])
  const [questionsPreparing, setQuestionsPreparing] = useState(false)
  const [numQuestions, setNumQuestions] = useState(10)

  // Phase 3A: MODE 1 live interview state.
  const liveWsRef = useRef<WebSocket | null>(null)
  const currentQuestionSet = useRef<Set<string>>(new Set())
  const preparedQuestionsRef = useRef<QuestionItem[]>([])
  const [liveConnected, setLiveConnected] = useState(false)
  const [recruiterLive, setRecruiterLive] = useState(false)
  const [candidateLive, setCandidateLive] = useState(false)
  const [liveCurrentQuestion, setLiveCurrentQuestion] = useState<QuestionItem | null>(null)
  const [liveTranscript, setLiveTranscript] = useState("")
  const [liveAsking, setLiveAsking] = useState(false)

  useEffect(() => {
    let cancelled = false
    setCandidatesLoading(true)
    api.getCandidates()
      .then((list) => {
        if (!cancelled) setCandidates(list)
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setCandidatesLoading(false) })
    return () => { cancelled = true }
  }, [])

  // Fetch the Mode 2 interview status + question-set summary for the selected
  // candidate so the recruiter sees Not prepared / Ready / In progress /
  // Completed without needing a live connection.
  useEffect(() => {
    let cancelled = false
    setInterviewStatus(null)
    if (!selectedCandidateId) return
    api.getCandidateInterviewStatus(selectedCandidateId)
      .then((s) => { if (!cancelled) setInterviewStatus(s) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [selectedCandidateId])

  const startCamera = useCallback(async () => {
    try {
      if ((window as any).electronAPI?.getSources) {
        const sources = await (window as any).electronAPI.getSources({ types: ["window", "screen"] })
        if (sources.length > 0) {
          const stream = await (navigator.mediaDevices as any).getUserMedia({
            video: { mandatory: { chromeMediaSource: "desktop", chromeMediaSourceId: sources[0].id } },
            audio: false,
          })
          if (videoRef.current) { videoRef.current.srcObject = stream; setCameraActive(true) }
          return
        }
      }
    } catch {}
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      if (videoRef.current) { videoRef.current.srcObject = stream; setCameraActive(true) }
    } catch { setCameraActive(false) }
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
    getBaseUrl().then((base) => {
      const token = getAuthToken() || ''
      const wsUrl = `${base.replace(/^http/, "ws")}/api/ws/integrity/${sessionId}?token=${encodeURIComponent(token)}`
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws
      ws.onopen = () => setWsConnected(true)
      ws.onclose = () => setWsConnected(false)
      ws.onerror = () => setWsConnected(false)
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data && data.flags && Array.isArray(data.flags)) {
            if (data.flags.length > 0) setIntegrityFlags((prev) => [...data.flags, ...prev])
          } else if (Array.isArray(data)) {
            setIntegrityFlags(data)
          } else if (data && data.flag_type) {
            setIntegrityFlags((prev) => [data, ...prev])
          }
        } catch {}
      }
    })
  }, [])

  const connectIntegrityMonitor = useCallback(async (sessionId: string) => {
    let mode = "local"
    try {
      const cfg = await (window as any).appConfig?.getConfig?.()
      mode = cfg?.backendMode || "local"
    } catch {}

    if (mode === "remote") {
      const scanAndReport = (await import("@/lib/integrity")).scanAndReport
      const pushFlags = async () => {
        try {
          const flags = await scanAndReport(sessionId)
          if (flags.length > 0) {
            setIntegrityFlags((prev) => [
              ...flags.map((f) => ({ ...f, timestamp: new Date().toISOString() })),
              ...prev,
            ])
          }
        } catch {}
      }
      await pushFlags()
      integrityPollRef.current = setInterval(pushFlags, 15000)
      setWsConnected(true)
      return
    }
    connectWebSocket(sessionId)
  }, [connectWebSocket])

  const disconnectWebSocket = useCallback(() => {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    if (integrityPollRef.current) { clearInterval(integrityPollRef.current); integrityPollRef.current = null }
    setWsConnected(false)
  }, [])

  const handleStartSession = async () => {
    if (!selectedCandidateId) return
    const selected = candidates.find((c) => c.candidate_id === selectedCandidateId)
    try {
      const created = await api.createSession({ candidate_id: selectedCandidateId })
      setSession(created)
      setJobTitle(created.job_title || selected?.job_title || "")
      setIsRecording(true)
      setElapsedTime(0)
      setIntegrityFlags([])
      setScoringResult(null)
      await connectIntegrityMonitor(created.session_id)
      await startCamera()
    } catch (err) {
      console.error("Failed to create session:", err)
    }
  }

  const handlePrepareQuestions = async () => {
    if (!session || questionsPreparing) return
    setQuestionsPreparing(true)
    try {
      const res = await api.selectQuestions(session.session_id, numQuestions)
      setPreparedQuestions(res.questions)
    } catch (err) {
      console.error("Failed to prepare questions:", err)
    } finally {
      setQuestionsPreparing(false)
    }
  }

  const handleRegenerateQuestions = async () => {
    if (!session || questionsPreparing) return
    setQuestionsPreparing(true)
    try {
      const res = await api.selectQuestions(session.session_id, numQuestions)
      setPreparedQuestions(res.questions)
    } catch (err) {
      console.error("Failed to regenerate questions:", err)
    } finally {
      setQuestionsPreparing(false)
    }
  }

  const handleStopSession = () => {
    setIsRecording(false)
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
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

  // Phase 3A: MODE 1 shared live interview. The recruiter connects with their
  // Bearer token; server auth resolves the role and the owned session.
  const liveSend = (payload: Record<string, unknown>) => {
    if (liveWsRef.current?.readyState === WebSocket.OPEN) {
      liveWsRef.current.send(JSON.stringify(payload))
    }
  }

  const handleLiveMessage = useCallback((msg: LiveServerMessage) => {
    switch (msg.type) {
      case "joined": {
        setLiveConnected(true)
        setRecruiterLive((msg.role ?? "candidate") === "recruiter")
        setCandidateLive((msg.connections?.candidate ?? 0) > 0)
        // Find the persisted live question among prepared questions.
        if (msg.current_question) {
          const found = preparedQuestionsRef.current.find(
            (q) => q.question_id === msg.current_question?.question_id
          )
          setLiveCurrentQuestion(found ?? msg.current_question!)
          setLiveTranscript("")
        } else {
          setLiveCurrentQuestion(null)
        }
        break
      }
      case "connection_status": {
        setRecruiterLive((msg.recruiter ?? 0) > 0)
        setCandidateLive((msg.candidate ?? 0) > 0)
        break
      }
      case "transcript_ready": {
        setLiveTranscript(msg.transcript ?? "")
        break
      }
      case "answer_started": {
        setLiveTranscript("")
        break
      }
      case "interview_ended": {
        setLiveConnected(false)
        break
      }
      default:
        break
    }
  }, [])

  const connectLive = async () => {
    if (!session) return
    const token = await getAuthToken()
    if (!token) { toast.error("Not authenticated"); return }
    connectRecruiterLive(
      { token, sessionId: session.session_id },
      {
        onOpen: () => { setRecruiterLive(true) },
        onClose: () => { setLiveConnected(false); setRecruiterLive(false) },
        onMessage: handleLiveMessage,
      }
    ).then((ws) => { liveWsRef.current = ws })
  }

  const disconnectLive = () => {
    liveWsRef.current?.close()
    liveWsRef.current = null
    setLiveConnected(false)
    setRecruiterLive(false)
    setCandidateLive(false)
  }

  // Ask the next prepared question that has not yet been asked.
  const handleAskNextQuestion = async () => {
    if (!liveWsRef.current || liveWsRef.current.readyState !== WebSocket.OPEN) return
    const asked = currentQuestionSet.current
    setLiveAsking(true)
    try {
      const next = preparedQuestionsRef.current.find((q) => !asked.has(q.question_id))
      if (!next) {
        toast.info("All prepared questions have been asked.")
        return
      }
      setLiveCurrentQuestion(next)
      setLiveTranscript("")
      currentQuestionSet.current.add(next.question_id)
      liveSend({ type: "ask_question", question_id: next.question_id })
    } finally {
      setLiveAsking(false)
    }
  }

  const handleEndLiveInterview = async () => {
    if (!liveWsRef.current || liveWsRef.current.readyState !== WebSocket.OPEN) return
    toast("Ending live interview…")
    liveSend({ type: "end_interview" })
    setLiveConnected(false)
  }

  // Keep prepared questions mirrored for the live message handler.
  useEffect(() => {
    preparedQuestionsRef.current = preparedQuestions
  }, [preparedQuestions])


  useEffect(() => {
    if (isRecording) {
      timerRef.current = setInterval(() => setElapsedTime((prev) => prev + 1), 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [isRecording])

  useEffect(() => {
    return () => { handleStopSession() }
  }, [])

  const flagCount = integrityFlags.length
  const flagBadgeColor =
    flagCount >= 3
      ? "bg-destructive/20 text-destructive border-destructive/30"
      : flagCount >= 1
        ? "bg-warning/20 text-warning border-warning/30"
        : "bg-success/20 text-success border-success/30"

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-[1600px]">
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="flex flex-col gap-6 lg:col-span-3">
            <div className="flex items-center justify-between">
              <h1 className="text-2xl font-bold tracking-tight text-foreground">Interview Session</h1>
                <Button onClick={isRecording ? handleStopSession : handleStartSession} variant={isRecording ? "destructive" : "default"} disabled={!isRecording && !selectedCandidateId} size="lg">
                {isRecording ? (<><Square className="mr-2 h-4 w-4" /> Stop Session</>) : (<><Play className="mr-2 h-4 w-4" /> Start Session</>)}
              </Button>
            </div>

            <Card className="overflow-hidden">
              <CardContent className="p-0">
                <div className="relative aspect-video bg-black/90">
                  <video ref={videoRef} autoPlay muted playsInline className={`h-full w-full object-cover ${cameraActive ? "" : "hidden"}`} />
                  {!cameraActive && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground">
                      <Camera className="mb-3 h-16 w-16 opacity-30" />
                      <p className="text-sm">Camera feed will appear here</p>
                    </div>
                  )}
                  <Badge variant={session?.status === "completed" ? "secondary" : "default"} className="absolute right-3 top-3">
                    {session?.status === "completed" ? "Completed" : isRecording ? "In Progress" : "Idle"}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Question {currentQuestion + 1} of {QUESTIONS.length}</CardTitle>
                  <div className="flex gap-2">
                    <Button variant="outline" size="icon" onClick={() => setCurrentQuestion((p) => Math.max(0, p - 1))} disabled={currentQuestion === 0}><ChevronLeft className="h-4 w-4" /></Button>
                    <Button variant="outline" size="icon" onClick={() => setCurrentQuestion((p) => Math.min(QUESTIONS.length - 1, p + 1))} disabled={currentQuestion === QUESTIONS.length - 1}><ChevronRight className="h-4 w-4" /></Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed text-muted-foreground">{QUESTIONS[currentQuestion]}</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Transcript</CardTitle>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger className="w-[180px]"><SelectValue placeholder="Category" /></SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map((c) => (<SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>))}
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

          <div className="flex flex-col gap-6 lg:col-span-2">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Activity className="h-4 w-4" /> Integrity Monitor
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${wsConnected ? "bg-success" : "bg-destructive"}`} />
                    <span className="text-xs text-muted-foreground">
                      {wsConnected ? <Wifi className="inline h-3 w-3" /> : <WifiOff className="inline h-3 w-3" />}
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
                    <p className="py-8 text-center text-xs text-muted-foreground">No integrity flags detected</p>
                  ) : (
                    <div className="space-y-2">
                      {integrityFlags.map((flag, i) => (
                        <div key={flag.id ?? i} className="flex items-start gap-2 rounded-md border border-border p-2 text-xs">
                          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-warning" />
                          <div className="flex-1">
                            <div className="flex items-center gap-1">
                              <Badge variant={getFlagSeverityBadge(flag.severity)} className="text-[10px]">{flag.severity}</Badge>
                              <span className="font-medium text-foreground">{flag.flag_type}</span>
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

            <Card>
              <CardHeader><CardTitle className="text-base">Session Info</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Candidate</label>
                  {candidatesLoading ? (
                    <div className="text-sm text-muted-foreground">Loading candidates...</div>
                  ) : (
                    <Select
                      value={selectedCandidateId}
                      onValueChange={setSelectedCandidateId}
                      disabled={isRecording}
                    >
                      <SelectTrigger className="w-full"><SelectValue placeholder="Select a candidate" /></SelectTrigger>
                      <SelectContent>
                        {candidates.map((c) => (
                          <SelectItem key={c.candidate_id} value={c.candidate_id}>
                            {c.name}{c.job_title ? ` — ${c.job_title}` : ""} ({c.status})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Job Title</label>
                  <Input placeholder={jobTitle || "Resolved from candidate"} value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} disabled={isRecording} />
                </div>
                <div className="flex items-center justify-between border-t border-border pt-4">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Clock className="h-4 w-4" /><span className="text-sm">Elapsed</span>
                  </div>
                  <span className="font-mono text-lg font-semibold tabular-nums text-foreground">{formatTime(elapsedTime)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Status</span>
                  <Badge variant={isRecording ? "default" : "secondary"}>{session?.status ?? "idle"}</Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">Interview Status</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {!selectedCandidateId ? (
                  <p className="text-sm text-muted-foreground">Select a candidate to see their interview status.</p>
                ) : interviewStatus ? (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Stage</span>
                      <Badge variant={interviewStatus.interview_status === "completed" ? "default" : "secondary"}>
                        {interviewStatusLabel(interviewStatus.interview_status)}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Question set</span>
                      <span className="text-foreground">{interviewStatus.locked ? "Locked" : "Not prepared"}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Questions</span>
                      <span className="text-foreground">{interviewStatus.answered_questions} / {interviewStatus.total_questions} answered</span>
                    </div>
                    {interviewStatus.categories.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        {interviewStatus.categories.map((cat) => (
                          <span key={cat} className="rounded-full border border-input px-2 py-0.5 text-[11px] text-muted-foreground">
                            {cat}
                          </span>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">Loading…</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Sparkles className="h-4 w-4" /> AI Question Set
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-xs text-muted-foreground">
                  Generate/select a question set tailored to the job description, then lock it to
                  this session. Once locked, the candidate receives exactly these questions — no
                  regeneration after the interview starts.
                </p>

                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min={3}
                    max={20}
                    value={numQuestions}
                    onChange={(e) => setNumQuestions(parseInt(e.target.value || "10", 10))}
                    disabled={preparedQuestions.length > 0}
                    className="w-24"
                  />
                  <Button
                    onClick={handlePrepareQuestions}
                    disabled={!session || questionsPreparing || preparedQuestions.length > 0}
                    variant="outline"
                    className="flex-1"
                  >
                    {questionsPreparing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                    Prepare Questions
                  </Button>
                </div>

                {preparedQuestions.length > 0 && (
                  <>
                    <div className="max-h-64 space-y-2 overflow-y-auto rounded-md border border-border p-3">
                      {preparedQuestions.map((q) => (
                        <div key={q.question_id} className="flex items-start gap-2 text-xs">
                          <span className="mt-0.5 shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                            {q.question_index + 1}
                          </span>
                          <div className="flex-1">
                            <p className="text-foreground">{q.question_text}</p>
                            <p className="mt-0.5 text-muted-foreground">
                              {q.category} · {q.difficulty} · {q.source}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        onClick={handleRegenerateQuestions}
                        disabled={questionsPreparing}
                        variant="ghost"
                        size="sm"
                        className="gap-1 text-xs"
                      >
                        <RotateCcw className="h-3 w-3" /> Regenerate
                      </Button>
                      <div className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
                        <Lock className="h-3 w-3" /> Locked to session
                      </div>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">Live Interview</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                {!liveConnected ? (
                  <Button
                    onClick={connectLive}
                    disabled={!session}
                    className="w-full"
                    variant="outline"
                  >
                    <Wifi className="mr-2 h-4 w-4" /> Connect to Live Session
                  </Button>
                ) : (
                  <>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <span className={`h-2 w-2 rounded-full ${recruiterLive ? "bg-success" : "bg-muted"}`} />
                        Recruiter {recruiterLive ? "online" : "offline"}
                      </span>
                      <span className="flex items-center gap-1">
                        <span className={`h-2 w-2 rounded-full ${candidateLive ? "bg-success" : "bg-muted"}`} />
                        Candidate {candidateLive ? "online" : "offline"}
                      </span>
                      <span className="ml-auto flex items-center gap-1">
                        {candidateLive ? <Wifi className="h-3 w-3 text-success" /> : <WifiOff className="h-3 w-3 text-destructive" />}
                      </span>
                    </div>

                    <div className="rounded-md border border-border p-3">
                      <p className="mb-1 text-xs font-medium text-muted-foreground">Current question</p>
                      {liveCurrentQuestion ? (
                        <p className="text-sm text-foreground">{liveCurrentQuestion.question_text}</p>
                      ) : (
                        <p className="text-sm text-muted-foreground">No question asked yet.</p>
                      )}
                    </div>

                    <div className="rounded-md border border-border p-3">
                      <p className="mb-1 text-xs font-medium text-muted-foreground">Candidate answer (transcript)</p>
                      {liveTranscript ? (
                        <p className="text-sm whitespace-pre-wrap text-foreground">{liveTranscript}</p>
                      ) : (
                        <p className="text-sm text-muted-foreground">Waiting for the candidate to answer…</p>
                      )}
                    </div>

                    <Button
                      onClick={handleAskNextQuestion}
                      disabled={liveAsking || !candidateLive || preparedQuestions.length === 0}
                      className="w-full"
                    >
                      {liveAsking ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <MessageSquarePlus className="mr-2 h-4 w-4" />}
                      Ask Next Question
                    </Button>

                    <Button
                      onClick={handleEndLiveInterview}
                      variant="destructive"
                      className="w-full"
                    >
                      <CircleStop className="mr-2 h-4 w-4" /> End Interview
                    </Button>
                  </>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">Scoring</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <Button onClick={handleRunScoring} disabled={!transcript.trim() || scoringLoading || !session} className="w-full" variant="outline">
                  {scoringLoading ? (<><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Running...</>) : (<><Zap className="mr-2 h-4 w-4" /> Run Scoring</>)}
                </Button>

                {scoringResult && (
                  <div className="space-y-3 rounded-md border border-border p-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Score</span>
                      <span className={`text-3xl font-bold tabular-nums ${getScoreColor(scoringResult.score?.score ?? 0)}`}>
                        {scoringResult.score?.score ?? 0}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Confidence</span>
                      <span className="font-medium text-foreground">{((scoringResult.score?.confidence ?? 0) * 100).toFixed(1)}%</span>
                    </div>
                    {scoringResult.ml_score !== null && scoringResult.ml_score !== undefined && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">ML model score</span>
                        <span className="font-medium text-foreground">{scoringResult.ml_score.toFixed(1)}</span>
                      </div>
                    )}
                    {scoringResult.explanation?.summary && (
                      <div className="border-t border-border pt-3">
                        <p className="text-xs font-medium text-muted-foreground">Explanation</p>
                        <p className="mt-1 text-sm text-foreground">{scoringResult.explanation.summary}</p>
                      </div>
                    )}
                    {scoringResult.fairness?.score_delta !== undefined && (
                      <div className="flex items-center justify-between border-t border-border pt-3 text-sm">
                        <span className="text-muted-foreground">Fairness Delta</span>
                        <span className={Math.abs(scoringResult.fairness.score_delta) > 10 ? "text-warning font-medium" : "text-muted-foreground"}>
                          {scoringResult.fairness.score_delta > 0 ? "+" : ""}{scoringResult.fairness.score_delta.toFixed(2)}
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
