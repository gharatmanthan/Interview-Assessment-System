import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor, fireEvent } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

const mockGetBaseUrl = vi.fn().mockResolvedValue("http://localhost:8000")
vi.mock("@/lib/api", () => ({ getBaseUrl: (...args: any[]) => mockGetBaseUrl(...args) }))

const mockGetSearchParam = vi.fn()
vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: (key: string) => mockGetSearchParam(key) }),
}))

const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

import ApplyPage from "../page"

const JOB_DATA = {
  job_id: "job-test-1",
  title: "Frontend Engineer",
  description: "Build beautiful UIs with React and TypeScript.",
  required_skills: ["React", "TypeScript"],
  experience_level: "Mid",
  department: "Engineering",
}

function uploadFile(input: HTMLElement, file: File) {
  fireEvent.change(input, { target: { files: [file] } })
}

describe("Apply page", () => {
  beforeEach(() => {
    mockGetSearchParam.mockImplementation((key: string) => key === "jobId" ? "job-test-1" : null)
    mockGetBaseUrl.mockResolvedValue("http://localhost:8000")
    mockFetch.mockReset()
  })

  it("shows loading state initially", () => {
    mockFetch.mockReturnValue(new Promise(() => {}))
    render(<ApplyPage />)
    expect(screen.getByText("Loading...")).toBeInTheDocument()
  })

  it("renders job details after fetch", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(JOB_DATA) })
    render(<ApplyPage />)

    await waitFor(() => {
      expect(screen.getByText("Frontend Engineer")).toBeInTheDocument()
    })
    expect(screen.getByText("Engineering · Mid")).toBeInTheDocument()
    expect(screen.getByText("Build beautiful UIs with React and TypeScript.")).toBeInTheDocument()
    expect(screen.getByText("React")).toBeInTheDocument()
    expect(screen.getByText("TypeScript")).toBeInTheDocument()
  })

  it("shows error state for invalid job", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404 })
    render(<ApplyPage />)

    await waitFor(() => {
      expect(screen.getByText("Job Not Found")).toBeInTheDocument()
    })
  })

  it("shows invalid application link when no query param", async () => {
    mockGetSearchParam.mockImplementation(() => null)
    render(<ApplyPage />)

    await waitFor(() => {
      expect(screen.getByText("Invalid Application Link")).toBeInTheDocument()
    })
  })

  it("renders the application form", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(JOB_DATA) })
    render(<ApplyPage />)

    await waitFor(() => {
      expect(screen.getByLabelText("Full Name")).toBeInTheDocument()
    })
    expect(screen.getByLabelText("Email")).toBeInTheDocument()
    expect(screen.getByLabelText(/Resume/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Submit Application" })).toBeInTheDocument()
  })

  it("does NOT show screening results or invite codes", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(JOB_DATA) })
    render(<ApplyPage />)

    await waitFor(() => {
      expect(screen.getByText("Frontend Engineer")).toBeInTheDocument()
    })
    expect(screen.queryByText(/match score/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/invite code/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/passed/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/below threshold/i)).not.toBeInTheDocument()
  })

  it("shows generic confirmation after successful submission", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(JOB_DATA) })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          candidate_id: "apply_portal-abc123",
          match_score: 75.0,
          screening_status: "passed_threshold",
          invite_code: "test-code",
          message: "Application received successfully.",
        }),
      })

    const user = userEvent.setup()
    render(<ApplyPage />)

    await waitFor(() => {
      expect(screen.getByLabelText("Full Name")).toBeInTheDocument()
    })

    await user.type(screen.getByLabelText("Full Name"), "Jane Doe")
    await user.type(screen.getByLabelText("Email"), "jane@example.com")

    const fileInput = screen.getByLabelText(/Resume/)
    const file = new File(["resume content"], "resume.pdf", { type: "application/pdf" })
    uploadFile(fileInput, file)

    const form = fileInput.closest("form")!
    fireEvent.submit(form)

    await waitFor(() => {
      expect(screen.getByText("Application Submitted")).toBeInTheDocument()
    })

    expect(screen.getByText(/Thanks for applying/)).toBeInTheDocument()
    expect(screen.getByText(/shortlisted for an interview/)).toBeInTheDocument()
    // Must NOT show score, invite code, or pass/fail
    expect(screen.queryByText("75")).not.toBeInTheDocument()
    expect(screen.queryByText("test-code")).not.toBeInTheDocument()
    expect(screen.queryByText(/passed/i)).not.toBeInTheDocument()
  })

  it("shows error message on failed submission", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(JOB_DATA) })
      .mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ detail: "Unsupported file type" }),
      })

    const user = userEvent.setup()
    render(<ApplyPage />)

    await waitFor(() => {
      expect(screen.getByLabelText("Full Name")).toBeInTheDocument()
    })

    await user.type(screen.getByLabelText("Full Name"), "Test User")
    await user.type(screen.getByLabelText("Email"), "test@example.com")

    const fileInput = screen.getByLabelText(/Resume/)
    const file = new File(["bad"], "malware.exe", { type: "application/octet-stream" })
    uploadFile(fileInput, file)

    const form = fileInput.closest("form")!
    fireEvent.submit(form)

    await waitFor(() => {
      expect(screen.getByText("Unsupported file type")).toBeInTheDocument()
    })
  })
})
