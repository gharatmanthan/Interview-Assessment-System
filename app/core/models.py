"""
Shared data contract for the whole app.

This is the ONE file everyone is allowed to depend on across module
boundaries. If your module needs to hand data to someone else's module,
it goes through one of these shapes — never import another person's
internal functions directly.

Owner: shared (changes require a quick group message, not a silent edit).
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class IntegrityFlag:
    """One suspicious-activity flag raised during a session.
    Produced by: app/candidate/integrity.py (Member A)
    Consumed by: app/reports/ (Member C) for the Integrity Log page
    """
    session_id: str
    flag_type: str          # e.g. "remote_access_port", "vm_detected", "extra_person", "gaze_offscreen"
    detail: str              # human-readable description, e.g. "TeamViewer port 5938 open"
    severity: str = "medium"  # "low" | "medium" | "high"
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CompetencyScore:
    """One question's competency score.
    Produced by: app/engine/scoring.py (Member B)
    Consumed by: app/reports/ (Member C) for Candidate Reports page
    """
    session_id: str
    question_id: str
    category: str            # e.g. "DSA", "System Design", "Communication"
    score: float              # 0-100
    confidence: float = 0.0   # model's confidence in this score, 0-1


@dataclass
class ExplanationItem:
    """Why a score was given for one answer.
    Produced by: app/engine/explainability.py (Member B)
    Consumed by: app/reports/ (Member C)
    """
    session_id: str
    question_id: str
    summary: str              # 1-2 sentence plain-language rationale
    supporting_phrases: list = field(default_factory=list)  # phrases from transcript that drove the score


@dataclass
class FairnessFlag:
    """A bias/fairness signal from the counterfactual audit.
    Produced by: app/engine/fairness.py (Member B)
    Consumed by: app/reports/ (Member C) for Bias Audit page
    """
    session_id: str
    question_id: str
    score_delta: float        # difference observed between counterfactual demographic variants
    note: str = ""


@dataclass
class RecruiterUser:
    """A recruiter account. Simple auth — gates the app before MainWindow shows.
    Owner: Member C
    """
    username: str
    password_hash: str
    full_name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Candidate:
    """An invited candidate for a specific job posting — exists from the
    moment a recruiter invites them, before any InterviewSession starts.
    This is what makes the dashboard's candidate list complete: invited-but-
    not-started candidates show up here, not just completed sessions.
    Owner: Member C
    """
    candidate_id: str
    job_id: str
    name: str
    email: str
    invite_code: str               # unique code/link the candidate uses to start
    status: str = "invited"         # "invited" | "in_progress" | "completed" | "expired"
    session_id: Optional[str] = None  # linked once they actually start the interview
    invited_at: datetime = field(default_factory=datetime.utcnow)
    # Resume data (Objective 2 deliverable — filled via app/engine/resume_parser.py
    # + app/engine/jd_matcher.py once a resume is attached)
    resume_path: Optional[str] = None
    resume_skills: list = field(default_factory=list)
    experience_years: Optional[float] = None
    match_score: Optional[float] = None
    matched_skills: list = field(default_factory=list)
    missing_skills: list = field(default_factory=list)
    source: str = "manual"              # "manual" | "email_auto" | "apply_portal"
    screening_status: str = "pending"   # "pending" | "passed_threshold" | "below_threshold"
    invite_email_sent: bool = False     # True only after confirmed Gmail send success
    application_id: Optional[str] = None  # links a candidate back to the application that created them
    # Interview-mode routing progression ('' until assigned).
    interview_mode: str = ""
    mode_status: str = ""
    mode2_score: Optional[float] = None
    overall_score: Optional[float] = None
    rank: Optional[int] = None
    ranked_at: Optional[str] = None
    promoted_at: Optional[str] = None
    mode_assignment_source: str = ""


@dataclass
class Application:
    """A candidate-submitted application for one job posting. Exists before
    any Candidate is created — applicants who fail screening still have a
    durable record here. Lifecycle owner: screening service.
    """
    application_id: str
    job_id: str
    full_name: str
    email: str
    phone: str = ""
    resume_path: str = ""
    source: str = "apply_portal"          # "apply_portal" | "email_auto" | "manual"
    status: str = "received"              # received|screening|passed|rejected|manual_review|candidate_created|invite_pending|invite_sent
    screening_status: str = "queued"      # queued|processing|completed|failed
    candidate_id: Optional[str] = None
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ScreeningJob:
    """Lightweight async queue item — one per application. Worker claims
    queued rows, retries failures up to MAX_ATTEMPTS.
    """
    application_id: str
    id: Optional[int] = None
    status: str = "queued"                # queued|processing|completed|failed
    attempts: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None


@dataclass
class ScreeningResult:
    """Explainable ATS screening outcome for one application. Persisted once
    (UNIQUE application_id) so re-processing is idempotent.
    """
    application_id: str
    id: Optional[int] = None
    ats_score: Optional[float] = None
    skills_score: Optional[float] = None
    experience_score: Optional[float] = None
    semantic_score: Optional[float] = None
    education_score: Optional[float] = None
    keyword_score: Optional[float] = None
    matched_skills: list = field(default_factory=list)
    missing_skills: list = field(default_factory=list)
    hard_requirements_passed: bool = False
    hard_requirement_failures: list = field(default_factory=list)
    decision: str = "rejected"            # passed|rejected|manual_review
    decision_reason: str = ""
    threshold_used: Optional[float] = None  # threshold applied at screening time
    scoring_method: str = ""              # e.g. "weighted_components"
    matcher_method: str = ""              # llm_semantic|keyword_overlap
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NotificationOutbox:
    """Outbox pattern: side effects (email) are recorded here as a durable
    event and drained asynchronously. Gmail availability never blocks the
    application/screening transaction.
    """
    job_id: str
    notification_type: str                # hr_shortlist | interview_invite
    recipient: str
    subject: str = ""
    body: str = ""
    id: Optional[int] = None
    application_id: Optional[str] = None
    candidate_id: Optional[str] = None
    status: str = "pending"               # pending|sending|sent|failed
    attempts: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    last_error: Optional[str] = None


@dataclass
class InterviewInvite:
    """A cryptographically-random, expirable interview invite for one
    candidate. Consumed (one-time) when the candidate starts their session.
    """
    candidate_id: str
    token: str
    job_id: str = ""
    application_id: Optional[str] = None
    id: Optional[int] = None
    status: str = "active"                # active|consumed|expired
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(days=30))
    consumed_at: Optional[datetime] = None


@dataclass
class JobPosting:
    """A recruiter-created job posting — drives RAG-grounded question
    selection and scoring for every candidate interviewed against it.
    Owner: Member C (creation UI) — read by Member B's rag.py + question_selector.py
    """
    job_id: str
    title: str
    description: str
    required_skills: list          # e.g. ["Python", "SQL", "System Design"]
    experience_level: str          # "Fresher" | "Junior" | "Mid" | "Senior"
    department: str
    num_rounds: int = 1
    time_limit_seconds: int = 120
    adaptive_difficulty: bool = True
    # competency category -> weight (0-100), should sum to 100
    competency_weights: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    screening_threshold: float = 60.0       # 0-100, recruiter-configurable per job
    application_gmail_label: str = ""       # Gmail label to watch for applications
    # Automated screening configuration (candidate-first pipeline)
    screening_enabled: bool = True          # master switch for auto-screening this job
    auto_invite_enabled: bool = True        # send interview invite when candidate passes
    minimum_experience_years: Optional[float] = None  # hard requirement if set
    required_education: str = ""            # hard requirement if non-empty (e.g. "B.Tech")
    screening_weights: dict = field(default_factory=lambda: {
        "skills": 40, "experience": 20, "semantic": 20, "education": 10, "keyword": 10,
    })  # configurable ATS component weights (percent, should sum to 100)
    created_by: str = "recruiter"           # owning recruiter username (authorization root)

    # Interview-mode allocation (hybrid routing workflow). AUTO follows the
    # final shortlist count; the recruiter explicitly confirms before any
    # invitations are generated.
    interview_strategy: str = "AUTO"          # AUTO | MODE_1_ONLY | MODE_2_THEN_MODE_1
    recommended_strategy: str = ""            # computed recommendation (AUTO)
    strategy_confirmed: bool = False
    strategy_confirmed_at: str = ""
    cohort_finalized_at: str = ""


@dataclass
class InterviewSession:
    """The top-level record tying one interview together.
    Created by: app/candidate/capture.py (Member A) when a session starts
    Updated by: app/engine/ (Member B) as scoring completes
    Read by: app/reports/ (Member C) for all dashboard/report views
    """
    session_id: str
    candidate_name: str
    job_title: str
    job_id: Optional[str] = None   # links back to JobPosting.job_id
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    transcript: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "in_progress"   # "in_progress" | "scoring" | "complete"
    live_question_id: str = ""   # Phase 3A: currently-active question ('' = none)


@dataclass
class ProcessedEmail:
    """Record of a Gmail message that has been processed by the email intake pipeline.
    Prevents re-processing the same email on every poll.
    """
    message_id: str                        # Gmail's unique message ID (primary key)
    job_id: str
    candidate_id: Optional[str] = None     # None if resume parsing failed before Candidate creation
    processed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class LinkedinConnection:
    """One recruiter's LinkedIn OAuth connection (member posting).

    Stored per recruiter in SQLite (not the machine-global settings.json) so
    Recruiter A can never see or reuse Recruiter B's LinkedIn token. The author
    identity is derived server-side from the authenticated member (never from
    the frontend)."
    """
    recruiter_username: str
    linkedin_member_id: str
    member_name: str = ""
    member_email: str = ""
    access_token: str = ""
    refresh_token: str = ""
    token_expires_at: str = ""
    scope: str = ""
    connected_at: datetime = field(default_factory=datetime.utcnow)
