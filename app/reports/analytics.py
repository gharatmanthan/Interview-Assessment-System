"""
Owner: Member C
Touches: this file, app/ui/pages/dashboard_page.py, app/ui/pages/reports_page.py,
app/ui/pages/bias_audit_page.py, app/ui/pages/integrity_log_page.py

Pulls real numbers from app/core/db.py for the Dashboard's stat cards and
the three detail pages.
"""
from app.core import db


def _scope_sessions(username: str | None = None) -> list:
    return db.get_owned_sessions(username) if username else db.get_all_sessions()


def _scope_candidates(username: str | None = None) -> list:
    return db.get_owned_candidates(username) if username else db.get_all_candidates()


def get_dashboard_stats(username: str | None = None) -> dict:
    """
    Returns:
    {
        "interviews_conducted": int,
        "avg_explainability_score": float,   # avg competency score, 0-100
        "bias_flags_raised": int,
        "integrity_flags": int,
        "candidates_by_status": dict,        # {"invited": n, "in_progress": n, "completed": n}
    }
    Consumed by: app/ui/pages/dashboard_page.py
    When `username` is given, all numbers are scoped to that recruiter's jobs.
    """
    sessions = _scope_sessions(username)
    owned_session_ids = {s["session_id"] for s in sessions}

    all_scores = []
    for s in sessions:
        all_scores.extend(db.get_session_scores(s["session_id"]))
    avg_score = (
        sum(sc["score"] for sc in all_scores) / len(all_scores)
        if all_scores else 0.0
    )

    fairness_flags = [
        f for f in db.get_all_fairness_flags()
        if not username or f.get("session_id") in owned_session_ids
    ]
    integrity_flags = [
        f for f in db.get_all_integrity_flags()
        if not username or f.get("session_id") in owned_session_ids
    ]

    candidates = _scope_candidates(username)
    by_status = {"invited": 0, "in_progress": 0, "completed": 0, "expired": 0}
    for c in candidates:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1

    return {
        "interviews_conducted": len(sessions),
        "avg_explainability_score": avg_score,
        "bias_flags_raised": len(fairness_flags),
        "integrity_flags": len(integrity_flags),
        "candidates_by_status": by_status,
    }


def get_candidate_report(session_id: str) -> dict:
    """Full detail for one candidate's Candidate Report page.
    Returns:
    {
        "session": dict,
        "scores": list[dict],        # from competency_scores
        "explanations": list[dict],  # from explanations
        "overall_score": float,
    }
    """
    sessions = {s["session_id"]: s for s in db.get_all_sessions()}
    session = sessions.get(session_id, {})
    scores = db.get_session_scores(session_id)
    explanations = db.get_session_explanations(session_id)
    overall = sum(s["score"] for s in scores) / len(scores) if scores else 0.0

    return {
        "session": session,
        "scores": scores,
        "explanations": explanations,
        "overall_score": overall,
    }


def get_candidate_comparison(job_id: str = None, username: str | None = None) -> list:
    """Ranked list of candidates by overall score, optionally filtered to
    one job posting. Powers the Reports page's 'Compare Candidates' view.
    Returns list of dicts, sorted by overall_score descending:
    [{"session_id", "candidate_name", "job_title", "overall_score",
      "category_scores": {category: score}}, ...]
    When `username` is given, only that recruiter's sessions are used.
    """
    sessions = _scope_sessions(username)
    if job_id:
        jobs = {j["job_id"]: j for j in db.get_all_job_postings()}
        job_title = jobs.get(job_id, {}).get("title")
        sessions = [s for s in sessions if s.get("job_title") == job_title]

    rows = []
    for s in sessions:
        scores = db.get_session_scores(s["session_id"])
        overall = sum(sc["score"] for sc in scores) / len(scores) if scores else 0.0
        category_scores = {sc["category"]: sc["score"] for sc in scores}
        rows.append({
            "session_id": s["session_id"],
            "candidate_name": s.get("candidate_name", "Unknown"),
            "job_title": s.get("job_title", "—"),
            "overall_score": overall,
            "category_scores": category_scores,
        })

    rows.sort(key=lambda r: r["overall_score"], reverse=True)
    return rows


def export_candidates_csv(output_path: str, job_id: str = None, username: str | None = None) -> str:
    """Writes a CSV of all candidates (ranked) to output_path. Returns the path.
    Includes both interview-scored candidates and invited-but-not-yet-scored
    candidates from the candidates table, so recruiters get one full picture.
    """
    import csv

    comparison = get_candidate_comparison(job_id, username)
    all_categories = sorted({cat for row in comparison for cat in row["category_scores"]})

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Candidate", "Job Title", "Overall Score"] + all_categories)
        for row in comparison:
            writer.writerow([
                row["candidate_name"], row["job_title"], f"{row['overall_score']:.1f}",
                *[f"{row['category_scores'].get(cat, ''):.1f}" if cat in row["category_scores"] else ""
                  for cat in all_categories],
            ])

    return output_path
