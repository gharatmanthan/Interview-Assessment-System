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
  getLinkedinStatus: vi.fn(),
  connectLinkedin: vi.fn(),
  disconnectLinkedin: vi.fn(),
  getLinkedinPreview: vi.fn(),
  publishLinkedinPost: vi.fn(),
}))
vi.mock("@/lib/api", () => ({ api: apiMock }))

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))
vi.mock("sonner", () => ({ toast: toastMock }))

import JobsPage from "../page"

const openMock = vi.fn()
beforeEach(() => {
  vi.clearAllMocks()
  globalThis.open = openMock
})

function makeJob(overrides: Record<string, unknown> = {}) {
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

function makePreview(overrides: Record<string, unknown> = {}) {
  return {
    job_id: "abc123",
    content: "We're Hiring!\nJava Developer\n\nApply here:\nhttps://jobs.example.com/apply?jobId=abc123",
    public_url: "https://jobs.example.com/apply?jobId=abc123",
    linkedin_post_status: "NOT_POSTED",
    connected: false,
    ...overrides,
  }
}

async function renderJobs() {
  render(<JobsPage />)
  await waitFor(() => {
    expect(screen.getByText("Java Developer")).toBeInTheDocument()
  })
}

beforeEach(() => {
  apiMock.getJobs.mockResolvedValue([makeJob()])
  apiMock.getGmailStatus.mockResolvedValue({ connected: false })
  apiMock.getSettings.mockResolvedValue({ backend_mode: "local" })
  apiMock.getPollLogs.mockResolvedValue({ logs: [] })
  apiMock.getLinkedinStatus.mockResolvedValue({ connected: false })
})

describe("Post on LinkedIn", () => {
  it("opens the editable preview dialog and publishes edited content", async () => {
    apiMock.getLinkedinPreview.mockResolvedValue(makePreview({ connected: true }))
    apiMock.publishLinkedinPost.mockResolvedValue({
      success: true,
      job_id: "abc123",
      linkedin_post_status: "PUBLISHED",
      post_id: "urn:li:share:1",
      post_url: "https://www.linkedin.com/feed/update/urn:li:share:1",
    })
    apiMock.getLinkedinStatus.mockResolvedValue({ connected: true })

    await renderJobs()
    await userEvent.click(screen.getByTitle("Post this job on LinkedIn"))

    await waitFor(() => {
      expect(screen.getByText(/Review and edit the draft/i)).toBeInTheDocument()
    })

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement
    expect(textarea.value).toContain("Java Developer")
    await userEvent.type(textarea, " #NowHiring")

    await userEvent.click(screen.getByRole("button", { name: /Publish to LinkedIn/i }))

    await waitFor(() => {
      expect(apiMock.publishLinkedinPost).toHaveBeenCalledWith(
        "abc123",
        expect.stringContaining("#NowHiring"),
      )
    })
    expect(toastMock.success).toHaveBeenCalledWith("Posted to LinkedIn")
    expect(openMock).toHaveBeenCalledWith(
      "https://www.linkedin.com/feed/update/urn:li:share:1",
      "_blank",
      "noopener,noreferrer",
    )
  })

  it("disables publishing and prompts to connect when no account is linked", async () => {
    apiMock.getLinkedinPreview.mockResolvedValue(makePreview({ connected: false }))
    await renderJobs()

    await userEvent.click(screen.getByTitle("Post this job on LinkedIn"))
    await waitFor(() => {
      expect(screen.getByRole("textbox")).toBeInTheDocument()
    })

    expect(screen.getByText(/Connect in Settings/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Publish to LinkedIn/i })).toBeDisabled()
    expect(apiMock.publishLinkedinPost).not.toHaveBeenCalled()
  })

  it("reports a publish failure and refreshes job state", async () => {
    apiMock.getLinkedinPreview.mockResolvedValue(makePreview({ connected: true }))
    apiMock.getLinkedinStatus.mockResolvedValue({ connected: true })
    apiMock.publishLinkedinPost.mockRejectedValue(new Error("API error 502: LinkedIn rejected the post."))
    await renderJobs()

    await userEvent.click(screen.getByTitle("Post this job on LinkedIn"))
    await waitFor(() => {
      expect(screen.getByRole("textbox")).toBeInTheDocument()
    })
    await userEvent.click(screen.getByRole("button", { name: /Publish to LinkedIn/i }))
    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalled()
    })
    expect(openMock).not.toHaveBeenCalled()
  })

  it("opens the live post link for an already-published job instead of a dialog", async () => {
    apiMock.getJobs.mockResolvedValue([
      makeJob({
        linkedin_post_status: "PUBLISHED",
        linkedin_post_url: "https://www.linkedin.com/feed/update/urn:li:share:9",
      }),
    ])
    await renderJobs()

    await userEvent.click(screen.getByTitle("Open LinkedIn post"))
    expect(openMock).toHaveBeenCalledWith(
      "https://www.linkedin.com/feed/update/urn:li:share:9",
      "_blank",
      "noopener,noreferrer",
    )
    expect(apiMock.getLinkedinPreview).not.toHaveBeenCalled()
  })

  it("shows a notify-and-verify message when a publish times out", async () => {
    apiMock.getLinkedinPreview.mockResolvedValue(makePreview({ connected: true }))
    apiMock.getLinkedinStatus.mockResolvedValue({ connected: true })
    apiMock.publishLinkedinPost.mockRejectedValue(
      new Error("API error 502: LinkedIn did not respond in time. Verify on LinkedIn before retrying."),
    )
    await renderJobs()

    await userEvent.click(screen.getByTitle("Post this job on LinkedIn"))
    await waitFor(() => {
      expect(screen.getByRole("textbox")).toBeInTheDocument()
    })
    await userEvent.click(screen.getByRole("button", { name: /Publish to LinkedIn/i }))
    await waitFor(() => {
      expect(toastMock.info).toHaveBeenCalledWith(expect.stringContaining("confirm"))
    })
  })

  it("shows a Failed status badge with the last error", async () => {
    apiMock.getJobs.mockResolvedValue([
      makeJob({ linkedin_post_status: "FAILED", linkedin_last_error: "LinkedIn rejected the post." }),
    ])
    await renderJobs()

    const badge = screen.getByText("Failed")
    expect(badge.getAttribute("title")).toBe("LinkedIn rejected the post.")

    apiMock.getLinkedinPreview.mockResolvedValue(makePreview({ connected: true }))
    apiMock.getLinkedinStatus.mockResolvedValue({ connected: true })
    await userEvent.click(screen.getByTitle("Post this job on LinkedIn"))
    await waitFor(() => {
      expect(screen.getByRole("textbox")).toBeInTheDocument()
    })
    expect(screen.getByText("Retry after failure")).toBeInTheDocument()
  })
})