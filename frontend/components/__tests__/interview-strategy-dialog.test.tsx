import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import InterviewStrategyDialog from "../interview-strategy-dialog"

const apiMock = vi.hoisted(() => ({
  getJobInterviewModeStatus: vi.fn(),
  confirmJobInterviewMode: vi.fn(),
}))
vi.mock("@/lib/api", () => ({ api: apiMock }))

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))
vi.mock("sonner", () => ({ toast: toastMock }))

function makeStatus(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    job_id: "abc123",
    screening_pending: 0,
    shortlisted: 4,
    cohort_finalized: true,
    recommended_strategy: "MODE_1_ONLY",
    interview_strategy: "AUTO",
    strategy_confirmed: false,
    strategy_confirmed_at: null,
    cohort_finalized_at: null,
    interview_capacity: 6,
    ...overrides,
  }
}

function renderDialog() {
  render(
    <InterviewStrategyDialog
      jobId="abc123"
      jobTitle="Java Developer"
      open
      onOpenChange={() => {}}
      onConfirmed={() => {}}
    />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("Interview Strategy Dialog", () => {
  it("shows a confirmed strategy banner after confirmation", async () => {
    apiMock.getJobInterviewModeStatus.mockResolvedValue(
      makeStatus({ recommended_strategy: "MODE_1_ONLY", interview_strategy: "MODE_1_ONLY", strategy_confirmed: true })
    )
    renderDialog()
    await waitFor(() => {
      expect(screen.getByText("Interview strategy confirmed")).toBeInTheDocument()
    })
  })

  it("recommends Mode 1 when the shortlist is within live capacity and lets the recruiter confirm", async () => {
    apiMock.getJobInterviewModeStatus.mockResolvedValue(
      makeStatus({ recommended_strategy: "MODE_1_ONLY", interview_strategy: "AUTO", shortlisted: 4 })
    )
    apiMock.confirmJobInterviewMode.mockResolvedValue(
      makeStatus({ recommended_strategy: "MODE_1_ONLY", interview_strategy: "MODE_1_ONLY", strategy_confirmed: true })
    )
    renderDialog()
    await waitFor(() => {
      expect(screen.getAllByText("Mode 1 Only").length).toBeGreaterThan(0)
    })
    // Default selection is Automatic, which makes the backend apply its Mode 1 recommendation.
    await userEvent.click(screen.getByRole("button", { name: /Confirm Strategy/i }))
    await waitFor(() => {
      expect(apiMock.confirmJobInterviewMode).toHaveBeenCalledWith("abc123", { strategy: "AUTO" })
      expect(screen.getByText("Interview strategy confirmed")).toBeInTheDocument()
    })
  })

  it("recommends Mode 2 → Top 6 Mode 1 when the shortlist exceeds live capacity", async () => {
    apiMock.getJobInterviewModeStatus.mockResolvedValue(
      makeStatus({ recommended_strategy: "MODE_2_THEN_MODE_1", shortlisted: 30 })
    )
    renderDialog()
    await waitFor(() => {
      // Both the recommendation badge and the recommended option carry this label.
      expect(screen.getAllByText("Mode 2 → Top 6 Mode 1").length).toBeGreaterThan(0)
    })
    expect(screen.getByText("30")).toBeInTheDocument()
  })

  it("lets the recruiter select Mode 1 Only and confirms that explicit strategy", async () => {
    apiMock.getJobInterviewModeStatus.mockResolvedValue(makeStatus({ recommended_strategy: "AUTO", shortlisted: 4 }))
    apiMock.confirmJobInterviewMode.mockResolvedValue(
      makeStatus({ recommended_strategy: "AUTO", interview_strategy: "MODE_1_ONLY", strategy_confirmed: true })
    )
    renderDialog()
    await waitFor(() => {
      expect(screen.getByText("Mode 1 Only", { selector: "span" })).toBeInTheDocument()
    })
    await userEvent.click(screen.getByText("Mode 1 Only", { selector: "span" }))
    await userEvent.click(screen.getByRole("button", { name: /Confirm Strategy/i }))
    await waitFor(() => {
      expect(apiMock.confirmJobInterviewMode).toHaveBeenCalledWith("abc123", { strategy: "MODE_1_ONLY" })
    })
  })

  it("lets the recruiter select Mode 2 → Top 6 Mode 1 and confirms that explicit strategy", async () => {
    apiMock.getJobInterviewModeStatus.mockResolvedValue(makeStatus({ recommended_strategy: "AUTO", shortlisted: 4 }))
    apiMock.confirmJobInterviewMode.mockResolvedValue(
      makeStatus({ recommended_strategy: "AUTO", interview_strategy: "MODE_2_THEN_MODE_1", strategy_confirmed: true })
    )
    renderDialog()
    await waitFor(() => {
      expect(screen.getByText("Mode 2 → Top 6 Mode 1")).toBeInTheDocument()
    })
    await userEvent.click(screen.getByText("Mode 2 → Top 6 Mode 1"))
    await userEvent.click(screen.getByRole("button", { name: /Confirm Strategy/i }))
    await waitFor(() => {
      expect(apiMock.confirmJobInterviewMode).toHaveBeenCalledWith("abc123", { strategy: "MODE_2_THEN_MODE_1" })
    })
  })

  it("blocks confirmation while screening is still in progress", async () => {
    apiMock.getJobInterviewModeStatus.mockResolvedValue(
      makeStatus({ screening_pending: 5, cohort_finalized: false, shortlisted: 3 })
    )
    renderDialog()
    await waitFor(() => {
      expect(getConfirmButton()?.disabled).toBe(true)
    })
    expect(screen.getAllByText(/Screening in progress/).length).toBeGreaterThan(0)
  })

  it("disables confirmation when a strategy is already confirmed (frozen)", async () => {
    apiMock.getJobInterviewModeStatus.mockResolvedValue(
      makeStatus({ interview_strategy: "MODE_1_ONLY", strategy_confirmed: true })
    )
    renderDialog()
    await waitFor(() => {
      expect(screen.getByText("Interview strategy confirmed")).toBeInTheDocument()
    })
    expect(screen.queryByRole("button", { name: /Confirm Strategy/i })).not.toBeInTheDocument()
  })

  it("shows an error and keeps the dialog usable when the status request fails", async () => {
    apiMock.getJobInterviewModeStatus.mockRejectedValue(new Error("network down"))
    renderDialog()
    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith("network down")
    })
  })

  it("shows an error when strategy confirmation fails", async () => {
    apiMock.getJobInterviewModeStatus.mockResolvedValue(makeStatus({ recommended_strategy: "MODE_1_ONLY", shortlisted: 4 }))
    apiMock.confirmJobInterviewMode.mockRejectedValue(new Error("backend rejected"))
    renderDialog()
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Confirm Strategy/i })).toBeInTheDocument()
    })
    await userEvent.click(screen.getByRole("button", { name: /Confirm Strategy/i }))
    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith("backend rejected")
    })
  })
})

function getConfirmButton(): HTMLButtonElement | null {
  const buttons = screen.getAllByRole("button")
  const btn = buttons.find((b) => /Confirm Strategy/i.test(b.textContent || ""))
  return btn instanceof HTMLButtonElement ? btn : null
}