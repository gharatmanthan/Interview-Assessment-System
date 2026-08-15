"""
Owner: Member B

Scores a transcript against the retrieved rubric. Uses the LLM (via
llm_client) when GROQ_API_KEY is configured; otherwise falls back to a
transparent, rule-based heuristic so the pipeline still produces a real
score end-to-end without any setup.
"""
import json
import re

from app.core.models import CompetencyScore
from app.engine import llm_client

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


def score_answer(session_id: str, question_id: str, category: str,
                  transcript: str, rubric: dict) -> CompetencyScore:
    """Must return: a CompetencyScore (see app/core/models.py)."""
    score, confidence = None, None

    if llm_client.llm_available():
        try:
            system = (
                "You are an expert technical interviewer scoring one candidate answer. "
                "Score strictly 0-100 based on the given rubric criteria. "
                'Respond ONLY as JSON: {"score": <0-100 float>, "confidence": <0-1 float>}'
            )
            user = f"Rubric criteria: {rubric.get('criteria', [])}\n\nCandidate's answer:\n{transcript}"
            raw = llm_client.ask_llm(system, user, json_mode=True)
            data = json.loads(raw)
            score, confidence = float(data["score"]), float(data.get("confidence", 0.7))
        except Exception:
            score, confidence = None, None

    if score is None:
        score, confidence = _heuristic_score(transcript, rubric)

    return CompetencyScore(
        session_id=session_id,
        question_id=question_id,
        category=category,
        score=round(score, 1),
        confidence=round(confidence, 2),
    )