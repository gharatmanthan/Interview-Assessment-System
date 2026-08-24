"""
Trains the classical ML scorer (trained_scorer.py) and prints LOO
cross-validation metrics plus sanity-check predictions.

PLACEHOLDER DATASET WARNING:
    The dataset below is HAND-WRITTEN (8 transcript/score pairs) purely to
    prove the training pipeline runs end-to-end. These are NOT real
    evaluation results — replace PLACEHOLDER_DATASET with a finalized
    labeled set (e.g. Kaggle-derived graded answers, or LLM-generated
    sample answers at varying quality tiers over the question bank) before
    quoting any metric in the report.

Usage:  python scripts/train_trained_scorer.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine.feature_extraction import extract_features  # noqa: E402
from app.engine.trained_scorer import (  # noqa: E402
    get_last_training_metrics,
    predict_score,
    train_from_dataset,
)

# PLACEHOLDER dataset - replace with the finalized labeled dataset.
STRONG = (
    "I'd start with brute force to establish correctness, note its O(n squared) time "
    "complexity, then move to a hash map for O(n) average time and O(n) space. Edge cases: "
    "empty input, duplicates, negative numbers. The trade-off favors memory for speed, which "
    "is optimal here."
)
GOOD = (
    "We used a message queue between services so failures could retry independently. I chose "
    "Kafka over RabbitMQ after benchmarking both; throughput doubled. We monitored lag and "
    "alerted on backlog growth."
)
MEDIOCRE = (
    "Basically we had like a lot of requests so we added caching of some kind and it sort of "
    "worked faster afterwards. I think there was also a database involved somewhere."
)
WEAK = (
    "Um I don't really know, maybe you just loop through things? I usually look it up online "
    "when something like this comes up at work honestly."
)
OFF_TOPIC = (
    "On weekends I go hiking with my family and cook pasta. My favorite trail has a great view "
    "of the valley and we take photos at the summit."
)
TERSE = "Use a dictionary."

# PLACEHOLDER dataset - hand-written scores, NOT real evaluation data.
PLACEHOLDER_DATASET = [
    (STRONG, 92.0),
    (GOOD, 78.0),
    (STRONG.replace("hash map", "trie").replace("O(n squared)", "quadratic"), 88.0),
    (GOOD + " Additionally, we load-tested with realistic traffic profiles before rollout.", 82.0),
    (MEDIOCRE, 45.0),
    (WEAK, 18.0),
    (OFF_TOPIC, 12.0),
    (TERSE, 25.0),
]


def main() -> int:
    metrics = train_from_dataset(PLACEHOLDER_DATASET)
    print("Training complete. Metrics (PLACEHOLDER dataset - not real results):")
    print(f"  n_samples={metrics['n_samples']} cv={metrics['cv_method']}")
    print(f"  pearson_r={metrics['pearson_r']:.3f} p_value={metrics['p_value']:.4f}")
    print(f"  mae={metrics['mae']:.2f} rmse={metrics['rmse']:.2f}")

    strong_pred = predict_score(STRONG)
    weak_pred = predict_score(WEAK)
    print(f"\nSanity check predictions:")
    print(f"  strong transcript -> {strong_pred:.1f}")
    print(f"  weak transcript   -> {weak_pred:.1f}")
    ok = strong_pred > weak_pred
    print("PASS: strong > weak" if ok else "FAIL: model does not separate strong from weak")

    feats = extract_features(MEDIOCRE)
    print(f"\nSample features (mediocre): filler_rate={feats['filler_word_rate']:.3f} "
          f"positive_kw={feats['positive_keyword_count']} words={feats['word_count']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
