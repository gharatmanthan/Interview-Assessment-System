import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"

const apiMock = vi.hoisted(() => ({
  getApplications: vi.fn(),
  getJobs: vi.fn(),
  getApplicationStats: vi.fn(),
}))
vi.mock("@/lib/api", () => ({
  api: apiMock,
  mediaUrl: vi.fn().mockResolvedValue("/media/resume.pdf"),
}))

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock("sonner", () => ({ toast: toastMock }))

import ApplicationsPage from "../page"

function makeApplication(application_id: string, ats_score: number | null) {
  return {
    application_id,
    full_name: `Candidate ${application_id}`,
    email: `${application_id}@example.com`,
    job_id: "job-1",
    status: "passed",
    screening_status: "completed",
    screening_result: ats_score == null ? null : {
      decision: "passed",
      decision_reason: "ok",
      ats_score,
      threshold_used: 60,
      matched_skills: [],
      missing_skills: [],
      hard_requirement_failures: [],
    },
    resume_path: "resumes/r.pdf",
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("Applications default ATS sort", () => {
  it("renders higher ATS scores first even when the API returns them unordered", async () => {
    apiMock.getApplications.mockResolvedValue({
      applications: [
        makeApplication("a", 45),
        makeApplication("b", 82),
        makeApplication("c", 66),
      ],
    })
    apiMock.getJobs.mockResolvedValue([{
      job_id: "job-1", title: "Backend Engineer", department: "Software/CS",
      description: "", required_skills: [], experience_level: "Mid", num_rounds: 5,
      time_limit_seconds: 300, adaptive_difficulty: true,
      competency_weights: {}, screening_threshold: 60, application_gmail_label: "",
    }])
    apiMock.getApplicationStats.mockResolvedValue({ jobs: [] })

    render(<ApplicationsPage />)
    await waitFor(() => {
      expect(screen.getByText("Candidate b")).toBeInTheDocument()
    })

    const rows = screen.getAllByRole("row").slice(1)
    const scores = rows.map((r) => {
      const score = (r.textContent ?? "").match(/(\d+)%/)?.[1]
      return score ? Number(score) : null
    }).filter((s): s is number => s !== null)
    expect(scores).toEqual([82, 66, 45])
  })

  it("keeps unscored applications at the bottom", async () => {
    apiMock.getApplications.mockResolvedValue({
      applications: [
        makeApplication("unscored", null),
        makeApplication("scored", 90),
      ],
    })
    apiMock.getJobs.mockResolvedValue([])
    apiMock.getApplicationStats.mockResolvedValue({ jobs: [] })

    render(<ApplicationsPage />)
    await waitFor(() => {
      expect(screen.getByText("Candidate scored")).toBeInTheDocument()
    })

    const rows = screen.getAllByRole("row").slice(1)
    expect(rows[0].textContent).toContain("Candidate scored")
    expect(rows[1].textContent).toContain("Candidate unscored")
  })
})