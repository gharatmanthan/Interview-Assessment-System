"""
Owner: Member B

Counterfactual bias audit (per Mujtaba & Mahapatra 2025 style probing):
swap demographic-coded language (currently: gendered pronouns) in the
transcript, rescore the variant with the same scorer, and flag any
answer where the score shifts meaningfully — that shift is evidence the
scorer is picking up on identity-coded language rather than content.
"""
import json
import re

from app.core.models import FairnessFlag
from app.engine import llm_client
from app.engine.scoring import _heuristic_score

PRONOUN_SWAPS = [
    (r"\bhe\b", "she"), (r"\bshe\b", "he"),
    (r"\bhis\b", "her"), (r"\bher\b", "his"),
    (r"\bhim\b", "her"),
]

FLAG_THRESHOLD = 5.0  # point shift considered worth flagging


def _counterfactual_transcript(transcript: str) -> str:
    result = transcript
    for pattern, repl in PRONOUN_SWAPS:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)
    return result


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
            variant_score = float(json.loads(raw)["score"])
        except Exception:
            variant_score = None

    if variant_score is None:
        variant_score, _ = _heuristic_score(variant, {"criteria": []})

    delta = round(variant_score - original_score, 1)
    flagged = abs(delta) >= FLAG_THRESHOLD
    note = (
        f"Swapped gendered pronouns and rescored: {delta:+.1f} point shift. "
        + ("Flagged - scoring appears sensitive to gendered language, review manually."
           if flagged else "Within normal variance.")
    )

    return FairnessFlag(session_id=session_id, question_id=question_id, score_delta=delta, note=note)