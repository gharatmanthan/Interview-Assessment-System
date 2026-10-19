"""Request and response models for the InterviewIQ API."""
from typing import Any

from pydantic import BaseModel, Field


class StartInterviewRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    candidate_name: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    question_index: int = Field(default=0, ge=0)


class InterviewUpdateRequest(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    question_index: int | None = Field(default=None, ge=0)
    transcript: str | None = Field(default=None, max_length=100000)
    status: str | None = Field(
        default=None, pattern="^(live|complete|completed|cancelled)$"
    )
    pending_question: str | None = Field(default=None, max_length=2000)
    pending_status: str | None = Field(
        default=None, pattern="^(none|pending|approved)$"
    )
    question_count: int | None = Field(default=None, ge=0)
    interview_context: str | None = Field(default=None, max_length=100000)

    def database_fields(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ApproveQuestionRequest(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=2000)


class CandidateCredentials(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class CandidateAccountRequest(CandidateCredentials):
    full_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    identity: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class JobPostingRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)


class FrameRequest(BaseModel):
    image: str = Field(min_length=1, max_length=500000)


class IntegrityFlagRequest(BaseModel):
    flag_type: str = Field(min_length=1, max_length=100)
    detail: str = Field(min_length=1, max_length=2000)
    severity: str = Field(pattern="^(low|medium|high)$")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    timestamp: str | None = None


class IntegrityReviewRequest(BaseModel):
    status: str = Field(pattern="^(open|reviewed|dismissed)$")
    note: str = Field(default="", max_length=2000)


class InvitationRequest(BaseModel):
    job_id: int = Field(ge=1)
    expires_in_hours: int = Field(default=72, ge=1, le=720)


class PublicRegistrationRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)
