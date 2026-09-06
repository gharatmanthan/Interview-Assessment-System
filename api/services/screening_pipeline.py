"""
Canonical ATS Screening Pipeline.

Single entry point: screen_resume_against_job(resume_data, job)
All ingestion paths (public apply, manual upload, re-screen, email intake)
must call this function to ensure identical results for identical inputs.
"""
from __future__ import annotations

from typing import TypedDict, NotRequired
from dataclasses import dataclass


# ─── Output Type Definitions ──────────────────────────────────────────────


class MatchResult(TypedDict):
    match_score: float
    matched_skills: list[str]
    missing_skills: list[str]


class HardRequirementsResult(TypedDict):
    hard_requirements_passed: bool
    hard_requirement_failures: list[str]


class ComponentScores(TypedDict):
    skills: float
    experience: float
    semantic: float
    education: float
    keyword: float


class DecisionResult(TypedDict):
    decision: str  # "passed" | "manual_review" | "below_threshold"
    decision_reason: str


class ScreeningResult(TypedDict):
    ats_score: float
    component_scores: ComponentScores
    matched_skills: list[str]
    missing_skills: list[str]
    hard_requirements_passed: bool
    hard_requirement_failures: list[str]
    decision: str
    decision_reason: str
    matcher_method: str


# ─── Configuration ────────────────────────────────────────────────────────

DEFAULT_WEIGHTS: dict[str, int] = {
    "skills": 40,
    "experience": 20,
    "semantic": 20,
    "education": 10,
    "keyword": 10,
}

# Education synonym mapping for semantic matching
# Maps canonical degree/field names to their common variants
EDUCATION_SYNONYMS: dict[str, list[str]] = {
    # Computer Science / Software Engineering degrees
    "computer science": [
        "computer science", "cs", "b.tech computer science", "btech cs",
        "b.e. computer science", "be cs", "b.sc computer science", "bsc cs",
        "m.tech computer science", "mtech cs", "m.e. computer science", "me cs",
        "ms computer science", "master of computer applications", "mca",
        "bachelor of computer applications", "bca",
    ],
    "software engineering": [
        "software engineering", "b.tech software engineering", "btech se",
        "b.e. software engineering", "be se", "m.tech software engineering",
        "ms software engineering",
    ],
    "information technology": [
        "information technology", "it", "b.tech it", "btech it",
        "b.e. it", "be it", "m.tech it", "mtech it",
        "b.sc it", "bsc it", "m.sc it", "msc it",
        "mca", "master of computer applications",
    ],
    "computer engineering": [
        "computer engineering", "b.tech computer engineering", "btech ce",
        "b.e. computer engineering", "be ce", "m.tech computer engineering",
    ],
    # Generic degree levels (bachelor's, master's)
    "bachelor": [
        "bachelor", "b.tech", "btech", "bachelor of technology",
        "b.e.", "be", "bachelor of engineering",
        "b.sc", "bsc", "bachelor of science",
        "bca", "bachelor of computer applications",
    ],
    "master": [
        "master", "m.tech", "mtech", "master of technology",
        "m.e.", "me", "master of engineering",
        "m.sc", "msc", "master of science",
        "mca", "master of computer applications",
        "ms", "m.s.",
    ],
    # Specific degree variants (for backward compatibility)
    "btech": ["b.tech", "btech", "bachelor of technology"],
    "be": ["b.e.", "be", "bachelor of engineering"],
    "mtech": ["m.tech", "mtech", "master of technology"],
    "me": ["m.e.", "me", "master of engineering"],
    "bsc": ["b.sc", "bsc", "bachelor of science"],
    "msc": ["m.sc", "msc", "master of science"],
    "bca": ["bca", "bachelor of computer applications"],
    "mca": ["mca", "master of computer applications"],
    # Generic CS-related fields
    "data science": ["data science", "data analytics", "machine learning", "artificial intelligence"],
    "cybersecurity": ["cybersecurity", "information security", "network security"],
}

# Fields that qualify as "Software/CS" for education matching
SOFTWARE_CS_FIELDS: set[str] = {
    "computer science", "software engineering", "information technology",
    "computer engineering", "data science", "cybersecurity",
}

# Internship keywords for fresher experience credit
INTERNSHIP_KEYWORDS: set[str] = {
    "intern", "internship", "trainee", "apprentice", "co-op", "coop",
    "summer intern", "winter intern", "industrial training",
}

