"""SQLAlchemy models for Alembic autogenerate.

These models mirror the existing SQLite schema from app/core/db.py
for use with Alembic autogenerate.
"""
from sqlalchemy import (
    Column, String, Text, Integer, Real, Boolean, DateTime, ForeignKey,
    UniqueConstraint, Index, text
)
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class RecruiterUser(Base):
    __tablename__ = "recruiter_users"
    username = Column(String(255), primary_key=True)
    password_hash = Column(Text)
    full_name = Column(Text)
    created_at = Column(Text)


class Candidate(Base):
    __tablename__ = "candidates"
    candidate_id = Column(String(255), primary_key=True)
    job_id = Column(String(255), nullable=False)
    name = Column(Text)
    email = Column(Text)
    invite_code = Column(String(255), unique=True)
    status = Column(Text)
    session_id = Column(String(255))
    invited_at = Column(Text)
    resume_path = Column(Text)
    resume_skills = Column(Text)
    experience_years = Column(Real)
    match_score = Column(Real)
    matched_skills = Column(Text)
    missing_skills = Column(Text)
    source = Column(Text, default="manual")
    screening_status = Column(Text, default="pending")
    invite_email_sent = Column(Integer, default=0)
    application_id = Column(String(255))
    interview_mode = Column(String(50))
    mode_status = Column(String(50))
    mode2_score = Column(Real)
    overall_score = Column(Real)
    rank = Column(Integer)
    ranked_at = Column(Text)
    promoted_at = Column(Text)
    mode_assignment_source = Column(String(50))


class JobPosting(Base):
    __tablename__ = "job_postings"
    job_id = Column(String(255), primary_key=True)
    title = Column(Text)
    description = Column(Text)
    required_skills = Column(Text)
    experience_level = Column(Text)
    department = Column(Text)
    num_rounds = Column(Integer)
    time_limit_seconds = Column(Integer)
    adaptive_difficulty = Column(Integer)
    competency_weights = Column(Text)
    created_at = Column(Text)
    screening_threshold = Column(Real, default=60.0)
    application_gmail_label = Column(Text, default="")
    screening_enabled = Column(Integer, default=1)
    auto_invite_enabled = Column(Integer, default=1)
    minimum_experience_years = Column(Real)
    required_education = Column(Text, default="")
    screening_weights = Column(Text)
    created_by = Column(String(255), default="recruiter")
    linkedin_post_status = Column(String(50), default="NOT_POSTED")
    linkedin_post_id = Column(String(255))
    linkedin_post_url = Column(Text)
    linkedin_posted_at = Column(Text)
    linkedin_author_urn = Column(String(255))
    linkedin_last_error = Column(Text)
    linkedin_claim_started_at = Column(Text)
    interview_strategy = Column(String(50), default="AUTO")
    recommended_strategy = Column(String(50), default="")
    strategy_confirmed = Column(Integer, default=0)
    strategy_confirmed_at = Column(Text, default="")
    cohort_finalized_at = Column(Text, default="")


class Session(Base):
    __tablename__ = "sessions"
    session_id = Column(String(255), primary_key=True)
    candidate_name = Column(Text)
    job_title = Column(Text)
    job_id = Column(String(255))
    video_path = Column(Text)
    audio_path = Column(Text)
    transcript = Column(Text)
    started_at = Column(Text)
    completed_at = Column(Text)
    status = Column(Text)
    live_question_id = Column(String(255), default="")


class IntegrityFlag(Base):
    __tablename__ = "integrity_flags"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255))
    flag_type = Column(Text)
    detail = Column(Text)
    severity = Column(Text)
    timestamp = Column(Text)


class CompetencyScore(Base):
    __tablename__ = "competency_scores"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255))
    question_id = Column(Text)
    category = Column(Text)
    score = Column(Real)
    confidence = Column(Real)
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="idx_competency_session_question"),)


class Explanation(Base):
    __tablename__ = "explanations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255))
    question_id = Column(Text)
    summary = Column(Text)
    supporting_phrases = Column(Text)
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="idx_explanation_session_question"),)


