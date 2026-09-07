DEFAULT_QUESTIONS = [
    "Tell me about yourself and your background.",
    "Describe a challenging technical problem you solved recently.",
    "How do you approach working in a team with conflicting opinions?",
    "What interests you about this role?",
    "Where do you see yourself professionally in three years?",
]


def questions_for_job(job_title: str, description: str, profile: dict | None = None) -> list[str]:
    """Build a small, explainable question set from the job and resume."""
    profile = profile or {}
    skills = profile.get("skills", [])
    questions = [
        f"What makes you a strong fit for the {job_title} role?",
        f"Describe a project where you applied skills relevant to {job_title}.",
    ]
    if skills:
        questions.append(
            f"Walk me through your experience with {', '.join(skills[:3])}."
        )
    questions.extend([
        f"How would you approach a difficult problem described in this role: {description[:180]}?",
        "Tell me about a time you received difficult feedback and what you changed.",
    ])
    return questions
