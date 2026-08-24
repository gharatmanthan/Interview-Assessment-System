"""
Owner: Member B

RAG rubric retrieval (OBJECTIVE 2 deliverable).

Primary path - real retrieval:
  The rubric knowledge base (rubric_kb.py, ~50 hand-authored snippets
  describing strong/weak answers per competency) is embedded ONCE via a
  local embedding model (embeddings.py). At scoring time the actual job
  title/description plus the question category are embedded and the top-k
  most similar rubric snippets are retrieved by cosine similarity. Those
  snippets - not a fixed category block - ground the scoring prompt in
  rag.py's caller (scoring.py).

Fallback path - static lookup:
  If no job description is supplied, or anything in the embedding /
  retrieval step fails, retrieve_rubric() returns the original fixed
  per-category criteria (RUBRIC_BANK), same shape as always, with a logged
  reason. Same resilience principle as the LLM heuristic fallback.

The returned dict keeps the legacy contract {"criteria": [...],
"weight": float} and adds transparency keys ("retrieved_snippets",
"retrieval_backend", "retrieval_used").
"""
import logging

import numpy as np

from app.engine import embeddings as _embeddings
from app.engine.rubric_kb import RUBRIC_KB

logger = logging.getLogger(__name__)

TOP_K = 8  # rubric snippets retrieved per query

RUBRIC_BANK = {
    "behavioral": {
        "criteria": ["specific example", "outcome", "ownership", "teamwork", "reflection"],
        "weight": 1.0,
    },
    "technical": {
        "criteria": ["correctness", "depth", "problem-solving", "trade-offs", "examples"],
        "weight": 1.2,
    },
    "dsa": {
        "criteria": ["time complexity", "space complexity", "edge cases", "correctness", "optimal approach"],
        "weight": 1.3,
    },
    "system design": {
        "criteria": ["scalability", "trade-offs", "components", "bottlenecks", "clarity"],
        "weight": 1.3,
    },
    "communication": {
        "criteria": ["clarity", "structure", "conciseness", "confidence"],
        "weight": 1.0,
    },
}

DEFAULT_RUBRIC = {"criteria": ["clarity", "relevance", "depth"], "weight": 1.0}

# Embedding index over RUBRIC_KB, built lazily once per process.
_index = None


class _RubricIndex:
    def __init__(self):
        self.snippets = list(RUBRIC_KB)
        self.embedder = _embeddings.get_embedder(
            reference_corpus=[s.text for s in self.snippets])
        self.matrix = self.embedder.encode([s.text for s in self.snippets])

    def search(self, query_text: str, k: int) -> list:
        """Return [(snippet, similarity)] top-k by cosine similarity."""
        query_vec = self.embedder.encode([query_text])[0]
        similarities = self.matrix @ query_vec  # vectors are L2-normalized
        # Stable sort so ties (e.g. an all-zero query vector) keep KB order
        order = np.argsort(-similarities, kind="stable")[:k]
        return [(self.snippets[i], float(similarities[i])) for i in order]


def _get_index() -> _RubricIndex:
    global _index
    if _index is None:
        _index = _RubricIndex()
    return _index


def reset_retrieval_cache():
    """Test hook: drop the cached embedding index."""
    global _index
    _index = None


def _normalize_category(question_category: str) -> str:
    # Frontend sends e.g. "system_design"; the bank keys on "system design".
    return (question_category or "").strip().lower().replace("_", " ")


def _static_rubric(question_category: str) -> dict:
    return RUBRIC_BANK.get(_normalize_category(question_category), DEFAULT_RUBRIC)


def _retrieved_rubric(job_title: str, question_category: str, job_description: str) -> dict:
    index = _get_index()

    # Query combines what the job needs with what this question probes.
    query_text = " | ".join(part for part in (
        f"Job: {job_title}", f"Question category: {question_category}",
        f"Job description: {job_description}",
    ) if part and part.split(":", 1)[1].strip())

    hits = index.search(query_text, TOP_K)

    # Criteria: base criteria of the categories dominating the top-k hits,
    # ordered by aggregate similarity so JD-relevant competencies come first.
    category_scores = {}
    for snippet, sim in hits:
        category_scores.setdefault(snippet.category, []).append(sim)
    ranked_categories = sorted(
        category_scores, key=lambda c: sum(category_scores[c]), reverse=True)

    criteria = []
    for cat in ranked_categories:
        bank_entry = RUBRIC_BANK.get(cat, DEFAULT_RUBRIC)
        for criterion in bank_entry["criteria"]:
            if criterion not in criteria:
                criteria.append(criterion)
    weight = max(
        (RUBRIC_BANK.get(cat, DEFAULT_RUBRIC)["weight"] for cat in ranked_categories),
        default=DEFAULT_RUBRIC["weight"],
    )

    return {
        "criteria": criteria[:7],
        "weight": weight,
        "retrieved_snippets": [f"[{s.category}/{s.level}] {s.text}" for s, _ in hits],
        "retrieval_backend": index.embedder.name,
        "retrieval_used": True,
    }


def retrieve_rubric(job_title: str, question_category: str,
                    job_description: str = "") -> dict:
    """
    Must return: {"criteria": [str, ...], "weight": float} (+ retrieval
    transparency keys when the vector path ran).
    Consumed by: scoring.py (rubric grounds both LLM prompt and heuristic).
    """
    jd = (job_description or "").strip()
    if len(jd) < 40:  # too little content for meaningful similarity
        logger.info("retrieve_rubric[%s/%s]: no usable job description - static lookup path",
                    job_title, question_category)
        result = _static_rubric(question_category)
        return {**result, "retrieval_used": False}

    try:
        category = _normalize_category(question_category)
        result = _retrieved_rubric(job_title or "", category, jd)
        logger.info("retrieve_rubric[%s/%s]: vector retrieval via %s (%d snippets)",
                    job_title, question_category, result["retrieval_backend"], TOP_K)
        return result
    except Exception as exc:
        logger.warning(
            "retrieve_rubric[%s/%s]: retrieval failed (%s: %s) - falling back to "
            "static rubric lookup", job_title, question_category, type(exc).__name__, exc)
        result = _static_rubric(question_category)
        return {**result, "retrieval_used": False}
