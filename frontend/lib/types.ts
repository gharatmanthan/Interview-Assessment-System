export interface AuthResponse {
  success: boolean
  message: string
  username?: string
}

export type InterviewStrategy = "AUTO" | "MODE_1_ONLY" | "MODE_2_THEN_MODE_1"

export type InterviewMode = "MODE_1" | "MODE_2"

export type ModeStatus =
  | "SHORTLISTED"
  | "CONFIRMED"
  | "INVITED"
  | "COMPLETED"
  | "PROMOTED"
  | "NOT_PROMOTED"
  | ""

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
  linkedin_post_status?: string
  linkedin_post_id?: string | null
  linkedin_post_url?: string | null
  linkedin_posted_at?: string | null
  linkedin_author_urn?: string | null
  linkedin_last_error?: string | null
  // Interview-mode routing (job-level strategy)
  interview_strategy?: InterviewStrategy
  recommended_strategy?: InterviewStrategy
  strategy_confirmed?: boolean
  strategy_confirmed_at?: string | null
  cohort_finalized_at?: string | null
}

// Server assigns the canonical id on create; the client never supplies it.
export type JobCreateInput = Omit<JobPosting, "job_id" | "linkedin_post_status" | "linkedin_post_id" | "linkedin_post_url" | "linkedin_posted_at" | "linkedin_author_urn" | "linkedin_last_error" | "interview_strategy" | "recommended_strategy" | "strategy_confirmed" | "strategy_confirmed_at" | "cohort_finalized_at">

export type LinkedInPostStatus =
  | "NOT_POSTED"
  | "DRAFT"
  | "PUBLISHING"
  | "PUBLISHED"
  | "FAILED"

// Live interview-mode routing status for a job's screening cohort.
// Mirrors api/schemas.py JobStrategyStatusResponse.
export interface JobStrategyStatus {
  job_id: string
  screening_pending: number
  shortlisted: number
  cohort_finalized: boolean
  recommended_strategy: InterviewStrategy
  interview_strategy: InterviewStrategy
  strategy_confirmed: boolean
  strategy_confirmed_at?: string | null
  cohort_finalized_at?: string | null
  interview_capacity: number
}

export interface JobStrategyConfirmInput {
  strategy: InterviewStrategy
}

export interface LinkedInStatus {
  connected: boolean
  member_name: string
  member_email: string
  connected_at?: string | null
  member_author_urn: string
}

export interface LinkedInConnectResult {
  authorization_url: string
}

export interface LinkedInPreview {
  job_id: string
  content: string
  public_url: string
  linkedin_post_status: string
  connected: boolean
}

export interface LinkedInPublishResult {
  success: boolean
  job_id: string
  linkedin_post_status: string
  post_id?: string | null
  post_url?: string | null
}

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
  // Interview-mode routing (candidate-level)
  interview_mode?: InterviewMode | ""
  mode_status?: ModeStatus
  mode2_score?: number | null
  overall_score?: number | null
  rank?: number | null
  ranked_at?: string | null
  promoted_at?: string | null
  mode_assignment_source?: string
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

export interface TranscriptionResponse {
  question_id: string
  transcript: string
  audio_path?: string
}

export interface QuestionItem {
  question_index: number
  question_id: string
  question_text: string
  category: string
  competency: string
  difficulty: string
  source: string
}

export interface SelectQuestionsResponse {
  session_id: string
  questions: QuestionItem[]
  locked: boolean
}

export interface CandidateQuestionsResponse {
  session_id: string
  questions: QuestionItem[]
}

// --- Phase 3B: MODE 2 self-serve interview progress / status ---

export interface CandidateProgressResponse {
  session_id: string
  interview_status: string // not_ready | ready | in_progress | completed
  total_questions: number
  answered_questions: number
  remaining_questions: number
  current_question: QuestionItem | null
  completed: boolean
}

export interface InterviewStatusResponse {
  candidate_id: string
  session_id: string
  interview_status: string // not_ready | ready | in_progress | completed
  locked: boolean
  total_questions: number
  answered_questions: number
  categories: string[]
  candidate_status: string
}

// --- Phase 3A: MODE 1 live interview ---

export type LiveRole = "recruiter" | "candidate"

export interface LiveConnectionCounts {
  recruiter: number
  candidate: number
}

export interface LiveJoinedMessage {
  type: "joined"
  role: LiveRole
  session_status: string
  current_question: QuestionItem | null
  has_questions: boolean
  connections: LiveConnectionCounts
}

export interface LiveQuestionAskedMessage {
  type: "question_asked"
  question: QuestionItem
}

export interface LiveTranscriptReadyMessage {
  type: "transcript_ready"
  question_id: string
  transcript: string
}

export interface LiveConnectionStatusMessage {
  type: "connection_status"
  recruiter: number
  candidate: number
}

export interface LiveInterviewEndedMessage {
  type: "interview_ended"
  status: string
}

export interface LiveAnswerStartedMessage {
  type: "answer_started"
}

export interface LiveErrorMessage {
  type: "error"
  code: string
  message?: string
}

export type LiveServerMessage =
  | LiveJoinedMessage
  | LiveQuestionAskedMessage
  | LiveTranscriptReadyMessage
  | LiveConnectionStatusMessage
  | LiveInterviewEndedMessage
  | LiveAnswerStartedMessage
  | LiveErrorMessage

export interface LiveCandidateState {
  interviewToken: string
  sessionId: string | null
}

export interface LiveRecruiterState {
  token: string
  sessionId: string
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

export interface FaceCheckResponse {
  faces: number
  message: string
  flag_type?: string
  severity?: string
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
