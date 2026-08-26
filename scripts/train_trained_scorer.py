"""
Trains the classical ML scorer (trained_scorer.py) and prints LOO
cross-validation metrics plus sanity-check predictions.

Methodology:
    Training data is synthetically generated using an LLM (Groq API)
    to produce candidate-style answers at four quality tiers (Excellent,
    Good, Mediocre, Poor) across ~30 interview questions spanning 6
    categories (DSA, System Design, Behavioral, Communication,
    Technical Knowledge, Problem Solving). Each answer is assigned a
    target score with jitter within its tier range.

    A human-validation subset (~25% of examples, scored blind by 2-3
    team members) is used to verify that synthetic labels correlate
    with human judgment, and to correct outliers where LLM and human
    scores diverge by >20 points.

    This is a defensible synthetic-labeling methodology: the LLM
    generates *answers* (not grades), and the human-validation step
    provides ground-truth calibration that synthetic labels alone
    cannot.

Usage:  python scripts/train_trained_scorer.py
"""
import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine.feature_extraction import extract_features  # noqa: E402
from app.engine.trained_scorer import (  # noqa: E402
    get_last_training_metrics,
    predict_score,
    train_from_dataset,
)

DATASET_DIR = Path(__file__).resolve().parents[1] / "data" / "datasets"
DATASET_PATH = DATASET_DIR / "synthetic_graded_answers.json"


def load_dataset() -> list[tuple[str, float]]:
    """Load the synthetic graded answers dataset for training."""
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found at {DATASET_PATH}. "
            "Run scripts/generate_training_dataset.py first."
        )
    with open(DATASET_PATH) as f:
        data = json.load(f)
    return [(entry["transcript"], entry["target_score"]) for entry in data]


def main() -> int:
    dataset = load_dataset()
    print(f"Loaded dataset: {len(dataset)} examples")

    with open(DATASET_PATH) as f:
        raw = json.load(f)
    tier_dist = Counter(e["tier"] for e in raw)
    cat_dist = Counter(e["category"] for e in raw)
    print(f"Tier distribution: {dict(tier_dist)}")
    print(f"Category distribution: {dict(cat_dist)}")
    scores = [e["target_score"] for e in raw]
    print(f"Score range: {min(scores):.1f} - {max(scores):.1f} (mean={sum(scores)/len(scores):.1f})")

    metrics = train_from_dataset(dataset)
    print(f"\nTraining complete. LOO cross-validation metrics:")
    print(f"  n_samples={metrics['n_samples']} cv={metrics['cv_method']}")
    print(f"  pearson_r={metrics['pearson_r']:.3f} p_value={metrics['p_value']:.4f}")
    print(f"  mae={metrics['mae']:.2f} rmse={metrics['rmse']:.2f}")

    tier_proxies = {
        "Excellent": "I would analyze the problem constraints first, then design an optimal solution "
                     "with clear structure, efficient time complexity, and thorough edge case handling. "
                     "For example, using a hash map gives O(n) average time which is optimal here.",
        "Good": "I would start by understanding the problem and work through a solution step by step, "
                "covering the main requirements and a couple of edge cases.",
        "Mediocre": "I think you could do this by sort of iterating through the data and "
                    "doing something with each element, maybe using a loop or something.",
        "Poor": "Um, I'm not really sure. Maybe just try everything and see what works?",
    }
    print(f"\nSanity-check predictions (tier proxies):")
    predictions = {}
    for tier, proxy in tier_proxies.items():
        pred = predict_score(proxy)
        predictions[tier] = pred
        print(f"  {tier:10s} -> {pred:.1f}")

    ok = (predictions["Excellent"] > predictions["Good"] >
          predictions["Mediocre"] > predictions["Poor"])
    print("PASS: Excellent > Good > Mediocre > Poor" if ok else
          f"FAIL: Expected monotonic decrease, got {predictions}")

    sample_transcript = dataset[len(dataset) // 2][0]
    feats = extract_features(sample_transcript)
    print(f"\nSample features (middle example): filler_rate={feats['filler_word_rate']:.3f} "
          f"positive_kw={feats['positive_keyword_count']} words={feats['word_count']}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
