"""
Live verification (Task 1): proves score_answer / explain_score /
audit_bias actually reach the Groq API with a real key - verified via
llm_client.call_log, not assumed.

Usage:
    1. Put GROQ_API_KEY=<your free key> in .env (or $env:GROQ_API_KEY)
    2. python scripts/verify_llm_live.py

Exit code 0 = all three functions demonstrably called the LLM.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine import llm_client  # noqa: E402
from app.engine.explainability import explain_score  # noqa: E402
from app.engine.fairness import audit_bias  # noqa: E402
from app.engine.scoring import score_answer  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

TRANSCRIPT = (
    "I would solve the duplicate-detection problem with a hash map keyed on a normalized "
    "fingerprint of each record. Building it is O(n) time and O(n) space. The edge cases I'd "
    "handle are empty input, unicode normalization differences, and near-duplicates that differ "
    "only in whitespace. A brute-force pairwise comparison would be O(n squared), so the hash "
    "approach is the optimal trade-off here."
)

RUBRIC = {"criteria": ["time complexity", "space complexity", "edge cases", "optimal approach"]}


def main() -> int:
    if not llm_client.llm_available():
        print("GROQ_API_KEY is NOT set (checked env + .env). "
              "Add it to .env first - this script cannot verify anything without it.")
        return 2

    print(f"Key found. Model: {llm_client.GROQ_MODEL}. Running the three functions...\n")

    calls_before = len(llm_client.call_log)

    score = score_answer("verify-session", "q1", "DSA", TRANSCRIPT, RUBRIC)
    print(f"[1/3] score_answer    -> score={score.score} confidence={score.confidence}")

    explanation = explain_score("verify-session", "q1", TRANSCRIPT, score.score)
    print(f"[2/3] explain_score   -> {explanation.summary[:120]}")
    print(f"      supporting      -> {explanation.supporting_phrases}")

    flag = audit_bias("verify-session", "q1",
                      "He said his solution was robust and he tested it carefully.", score.score)
    print(f"[3/3] audit_bias      -> delta={flag.score_delta} note={flag.note[:100]}")

    new_calls = llm_client.call_log[calls_before:]
    ok_calls = [c for c in new_calls if c.get("ok")]
    print(f"\nGroq API calls recorded during this run: {len(new_calls)} "
          f"({len(ok_calls)} succeeded)")
    for c in new_calls:
        print(f"  - attempt={c.get('attempt')} status={c.get('status')} "
              f"ok={c.get('ok')} latency_ms={c.get('latency_ms')} error={c.get('error')}")

    # Each function should have made exactly one successful API call;
    # fewer than 3 means something silently dropped to the heuristic path.
    verified = len(ok_calls) >= 3
    print("\nVERDICT:", "PASS - all three functions demonstrably reached the LLM."
          if verified else
          "FAIL - fewer than 3 successful API calls; some function fell back to heuristic.")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
