"""
Owner: Member B
Shared LLM helper for scoring.py, explainability.py, fairness.py.

Uses Groq's free-tier API (OpenAI-compatible models) if
GROQ_API_KEY is set as an environment variable. If no key is configured,
llm_available() returns False and every caller in this package falls back
to a heuristic (non-LLM) method — so the app runs end-to-end out of the
box, just with lower-quality scoring until a key is added.

To enable real LLM scoring:
    1. Get a free key at https://console.groq.com
    2. Windows (PowerShell), before running the app:
       $env:GROQ_API_KEY = "your-key-here"
       python -m app.main
"""
import os
import json
from pathlib import Path
import requests


def _load_api_key():
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key

    settings_path = Path(__file__).parents[2] / "data" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        configured = str(settings.get("llm_api_key", "")).strip()
        if configured.startswith("GROQ_API_KEY="):
            configured = configured.split("=", 1)[1].strip()
        return configured.strip('"\'')
    except (OSError, json.JSONDecodeError):
        return ""


GROQ_API_KEY = _load_api_key()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Keep this on a current production model; retired model IDs return 404.
GROQ_MODEL = "openai/gpt-oss-20b"


def llm_available() -> bool:
    return bool(GROQ_API_KEY)


def ask_llm(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    """
    Call the LLM, return raw text content of its response.
    Raises on failure — callers must check llm_available() first and
    wrap this in try/except with a heuristic fallback (see scoring.py).
    """
    if not GROQ_API_KEY:
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

    resp = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]