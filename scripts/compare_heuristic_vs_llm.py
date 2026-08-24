"""
Evidence script (Task 1): runs the same transcripts through the heuristic
scorer AND the real scorer (LLM when GROQ_API_KEY is set, heuristic
otherwise) and prints both side by side. This is evaluation-section
evidence for the report, not a pass/fail test.

Usage:  python scripts/compare_heuristic_vs_llm.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine import llm_client  # noqa: E402
from app.engine.scoring import _heuristic_score, score_answer  # noqa: E402

RUBRIC = {
    "criteria": ["time complexity", "space complexity", "edge cases",
                 "optimal approach", "trade-offs", "correctness"],
}

TRANSCRIPTS = {
    "strong": (
        "The naive approach compares every pair, which is O(n squared). Instead I'd build a "
        "hash map from a normalized fingerprint to indices, giving O(n) average time and O(n) "
        "space. Edge cases: empty input, unicode normalization, near-duplicates differing only "
        "in whitespace. The trade-off is memory for speed, which is optimal for this problem."
    ),
    "weak": (
        "I don't really remember this one. Maybe you could use some kind of loop and check "
        "things. I usually just Google it at work if I'm honest."
    ),
    "rambling": (
        "So basically, um, in my last project we had like a lot of data, you know, and I kind "
        "of thought about it and basically we just sort of wrote some code that actually kind "
        "of worked, literally, and then my manager, he was like okay, and I mean it was fine "
        "basically. So yeah, um, that's like how I would probably approach it honestly."
    ),
    "off-topic": (
        "On weekends I enjoy hiking and cooking pasta with my family. My favorite trail has a "
        "great view. I also collect vinyl records."
    ),
}


def main() -> int:
    llm_on = llm_client.llm_available()
    print(f"LLM available: {llm_on}"
          + ("" if llm_on else "  (no GROQ_API_KEY - 'actual path' column is heuristic too; "
                               "set a key to get real comparison evidence)\n"))
    header = f"{'transcript':<10} | {'heuristic':>9} | {'actual':>9} | note"
    print(header)
    print("-" * len(header))

    for name, transcript in TRANSCRIPTS.items():
        h_score, _ = _heuristic_score(transcript, RUBRIC)
        calls_before = len([c for c in llm_client.call_log if c.get("ok")])
        result = score_answer("compare", f"q-{name}", "DSA", transcript, RUBRIC)
        made_llm_call = len([c for c in llm_client.call_log if c.get("ok")]) > calls_before
        if not llm_on:
            actual = "heuristic"
        elif made_llm_call:
            actual = "LLM"
        else:
            actual = "fallback"  # key present but LLM failed -> heuristic
        note = {
            "strong": "detailed, on-rubric",
            "weak": "no substance",
            "rambling": "long but filler-heavy",
            "off-topic": "irrelevant content",
        }[name]
        print(f"{name:<10} | {h_score:>9.1f} | {result.score:>6.1f} ({actual}) | {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
