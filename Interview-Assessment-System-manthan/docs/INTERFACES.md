# Data Contracts Between Modules

This is what actually prevents conflicts — not the folder split by itself.
Everyone builds against these shapes from day one, using fake/dummy data
if their upstream dependency isn't done yet.

## The pipeline, end to end

```
Member A (candidate/)          Member B (engine/)                Member C (reports/)
─────────────────────          ───────────────────                ────────────────────
capture.py
  start_recording()
  stop_recording()
     → {video_path, audio_path}
                          ──►  stt.py
                                 transcribe(audio_path) → str
                                        │
                          ──►  rag.py
                                 retrieve_rubric(job_title, category) → dict
                                        │
                          ──►  scoring.py
                                 score_answer(...) → CompetencyScore
                                        │
                          ──►  explainability.py
                                 explain_score(...) → ExplanationItem
                          ──►  fairness.py
                                 audit_bias(...) → FairnessFlag
                                                                ──►  analytics.py
                                                                       get_dashboard_stats() → dict
integrity.py
  run_checks() → list[IntegrityFlag]
                                                                ──►  pdf_export.py
                                                                       export_report(...) → path
```

## The 5 shapes everything flows through

All defined in `app/core/models.py` — read that file, it's short:

1. **`InterviewSession`** — one interview, start to finish
2. **`IntegrityFlag`** — one suspicious-activity signal (Member A → Member C)
3. **`CompetencyScore`** — one question's score (Member B → Member C)
4. **`ExplanationItem`** — why that score was given (Member B → Member C)
5. **`FairnessFlag`** — one bias signal (Member B → Member C)

## How to build in parallel without waiting

- **Member C can build the whole dashboard today** using fake data:
  ```python
  fake_stats = {"interviews_conducted": 12, "avg_explainability_score": 78.5,
                "bias_flags_raised": 2, "integrity_flags": 1}
  ```
  shaped exactly like what `analytics.get_dashboard_stats()` will eventually return — swap the fake dict for the real function call once Member B's pipeline exists. Zero code changes needed elsewhere.

- **Member B can test scoring against a fake transcript** without waiting for Member A's mic/Whisper pipeline:
  ```python
  fake_transcript = "I would use a hash map to solve this in O(n) time..."
  ```

- **Member A's integrity checks don't depend on anyone** — `port_scan()` in `app/candidate/integrity.py` already works standalone, start there.

## If a shape needs to change

Post in the group chat: *"adding `confidence` field to CompetencyScore, anyone relying on the old shape?"* — then update `app/core/models.py` once. That's the whole process. It's a message, not a merge conflict.
