"""
Owner: Member B
OBJECTIVE 2 deliverable: Resume parsing

Extracts raw text from PDF/DOCX/TXT resumes, then either uses the LLM
(if GROQ_API_KEY is configured) to pull structured fields, or falls back
to a keyword/regex heuristic. Output feeds jd_matcher.py.
"""
import json
import re
from pathlib import Path

from app.engine import llm_client

COMMON_SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "sql", "nosql",
    "react", "angular", "vue", "node.js", "django", "flask", "fastapi",
    "aws", "azure", "gcp", "docker", "kubernetes", "git", "linux",
    "machine learning", "deep learning", "nlp", "pandas", "numpy", "pytorch",
    "tensorflow", "rest api", "graphql", "microservices", "ci/cd", "agile",
]


def _extract_text(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        import pdfplumber
        chunks = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text() or "")
        return "\n".join(chunks)

    if suffix == ".docx":
        import docx
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)

    # .txt or anything else — read as plain text
    return path.read_text(encoding="utf-8", errors="ignore")


def _heuristic_parse(raw_text: str) -> dict:
    lower = raw_text.lower()
    found_skills = [s for s in COMMON_SKILLS if s in lower]

    years_match = re.search(r"(\d+)\+?\s*years?\s+(of\s+)?experience", lower)
    experience_years = float(years_match.group(1)) if years_match else None

    education_keywords = ["b.tech", "bachelor", "b.e.", "m.tech", "master", "phd", "diploma", "b.sc", "m.sc"]
    education = [line.strip() for line in raw_text.splitlines()
                 if any(k in line.lower() for k in education_keywords)][:5]

    return {"skills": found_skills, "experience_years": experience_years, "education": education}


def parse_resume(file_path: str) -> dict:
    """
    Must return:
    {"raw_text": str, "skills": [str], "experience_years": float|None, "education": [str]}
    Consumed by: app/engine/jd_matcher.py
    """
    raw_text = _extract_text(file_path)
    structured = None

    if llm_client.llm_available():
        try:
            system = (
                "Extract structured fields from this resume text. "
                'Respond ONLY as JSON: {"skills": [str, ...], '
                '"experience_years": <float or null>, "education": [str, ...]}'
            )
            raw = llm_client.ask_llm(system, raw_text[:6000], json_mode=True)
            structured = json.loads(raw)
        except Exception:
            structured = None

    if structured is None:
        structured = _heuristic_parse(raw_text)

    return {
        "raw_text": raw_text,
        "skills": structured.get("skills", []),
        "experience_years": structured.get("experience_years"),
        "education": structured.get("education", []),
    }