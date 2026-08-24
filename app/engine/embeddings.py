"""
Owner: Member B

Local text embeddings for the RAG rubric retrieval in rag.py.

Backend chain (first available wins, choice cached and logged):
  1. model2vec   - static embeddings distilled from MiniLM
                   (minishlab/potion-base-8M, ~32MB, no torch) - semantic,
                   lightweight, the intended default.
  2. sentence-transformers - full neural embeddings (all-MiniLM-L6-v2),
                   used automatically if it happens to be installed.
  3. TF-IDF      - scikit-learn lexical vectors fitted on the rubric KB.
                   Fully offline, deterministic, no downloads - the
                   guaranteed fallback when neither neural backend can load
                   (e.g. first run with no network for model download).

All backends return L2-normalized float vectors, so cosine similarity is a
plain dot product downstream. rag.py falls back to its static lookup if
this module raises for any reason.
"""
import logging

import numpy as np

logger = logging.getLogger(__name__)

MODEL2VEC_MODEL = "minishlab/potion-base-8M"
SENTENCE_TRANSFORMER_MODEL = "all-MiniLM-L6-v2"


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class BaseEmbedder:
    name = "base"

    def encode(self, texts: list) -> np.ndarray:
        raise NotImplementedError


class Model2VecEmbedder(BaseEmbedder):
    """Static embeddings via model2vec - semantic quality, tiny footprint."""

    def __init__(self):
        from model2vec import StaticModel

        self._model = StaticModel.from_pretrained(MODEL2VEC_MODEL)
        self.name = f"model2vec:{MODEL2VEC_MODEL}"

    def encode(self, texts: list) -> np.ndarray:
        return _l2_normalize(np.asarray(self._model.encode(texts), dtype=np.float64))


class SentenceTransformerEmbedder(BaseEmbedder):
    """Full transformer embeddings - highest quality, heaviest dependency."""

    def __init__(self):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)
        self.name = f"sentence-transformers:{SENTENCE_TRANSFORMER_MODEL}"

    def encode(self, texts: list) -> np.ndarray:
        return _l2_normalize(np.asarray(
            self._model.encode(texts, show_progress_bar=False), dtype=np.float64))


class TfidfEmbedder(BaseEmbedder):
    """
    Lexical TF-IDF vectors fitted on a reference corpus (the rubric KB).
    Content-dependent retrieval at near-zero cost; weaker semantics than
    the neural backends but always available offline.
    """

    def __init__(self, reference_corpus: list):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, strip_accents="unicode")
        self._vectorizer.fit(reference_corpus)
        self.name = "tfidf"

    def encode(self, texts: list) -> np.ndarray:
        return _l2_normalize(self._vectorizer.transform(texts).toarray().astype(np.float64))


_embedder = None
_embedder_failed = False


def get_embedder(reference_corpus: list = None) -> BaseEmbedder:
    """
    Return the best available embedder (cached). Neural backends are tried
    first; any failure loading them (not installed, no network for the
    model download, corrupted cache) falls through to TF-IDF. Set
    reference_corpus to enable the TF-IDF fallback path.
    """
    global _embedder, _embedder_failed

    if _embedder is not None:
        return _embedder
    if _embedder_failed:
        return TfidfEmbedder(reference_corpus or ["fallback"])

    for embedder_cls in (Model2VecEmbedder, SentenceTransformerEmbedder):
        try:
            _embedder = embedder_cls()
            logger.info("Embedding backend: %s", _embedder.name)
            return _embedder
        except ImportError:
            logger.info("%s not installed - trying next embedding backend", embedder_cls.__name__)
        except Exception as exc:
            logger.warning("Failed to load %s (%s: %s) - trying next embedding backend",
                           embedder_cls.__name__, type(exc).__name__, exc)

    if reference_corpus is None:
        raise RuntimeError("No embedding backend available and no reference corpus given "
                           "for the TF-IDF fallback.")
    _embedder_failed = True
    _embedder = TfidfEmbedder(reference_corpus)
    logger.warning("Falling back to TF-IDF embeddings over the rubric knowledge base.")
    return _embedder


def reset_embedder_cache():
    """Test hook: force re-detection of the embedding backend."""
    global _embedder, _embedder_failed
    _embedder = None
    _embedder_failed = False
