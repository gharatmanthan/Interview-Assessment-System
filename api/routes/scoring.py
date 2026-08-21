from fastapi import APIRouter
from api.schemas import ScoringRequest, ScoringResult, CompetencyScoreResponse, ExplanationResponse, FairnessFlagResponse
from app.engine.scoring import score_answer
from app.engine.explainability import explain_score
from app.engine.fairness import audit_bias
from app.engine.rag import retrieve_rubric
from app.core import db

router = APIRouter()


@router.post("/run", response_model=ScoringResult)
def run_scoring(req: ScoringRequest):
    rubric = retrieve_rubric(req.category, req.category)

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

    return ScoringResult(
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
