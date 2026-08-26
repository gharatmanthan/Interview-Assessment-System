"""Resume extraction and transparent job matching helpers."""
import json
import re
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
SKILL_TERMS = {
    "python", "java", "javascript", "typescript", "c++", "sql", "nosql",
    "html", "css", "react", "django", "flask", "fastapi", "node.js",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "opencv",
    "docker", "kubernetes", "aws", "azure", "gcp", "git", "linux",
    "rest", "graphql", "microservices", "machine learning", "deep learning",
    "data structures", "algorithms", "system design", "communication",
}
SECTION_NAMES = {
    "summary": "summary",
    "profile": "summary",
    "objective": "summary",
    "experience": "experience",
    "work experience": "experience",
    "education": "education",
    "projects": "projects",
    "certifications": "certifications",
    "skills": "skills",
}


def _read_text(path: Path) -> str:
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if path.suffix.lower() == ".docx":
        from docx import Document
        return "\n".join(paragraph.text for paragraph in Document(str(path)).paragraphs)
    raise ValueError("Supported resume formats are PDF, DOCX, and TXT.")


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _sections(text: str) -> dict:
    sections = {name: [] for name in set(SECTION_NAMES.values())}
    current = "summary"
    for line in text.splitlines():
        heading = re.sub(r"[^a-z ]", "", line.lower()).strip()
        if heading in SECTION_NAMES:
            current = SECTION_NAMES[heading]
            continue
        if line.strip():
            sections[current].append(line.strip())
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def extract_resume(path: str) -> dict:
    """Extract searchable profile data from a local resume file."""
    resume_path = Path(path)
    if not resume_path.is_file():
        raise FileNotFoundError(f"Resume file not found: {path}")
    if resume_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("Supported resume formats are PDF, DOCX, and TXT.")

    text = _read_text(resume_path).strip()
    if not text:
        raise ValueError("The resume did not contain readable text.")
    normalised = _normalise(text)
    skills = sorted(skill for skill in SKILL_TERMS if skill in normalised)
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone_match = re.search(r"(?:\+?\d[\d ()-]{7,}\d)", text)
    years = [int(value) for value in re.findall(r"\b(\d{1,2})\+?\s+years?", normalised)]
    sections = _sections(text)
    return {
        "file_name": resume_path.name,
        "name": text.splitlines()[0].strip()[:120],
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
        "skills": skills,
        "years_experience": max(years, default=0),
        "sections": sections,
        "raw_text": text,
    }


def match_resume_to_job(profile: dict, job_title: str, description: str) -> dict:
    """Return an explainable keyword match between a profile and job posting."""
    job_text = _normalise(f"{job_title} {description}")
    required_terms = sorted({skill for skill in SKILL_TERMS if skill in job_text})
    profile_skills = set(profile.get("skills", []))
    matched = sorted(profile_skills.intersection(required_terms))
    missing = sorted(set(required_terms).difference(profile_skills))
    score = round((len(matched) / len(required_terms)) * 100, 1) if required_terms else 0.0
    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "required_skills": required_terms,
        "summary": "No recognised skills were found in this job posting." if not required_terms else (
            f"Matched {len(matched)} of {len(required_terms)} recognised job skills."
        ),
    }


def profile_json(profile: dict) -> str:
    return json.dumps(profile, ensure_ascii=True)
