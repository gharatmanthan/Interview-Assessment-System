"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { CheckCircle } from "lucide-react"

export default function CandidateDonePage() {
  const router = useRouter()

  useEffect(() => {
    sessionStorage.removeItem("candidate")
    sessionStorage.removeItem("candidate_job")
    sessionStorage.removeItem("session_id")
  }, [])

  return (
    <Card className="rounded-2xl border bg-white shadow-lg">
      <CardContent className="p-8 text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
          <CheckCircle className="h-8 w-8 text-green-600" />
        </div>

        <h1 className="text-2xl font-bold text-slate-900">Interview Complete</h1>
        <p className="mt-2 text-sm text-slate-500 max-w-sm mx-auto">
          Thank you for completing the interview. Your responses have been recorded 
          and will be reviewed by the hiring team.
        </p>

        <p className="mt-4 text-sm text-slate-500">
          The recruiter will be in touch with next steps.
        </p>

        <div className="mt-8">
          <Button
            variant="outline"
            onClick={() => router.push("/candidate/entry")}
          >
            Close
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
