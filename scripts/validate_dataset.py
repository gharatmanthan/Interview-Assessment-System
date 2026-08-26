"""
Validates the generated synthetic dataset before training.

Phase A — Automated sanity checks:
  - Near-duplicate detection (TF-IDF cosine similarity > 0.95)
  - Length validation (flag <10 or >500 words)
  - Tier separation (features should differ across tiers)

Phase B — Human validation subset:
  --sample   : export blind subset CSV for team scoring (default)
  --apply-scores : ingest human_scores.csv, compute correlation, apply corrections

Usage:
    python scripts/validate_dataset.py --sample          # export blind subset
    python scripts/validate_dataset.py --apply-scores    # ingest scores + correct
    python scripts/validate_dataset.py --both            # sample first, then apply if scores exist
"""
import argparse
import csv
import json
import logging
import random
import sys
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine.feature_extraction import extract_features

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATASET_DIR = Path(__file__).resolve().parents[1] / "data" / "datasets"
DATASET_PATH = DATASET_DIR / "synthetic_graded_answers.json"
SUBSET_PATH = DATASET_DIR / "human_validation_subset.csv"
SCORES_PATH = DATASET_DIR / "human_scores.csv"
REPORT_PATH = DATASET_DIR / "human_validation_report.json"

RANDOM_SEED = 42
SAMPLE_SIZE = 25
DUPLICATE_THRESHOLD = 0.95


# ─── Helpers ────────────────────────────────────────────────────────────────

def load_dataset() -> list[dict]:
    with open(DATASET_PATH) as f:
        return json.load(f)


def save_dataset(dataset: list[dict]) -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATASET_PATH, "w") as f:
        json.dump(dataset, f, indent=2)


# ─── Phase A: Automated Sanity Checks ─────────────────────────────────────

def check_near_duplicates(dataset: list[dict]) -> list[tuple[int, int, float]]:
    """Return list of (idx_i, idx_j, similarity) for pairs above threshold."""
    transcripts = [e["transcript"] for e in dataset]
    vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
    tfidf_matrix = vectorizer.fit_transform(transcripts)
    sim_matrix = cosine_similarity(tfidf_matrix)

    flagged = []
    n = len(dataset)
    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] > DUPLICATE_THRESHOLD:
                flagged.append((i, j, float(sim_matrix[i, j])))
    return flagged


def check_length_flags(dataset: list[dict]) -> list[dict]:
    """Flag answers with <10 or >500 words."""
    flagged = []
    for i, entry in enumerate(dataset):
        word_count = len(entry["transcript"].split())
        if word_count < 10 or word_count > 500:
            flagged.append({
                "index": i,
                "id": entry["id"],
                "tier": entry["tier"],
                "word_count": word_count,
                "question": entry["question"][:60],
            })
    return flagged


def check_tier_separation(dataset: list[dict]) -> dict:
    """Check that features differ meaningfully across tiers."""
    tier_features = {}
    for tier in ["Poor", "Mediocre", "Good", "Excellent"]:
        entries = [e for e in dataset if e["tier"] == tier]
        if not entries:
            continue
        features = [extract_features(e["transcript"]) for e in entries]
        tier_features[tier] = {
            "avg_word_count": float(np.mean([f["word_count"] for f in features])),
            "avg_filler_rate": float(np.mean([f["filler_word_rate"] for f in features])),
            "avg_positive_kw": float(np.mean([f["positive_keyword_count"] for f in features])),
            "count": len(entries),
        }

    orders = {
        "word_count": ["Poor", "Mediocre", "Good", "Excellent"],
        "filler_rate": ["Excellent", "Good", "Mediocre", "Poor"],
        "positive_kw": ["Poor", "Mediocre", "Good", "Excellent"],
    }
    violations = []
    for feature, expected_order in orders.items():
        key = f"avg_{feature}"
        vals = [tier_features[t][key] for t in expected_order if t in tier_features]
        if len(vals) >= 2 and not all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)):
            violations.append(feature)

    return {"tier_features": tier_features, "monotonicity_violations": violations}


def run_sanity_checks(dataset: list[dict]) -> dict:
    """Run all Phase A checks and return results."""
    logger.info("Running sanity checks on %d examples...", len(dataset))

    duplicates = check_near_duplicates(dataset)
    length_flags = check_length_flags(dataset)
    tier_sep = check_tier_separation(dataset)

    report = {
        "n_examples": len(dataset),
        "near_duplicates": [{"i": i, "j": j, "similarity": s} for i, j, s in duplicates],
        "n_near_duplicates": len(duplicates),
        "length_flags": length_flags,
        "n_length_flags": len(length_flags),
        "tier_separation": tier_sep,
    }

    print(f"\n=== Sanity Check Results ===")
    print(f"Total examples: {report['n_examples']}")
    print(f"Near-duplicates (similarity > {DUPLICATE_THRESHOLD}): {report['n_near_duplicates']}")
    for dup in duplicates:
        print(f"  Pair ({dup[0]}, {dup[1]}): similarity={dup[2]:.3f}")
        print(f"    [{dup[0]}]: {dataset[dup[0]]['transcript'][:60]}...")
        print(f"    [{dup[1]}]: {dataset[dup[1]]['transcript'][:60]}...")

    print(f"\nLength flags (<10 or >500 words): {report['n_length_flags']}")
    for flag in length_flags:
        print(f"  [{flag['index']}] {flag['tier']}: {flag['word_count']} words — {flag['question']}")

    print(f"\nTier separation:")
    for tier, stats in tier_sep["tier_features"].items():
        print(f"  {tier:10s} (n={stats['count']:3d}): words={stats['avg_word_count']:.0f} "
              f"filler_rate={stats['avg_filler_rate']:.3f} pos_kw={stats['avg_positive_kw']:.1f}")
    if tier_sep["monotonicity_violations"]:
        print(f"  WARNING: Monotonicity violations in: {tier_sep['monotonicity_violations']}")
    else:
        print(f"  OK: All features show expected monotonic trends across tiers")

    return report


