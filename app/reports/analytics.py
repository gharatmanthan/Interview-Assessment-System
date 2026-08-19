"""
Owner: Member C
Touches: this file, app/ui/pages/dashboard_page.py, app/ui/pages/reports_page.py,
app/ui/pages/bias_audit_page.py, app/ui/pages/integrity_log_page.py

Pulls real numbers from app/core/db.py for the Dashboard's stat cards and
the three detail pages.
"""
from app.core import db


def get_dashboard_stats() -> dict:
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
    """
    sessions = db.get_all_sessions()

    all_scores = []
    for s in sessions:
        all_scores.extend(db.get_session_scores(s["session_id"]))
    avg_score = (
        sum(sc["score"] for sc in all_scores) / len(all_scores)
        if all_scores else 0.0
    )

    fairness_flags = db.get_all_fairness_flags()
    integrity_flags = db.get_all_integrity_flags()

    candidates = db.get_all_candidates()
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
