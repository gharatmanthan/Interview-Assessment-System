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

    criteria_phrases = []
    for c in rubric.get("criteria", []):
        phrase = re.findall(r"[a-zA-Z']+", c.lower())
        if phrase:
            criteria_phrases.append(phrase)

    answer_text = " ".join(words)
    matched_criteria = sum(
        1 for phrase in criteria_phrases
        if " ".join(phrase) in answer_text
        or any(term in words for term in phrase)
    )
    filler_count = sum(1 for w in words if w in FILLER_WORDS)

    length_score = min(len(words) / 80, 1.0) * 30
    relevance_score = min(matched_criteria / max(len(criteria_phrases), 1), 1.0) * 50
    structure_score = 10 if len(words) >= 25 and any(
        marker in answer_text for marker in ("because", "therefore", "for example", "first", "then")
    ) else 0
    filler_penalty = min(filler_count * 2, 15)

    score = max(0.0, min(100.0, length_score + relevance_score + structure_score + 10 - filler_penalty))
    confidence = min(0.85, 0.35 + (0.2 if matched_criteria else 0) + (0.15 if len(words) >= 25 else 0))
    return score, confidence


def score_answer(session_id: str, question_id: str, category: str,
                  transcript: str, rubric: dict, question: str = "") -> CompetencyScore:
    """Must return: a CompetencyScore (see app/core/models.py)."""
    score, confidence = None, None

    if llm_client.llm_available():
        try:
            system = (
                "You are an expert technical interviewer scoring one candidate answer. "
                "Score strictly 0-100 based on how well the answer addresses the question "
                "and rubric criteria. Reward correctness, relevant evidence, clear reasoning, "
                "and useful examples. Do not reward length or confidence alone. "
                'Respond ONLY as JSON: {"score": <0-100 float>, "confidence": <0-1 float>}'
            )
            user = (
                f"Question: {question}\n"
                f"Category: {category}\n"
                f"Rubric criteria: {rubric.get('criteria', [])}\n\n"
                f"Candidate's answer:\n{transcript}"
            )
            raw = llm_client.ask_llm(system, user, json_mode=True)
            data = json.loads(raw)
            score, confidence = float(data["score"]), float(data.get("confidence", 0.7))
            if not 0 <= score <= 100 or not 0 <= confidence <= 1:
                raise ValueError("LLM returned an out-of-range score or confidence")
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