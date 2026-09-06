import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

const apiMock = vi.hoisted(() => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
  getDevices: vi.fn(),
  getGmailStatus: vi.fn(),
  connectGmail: vi.fn(),
  disconnectGmail: vi.fn(),
  getCalendarStatus: vi.fn(),
  connectCalendar: vi.fn(),
  disconnectCalendar: vi.fn(),
  getLinkedinStatus: vi.fn(),
  connectLinkedin: vi.fn(),
  disconnectLinkedin: vi.fn(),
}))
vi.mock("@/lib/api", () => ({ api: apiMock }))

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))
vi.mock("sonner", () => ({ toast: toastMock }))

import SettingsPage from "../page"

const openMock = vi.fn()
beforeEach(() => {
  vi.clearAllMocks()
  globalThis.open = openMock
})

function baseSettings() {
  return {
    camera_index: 0,
    mic_device: "",
    llm_provider: "Groq",
    export_dir: "",
    gmail_connected: false,
    gmail_user: "",
    calendar_connected: false,
    calendar_user: "",
    interview_duration_minutes: 45,
    interview_buffer_minutes: 10,
    work_start_hour: 9,
    work_end_hour: 18,
    scheduling_horizon_days: 30,
    working_days: [0, 1, 2, 3, 4],
    excluded_dates: [],
  }
}

beforeEach(() => {
  apiMock.getSettings.mockResolvedValue(baseSettings())
  apiMock.getDevices.mockResolvedValue([])
  apiMock.getGmailStatus.mockResolvedValue({ connected: false, email: "" })
  apiMock.getCalendarStatus.mockResolvedValue({ connected: false, email: "" })
  apiMock.getLinkedinStatus.mockResolvedValue({ connected: false, member_name: "", member_email: "", member_author_urn: "" })
})

async function renderSettings() {
  render(<SettingsPage />)
  await waitFor(() => {
    expect(screen.getByText("Settings")).toBeInTheDocument()
  })
}

describe("LinkedIn Settings", () => {
  it("shows Connect when no profile is linked", async () => {
    await renderSettings()
    expect(screen.getByRole("button", { name: /Connect LinkedIn/i })).toBeInTheDocument()
  })

  it("opens LinkedIn consent in a new tab when connecting", async () => {
    apiMock.connectLinkedin.mockResolvedValue({
      authorization_url: "https://www.linkedin.com/oauth/v2/authorization?state=abc",
    })
    await renderSettings()

    await userEvent.click(screen.getByRole("button", { name: /Connect LinkedIn/i }))

    await waitFor(() => {
      expect(openMock).toHaveBeenCalledWith(
        "https://www.linkedin.com/oauth/v2/authorization?state=abc",
        "_blank",
        "noopener,noreferrer",
      )
    })
    expect(toastMock.info).toHaveBeenCalledWith(expect.stringContaining("new tab"))
  })

  it("surfaces a backend misconfiguration instead of opening a dead tab", async () => {
    apiMock.connectLinkedin.mockResolvedValue({ authorization_url: "" })
    await renderSettings()

    await userEvent.click(screen.getByRole("button", { name: /Connect LinkedIn/i }))

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith(
        "LinkedIn app is not configured on the server.",
      )
    })
    expect(openMock).not.toHaveBeenCalled()
  })

  it("shows identity (never credentials) once connected and disconnects", async () => {
    apiMock.getLinkedinStatus.mockResolvedValue({
      connected: true,
      member_name: "Ada Lovelace",
      member_email: "ada@example.com",
      member_author_urn: "urn:li:person:u987",
    })
    apiMock.disconnectLinkedin.mockResolvedValue({ success: true, message: "LinkedIn disconnected" })
    await renderSettings()

    expect(screen.getByText(/Connected as Ada Lovelace/)).toBeInTheDocument()
    const raw = document.body.textContent || ""
    // Tokens must never be rendered into the page.
    expect(raw).not.toContain("member-access-token")
    expect(raw).not.toContain("access_token")

    await userEvent.click(screen.getByRole("button", { name: /Disconnect/i }))
    await waitFor(() => {
      expect(apiMock.disconnectLinkedin).toHaveBeenCalled()
    })
    expect(toastMock.success).toHaveBeenCalledWith("LinkedIn disconnected")
  })
})