"""
Owner: Member B

Explains why a score was given — either via LLM-generated rationale
grounded in the transcript, or a transparent heuristic summary when no
LLM key is configured (the heuristic path says exactly that, rather than
pretending to be a semantic explanation).
"""
import logging

from app.core.models import ExplanationItem
from app.engine import llm_client

logger = logging.getLogger(__name__)


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
            data = llm_client.parse_llm_json(raw)
            summary = str(data["summary"])
            supporting = [str(p) for p in data.get("supporting_phrases", [])]
            logger.info("explain_score[%s/%s]: LLM path", session_id, question_id)
        except Exception as exc:
            logger.warning(
                "explain_score[%s/%s]: LLM explanation failed (%s: %s) — falling back to heuristic",
                session_id, question_id, type(exc).__name__, exc,
            )
            summary, supporting = None, None

    if summary is None:
        summary, supporting = _heuristic_explanation(transcript, score)
        logger.info("explain_score[%s/%s]: heuristic path", session_id, question_id)

    return ExplanationItem(
        session_id=session_id,
        question_id=question_id,
        summary=summary,
        supporting_phrases=supporting,
    )