export interface AuthResponse {
  success: boolean
  message: string
  username?: string
}

export interface JobPosting {
  job_id: string
  title: string
  description: string
  required_skills: string[]
  experience_level: string
  department: string
  num_rounds: number
  time_limit_seconds: number
  adaptive_difficulty: boolean
  competency_weights: Record<string, number>
  created_at?: string
  screening_threshold: number
  application_gmail_label: string
}

// Server assigns the canonical id on create; the client never supplies it.
export type JobCreateInput = Omit<JobPosting, "job_id">

export interface Candidate {
  candidate_id: string
  job_id: string
  name: string
  email: string
  invite_code: string
  status: string
  session_id?: string
  invited_at?: string
  resume_path?: string
  resume_skills: string[]
  experience_years?: number
  match_score?: number
  matched_skills: string[]
  missing_skills: string[]
  job_title?: string
  source: string
  screening_status: string
  invite_email_sent: boolean
  application_id?: string | null
  screening_result?: ScreeningResult | null
}

export interface InterviewSession {
  session_id: string
  candidate_name: string
  job_title: string
  job_id?: string
  video_path?: string
  audio_path?: string
  transcript?: string
  started_at?: string
  completed_at?: string
  status: string
}

export interface DashboardStats {
  interviews_conducted: number
  avg_explainability_score: number
  bias_flags_raised: number
  integrity_flags: number
  candidates_by_status: Record<string, number>
}

export interface CompetencyScore {
  session_id: string
  question_id: string
  category: string
  score: number
  confidence: number
}

export interface Explanation {
  session_id: string
  question_id: string
  summary: string
  supporting_phrases: string[]
}

export interface FairnessFlag {
  session_id: string
  question_id: string
  score_delta: number
  note: string
}

export interface IntegrityFlag {
  id?: number
  session_id: string
  flag_type: string
  detail: string
  severity: string
  timestamp?: string
  candidate_name?: string
  job_title?: string
}

export interface CandidateReport {
  session: InterviewSession
  scores: CompetencyScore[]
  explanations: Explanation[]
  overall_score: number
}

export interface ComparisonRow {
  session_id: string
  candidate_name: string
  job_title: string
  overall_score: number
  category_scores: Record<string, number>
}

export interface Settings {
  camera_index: number
  mic_device: string
  llm_provider: string
  export_dir: string
  gmail_connected: boolean
  gmail_user: string
  calendar_connected: boolean
  calendar_user: string
  interview_duration_minutes: number
  interview_buffer_minutes: number
  work_start_hour: number
  work_end_hour: number
  scheduling_horizon_days: number
  working_days: number[]
  excluded_dates: string[]
}

export interface DeviceInfo {
  name: string
  index?: number
  device_class: string
}

export interface InviteValidation {
  valid: boolean
  candidate?: Candidate
  job?: JobPosting
  message?: string
  interview_token?: string
  expires_at?: string
}

export interface GmailStatus {
  connected: boolean
  email: string
}

export interface GmailConnectResult {
  success: boolean
  email: string
  message: string
}

export interface CalendarStatus {
  connected: boolean
  email: string
}

export interface CalendarConnectResult {
  success: boolean
  email: string
  message: string
}

export interface ScheduledInterview {
  id?: number
  candidate_id: string
  job_id: string
  scheduled_at?: string
  duration_minutes: number
  gcal_event_id?: string
  status: string
  created_at?: string
  candidate_name?: string
  candidate_email?: string
  candidate_status?: string
  job_title?: string
}

export interface EmailCheckResult {
  results: Record<string, any>[]
  summary: string
}

export interface PollLogEntry {
  id: number
  run_at: string
  job_id: string
  job_title: string
  total_checked: number
  invited: number
  below_threshold: number
  skipped: number
  failed: number
  mode: string
}

export interface ScreeningResult {
  application_id: string
  ats_score?: number | null
  skills_score?: number | null
  experience_score?: number | null
  semantic_score?: number | null
  education_score?: number | null
  keyword_score?: number | null
  matched_skills: string[]
  missing_skills: string[]
  hard_requirements_passed: boolean
  hard_requirement_failures: string[]
  decision: string
  decision_reason: string
  threshold_used?: number | null
  scoring_method: string
  matcher_method: string
  confidence: number
  completed_at?: string
}

export interface ApplicationEvent {
  event: string
  detail: string
  created_at?: string
}

export interface JobPipelineStat {
  job_id: string
  title: string
  applications: number
  screening_pending: number
  shortlisted: number
  rejected: number
  manual_review: number
  invites_sent: number
  interviews_completed: number
  email_failures: number
}

export interface OutboxNotification {
  id?: number
  application_id?: string | null
  candidate_id?: string | null
  job_id: string
  notification_type: string
  recipient: string
  status: string
  attempts: number
  subject: string
  body: string
  created_at?: string
  sent_at?: string
  last_error?: string
}

export interface ApplicationDetail {
  application_id: string
  job_id: string
  full_name: string
  email: string
  phone: string
  resume_path: string
  source: string
  status: string
  screening_status: string
  candidate_id?: string | null
  submitted_at?: string
  updated_at?: string
  screening_result?: ScreeningResult | null
  notifications: OutboxNotification[]
  events?: ApplicationEvent[]
}
