import type { JobPosting, JobCreateInput, Candidate, InterviewSession, DashboardStats, CompetencyScore, Explanation, FairnessFlag, IntegrityFlag, CandidateReport, ComparisonRow, Settings, DeviceInfo, InviteValidation, GmailStatus, GmailConnectResult, EmailCheckResult, PollLogEntry, CalendarStatus, CalendarConnectResult, ScheduledInterview, ApplicationDetail, JobPipelineStat, LinkedInStatus, LinkedInConnectResult, LinkedInPreview, LinkedInPublishResult, TranscriptionResponse, QuestionItem, SelectQuestionsResponse, CandidateQuestionsResponse, CandidateProgressResponse, InterviewStatusResponse, JobStrategyStatus, JobStrategyConfirmInput, FaceCheckResponse } from './types'

let cachedBaseUrl: string | null = null

const TOKEN_KEY = 'interviewiq_token'
const USERNAME_KEY = 'interviewiq_username'

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(TOKEN_KEY)
}

export function setAuthToken(token: string | null) {
  if (typeof window !== 'undefined') {
    if (token) window.localStorage.setItem(TOKEN_KEY, token)
    else window.localStorage.removeItem(TOKEN_KEY)
  }
}

export function getUsername(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(USERNAME_KEY) ?? (typeof window !== 'undefined' ? window.localStorage.getItem('username') : null)
}

export function setUsername(username: string | null) {
  if (typeof window !== 'undefined') {
    if (username) window.localStorage.setItem(USERNAME_KEY, username)
    else window.localStorage.removeItem(USERNAME_KEY)
  }
}

export function clearAuth() {
  setAuthToken(null)
  setUsername(null)
}

function authHeaders(): Record<string, string> {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/**
 * Resolved API base URL.
 *
 * Electron's main process decides where shared-data traffic goes:
 * - backend_mode "local": the FastAPI sidecar it spawned on a random port
 * - backend_mode "remote": the central deployed server (remote_api_url)
 * The URL reaches the renderer through preload (contextBridge).
 *
 * Outside Electron, the frontend is served as a public website for external
 * candidates, and the backend origin is provided via NEXT_PUBLIC_API_URL.
 * Without it, localhost:8000 is only a development convenience.
 */
export async function getBaseUrl(): Promise<string> {
  if (cachedBaseUrl) return cachedBaseUrl
  const w = typeof window !== 'undefined' ? (window as any) : undefined
  if (w?.appConfig?.getApiBaseUrl) {
    // Electron host resolves its backend target (local sidecar or remote server).
    cachedBaseUrl = await w.appConfig.getApiBaseUrl()
  } else {
    // Plain web deployment: the backend origin is set at build/runtime via
    // NEXT_PUBLIC_API_URL. Never fall back to a machine-localhost backend in
    // production — an external candidate's browser must not call its own host.
    cachedBaseUrl =
      (process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/+$/, '')) ||
      `http://localhost:${w?.__API_PORT__ || 8000}`
  }
  return cachedBaseUrl!
}

export async function mediaUrl(relPath: string): Promise<string> {
  const baseUrl = await getBaseUrl()
  const clean = relPath.replace(/^\/+/, '')
  try {
    const token = getAuthToken()
    const res = await fetch(`${baseUrl}/api/media/sign?path=${encodeURIComponent(clean)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (res.ok) {
      const { url } = await res.json()
      return `${baseUrl}${url}`
    }
  } catch {
    // fall through to the unchanged URL — it will 403 if unsigned, which is
    // the intended security posture
  }
  return `${baseUrl}/media/${clean}`
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const baseUrl = await getBaseUrl()
  const res = await fetch(`${baseUrl}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...options?.headers,
    },
    ...options,
  })
  if (!res.ok) {
    const err = await res.text()
    if (res.status === 401) clearAuth()
    throw new Error(`API error ${res.status}: ${err}`)
  }
  return res.json()
}

