"""
Question selection engine for MODE 2 structured screening.

Selects questions from the existing question_bank.py first, then uses LLM
generation when bank coverage is insufficient or the recruiter requests
JD-specific questions.  Every returned question carries full metadata so
the scoring pipeline and candidate page can consume it uniformly.

Fallback hierarchy:
  JD skill matching  →  question bank  →  LLM generation  →  generic bank
"""
import json
import logging
import uuid
from typing import Optional

from app.core.question_bank import QUESTION_BANK
from app.engine import llm_client

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {q["category"] for q in QUESTION_BANK}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}

DEFAULT_COMPOSITION = {
    "Technical Knowledge": 5,
    "Problem Solving": 2,
    "Behavioral": 1,
    "Communication": 1,
    "DSA": 1,
}

CATEGORY_KEYWORDS = {
    "Technical Knowledge": [],
    "DSA": [],
    "System Design": [],
    "Behavioral": [],
    "Communication": [],
    "Problem Solving": [],
}


def _skill_keywords(job_description: str) -> list[str]:
    """Extract lowercase skill tokens from the JD for fuzzy matching."""
    if not job_description:
        return []
    lower = job_description.lower()
    technical_tokens = [
        "python", "java", "javascript", "typescript", "react", "node",
        "fastapi", "django", "flask", "spring", "sql", "postgresql",
        "mysql", "mongodb", "redis", "docker", "kubernetes", "aws",
        "gcp", "azure", "ci/cd", "git", "rest", "graphql", "api",
        "microservices", "linux", "bash", "html", "css", "tailwind",
        "machine learning", "ml", "data", "pandas", "numpy", "spark",
        "kafka", "rabbitmq", "elasticsearch", "terraform", "ansible",
        "testing", "pytest", "jest", "cypress", "selenium", "agile",
        "scrum", "system design", "oop", "design pattern",
    ]
    return [t for t in technical_tokens if t in lower]


def _scale_composition(composition: dict[str, int], num_questions: int) -> dict[str, int]:
    """Scale a fixed category->count composition to the requested size.

    Preserves relative weights so a smaller interview doesn't collapse into
    a single category. Rounds to whole counts and returns the original order.
    """
    total = sum(composition.values())
    if total <= 0 or num_questions <= 0:
        return {k: 0 for k in composition}
    scaled: dict[str, int] = {}
    remaining = num_questions
    keys = list(composition.keys())
    for i, k in enumerate(keys):
        if i == len(keys) - 1:
            scaled[k] = remaining
        else:
            count = round(composition[k] / total * num_questions)
            count = max(0, min(count, remaining))
            scaled[k] = count
            remaining -= count
    return scaled


def _bank_questions_by_category() -> dict[str, list[dict]]:
    by_cat: dict[str, list[dict]] = {}
    for i, q in enumerate(QUESTION_BANK):
        cat = q["category"]
        by_cat.setdefault(cat, []).append({
            "question_id": f"bank_{i}",
            "question_text": q["question"],
            "category": cat,
            "competency": cat,
            "difficulty": "medium",
            "source": "bank",
        })
    return by_cat


def _skill_matches_question(skill: str, question_text: str) -> bool:
    """Check if a skill keyword appears in a question's text."""
    return skill.lower() in question_text.lower()


def _select_from_bank(
    job_description: str,
    num_questions: int,
    composition: Optional[dict[str, int]] = None,
) -> list[dict]:
    """Select questions from the bank, prioritising JD-relevant ones."""
    if composition is None:
        composition = DEFAULT_COMPOSITION

    by_cat = _bank_questions_by_category()
    skills = _skill_keywords(job_description)
    selected: list[dict] = []
    used_ids: set[str] = set()

    for category, count in composition.items():
        pool = by_cat.get(category, [])
        if not pool:
            continue

        def _score(q: dict) -> int:
            s = 0
            for sk in skills:
                if _skill_matches_question(sk, q["question_text"]):
                    s += 10
            return s

        ranked = sorted(pool, key=_score, reverse=True)
        taken = 0
        for q in ranked:
            if len(selected) >= num_questions:
                break
            if taken >= count:
                break
            if q["question_id"] in used_ids:
                continue
            selected.append(q)
            used_ids.add(q["question_id"])
            taken += 1

    remaining = num_questions - len(selected)
    if remaining > 0:
        for cat, pool in by_cat.items():
            if cat in composition:
                continue
            for q in pool:
                if remaining <= 0:
                    break
                if q["question_id"] in used_ids:
                    continue
                selected.append(q)
                used_ids.add(q["question_id"])
                remaining -= 1

    return selected[:num_questions]


