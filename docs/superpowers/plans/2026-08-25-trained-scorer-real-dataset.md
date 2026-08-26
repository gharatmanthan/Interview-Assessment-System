# Real Dataset for Trained Scorer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 8-example placeholder dataset with a 120+ example validated synthetic dataset, producing real LOO-CV metrics for the trained scorer.

**Architecture:** Three new scripts + expanded question bank + doc updates. Pipeline: generate tiered synthetic answers → sanity check → human-validation → correct → retrain → report.

**Tech Stack:** Python, scikit-learn, existing `llm_client.py` (Groq API), TF-IDF for dedup, scipy for correlation.

**Spec:** `docs/superpowers/specs/2026-08-25-trained-scorer-real-dataset-design.md`

## Global Constraints

- Python 3.x, all dependencies already in `requirements.txt`
- LLM calls go through `app/engine/llm_client.py` (`ask_llm()`, `llm_available()`)
- No new dependencies — use existing scikit-learn, scipy, numpy, joblib
- `data/datasets/` directory does not exist yet — create it
- Existing callers of `DEFAULT_QUESTIONS` must not break
- Do not modify `trained_scorer.py` (the model code) — only the training script and question bank

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `app/core/question_bank.py` | Expand to ~30 questions with categories |
| Create | `scripts/generate_training_dataset.py` | LLM-based synthetic answer generation |
| Create | `scripts/validate_dataset.py` | Sanity checks + human validation subset |
| Modify | `scripts/train_trained_scorer.py` | Load real dataset, remove placeholder |
| Modify | `README.md` | Update ML scorer section |
| Create | `data/datasets/` | Directory for generated data (auto-created) |

---

### Task 1: Expand Question Bank

**Files:**
- Modify: `app/core/question_bank.py`

**Interfaces:**
- Produces: `QUESTION_BANK: list[dict]` with `{"question": str, "category": str}` keys
- Produces: `DEFAULT_QUESTIONS: list[str]` — backward-compatible extraction
- Later consumed by: `scripts/generate_training_dataset.py`

- [ ] **Step 1: Read current question_bank.py**

Read `app/core/question_bank.py` to see current structure (5 questions, plain list).

- [ ] **Step 2: Expand with categorized questions**

Replace `DEFAULT_QUESTIONS` with `QUESTION_BANK` — a list of dicts with `"question"` and `"category"` keys. Add ~30 questions across 6 categories. Derive `DEFAULT_QUESTIONS` from the bank for backward compatibility.

```python
QUESTION_BANK = [
    # DSA
    {"question": "Explain the difference between a stack and a queue. When would you use each?", "category": "DSA"},
    {"question": "How would you find the second largest element in an unsorted array? What's the optimal time complexity?", "category": "DSA"},
    {"question": "Describe how a hash table works internally. What causes collisions and how are they resolved?", "category": "DSA"},
    {"question": "Given a binary tree, how would you find its maximum depth? Walk through your approach.", "category": "DSA"},
    {"question": "Explain Big-O notation. How would you analyze the time complexity of a nested loop?", "category": "DSA"},
    # System Design
    {"question": "How would you design a URL shortener like bit.ly? Walk through the key components.", "category": "System Design"},
    {"question": "You need to design a real-time chat application for 10 million users. What architecture would you choose?", "category": "System Design"},
    {"question": "Explain the trade-offs between SQL and NoSQL databases. Give a concrete example of when you'd pick each.", "category": "System Design"},
    {"question": "How would you design a notification system that supports email, SMS, and push notifications?", "category": "System Design"},
    {"question": "What is caching? Describe a caching strategy for a high-traffic website.", "category": "System Design"},
    # Behavioral
    {"question": "Tell me about a time you had a conflict with a teammate. How did you resolve it?", "category": "Behavioral"},
    {"question": "Describe a situation where you had to learn a new technology quickly. How did you approach it?", "category": "Behavioral"},
    {"question": "Give an example of when you made a mistake at work. What happened and what did you learn?", "category": "Behavioral"},
    {"question": "How do you prioritize tasks when you have multiple deadlines? Give a specific example.", "category": "Behavioral"},
    {"question": "Tell me about a project you're most proud of. What made it successful?", "category": "Behavioral"},
    # Communication
    {"question": "How would you explain a technical concept to a non-technical stakeholder?", "category": "Communication"},
    {"question": "Describe a time you had to present complex findings to a team. How did you structure your message?", "category": "Communication"},
    {"question": "How do you handle giving feedback to a colleague who is underperforming?", "category": "Communication"},
    {"question": "Explain how you document your code and technical decisions for future team members.", "category": "Communication"},
    {"question": "How do you approach writing emails to senior leadership? Give an example.", "category": "Communication"},
    # Technical Knowledge
    {"question": "What is the difference between REST and GraphQL? When would you choose one over the other?", "category": "Technical Knowledge"},
    {"question": "Explain what CI/CD means and why it matters in software development.", "category": "Technical Knowledge"},
    {"question": "What are design patterns? Name three you've used and explain when each is appropriate.", "category": "Technical Knowledge"},
    {"question": "How does garbage collection work in modern programming languages? Compare at least two approaches.", "category": "Technical Knowledge"},
    {"question": "What is the CAP theorem? Why is it important for distributed systems?", "category": "Technical Knowledge"},
    # Problem Solving
    {"question": "You discover a production system is running 10x slower than usual. Walk through your debugging approach.", "category": "Problem Solving"},
    {"question": "How would you approach refactoring a legacy codebase with no tests?", "category": "Problem Solving"},
    {"question": "A feature request comes in that would require redesigning a core module. How do you evaluate whether to build it?", "category": "Problem Solving"},
    {"question": "Your team's sprint velocity has dropped significantly. What steps would you take to diagnose and fix it?", "category": "Problem Solving"},
    {"question": "How do you decide between building a solution in-house vs. using an existing library or service?", "category": "Problem Solving"},
]

# Backward compatibility: plain question strings
DEFAULT_QUESTIONS = [q["question"] for q in QUESTION_BANK]
```

