"""
Shared data contract for the whole app.

This is the ONE file everyone is allowed to depend on across module
boundaries. If your module needs to hand data to someone else's module,
it goes through one of these shapes — never import another person's
internal functions directly.

Owner: shared (changes require a quick group message, not a silent edit).
"""
from dataclasses import dataclass, field
from datetime import datetime
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
    confidence: float = 0.0   # detector confidence, 0-1; review signal, not proof
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
    evaluation_source: str = "heuristic"


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
    evaluation_source: str = "heuristic"


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
