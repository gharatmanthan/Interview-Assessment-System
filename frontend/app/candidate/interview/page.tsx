"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { runLocalScan } from "@/lib/integrity"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { TimerRing } from "@/components/timer-ring"
import { Video, Send, ChevronRight } from "lucide-react"

const QUESTIONS = [
  "Tell me about a challenging project you worked on and how you handled it.",
  "Describe a time when you had to learn a new technology quickly.",
  "How do you approach debugging a complex issue?",
  "Explain a technical concept to a non-technical person.",
  "What would you do if you disagreed with a technical decision made by your team?",
]

const CATEGORIES = ["behavioral", "technical", "dsa", "system_design", "communication"]

const INTEGRITY_POLL_MS = 30000
const LIVE_FRAME_INTERVAL_MS = 1500

export default function CandidateInterviewPage() {
  const router = useRouter()
  const videoRef = useRef<HTMLVideoElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reportedFlagsRef = useRef<Set<string>>(new Set())
  const frameTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [sessionStarted, setSessionStarted] = useState(false)
  const [currentQuestion, setCurrentQuestion] = useState(0)
  const [timeLeft, setTimeLeft] = useState(300)
  const [recording, setRecording] = useState(false)
  const [transcript, setTranscript] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [cameraActive, setCameraActive] = useState(false)

  const candidate = typeof window !== "undefined" ? JSON.parse(sessionStorage.getItem("candidate") || "null") : null
  const job = typeof window !== "undefined" ? JSON.parse(sessionStorage.getItem("candidate_job") || "null") : null
  const sessionId = typeof window !== "undefined" ? sessionStorage.getItem("session_id") : null
  const interviewToken = typeof window !== "undefined" ? sessionStorage.getItem("interview_token") || "" : ""

  useEffect(() => {
    if (!candidate || !job || !sessionId) {
      router.push("/candidate/entry")
      return
    }
    async function init() {
      try {
        await api.startCandidateSession(sessionId!, candidate.candidate_id, job.job_id, interviewToken)
        setSessionStarted(true)
      } catch {
        toast.error("Failed to start session")
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          setCameraActive(true)
        }
        startRecording(stream)
        setRecording(true)
      } catch {
        setCameraActive(false)
      }
      pollRef.current = setInterval(() => {
        pollIntegrityOnce(sessionId!).catch(() => {})
      }, INTEGRITY_POLL_MS)

      frameTimerRef.current = setInterval(() => {
        pushLiveFrame(sessionId!).catch(() => {})
      }, LIVE_FRAME_INTERVAL_MS)
    }
    init()
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (frameTimerRef.current) clearInterval(frameTimerRef.current)
    }
  }, [])

  async function pushLiveFrame(sid: string) {
    const video = videoRef.current
    if (!video || video.readyState < 2 || !video.videoWidth) return
    const canvas = document.createElement("canvas")
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext("2d")?.drawImage(video, 0, 0)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.6)
    )
    if (blob) await api.uploadLiveFrame(sid, blob)
  }

  async function pollIntegrityOnce(sid: string) {
    const result = await runLocalScan()
    if (!result) return
    const candidates = [
      ...result.open_ports.map((p) => ({
        session_id: sid,
        flag_type: "remote_access_port",
        detail: `${p.tool} port ${p.port} is open`,
        severity: "high",
      })),
      ...result.flagged_processes.map((proc) => ({
        session_id: sid,
        flag_type: "suspicious_process",
        detail: proc.detail,
        severity: "high",
      })),
    ]
    const fresh = candidates.filter((f) => !reportedFlagsRef.current.has(f.detail))
    if (fresh.length > 0) {
      fresh.forEach((f) => reportedFlagsRef.current.add(f.detail))
      await api.postIntegrityFlags(fresh)
    }
  }

  useEffect(() => {
    if (!recording || timeLeft <= 0) return
    const timer = setInterval(() => {
      setTimeLeft((t) => {
        if (t <= 1) {
          handleSubmit()
          return 0
        }
        return t - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [recording, currentQuestion])

  function startRecording(stream: MediaStream) {
    try {
      if (typeof MediaRecorder === "undefined") return
      const mimeCandidates = ["video/webm;codecs=vp8,opus", "video/webm", "audio/webm"]
      const mimeType = mimeCandidates.find((m) => MediaRecorder.isTypeSupported(m))
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.start(5000)
      recorderRef.current = recorder
    } catch {
    }
  }

  function stopRecording(): Promise<Blob | null> {
    return new Promise((resolve) => {
      const recorder = recorderRef.current
      if (!recorder || recorder.state === "inactive") {
        resolve(null)
        return
      }
      recorder.onstop = () => {
        const blob = chunksRef.current.length > 0 ? new Blob(chunksRef.current, { type: chunksRef.current[0].type }) : null
        resolve(blob)
      }
      recorder.stop()
    })
  }

  async function uploadRecording() {
    try {
      const blob = await stopRecording()
      streamRef.current?.getTracks().forEach((t) => t.stop())
      if (!blob || !sessionId) return
      const ext = blob.type.includes("webm") ? "webm" : "bin"
      await api.uploadRecording(sessionId, { video: blob }, { video: `${sessionId}_capture.${ext}` })
    } catch {
      toast.error("Interview recording could not be uploaded")
    }
  }

  async function handleSubmit() {
    if (!sessionId || submitting) return
    setSubmitting(true)
    try {
      if (transcript.trim()) {
        await api.submitAnswer(
          sessionId,
          `q${currentQuestion + 1}`,
          CATEGORIES[currentQuestion % CATEGORIES.length],
          transcript
        )
      }
      setTranscript("")
      if (currentQuestion < QUESTIONS.length - 1) {
        setCurrentQuestion((q) => q + 1)
        setTimeLeft(300)
      } else {
        if (frameTimerRef.current) clearInterval(frameTimerRef.current)
        frameTimerRef.current = null
        await api.completeCandidateSession(sessionId)
        await uploadRecording()
        router.push("/candidate/done")
      }
    } catch (err) {
      toast.error("Failed to submit. Please try again.")
    } finally {
      setSubmitting(false)
    }
  }

  if (!candidate || !job) return null

  return (
    <div className="-mx-4 min-h-screen bg-background p-4 md:-mx-8 md:p-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-foreground">{job.title}</h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Question {currentQuestion + 1} of {QUESTIONS.length}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {recording && (
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 animate-pulse rounded-full bg-destructive" />
                <span className="text-xs text-muted-foreground">Recording</span>
              </div>
            )}
          </div>
        </div>

        <div className="fixed bottom-4 right-4 z-50">
          <div className="h-32 w-44 overflow-hidden rounded-xl border-2 border-white shadow-lg">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className={`h-full w-full object-cover ${cameraActive ? "" : "hidden"}`}
            />
            {!cameraActive && (
              <div className="flex h-full items-center justify-center bg-foreground text-white/40">
                <Video className="h-6 w-6" />
              </div>
            )}
          </div>
        </div>

        <Card className="rounded-2xl shadow-sm">
          <CardContent className="p-8">
            <p className="text-lg leading-relaxed text-foreground">
              {QUESTIONS[currentQuestion]}
            </p>
          </CardContent>
        </Card>

        <div className="flex justify-center">
          <TimerRing seconds={timeLeft} maxSeconds={300} size={140} />
        </div>

        <Card className="rounded-2xl shadow-sm">
          <CardContent className="p-6">
            <textarea
              className="h-40 w-full rounded-lg border border-input bg-background px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary focus:ring-2 focus:ring-ring/20"
              placeholder="Type your answer here..."
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
            />
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button
            size="lg"
            disabled={!transcript.trim() || submitting}
            onClick={handleSubmit}
          >
            {submitting ? (
              "Submitting..."
            ) : currentQuestion < QUESTIONS.length - 1 ? (
              <>
                Next Question <ChevronRight className="ml-2 h-4 w-4" />
              </>
            ) : (
              <>
                Finish Interview <Send className="ml-2 h-4 w-4" />
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