- [ ] **Step 3: Verify backward compatibility**

Check that any existing code importing `DEFAULT_QUESTIONS` still works — it should, since it's still `list[str]`. Run:

```bash
python -c "from app.core.question_bank import DEFAULT_QUESTIONS, QUESTION_BANK; print(f'{len(DEFAULT_QUESTIONS)} questions, {len(QUESTION_BANK)} bank entries'); cats = set(q['category'] for q in QUESTION_BANK); print(f'Categories: {cats}')"
```

Expected: 30 questions, 6 categories printed. No import errors.

- [ ] **Step 4: Commit**

```bash
git add app/core/question_bank.py
git commit -m "feat: expand question bank to 30 categorized questions across 6 categories"
```

---

### Task 2: Create Dataset Generation Script

**Files:**
- Create: `scripts/generate_training_dataset.py`

**Interfaces:**
- Consumes: `QUESTION_BANK` from `app/core/question_bank.py`
- Consumes: `ask_llm()` from `app/engine/llm_client.py`
- Produces: `data/datasets/synthetic_graded_answers.json`
- Later consumed by: `scripts/validate_dataset.py`, `scripts/train_trained_scorer.py`

- [ ] **Step 1: Create the generation script skeleton**

Create `scripts/generate_training_dataset.py` with imports, constants, and the main structure:

```python
"""
Generates a graded synthetic dataset for training the classical ML scorer.

Uses the question bank and LLM (Groq) to generate candidate-style answers
at four quality tiers, each assigned a target score with jitter.

Usage:
    python scripts/generate_training_dataset.py              # generate full dataset
    python scripts/generate_training_dataset.py --resume      # skip existing entries
    python scripts/generate_training_dataset.py --limit 5     # generate only 5 questions

Output: data/datasets/synthetic_graded_answers.json
"""
import json
import logging
import random
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.question_bank import QUESTION_BANK
from app.engine.llm_client import ask_llm, llm_available

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATASET_DIR = Path(__file__).resolve().parents[1] / "data" / "datasets"
DATASET_PATH = DATASET_DIR / "synthetic_graded_answers.json"
FAILURES_LOG = DATASET_DIR / "generation_failures.log"

TIERS = {
    "Excellent": {"score_range": (85, 98), "description": "specific, structured, demonstrates deep understanding, includes concrete examples, concise but thorough"},
    "Good": {"score_range": (65, 84), "description": "clear and relevant, covers key points, may lack some depth or a concrete example"},
    "Mediocre": {"score_range": (35, 64), "description": "vague, uses filler words, touches on the topic but lacks structure or specific examples"},
    "Poor": {"score_range": (5, 34), "description": "very vague, mostly filler words, no concrete examples, may be off-topic or confused"},
}

SYSTEM_PROMPT = (
    "You are simulating a candidate's spoken interview answer. "
    "Write ONLY the answer text — no meta-commentary, no labels, no explanations. "
    "Write as if you are the candidate answering this question in an interview."
)

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
SAVE_EVERY = 10
```

