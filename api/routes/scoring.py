import logging

from fastapi import APIRouter
from api.schemas import ScoringRequest, ScoringResult, CompetencyScoreResponse, ExplanationResponse, FairnessFlagResponse
from app.engine.scoring import get_ml_score, score_answer
from app.engine.explainability import explain_score
from app.engine.fairness import audit_bias
from app.engine.rag import retrieve_rubric
from app.core import db

logger = logging.getLogger(__name__)

router = APIRouter()


def _job_context(session_id: str) -> tuple:
    """Best-effort lookup of (job_title, job_description) for RAG retrieval."""
    session = db.get_session(session_id)
    if not session:
        return "", ""
    job = db.get_job_posting(session.get("job_id")) if session.get("job_id") else None
    if not job:
        return session.get("job_title") or "", ""
    return job.get("title") or "", job.get("description") or ""


@router.post("/run", response_model=ScoringResult)
def run_scoring(req: ScoringRequest):
    # Ground rubric retrieval in the ACTUAL job description when the session
    # links to one; falls back to static category rubric otherwise.
    job_title, jd_text = _job_context(req.session_id)
    jd_text = req.job_description or jd_text
    rubric = retrieve_rubric(job_title or req.category, req.category, jd_text)

    score = score_answer(
        session_id=req.session_id,
        question_id=req.question_id,
        category=req.category,
        transcript=req.transcript,
        rubric=rubric,
    )
    db.save_competency_score(score)

    explanation = explain_score(
        session_id=req.session_id,
        question_id=req.question_id,
        transcript=req.transcript,
        score=score.score,
    )
    db.save_explanation(explanation)

    fairness = audit_bias(
        session_id=req.session_id,
        question_id=req.question_id,
        transcript=req.transcript,
        original_score=score.score,
    )
    db.save_fairness_flag(fairness)

    # Third, independent scoring signal (trained RandomForest). Optional by
    # design: None when no model has been trained yet.
    ml_score = get_ml_score(req.transcript)
    if ml_score is not None:
        logger.info("run_scoring[%s/%s]: ML model score %.1f (surfaced alongside primary score)",
                    req.session_id, req.question_id, ml_score)

    return ScoringResult(
        ml_score=ml_score,
        rubric_source=("retrieval:" + rubric["retrieval_backend"]) if rubric.get("retrieval_used")
        else "static_category_lookup",
        score=CompetencyScoreResponse(
            session_id=score.session_id,
            question_id=score.question_id,
            category=score.category,
            score=score.score,
            confidence=score.confidence,
        ),
        explanation=ExplanationResponse(
            session_id=explanation.session_id,
            question_id=explanation.question_id,
            summary=explanation.summary,
            supporting_phrases=explanation.supporting_phrases,
        ),
        fairness=FairnessFlagResponse(
            session_id=fairness.session_id,
            question_id=fairness.question_id,
            score_delta=fairness.score_delta,
            note=fairness.note,
        ),
    )
