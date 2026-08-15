"""
Owner: Member B

Explains why a score was given — either via LLM-generated rationale
grounded in the transcript, or a transparent heuristic summary when no
LLM key is configured (the heuristic path says exactly that, rather than
pretending to be a semantic explanation).
"""
import json

from app.core.models import ExplanationItem
from app.engine import llm_client


def _heuristic_explanation(transcript: str, score: float) -> tuple[str, list]:
    words = transcript.split()
    length_note = "a detailed" if len(words) > 60 else "a brief"
    summary = (
        f"Score reflects {length_note} answer ({len(words)} words) evaluated by keyword "
        f"overlap with the expected rubric. No LLM key is configured, so this is a "
        f"heuristic estimate rather than a semantic evaluation - configure GROQ_API_KEY "
        f"for real explanations."
    )
    supporting = words[:12]
    return summary, supporting


def explain_score(session_id: str, question_id: str, transcript: str,
                   score: float) -> ExplanationItem:
    """Must return: an ExplanationItem (see app/core/models.py)."""
    summary, supporting = None, None

    if llm_client.llm_available():
        try:
            system = (
                "You explain interview answer scores in 1-2 plain-language sentences, "
                "and extract up to 4 short exact phrases from the transcript that most "
                'influenced the score. Respond ONLY as JSON: '
                '{"summary": str, "supporting_phrases": [str, ...]}'
            )
            user = f"Score given: {score}/100\n\nTranscript:\n{transcript}"
            raw = llm_client.ask_llm(system, user, json_mode=True)
            data = json.loads(raw)
            summary, supporting = data["summary"], data.get("supporting_phrases", [])
        except Exception:
            summary, supporting = None, None

    if summary is None:
        summary, supporting = _heuristic_explanation(transcript, score)

    return ExplanationItem(
        session_id=session_id,
        question_id=question_id,
        summary=summary,
        supporting_phrases=supporting,
    )