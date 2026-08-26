# Real Dataset for Trained Scorer — Design Spec

> **Goal:** Replace the 8-example placeholder dataset in `trained_scorer.py` with a defensible, 120+ example synthetic dataset, validated against human judgment, producing real LOO-CV metrics.

**Architecture:** Three new scripts (generate, validate, retrain) + expanded question bank + documentation updates. The pipeline: generate tiered synthetic answers via LLM → sanity check → human-validation subset → apply corrections → retrain → report real metrics.

**Tech Stack:** Python, scikit-learn, existing `llm_client.py` (Groq API), TF-IDF for near-duplicate detection, scipy for correlation.

---

## Task 1: Expand Question Bank

**File:** `app/core/question_bank.py`

Expand from 5 unstructured questions to ~30 questions with category metadata:

- Categories: DSA, System Design, Behavioral, Communication, Technical Knowledge, Problem Solving
- ~5 questions per category
- Data structure: `QUESTION_BANK: list[dict]` where each dict has `{"question": str, "category": str}`
- Backward-compatibility: `DEFAULT_QUESTIONS: list[str]` derived from the bank (existing callers unchanged)
- Existing `DEFAULT_QUESTIONS` entries preserved in their appropriate categories

## Task 2: Generate Training Dataset

**File:** `scripts/generate_training_dataset.py`

### Inputs
- Question bank from `app/core/question_bank.py`
- LLM via `app/engine/llm_client.py` (Groq, llama-3.1-8b-instant)

### Generation process
For each question × tier combination:
1. Build a tier-specific system prompt instructing the LLM to *simulate* a candidate answer at that skill level (not to grade an answer)
2. User prompt includes the question, category, tier name, and concrete tier description
3. Call `ask_llm()` and capture the raw answer text
4. Assign target score with jitter within tier range:
   - Excellent: 85–98
   - Good: 65–84
   - Mediocre: 35–64
   - Poor: 5–34

### Error handling
- Retry up to 3 times per question-tier pair with 2s backoff
- Save progress after each batch of 10 to `data/datasets/synthetic_graded_answers.json`
- On rerun, skip already-generated entries (idempotent)
- Log failures to `data/datasets/generation_failures.log`

### Output
`data/datasets/synthetic_graded_answers.json` — list of:
```json
{
  "question": str,
  "category": str,
  "tier": str,
  "transcript": str,
  "target_score": float,
  "id": str (uuid4)
}
```

Target: ≥100 examples (30 questions × 4 tiers = 120 if all succeed).

## Task 3: Sanity Check + Human Validation

**File:** `scripts/validate_dataset.py`

### Phase A: Automated Sanity Checks (runs on load)

1. **Near-duplicate detection:** TF-IDF vectorize all transcripts, compute pairwise cosine similarity. Flag any pair >0.95 as near-duplicate. Report flagged pairs for review.
2. **Length validation:** Flag answers <10 words or >500 words as generation glitches. Offer to regenerate flagged entries.
3. **Tier separation check:** Compute average `word_count` and `filler_word_rate` per tier. Verify monotonic trend (Excellent has more words, fewer fillers than Poor). Report if violated.

### Phase B: Human Validation Subset

1. **Sampling:** Stratified random sample of 25 examples (~21% of dataset), balanced across tiers (6-7 per tier) and categories
2. **Export blind:** Write `data/datasets/human_validation_subset.csv` with columns `id, question, category, transcript` (NO tier/score — blind to LLM labels)
3. **Print instructions:** Clear rubric + scoring guide for team members
4. **Ingest scores:** On rerun with `--apply-scores` flag:
   - Read `data/datasets/human_scores.csv` (team fills `human_score` column)
   - Compute Pearson's r between human-averaged scores and LLM target scores
   - Report correlation with interpretation guide
   - For divergences >20 points: replace `target_score` with human-averaged score
   - Save corrected dataset back to `synthetic_graded_answers.json`

### Output
- Updated `synthetic_graded_answers.json` (with human corrections applied)
- `data/datasets/human_validation_report.json` containing:
  - `correlation_pearson_r`, `correlation_p_value`
  - `n_human_scored`, `n_corrected`
  - Per-example divergence table

## Task 4: Retrain on Real Dataset

**File:** `scripts/train_trained_scorer.py` (modify existing)

### Changes
- Remove `PLACEHOLDER_DATASET` and all placeholder-related constants/comments
- Remove the "PLACEHOLDER DATASET WARNING" docstring
- Add `load_dataset()` function that reads `data/datasets/synthetic_graded_answers.json` and returns `[(transcript, score), ...]` for `train_from_dataset()`
- Add dataset statistics printout (n_examples, category distribution, tier distribution)
- Same training logic: `train_from_dataset()` → LOO-CV metrics → save to `data/models/`
- Sanity-check predictions: verify score ordering Excellent > Good > Mediocre > Poor using representative transcripts

### Output
- Updated `data/models/trained_scorer_metrics.json` with real metrics
- Updated `data/models/trained_scorer.joblib` with retrained model

## Task 5: Update Documentation

### README.md
- Replace "still on a placeholder dataset" language in the Trained ML Scorer section
- Add dataset description: size, generation method, validation approach
- Update the "Replace placeholder" item in the Roadmap to completed

### Training script docstring
- Replace PLACEHOLDER warning with accurate methodology description
- Explain synthetic-generation + human-validation-subset approach
- Note this is a defensible methodology for a student project when described accurately

---

## Acceptance Criteria

1. `data/datasets/synthetic_graded_answers.json` exists with ≥100 examples across ≥4 categories and all 4 tiers
2. Sanity checks pass: no near-duplicate answers, tier separation holds
3. Human-validation correlation is computed and reported (whatever the number)
4. `train_from_dataset()` runs on real dataset, produces LOO metrics saved to `data/models/trained_scorer_metrics.json`
5. Metrics are meaningfully different from placeholder (n=8 → n=100+, likely lower/realistic Pearson's r)
6. README and training script contain accurate methodology description, no placeholder warnings
