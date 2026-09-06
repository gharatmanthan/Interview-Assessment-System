"""
Owner: Member B
OBJECTIVE 2 deliverable: JD matching

Compares parsed resume data (from resume_parser.py) against a job
description to compute a fit score and surface matched/missing skills.

Two paths:
  - LLM semantic matching (default when GROQ_API_KEY is configured):
    the model assesses overall fit in its own words — equivalent skills
    phrased differently ("built REST services" vs "rest api") still count,
    and it produces a short gap analysis.
  - keyword-overlap heuristic (fallback on failure / no key): exact
    substring matches against a common-skills list only.

Which path ran is reported in the result ("matched_by") and logged.
"""
import logging

from app.engine import llm_client
from app.engine.resume_parser import COMMON_SKILLS

logger = logging.getLogger(__name__)


def _extract_jd_skills(job_description: str) -> set:
    lower = job_description.lower()
    return {s for s in COMMON_SKILLS if s in lower}


def _heuristic_match(resume_data: dict, job_description: str) -> dict:
    resume_skills = {s.lower() for s in resume_data.get("skills", [])}
    jd_skills = _extract_jd_skills(job_description)

    if not jd_skills:
        return {"match_score": 0.0, "matched_skills": [], "missing_skills": [],
                "matched_by": "keyword_overlap", "fit_summary":
                "No recognizable skills found in the job description for keyword matching."}

    matched = sorted(resume_skills & jd_skills)
    missing = sorted(jd_skills - resume_skills)
    match_score = round(len(matched) / len(jd_skills) * 100, 1)
    match_score = max(0.0, min(100.0, match_score))

    return {"match_score": match_score, "matched_skills": matched, "missing_skills": missing,
            "matched_by": "keyword_overlap",
            "fit_summary": f"{len(matched)}/{len(jd_skills)} keyword-listed JD skills found on the resume."}


def _clamp(value, lo, hi, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def _llm_match(resume_data: dict, job_description: str) -> dict:
    system = (
        "You are a technical recruiter assessing how well a candidate fits a job. "
        "Match semantically: equivalent experience phrased differently counts "
        '(e.g. "built REST services" covers "rest api"). Respond ONLY as JSON: '
        '{"match_score": <0-100 float>, '
        '"matched_skills": [str, ...], '
        '"missing_skills": [str, ...], '
        '"fit_summary": "<1-2 sentences naming the biggest skill gaps in your own words>"}'
    )
    user = (
        f"Resume skills: {resume_data.get('skills', [])}\n"
        f"Resume experience (years): {resume_data.get('experience_years')}\n\n"
        f"Job description:\n{job_description}"
    )
    raw = llm_client.ask_llm(system, user, json_mode=True, temperature=0.0)
    data = llm_client.parse_llm_json(raw)

    match_score = _clamp(data["match_score"], 0.0, 100.0, None)
    if match_score is None:
        raise ValueError("missing or non-numeric 'match_score' field")

    return {
        "match_score": round(match_score, 1),
        "matched_skills": [str(s) for s in data.get("matched_skills", [])],
        "missing_skills": [str(s) for s in data.get("missing_skills", [])],
        "fit_summary": str(data.get("fit_summary", "")),
        "matched_by": "llm_semantic",
    }


def match_resume_to_jd(resume_data: dict, job_description: str) -> dict:
    """
    Must return: {"match_score": float (0-100), "matched_skills": [str],
                  "missing_skills": [str], "fit_summary": str,
                  "matched_by": "llm_semantic" | "keyword_overlap"}
    Consumed by: interview question selection / Candidate Reports page.
    """
    if llm_client.llm_available():
        try:
            result = _llm_match(resume_data, job_description)
            logger.info(
                "match_resume_to_jd: LLM semantic path (score=%.1f)",
                result["match_score"],
            )
            return result
        except Exception as exc:
            logger.warning(
                "match_resume_to_jd: LLM semantic matching failed (%s: %s) — "
                "falling back to keyword-overlap heuristic",
                type(exc).__name__, exc,
            )

    result = _heuristic_match(resume_data, job_description)
    logger.info(
        "match_resume_to_jd: keyword-overlap path (score=%.1f)",
        result["match_score"],
    )
    return result
