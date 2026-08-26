"""
Owner: Member B
Shared LLM helper for scoring.py, explainability.py, fairness.py,
jd_matcher.py and resume_parser.py.

Uses Groq's free-tier API (OpenAI-compatible, fast Llama models) when
GROQ_API_KEY is configured — either as a real environment variable or in
a `.env` file at the project root (auto-loaded here via python-dotenv).
If no key is configured, llm_available() returns False and every caller
falls back to a heuristic (non-LLM) method with a logged reason — never
a silent one.

Hardening guarantees:
  - explicit per-request timeout (LLM_REQUEST_TIMEOUT seconds)
  - one automatic retry with short backoff on transient failures only
    (timeouts, connection errors, 5xx) — 4xx responses fail immediately
  - parse_llm_json() tolerates markdown-fenced or preamble-wrapped JSON

Every real API call is appended to call_log so scripts/tests can verify
the LLM path was actually taken instead of assuming it.

To enable real LLM scoring:
    1. Get a free key at https://console.groq.com
    2. Copy .env.example to .env and set GROQ_API_KEY=<your-key>
       (or set $env:GROQ_API_KEY before launching)
"""
import json
import logging
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ENV_PATH = PROJECT_ROOT / ".env"

# .env values never override variables already set in the environment.
load_dotenv(PROJECT_ENV_PATH)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.6-27b"

# An interview flow cannot hang indefinitely; 15s covers slow generations
# without freezing the scoring pipeline.
LLM_REQUEST_TIMEOUT = 15.0
RETRY_BACKOFF_SECONDS = 1.0
MAX_ATTEMPTS = 2  # first try + one retry for transient failures

# Appended for every attempt at the real API — lets callers prove the LLM
# path ran (see scripts/verify_llm_live.py).
call_log = []


def _get_api_key():
    """Read live from the environment each call (tests monkeypatch env vars)."""
    key = os.environ.get("GROQ_API_KEY", "").strip()
    return key or None


def llm_available() -> bool:
    return _get_api_key() is not None


def ask_llm(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    """
    Call the LLM, return raw text content of its response.

    Retries once on transient failures (timeout / connection error / 5xx),
    raises immediately on 4xx. Raises on total failure — callers must check
    llm_available() first and wrap this in try/except with a logged
    heuristic fallback (see scoring.py).
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("No GROQ_API_KEY configured")

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        entry = {"attempt": attempt, "model": GROQ_MODEL}
        try:
            logger.info("Groq API call (model=%s, attempt=%d/%d)", GROQ_MODEL, attempt, MAX_ATTEMPTS)
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=LLM_REQUEST_TIMEOUT)
            entry["status"] = resp.status_code
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            entry.update(ok=True, latency_ms=round((time.monotonic() - started) * 1000))
            call_log.append(entry)
            logger.info("Groq API call succeeded in %dms", entry["latency_ms"])
            return content
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            last_error = exc
            call_log.append({**entry, "ok": False, "error": f"http_{status}"})
            # 4xx is our fault (bad key/bad request) — retrying won't help.
            if status is not None and status < 500:
                logger.warning("Groq API returned HTTP %d (no retry): %s", status, exc)
                raise
            logger.warning("Groq API server error (HTTP %s) on attempt %d: %s", status, attempt, exc)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            call_log.append({**entry, "ok": False, "error": type(exc).__name__})
            logger.warning("Groq API transient failure on attempt %d: %s", attempt, exc)
        except (ValueError, KeyError) as exc:
            # Malformed response body (e.g. non-JSON payload from a proxy).
            last_error = exc
            call_log.append({**entry, "ok": False, "error": f"malformed_response: {exc}"})
            logger.warning("Groq API returned malformed response on attempt %d: %s", attempt, exc)

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS)

    raise RuntimeError(f"Groq API failed after {MAX_ATTEMPTS} attempts: {last_error}")


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_llm_json(raw: str) -> dict:
    """
    Parse a JSON object out of a raw LLM response.

    Real models frequently wrap JSON in markdown fences ("```json ... ```")
    or add preamble text ("Here is the JSON you asked for: {...}"), which
    breaks naive json.loads(). Tries, in order: fenced block, whole text,
    outermost {...} span. Raises ValueError if none parse to a dict.
    """
    text = (raw or "").strip()

    candidates = []
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data

    raise ValueError(f"LLM response was not parseable as JSON object: {text[:200]!r}")