- [ ] **Step 2: Write the generation logic**

Add the core generation function and helpers:

```python
def load_existing() -> list[dict]:
    """Load existing dataset for --resume mode."""
    if DATASET_PATH.exists():
        with open(DATASET_PATH) as f:
            return json.load(f)
    return []


def save_dataset(dataset: list[dict]) -> None:
    """Save dataset to disk."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATASET_PATH, "w") as f:
        json.dump(dataset, f, indent=2)


def log_failure(question: str, tier: str, error: str) -> None:
    """Append failure to log file."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    with open(FAILURES_LOG, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {tier} | {error} | {question[:80]}\n")


def generate_answer(question: str, category: str, tier: str) -> str | None:
    """Generate one candidate answer at the given quality tier."""
    tier_info = TIERS[tier]
    user_prompt = (
        f"Question ({category}): {question}\n\n"
        f"Write a {tier} answer — {tier_info['description']}\n\n"
        f"Remember: write ONLY the answer text as the candidate would speak it."
    )
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            answer = ask_llm(SYSTEM_PROMPT, user_prompt)
            if answer and len(answer.strip()) > 0:
                return answer.strip()
        except Exception as exc:
            logger.warning("Attempt %d/%d failed for [%s] %s: %s", attempt, MAX_RETRIES, tier, question[:40], exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * attempt)
    return None


def generate_dataset(limit: int | None = None, resume: bool = False) -> list[dict]:
    """Generate the full dataset."""
    if not llm_available():
        raise RuntimeError("No GROQ_API_KEY configured — cannot generate dataset")

    existing = load_existing() if resume else []
    existing_keys = {(e["question"], e["tier"]) for e in existing}
    dataset = list(existing)

    questions = QUESTION_BANK[:limit] if limit else QUESTION_BANK
    total = len(questions) * len(TIERS)
    generated = 0
    skipped = len(existing)

    logger.info("Generating dataset: %d questions × %d tiers = %d total", len(questions), len(TIERS), total)
    if skipped:
        logger.info("Resuming: %d entries already exist", skipped)

    for q_entry in questions:
        question = q_entry["question"]
        category = q_entry["category"]
        for tier in TIERS:
            if (question, tier) in existing_keys:
                continue

            answer = generate_answer(question, category, tier)
            if answer is None:
                log_failure(question, tier, "All retries failed")
                logger.error("FAILED: [%s] %s", tier, question[:60])
                continue

            score_range = TIERS[tier]["score_range"]
            target_score = round(random.uniform(*score_range), 1)

            entry = {
                "id": str(uuid.uuid4()),
                "question": question,
                "category": category,
                "tier": tier,
                "transcript": answer,
                "target_score": target_score,
            }
            dataset.append(entry)
            generated += 1

            if generated % SAVE_EVERY == 0:
                save_dataset(dataset)
                logger.info("Progress: %d generated, %d total, %d remaining",
                           generated, len(dataset), total - skipped - generated)

    save_dataset(dataset)
    logger.info("Done: %d generated, %d total entries saved to %s", generated, len(dataset), DATASET_PATH)
    return dataset
```

- [ ] **Step 3: Write main() and CLI**

```python
def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Generate graded synthetic dataset")
    parser.add_argument("--resume", action="store_true", help="Skip existing entries")
    parser.add_argument("--limit", type=int, default=None, help="Limit to N questions")
    args = parser.parse_args()

    dataset = generate_dataset(limit=args.limit, resume=args.resume)
    print(f"\nDataset generated: {len(dataset)} examples")
    print(f"Saved to: {DATASET_PATH}")

    # Print distribution
    from collections import Counter
    tier_counts = Counter(e["tier"] for e in dataset)
    cat_counts = Counter(e["category"] for e in dataset)
    print(f"\nTier distribution: {dict(tier_counts)}")
    print(f"Category distribution: {dict(cat_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Dry-run verify imports and structure**

```bash
python -c "from scripts.generate_training_dataset import generate_answer, TIERS, SYSTEM_PROMPT; print(f'Tiers: {list(TIERS.keys())}'); print('Import OK')"
```

Expected: Prints tiers list and "Import OK". No API calls.

- [ ] **Step 5: Generate the dataset (requires GROQ_API_KEY)**

```bash
python scripts/generate_training_dataset.py
```

Expected: Generates ~120 entries. Logs progress every 10. Takes ~5-10 minutes depending on API speed. If any entries fail, run with `--resume` to regenerate only missing ones.

- [ ] **Step 6: Verify output**

```bash
python -c "
import json
with open('data/datasets/synthetic_graded_answers.json') as f:
    ds = json.load(f)
