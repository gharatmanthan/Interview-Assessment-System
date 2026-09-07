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
class InterviewSession:
    """The top-level record tying one interview together.
    Created by: app/candidate/capture.py (Member A) when a session starts
    Updated by: app/engine/ (Member B) as scoring completes
    Read by: app/reports/ (Member C) for all dashboard/report views
    """
    session_id: str
    candidate_name: str
    job_title: str
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    transcript: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "in_progress"   # "in_progress" | "scoring" | "complete"
