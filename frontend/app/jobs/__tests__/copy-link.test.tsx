import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

const apiMock = vi.hoisted(() => ({
  getJobs: vi.fn(),
  getGmailStatus: vi.fn(),
  getSettings: vi.fn(),
  getPollLogs: vi.fn(),
  createJob: vi.fn(),
  updateJob: vi.fn(),
  deleteJob: vi.fn(),
  checkEmailApplications: vi.fn(),
}))
vi.mock("@/lib/api", () => ({ api: apiMock }))

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock("sonner", () => ({ toast: toastMock }))

import JobsPage from "../page"

const writeTextMock = vi.fn()
beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: writeTextMock },
    configurable: true,
  })
})

function makeJob(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    job_id: "abc123",
    title: "Java Developer",
    description: "Build backend services in Java.",
    required_skills: ["Java", "Spring"],
    experience_level: "Senior",
    department: "Software/CS",
    num_rounds: 4,
    time_limit_seconds: 300,
    adaptive_difficulty: true,
    competency_weights: { dsa: 20, system_design: 20, communication: 20, domain_knowledge: 20, problem_solving: 20 },
    screening_threshold: 60,
    application_gmail_label: "",
    ...overrides,
  }
}

async function renderJobs() {
  render(<JobsPage />)
  await waitFor(() => {
    expect(screen.getByText("Java Developer")).toBeInTheDocument()
  })
}

describe("Copy Application Link", () => {
  beforeEach(() => {
    apiMock.getJobs.mockResolvedValue([makeJob()])
    apiMock.getGmailStatus.mockResolvedValue({ connected: false })
    apiMock.getSettings.mockResolvedValue({ backend_mode: "local" })
    apiMock.getPollLogs.mockResolvedValue({ logs: [] })
    writeTextMock.mockResolvedValue(undefined)
  })

  it("copies a full application link built from the backend job_id", async () => {
    await renderJobs()

    await userEvent.click(screen.getByTitle("Copy application link"))

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith("http://localhost:3000/apply?jobId=abc123")
    })
  })

  it("never copies a blank application link when the job id is missing", async () => {
    apiMock.getJobs.mockResolvedValue([makeJob({ job_id: "" })])
    await renderJobs()

    await userEvent.click(screen.getByTitle("Copy application link"))

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith("Unable to create application link: job ID is missing.")
    })
    expect(writeTextMock).not.toHaveBeenCalled()
  })

  it("keeps distinct job ids per row (no accidental first-job reuse)", async () => {
    apiMock.getJobs.mockResolvedValue([
      makeJob({ job_id: "AAA", title: "Job A" }),
      makeJob({ job_id: "BBB", title: "Job B" }),
    ])
    render(<JobsPage />)
    await waitFor(() => {
      expect(screen.getByText("Job A")).toBeInTheDocument()
      expect(screen.getByText("Job B")).toBeInTheDocument()
    })

    const copyButtons = screen.getAllByTitle("Copy application link")
    await userEvent.click(copyButtons[1])

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith("http://localhost:3000/apply?jobId=BBB")
    })
  })
})