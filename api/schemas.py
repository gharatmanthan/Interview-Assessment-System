"""
Pydantic schemas matching app/core/models.py dataclasses.
These are API request/response models only — the dataclasses remain source of truth.
"""
from pydantic import BaseModel, field_validator
from typing import Optional, Union
from datetime import datetime

from app.core.validation import is_valid_email, normalize_email


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    success: bool
    message: str
    username: Optional[str] = None
    token: Optional[str] = None
    expires_at: Optional[str] = None


class CurrentUserResponse(BaseModel):
    username: str
    full_name: str = ""


class ValidateCodeRequest(BaseModel):
    invite_code: str


class ConsentRequest(BaseModel):
    session_id: str = ""  # deprecated/ignored — the server resolves the authoritative session
    candidate_id: str = ""
    interview_token: str = ""


class StartSessionRequest(BaseModel):
    session_id: str = ""  # deprecated/ignored — the server resolves the authoritative session
    candidate_id: str = ""
    job_id: str = ""
    interview_token: str = ""


class ValidateCodeResponse(BaseModel):
    valid: bool
    candidate: Optional[dict] = None
    job: Optional[dict] = None
    message: Optional[str] = None
    interview_token: Optional[str] = None
    expires_at: Optional[str] = None


class SubmitAnswerRequest(BaseModel):
    session_id: str
    question_id: str
    category: str
    transcript: str
    interview_token: str = ""


class CompleteSessionRequest(BaseModel):
    session_id: str
    interview_token: str = ""


class JobPostingCreate(BaseModel):
    # Canonical id is assigned server-side on create; the client may omit it.
    job_id: str = ""
    title: str
    description: str
    required_skills: list[str] = []
    experience_level: str = "Junior"
    department: str = ""
    num_rounds: int = 1
    time_limit_seconds: int = 120
    adaptive_difficulty: bool = True
    competency_weights: dict[str, float] = {}
    screening_threshold: float = 60.0
    application_gmail_label: str = ""
    screening_enabled: bool = True
    auto_invite_enabled: bool = True
    minimum_experience_years: Optional[float] = None
    required_education: str = ""
    screening_weights: dict[str, float] = {
        "skills": 40, "experience": 20, "semantic": 20, "education": 10, "keyword": 10,
    }


class JobPostingResponse(BaseModel):
    job_id: str
    title: str
    description: str
    required_skills: list[str]
    experience_level: str
    department: str
    num_rounds: int
    time_limit_seconds: int
    adaptive_difficulty: bool
    competency_weights: dict[str, float]
    created_at: Optional[str] = None
    screening_threshold: float = 60.0
    application_gmail_label: str = ""
    screening_enabled: bool = True
    auto_invite_enabled: bool = True
    minimum_experience_years: Optional[float] = None
    required_education: str = ""
    screening_weights: dict[str, float] = {}
    created_by: str = "recruiter"
    linkedin_post_status: str = "NOT_POSTED"
    linkedin_post_id: Optional[str] = None
    linkedin_post_url: Optional[str] = None
    linkedin_posted_at: Optional[str] = None
    linkedin_author_urn: Optional[str] = None
    linkedin_last_error: Optional[str] = None
    # Interview-mode routing (job-level strategy)
    interview_strategy: str = "AUTO"
    recommended_strategy: str = "AUTO"
    strategy_confirmed: bool = False
    strategy_confirmed_at: Optional[str] = None
    cohort_finalized_at: Optional[str] = None


class JobStrategyConfirmRequest(BaseModel):
    """Recruiter confirmation of the job's interview-mode strategy. AUTO uses
    the recommendation computed from the finalized shortlist; the explicit
    modes override it. Invitations are only enqueued after confirmation."""
    strategy: str = "AUTO"


class JobStrategyStatusResponse(BaseModel):
    """Live interview-mode routing status for a job's screening cohort."""
    job_id: str
    screening_pending: int = 0
    shortlisted: int = 0
    cohort_finalized: bool = False
    recommended_strategy: str = "AUTO"
    interview_strategy: str = "AUTO"
    strategy_confirmed: bool = False
    strategy_confirmed_at: Optional[str] = None
    cohort_finalized_at: Optional[str] = None
    interview_capacity: int = 6


