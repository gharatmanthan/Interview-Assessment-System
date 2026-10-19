"""Shared Groq LLM helper with explicit error reporting."""
import json
import os
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
GROQ_MODEL = "openai/gpt-oss-20b"
last_error = ""


def llm_available() -> bool:
    return bool(GROQ_API_KEY)


def ask_llm(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    global last_error
    if not GROQ_API_KEY:
        last_error = "GROQ_API_KEY is not configured."
        raise RuntimeError(last_error)
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
    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        last_error = ""
        return content
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        last_error = f"{type(exc).__name__}: {exc}"
        raise RuntimeError(f"Groq request failed: {last_error}") from exc
