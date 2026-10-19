"""
Dynamic AI question generator for InterviewIQ.

Generates the next interview question dynamically after each answer, using:
  - Job title and description
  - Candidate resume profile (skills, experience, projects)
  - Full interview history so far (previous questions + answers + scores)

Uses Groq LLM when GROQ_API_KEY is set.
Falls back to a heuristic template generator when the key is absent or the call fails.
Every fallback is logged so it is never silent.

Max questions per interview: MAX_QUESTIONS = 8
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.engine.llm_client import ask_llm, llm_available

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 8

# Question category rotation — ensures variety across the 8-question interview
_CATEGORY_SEQUENCE = [
    "opening",      # Q1 — who they are, their background
    "technical",    # Q2 — skill-based, drawn from resume skills
    "role_fit",     # Q3 — JD-specific, why this role
    "technical",    # Q4 — deeper technical, probe weak areas
    "project",      # Q5 — reference a real project from resume
    "role_fit",     # Q6 — scenario from JD
    "technical",    # Q7 — hardest technical based on low-scoring areas
    "behavioural",  # Q8 — closing behavioural
]


def _build_history_summary(history: list[dict]) -> str:
    """Format interview history into a compact string for the LLM prompt."""
    if not history:
        return "No questions asked yet — this is the first question."
    lines = []
    for i, entry in enumerate(history, 1):
        score = entry.get("score")
        score_str = f" (scored {score}/100)" if score is not None else ""
        lines.append(
            f"Q{i} [{entry.get('category', 'general')}]: {entry['question']}\n"
            f"   Answer: {entry.get('answer', '(no answer recorded)')[:300]}{score_str}"
        )
    return "\n".join(lines)


def _parse_llm_question(raw: str) -> str:
    """Extract the question string from LLM output, handling JSON or plain text."""
    # Try JSON object with a 'question' key
    try:
        clean = re.sub(r"```(?:json)?\s*|```", "", raw).strip()
        data = json.loads(clean)
        if isinstance(data, dict) and "question" in data:
            return str(data["question"]).strip()
        if isinstance(data, list) and data:
            return str(data[0]).strip()
    except (json.JSONDecodeError, ValueError):
        pass
    # Fall back to first non-empty line
    for line in raw.strip().splitlines():
        line = line.strip().lstrip("1234567890.) -")
        if line and len(line) > 20:
            return line
    return raw.strip()


def generate_next_question(
    job_title: str,
    job_description: str,
    resume_profile: dict[str, Any],
    history: list[dict],
) -> str:
    """
    Generate the next interview question.

    Args:
        job_title:       The job role being interviewed for.
        job_description: Full job description text.
        resume_profile:  Parsed resume dict with keys: skills, experience, projects, education.
        history:         List of dicts, each with keys: question, answer, score, category.
                         Most recent entry is history[-1].

    Returns:
        The next question as a plain string.
    """
    question_number = len(history) + 1
    if question_number > MAX_QUESTIONS:
        return (
            "Thank you — that completes your interview. "
            "The interviewer will review your responses shortly."
        )

    category = _CATEGORY_SEQUENCE[question_number - 1]

    if llm_available():
        try:
            return _generate_llm_question(
                job_title, job_description, resume_profile, history, category, question_number
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM question generation failed (Q%d), using fallback: %s", question_number, exc)

    logger.info("Using heuristic question generation (no API key or LLM failed) for Q%d", question_number)
    return _generate_fallback_question(
        job_title, job_description, resume_profile, history, category, question_number
    )


def _generate_llm_question(
    job_title: str,
    job_description: str,
    resume_profile: dict,
    history: list[dict],
    category: str,
    question_number: int,
) -> str:
    """Call Groq to generate the next tailored question."""
    skills = ", ".join(resume_profile.get("skills", [])[:8]) or "not listed"
    experience = resume_profile.get("experience", "not provided")
    projects = resume_profile.get("projects", "not provided")

    # Identify weak areas from history (score < 60) to probe deeper
    weak_areas = [
        e["question"] for e in history
        if e.get("score") is not None and e["score"] < 60
    ]
    weak_note = ""
    if weak_areas:
        weak_note = (
            f"\nNote: The candidate scored poorly on: {'; '.join(weak_areas[:2])}. "
            "Consider probing these areas deeper if the category allows."
        )

    category_instruction = {
        "opening":    "Ask an opening question about the candidate's background and what draws them to this role.",
        "technical":  "Ask a specific technical question referencing one of their listed skills and the job requirements. Be concrete — name the skill.",
        "role_fit":   "Ask how the candidate's specific experience maps to a requirement in the job description. Quote part of the JD.",
        "project":    "Ask about one of the candidate's listed projects or work experience — their specific contribution and outcomes.",
        "behavioural": "Ask a STAR-method behavioural question relevant to challenges in the job description.",
    }.get(category, "Ask a relevant, tailored interview question.")

    system_prompt = (
        "You are an expert technical interviewer conducting a real job interview. "
        "Generate ONE concise, specific, engaging interview question tailored to THIS candidate and role. "
        "Do not ask generic questions. Reference the candidate's actual skills or experience. "
        'Reply ONLY with a JSON object: {"question": "<your question here>"}'
    )

    user_prompt = (
        f"Job role: {job_title}\n"
        f"Job description (excerpt): {job_description[:600]}\n\n"
        f"Candidate resume:\n"
        f"  Skills: {skills}\n"
        f"  Experience: {experience}\n"
        f"  Projects: {projects}\n\n"
        f"Interview so far (question {question_number} of {MAX_QUESTIONS}):\n"
        f"{_build_history_summary(history)}"
        f"{weak_note}\n\n"
        f"Your task for question {question_number} ({category}):\n"
        f"{category_instruction}\n\n"
        "IMPORTANT: Reference the candidate's ACTUAL skills or experience. One question only."
    )

    raw = ask_llm(system_prompt, user_prompt, json_mode=True)
    question = _parse_llm_question(raw)
    logger.info("LLM generated Q%d [%s]: %s", question_number, category, question[:80])
    return question


def _generate_fallback_question(
    job_title: str,
    job_description: str,
    resume_profile: dict,
    history: list[dict],
    category: str,
    question_number: int,
) -> str:
    """Rule-based question generation when LLM is unavailable."""
    skills = resume_profile.get("skills", [])
    projects = resume_profile.get("projects", "your recent projects")
    jd_excerpt = job_description[:150] if job_description else job_title

    # Rotate through skills for variety
    skill_for_q = skills[question_number % len(skills)] if skills else "your main skill"
    skill_str = ", ".join(skills[:3]) if skills else "your core technical skills"

    templates = {
        "opening": (
            f"Tell me about yourself and what drew you to the {job_title} position."
        ),
        "technical": (
            f"Walk me through a complex problem you solved using {skill_for_q}. "
            "What was your approach and what did you learn from the experience?"
        ),
        "role_fit": (
            f"Looking at this role — '{jd_excerpt}...' — "
            "which part of your experience makes you most ready for these responsibilities?"
        ),
        "project": (
            f"Tell me about {projects if isinstance(projects, str) else 'your most impactful project'}. "
            "What was your specific contribution and what was the measurable outcome?"
        ),
        "behavioural": (
            "Describe a time you had to deliver under tight pressure or ambiguity. "
            "How did you handle it, and what would you do differently now?"
        ),
    }

    # If the previous answer was very short or scored very low, ask a targeted follow-up
    if history:
        last = history[-1]
        last_answer = last.get("answer", "")
        last_score = last.get("score")
        if last_answer and len(last_answer.split()) < 20:
            return (
                f"Could you expand on that? Specifically regarding {skill_str} — "
                "can you give a concrete, real-world example?"
            )
        if last_score is not None and last_score < 50:
            return (
                f"Let's revisit your last point. Can you provide a more specific example "
                f"demonstrating your depth in {skill_for_q}?"
            )

    return templates.get(category, f"What makes you uniquely qualified for the {job_title} role?")
