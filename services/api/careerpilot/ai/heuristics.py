"""Deterministic resume parsing.

Used (1) when the candidate has not consented to third-party AI processing, (2) by the clearly labeled
mock LLM provider in development/tests, and (3) as a fallback when the AI provider is unavailable.
Output conforms to the same ResumeExtraction schema; confidence values are fixed heuristic levels.
"""

from __future__ import annotations

import re

from careerpilot.ai.schemas import (
    RESUME_SCHEMA_VERSION,
    ResumeCertification,
    ResumeEducation,
    ResumeExperience,
    ResumeExtraction,
    ResumeProject,
    ResumeSkill,
)
from careerpilot.ai.skills import SkillNormalizer

SECTION_ALIASES = {
    "summary": ["summary", "profile", "professional summary", "about me", "objective", "career objective"],
    "experience": [
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "employment",
        "work history",
        "career history",
    ],
    "education": ["education", "academic background", "education and training", "qualifications"],
    "skills": ["skills", "technical skills", "core skills", "key skills", "competencies", "technologies"],
    "projects": ["projects", "selected projects", "personal projects"],
    "certifications": ["certifications", "certificates", "licenses and certifications", "licenses"],
}
_HEADER_LOOKUP = {alias: key for key, aliases in SECTION_ALIASES.items() for alias in aliases}

_MONTHS = {
    m: i
    for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)
}
_MONTH_RE = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_RE = rf"(?:{_MONTH_RE}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}}-\d{{2}}|\d{{4}})"
_RANGE_RE = re.compile(rf"(?P<start>{_DATE_RE})\s*(?:-|–|—|to)\s*(?P<end>{_DATE_RE}|present|current|now|today)", re.I)
_DEGREE_RE = re.compile(
    r"\b(bachelor|master|b\.?sc|m\.?sc|b\.?s\.?|m\.?s\.?|b\.?a\.?|m\.?a\.?|mba|ph\.?d|doctorate|diploma|"
    r"associate|b\.?eng|m\.?eng|bachelor's|master's)\b",
    re.I,
)
_INSTITUTION_RE = re.compile(r"\b(university|college|institute|school|academy|polytechnic)\b", re.I)
_CONTACT_RE = re.compile(r"(@|https?://|www\.|linkedin|github\.com|\+?\d[\d\s().-]{7,})", re.I)
_INJECTION_RE = re.compile(
    r"(ignore (all |any )?(previous|prior|above) instructions|system prompt|you are now|"
    r"disregard (the )?(rules|instructions)|rate this (candidate|resume)|perfect match)",
    re.I,
)


def _to_ym(token: str) -> str | None:
    token = token.strip().lower().rstrip(".")
    if token in {"present", "current", "now", "today"}:
        return None
    if m := re.match(rf"({_MONTH_RE})\s+(\d{{4}})", token):
        month = _MONTHS.get(m.group(1)[:3])
        return f"{m.group(2)}-{month:02d}" if month else m.group(2)
    if m := re.match(r"(\d{1,2})/(\d{4})", token):
        month = int(m.group(1))
        return f"{m.group(2)}-{month:02d}" if 1 <= month <= 12 else m.group(2)
    if m := re.match(r"(\d{4})-(\d{2})", token):
        return token if 1 <= int(m.group(2)) <= 12 else m.group(1)
    if re.fullmatch(r"\d{4}", token):
        return token
    return None


