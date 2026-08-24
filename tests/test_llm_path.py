"""
CI-safe tests for the hardened LLM call path — no live API key needed.

Covers (Task 1 acceptance):
  - well-formed JSON responses parse
  - JSON wrapped in markdown fences parses
  - JSON with preamble text parses
  - malformed / non-JSON responses -> heuristic fallback, logged
  - simulated timeout -> one retry then fallback, logged
  - 4xx errors are NOT retried; 5xx are retried once
  - no key present -> straight to heuristic, LLM never called
"""
import json

import pytest
import requests

from app.engine import llm_client
from app.engine.explainability import explain_score
from app.engine.fairness import audit_bias
from app.engine.scoring import score_answer


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {
            "choices": [{"message": {"content": json.dumps({"score": 77.0})}}]
        }

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def no_real_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


def _post_succeeding_with(raw_content):
    def fake_post(url, headers=None, json=None, timeout=None):
        assert timeout == llm_client.LLM_REQUEST_TIMEOUT
        return FakeResponse(payload={"choices": [{"message": {"content": raw_content}}]})

    return fake_post


class TestLlmAvailable:
    def test_no_key(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        assert llm_client.llm_available() is False

    def test_key_present(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
        assert llm_client.llm_available() is True


class TestAskLlmRetries:
    def _with_key(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
        calls = []
        return calls

    def test_timeout_retries_once_then_succeeds(self, monkeypatch):
        calls = self._with_key(monkeypatch)
        attempts = []

        def flaky_post(url, headers=None, json=None, timeout=None):
            attempts.append(1)
            if len(attempts) == 1:
                raise requests.Timeout("timed out")
            return FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]})

        monkeypatch.setattr(llm_client.requests, "post", flaky_post)
        assert llm_client.ask_llm("sys", "user") == "ok"
        assert len(attempts) == 2

    def test_timeout_twice_raises(self, monkeypatch):
        self._with_key(monkeypatch)
        attempts = []

        def dead_post(url, headers=None, json=None, timeout=None):
            attempts.append(1)
            raise requests.Timeout("timed out")

        monkeypatch.setattr(llm_client.requests, "post", dead_post)
        with pytest.raises(RuntimeError, match="failed after"):
            llm_client.ask_llm("sys", "user")
        assert len(attempts) == 2  # first try + exactly one retry

    def test_server_error_retried_then_succeeds(self, monkeypatch):
        self._with_key(monkeypatch)
        payloads = [
            FakeResponse(status_code=500),
            FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]}),
        ]

        def post(url, headers=None, json=None, timeout=None):
            return payloads.pop(0)

        monkeypatch.setattr(llm_client.requests, "post", post)
        assert llm_client.ask_llm("sys", "user") == "ok"

    def test_client_error_not_retried(self, monkeypatch):
        self._with_key(monkeypatch)
        attempts = []

        def unauthorized_post(url, headers=None, json=None, timeout=None):
            attempts.append(1)
            return FakeResponse(status_code=401)

        monkeypatch.setattr(llm_client.requests, "post", unauthorized_post)
        with pytest.raises(requests.HTTPError):
            llm_client.ask_llm("sys", "user")
        assert len(attempts) == 1  # 4xx must fail fast

    def test_no_key_raises_immediately_without_http_call(self, monkeypatch):
        def unexpected_post(*args, **kwargs):
            raise AssertionError("HTTP call attempted without an API key")

        monkeypatch.setattr(llm_client.requests, "post", unexpected_post)
        with pytest.raises(RuntimeError, match="No GROQ_API_KEY"):
            llm_client.ask_llm("sys", "user")

    def test_successful_calls_recorded_in_call_log(self, monkeypatch):
        self._with_key(monkeypatch)
        monkeypatch.setattr(
            llm_client.requests, "post",
            _post_succeeding_with('{"score": 50}'),
        )
        before = len(llm_client.call_log)
        llm_client.ask_llm("sys", "user")
        assert len(llm_client.call_log) == before + 1
        entry = llm_client.call_log[-1]
        assert entry["ok"] is True and "latency_ms" in entry


class TestParseLlmJson:
    def test_plain_json(self):
        assert llm_client.parse_llm_json('{"score": 90}') == {"score": 90}

    def test_markdown_fenced_json(self):
        raw = '```json\n{"score": 90, "reasoning": "solid"}\n```'
        assert llm_client.parse_llm_json(raw) == {"score": 90, "reasoning": "solid"}

    def test_fenced_without_language_tag(self):
        raw = '```\n{"a": 1}\n```'
        assert llm_client.parse_llm_json(raw) == {"a": 1}

    def test_preamble_text_before_json(self):
        raw = 'Here is your evaluation:\n{"score": 65}\nHope this helps!'
        assert llm_client.parse_llm_json(raw) == {"score": 65}

    def test_malformed_response_raises_valueerror(self):
        with pytest.raises(ValueError, match="not parseable"):
            llm_client.parse_llm_json("I think the answer deserves a good score.")

    def test_empty_response_raises_valueerror(self):
        with pytest.raises(ValueError):
            llm_client.parse_llm_json("")


