"""
Owner: Member B

Counterfactual bias audit (per Mujtaba & Mahapatra 2025 style probing):
swap demographic-coded language (currently: gendered pronouns) in the
transcript, rescore the variant with the same scorer, and flag any
answer where the score shifts meaningfully — that shift is evidence the
scorer is picking up on identity-coded language rather than content.
"""
import logging
import re

from app.core.models import FairnessFlag
from app.engine import llm_client
from app.engine.scoring import _heuristic_score

logger = logging.getLogger(__name__)

PRONOUN_SWAPS = {
    "he": "she", "she": "he",
    "his": "her", "her": "his",
    "him": "her",
}
_PRONOUN_PATTERN = re.compile(r"\b(he|she|his|her|him)\b", re.IGNORECASE)

FLAG_THRESHOLD = 5.0  # point shift considered worth flagging


def _counterfactual_transcript(transcript: str) -> str:
    # Single pass so an already-swapped word can't be swapped back
    # (sequential re.sub passes would undo each other: he->she then she->he).
    return _PRONOUN_PATTERN.sub(lambda m: PRONOUN_SWAPS[m.group(0).lower()], transcript)


def audit_bias(session_id: str, question_id: str, transcript: str,
                original_score: float) -> FairnessFlag:
    """Must return: a FairnessFlag (see app/core/models.py)."""
    variant = _counterfactual_transcript(transcript)

    if variant == transcript:
        return FairnessFlag(
            session_id=session_id, question_id=question_id,
            score_delta=0.0,
            note="No gendered language detected in this answer to probe.",
        )

    variant_score = None
    if llm_client.llm_available():
        try:
            system = 'Score this interview answer 0-100 for quality. Respond ONLY as JSON: {"score": <0-100>}'
            raw = llm_client.ask_llm(system, variant, json_mode=True)
            variant_score = float(llm_client.parse_llm_json(raw)["score"])
            logger.info("audit_bias[%s/%s]: LLM path", session_id, question_id)
        except Exception as exc:
            logger.warning(
                "audit_bias[%s/%s]: LLM rescore failed (%s: %s) — falling back to heuristic",
                session_id, question_id, type(exc).__name__, exc,
            )
            variant_score = None

    if variant_score is None:
        variant_score, _ = _heuristic_score(variant, {"criteria": []})
        logger.info("audit_bias[%s/%s]: heuristic path", session_id, question_id)

    delta = round(variant_score - original_score, 1)
    flagged = abs(delta) >= FLAG_THRESHOLD
    note = (
        f"Swapped gendered pronouns and rescored: {delta:+.1f} point shift. "
        + ("Flagged - scoring appears sensitive to gendered language, review manually."
           if flagged else "Within normal variance.")
    )

    return FairnessFlag(session_id=session_id, question_id=question_id, score_delta=delta, note=note)