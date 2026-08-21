"""
Pydantic schemas matching app/core/models.py dataclasses.
These are API request/response models only — the dataclasses remain source of truth.
"""
from pydantic import BaseModel
from typing import Optional, Union
from datetime import datetime


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


class JobPostingCreate(BaseModel):
    job_id: str
    title: str
    description: str
    required_skills: list[str] = []
    experience_level: str = "Junior"
    department: str = ""
    num_rounds: int = 1
    time_limit_seconds: int = 120
    adaptive_difficulty: bool = True
    competency_weights: dict[str, float] = {}


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


class CandidateCreate(BaseModel):
    candidate_id: str
    job_id: str
    name: str
    email: str


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


class SessionCreate(BaseModel):
    session_id: str
    candidate_name: str
    job_title: str
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


class ScoringRequest(BaseModel):
    session_id: str
    question_id: str
    category: str
    transcript: str


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


class SettingsUpdate(BaseModel):
    camera_index: Optional[int] = None
    # The desktop UI stores the mic as a device index (int); accept both so
    # saving settings from the UI never breaks GET /api/settings validation.
    mic_device: Optional[Union[str, int]] = None
    llm_provider: Optional[str] = None
    llm_api_key: Optional[str] = None
    export_dir: Optional[str] = None


class SettingsResponse(BaseModel):
    camera_index: int = 0
    mic_device: Union[str, int] = "default"
    llm_provider: str = "Groq"
    llm_api_key: str = ""
    export_dir: str = ""


class DeviceInfo(BaseModel):
    name: str
    index: Optional[int] = None
    device_class: str  # "camera", "microphone"


class ResendInviteResponse(BaseModel):
    invite_code: str
    message: str
