# Module Ownership

Read this once, together, before anyone writes code. It's the whole point.

| Person | Folder(s) | Objective(s) covered | Never touches |
|---|---|---|---|
| **Member A** | `app/candidate/` (`capture.py`, `integrity.py`) + `app/ui/pages/interview_page.py` | Obj 1 (multimodal capture), Obj 3 (integrity monitoring) | `app/engine/`, `app/reports/` |
| **Member B** | `app/engine/` (`stt.py`, `rag.py`, `scoring.py`, `explainability.py`, `fairness.py`) | Obj 2 (competency evaluation), Obj 4 (explainability & fairness) | `app/ui/`, `app/candidate/`, `app/reports/` |
| **Member C** | `app/reports/` (`analytics.py`, `pdf_export.py`) + `app/ui/pages/dashboard_page.py` + new report/bias/integrity-log pages | Obj 5 (recruiter dashboard) | `app/candidate/`, `app/engine/` |

**Shared ground (everyone reads/writes, nobody "owns"):**
- `app/core/models.py` — the data shapes. Changing a field here is a group-chat message first, not a silent edit.
- `app/core/db.py` — the DB layer. Add a new `save_x()`/`get_x()` function if you need one; don't edit someone else's existing function.
- `app/ui/main_window.py`, `app/ui/sidebar.py` — the app shell. Stable after initial setup, rarely needs touching.
- `app/utils/theme.py` — shared styling. Ask before changing colors everyone relies on.

**The rule that prevents merge conflicts:** if you find yourself editing a file inside someone else's folder, stop — that means the data contract in `app/core/models.py` is missing something you need. Add the field there (with a heads-up to the team) instead of reaching into their code.
