"""
Owner: Member B

Built-in rubric bank, matched by question category. This is a simpler
stand-in for a full embedding-based RAG pipeline (ChromaDB/FAISS) — the
retrieve_rubric() signature is what scoring.py depends on, so swapping in
real vector retrieval later doesn't require changing any other file.
"""

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


def retrieve_rubric(job_title: str, question_category: str) -> dict:
    """Must return: {"criteria": [str, ...], "weight": float}"""
    return RUBRIC_BANK.get(question_category.strip().lower(), DEFAULT_RUBRIC)