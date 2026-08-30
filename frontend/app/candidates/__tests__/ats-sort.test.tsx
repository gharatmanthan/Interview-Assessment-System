import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"

const apiMock = vi.hoisted(() => ({
  getCandidates: vi.fn(),
  getJobs: vi.fn(),
  getGmailStatus: vi.fn(),
}))

vi.mock("@/lib/api", () => ({ api: apiMock }))

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock("sonner", () => ({ toast: toastMock }))

import CandidatesPage from "../page"

function makeCandidate(candidate_id: string, match_score: number | null) {
  return {
    candidate_id,
    job_id: "job-1",
    name: `Candidate ${candidate_id}`,
    email: `${candidate_id}@example.com`,
    invite_code: `code-${candidate_id}`,
    status: "invited",
    source: "apply_portal",
    screening_status: "passed_threshold",
    invite_email_sent: true,
    resume_path: null,
    resume_skills: [],
    matched_skills: [],
    missing_skills: [],
    match_score,
    screening_result: match_score == null ? null : {
      decision: "passed",
      decision_reason: "ok",
      ats_score: match_score,
      threshold_used: 60,
      matched_skills: [],
      missing_skills: [],
      hard_requirement_failures: [],
    },
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("Candidates default ATS sort", () => {
  it("renders higher match scores first regardless of API order", async () => {
    apiMock.getCandidates.mockResolvedValue([
      makeCandidate("low", 30),
      makeCandidate("high", 95),
      makeCandidate("mid", 55),
    ])
    apiMock.getJobs.mockResolvedValue([{
      job_id: "job-1", title: "Backend Engineer", department: "Software/CS",
      description: "", required_skills: [], experience_level: "Mid", num_rounds: 5,
      time_limit_seconds: 300, adaptive_difficulty: true,
      competency_weights: {}, screening_threshold: 60, application_gmail_label: "",
    }])
    apiMock.getGmailStatus.mockResolvedValue({ connected: false })

    render(<CandidatesPage />)
    await waitFor(() => {
      expect(screen.getByText("Candidate high")).toBeInTheDocument()
    })

    const rows = screen.getAllByRole("row").slice(1)
    expect(rows[0].textContent).toContain("Candidate high")
    expect(rows[1].textContent).toContain("Candidate mid")
    expect(rows[2].textContent).toContain("Candidate low")
  })

  it("keeps unscored candidates at the bottom", async () => {
    apiMock.getCandidates.mockResolvedValue([
      makeCandidate("manual", null),
      makeCandidate("scored", 88),
    ])
    apiMock.getJobs.mockResolvedValue([])
    apiMock.getGmailStatus.mockResolvedValue({ connected: false })

    render(<CandidatesPage />)
    await waitFor(() => {
      expect(screen.getByText("Candidate scored")).toBeInTheDocument()
    })

    const rows = screen.getAllByRole("row").slice(1)
    expect(rows[0].textContent).toContain("Candidate scored")
    expect(rows[1].textContent).toContain("Candidate manual")
  })
})