# LLM System Prompt for semantic screening inference
LLM_SYSTEM_PROMPT: str = """
You are an expert ATS (Applicant Tracking System) evaluator. Your task is to perform semantic matching
between a candidate's resume and a job description, going beyond simple keyword matching.

EVALUATION CRITERIA:
1. SKILLS: Identify both explicit skills and semantically related skills (e.g., "PyTorch" relates to "Deep Learning",
   "React" relates to "Frontend Development", "Kubernetes" relates to "Container Orchestration").
   
2. EXPERIENCE: Evaluate years of relevant experience semantically. Consider:
   - Internships, co-ops, and apprenticeships count as valid experience, especially for fresher/entry-level roles
   - Project work, open source contributions, and freelance work count as experience
   - For roles requiring 0 years (freshers), any internship/project work = full credit (100)
   - Experience quality matters more than just duration

3. EDUCATION: Use semantic field matching, not just string matching:
   - "Computer Engineering", "B.E.", "B.Tech", "B.Sc Computer Science", "MCA", "M.Tech" 
     all qualify as "Computer Science/Software Engineering" fields
   - Consider the field of study, not just the exact degree name
   - Related fields (IT, Data Science, Cybersecurity) may partially qualify

4. HARD REQUIREMENTS: Evaluate strictly but with semantic understanding:
   - Minimum experience: consider internship/project experience for freshers
   - Required education: match field semantically, not just string containment
   - Mandatory skills: check for semantic equivalents, not just exact matches

OUTPUT FORMAT: Return a JSON object with:
- matched_skills: list of skills found (including semantic matches)
- missing_skills: list of required skills not found
- experience_assessment: {years: float, quality: "high|medium|low", fresher_credit: bool}
- education_match: {matched: bool, field: str, confidence: float}
- hard_requirements: {passed: bool, failures: list[str]}
- overall_reasoning: brief explanation of the evaluation

Be thorough but concise. Prioritize semantic understanding over literal matching.
"""

COMMON_SKILLS: list[str] = [
    "python", "java", "javascript", "typescript", "sql", "postgresql", "mysql",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
    "react", "vue", "angular", "django", "flask", "fastapi", "spring boot",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
    "git", "ci/cd", "jenkins", "github actions", "gitlab ci",
    "redis", "mongodb", "elasticsearch", "kafka", "rabbitmq",
    "microservices", "rest api", "graphql", "grpc",
    "system design", "algorithms", "data structures",
]


# ─── Helper Functions ─────────────────────────────────────────────────────


def _normalize_text(text: str) -> str:
    """Lowercase and normalize whitespace for keyword matching."""
    return " ".join((text or "").lower().split())


def _extract_skills(text: str) -> set[str]:
    """Extract known skills from text using COMMON_SKILLS list."""
    normalized = _normalize_text(text)
    return {skill for skill in COMMON_SKILLS if skill in normalized}


def _build_jd_text(job: dict) -> str:
    """
    Step 1: Build the full JD text combining description + required skills.
    This ensures manual uploads don't bypass the required_skills list.
    """
    description = job.get("description", "") or ""
    required_skills = job.get("required_skills", []) or []

    parts = [description.strip()]
    if required_skills:
        parts.append("Required skills:\n" + "\n".join(f"- {s}" for s in required_skills))

    return "\n\n".join(p for p in parts if p)


def match_resume_to_jd(resume_data: dict, jd_text: str) -> MatchResult:
    """
    Step 2: Match resume against JD using keyword overlap.
    Returns match_score (0-100), matched_skills, missing_skills.
    """
    resume_text = resume_data.get("raw_text", "") or resume_data.get("text", "") or ""
    resume_skills = _extract_skills(resume_text)
    jd_skills = _extract_skills(jd_text)

    matched = sorted(resume_skills & jd_skills)
    missing = sorted(jd_skills - resume_skills)

    if jd_skills:
        match_score = round(len(matched) / len(jd_skills) * 100, 1)
    else:
        match_score = 0.0

    return MatchResult(
        match_score=match_score,
        matched_skills=matched,
        missing_skills=missing,
    )


def _normalize_education(text: str) -> str:
    """Normalize education text for comparison."""
    return _normalize_text(text)


def _education_matches(required_edu: str, resume_edu: str) -> bool:
    """
    Semantic education matching using synonym mapping.
    Returns True if resume education matches required education semantically.
    """
    required_norm = _normalize_education(required_edu)
    resume_norm = _normalize_education(resume_edu)

    if not required_norm or not resume_norm:
        return False

    # Direct substring match (original behavior)
    if required_norm in resume_norm:
        return True

    # Semantic matching via synonyms
    for canonical_field, variants in EDUCATION_SYNONYMS.items():
        required_matches = any(v in required_norm for v in variants)
        resume_matches = any(v in resume_norm for v in variants)
        if required_matches and resume_matches:
            # Both map to the same canonical field
            return True

    # Check if both are in software/CS fields
    required_in_cs = any(field in required_norm for field in SOFTWARE_CS_FIELDS)
    resume_in_cs = any(field in resume_norm for field in SOFTWARE_CS_FIELDS)
    if required_in_cs and resume_in_cs:
        return True

    return False