class TestScoreAnswerFallbacks:
    RUBRIC = {"criteria": ["depth"]}

    def test_fenced_json_response_scores_via_llm_path(self, monkeypatch, caplog):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
        monkeypatch.setattr(
            llm_client.requests, "post",
            _post_succeeding_with('Here you go:\n```json\n{"score": 91.2, "confidence": 0.88}\n```'),
        )
        with caplog.at_level("INFO", logger="app.engine.scoring"):
            result = score_answer("s1", "q1", "DSA", "answer", self.RUBRIC)
        assert result.score == 91.2
        assert result.confidence == 0.88
        assert "LLM path" in caplog.text

    def test_out_of_range_score_is_clamped(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
        monkeypatch.setattr(
            llm_client.requests, "post",
            _post_succeeding_with('{"score": 250, "confidence": 5}'),
        )
        result = score_answer("s1", "q1", "DSA", "answer", self.RUBRIC)
        assert result.score == 100.0
        assert result.confidence == 1.0

    def test_non_numeric_score_falls_back_and_logs(self, monkeypatch, caplog):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
        monkeypatch.setattr(
            llm_client.requests, "post",
            _post_succeeding_with('{"score": "excellent"}'),
        )
        with caplog.at_level("WARNING", logger="app.engine.scoring"):
            result = score_answer("s1", "q1", "DSA", "", self.RUBRIC)
        assert result.score >= 0.0
        assert "falling back to heuristic" in caplog.text

    def test_malformed_text_falls_back_and_logs(self, monkeypatch, caplog):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
        monkeypatch.setattr(
            llm_client.requests, "post",
            _post_succeeding_with("The candidate did fine overall."),
        )
        with caplog.at_level("WARNING", logger="app.engine.scoring"):
            result = score_answer("s1", "q1", "DSA", "", self.RUBRIC)
        assert "falling back to heuristic" in caplog.text

    def test_double_timeout_falls_back_and_logs(self, monkeypatch, caplog):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")

        def dead_post(url, headers=None, json=None, timeout=None):
            raise requests.Timeout("timed out")

        monkeypatch.setattr(llm_client.requests, "post", dead_post)
        with caplog.at_level("WARNING", logger="app.engine.scoring"):
            result = score_answer("s1", "q1", "DSA", "some words here", self.RUBRIC)
        assert result.confidence == 0.35  # heuristic confidence
        assert "falling back to heuristic" in caplog.text

    def test_no_key_goes_straight_to_heuristic(self, monkeypatch, caplog):
        def unexpected_post(*args, **kwargs):
            raise AssertionError("LLM called without a key")

        monkeypatch.setattr(llm_client.requests, "post", unexpected_post)
        with caplog.at_level("INFO", logger="app.engine.scoring"):
            result = score_answer("s1", "q1", "DSA", "discussing time complexity", self.RUBRIC)
        assert result.confidence == 0.35
        assert "heuristic path" in caplog.text


class TestJdMatcherLlmPath:
    def test_semantic_path_parses_and_labels_itself(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
        monkeypatch.setattr(
            llm_client.requests, "post",
            _post_succeeding_with(
                '```json\n{"match_score": 82.5, "matched_skills": ["python", "rest api"], '
                '"missing_skills": ["kubernetes"], '
                '"fit_summary": "Strong backend base; gaps in container orchestration."}\n```'
            ),
        )
        from app.engine import jd_matcher

        result = jd_matcher.match_resume_to_jd(
            {"skills": ["python"], "experience_years": 3},
            "Backend engineer role needing python and kubernetes.",
        )
        assert result["matched_by"] == "llm_semantic"
        assert result["match_score"] == 82.5
        assert "orchestration" in result["fit_summary"]

    def test_malformed_llm_output_falls_back_logged(self, monkeypatch, caplog):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
        monkeypatch.setattr(
            llm_client.requests, "post",
            _post_succeeding_with("The candidate seems like a decent fit overall."),
        )
        from app.engine import jd_matcher

        with caplog.at_level("WARNING", logger="app.engine.jd_matcher"):
            result = jd_matcher.match_resume_to_jd({"skills": ["python"]}, "Needs python.")
        assert result["matched_by"] == "keyword_overlap"
        assert "falling back to keyword-overlap" in caplog.text

    def test_no_key_uses_keyword_overlap(self, monkeypatch, caplog):
        from app.engine import jd_matcher

        with caplog.at_level("INFO", logger="app.engine.jd_matcher"):
            result = jd_matcher.match_resume_to_jd({"skills": ["python"]}, "Needs python and docker.")
        assert result["matched_by"] == "keyword_overlap"
        assert "keyword-overlap path" in caplog.text


class TestExplainAndFairnessFallbackLogging:
    def test_explain_score_malformed_falls_back_logged(self, monkeypatch, caplog):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
        monkeypatch.setattr(
            llm_client.requests, "post",
            _post_succeeding_with("no json here at all"),
        )
        with caplog.at_level("WARNING", logger="app.engine.explainability"):
            item = explain_score("s1", "q1", "short text", 42.0)
        assert "No LLM key is configured" in item.summary or "heuristic estimate" in item.summary
        assert "falling back to heuristic" in caplog.text

    def test_audit_bias_malformed_falls_back_logged(self, monkeypatch, caplog):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_123")
        monkeypatch.setattr(
            llm_client.requests, "post",
            _post_succeeding_with("cannot parse this"),
        )
        with caplog.at_level("WARNING", logger="app.engine.fairness"):
            flag = audit_bias("s1", "q1", "He solved it quickly.", 50.0)
        assert isinstance(flag.score_delta, float)
        assert "falling back to heuristic" in caplog.text
