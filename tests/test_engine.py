import json

import pytest

from app.engine import jd_matcher, llm_client, rag, resume_parser
from app.engine.explainability import explain_score
from app.engine.fairness import FLAG_THRESHOLD, _counterfactual_transcript, audit_bias
from app.engine.scoring import _heuristic_score, score_answer


class FakeLLM:
    def __init__(self, monkeypatch):
        self.calls = []
        self._monkeypatch = monkeypatch
        self.install({"score": 50})

    def install(self, response):
        calls = self.calls

        def fake_ask(system_prompt, user_prompt, json_mode=False):
            calls.append({"system": system_prompt, "user": user_prompt})
            return json.dumps(response)

        self._monkeypatch.setattr(llm_client, "llm_available", lambda: True)
        self._monkeypatch.setattr(llm_client, "ask_llm", fake_ask)


@pytest.fixture
def fake_llm(monkeypatch):
    return FakeLLM(monkeypatch)


class TestRetrieveRubric:
    def test_known_category_returns_bank_entry(self):
        rubric = rag.retrieve_rubric("Backend Engineer", "dsa")
        assert "time complexity" in rubric["criteria"]
        assert rubric["weight"] == 1.3

    def test_category_matching_ignores_case_whitespace_and_underscores(self):
        static = dict(rag.RUBRIC_BANK["system design"])
        assert rag.retrieve_rubric("", " System Design ") == {**static, "retrieval_used": False}
        assert rag.retrieve_rubric("", "system_design") == {**static, "retrieval_used": False}

    def test_unknown_category_falls_back_to_default(self):
        rubric = rag.retrieve_rubric("Any Title", "quantum computing")
        assert rubric == {**rag.DEFAULT_RUBRIC, "retrieval_used": False}


class TestHeuristicScore:
    def test_empty_transcript_scores_zero_with_low_confidence(self):
        score, confidence = _heuristic_score("", {"criteria": ["depth"]})
        assert score == 0.0
        assert confidence == 0.15

    def test_on_topic_answer_outscores_off_topic_answer(self):
        rubric = {"criteria": ["time complexity", "edge cases", "optimal approach"]}
        on_topic = (
            "I would start with a brute force solution, then discuss time complexity "
            "trade-offs and handle edge cases before reaching the optimal approach."
        )
        off_topic = "I really enjoy hiking and cooking on weekends with my family."
        assert _heuristic_score(on_topic, rubric)[0] > _heuristic_score(off_topic, rubric)[0]

    def test_filler_words_reduce_score(self):
        rubric = {"criteria": []}
        clean = "The solution uses a hash map for lookups."
        filler_heavy = "um basically like the you know solution uses a hash map"
        assert _heuristic_score(clean, rubric)[0] > _heuristic_score(filler_heavy, rubric)[0]

    def test_score_stays_within_bounds_for_huge_transcript(self):
        words = " ".join(["um"] * 500)
        score, _ = _heuristic_score(words, {"criteria": []})
        assert 0.0 <= score <= 100.0


class TestScoreAnswer:
    def test_heuristic_path_when_no_llm(self):
        result = score_answer("s1", "q1", "DSA", "discussing time complexity", {"criteria": []})

        assert result.session_id == "s1"
        assert result.question_id == "q1"
        assert result.category == "DSA"
        assert 0.0 <= result.score <= 100.0
        assert result.confidence == 0.35

    def test_llm_path_returns_parsed_values(self, fake_llm):
        fake_llm.install({"score": 88.44, "confidence": 0.912})
        result = score_answer("s1", "q1", "DSA", "good answer", {"criteria": ["depth"]})

        assert result.score == 88.4
        assert result.confidence == 0.91
        assert result.session_id == "s1"
        assert result.question_id == "q1"
        assert result.category == "DSA"

    def test_llm_failure_falls_back_to_heuristic(self, monkeypatch):
        monkeypatch.setattr(llm_client, "llm_available", lambda: True)

        def boom(*args, **kwargs):
            raise RuntimeError("api down")

        monkeypatch.setattr(llm_client, "ask_llm", boom)
        result = score_answer("s1", "q1", "DSA", "", {"criteria": []})

        assert result.score == 0.0
        assert result.confidence == 0.15


class TestExplainScore:
    def test_heuristic_explanation_flags_no_llm_configured(self):
        item = explain_score("s1", "q1", "short answer text", 42.0)
        assert "No LLM key is configured" in item.summary
        assert item.supporting_phrases == ["short", "answer", "text"]

    def test_supporting_phrases_capped_at_twelve_words(self):
        transcript = " ".join(f"word{i}" for i in range(30))
        item = explain_score("s1", "q1", transcript, 10.0)
        assert len(item.supporting_phrases) == 12

    def test_length_note_changes_for_detailed_answers(self):
        brief = explain_score("s1", "q1", "one two three", 10.0)
        detailed = explain_score("s1", "q1", " ".join(["deep"] * 61), 10.0)
        assert "a brief" in brief.summary
        assert "a detailed" in detailed.summary

    def test_llm_path_returns_summary_and_phrases(self, fake_llm):
        fake_llm.install({"summary": "Strong answer.", "supporting_phrases": ["recursion"]})
        item = explain_score("s1", "q1", "used recursion well", 90.0)

        assert item.summary == "Strong answer."
        assert item.supporting_phrases == ["recursion"]
        assert "90.0/100" in fake_llm.calls[0]["user"]


