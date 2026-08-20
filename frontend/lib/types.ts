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
  llm_api_key: string
  export_dir: string
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
}