class FairnessFlag(Base):
    __tablename__ = "fairness_flags"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255))
    question_id = Column(Text)
    score_delta = Column(Real)
    note = Column(Text)
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="idx_fairness_session_question"),)


class CandidateAccount(Base):
    __tablename__ = "candidate_accounts"
    candidate_id = Column(String(255), primary_key=True)
    password_hash = Column(Text, nullable=False)
    full_name = Column(Text, nullable=False)


class LiveInterview(Base):
    __tablename__ = "live_interviews"
    session_id = Column(String(255), primary_key=True)
    candidate_id = Column(String(255), nullable=False)
    candidate_name = Column(Text, nullable=False)
    question = Column(Text, nullable=False)
    question_index = Column(Integer, default=0)
    transcript = Column(Text, default="")
    status = Column(Text, default="live")
    updated_at = Column(Text, default=datetime.utcnow().isoformat())


class ProcessedEmail(Base):
    __tablename__ = "processed_emails"
    message_id = Column(String(255), primary_key=True)
    job_id = Column(String(255), nullable=False)
    candidate_id = Column(String(255))
    processed_at = Column(Text, nullable=False)


class EmailPollLog(Base):
    __tablename__ = "email_poll_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(Text, nullable=False)
    job_id = Column(String(255), nullable=False)
    job_title = Column(Text, nullable=False)
    total_checked = Column(Integer, default=0)
    invited = Column(Integer, default=0)
    below_threshold = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    mode = Column(Text, default="auto")


class ScheduledInterview(Base):
    __tablename__ = "scheduled_interviews"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String(255), unique=True, nullable=False)
    job_id = Column(String(255), nullable=False)
    scheduled_at = Column(Text, nullable=False)
    duration_minutes = Column(Integer, default=45)
    gcal_event_id = Column(String(255))
    status = Column(String(50), default="scheduled")
    created_at = Column(Text, nullable=False)


class Application(Base):
    __tablename__ = "applications"
    application_id = Column(String(255), primary_key=True)
    job_id = Column(String(255), nullable=False)
    full_name = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    phone = Column(Text, default="")
    resume_path = Column(Text, default="")
    source = Column(String(50), default="apply_portal")
    status = Column(String(50), default="received")
    screening_status = Column(String(50), default="queued")
    candidate_id = Column(String(255))
    submitted_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=False)


class ScreeningJob(Base):
    __tablename__ = "screening_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(String(255), unique=True, nullable=False)
    status = Column(String(50), default="queued")
    attempts = Column(Integer, default=0)
    created_at = Column(Text, nullable=False)
    started_at = Column(Text)
    completed_at = Column(Text)
    last_error = Column(Text)


class ScreeningResult(Base):
    __tablename__ = "screening_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(String(255), unique=True, nullable=False)
    ats_score = Column(Real)
    skills_score = Column(Real)
    experience_score = Column(Real)
    semantic_score = Column(Real)
    education_score = Column(Real)
    keyword_score = Column(Real)
    matched_skills = Column(Text, default="[]")
    missing_skills = Column(Text, default="[]")
    hard_requirements_passed = Column(Integer, default=0)
    hard_requirement_failures = Column(Text, default="[]")
    decision = Column(String(50), default="rejected")
    decision_reason = Column(Text, default="")
    threshold_used = Column(Real)
    scoring_method = Column(String(50), default="")
    matcher_method = Column(String(50), default="")
    confidence = Column(Real, default=0.0)
    created_at = Column(Text, nullable=False)
    completed_at = Column(Text, nullable=False)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(String(255))
    candidate_id = Column(String(255))
    job_id = Column(String(255), nullable=False)
    notification_type = Column(String(50), nullable=False)
    recipient = Column(Text, nullable=False)
    subject = Column(Text, default="")
    body = Column(Text, default="")
    status = Column(String(20), default="pending")
    attempts = Column(Integer, default=0)
    created_at = Column(Text, nullable=False)
    sent_at = Column(Text)
    last_error = Column(Text)
    __table_args__ = (
        UniqueConstraint("application_id", "notification_type", "recipient", name="unique_app_type_recipient"),
    )