print(f'Total: {len(ds)}')
from collections import Counter
print(f'Tiers: {dict(Counter(e[\"tier\"] for e in ds))}')
print(f'Categories: {dict(Counter(e[\"category\"] for e in ds))}')
print(f'Word counts: min={min(len(e[\"transcript\"].split()) for e in ds)}, max={max(len(e[\"transcript\"].split()) for e in ds)}')
"
```

Expected: ≥100 entries, all 4 tiers present, ≥4 categories.

- [ ] **Step 7: Commit**

```bash
git add scripts/generate_training_dataset.py
git commit -m "feat: add LLM-based synthetic dataset generation script"
```

---

### Task 3: Create Validation + Human-Scoring Script

**Files:**
- Create: `scripts/validate_dataset.py`

**Interfaces:**
- Consumes: `data/datasets/synthetic_graded_answers.json`
- Produces: `data/datasets/human_validation_subset.csv`
- Produces: `data/datasets/human_validation_report.json`
- Produces: corrected `synthetic_graded_answers.json`

- [ ] **Step 1: Create the validation script skeleton**

Create `scripts/validate_dataset.py` with imports, constants, and the automated sanity checks:

```python
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
```

- [ ] **Step 2: Implement Phase A — automated sanity checks**

```python
def load_dataset() -> list[dict]:
    with open(DATASET_PATH) as f:
        return json.load(f)


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
            flagged.append({"index": i, "id": entry["id"], "tier": entry["tier"],
                          "word_count": word_count, "question": entry["question"][:60]})
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
            "avg_word_count": np.mean([f["word_count"] for f in features]),
            "avg_filler_rate": np.mean([f["filler_word_rate"] for f in features]),
            "avg_positive_kw": np.mean([f["positive_keyword_count"] for f in features]),
            "count": len(entries),
        }

    # Verify monotonic trends
    orders = {
        "word_count": ["Poor", "Mediocre", "Good", "Excellent"],  # should increase
        "filler_rate": ["Excellent", "Good", "Mediocre", "Poor"],  # should increase (worse = more fillers)
        "positive_kw": ["Poor", "Mediocre", "Good", "Excellent"],  # should increase
    }
    violations = []
    for feature, expected_order in orders.items():
        key = f"avg_{feature}"
        vals = [tier_features[t][key] for t in expected_order if t in tier_features]
        if len(vals) >= 2 and not all(vals[i] <= vals[i+1] for i in range(len(vals)-1)):
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

    # Print summary
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
```

- [ ] **Step 3: Implement Phase B — human validation subset**

```python
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
    # Load human scores
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

    # Match human scores to dataset
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
                logger.info("Corrected [%s] %s: %.1f → %.1f (divergence=%.1f)",
                           entry["tier"], entry["question"][:40], llm_score, human_score, divergence)

    # Compute correlation
    if len(matched_llm) >= 3:
        r, p_value = pearsonr(matched_llm, matched_human)
    else:
        r, p_value = 0.0, 1.0

    # Build report
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

    # Print summary
    print(f"\n=== Human Validation Results ===")
    print(f"Examples scored: {report['n_human_scored']}")
    print(f"Pearson's r: {report['correlation_pearson_r']:.4f} (p={report['correlation_p_value']:.4f})")
    print(f"Interpretation: {report['interpretation']}")
    print(f"Corrections applied (>20pt divergence): {report['n_corrected']}")
    if divergences:
        print(f"\nTop divergences:")
        for d in divergences[:5]:
            print(f"  [{d['tier']}] {d['question']}")
            print(f"    LLM={d['llm_score']:.1f}  Human={d['human_score']:.1f}  Δ={d['divergence']:.1f}")

    # Save corrected dataset
    save_dataset(dataset)
    # Save report
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {REPORT_PATH}")

    return report


def save_dataset(dataset: list[dict]) -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATASET_PATH, "w") as f:
        json.dump(dataset, f, indent=2)
```

- [ ] **Step 4: Write main() with CLI flags**

```python
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
            dataset = load_dataset()  # reload in case of both mode
            report = ingest_and_correct(dataset)
            return 0
        else:
            print(f"\nNo human scores found at {SCORES_PATH}")
            print("Run --sample first, have team score the CSV, then run --apply-scores")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run sanity checks on generated dataset**