class LinkedInStatusResponse(BaseModel):
    connected: bool
    member_name: str = ""
    member_email: str = ""
    connected_at: Optional[str] = None
    member_author_urn: str = ""


class LinkedInConnectResponse(BaseModel):
    authorization_url: str = ""


class LinkedInPreviewResponse(BaseModel):
    job_id: str
    content: str
    public_url: str
    linkedin_post_status: str = "NOT_POSTED"
    connected: bool = False


class LinkedInPublishRequest(BaseModel):
    content: str


class LinkedInPublishResponse(BaseModel):
    success: bool
    job_id: str
    linkedin_post_status: str = "NOT_POSTED"
    post_id: Optional[str] = None
    post_url: Optional[str] = None


class CandidateCreate(BaseModel):
    candidate_id: str
    job_id: str
    name: str
    email: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        normalized = normalize_email(v)
        if not is_valid_email(normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class CandidateResponse(BaseModel):
    candidate_id: str
    job_id: str
    name: str
    email: str
    invite_code: str
    status: str = "invited"
    session_id: Optional[str] = None
    invited_at: Optional[str] = None
    resume_path: Optional[str] = None
    resume_skills: list[str] = []
    experience_years: Optional[float] = None
    match_score: Optional[float] = None
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    job_title: Optional[str] = None
    source: str = "manual"
    screening_status: str = "pending"
    invite_email_sent: bool = False
    application_id: Optional[str] = None
    screening_result: Optional[dict] = None
    # Interview-mode routing (candidate-level)
    interview_mode: str = ""
    mode_status: str = ""
    mode2_score: Optional[float] = None
    overall_score: Optional[float] = None
    rank: Optional[int] = None
    ranked_at: Optional[str] = None
    promoted_at: Optional[str] = None
    mode_assignment_source: str = ""


class SessionCreate(BaseModel):
    candidate_id: str
    session_id: str = ""  # ignored for authority; server resolves the real id
    candidate_name: str = ""
    job_title: str = ""
    job_id: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    candidate_name: str
    job_title: str
    job_id: Optional[str] = None
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    transcript: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    status: str = "in_progress"


class TranscriptionResponse(BaseModel):
    question_id: str
    transcript: str
    audio_path: Optional[str] = None


class QuestionItem(BaseModel):
    question_index: int
    question_id: str
    question_text: str
    category: str
    competency: str
    difficulty: str
    source: str


class SelectQuestionsRequest(BaseModel):
    session_id: str
    num_questions: int = 10
    force_generated: bool = False


class SelectQuestionsResponse(BaseModel):
    session_id: str
    questions: list[QuestionItem]
    locked: bool = True


class CandidateQuestionsResponse(BaseModel):
    session_id: str
    questions: list[QuestionItem]


class CandidateProgressResponse(BaseModel):
    """Server-authoritative Mode 2 interview progress.

    The candidate UI recovers its position from this endpoint (refresh-proof)
    instead of trusting browser sessionStorage. current_question is the first
    locked question (by question_index) that has no competency score yet.
    """
    session_id: str
    interview_status: str                 # not_ready | ready | in_progress | completed
    total_questions: int
    answered_questions: int
    remaining_questions: int
    current_question: Optional[QuestionItem] = None
    completed: bool = False


class InterviewStatusResponse(BaseModel):
    """Recruiter-facing Mode 2 interview status + question-set summary.

    Derives the high-level state (Not prepared / Ready / In progress /
    Completed) from the session's locked question set + scored answers, so the
    recruiter never needs a live connection to see where the candidate is.
    """
    candidate_id: str
    session_id: str
    interview_status: str                 # not_ready | ready | in_progress | completed
    locked: bool
    total_questions: int
    answered_questions: int
    categories: list[str] = []
    candidate_status: str = ""


class ScoringRequest(BaseModel):
    session_id: str
    question_id: str
    category: str
    transcript: str
    job_description: Optional[str] = None  # overrides session-linked JD for RAG retrieval


class CompetencyScoreResponse(BaseModel):
    session_id: str
    question_id: str
    category: str
    score: float
    confidence: float


class ExplanationResponse(BaseModel):
    session_id: str
    question_id: str
    summary: str
    supporting_phrases: list[str] = []


class FairnessFlagResponse(BaseModel):
    session_id: str
    question_id: str
    score_delta: float
    note: str = ""


class ScoringResult(BaseModel):
    score: CompetencyScoreResponse
    explanation: ExplanationResponse
    fairness: FairnessFlagResponse
    ml_score: Optional[float] = None          # trained-model signal; None until trained
    rubric_source: str = "static_category_lookup"  # "retrieval:<backend>" when RAG ran


class DashboardStats(BaseModel):
    interviews_conducted: int
    avg_explainability_score: float
    bias_flags_raised: int
    integrity_flags: int
    candidates_by_status: dict[str, int]


class CandidateReport(BaseModel):
    session: dict
    scores: list[dict]
    explanations: list[dict]
    overall_score: float


class ComparisonRow(BaseModel):
    session_id: str
    candidate_name: str
    job_title: str
    overall_score: float
    category_scores: dict[str, float]


class IntegrityFlagResponse(BaseModel):
    id: Optional[int] = None
    session_id: str
    flag_type: str
    detail: str
    severity: str = "medium"
    timestamp: Optional[str] = None
    candidate_name: Optional[str] = None
    job_title: Optional[str] = None


class IntegrityFlagCreate(BaseModel):
    """One integrity flag produced by a client-side (local) scan.

    In remote mode the candidate's Electron app runs port/process scans on
    its own machine and POSTs the results here; the central server just
    persists them so they show up in the recruiter's Integrity Log.
    """
    session_id: str
    flag_type: str
    detail: str
    severity: str = "medium"
    timestamp: Optional[str] = None


class IntegrityFlagBatch(BaseModel):
    flags: list[IntegrityFlagCreate]


class SettingsUpdate(BaseModel):
    camera_index: Optional[int] = None
    mic_device: Optional[Union[str, int]] = None
    llm_provider: Optional[str] = None
    export_dir: Optional[str] = None
    # Auto-scheduling config (recruiter availability / interview preferences)
    interview_duration_minutes: Optional[int] = None
    interview_buffer_minutes: Optional[int] = None
    work_start_hour: Optional[int] = None
    work_end_hour: Optional[int] = None
    scheduling_horizon_days: Optional[int] = None
    working_days: Optional[list[int]] = None
    excluded_dates: Optional[list[str]] = None


class SettingsResponse(BaseModel):
    camera_index: int = 0
    mic_device: Union[str, int] = "default"
    llm_provider: str = "Groq"
    export_dir: str = ""
    gmail_connected: bool = False
    gmail_user: str = ""
    calendar_connected: bool = False
    calendar_user: str = ""
    interview_duration_minutes: int = 45
    interview_buffer_minutes: int = 10
    work_start_hour: int = 9
    work_end_hour: int = 18
    scheduling_horizon_days: int = 30
    working_days: list[int] = [0, 1, 2, 3, 4]
    excluded_dates: list[str] = []


class DeviceInfo(BaseModel):
    name: str
    index: Optional[int] = None
    device_class: str  # "camera", "microphone"


class ResendInviteResponse(BaseModel):
    invite_code: str
    message: str


class GmailStatusResponse(BaseModel):
    connected: bool
    email: str = ""


class GmailConnectResponse(BaseModel):
    success: bool
    email: str = ""
    message: str = ""


class CalendarStatusResponse(BaseModel):
    connected: bool
    email: str = ""


class CalendarConnectResponse(BaseModel):
    success: bool
    email: str = ""
    message: str = ""


class ScheduledInterviewResponse(BaseModel):
    id: Optional[int] = None
    candidate_id: str
    job_id: str
    scheduled_at: Optional[str] = None
    duration_minutes: int = 45
    gcal_event_id: Optional[str] = None
    status: str = "scheduled"
    created_at: Optional[str] = None
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_status: Optional[str] = None
    job_title: Optional[str] = None


class AllocateSlotRequest(BaseModel):
    candidate_id: str
    job_id: str


class AllocateSlotResponse(BaseModel):
    success: bool
    scheduled_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    message: str = ""


class AvailabilityResponse(BaseModel):
    connected: bool
    slots: list[str] = []
    message: str = ""


class EmailCheckRequest(BaseModel):
    job_id: str


class EmailCheckResponse(BaseModel):
    results: list[dict]
    summary: str


class PollLogEntry(BaseModel):
    id: int
    run_at: str
    job_id: str
    job_title: str
    total_checked: int
    invited: int
    below_threshold: int
    skipped: int
    failed: int
    mode: str


class PollLogResponse(BaseModel):
    logs: list[PollLogEntry]


class PublicJobResponse(BaseModel):
    job_id: str
    title: str
    description: str
    required_skills: list[str]
    experience_level: str
    department: str


class ApplyRequest(BaseModel):
    name: str
    email: str


class ApplyResponse(BaseModel):
    success: bool
    candidate_id: str
    match_score: float
    screening_status: str
    invite_code: str
    message: str


class PublicApplyResponse(BaseModel):
    """Stored-first submission — processing happens asynchronously."""
    success: bool = True
    status: str = "received"
    application_id: str
    message: str = "Application received and queued for screening."


class PublicApplyRequest(BaseModel):
    name: str
    email: str
    phone: str = ""


class ApplicationResponse(BaseModel):
    application_id: str
    job_id: str
    full_name: str
    email: str
    phone: str = ""
    resume_path: str = ""
    source: str = "apply_portal"
    status: str = "received"
    screening_status: str = "queued"
    candidate_id: Optional[str] = None
    submitted_at: Optional[str] = None
    updated_at: Optional[str] = None


class ScreeningResultResponse(BaseModel):
    application_id: str
    ats_score: Optional[float] = None
    skills_score: Optional[float] = None
    experience_score: Optional[float] = None
    semantic_score: Optional[float] = None
    education_score: Optional[float] = None
    keyword_score: Optional[float] = None
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    hard_requirements_passed: bool = False
    hard_requirement_failures: list[str] = []
    decision: str = "rejected"
    decision_reason: str = ""
    threshold_used: Optional[float] = None
    scoring_method: str = ""
    matcher_method: str = ""
    confidence: float = 0.0
    completed_at: Optional[str] = None


class ApplicationEventResponse(BaseModel):
    event: str
    detail: str = ""
    created_at: Optional[str] = None


class ApplicationDetailResponse(ApplicationResponse):
    screening_result: Optional[ScreeningResultResponse] = None
    notifications: list[dict] = []
    events: list[dict] = []


class ApplicationListResponse(BaseModel):
    applications: list[ApplicationDetailResponse]


class JobPipelineStat(BaseModel):
    job_id: str
    title: str
    applications: int = 0
    screening_pending: int = 0
    shortlisted: int = 0
    rejected: int = 0
    manual_review: int = 0
    invites_sent: int = 0
    interviews_completed: int = 0
    email_failures: int = 0


class JobPipelineStatsResponse(BaseModel):
    jobs: list[JobPipelineStat]


class NotificationOutboxResponse(BaseModel):
    id: Optional[int] = None
    application_id: Optional[str] = None
    candidate_id: Optional[str] = None
    job_id: str
    notification_type: str
    recipient: str
    status: str = "pending"
    attempts: int = 0
    subject: str = ""
    body: str = ""
    created_at: Optional[str] = None
    sent_at: Optional[str] = None
    last_error: Optional[str] = None


class InterviewInviteResponse(BaseModel):
    id: Optional[int] = None
    candidate_id: str
    job_id: str = ""
    application_id: Optional[str] = None
    token: Optional[str] = None
    status: str = "active"
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    consumed_at: Optional[str] = None


class FaceCheckRequest(BaseModel):
    """Face detection check during interview. The candidate's Electron/renderer
    captures a frame from the webcam and sends it for face-count verification.
    """
    frame_base64: str
    interview_token: str = ""


class FaceCheckResponse(BaseModel):
    faces: int
    message: str
    flag_type: Optional[str] = None
    severity: Optional[str] = None