def _has_internship_experience(resume_text: str) -> bool:
    """Check if resume mentions internship or equivalent experience."""
    normalized = _normalize_text(resume_text)
    return any(kw in normalized for kw in INTERNSHIP_KEYWORDS)


def _has_project_experience(resume_text: str) -> bool:
    """Check if resume mentions project work."""
    normalized = _normalize_text(resume_text)
    project_keywords = {"project", "projects", "capstone", "thesis", "dissertation", 
                        "github", "portfolio", "open source", "freelance", "personal project"}
    return any(kw in normalized for kw in project_keywords)


def _build_jd_text(job: dict) -> str:
    """
    Step 1: Build the full JD text combining description + required skills.
    This ensures manual uploads don't bypass the required_skills list.
    """
    description = job.get("description", "") or ""
    required_skills = job.get("required_skills", []) or []

    parts = [description.strip()]
    if required_skills:
        parts.append("Required skills:\n" + "\n".join(f"- {s}" for s in required_skills))

    return "\n\n".join(p for p in parts if p)


def match_resume_to_jd(resume_data: dict, jd_text: str) -> MatchResult:
    """
    Step 2: Match resume against JD using keyword overlap.
    Returns match_score (0-100), matched_skills, missing_skills.
    """
    resume_text = resume_data.get("raw_text", "") or resume_data.get("text", "") or ""
    resume_skills = _extract_skills(resume_text)
    jd_skills = _extract_skills(jd_text)

    matched = sorted(resume_skills & jd_skills)
    missing = sorted(jd_skills - resume_skills)

    if jd_skills:
        match_score = round(len(matched) / len(jd_skills) * 100, 1)
    else:
        match_score = 0.0

    return MatchResult(
        match_score=match_score,
        matched_skills=matched,
        missing_skills=missing,
    )


def eval_hard_requirements(
    resume_data: dict,
    job: dict,
    missing_skills: list[str],
) -> HardRequirementsResult:
    """
    Step 3: Evaluate hard requirements.
    Checks: minimum_experience_years, required_education, mandatory skills.
    Uses semantic matching for education and considers internship for freshers.
    """
    failures: list[str] = []

    # Experience years
    min_exp = job.get("minimum_experience_years")
    resume_exp = resume_data.get("experience_years", 0) or 0
    resume_text = resume_data.get("raw_text", "") or resume_data.get("text", "") or ""

    # Check for internship/project experience for fresher roles
    has_internship = _has_internship_experience(resume_text)
    has_projects = _has_project_experience(resume_text)
    is_fresher_role = min_exp is not None and min_exp == 0

    if min_exp is not None:
        if is_fresher_role:
            # For fresher roles, check if candidate has internship/project experience
            if not (has_internship or has_projects):
                failures.append(
                    f"Experience: fresher role requires internship/project experience, none found"
                )
        else:
            # Standard experience check
            if resume_exp < min_exp:
                failures.append(
                    f"Experience: requires {min_exp}+ years, resume shows {resume_exp}"
                )

    # Education - semantic matching
    required_edu = (job.get("required_education") or "").strip().lower()
    if required_edu:
        resume_edu = (resume_data.get("education") or "").strip().lower()
        if not _education_matches(required_edu, resume_edu):
            failures.append(f"Education: requires '{required_edu}'")

    # Mandatory skills (required_skills that are missing)
    required_skills = set(job.get("required_skills", []) or [])
    mandatory_missing = required_skills & set(missing_skills)
    for skill in sorted(mandatory_missing):
        failures.append(f"Missing required skill: {skill}")

    return HardRequirementsResult(
        hard_requirements_passed=len(failures) == 0,
        hard_requirement_failures=failures,
    )


