import type { JobPosting, Candidate, InterviewSession, DashboardStats, CompetencyScore, Explanation, FairnessFlag, IntegrityFlag, CandidateReport, ComparisonRow, Settings, DeviceInfo, InviteValidation } from './types'

let cachedBaseUrl: string | null = null

/**
 * Resolved API base URL.
 *
 * Electron's main process decides where shared-data traffic goes:
 * - backend_mode "local": the FastAPI sidecar it spawned on a random port
 * - backend_mode "remote": the central deployed server (remote_api_url)
 * The URL reaches the renderer through preload (contextBridge). Outside
 * Electron (plain `next dev` in a browser tab) this falls back to :8000,
 * which is only ever a development convenience — the frontend is not
 * meant to be served as a standalone website.
 */
export async function getBaseUrl(): Promise<string> {
  if (cachedBaseUrl) return cachedBaseUrl
  const w = typeof window !== 'undefined' ? (window as any) : undefined
  if (w?.appConfig?.getApiBaseUrl) {
    cachedBaseUrl = await w.appConfig.getApiBaseUrl()
  } else {
    cachedBaseUrl = `http://localhost:${w?.__API_PORT__ || 8000}`
  }
  return cachedBaseUrl!
}

export function mediaUrl(relPath: string): Promise<string> {
  return getBaseUrl().then((base) => `${base}/media/${relPath.replace(/^\/+/, '')}`)
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const baseUrl = await getBaseUrl()
  const res = await fetch(`${baseUrl}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API error ${res.status}: ${err}`)
  }
  return res.json()
}

async function requestForm<T>(path: string, formData: FormData): Promise<T> {
  const baseUrl = await getBaseUrl()
  // No Content-Type header: the browser sets the multipart boundary.
  const res = await fetch(`${baseUrl}${path}`, { method: 'POST', body: formData })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API error ${res.status}: ${err}`)
  }
  return res.json()
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    request<{ success: boolean; message: string; username?: string }>('/api/auth/login', {
      method: 'POST', body: JSON.stringify({ username, password }),
    }),
  register: (username: string, password: string, full_name: string) =>
    request<{ success: boolean; message: string; username?: string }>('/api/auth/register', {
      method: 'POST', body: JSON.stringify({ username, password, full_name }),
    }),

  // Jobs
  getJobs: () => request<JobPosting[]>('/api/jobs'),
  createJob: (job: JobPosting) =>
    request<JobPosting>('/api/jobs', { method: 'POST', body: JSON.stringify(job) }),
  updateJob: (job_id: string, job: JobPosting) =>
    request<JobPosting>(`/api/jobs/${job_id}`, { method: 'PUT', body: JSON.stringify(job) }),
  deleteJob: (job_id: string) =>
    request<{ success: boolean }>(`/api/jobs/${job_id}`, { method: 'DELETE' }),

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
  createSession: (data: { session_id: string; candidate_name: string; job_title: string; job_id?: string }) =>
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
      formData
    )
  },

  // Live monitor preview frames
  uploadLiveFrame: async (session_id: string, blob: Blob) => {
    // Raw JPEG body, no JSON envelope — called every ~1.5s per candidate,
    // so keep it as light as possible.
    const base = await getBaseUrl()
    await fetch(`${base}/api/sessions/${session_id}/live-frame`, {
      method: 'POST',
      headers: { 'Content-Type': 'image/jpeg' },
      body: blob,
    })
  },
  fetchLiveFrame: async (session_id: string): Promise<string | null> => {
    const base = await getBaseUrl()
    try {
      const res = await fetch(`${base}/api/sessions/${session_id}/live-frame?t=${Date.now()}`, {
        cache: 'no-store',
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
  postIntegrityFlags: (flags: Array<Pick<IntegrityFlag, 'session_id' | 'flag_type' | 'detail' | 'severity'>>) =>
    request<{ saved: number }>('/api/integrity/flags', {
      method: 'POST',
      body: JSON.stringify({ flags }),
    }),

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
  recordConsent: (session_id: string, candidate_id: string) =>
    request<{ success: boolean }>('/api/candidate/consent', {
      method: 'POST', body: JSON.stringify({ session_id, candidate_id }),
    }),
  startCandidateSession: (session_id: string, candidate_id: string, job_id: string) =>
    request<InterviewSession>('/api/candidate/start-session', {
      method: 'POST', body: JSON.stringify({ session_id, candidate_id, job_id }),
    }),
  submitAnswer: (session_id: string, question_id: string, category: string, transcript: string) =>
    request<{ score: CompetencyScore; explanation: Explanation; fairness: FairnessFlag | null }>('/api/candidate/submit-answer', {
      method: 'POST', body: JSON.stringify({ session_id, question_id, category, transcript }),
    }),
  completeCandidateSession: (session_id: string) =>
    request<{ success: boolean }>('/api/candidate/complete-session', {
      method: 'POST', body: JSON.stringify({ session_id }),
    }),
}
