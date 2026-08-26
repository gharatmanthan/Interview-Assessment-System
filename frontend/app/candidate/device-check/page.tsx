"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Camera, CameraOff, Mic, CheckCircle, AlertTriangle, Loader2, ShieldAlert } from "lucide-react"
import { scanAndReport } from "@/lib/integrity"
import type { IntegrityFlag } from "@/lib/types"

export default function CandidateCheckPage() {
  const router = useRouter()
  const videoRef = useRef<HTMLVideoElement>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animFrameRef = useRef<number>(0)

  const [cameraOk, setCameraOk] = useState<boolean | null>(null)
  const [micOk, setMicOk] = useState<boolean | null>(null)
  const [micLevel, setMicLevel] = useState(0)
  const [integrityFlags, setIntegrityFlags] = useState<IntegrityFlag[]>([])
  const [integrityDone, setIntegrityDone] = useState(false)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    const c = sessionStorage.getItem("candidate")
    if (!c) {
      router.push("/candidate/entry")
      return
    }
    startDevices()
    runLocalIntegrityCheck()
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop())
      if (audioContextRef.current) audioContextRef.current.close()
      cancelAnimationFrame(animFrameRef.current)
    }
  }, [])

  async function runLocalIntegrityCheck() {
    try {
      const sessionId = sessionStorage.getItem("session_id")
      if (!sessionId) {
        setIntegrityDone(true)
        return
      }
      const flags = await scanAndReport(sessionId)
      setIntegrityFlags(flags)
    } catch {
    } finally {
      setIntegrityDone(true)
    }
  }

  async function startDevices() {
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true,
      })
      streamRef.current = mediaStream
      setCameraOk(true)

      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream
      }

      const audioCtx = new AudioContext()
      audioContextRef.current = audioCtx
      const source = audioCtx.createMediaStreamSource(mediaStream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      analyserRef.current = analyser
      setMicOk(true)

      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      function updateLevel() {
        analyser.getByteFrequencyData(dataArray)
        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length
        setMicLevel(avg / 255)
        animFrameRef.current = requestAnimationFrame(updateLevel)
      }
      updateLevel()
    } catch {
      if (cameraOk !== false) setCameraOk(false)
      if (micOk !== false) setMicOk(false)
    }
  }

  const allPassed = cameraOk === true && micOk === true

  function handleStart() {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    if (audioContextRef.current) audioContextRef.current.close()
    cancelAnimationFrame(animFrameRef.current)
    router.push("/candidate/interview")
  }

  return (
    <Card className="rounded-2xl shadow-lg">
      <CardContent className="p-8">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-foreground">Device Check</h1>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            Let's make sure your camera and microphone are working
          </p>
        </div>

        <div className="mb-6">
          <div className="relative aspect-video overflow-hidden rounded-xl bg-black">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className={`h-full w-full object-cover ${cameraOk === true ? "" : "hidden"}`}
            />
            {cameraOk !== true && (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-white/60">
                <CameraOff className="mb-2 h-12 w-12" />
                <p className="text-sm">Camera not available</p>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-3 mb-6">
          <div className="flex items-center justify-between rounded-lg border border-border p-3">
            <div className="flex items-center gap-3">
              <Camera className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm font-medium text-foreground">Camera</span>
            </div>
            {cameraOk === null ? (
              <Badge variant="outline"><Loader2 className="h-3 w-3 animate-spin mr-1" />Checking</Badge>
            ) : cameraOk ? (
              <Badge variant="success">
                <CheckCircle className="h-3 w-3 mr-1" />Working
              </Badge>
            ) : (
              <Badge variant="destructive">
                <AlertTriangle className="h-3 w-3 mr-1" />Not available
              </Badge>
            )}
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border p-3">
            <div className="flex items-center gap-3">
              <Mic className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm font-medium text-foreground">Microphone</span>
            </div>
            <div className="flex items-center gap-2">
              {micOk && (
                <div className="w-24">
                  <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary transition-all duration-100"
                      style={{ width: `${micLevel * 100}%` }}
                    />
                  </div>
                </div>
              )}
              {micOk === null ? (
                <Badge variant="outline"><Loader2 className="h-3 w-3 animate-spin mr-1" />Checking</Badge>
              ) : micOk ? (
                <Badge variant="success">
                  <CheckCircle className="h-3 w-3 mr-1" />Working
                </Badge>
              ) : (
                <Badge variant="destructive">
                  <AlertTriangle className="h-3 w-3 mr-1" />Not available
                </Badge>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-border p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <ShieldAlert className="h-5 w-5 text-muted-foreground" />
                <div>
                  <span className="text-sm font-medium text-foreground">Environment Integrity</span>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    Checked locally on your machine for remote-access tools
                  </p>
                </div>
              </div>
              {!integrityDone ? (
                <Badge variant="outline"><Loader2 className="h-3 w-3 animate-spin mr-1" />Scanning</Badge>
              ) : integrityFlags.length === 0 ? (
                <Badge variant="success">
                  <CheckCircle className="h-3 w-3 mr-1" />All clear
                </Badge>
              ) : (
                <Badge variant="destructive">
                  <AlertTriangle className="h-3 w-3 mr-1" />{integrityFlags.length} issue{integrityFlags.length > 1 ? "s" : ""} found
                </Badge>
              )}
            </div>
            {integrityFlags.length > 0 && (
              <ul className="mt-2 space-y-1 border-t border-border pt-2">
                {integrityFlags.map((flag, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-destructive">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                    {flag.detail}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <Button
          className="w-full"
          size="lg"
          disabled={!allPassed}
          onClick={handleStart}
        >
          {allPassed ? (integrityFlags.length > 0 ? "Continue Anyway" : "Start Interview") : "Please allow camera and microphone access"}
        </Button>
      </CardContent>
    </Card>
  )
}
