import type { JobPosting, Candidate, InterviewSession, DashboardStats, CompetencyScore, Explanation, FairnessFlag, IntegrityFlag, CandidateReport, ComparisonRow, Settings, DeviceInfo, InviteValidation } from './types'

const BASE_URL = typeof window !== 'undefined'
  ? `http://localhost:${(window as any).__API_PORT__ || 8000}`
  : 'http://localhost:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
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
    const res = await fetch(`${BASE_URL}/api/candidates/${id}/resume`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) {
      const err = await res.text()
      throw new Error(`API error ${res.status}: ${err}`)
    }
    return res.json() as Promise<Candidate>
  },

  // Sessions
  getSessions: () => request<InterviewSession[]>('/api/sessions'),
  createSession: (data: { session_id: string; candidate_name: string; job_title: string; job_id?: string }) =>
    request<InterviewSession>('/api/sessions', { method: 'POST', body: JSON.stringify(data) }),

  // Scoring
  runScoring: (data: { session_id: string; question_id: string; category: string; transcript: string }) =>
    request<{ score: CompetencyScore; explanation: Explanation; fairness: FairnessFlag }>('/api/scoring/run', {
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
