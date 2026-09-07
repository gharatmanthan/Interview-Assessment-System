"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { connectCandidateLive } from "@/lib/live"
import type { LiveConnection } from "@/lib/live"
import { runLocalScan } from "@/lib/integrity"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { TimerRing } from "@/components/timer-ring"
import { Video, Send, ChevronRight, Mic, MicOff, RotateCcw, Loader2, Wifi, WifiOff } from "lucide-react"
import type { QuestionItem, LiveServerMessage } from "@/lib/types"

const INTEGRITY_POLL_MS = 30000
const LIVE_FRAME_INTERVAL_MS = 1500
const FACE_CHECK_INTERVAL_MS = 15000
const PROGRESS_KEY = "candidate_question_progress"

// WebSocket reconnection constants
const WS_RECONNECT_BASE_MS = 1000
const WS_RECONNECT_MAX_MS = 30000
const WS_RECONNECT_JITTER = 0.3

type RecState = "idle" | "recording" | "uploading" | "transcribing" | "transcript_ready" | "error"
type LoadState = "loading" | "ready" | "error"

export default function CandidateInterviewPage() {
  const router = useRouter()
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reportedFlagsRef = useRef<Set<string>>(new Set())
  const frameTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const faceCheckTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const liveWsRef = useRef<LiveConnection | null>(null)
  const answeredRef = useRef(false)
  const liveConnectedRef = useRef(false)
  const faceCheckAbortRef = useRef<AbortController | null>(null)
  const framePushAbortRef = useRef<AbortController | null>(null)
  const wsReconnectAttemptRef = useRef(0)
  const cameraDisconnectedRef = useRef(false)
  const micDisconnectedRef = useRef(false)

  const [sessionStarted, setSessionStarted] = useState(false)
  const [questions, setQuestions] = useState<QuestionItem[]>([])
  const [loadState, setLoadState] = useState<LoadState>("loading")
  const [currentQuestion, setCurrentQuestion] = useState(0)
  const [timeLeft, setTimeLeft] = useState(300)
  const [recState, setRecState] = useState<RecState>("idle")
  const [transcript, setTranscript] = useState("")
  const [typedAnswer, setTypedAnswer] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [cameraActive, setCameraActive] = useState(false)
  const [errorMsg, setErrorMsg] = useState("")
  const [liveConnected, setLiveConnected] = useState(false)
  const [liveRecruiterOnline, setLiveRecruiterOnline] = useState(false)

  const candidate = typeof window !== "undefined" ? JSON.parse(sessionStorage.getItem("candidate") || "null") : null
  const job = typeof window !== "undefined" ? JSON.parse(sessionStorage.getItem("candidate_job") || "null") : null
  const interviewToken = typeof window !== "undefined" ? sessionStorage.getItem("interview_token") || "" : ""
  const sessionId = typeof window !== "undefined" ? sessionStorage.getItem("session_id") : null

  const currentItem = questions[currentQuestion]
  // question_id (and category) now come from the locked backend question set.
  const questionId = currentItem?.question_id ?? ""
  const category = currentItem?.category ?? "Technical Knowledge"
  const canSubmit = (transcript.trim() || typedAnswer.trim()) && !submitting && recState !== "recording" && recState !== "uploading" && recState !== "transcribing"

  const questionsRef = useRef<QuestionItem[]>([])
  useEffect(() => { questionsRef.current = questions }, [questions])

  // Server-authoritative position recovery (Phase 3B). The current question is
  // the first locked question without a competency score — derived from the
  // backend, not from browser sessionStorage — so a refresh / reconnect always
  // restores the true position. sessionStorage is kept only as a coarse cache.
  const applyServerProgress = useCallback((id: string | null | undefined) => {
    if (id) {
      const idx = questionsRef.current.findIndex((q) => q.question_id === id)
      if (idx >= 0) {
        setCurrentQuestion(idx)
        setTimeLeft(300)
        setRecState("idle")
        if (typeof window !== "undefined") {
          window.sessionStorage.setItem(PROGRESS_KEY, String(idx))
        }
        return
      }
    }
    // No server current question: fall back to first unanswered in the loaded
    // set, then to the stored index, then question 0.
    let idx = 0
    if (typeof window !== "undefined") {
      const saved = window.sessionStorage.getItem(PROGRESS_KEY)
      const stored = saved !== null ? parseInt(saved, 10) : NaN
      if (Number.isFinite(stored) && stored > 0) idx = stored
    }
    setCurrentQuestion(idx)
    setTimeLeft(300)
  }, [])

  const restoreProgress = useCallback(() => {
    if (typeof window === "undefined") return
    applyServerProgress(null)
  }, [applyServerProgress])

  // Live connection to the shared interview session. The server authenticates
  // this candidate from the interview token and routes recruiter events here.
  const connectLive = useCallback(() => {
    if (!sessionId) return () => {}
    let disposed = false
    let liveConn: LiveConnection | null = null
    
    connectCandidateLive(
      { interviewToken, sessionId },
      {
        onOpen: () => {
          if (!disposed) {
            setLiveConnected(true)
            liveConnectedRef.current = true
          }
        },
        onClose: () => {
          setLiveConnected(false)
          liveConnectedRef.current = false
        },
        onError: (err) => {
          console.warn("Live WS error:", err)
        },
        onReconnecting: (attempt, delay) => {
          console.log(`Reconnecting to live server (attempt ${attempt}, delay ${Math.round(delay)}ms)`)
          setErrorMsg(`Reconnecting... (attempt ${attempt})`)
        },
        onMessage: (msg: LiveServerMessage) => {
          setErrorMsg("") // Clear reconnecting message on successful message
          switch (msg.type) {
            case "joined": {
              setLiveConnected(true)
              setLiveRecruiterOnline((msg.connections?.recruiter ?? 0) > 0)
              if (msg.current_question) {
                const idx = questionsRef.current.findIndex(
                  (q) => q.question_id === msg.current_question?.question_id
                )
                if (idx >= 0) {
                  setCurrentQuestion(idx)
                  setTimeLeft(300)
                  setRecState("idle")
                }
              }
              break
            }
            case "question_asked": {
              // Recruiter asked a question -> jump straight to it.
              const idx = questionsRef.current.findIndex(
                (q) => q.question_id === msg.question?.question_id
              )
              if (idx >= 0) {
                setCurrentQuestion(idx)
                answeredRef.current = false
                setTimeLeft(300)
                setRecState("idle")
                setTranscript("")
                setTypedAnswer("")
              }
              break
            }
            case "connection_status": {
              setLiveRecruiterOnline((msg.recruiter ?? 0) > 0)
              break
            }
            case "interview_ended": {
              toast.info("The interviewer has ended this interview.")
              setLiveConnected(false)
              liveConnectedRef.current = false
              break
            }
            default:
              break
          }
        },
      }
    ).then((conn) => {
      liveConn = conn
      liveWsRef.current = conn
      if (disposed) conn.close()
    })
    return () => {
      disposed = true
      liveConn?.close()
      liveConn = null
      liveWsRef.current = null
    }
  }, [sessionId, interviewToken])

  useEffect(() => {
    if (!candidate || !job || !sessionId) {
      router.push("/candidate/entry")
      return
    }
    const disconnectLive = connectLive()
    async function init() {
      try {
        await api.startCandidateSession(sessionId!, candidate.candidate_id, job.job_id, interviewToken)
      } catch {
        toast.error("Failed to start session")
      }

      // Load the locked question set from the backend.
      try {
        const res = await api.getCandidateQuestions()
        setQuestions(res.questions)
        questionsRef.current = res.questions
        setLoadState("ready")
      } catch (err: any) {
        setLoadState("error")
        setErrorMsg(
          (err?.message ?? "").includes("404")
            ? "No questions have been prepared for this interview yet. Please wait for the recruiter."
            : "Failed to load interview questions. Please try again."
        )
      }

      // Server-authoritative recovery: jump straight to the first unanswered
      // question (or the finish page if the interview already completed).
      if (sessionId) {
        try {
          const prog = await api.getCandidateProgress()
          if (prog.completed || prog.interview_status === "completed") {
            streamRef.current?.getTracks().forEach((t) => t.stop())
            router.push("/candidate/done")
            return
          }
          applyServerProgress(prog.current_question?.question_id)
        } catch {
          restoreProgress()
        }
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
        streamRef.current = stream
        
        // Detect camera/mic disconnect during interview
        const videoTrack = stream.getVideoTracks()[0]
        const audioTrack = stream.getAudioTracks()[0]
        
        if (videoTrack) {
          videoTrack.addEventListener("ended", () => {
            cameraDisconnectedRef.current = true
            setCameraActive(false)
            setErrorMsg("Camera disconnected. Please reconnect your camera.")
            toast.warning("Camera disconnected")
          })
        }
        
        if (audioTrack) {
          audioTrack.addEventListener("ended", () => {
            micDisconnectedRef.current = true
            setErrorMsg("Microphone disconnected. Please reconnect your microphone.")
            toast.warning("Microphone disconnected")
          })
        }
        
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          setCameraActive(true)
        }
      } catch {
        setCameraActive(false)
      }

      pollRef.current = setInterval(() => {
        pollIntegrityOnce(sessionId!).catch(() => {})
      }, INTEGRITY_POLL_MS)

      frameTimerRef.current = setInterval(() => {
        pushLiveFrame(sessionId!).catch(() => {})
      }, LIVE_FRAME_INTERVAL_MS)

      faceCheckTimerRef.current = setInterval(() => {
        runFaceCheck(sessionId!).catch(() => {})
      }, FACE_CHECK_INTERVAL_MS)
    }
    init()
    return () => {
      disconnectLive()
      if (pollRef.current) clearInterval(pollRef.current)
      if (frameTimerRef.current) clearInterval(frameTimerRef.current)
      if (faceCheckTimerRef.current) clearInterval(faceCheckTimerRef.current)
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.stop()
      }
    }
  }, [])

  async function pushLiveFrame(sid: string) {
    const video = videoRef.current
    if (!video || video.readyState < 2 || !video.videoWidth) return
    
    // Cancel any in-flight frame push to prevent queue buildup
    framePushAbortRef.current?.abort()
    const controller = new AbortController()
    framePushAbortRef.current = controller
    
    const canvas = document.createElement("canvas")
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext("2d")?.drawImage(video, 0, 0)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.6)
    )
    if (blob && !controller.signal.aborted) {
      await api.uploadLiveFrame(sid, blob)
    }
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

  async function runFaceCheck(sid: string) {
    if (!videoRef.current || videoRef.current.readyState < 2 || !videoRef.current.videoWidth) return
    
    // Cancel any in-flight face check to prevent overlap
    faceCheckAbortRef.current?.abort()
    const controller = new AbortController()
    faceCheckAbortRef.current = controller
    
    const canvas = document.createElement("canvas")
    canvas.width = videoRef.current.videoWidth
    canvas.height = videoRef.current.videoHeight
    canvas.getContext("2d")?.drawImage(videoRef.current, 0, 0)
    const frameBase64 = canvas.toDataURL("image/jpeg", 0.6).split(",")[1]
    if (!frameBase64) return
    try {
      const res = await api.faceCheck(frameBase64, interviewToken)
      if (controller.signal.aborted) return
      
      if (res.flag_type && res.severity) {
        const detail = res.message
        const key = `${res.flag_type}:${detail}`
        if (!reportedFlagsRef.current.has(key)) {
          reportedFlagsRef.current.add(key)
          await api.postIntegrityFlags([{
            session_id: sid,
            flag_type: res.flag_type,
            detail,
            severity: res.severity,
          }])
        }
      }
    } catch (err: any) {
      if (err.name === "AbortError") return
      // Face check failed silently - don't interrupt interview
    }
  }

  useEffect(() => {
    if (recState !== "recording" || timeLeft <= 0) return
    const timer = setInterval(() => {
      setTimeLeft((t) => {
        if (t <= 1) {
          handleStopRecording()
          return 0
        }
        return t - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [recState, currentQuestion])

  function startQuestionRecording() {
    if (!streamRef.current) {
      setErrorMsg("Microphone not available. Please type your answer.")
      return
    }
    try {
      if (typeof MediaRecorder === "undefined") {
        setErrorMsg("Recording not supported in this browser. Please type your answer.")
        return
      }
      const mimeCandidates = ["audio/webm;codecs=opus", "audio/webm", "video/webm;codecs=vp8,opus", "video/webm"]
      const mimeType = mimeCandidates.find((m) => MediaRecorder.isTypeSupported(m))
      const recorder = new MediaRecorder(streamRef.current, mimeType ? { mimeType } : undefined)
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.start(1000)
      recorderRef.current = recorder
      setRecState("recording")
      setErrorMsg("")
      if (liveWsRef.current?.ws.readyState === WebSocket.OPEN) {
        liveWsRef.current.ws.send(JSON.stringify({ type: "answer_started" }))
      }
    } catch {
      setErrorMsg("Could not start recording. Please type your answer.")
    }
  }

  function handleStopRecording() {
    const recorder = recorderRef.current
    if (!recorder || recorder.state === "inactive") {
      setRecState("idle")
      return
    }
    recorder.onstop = () => {
      const blob = chunksRef.current.length > 0
        ? new Blob(chunksRef.current, { type: chunksRef.current[0].type })
        : null
      if (blob && sessionId && questionId) {
        uploadAndTranscribe(blob)
      } else {
        setRecState("idle")
      }
    }
    recorder.stop()
    recorderRef.current = null
  }

  async function uploadAndTranscribe(audioBlob: Blob) {
    if (!sessionId || !questionId) return
    setRecState("uploading")
    try {
      setRecState("transcribing")
      const result = await api.transcribeSession(sessionId, questionId, audioBlob)
      setTranscript(result.transcript)
      setRecState("transcript_ready")
      // Notify the live interviewer that this answer's transcript is ready.
      if (liveWsRef.current?.ws.readyState === WebSocket.OPEN) {
        liveWsRef.current.ws.send(JSON.stringify({ type: "answer_completed" }))
      }
    } catch (err: any) {
      const msg = err?.message || "Transcription failed"
      if (msg.includes("422")) {
        setErrorMsg("Transcription was empty. Please try recording again.")
      } else if (msg.includes("500")) {
        setErrorMsg("Transcription service error. Please try again.")
      } else {
        setErrorMsg("Transcription failed. Please try again.")
      }
      setRecState("error")
    }
  }

  async function handleSubmit() {
    if (!sessionId || !questionId || submitting) return
    setSubmitting(true)
    try {
      const answerText = transcript.trim() || typedAnswer.trim()
      if (answerText) {
        await api.submitAnswer(
          sessionId,
          questionId,
          category,
          answerText
        )
      }
      setTranscript("")
      setTypedAnswer("")
      setRecState("idle")
      setErrorMsg("")

      const next = currentQuestion + 1
      if (next < questions.length) {
        setCurrentQuestion(next)
        setTimeLeft(300)
        if (typeof window !== "undefined") {
          window.sessionStorage.setItem(PROGRESS_KEY, String(next))
        }
      } else {
        if (frameTimerRef.current) clearInterval(frameTimerRef.current)
        frameTimerRef.current = null
        streamRef.current?.getTracks().forEach((t) => t.stop())
        if (typeof window !== "undefined") {
          window.sessionStorage.removeItem(PROGRESS_KEY)
        }
        await api.completeCandidateSession(sessionId)
        router.push("/candidate/done")
      }
    } catch (err) {
      toast.error("Failed to submit. Please try again.")
    } finally {
      setSubmitting(false)
    }
  }

  if (!candidate || !job) return null

  if (loadState === "loading") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Loading your interview questions...</p>
      </div>
    )
  }

  if (loadState === "error") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-6">
        <p className="text-center text-sm text-destructive">{errorMsg}</p>
        <Button variant="outline" onClick={() => router.back()}>Go Back</Button>
      </div>
    )
  }

  return (
    <div className="-mx-4 min-h-screen bg-background p-4 md:-mx-8 md:p-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-foreground">{job.title}</h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Question {currentQuestion + 1} of {questions.length}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 rounded-full border border-input px-2.5 py-1 text-xs text-muted-foreground">
              {liveConnected
                ? liveRecruiterOnline
                  ? <><Wifi className="h-3 w-3 text-success" /><span>Interviewer online</span></>
                  : <><span className="h-2 w-2 rounded-full bg-warning" /><span>Waiting for interviewer</span></>
                : <><WifiOff className="h-3 w-3 text-destructive" /><span>Offline</span></>}
            </div>
            {recState === "recording" && (
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 animate-pulse rounded-full bg-destructive" />
                <span className="text-xs text-muted-foreground">Recording</span>
              </div>
            )}
            {recState === "uploading" && (
              <span className="text-xs text-muted-foreground">Uploading...</span>
            )}
            {recState === "transcribing" && (
              <span className="text-xs text-muted-foreground">Transcribing...</span>
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
            <div className="mb-3 flex items-center gap-2">
              <span className="rounded-full border border-input px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                {currentItem?.category ?? "Interview"}
              </span>
              <span className="rounded-full border border-input px-2.5 py-0.5 text-xs font-medium text-muted-foreground capitalize">
                {currentItem?.difficulty ?? "medium"}
              </span>
            </div>
            <p className="text-lg leading-relaxed text-foreground">
              {currentItem?.question_text ?? ""}
            </p>
          </CardContent>
        </Card>

        <div className="flex justify-center">
          <TimerRing seconds={timeLeft} maxSeconds={300} size={140} />
        </div>

        <Card className="rounded-2xl shadow-sm">
          <CardContent className="space-y-4 p-6">
            {recState === "idle" && !transcript && (
              <div className="flex flex-col items-center gap-3 py-4">
                <p className="text-sm text-muted-foreground">
                  Click to start recording your answer, or type below.
                </p>
                <Button
                  variant="outline"
                  size="lg"
                  onClick={startQuestionRecording}
                  className="gap-2"
                >
                  <Mic className="h-5 w-5" />
                  Start Recording
                </Button>
              </div>
            )}

            {recState === "recording" && (
              <div className="flex flex-col items-center gap-3 py-4">
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 animate-pulse rounded-full bg-destructive" />
                  <span className="text-sm font-medium text-foreground">Recording your answer...</span>
                </div>
                <Button
                  variant="destructive"
                  size="lg"
                  onClick={handleStopRecording}
                  className="gap-2"
                >
                  <MicOff className="h-5 w-5" />
                  Stop Answer
                </Button>
              </div>
            )}

            {recState === "uploading" && (
              <div className="flex flex-col items-center gap-2 py-4">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                <span className="text-sm text-muted-foreground">Uploading audio...</span>
              </div>
            )}

            {recState === "transcribing" && (
              <div className="flex flex-col items-center gap-2 py-4">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                <span className="text-sm text-muted-foreground">Transcribing your answer...</span>
              </div>
            )}

            {(recState === "transcript_ready" || recState === "error") && transcript && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">Transcript</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setTranscript("")
                      setRecState("idle")
                    }}
                    className="gap-1 text-xs"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Re-record
                  </Button>
                </div>
                <div className="rounded-lg border border-input bg-muted/50 p-4">
                  <p className="text-sm leading-relaxed text-foreground">{transcript}</p>
                </div>
              </div>
            )}

            {recState === "error" && !transcript && (
              <div className="space-y-3 py-2">
                <p className="text-sm text-destructive">{errorMsg}</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setRecState("idle")
                    setErrorMsg("")
                  }}
                  className="gap-1"
                >
                  <RotateCcw className="h-3 w-3" />
                  Try Again
                </Button>
              </div>
            )}

            <div className="pt-2">
              <textarea
                className="h-28 w-full rounded-lg border border-input bg-background px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary focus:ring-2 focus:ring-ring/20"
                placeholder="Type your answer here (or use recording above)..."
                value={typedAnswer}
                onChange={(e) => setTypedAnswer(e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button
            size="lg"
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {submitting ? (
              "Submitting..."
            ) : currentQuestion < questions.length - 1 ? (
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
