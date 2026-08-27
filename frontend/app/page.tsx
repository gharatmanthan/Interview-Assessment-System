"use client"

import { useRouter } from "next/navigation"
import { Card, CardContent } from "@/components/ui/card"
import { Briefcase, Code } from "lucide-react"

export default function Home() {
  const router = useRouter()

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
      <div className="mb-10 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground font-bold text-xl">
          IQ
        </div>
        <h1 className="mt-4 text-3xl font-bold text-foreground">InterviewIQ</h1>
        <p className="mt-2 text-sm text-muted-foreground">Who is using this device?</p>
      </div>

      <div className="grid w-full max-w-lg grid-cols-1 gap-6 sm:grid-cols-2">
        <button
          onClick={() => router.push("/login")}
          className="group"
        >
          <Card className="h-full rounded-2xl border-border transition-all hover:border-primary hover:shadow-md">
            <CardContent className="flex flex-col items-center justify-center p-8 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                <Briefcase className="h-7 w-7" />
              </div>
              <h2 className="text-lg font-bold text-foreground">I'm a Recruiter</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Create job postings, invite candidates, and review reports
              </p>
            </CardContent>
          </Card>
        </button>

        <button
          onClick={() => router.push("/candidate/entry")}
          className="group"
        >
          <Card className="h-full rounded-2xl border-border transition-all hover:border-primary hover:shadow-md">
            <CardContent className="flex flex-col items-center justify-center p-8 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                <Code className="h-7 w-7" />
              </div>
              <h2 className="text-lg font-bold text-foreground">I'm a Candidate</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Enter your invite code to start your interview
              </p>
            </CardContent>
          </Card>
        </button>
      </div>
    </div>
  )
}