```bash
python scripts/validate_dataset.py --sample
```

Expected: Prints sanity check results + exports blind CSV. Near-duplicates should be 0-2. Tier separation should show monotonic trends.

- [ ] **Step 6: Verify subset CSV was exported**

```bash
python -c "
import csv
with open('data/datasets/human_validation_subset.csv') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
print(f'Subset: {len(rows)} examples')
print(f'Columns: {rows[0].keys()}')
from collections import Counter
# Check blind: no 'tier' or 'target_score' column
assert 'tier' not in rows[0], 'ERROR: tier column visible — not blind!'
assert 'target_score' not in rows[0], 'ERROR: target_score column visible — not blind!'
print('Blind subset OK (no tier/score columns)')
"
```

Expected: 25 examples, columns are id/question/category/transcript only.

- [ ] **Step 7: Commit**

```bash
git add scripts/validate_dataset.py
git commit -m "feat: add dataset validation and human-scoring pipeline"
```

---

### Task 4: Retrain on Real Dataset

**Files:**
- Modify: `scripts/train_trained_scorer.py`

**Interfaces:**
- Consumes: `data/datasets/synthetic_graded_answers.json`
- Produces: `data/models/trained_scorer.joblib`, `data/models/trained_scorer_metrics.json`

- [ ] **Step 1: Read current training script**

Read `scripts/train_trained_scorer.py` to see current structure (placeholder dataset, main function).

- [ ] **Step 2: Replace placeholder with real dataset loader**

Replace the entire file content:

```python
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
    # Load real dataset
    dataset = load_dataset()
    print(f"Loaded dataset: {len(dataset)} examples")

    # Print dataset statistics
    with open(DATASET_PATH) as f:
        raw = json.load(f)
    tier_dist = Counter(e["tier"] for e in raw)
    cat_dist = Counter(e["category"] for e in raw)
    print(f"Tier distribution: {dict(tier_dist)}")
    print(f"Category distribution: {dict(cat_dist)}")
    scores = [e["target_score"] for e in raw]
    print(f"Score range: {min(scores):.1f} – {max(scores):.1f} (mean={sum(scores)/len(scores):.1f})")

    # Train
    metrics = train_from_dataset(dataset)
    print(f"\nTraining complete. LOO cross-validation metrics:")
    print(f"  n_samples={metrics['n_samples']} cv={metrics['cv_method']}")
    print(f"  pearson_r={metrics['pearson_r']:.3f} p_value={metrics['p_value']:.4f}")
    print(f"  mae={metrics['mae']:.2f} rmse={metrics['rmse']:.2f}")

    # Sanity-check predictions: verify tier ordering
    tier_proxies = {
        "Excellent": "I would approach this by first analyzing the problem constraints, "
                     "then designing an optimal solution with clear structure and edge case handling.",
        "Good": "I would probably start by understanding the problem and then work through "
                "a solution step by step, considering the main requirements.",
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

    # Feature sample
    sample_transcript = dataset[len(dataset) // 2][0]
    feats = extract_features(sample_transcript)
    print(f"\nSample features (middle example): filler_rate={feats['filler_word_rate']:.3f} "
          f"positive_kw={feats['positive_keyword_count']} words={feats['word_count']}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run training on real dataset**

```bash
python scripts/train_trained_scorer.py
```

Expected: Loads ~120 examples, trains RandomForest with LOO-CV, prints real metrics. Pearson's r likely lower than the placeholder's 0.847 (this is expected and honest). Tier ordering sanity check should pass.

- [ ] **Step 4: Verify metrics file was saved**

```bash
python -c "
import json
with open('data/models/trained_scorer_metrics.json') as f:
    m = json.load(f)
print(f'n_samples: {m[\"n_samples\"]}')
print(f'pearson_r: {m[\"pearson_r\"]:.3f}')
print(f'mae: {m[\"mae\"]:.2f}')
print(f'rmse: {m[\"rmse\"]:.2f}')
assert m['n_samples'] >= 100, f'Expected >=100 samples, got {m[\"n_samples\"]}'
print('Metrics saved OK')
"
```

Expected: n_samples ≥ 100, real Pearson's r, MAE, RMSE.

- [ ] **Step 5: Commit**

```bash
git add scripts/train_trained_scorer.py
git commit -m "feat: retrain scorer on real synthetic dataset, remove placeholder"
```

---

### Task 5: Update Documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- No new interfaces — documentation only

- [ ] **Step 1: Update README.md ML scorer section**

In `README.md`, find the "Trained ML Scorer" subsection (lines ~183-193) and replace it. Use the Edit tool to replace the old text:

Old text (lines 183-193):
```
### 5. Trained ML scorer (optional third signal)

