"""
Hard-requirement evaluation + deterministic decision engine.

Hard requirements are gating and evaluated SEPARATELY from the soft ATS
score: failing any hard requirement rejects the application regardless of
ATS score. Only when all hard requirements pass does the weighted ATS
score decide (passed / manual_review / rejected).
"""
from typing import Optional


def _years_field(resume_data: dict) -> Optional[float]:
    try:
        years = float(resume_data.get("experience_years"))
    except (TypeError, ValueError):
        return None
    return years


def eval_hard_requirements(resume_data: dict, job: dict) -> dict:
    """Run the configured hard gates. Returns
    {"passed": bool, "failures": [str], "checks": {name: {passed, detail}}}.
    """
    failures = []
    checks = {}

    min_years = job.get("minimum_experience_years")
    if min_years is not None:
        years = _years_field(resume_data)
        if years is None:
            failures.append(f"minimum experience ({min_years} yrs) not verifiable from resume")
            checks["experience"] = {"passed": False, "detail": "resume did not state total experience in years"}
        elif years < float(min_years):
            failures.append(f"minimum experience not met: {years} yrs < required {min_years} yrs")
            checks["experience"] = {"passed": False, "detail": f"{years} < {min_years}"}
        else:
            checks["experience"] = {"passed": True, "detail": f"{years} >= {min_years}"}

    required_ed = (job.get("required_education") or "").strip()
    if required_ed:
        resume_education = [str(line).lower() for line in (resume_data.get("education") or [])]
        if not resume_education:
            failures.append(f"required education ('{required_ed}') not verifiable — no education on resume")
            checks["education"] = {"passed": False, "detail": "no education listed"}
        elif any(required_ed.lower() in line for line in resume_education):
            checks["education"] = {"passed": True, "detail": f"{required_ed} found"}
        else:
            failures.append(f"required education ('{required_ed}') not found on resume")
            checks["education"] = {"passed": False, "detail": f"no match for {required_ed}"}

    return {"passed": not failures, "failures": failures, "checks": checks}


def decide(ats_score: Optional[float], hard_passed: bool, threshold: float,
           manual_review_floor: float = 10.0) -> tuple:
    """Deterministic decision.

    Priority: hard requirements gate -> ATS threshold. Returns
    (decision, reason) where decision is passed | manual_review | rejected.
    """
    if not hard_passed:
        return ("rejected", "failed hard requirements")

    if ats_score is None:
        # Not enough criteria to score: surface rather than reject silently.
        return ("manual_review", "insufficient data to score")

    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        threshold = 60.0

    if ats_score >= threshold:
        return ("passed", f"ATS score ({ats_score:.1f}) >= threshold ({threshold:.1f})")
    if ats_score >= threshold - manual_review_floor and manual_review_floor > 0:
        return ("manual_review",
                f"ATS score ({ats_score:.1f}) is near threshold {threshold:.1f} — recruiter review")
    return ("rejected", f"ATS score ({ats_score:.1f}) below threshold ({threshold:.1f})")