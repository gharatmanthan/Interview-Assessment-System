"""Deterministic LinkedIn job-post generator.

Builds the recruiter's post from the job posting itself — no LLM, no invented
data. A field is included only when it is actually present on the job missing
fields are omitted rather than hallucinated. The output is editable in the
frontend preview before publishing.
"""
import re

MAX_POST_CHARS = 3000  # LinkedIn commentary limit


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _eventual_a(title: str) -> str:
    return "an" if (title[:1] or "").lower() in "aeiou" else "a"


def _heading_slug(text: str) -> str:
    """One save hashtag-derived token: alphanumeric only, <= 24 chars."""
    slug = re.sub(r"[^a-zA-Z0-9]", "", text)
    return slug[:24]


def _hashtags(title: str, skills) -> list:
    tags = []
    for token in title.split():
        tag = _heading_slug(token)
        if tag and tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
            if len(tags) >= 2:
                break
    for skill in skills:
        tag = _heading_slug(str(skill))
        if tag and tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
            if len(tags) >= 4:
                break
    return tags


def _description_snippet(description: str, limit: int = 220) -> str:
    text = _strip(description)
    if not text:
        return ""
    if len(text) <= limit + 20:
        return text
    cut = text[:limit]
    at = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("; "))
    if at < limit // 2:
        at = cut.rfind(" ")
    if at <= 0:
        at = limit
    return cut[:at + 1].strip() + " …"


def generate_linkedin_post(job, public_url: str) -> str:
    """Compose the post from a job row (decoded dict / dataclass).

    Only fields present on the job are emitted; nothing is invented.
    """
    title = _strip(job.get("title", "")) or "This role"
    experience = _strip(job.get("experience_level", "") or "")
    department = _strip(job.get("department", "") or "")
    skills = [str(s).strip() for s in (job.get("required_skills") or []) if str(s).strip()]
    description = job.get("description", "") or ""

    lines = []
    lines.append("🚀 We're Hiring!")
    lines.append("")
    lines.append(title)
    lines.append("")

    detail = []
    if experience:
        detail.append(f"💼 Experience: {experience}")
    if department:
        detail.append(f"🏢 Department: {department}")
    if detail:
        lines.extend(detail)
        lines.append("")

    lines.append(f"We're looking for {_eventual_a(title)} {title} to join our team.")
    lines.append("")

    snippet = _description_snippet(description)
    if snippet:
        lines.append(snippet)
        lines.append("")

    if skills:
        lines.append("Key skills:")
        lines.extend(f"• {skill}" for skill in skills)
        lines.append("")

    lines.append("Apply here:")
    lines.append(public_url or "")
    lines.append("")

    tags = ["#Hiring", "#Jobs", "#Careers"]
    for tag in _hashtags(title, skills):
        tags.append(f"#{tag}")
    lines.append(" ".join(tags[:6]))

    post = "\n".join(lines)
    if len(post) > MAX_POST_CHARS:
        # Far beyond any realistic job posting — never let the payload float to
        # the API limit silently.
        post = post[:MAX_POST_CHARS].rstrip() + " …"
    return post.strip()