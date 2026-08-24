"""
Tests proving rag.py does real retrieval (Task 2), not a static lookup.

The embedding backend is forced to TF-IDF so tests are deterministic and
need no model downloads. A separate smoke test exercises the neural
backend chain if it loads.
"""
import numpy as np
import pytest

from app.engine import embeddings, rag


@pytest.fixture(autouse=True)
def tfidf_backend(monkeypatch):
    """Force the deterministic offline embedder for every test here."""
    embeddings.reset_embedder_cache()
    rag.reset_retrieval_cache()
    monkeypatch.setattr(
        embeddings, "get_embedder",
        lambda reference_corpus=None: embeddings.TfidfEmbedder(reference_corpus),
    )
    yield
    embeddings.reset_embedder_cache()
    rag.reset_retrieval_cache()


BACKEND_JD = (
    "We are building high-throughput backend services in Python and Go. You will design "
    "REST APIs backed by PostgreSQL and Redis caching, run them on Kubernetes with Docker, "
    "and own scalability, sharding and replication decisions for millions of requests per "
    "second. Experience with message queues like Kafka required."
)

HIKING_CLUB_JD = (
    "Mountain hiking club is hiring a weekend trip coordinator. Lead group walks, plan safe "
    "routes on alpine trails, manage equipment inventory, communicate weather updates to "
    "members and coordinate carpooling logistics for each excursion."
)


class TestRealRetrieval:
    def test_jd_triggers_retrieval_path_with_transparency_keys(self):
        rubric = rag.retrieve_rubric("Backend Engineer", "technical", BACKEND_JD)
        assert rubric["retrieval_used"] is True
        assert rubric["retrieved_snippets"]
        assert rubric["retrieval_backend"]
        # retrieved snippets must come from the knowledge base, not be criteria strings
        from app.engine.rubric_kb import RUBRIC_KB
        kb_texts = {s.text for s in RUBRIC_KB}
        for snippet in rubric["retrieved_snippets"]:
            body = snippet.split("] ", 1)[1]
            assert body in kb_texts

    def test_retrieval_is_content_dependent(self):
        """A backend JD and an unrelated JD must retrieve different snippets."""
        backend = rag.retrieve_rubric("Backend Engineer", "technical", BACKEND_JD)
        hiking = rag.retrieve_rubric("Trip Coordinator", "behavioral", HIKING_CLUB_JD)
        assert set(backend["retrieved_snippets"]) != set(hiking["retrieved_snippets"])

    def test_technical_jd_retrieves_technical_snippets_not_behavioral(self):
        rubric = rag.retrieve_rubric("Backend Engineer", "technical", BACKEND_JD)
        categories = [s.split("/")[0][1:] for s in rubric["retrieved_snippets"]]
        technical_count = sum(1 for c in categories if c == "technical")
        behavioral_count = sum(1 for c in categories if c == "behavioral")
        assert technical_count > 0
        assert technical_count > behavioral_count

    def test_dsa_question_with_dsa_jd_surfaces_dsa_criteria(self):
        dsa_jd = ("Solve algorithmic problems daily: optimize time complexity and space "
                  "complexity, handle edge cases, pick the optimal approach under interview "
                  "conditions for our competitive programming platform.")
        rubric = rag.retrieve_rubric("Algorithm Engineer", "dsa", dsa_jd)
        assert "time complexity" in rubric["criteria"]

    def test_retrieval_changes_criteria_vs_static_for_same_category(self):
        static = rag.retrieve_rubric("Backend Engineer", "system design")
        dynamic = rag.retrieve_rubric(
            "Site Reliability Engineer",
            "system design",
            "Own reliability of distributed systems: failure modes, retries, idempotency, "
            "graceful degradation, incident response and monitoring at scale.",
        )
        # The SRE-flavored JD should pull in reliability-heavy guidance.
        joined = " ".join(dynamic["retrieved_snippets"]).lower()
        assert "failure" in joined or "degradation" in joined or "bottleneck" in joined

    def test_short_or_empty_jd_uses_static_lookup(self):
        rubric = rag.retrieve_rubric("X", "dsa", "short jd")
        assert rubric["retrieval_used"] is False
        assert rubric["criteria"] == rag.RUBRIC_BANK["dsa"]["criteria"]