class TestCounterfactualTranscript:
    def test_swaps_pronouns_in_both_directions(self):
        swapped = _counterfactual_transcript("He said his approach impressed her and him.")
        assert swapped == "she said her approach impressed his and her."

    def test_leaves_text_without_gendered_language_unchanged(self):
        text = "The candidate described a distributed cache."
        assert _counterfactual_transcript(text) == text


class TestAuditBias:
    def test_no_gendered_language_returns_zero_delta(self):
        flag = audit_bias("s1", "q1", "A neutral technical answer.", 60.0)
        assert flag.score_delta == 0.0
        assert "No gendered language" in flag.note

    def test_large_shift_is_flagged(self, fake_llm):
        fake_llm.install({"score": 80})
        flag = audit_bias("s1", "q1", "He solved it quickly.", 50.0)

        assert flag.score_delta == 30.0
        assert "Flagged" in flag.note

    def test_small_shift_is_not_flagged(self, fake_llm):
        fake_llm.install({"score": 52})
        flag = audit_bias("s1", "q1", "She solved it quickly.", 50.0)

        assert flag.score_delta == 2.0
        assert "Within normal variance." in flag.note

    def test_threshold_boundary_is_flagged(self, fake_llm):
        fake_llm.install({"score": 55})
        flag = audit_bias("s1", "q1", "He solved it quickly.", 50.0)
        assert abs(flag.score_delta) >= FLAG_THRESHOLD


class TestJdMatcher:
    def test_extract_jd_skills_finds_known_skills_only(self):
        skills = jd_matcher._extract_jd_skills("Must know Python and kubernetes; welding a plus")
        assert skills == {"python", "kubernetes"}

    def test_heuristic_match_computes_matched_missing_and_score(self):
        resume = {"skills": ["Python", "SQL", "React"]}
        jd = "Looking for python and sql engineers."

        result = jd_matcher.match_resume_to_jd(resume, jd)

        assert result["matched_skills"] == ["python", "sql"]
        assert result["missing_skills"] == []
        assert result["match_score"] == 100.0

    def test_match_against_jd_with_no_known_skills_scores_zero(self):
        result = jd_matcher.match_resume_to_jd({"skills": ["Python"]}, "Weld pipes all day.")
        assert result["match_score"] == 0.0
        assert result["matched_skills"] == []
        assert result["missing_skills"] == []
        assert result["matched_by"] == "keyword_overlap"

    def test_partial_overlap_reports_missing_skills(self):
        resume = {"skills": ["Python"]}
        jd = "Needs python, docker and kubernetes."

        result = jd_matcher.match_resume_to_jd(resume, jd)

        assert result["matched_skills"] == ["python"]
        assert result["missing_skills"] == ["docker", "kubernetes"]
        assert result["match_score"] == round(1 / 3 * 100, 1)

    def test_match_score_is_0_to_100_not_0_to_1(self):
        """match_score must be a plain percentage (0-100), never a 0-1 fraction.
        Regression: frontend was doing score * 100 on a 0-100 value, causing
        33.3% to display as 3330%."""
        resume = {"skills": ["Python", "SQL", "AWS"]}
        jd = "Needs python, sql, aws, docker, kubernetes, terraform, react, go, rust"
        result = jd_matcher.match_resume_to_jd(resume, jd)
        assert 0 < result["match_score"] < 100
        # 3 matched (python, sql, aws) out of 6 recognized JD skills = 50.0
        assert result["match_score"] == 50.0

    def test_match_score_clamped_to_100(self):
        """Even if a future code change produces > 100, the score must clamp."""
        resume = {"skills": ["python", "sql", "docker", "kubernetes"]}
        jd = "Needs python and sql."
        result = jd_matcher.match_resume_to_jd(resume, jd)
        assert result["match_score"] <= 100.0


class TestResumeParser:
    def test_heuristic_parse_extracts_skills_experience_education(self):
        raw = (
            "JANE DOE\nSkills: Python, SQL, Docker\n"
            "5+ years of experience\nB.Tech in Computer Science\n"
        )

        parsed = resume_parser._heuristic_parse(raw)

        assert set(parsed["skills"]) == {"python", "sql", "docker"}
        assert parsed["experience_years"] == 5.0
        assert any("B.Tech" in line for line in parsed["education"])

    def test_experience_regex_handles_of_and_plain_forms(self):
        assert resume_parser._heuristic_parse("3 years of experience")["experience_years"] == 3.0
        assert resume_parser._heuristic_parse("7 years experience")["experience_years"] == 7.0
        assert resume_parser._heuristic_parse("no numbers here")["experience_years"] is None

    def test_parse_resume_txt_file_end_to_end(self, tmp_path):
        resume_file = tmp_path / "resume.txt"
        resume_file.write_text(
            "Alex Kim\nSkills: Python, FastAPI\n2 years of experience\n",
            encoding="utf-8",
        )

        parsed = resume_parser.parse_resume(str(resume_file))

        assert "python" in parsed["skills"]
        assert "fastapi" in parsed["skills"]
        assert parsed["experience_years"] == 2.0
        assert parsed["raw_text"].startswith("Alex Kim")

    def test_llm_failure_falls_back_to_heuristic(self, tmp_path, monkeypatch):
        monkeypatch.setattr(llm_client, "llm_available", lambda: True)

        def boom(*args, **kwargs):
            raise RuntimeError("api down")

        monkeypatch.setattr(llm_client, "ask_llm", boom)
        resume_file = tmp_path / "resume.txt"
        resume_file.write_text("Skills: Python\n4 years of experience\n", encoding="utf-8")

        parsed = resume_parser.parse_resume(str(resume_file))
        assert parsed["skills"] == ["python"]
        assert parsed["experience_years"] == 4.0
