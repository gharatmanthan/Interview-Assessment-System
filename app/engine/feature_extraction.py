"""
Extracts numeric features from an interview answer transcript, for use by
the classical ML model in trained_scorer.py. Independent of scoring.py's
LLM/heuristic path — a third, separately-trained scoring signal.
"""
import re

FILLER_WORDS = {
    "um", "uh", "like", "you know", "sort of", "kind of",
    "basically", "actually", "literally", "i mean",
}

POSITIVE_WORDS = {
    "efficient", "scalable", "robust", "optimal", "clean", "tested",
    "maintainable", "clear", "structured", "confident", "successfully",
}


def extract_features(transcript: str) -> dict:
    text = (transcript or "").strip()
    text_lower = text.lower()
    words = re.findall(r"[a-zA-Z']+", text_lower)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]

    word_count = len(words)
    unique_words = len(set(words))
    sentence_count = max(1, len(sentences))

    filler_count = sum(text_lower.count(f) for f in FILLER_WORDS)
    positive_count = sum(1 for w in words if w in POSITIVE_WORDS)

    return {
        "word_count": word_count,
        "unique_word_ratio": (unique_words / word_count) if word_count else 0.0,
        "avg_sentence_length": word_count / sentence_count,
        "filler_word_rate": (filler_count / word_count) if word_count else 0.0,
        "positive_keyword_count": positive_count,
        "sentence_count": sentence_count,
    }


FEATURE_ORDER = [
    "word_count", "unique_word_ratio", "avg_sentence_length",
    "filler_word_rate", "positive_keyword_count", "sentence_count",
]


def features_to_vector(features: dict) -> list:
    return [features[k] for k in FEATURE_ORDER]