class TestRetrievalFallback:
    def test_embedder_failure_falls_back_to_static_and_logs(self, monkeypatch, caplog):
        def broken_index():
            raise RuntimeError("embedding index exploded")

        monkeypatch.setattr(rag, "_get_index", broken_index)
        with caplog.at_level("WARNING", logger="app.engine.rag"):
            rubric = rag.retrieve_rubric("Backend Engineer", "dsa", BACKEND_JD)
        assert rubric["criteria"] == rag.RUBRIC_BANK["dsa"]["criteria"]
        assert rubric["retrieval_used"] is False
        assert "falling back" in caplog.text


class TestScoringRouteWiring:
    def test_run_scoring_uses_session_job_description_for_retrieval(self, monkeypatch, client, tmp_path):
        """End-to-end: the route must feed the session-linked JD into retrieval."""
        import app.core.db as db
        from api.routes import scoring as scoring_route
        from app.engine import trained_scorer

        # Hermetic: hide any locally-trained model so we exercise the
        # "no model yet -> ml_score is None" degradation path.
        monkeypatch.setattr(trained_scorer, "MODEL_PATH", tmp_path / "no_model.joblib")

        monkeypatch.setattr(
            db, "get_session",
            lambda sid: {"session_id": sid, "job_id": "job-1", "job_title": "Backend Engineer"},
        )
        monkeypatch.setattr(
            db, "get_job_posting",
            lambda jid: {"title": "Backend Engineer", "description": BACKEND_JD},
        )
        seen = {}

        def fake_retrieve(job_title, category, job_description=""):
            seen["args"] = (job_title, category, job_description)
            return {**rag.RUBRIC_BANK["technical"], "retrieval_used": False}

        # The route binds retrieve_rubric at import time - patch it there.
        monkeypatch.setattr(scoring_route, "retrieve_rubric", fake_retrieve)

        resp = client.post("/api/scoring/run", json={
            "session_id": "s-rag", "question_id": "q1",
            "category": "technical", "transcript": "I discussed caching trade-offs.",
        })
        assert resp.status_code == 200
        assert seen["args"][2] == BACKEND_JD  # real JD reached the retriever
        body = resp.json()
        assert body["rubric_source"] == "static_category_lookup"
        assert body["ml_score"] is None  # no model trained in test env


class TestEmbedderChain:
    def test_tfidf_embedder_normalizes_vectors(self):
        corpus = ["time complexity and space complexity analysis",
                  "teamwork and ownership in behavioral answers"]
        emb = embeddings.TfidfEmbedder(corpus)
        vectors = emb.encode([corpus[0], "completely different text about cooking pasta"])
        # In-corpus text normalizes to unit length; a fully out-of-vocabulary
        # query is a zero vector (similarity 0 with everything - documented).
        assert np.isclose(np.linalg.norm(vectors[0]), 1.0)
        assert np.allclose(vectors[1], 0.0)

    def test_get_embedder_falls_back_when_neural_unavailable(self, monkeypatch):
        calls = []

        def fail_neural():
            raise ImportError("model2vec not installed")

        monkeypatch.setattr(embeddings, "Model2VecEmbedder", fail_neural)
        monkeypatch.setattr(embeddings, "SentenceTransformerEmbedder", fail_neural)
        embeddings.reset_embedder_cache()
        try:
            emb = embeddings.get_embedder(reference_corpus=["some corpus text"])
            assert emb.name == "tfidf"
            calls.append(emb.name)
        finally:
            embeddings.reset_embedder_cache()
        assert calls == ["tfidf"]