class InterviewInvite(Base):
    __tablename__ = "interview_invites"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String(255), nullable=False)
    job_id = Column(String(255), default="")
    application_id = Column(String(255))
    token = Column(String(255), unique=True, nullable=False)
    status = Column(String(20), default="active")
    created_at = Column(Text, nullable=False)
    expires_at = Column(Text, nullable=False)
    consumed_at = Column(Text)


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(String(255), nullable=False)
    event = Column(Text, nullable=False)
    detail = Column(Text, default="")
    created_at = Column(Text, nullable=False)


class ScreeningJob(Base):
    __tablename__ = "screening_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(String(255), unique=True, nullable=False)
    status = Column(String(20), default="queued")
    attempts = Column(Integer, default=0)
    created_at = Column(Text, nullable=False)
    started_at = Column(Text)
    completed_at = Column(Text)
    last_error = Column(Text)


class LinkedInConnection(Base):
    __tablename__ = "linkedin_connections"
    recruiter_username = Column(String(255), primary_key=True)
    linkedin_member_id = Column(String(255), nullable=False)
    member_name = Column(Text, default="")
    member_email = Column(Text, default="")
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, default="")
    token_expires_at = Column(Text, default="")
    scope = Column(Text, default="")
    connected_at = Column(Text, nullable=False)


class LinkedInOAuthState(Base):
    __tablename__ = "linkedin_oauth_states"
    state = Column(String(255), primary_key=True)
    recruiter_username = Column(String(255), nullable=False)
    redirect_uri = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False)
    expires_at = Column(Text, nullable=False)
    used_at = Column(Text)


class QuestionTranscript(Base):
    __tablename__ = "question_transcripts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False)
    question_id = Column(String(255), nullable=False)
    transcript = Column(Text, default="")
    created_at = Column(Text, nullable=False)
    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="unique_session_question"),
    )


class SessionQuestion(Base):
    __tablename__ = "session_questions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False)
    question_index = Column(Integer, nullable=False)
    question_id = Column(String(255), nullable=False)
    question_text = Column(Text, nullable=False)
    category = Column(Text, default="")
    competency = Column(Text, default="")
    difficulty = Column(Text, default="medium")
    source = Column(String(50), default="bank")
    created_at = Column(Text, nullable=False)
    asked = Column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("session_id", "question_index", name="unique_session_qindex"),
        UniqueConstraint("session_id", "question_id", name="unique_session_qid"),
    )


class LinkedInConnection(Base):
    __tablename__ = "linkedin_connections"
    recruiter_username = Column(String(255), primary_key=True)
    linkedin_member_id = Column(String(255), nullable=False)
    member_name = Column(Text, default="")
    member_email = Column(Text, default="")
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, default="")
    token_expires_at = Column(Text, default="")
    scope = Column(Text, default="")
    connected_at = Column(Text, nullable=False)


class LinkedInOAuthState(Base):
    __tablename__ = "linkedin_oauth_states"
    state = Column(String(255), primary_key=True)
    recruiter_username = Column(String(255), nullable=False)
    redirect_uri = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False)
    expires_at = Column(Text, nullable=False)
    used_at = Column(Text)


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(String(255), nullable=False)
    event = Column(Text, nullable=False)
    detail = Column(Text, default="")
    created_at = Column(Text, nullable=False)


class ScreeningJob(Base):
    __tablename__ = "screening_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(String(255), unique=True, nullable=False)
    status = Column(String(20), default="queued")
    attempts = Column(Integer, default=0)
    created_at = Column(Text, nullable=False)
    started_at = Column(Text)
    completed_at = Column(Text)
    last_error = Column(Text)


class EmailPollLog(Base):
    __tablename__ = "email_poll_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(Text, nullable=False)
    job_id = Column(String(255), nullable=False)
    job_title = Column(Text, nullable=False)
    total_checked = Column(Integer, default=0)
    invited = Column(Integer, default=0)
    below_threshold = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    mode = Column(Text, default="auto")


# Import all models to register them
from . import *  # noqa

# Export metadata for Alembic
from sqlalchemy import MetaData
metadata = MetaData()

# Reflect all tables
from sqlalchemy import inspect
from sqlalchemy import create_engine

# This will be populated by the environment
target_metadata = None