"""
Owner: Member B
OBJECTIVE 2 deliverable: JD matching

Compares parsed resume data (from resume_parser.py) against a job
description to compute a fit score and surface matched/missing skills.
"""
import json

from app.engine import llm_client
from app.engine.resume_parser import COMMON_SKILLS


def _extract_jd_skills(job_description: str) -> set:
    lower = job_description.lower()
    return {s for s in COMMON_SKILLS if s in lower}


def _heuristic_match(resume_data: dict, job_description: str) -> dict:
    resume_skills = {s.lower() for s in resume_data.get("skills", [])}
    jd_skills = _extract_jd_skills(job_description)

    if not jd_skills:
        return {"match_score": 0.0, "matched_skills": [], "missing_skills": []}

    matched = sorted(resume_skills & jd_skills)
    missing = sorted(jd_skills - resume_skills)
    match_score = round(len(matched) / len(jd_skills) * 100, 1)

    return {"match_score": match_score, "matched_skills": matched, "missing_skills": missing}


def match_resume_to_jd(resume_data: dict, job_description: str) -> dict:
    """
    Must return: {"match_score": float (0-100), "matched_skills": [str], "missing_skills": [str]}
    Consumed by: interview question selection / Candidate Reports page.
    """
    if llm_client.llm_available():
        try:
            system = (
                "Compare this candidate's resume skills against the job description. "
                'Respond ONLY as JSON: {"match_score": <0-100 float>, '
                '"matched_skills": [str, ...], "missing_skills": [str, ...]}'
            )
            user = (
                f"Resume skills: {resume_data.get('skills', [])}\n"
                f"Resume experience (years): {resume_data.get('experience_years')}\n\n"
                f"Job description:\n{job_description}"
            )
            raw = llm_client.ask_llm(system, user, json_mode=True)
            data = json.loads(raw)
            return {
                "match_score": float(data["match_score"]),
                "matched_skills": data.get("matched_skills", []),
                "missing_skills": data.get("missing_skills", []),
            }
        except Exception:
            pass

    return _heuristic_match(resume_data, job_description)