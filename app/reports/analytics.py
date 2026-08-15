"""
Owner: Member C
Touches: this file, app/ui/pages/dashboard_page.py, app/ui/pages/placeholder_page.py
(replacing the "reports"/"bias_audit"/"integrity" placeholders with real pages)

TODO: pull real numbers from app/core/db.py to replace the Dashboard
page's static "0" stat cards.
"""
from app.core import db


def get_dashboard_stats() -> dict:
    """Must return:
    {
        "interviews_conducted": int,
        "avg_explainability_score": float,
        "bias_flags_raised": int,
        "integrity_flags": int,
    }
    Consumed by: app/ui/pages/dashboard_page.py
    """
    sessions = db.get_all_sessions()
    # TODO: aggregate real scores/flags once Member A/B start writing data
    return {
        "interviews_conducted": len(sessions),
        "avg_explainability_score": 0.0,
        "bias_flags_raised": 0,
        "integrity_flags": 0,
    }
