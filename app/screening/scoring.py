"""
Component-based ATS scoring.

Produces an explainable 0-100 score from five sub-criteria with per-job,
recruiter-configurable weights (defaults: skills 40 / experience 20 /
semantic 20 / education 10 / keyword 10).

Robustness rule (spec): if a sub-criterion is not applicable for a job
(e.g. no experience requirement, or no education requirement), its weight
is redistributed proportionally across the remaining applicable criteria,
so the overall score stays on the same 0-100 scale.

Each component returns (value_or_None, reason). None means "not applicable
for this job" and is excluded from the weighted average.
"""


def _clamp(value, lo=0.0, hi=100.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, value))


def _skill_list(value) -> list:
    if isinstance(value, str):
        try:
            import json
            value = json.loads(value or "[]")
        except json.JSONDecodeError:
            value = []
    return [str(s).strip().lower() for s in (value or []) if str(s).strip()]


def skills_component(resume_data: dict, job: dict, match_result: dict) -> tuple:
    """Coverage of the job's explicitly-required skills present on the resume."""
    required = _skill_list(job.get("required_skills"))
    resume_skills = set(_skill_list(resume_data.get("skills")))
    if required:
        matched = [s for s in required if s in resume_skills]
        value = round(len(matched) / len(required) * 100, 1)
        return value, f"{len(matched)}/{len(required)} required skills found"
    # No explicit required_skills list: fall back to JD-skill coverage from the matcher.
    jd_total = len(match_result.get("matched_skills", [])) + len(match_result.get("missing_skills", []))
    if jd_total:
        value = round(len(match_result.get("matched_skills", [])) / jd_total * 100, 1)
        return value, f"{len(match_result.get('matched_skills', []))}/{jd_total} JD skills found"
    return None, "no skills requirement"


def experience_component(resume_data: dict, job: dict, match_result: dict = None) -> tuple:
    """Years of experience vs. the job's requirement. Absent requirement = N/A."""
    min_years = job.get("minimum_experience_years")
    years = resume_data.get("experience_years")
    if min_years is None:
        return None, "no minimum experience requirement"
    try:
        years = float(years)
    except (TypeError, ValueError):
        return 0.0, "resume did not state experience in years"
    try:
        target = float(min_years)
    except (TypeError, ValueError):
        return None, "invalid job minimum-experience value"
    return round(_clamp(years / target * 100), 1) if target > 0 else 100.0, \
        f"{years} yrs vs required {target} yrs"


def semantic_component(resume_data: dict, job: dict, match_result: dict) -> tuple:
    """Semantic fit from the matcher (LLM or heuristic overall match score)."""
    score = match_result.get("match_score")
    if score is None:
        return None, "no semantic match produced"
    return round(_clamp(score), 1), f"semantic fit via {match_result.get('matched_by')}"


def education_component(resume_data: dict, job: dict, match_result: dict = None) -> tuple:
    """Does the resume show the required education? Absent requirement = N/A."""
    required = (job.get("required_education") or "").strip()
    resume_education = [str(line).lower() for line in (resume_data.get("education") or [])]
    if not required:
        if not resume_education:
            return None, "no education requirement and no education on resume"
        return None, "no education requirement"
    if any(required.lower() in line for line in resume_education):
        return 100.0, f"required education ('{required}') present"
    return 0.0, f"required education ('{required}') not found on resume"


def keyword_component(resume_data: dict, job: dict, match_result: dict) -> tuple:
    """Precision of the surface-level skill overlap (hard keyword evidence)."""
    matched = _skill_list(match_result.get("matched_skills"))
    missing = _skill_list(match_result.get("missing_skills"))
    total = len(matched) + len(missing)
    if not total:
        return None, "no keyword comparison possible"
    return round(len(matched) / total * 100, 1), f"{len(matched)}/{total} JD keywords matched"


COMPONENT_FUNCS = {
    "skills": skills_component,
    "experience": experience_component,
    "semantic": semantic_component,
    "education": education_component,
    "keyword": keyword_component,
}


def component_scores(resume_data: dict, job: dict, match_result: dict) -> dict:
    """Compute every configured component. Returns
    {"components": {name: {value, weight, reason}}, "overall": float|None,
     "weights_used": {name: weight}, "adjustment": str}.
    """
    default_weights = {"skills": 40, "experience": 20, "semantic": 20, "education": 10, "keyword": 10}
    weights = dict(default_weights)
    configured = job.get("screening_weights")
    if isinstance(configured, dict):
        for key in weights:
            try:
                w = float(configured.get(key, weights[key]))
                weights[key] = max(0.0, w)
            except (TypeError, ValueError):
                pass

    components = {}
    for name, func in COMPONENT_FUNCS.items():
        value, reason = func(resume_data, job, match_result)
        components[name] = {
            "value": value,
            "weight": weights.get(name, 0.0),
            "reason": reason,
        }

    applicable = {n: c for n, c in components.items() if c["value"] is not None and c["weight"] > 0}
    total_weight = sum(c["weight"] for c in applicable.values())

    if not applicable or total_weight <= 0:
        return {
            "components": components,
            "overall": None,
            "weights_used": {},
            "adjustment": "every applicable criterion unavailable — score undefined",
        }

    normalization = 100.0 / total_weight
    overall = round(
        sum(c["value"] * (c["weight"] * normalization) / 100.0 for name, c in applicable.items()),
        1,
    )
    n_skipped = len(components) - len(applicable)
    adjustment = (
        f"weight redistributed across {len(applicable)} applicable criteria "
        f"({n_skipped} skipped)" if n_skipped else "all criteria applicable"
    )

    return {
        "components": components,
        "overall": overall,
        "weights_used": {n: round((c["weight"] * normalization) / 100.0, 4) for n, c in applicable.items()},
        "adjustment": adjustment,
    }