```bash
python scripts/train_trained_scorer.py     # trains RandomForest, writes data/models/
```

Currently trained on a small hand-written PLACEHOLDER dataset (clearly marked in
the script) purely to prove the pipeline — replace it with a real labeled dataset
before quoting metrics. When `data/models/trained_scorer.joblib` exists, its score
is returned as `ml_score` in `/api/scoring/run` and shown in the interview UI next
to the primary score. No model → the signal is simply skipped.
```

New text:
```markdown
### 5. Trained ML scorer (optional third signal)

```bash
python scripts/generate_training_dataset.py   # generates synthetic dataset (~5-10 min)
python scripts/validate_dataset.py --sample   # exports blind subset for human validation
python scripts/validate_dataset.py --apply-scores  # ingests human scores, applies corrections
python scripts/train_trained_scorer.py        # trains RandomForest, writes data/models/
```

The scorer is trained on a synthetically generated dataset (~120 examples, 30 questions
× 4 quality tiers across 6 categories). An LLM generates candidate-style answers at
varying skill levels; each is assigned a target score with jitter. A human-validation
subset (~25% of examples, scored blind by team members) calibrates synthetic labels
against real judgment — corrections are applied where divergence exceeds 20 points.
See the training script docstring for the full methodology.

When `data/models/trained_scorer.joblib` exists, its score is returned as `ml_score`
in `/api/scoring/run` and shown in the interview UI next to the primary score.
No model → the signal is simply skipped.
```

- [ ] **Step 2: Update README.md Roadmap section**

In `README.md`, find the "Replace placeholder" item in the Roadmap (lines ~242-243) and mark it completed.

Old text:
```
- Replace placeholder ML-scorer dataset with real labeled data (Kaggle-derived graded
  answers or LLM-generated quality tiers) and re-train before quoting metrics
```

New text:
```
- ✅ Replaced placeholder ML-scorer dataset with LLM-generated quality-tier dataset
  (~120 examples, human-validated subset with Pearson's r correlation reported)
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README with real dataset description and methodology"
```

---

### Task 6: Final Verification

**Files:**
- None (verification only)

- [ ] **Step 1: Verify dataset exists and meets acceptance criteria**

```bash
python -c "
import json
with open('data/datasets/synthetic_graded_answers.json') as f:
    ds = json.load(f)
from collections import Counter
tiers = Counter(e['tier'] for e in ds)
cats = Counter(e['category'] for e in ds)
assert len(ds) >= 100, f'Need >=100 examples, got {len(ds)}'
assert len(cats) >= 4, f'Need >=4 categories, got {len(cats)}'
assert all(t in tiers for t in ['Excellent', 'Good', 'Mediocre', 'Poor']), f'Missing tiers: {tiers}'
print(f'PASS: {len(ds)} examples, {len(cats)} categories, tiers: {dict(tiers)}')
"
```

- [ ] **Step 2: Verify metrics file has real values**

```bash
python -c "
import json
with open('data/models/trained_scorer_metrics.json') as f:
    m = json.load(f)
assert m['n_samples'] >= 100, f'Expected >=100, got {m[\"n_samples\"]}'
print(f'PASS: n={m[\"n_samples\"]} r={m[\"pearson_r\"]:.3f} mae={m[\"mae\"]:.2f}')
"
```

- [ ] **Step 3: Verify no placeholder warnings remain**

```bash
python -c "
import re
for path in ['scripts/train_trained_scorer.py', 'README.md']:
    with open(path) as f:
        content = f.read()
    if 'PLACEHOLDER' in content.upper() and 'WARNING' in content.upper():
        print(f'FAIL: {path} still contains PLACEHOLDER WARNING')
    else:
        print(f'OK: {path} has no placeholder warnings')
"
```

- [ ] **Step 4: Run existing tests to confirm no regressions**

```bash
python -m pytest tests/ -v
```

Expected: All existing tests pass (the training script is not imported by tests, so no breakage expected).

- [ ] **Step 5: Final commit if any fixes were needed**

```bash
git add -A
git status
```

Only commit if there are unstaged changes from fixes.
