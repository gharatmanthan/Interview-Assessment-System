"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent } from "@/components/ui/card"

export default function CandidateEntryPage() {
  const router = useRouter()
  const [code, setCode] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleValidate() {
    if (!code.trim()) return
    setLoading(true)
    setError("")
    try {
      const res = await api.validateInviteCode(code.trim())
      if (res.valid && res.candidate && res.job) {
        sessionStorage.setItem("candidate", JSON.stringify(res.candidate))
        sessionStorage.setItem("candidate_job", JSON.stringify(res.job))
        if (res.interview_token) {
          sessionStorage.setItem("interview_token", res.interview_token)
        }
        router.push("/candidate/consent")
      } else {
        setError(res.message || "Invalid invite code")
      }
    } catch (err: any) {
      setError("Unable to connect. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="rounded-2xl shadow-lg">
      <CardContent className="p-8">
        <div className="text-center mb-8">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground font-bold text-xl">
            IQ
          </div>
          <h1 className="mt-4 text-2xl font-bold text-foreground">Welcome</h1>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            Enter your invite code to begin the interview
          </p>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="invite-code">Invite Code</Label>
            <Input
              id="invite-code"
              value={code}
              onChange={(e) => { setCode(e.target.value); setError("") }}
              placeholder="e.g. abc123"
              className="text-center font-mono text-lg tracking-widest"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleValidate()}
            />
          </div>

          {error && (
            <p className="text-sm text-destructive text-center">{error}</p>
          )}

          <Button
            className="w-full"
            size="lg"
            disabled={!code.trim() || loading}
            onClick={handleValidate}
          >
            {loading ? "Verifying..." : "Continue"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
