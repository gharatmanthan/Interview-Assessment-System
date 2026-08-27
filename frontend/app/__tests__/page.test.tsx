import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

const push = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}))

import Home from "../page"

describe("Root page (role selector)", () => {
  beforeEach(() => {
    push.mockClear()
  })

  it("renders the role selector with both options", () => {
    render(<Home />)

    expect(screen.getByText("InterviewIQ")).toBeInTheDocument()
    expect(screen.getByText("Who is using this device?")).toBeInTheDocument()
    expect(screen.getByText("I'm a Recruiter")).toBeInTheDocument()
    expect(screen.getByText("I'm a Candidate")).toBeInTheDocument()
  })

  it("renders subtitles for both cards", () => {
    render(<Home />)

    expect(screen.getByText(/Create job postings/)).toBeInTheDocument()
    expect(screen.getByText(/Enter your invite code/)).toBeInTheDocument()
  })

  it("navigates to /login when Recruiter card is clicked", async () => {
    const user = userEvent.setup()
    render(<Home />)

    await user.click(screen.getByText("I'm a Recruiter"))

    expect(push).toHaveBeenCalledWith("/login")
  })

  it("navigates to /candidate/entry when Candidate card is clicked", async () => {
    const user = userEvent.setup()
    render(<Home />)

    await user.click(screen.getByText("I'm a Candidate"))

    expect(push).toHaveBeenCalledWith("/candidate/entry")
  })

  it("does NOT render a login form (no username/password fields)", () => {
    render(<Home />)

    expect(screen.queryByLabelText(/username/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()
  })
})
