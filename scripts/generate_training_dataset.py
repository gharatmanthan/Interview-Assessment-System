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


# ─── Helpers ────────────────────────────────────────────────────────────────

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


# ─── Core Generation ────────────────────────────────────────────────────────

def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks from model output."""
    import re
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return cleaned.strip()


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
            if answer:
                answer = _strip_thinking(answer)
            if answer and len(answer.strip()) > 0:
                return answer.strip()
        except Exception as exc:
            # Rate-limit errors get longer backoff
            is_rate_limit = "429" in str(exc)
            backoff = RETRY_BACKOFF * attempt * (3 if is_rate_limit else 1)
            logger.warning("Attempt %d/%d failed for [%s] %s: %s (backoff=%.1fs)", attempt, MAX_RETRIES, tier, question[:40], exc, backoff)
            if attempt < MAX_RETRIES:
                time.sleep(backoff)
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

            # Small delay between requests to avoid rate limits
            time.sleep(1.0)

            if generated % SAVE_EVERY == 0:
                save_dataset(dataset)
                logger.info("Progress: %d generated, %d total, %d remaining",
                           generated, len(dataset), total - skipped - generated)

    save_dataset(dataset)
    logger.info("Done: %d generated, %d total entries saved to %s", generated, len(dataset), DATASET_PATH)
    return dataset


# ─── CLI & Main ─────────────────────────────────────────────────────────────

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