def split_sections(text: str) -> dict[str, str]:
    """Split normalized resume text into sections keyed by canonical section name ('header' = preamble)."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for raw in text.splitlines():
        line = raw.strip()
        key = re.sub(r"[^a-z ]", "", line.lower()).strip()
        if key in _HEADER_LOOKUP and len(line) <= 40:
            current = _HEADER_LOOKUP[key]
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _split_title_company(text: str) -> tuple[str, str] | None:
    text = re.sub(r"\s+", " ", text).strip(" ,|-–—")
    if not text:
        return None
    for sep in (" at ", " @ ", " | ", " — ", " – ", " - ", ", "):
        if sep in text:
            title, company = text.split(sep, 1)
            title, company = title.strip(" ,|"), company.strip(" ,|")
            if title and company:
                return title[:200], company[:200]
    return None


def _parse_experiences(section: str) -> list[ResumeExperience]:
    lines = [ln for ln in section.splitlines()]
    results: list[ResumeExperience] = []
    for i, line in enumerate(lines):
        m = _RANGE_RE.search(line)
        if not m:
            continue
        remainder = (line[: m.start()] + " " + line[m.end() :]).strip()
        pair = _split_title_company(remainder)
        if pair is None and i > 0:
            pair = _split_title_company(lines[i - 1])
        if pair is None:
            continue
        end_token = m.group("end")
        is_current = end_token.lower() in {"present", "current", "now", "today"}
        desc_lines: list[str] = []
        for nxt in lines[i + 1 :]:
            if not nxt or _RANGE_RE.search(nxt):
                break
            desc_lines.append(nxt.lstrip("•*-– ").strip())
        # If the next experience's title line was captured as description, drop it.
        if desc_lines and i + len(desc_lines) + 1 < len(lines) and _RANGE_RE.search(lines[i + len(desc_lines) + 1]):
            desc_lines = desc_lines[:-1]
        results.append(
            ResumeExperience(
                title=pair[0],
                company=pair[1],
                location=None,
                start=_to_ym(m.group("start")),
                end=None if is_current else _to_ym(end_token),
                is_current=is_current,
                description="\n".join(desc_lines)[:4000] or None,
                source_quote=line[:400],
                confidence=0.6,
            )
        )
    return results


def _parse_educations(section: str) -> list[ResumeEducation]:
    results: list[ResumeEducation] = []
    lines = [ln for ln in section.splitlines() if ln.strip()]
    used: set[int] = set()
    for i, line in enumerate(lines):
        if i in used or not (_INSTITUTION_RE.search(line) or _DEGREE_RE.search(line)):
            continue
        block = [line]
        if i + 1 < len(lines) and (_INSTITUTION_RE.search(lines[i + 1]) or _DEGREE_RE.search(lines[i + 1])):
            block.append(lines[i + 1])
            used.add(i + 1)
        joined = " | ".join(block)
        inst_line = next((b for b in block if _INSTITUTION_RE.search(b)), None)
        degree_line = next((b for b in block if _DEGREE_RE.search(b)), None)
        year_vals = re.findall(r"\b(?:19|20)\d{2}\b", joined)
        institution = _RANGE_RE.sub("", inst_line or block[0]).strip(" ,|-–")
        degree = None
        field = None
        if degree_line:
            degree_text = _RANGE_RE.sub("", degree_line).strip(" ,|-–")
            if degree_line is inst_line:
                parts = re.split(r",| - | \| ", degree_text)
                degree_text = next((p for p in parts if _DEGREE_RE.search(p)), degree_text).strip()
            if " in " in degree_text:
                degree, field = (s.strip() for s in degree_text.split(" in ", 1))
            else:
                degree = degree_text
        if institution and degree and institution in degree:
            institution = institution.replace(degree, "").strip(" ,|-–")
        results.append(
            ResumeEducation(
                institution=(institution or "Unknown institution")[:200],
                degree=(degree or None) and degree[:200],
                field_of_study=(field or None) and field[:200],
                start=year_vals[0] if len(year_vals) >= 2 else None,
                end=year_vals[-1] if year_vals else None,
                source_quote=joined[:400],
                confidence=0.5,
            )
        )
    return results


def heuristic_extract(text: str, normalizer: SkillNormalizer) -> ResumeExtraction:
    sections = split_sections(text)
    warnings: list[str] = []
    if _INJECTION_RE.search(text):
        warnings.append("The document contains text that looks like instructions to an AI system; it was ignored.")

    skills: list[ResumeSkill] = []
    skills_section = sections.get("skills", "")
    for match in normalizer.find_in_text(text):
        in_skills_section = bool(skills_section) and match.context in skills_section
        skills.append(
            ResumeSkill(
                name=match.canonical,
                basis="stated",
                source_quote=match.context[:400],
                confidence=0.8 if in_skills_section else 0.6,
            )
        )

    experiences = _parse_experiences(sections.get("experience", ""))
    educations = _parse_educations(sections.get("education", ""))
    if "experience" not in sections:
        warnings.append("No experience section was detected.")

    summary = sections.get("summary") or None
    headline = None
    for line in sections.get("header", "").splitlines()[1:4]:
        if line and not _CONTACT_RE.search(line) and len(line) <= 120:
            headline = line
            break

    certifications = [
        ResumeCertification(name=ln.lstrip("•*- ")[:200], issuer=None, year=None, source_quote=ln[:400])
        for ln in sections.get("certifications", "").splitlines()
        if ln.strip()
    ][:20]
    projects = [
        ResumeProject(name=ln.lstrip("•*- ")[:200], description=None, source_quote=ln[:400])
        for ln in sections.get("projects", "").splitlines()
        if ln.strip() and len(ln) < 120
    ][:20]

    return ResumeExtraction(
        schema_version=RESUME_SCHEMA_VERSION,
        headline=headline,
        summary=summary[:2000] if summary else None,
        location=None,
        skills=skills,
        experiences=experiences,
        educations=educations,
        certifications=certifications,
        projects=projects,
        warnings=warnings,
    )
