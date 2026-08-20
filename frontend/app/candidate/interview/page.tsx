"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { api } from "@/lib/api"
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

export default function CandidateInterviewPage() {
  const router = useRouter()
  const videoRef = useRef<HTMLVideoElement>(null)

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

  useEffect(() => {
    if (!candidate || !job || !sessionId) {
      router.push("/candidate/entry")
      return
    }
    async function init() {
      try {
        await api.startCandidateSession(sessionId!, candidate.candidate_id, job.job_id)
        setSessionStarted(true)
      } catch {
        toast.error("Failed to start session")
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          setCameraActive(true)
        }
        setRecording(true)
      } catch {
        setCameraActive(false)
      }
    }
    init()
  }, [])

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

  return (
    <div className="-mx-4 min-h-screen bg-slate-50 p-4 md:-mx-8 md:p-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-slate-900">{job.title}</h1>
            <p className="text-sm text-slate-500">
              Question {currentQuestion + 1} of {QUESTIONS.length}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {recording && (
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
                <span className="text-xs text-slate-500">Recording</span>
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
              <div className="flex h-full items-center justify-center bg-slate-900 text-white/40">
                <Video className="h-6 w-6" />
              </div>
            )}
          </div>
        </div>

        <Card className="rounded-2xl border bg-white shadow-sm">
          <CardContent className="p-8">
            <p className="text-lg leading-relaxed text-slate-900">
              {QUESTIONS[currentQuestion]}
            </p>
          </CardContent>
        </Card>

        <div className="flex justify-center">
          <TimerRing seconds={timeLeft} maxSeconds={300} size={140} />
        </div>

        <Card className="rounded-2xl border bg-white shadow-sm">
          <CardContent className="p-6">
            <textarea
              className="h-40 w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
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
