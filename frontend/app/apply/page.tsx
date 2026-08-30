"use client"

import { useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Briefcase, CheckCircle, AlertCircle } from "lucide-react"
import { getBaseUrl } from "@/lib/api"

interface PublicJob {
  job_id: string
  title: string
  description: string
  required_skills: string[]
  experience_level: string
  department: string
}

export default function ApplyPage() {
  const searchParams = useSearchParams()
  const jobId = searchParams.get("jobId") || ""

  const [job, setJob] = useState<PublicJob | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchJob() {
      if (!jobId) {
        setError("invalid-link")
        setLoading(false)
        return
      }
      try {
        const base = await getBaseUrl()
        const res = await fetch(`${base}/api/public/jobs/${jobId}`)
        if (!res.ok) throw new Error("not-found")
        setJob(await res.json())
      } catch (err: any) {
        setError(err.message === "not-found" ? "not-found" : err.message || "not-found")
      } finally {
        setLoading(false)
      }
    }
    fetchJob()
  }, [jobId])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const base = await getBaseUrl()
      const formData = new FormData()
      formData.append("name", name)
      formData.append("email", email)
      formData.append("resume", file)
      const res = await fetch(`${base}/api/public/apply/${jobId}`, {
        method: "POST",
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || "Application failed")
      }
      setSubmitted(true)
    } catch (err: any) {
      setSubmitError(err.message || "Failed to submit application")
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <p className="text-muted-foreground text-sm">Loading...</p>
      </div>
    )
  }

  if (error && !job) {
    const isInvalidLink = error === "invalid-link"
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <Card className="w-full max-w-md">
          <CardContent className="pt-6 text-center">
            <AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
            <p className="text-lg font-medium text-foreground">{isInvalidLink ? "Invalid Application Link" : "Job Not Found"}</p>
            <p className="text-sm text-muted-foreground mt-1">
              {isInvalidLink ? "This link is missing a job ID. Check the link or contact the recruiter." : "The job you're looking for doesn't exist or has been removed."}
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (submitted) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <Card className="w-full max-w-md">
          <CardContent className="pt-6 text-center">
            <CheckCircle className="h-12 w-12 text-green-600 mx-auto mb-4" />
            <p className="text-lg font-medium text-foreground">Application Submitted</p>
            <p className="text-sm text-muted-foreground mt-2">
              Thanks for applying! We&apos;ll be in touch by email if you&apos;re shortlisted for an interview.
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-background px-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <div className="flex items-center gap-2 mb-2">
            <Briefcase className="h-5 w-5 text-primary" />
            <span className="text-sm text-muted-foreground">InterviewIQ</span>
          </div>
          <CardTitle className="text-xl">{job?.title}</CardTitle>
          <p className="text-sm text-muted-foreground">{job?.department} · {job?.experience_level}</p>
        </CardHeader>
        <CardContent>
          <div className="mb-4">
            <p className="text-sm text-muted-foreground mb-2 whitespace-pre-line">{job?.description}</p>
            <div className="flex flex-wrap gap-1.5">
              {job?.required_skills.map((skill) => (
                <Badge key={skill} variant="secondary" className="text-xs">{skill}</Badge>
              ))}
            </div>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Full Name</Label>
              <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@example.com" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="resume">Resume (PDF, DOCX, or TXT)</Label>
              <Input id="resume" type="file" required accept=".pdf,.docx,.txt"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
            {submitError && (
              <p className="text-sm text-destructive">{submitError}</p>
            )}
            <Button type="submit" className="w-full" disabled={submitting || !file}>
              {submitting ? "Submitting..." : "Submit Application"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}