def calculate_component_scores(
    resume_data: dict,
    jd_text: str,
    job: dict,
) -> ComponentScores:
    """
    Step 4: Calculate 5 normalized component scores (0-100).
    Uses improved heuristics with semantic matching for education and 
    fresher-friendly experience scoring.
    """
    resume_text = resume_data.get("raw_text", "") or resume_data.get("text", "") or ""
    resume_skills = _extract_skills(resume_text)
    jd_skills = _extract_skills(jd_text)

    # Skills: matched / required
    if jd_skills:
        skills_score = round(len(resume_skills & jd_skills) / len(jd_skills) * 100, 1)
    else:
        skills_score = 0.0

    # Experience: years vs requirement, with fresher-friendly logic
    min_exp = job.get("minimum_experience_years")
    resume_exp = resume_data.get("experience_years", 0) or 0
    resume_text = resume_data.get("raw_text", "") or resume_data.get("text", "") or ""
    has_internship = _has_internship_experience(resume_text)
    has_projects = _has_project_experience(resume_text)
    is_fresher_role = min_exp is not None and min_exp == 0

    if min_exp is not None and min_exp > 0:
        experience_score = round(min(resume_exp / min_exp, 1.0) * 100, 1)
    elif is_fresher_role:
        # Fresher role: full credit if has internship or project experience
        if has_internship or has_projects:
            experience_score = 100.0
        else:
            experience_score = 0.0  # No experience at all for fresher role
    else:
        experience_score = 100.0  # no requirement = full credit

    # Semantic: mock embedding similarity (placeholder)
    # TODO: replace with actual embedding cosine similarity
    semantic_score = round(skills_score * 0.9 + 10, 1)  # proxy

    # Education: semantic matching
    required_edu = (job.get("required_education") or "").strip().lower()
    resume_edu = (resume_data.get("education") or "").strip().lower()
    if required_edu:
        education_score = 100.0 if _education_matches(required_edu, resume_edu) else 0.0
    else:
        education_score = 100.0  # no requirement = full credit

    # Keyword: raw keyword overlap (same as skills for now)
    keyword_score = skills_score

    return ComponentScores(
        skills=skills_score,
        experience=experience_score,
        semantic=semantic_score,
        education=education_score,
        keyword=keyword_score,
    )


def decide_candidate_routing(
    ats_score: float,
    hard_requirements_passed: bool,
    threshold: float = 70.0,
) -> DecisionResult:
    """
    Step 5: Determine routing decision based on ATS score and hard requirements.
    """
    if ats_score >= threshold and hard_requirements_passed:
        return DecisionResult(
            decision="passed",
            decision_reason=f"ATS score {ats_score:.1f} meets threshold {threshold} and all hard requirements passed.",
        )
    elif ats_score >= threshold and not hard_requirements_passed:
        return DecisionResult(
            decision="manual_review",
            decision_reason=f"ATS score {ats_score:.1f} meets threshold {threshold} but hard requirements failed.",
        )
    else:
        return DecisionResult(
            decision="below_threshold",
            decision_reason=f"ATS score {ats_score:.1f} below threshold {threshold}.",
        )


# ─── Main Entry Point ─────────────────────────────────────────────────────


def screen_resume_against_job(resume_data: dict, job: dict) -> ScreeningResult:
    """
    Canonical screening pipeline. Single source of truth for all ATS scoring.

    Args:
        resume_data: dict with keys:
            - raw_text (str): full resume text
            - experience_years (float, optional)
            - education (str, optional)
        job: dict with keys:
            - description (str)
            - required_skills (list[str])
            - minimum_experience_years (float, optional)
            - required_education (str, optional)
            - screening_weights (dict, optional) — overrides DEFAULT_WEIGHTS
            - screening_threshold (float, optional) — overrides default 70.0

    Returns:
        ScreeningResult with all computed fields.
    """
    # Step 1: Build JD text
    jd_text = _build_jd_text(job)

    # Step 2: Match resume to JD
    match_result = match_resume_to_jd(resume_data, jd_text)

    # Step 3: Hard requirements
    hard_result = eval_hard_requirements(resume_data, job, match_result["missing_skills"])

    # Step 4: Component scores
    components = calculate_component_scores(resume_data, jd_text, job)

    # Step 5: Weighted ATS score
    weights = job.get("screening_weights", DEFAULT_WEIGHTS)
    total_weight = sum(weights.values()) or 100
    ats_score = sum(
        components[key] * weights.get(key, 0) for key in components
    ) / total_weight
    ats_score = round(ats_score, 1)

    # Decision
    threshold = job.get("screening_threshold", 70.0)
    decision = decide_candidate_routing(ats_score, hard_result["hard_requirements_passed"], threshold)

    return ScreeningResult(
        ats_score=ats_score,
        component_scores=components,
        matched_skills=match_result["matched_skills"],
        missing_skills=match_result["missing_skills"],
        hard_requirements_passed=hard_result["hard_requirements_passed"],
        hard_requirement_failures=hard_result["hard_requirement_failures"],
        decision=decision["decision"],
        decision_reason=decision["decision_reason"],
        matcher_method="keyword_overlap",
    )


# ─── Quick Self-Test ──────────────────────────────────────────────────────

if __name__ == "__main__":
    job = {
        "description": "We need a Python backend engineer with SQL and AWS experience.",
        "required_skills": ["python", "sql", "aws", "docker"],
        "minimum_experience_years": 3,
        "required_education": "bachelor",
        "screening_threshold": 70.0,
    }

    resume = {
        "raw_text": "Python developer with 5 years experience. Skills: Python, SQL, Docker, Kubernetes. Bachelor in CS.",
        "experience_years": 5,
        "education": "Bachelor of Science in Computer Science",
    }

    result = screen_resume_against_job(resume, job)

    import json
    print(json.dumps(result, indent=2))