"use client"

import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { InterviewStrategy, JobStrategyStatus } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog"
import { Loader2, Check, RefreshCw, Users } from "lucide-react"

export const STRATEGY_OPTIONS: { value: InterviewStrategy; label: string; helper: string }[] = [
  {
    value: "AUTO",
    label: "Automatic",
    helper: "InterviewIQ picks the best mode from the finalized shortlist.",
  },
  {
    value: "MODE_1_ONLY",
    label: "Mode 1 Only",
    helper: "Every shortlisted candidate goes straight to a live Mode 1 interview.",
  },
  {
    value: "MODE_2_THEN_MODE_1",
    label: "Mode 2 → Top 6 Mode 1",
    helper: "All shortlisted candidates go through Mode 2; the top-ranked are promoted to Mode 1.",
  },
]

const STRATEGY_LABELS: Record<InterviewStrategy, string> = {
  AUTO: "Automatic",
  MODE_1_ONLY: "Mode 1 Only",
  MODE_2_THEN_MODE_1: "Mode 2 → Top 6 Mode 1",
}

interface InterviewStrategyDialogProps {
  jobId: string
  jobTitle: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirmed?: () => void
}

export default function InterviewStrategyDialog({
  jobId, jobTitle, open, onOpenChange, onConfirmed,
}: InterviewStrategyDialogProps) {
  const [status, setStatus] = useState<JobStrategyStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [selected, setSelected] = useState<InterviewStrategy>("AUTO")
  const [justConfirmed, setJustConfirmed] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const s = await api.getJobInterviewModeStatus(jobId)
      setStatus(s)
      // Once a strategy is confirmed the backend owns it; keep the radio
      // reflecting the effective strategy so the UI never drifts from the API.
      setSelected(s.interview_strategy)
    } catch (err: any) {
      toast.error(err.message || "Failed to load interview strategy")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) {
      setJustConfirmed(false)
      load()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, jobId])

  async function handleConfirm() {
    if (!status) return
    setConfirming(true)
    try {
      const updated = await api.confirmJobInterviewMode(jobId, { strategy: selected })
      setStatus(updated)
      setSelected(updated.interview_strategy)
      setJustConfirmed(true)
      toast.success("Interview strategy confirmed")
      onConfirmed?.()
    } catch (err: any) {
      toast.error(err.message || "Failed to confirm interview strategy")
    } finally {
      setConfirming(false)
    }
  }

  const screeningInProgress = status != null && status.screening_pending > 0 && !status.cohort_finalized
  const confirmDisabled =
    !status ||
    status.strategy_confirmed ||
    screeningInProgress ||
    status.shortlisted === 0

  function confirmationSummary(): string {
    if (!status) return ""
    const n = status.shortlisted
    const cap = status.interview_capacity
    const eff = status.interview_strategy
    if (eff === "MODE_2_THEN_MODE_1") {
      return `${n} candidates will proceed through Mode 2. After Mode 2 completion, the top ${cap} will be promoted to Mode 1.`
    }
    if (eff === "MODE_1_ONLY") {
      return `${n} candidates will be invited to live Mode 1 interviews.`
    }
    const rec = status.recommended_strategy
    if (rec === "MODE_2_THEN_MODE_1") {
      return `${n} candidates will proceed through Mode 2. After Mode 2 completion, the top ${cap} will be promoted to Mode 1.`
    }
    return `${n} candidates will be invited to live Mode 1 interviews.`
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Interview Strategy</DialogTitle>
          <DialogDescription>{jobTitle}</DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
          {loading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !status ? (
            <div className="rounded-lg border border-border bg-muted/40 px-4 py-6 text-center text-sm text-muted-foreground">
              No strategy status available yet.
            </div>
          ) : (
            <>
              {/* ATS shortlist + recommendation */}
              <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2.5 text-sm">
                <Users className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">ATS Shortlisted:</span>
                <span className="font-semibold text-foreground">{status.shortlisted}</span>
                {status.screening_pending > 0 && (
                  <Badge variant="warning" className="ml-auto text-xs">
                    {status.screening_pending} screening pending
                  </Badge>
                )}
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground">System Recommendation</p>
                <Badge variant="secondary" className="mt-1 text-sm">
                  {STRATEGY_LABELS[status.recommended_strategy]}
                </Badge>
              </div>

              {/* Coarse lifecycle banner */}
              <StrategyLifecycleBanner status={status} />

              {/* Selection */}
              {status.strategy_confirmed ? (
                <div className="rounded-lg border border-success bg-success/10 px-4 py-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-success-text">
                    <Check className="h-4 w-4" /> Interview strategy confirmed
                  </div>
                  <p className="mt-1 text-sm text-foreground">
                    Strategy: {STRATEGY_LABELS[status.interview_strategy]}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {confirmationSummary()}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">Choose a strategy</p>
                  {screeningInProgress ? (
                    <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                      Screening in progress — interview strategy will be available when the shortlist is finalized.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {STRATEGY_OPTIONS.map((opt) => {
                        const active = selected === opt.value
                        const recommended = status.recommended_strategy === opt.value
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => setSelected(opt.value)}
                            className={`flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                              active
                                ? "border-primary bg-primary/5"
                                : "border-border hover:bg-muted/50"
                            }`}
                          >
                            <span
                              className={`mt-0.5 flex h-4 w-4 items-center justify-center rounded-full border ${
                                active ? "border-primary" : "border-muted-foreground/40"
                              }`}
                            >
                              {active && <span className="h-2 w-2 rounded-full bg-primary" />}
                            </span>
                            <span className="min-w-0">
                              <span className="flex items-center gap-2 text-sm font-medium text-foreground">
                                {opt.label}
                                {recommended && (
                                  <Badge variant="secondary" className="text-[10px]">Recommended</Badge>
                                )}
                              </span>
                              <span className="block text-xs leading-relaxed text-muted-foreground">
                                {opt.helper}
                              </span>
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter className="items-center">
          {status?.strategy_confirmed ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Check className="h-3.5 w-3.5 text-success-text" />
              Strategy confirmed{status.shortlisted === 0 ? "" : ` · ${status.shortlisted} candidates`}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">
              Confirm to release candidate invitations for this job.
            </span>
          )}
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            </Button>
            <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
            {status && !status.strategy_confirmed && (
              <Button
                onClick={handleConfirm}
                disabled={confirmDisabled || confirming}
              >
                {confirming ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : null}
                Confirm Strategy
              </Button>
            )}
          </div>
        </DialogFooter>

        {justConfirmed && (
          <div className="rounded-lg border border-success bg-success/10 px-4 py-2 text-sm">
            <span className="font-medium text-success-text">✓ Strategy confirmed</span> · {confirmationSummary()}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function StrategyLifecycleBanner({ status }: { status: JobStrategyStatus }) {
  const { cohort_finalized, strategy_confirmed, shortlisted } = status
  if (!strategy_confirmed && status.screening_pending > 0) {
    return (
      <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        Status: Screening in progress — strategy available when the shortlist is finalized.
      </div>
    )
  }
  if (!strategy_confirmed) {
    return (
      <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        Status: {shortlisted === 0 ? "No shortlisted candidates yet" : "Cohort finalized — awaiting strategy confirmation"}
        {cohort_finalized ? "" : ""}
      </div>
    )
  }
  const eff = status.interview_strategy
  let label: string
  if (eff === "MODE_2_THEN_MODE_1") {
    label = cohort_finalized
      ? `Cohort finalized · ${shortlisted} → Mode 2. Top ${status.interview_capacity} ranked will be promoted to Mode 1 after Mode 2 completion.`
      : `Awaiting Mode 2 completion before ranking and top-${status.interview_capacity} promotion.`
  } else {
    label = `Confirmed · ${shortlisted} candidate${shortlisted === 1 ? "" : "s"} → Mode 1.`
  }
  return (
    <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
      Status: {label}
    </div>
  )
}