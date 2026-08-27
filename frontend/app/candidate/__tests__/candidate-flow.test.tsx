import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"

const push = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}))

describe("Candidate flow guards", () => {
  beforeEach(() => {
    push.mockClear()
    sessionStorage.clear()
  })

  it("candidate entry page renders without any auth/session state", async () => {
    const { default: CandidateEntryPage } = await import("../entry/page")
    render(<CandidateEntryPage />)

    expect(screen.getByText("Welcome")).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/e\.g\. abc123/i)).toBeInTheDocument()
  })

  it("candidate consent page redirects to entry when no sessionStorage data", async () => {
    const { default: CandidateConsentPage } = await import("../consent/page")
    render(<CandidateConsentPage />)

    expect(push).toHaveBeenCalledWith("/candidate/entry")
  })

  it("candidate device-check page redirects to entry when no sessionStorage data", async () => {
    const { default: CandidateDeviceCheckPage } = await import("../device-check/page")
    render(<CandidateDeviceCheckPage />)

    expect(push).toHaveBeenCalledWith("/candidate/entry")
  })

  it("candidate interview page redirects to entry when no sessionStorage data", async () => {
    const { default: CandidateInterviewPage } = await import("../interview/page")
    render(<CandidateInterviewPage />)

    expect(push).toHaveBeenCalledWith("/candidate/entry")
  })

  it("candidate done page renders the completion message", async () => {
    const { default: CandidateDonePage } = await import("../done/page")
    render(<CandidateDonePage />)

    expect(screen.getByText("Interview Complete")).toBeInTheDocument()
  })
})