def _generate_llm_questions(
    job_description: str,
    num_questions: int,
    categories: Optional[list[str]] = None,
) -> list[dict]:
    """Use LLM to generate JD-specific questions. Returns validated list."""
    if not llm_client.llm_available():
        logger.warning("question_selector: LLM unavailable, skipping generation")
        return []

    cats = categories or list(DEFAULT_COMPOSITION.keys())[:3]
    system = (
        "You are an expert technical interviewer. Generate interview questions "
        "tailored to the given job description. Return ONLY a JSON object with a "
        "'questions' array, where each element is an object with: "
        "question_text (string), category (one of: Technical Knowledge, "
        "DSA, System Design, Behavioral, Communication, Problem Solving), "
        "competency (string describing what this tests), difficulty (easy|medium|hard). "
        "Generate questions that are specific to the technologies and skills mentioned "
        "in the job description. Do not generate generic questions."
    )
    user = (
        f"Job description:\n{job_description}\n\n"
        f"Generate {num_questions} interview questions.\n"
        f"Focus on these categories: {', '.join(cats)}\n"
        f"Return ONLY JSON: {{\"questions\": [...]}}"
    )

    try:
        raw = llm_client.ask_llm(system, user, json_mode=True)
        parsed = llm_client.parse_llm_json(raw)
        if isinstance(parsed, dict) and "questions" in parsed:
            items = parsed["questions"]
        elif isinstance(parsed, list):
            items = parsed
        else:
            items = None
        if not isinstance(items, list):
            # Tolerate a bare top-level array (some backends ignore json_mode).
            try:
                direct = json.loads(raw)
                if isinstance(direct, list):
                    items = direct
            except (TypeError, ValueError):
                pass
        if not isinstance(items, list):
            logger.warning("question_selector: unexpected LLM response shape")
            return []
    except Exception as exc:
        logger.warning("question_selector: LLM generation failed: %s", exc)
        return []

    validated = []
    seen_texts: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        qt = (item.get("question_text") or "").strip()
        cat = (item.get("category") or "").strip()
        comp = (item.get("competency") or "").strip()
        diff = (item.get("difficulty") or "medium").strip().lower()

        if not qt or len(qt) < 10:
            continue
        if qt.lower() in seen_texts:
            continue
        if cat not in VALID_CATEGORIES:
            cat = "Technical Knowledge"
        if diff not in VALID_DIFFICULTIES:
            diff = "medium"

        seen_texts.add(qt.lower())
        validated.append({
            "question_id": f"gen_{uuid.uuid4().hex[:8]}",
            "question_text": qt,
            "category": cat,
            "competency": comp or cat,
            "difficulty": diff,
            "source": "generated",
        })

    return validated[:num_questions]


def select_questions(
    job_description: str = "",
    num_questions: int = 10,
    composition: Optional[dict[str, int]] = None,
    force_generated: bool = False,
) -> list[dict]:
    """Main entry point: select a question set for an interview session.

    Args:
        job_description: The JD text for skill extraction.
        num_questions: Desired total question count.
        composition: Category -> count override. Uses DEFAULT_COMPOSITION if None.
        force_generated: If True, prefer LLM-generated questions.

    Returns:
        List of validated question dicts with full metadata.
    """
    if composition is None:
        composition = dict(DEFAULT_COMPOSITION)

    total_desired = num_questions
    composition = _scale_composition(composition, total_desired)

    if force_generated and llm_client.llm_available():
        generated = _generate_llm_questions(job_description, total_desired)
        if len(generated) >= total_desired:
            logger.info(
                "question_selector: generated %d questions (forced)", len(generated)
            )
            return generated
        remaining = total_desired - len(generated)
        bank = _select_from_bank(job_description, remaining, composition)
        combined = generated + bank
        logger.info(
            "question_selector: generated %d + bank %d = %d questions",
            len(generated), len(bank), len(combined),
        )
        return combined

    bank = _select_from_bank(job_description, total_desired, composition)
    if len(bank) >= total_desired:
        logger.info("question_selector: %d questions from bank", len(bank))
        return bank

    if llm_client.llm_available():
        shortfall = total_desired - len(bank)
        generated = _generate_llm_questions(job_description, shortfall)
        combined = bank + generated
        if len(combined) >= total_desired:
            logger.info(
                "question_selector: bank %d + generated %d = %d questions",
                len(bank), len(generated), len(combined),
            )
            return combined

    logger.info("question_selector: fallback — %d questions from bank only", len(bank))
    return bank
