"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Video, Mic, Monitor, Shield } from "lucide-react"

export default function CandidateConsentPage() {
  const router = useRouter()
  const [candidate, setCandidate] = useState<any>(null)
  const [job, setJob] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const c = sessionStorage.getItem("candidate")
    const j = sessionStorage.getItem("candidate_job")
    if (!c || !j) {
      router.push("/candidate/entry")
      return
    }
    setCandidate(JSON.parse(c))
    setJob(JSON.parse(j))
  }, [router])

  async function handleAccept() {
    if (!candidate) return
    setLoading(true)
    try {
      const sessionId = crypto.randomUUID()
      sessionStorage.setItem("session_id", sessionId)

      await api.recordConsent(sessionId, candidate.candidate_id)
      toast.success("Consent recorded")
      router.push("/candidate/device-check")
    } catch (err: any) {
      toast.error("Failed to record consent. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  if (!candidate || !job) return null

  return (
    <Card className="rounded-2xl shadow-lg">
      <CardContent className="p-8">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-foreground">Before We Begin</h1>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            Please review what happens during your interview
          </p>
        </div>

        <div className="space-y-4 mb-8">
          <h3 className="text-sm font-semibold text-foreground">
            What we collect during this interview:
          </h3>

          <div className="space-y-3">
            {[
              { icon: Video, label: "Video recording", desc: "Your webcam feed is recorded for the duration of the interview" },
              { icon: Mic, label: "Audio recording", desc: "Your responses are captured and transcribed for scoring" },
              { icon: Monitor, label: "Device integrity check", desc: "We check for remote desktop software and unusual devices to ensure interview integrity" },
              { icon: Shield, label: "AI-powered scoring", desc: "Your responses are scored by AI with explainability and bias auditing" },
            ].map(({ icon: Icon, label, desc }) => (
              <div key={label} className="flex items-start gap-3 rounded-lg border border-border p-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <Icon className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{label}</p>
                  <p className="text-xs leading-relaxed text-muted-foreground mt-0.5">{desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-lg bg-muted p-4">
            <p className="text-xs leading-relaxed text-muted-foreground">
              <strong>What we don't do:</strong> We do not access your files, browse your history,
              or monitor anything outside the interview window. The integrity check is limited to
              detecting remote desktop software and connected peripherals — nothing more.
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <Button
            className="w-full"
            size="lg"
            disabled={loading}
            onClick={handleAccept}
          >
            {loading ? "Recording consent..." : "I Agree and I'm Ready to Begin"}
          </Button>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => router.push("/candidate/entry")}
          >
            Go Back
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