async function requestForm<T>(path: string, formData: FormData, extraHeaders?: Record<string, string>): Promise<T> {
  const baseUrl = await getBaseUrl()
  // No Content-Type header: the browser sets the multipart boundary.
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { ...authHeaders(), ...extraHeaders },
    body: formData,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API error ${res.status}: ${err}`)
  }
  return res.json()
}

function getInterviewTokenHeader(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  const token = window.sessionStorage.getItem('interview_token')
  return token ? { 'X-Interview-Token': token } : {}
}

function interviewTokenHeaderFor(requestOptions?: RequestInit): Record<string, string> {
  const headers: Record<string, string> = {}
  const existing = requestOptions?.headers
  if (existing) {
    const h = new Headers(existing)
    h.forEach((value, key) => {
      headers[key] = value
    })
  }
  return { ...headers, ...getInterviewTokenHeader() }
}

export const api = {
  // Auth
  login: async (username: string, password: string) => {
    const res = await request<{ success: boolean; message: string; username?: string; token?: string }>('/api/auth/login', {
      method: 'POST', body: JSON.stringify({ username, password }),
    })
    if (res.success && res.token) {
      setAuthToken(res.token)
      setUsername(res.username ?? username)
    }
    return res
  },
  register: async (username: string, password: string, full_name: string) => {
    const res = await request<{ success: boolean; message: string; username?: string; token?: string }>('/api/auth/register', {
      method: 'POST', body: JSON.stringify({ username, password, full_name }),
    })
    if (res.success && res.token) {
      setAuthToken(res.token)
      setUsername(res.username ?? username)
    }
    return res
  },
  me: () => request<{ username: string; full_name: string }>('/api/auth/me'),

  // Jobs
  getJobs: () => request<JobPosting[]>('/api/jobs'),
  createJob: (job: JobCreateInput) =>
    request<JobPosting>('/api/jobs', { method: 'POST', body: JSON.stringify(job) }),
  updateJob: (job_id: string, job: JobPosting) =>
    request<JobPosting>(`/api/jobs/${job_id}`, { method: 'PUT', body: JSON.stringify(job) }),
  deleteJob: (job_id: string) =>
    request<{ success: boolean }>(`/api/jobs/${job_id}`, { method: 'DELETE' }),

  // Interview-mode strategy (job-level)
  getJobInterviewModeStatus: (job_id: string) =>
    request<JobStrategyStatus>(`/api/jobs/${job_id}/interview-mode/status`),
  confirmJobInterviewMode: (job_id: string, strategy: JobStrategyConfirmInput) =>
    request<JobStrategyStatus>(`/api/jobs/${job_id}/interview-mode/confirm`, {
      method: 'POST', body: JSON.stringify(strategy),
    }),

  // Candidates
  getCandidates: () => request<Candidate[]>('/api/candidates'),
  getCandidatesForJob: (job_id: string) => request<Candidate[]>(`/api/candidates/job/${job_id}`),
  createCandidate: (data: { candidate_id: string; job_id: string; name: string; email: string }) =>
    request<Candidate>('/api/candidates', { method: 'POST', body: JSON.stringify(data) }),
  deleteCandidate: (id: string) =>
    request<{ success: boolean }>(`/api/candidates/${id}`, { method: 'DELETE' }),
  resendInvite: (id: string) =>
    request<{ invite_code: string; message: string }>(`/api/candidates/${id}/resend`, { method: 'POST' }),
  uploadResume: async (id: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return requestForm<Candidate>(`/api/candidates/${id}/resume`, formData)
  },

  // Sessions
  getSessions: () => request<InterviewSession[]>('/api/sessions'),
  createSession: (data: { candidate_id: string }) =>
    request<InterviewSession>('/api/sessions', { method: 'POST', body: JSON.stringify(data) }),
  uploadRecording: async (
    session_id: string,
    files: { video?: Blob; audio?: Blob },
    filenames?: { video?: string; audio?: string }
  ) => {
    const formData = new FormData()
    if (files.video) formData.append('video', files.video, filenames?.video || `${session_id}_video.webm`)
    if (files.audio) formData.append('audio', files.audio, filenames?.audio || `${session_id}_audio.webm`)
      return requestForm<{ success: boolean; saved: Record<string, string> }>(
        `/api/sessions/${session_id}/upload`,
        formData,
        getInterviewTokenHeader()
      )
  },

  transcribeSession: async (session_id: string, question_id: string, audio: Blob) => {
    const formData = new FormData()
    const ext = audio.type.includes("webm") ? "webm" : audio.type.includes("mp3") ? "mp3" : "wav"
    formData.append("question_id", question_id)
    formData.append("audio", audio, `${session_id}_${question_id}.${ext}`)
    return requestForm<TranscriptionResponse>(
      `/api/sessions/${session_id}/transcribe`,
      formData,
      getInterviewTokenHeader()
    )
  },

  // Question engine (MODE 2 structured screening)
  selectQuestions: (session_id: string, num_questions: number = 10, force_generated: boolean = false) =>
    request<SelectQuestionsResponse>('/api/questions/select', {
      method: 'POST',
      body: JSON.stringify({ session_id, num_questions, force_generated }),
    }),
  getCandidateQuestions: () =>
    request<CandidateQuestionsResponse>('/api/candidate/questions', {
      headers: getInterviewTokenHeader(),
    }),
  getCandidateProgress: () =>
    request<CandidateProgressResponse>('/api/candidate/progress', {
      headers: getInterviewTokenHeader(),
    }),
  getCandidateInterviewStatus: (candidate_id: string) =>
    request<InterviewStatusResponse>(`/api/candidates/${candidate_id}/interview-status`),

  // Live monitor preview frames
  uploadLiveFrame: async (session_id: string, blob: Blob) => {
    // Raw JPEG body, no JSON envelope — called every ~1.5s per candidate,
    // so keep it as light as possible.
    const base = await getBaseUrl()
    await fetch(`${base}/api/sessions/${session_id}/live-frame`, {
      method: 'POST',
      headers: { 'Content-Type': 'image/jpeg', ...getInterviewTokenHeader() },
      body: blob,
    })
  },
  fetchLiveFrame: async (session_id: string): Promise<string | null> => {
    const base = await getBaseUrl()
    try {
      const res = await fetch(`${base}/api/sessions/${session_id}/live-frame?t=${Date.now()}`, {
        cache: 'no-store',
        headers: authHeaders(),
      })
      if (!res.ok) return null
      return URL.createObjectURL(await res.blob())
    } catch {
      return null
    }
  },

  // Scoring
  runScoring: (data: { session_id: string; question_id: string; category: string; transcript: string }) =>
    request<{ score: CompetencyScore; explanation: Explanation; fairness: FairnessFlag;
              ml_score: number | null; rubric_source: string }>('/api/scoring/run', {
      method: 'POST', body: JSON.stringify(data),
    }),

  // Reports
  getDashboardStats: () => request<DashboardStats>('/api/reports/dashboard'),
  getCandidateReport: (session_id: string) => request<CandidateReport>(`/api/reports/candidate/${session_id}`),
  getComparison: (job_id?: string) =>
    request<ComparisonRow[]>(`/api/reports/compare${job_id ? `?job_id=${job_id}` : ''}`),

  // Integrity & Bias
  getIntegrityFlags: () => request<IntegrityFlag[]>('/api/integrity/flags'),
  getBiasFlags: () => request<FairnessFlag[]>('/api/bias/flags'),
  postIntegrityFlags: (flags: Array<Pick<IntegrityFlag, 'session_id' | 'flag_type' | 'detail' | 'severity'>>) => {
    const itoken = typeof window !== 'undefined' ? window.sessionStorage.getItem('interview_token') || '' : ''
    return request<{ saved: number }>('/api/integrity/flags', {
      method: 'POST',
      body: JSON.stringify({ flags }),
      headers: { 'X-Interview-Token': itoken },
    })
  },

  // Settings
  getSettings: () => request<Settings>('/api/settings'),
  updateSettings: (settings: Partial<Settings>) =>
    request<Settings>('/api/settings', { method: 'PUT', body: JSON.stringify(settings) }),

  // Devices
  getDevices: () => request<DeviceInfo[]>('/api/devices'),

  // Candidate Flow
  validateInviteCode: (invite_code: string) =>
    request<InviteValidation>('/api/candidate/validate-code', {
      method: 'POST', body: JSON.stringify({ invite_code }),
    }),
  recordConsent: async (candidate_id: string, interview_token: string) => {
    const res = await request<{ success: boolean; session_id?: string }>('/api/candidate/consent', {
      method: 'POST', body: JSON.stringify({ candidate_id, interview_token }),
    })
    // The server resolves the authoritative session id and returns it here.
    // Persist it so the interview page (and device-check) use the SAME session
    // the server holds — never a client-fabricated one.
    if (res.session_id && typeof window !== 'undefined') {
      window.sessionStorage.setItem('session_id', res.session_id)
    }
    return res
  },
  startCandidateSession: (session_id: string, candidate_id: string, job_id: string, interview_token: string) =>
    request<InterviewSession>('/api/candidate/start-session', {
      method: 'POST', body: JSON.stringify({ session_id, candidate_id, job_id, interview_token }),
    }),
  submitAnswer: (session_id: string, question_id: string, category: string, transcript: string) => {
    const itoken = typeof window !== 'undefined' ? window.sessionStorage.getItem('interview_token') || '' : ''
    return request<{ score: CompetencyScore; explanation: Explanation; fairness: FairnessFlag | null }>('/api/candidate/submit-answer', {
      method: 'POST', body: JSON.stringify({ session_id, question_id, category, transcript, interview_token: itoken }),
    })
  },
  completeCandidateSession: (session_id: string) => {
    const itoken = typeof window !== 'undefined' ? window.sessionStorage.getItem('interview_token') || '' : ''
    return request<{ success: boolean }>('/api/candidate/complete-session', {
      method: 'POST', body: JSON.stringify({ session_id, interview_token: itoken }),
    })
  },
  faceCheck: (frame_base64: string, interview_token: string) =>
    request<FaceCheckResponse>('/api/candidate/face-check', {
      method: 'POST', body: JSON.stringify({ frame_base64, interview_token }),
    }),

  // Gmail Integration
  getGmailStatus: () => request<GmailStatus>('/api/settings/gmail/status'),
  connectGmail: () => request<GmailConnectResult>('/api/settings/gmail/connect', { method: 'POST' }),
  disconnectGmail: () => request<{ success: boolean; message: string }>('/api/settings/gmail/disconnect', { method: 'POST' }),

  // Email Intake
  checkEmailApplications: (job_id: string) =>
    request<EmailCheckResult>('/api/email-intake/check', {
      method: 'POST', body: JSON.stringify({ job_id }),
    }),
  getPollLogs: () =>
    request<{ logs: PollLogEntry[] }>('/api/email-intake/poll-logs'),

  // Google Calendar Integration
  getCalendarStatus: () => request<CalendarStatus>('/api/settings/calendar/status'),
  connectCalendar: () => request<CalendarConnectResult>('/api/settings/calendar/connect', { method: 'POST' }),
  disconnectCalendar: () => request<{ success: boolean; message: string }>('/api/settings/calendar/disconnect', { method: 'POST' }),

  // Scheduling
  getScheduledInterviews: () => request<ScheduledInterview[]>('/api/scheduling'),
  allocateSlot: (candidate_id: string, job_id: string) =>
    request<{ success: boolean; scheduled_at?: string; duration_minutes?: number; message: string }>('/api/scheduling/allocate', {
      method: 'POST', body: JSON.stringify({ candidate_id, job_id }),
    }),

  // Applications (candidate-first screening pipeline)
  getApplications: (jobId?: string) =>
    request<{ applications: ApplicationDetail[] }>(`/api/applications${jobId ? `?job_id=${jobId}` : ''}`),
  getApplication: (applicationId: string) =>
    request<ApplicationDetail>(`/api/applications/${applicationId}`),
  getApplicationStats: () =>
    request<{ jobs: JobPipelineStat[] }>('/api/applications/stats'),
  rescreenApplication: (applicationId: string) =>
    request<{ success: boolean; application_id: string; screening_status: string }>(`/api/applications/${applicationId}/rescreen`, {
      method: 'POST',
    }),

  // LinkedIn Integration (member posting)
  getLinkedinStatus: () => request<LinkedInStatus>('/api/integrations/linkedin/status'),
  connectLinkedin: () => request<LinkedInConnectResult>('/api/integrations/linkedin/connect'),
  disconnectLinkedin: () => request<{ success: boolean; message: string }>('/api/integrations/linkedin/disconnect', { method: 'POST' }),
  getLinkedinPreview: (job_id: string) =>
    request<LinkedInPreview>(`/api/jobs/${job_id}/linkedin/preview`, { method: 'POST' }),
  publishLinkedinPost: (job_id: string, content: string) =>
    request<LinkedInPublishResult>(`/api/jobs/${job_id}/linkedin/publish`, {
      method: 'POST', body: JSON.stringify({ content }),
    }),
}
