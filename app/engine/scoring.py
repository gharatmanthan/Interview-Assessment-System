"""
Owner: Member B

Scores a transcript against the retrieved rubric. Uses the LLM (via
llm_client) when GROQ_API_KEY is configured; otherwise falls back to a
transparent, rule-based heuristic so the pipeline still produces a real
score end-to-end without any setup. Which path ran is always logged, and
LLM failures fall back with a logged reason — never silently.
"""
import logging
import re

from app.core.models import CompetencyScore
from app.engine import llm_client

logger = logging.getLogger(__name__)

FILLER_WORDS = {"um", "uh", "like", "you know", "sort", "kind", "basically", "actually", "literally"}


def _heuristic_score(transcript: str, rubric: dict) -> tuple[float, float]:
    """
    Rewards keyword overlap with rubric criteria + answer substance,
    penalizes filler words. Low confidence by design — this is a stand-in
    for real semantic scoring, not a claim of real evaluation quality.
    """
    words = re.findall(r"[a-zA-Z']+", transcript.lower())
    if not words:
        return 0.0, 0.15

    criteria_terms = set()
    for c in rubric.get("criteria", []):
        criteria_terms.update(re.findall(r"[a-zA-Z']+", c.lower()))

    overlap = len(set(words) & criteria_terms)
    filler_count = sum(1 for w in words if w in FILLER_WORDS)

    length_score = min(len(words) / 80, 1.0) * 35
    overlap_score = min(overlap / max(len(criteria_terms), 1), 1.0) * 45
    filler_penalty = min(filler_count * 2, 15)

    score = max(0.0, min(100.0, length_score + overlap_score + 20 - filler_penalty))
    return score, 0.35


def _clamp(value, lo, hi, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def score_answer(session_id: str, question_id: str, category: str,
                  transcript: str, rubric: dict) -> CompetencyScore:
    """Must return: a CompetencyScore (see app/core/models.py)."""
    score, confidence = None, None

    if llm_client.llm_available():
        try:
            system = (
                "You are an expert technical interviewer scoring one candidate answer. "
                "Score strictly 0-100 based on the given rubric criteria. "
                'Respond ONLY as JSON: {"score": <0-100 float>, '
                '"confidence": <0-1 float>, "reasoning": "<one short sentence>"}'
            )
            criteria = rubric.get("criteria", [])
            user = f"Rubric criteria: {criteria}\n\nCandidate's answer:\n{transcript}"
            retrieved = rubric.get("retrieved_snippets")
            if retrieved:
                user += "\n\nAdditional job-specific evaluation guidance from retrieval:\n- " + \
                        "\n- ".join(retrieved)
            raw = llm_client.ask_llm(system, user, json_mode=True)
            data = llm_client.parse_llm_json(raw)
            score = _clamp(data["score"], 0.0, 100.0, None)
            confidence = _clamp(data.get("confidence", 0.7), 0.0, 1.0, 0.7)
            if score is None:
                raise ValueError("missing or non-numeric 'score' field")
            logger.info(
                "score_answer[%s/%s]: LLM path (%s)",
                session_id, question_id, data.get("reasoning", "")[:120],
            )
        except Exception as exc:
            logger.warning(
                "score_answer[%s/%s]: LLM scoring failed (%s: %s) — falling back to heuristic",
                session_id, question_id, type(exc).__name__, exc,
            )
            score, confidence = None, None

    if score is None:
        score, confidence = _heuristic_score(transcript, rubric)
        logger.info("score_answer[%s/%s]: heuristic path", session_id, question_id)

    return CompetencyScore(
        session_id=session_id,
        question_id=question_id,
        category=category,
        score=round(score, 1),
        confidence=round(confidence, 2),
    )


def get_ml_score(transcript: str):
    """
    Third scoring signal: the trained RandomForest in trained_scorer.py.

    Returns a 0-100 float, or None when no trained model exists / prediction
    fails - deliberately optional so the pipeline never depends on this
    model being present. Lazy import keeps sklearn off the startup path.
    """
    try:
        from app.engine import trained_scorer

        raw = trained_scorer.predict_score(transcript)
        return round(max(0.0, min(100.0, float(raw))), 1)
    except FileNotFoundError:
        logger.debug("get_ml_score: no trained model yet - skipping ML signal")
        return None
    except Exception as exc:
        logger.warning("get_ml_score: prediction failed (%s: %s) - skipping ML signal",
                       type(exc).__name__, exc)
        return None