# ─── Phase B: Human Validation ─────────────────────────────────────────────

def create_validation_subset(dataset: list[dict], seed: int = RANDOM_SEED) -> list[dict]:
    """Stratified sample of examples for human validation."""
    random.seed(seed)
    tiers = ["Poor", "Mediocre", "Good", "Excellent"]
    per_tier = SAMPLE_SIZE // len(tiers)
    remainder = SAMPLE_SIZE - per_tier * len(tiers)

    subset = []
    for tier in tiers:
        tier_entries = [e for e in dataset if e["tier"] == tier]
        n_sample = per_tier + (1 if tiers.index(tier) < remainder else 0)
        n_sample = min(n_sample, len(tier_entries))
        subset.extend(random.sample(tier_entries, n_sample))

    random.shuffle(subset)
    return subset


def export_blind_subset(subset: list[dict]) -> None:
    """Export CSV without tier/score info (blind to LLM labels)."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    with open(SUBSET_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "question", "category", "transcript"])
        writer.writeheader()
        for entry in subset:
            writer.writerow({
                "id": entry["id"],
                "question": entry["question"],
                "category": entry["category"],
                "transcript": entry["transcript"],
            })
    print(f"\nExported {len(subset)} blind examples to {SUBSET_PATH}")
    print("\n=== Scoring Instructions ===")
    print("For each row, score the candidate's answer from 0-100 using this rubric:")
    print("  90-100: Exceptional — specific, structured, deep understanding, concise")
    print("  70-89:  Strong — clear, relevant, covers key points well")
    print("  50-69:  Adequate — touches on the topic, some structure, lacks depth")
    print("  30-49:  Weak — vague, disorganized, missing key points")
    print("  0-29:   Poor — off-topic, confused, or no meaningful content")
    print(f"\nFill in the 'human_score' column in: {SCORES_PATH}")
    print("Then run: python scripts/validate_dataset.py --apply-scores")


def ingest_and_correct(dataset: list[dict]) -> dict:
    """Ingest human scores, compute correlation, apply corrections."""
    human_scores = {}
    with open(SCORES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                human_scores[row["id"]] = float(row["human_score"])
            except (ValueError, KeyError):
                continue

    if not human_scores:
        logger.error("No valid human scores found in %s", SCORES_PATH)
        return {}

    matched_llm = []
    matched_human = []
    divergences = []
    corrections = 0

    for entry in dataset:
        if entry["id"] in human_scores:
            llm_score = entry["target_score"]
            human_score = human_scores[entry["id"]]
            matched_llm.append(llm_score)
            matched_human.append(human_score)

            divergence = abs(llm_score - human_score)
            divergences.append({
                "id": entry["id"],
                "question": entry["question"][:60],
                "tier": entry["tier"],
                "llm_score": llm_score,
                "human_score": human_score,
                "divergence": round(divergence, 1),
            })

            if divergence > 20:
                entry["target_score"] = human_score
                entry["human_corrected"] = True
                corrections += 1
                logger.info("Corrected [%s] %s: %.1f -> %.1f (divergence=%.1f)",
                            entry["tier"], entry["question"][:40], llm_score, human_score, divergence)

    if len(matched_llm) >= 3:
        r, p_value = pearsonr(matched_llm, matched_human)
    else:
        r, p_value = 0.0, 1.0

    report = {
        "n_human_scored": len(matched_llm),
        "n_corrected": corrections,
        "correlation_pearson_r": round(float(r), 4),
        "correlation_p_value": round(float(p_value), 6),
        "divergences": sorted(divergences, key=lambda x: -x["divergence"]),
        "interpretation": (
            "Strong" if abs(r) > 0.7 else
            "Moderate" if abs(r) > 0.5 else
            "Weak" if abs(r) > 0.3 else
            "Very weak / no correlation"
        ),
    }

    print(f"\n=== Human Validation Results ===")
    print(f"Examples scored: {report['n_human_scored']}")
    print(f"Pearson's r: {report['correlation_pearson_r']:.4f} (p={report['correlation_p_value']:.4f})")
    print(f"Interpretation: {report['interpretation']}")
    print(f"Corrections applied (>20pt divergence): {report['n_corrected']}")
    if divergences:
        print(f"\nTop divergences:")
        for d in divergences[:5]:
            print(f"  [{d['tier']}] {d['question']}")
            print(f"    LLM={d['llm_score']:.1f}  Human={d['human_score']:.1f}  Delta={d['divergence']:.1f}")

    save_dataset(dataset)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {REPORT_PATH}")

    return report


# ─── CLI ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate synthetic dataset")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sample", action="store_true", help="Export blind validation subset CSV")
    group.add_argument("--apply-scores", action="store_true", help="Ingest human scores and apply corrections")
    group.add_argument("--both", action="store_true", help="Sample first, then apply if scores exist")
    args = parser.parse_args()

    dataset = load_dataset()
    report = run_sanity_checks(dataset)

    if args.sample or args.both:
        subset = create_validation_subset(dataset)
        export_blind_subset(subset)

    if args.apply_scores or args.both:
        if SCORES_PATH.exists():
            dataset = load_dataset()
            report = ingest_and_correct(dataset)
            return 0
        else:
            print(f"\nNo human scores found at {SCORES_PATH}")
            print("Run --sample first, have team score the CSV, then run --apply-scores")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
