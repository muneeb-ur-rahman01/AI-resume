"""Skill normalization against the controlled taxonomy (deterministic, no LLM)."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from careerpilot.ai.taxonomy_data import CASE_SENSITIVE_ALIASES, SKILLS


def slugify(text: str) -> str:
    text = text.lower().replace("+", "plus").replace("#", "sharp").replace(".", "dot")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def basic_normalize(name: str) -> str:
    """Normalization key for skills not in the taxonomy."""
    return re.sub(r"\s+", " ", name.strip().lower())[:120]


@dataclass(frozen=True)
class SkillMatch:
    canonical: str
    matched_text: str
    context: str


class SkillNormalizer:
    def __init__(self, entries: list[tuple[str, list[str]]]) -> None:
        self._lookup: dict[str, str] = {}
        patterns: list[tuple[str, re.Pattern[str]]] = []
        for canonical, aliases in entries:
            for term in [canonical, *aliases]:
                self._lookup[basic_normalize(term)] = canonical
                sensitive = term in CASE_SENSITIVE_ALIASES or len(term) <= 2
                flags = 0 if sensitive else re.IGNORECASE
                # Word-ish boundaries that also work for terms such as "C++", "C#", ".NET", "Node.js".
                pat = re.compile(r"(?<![A-Za-z0-9+#.&])" + re.escape(term) + r"(?![A-Za-z0-9+#&]|\.[A-Za-z])", flags)
                patterns.append((canonical, pat))
        # Longer terms first so that "React Native" wins over "React".
        self._patterns = sorted(patterns, key=lambda p: -len(p[1].pattern))
        self.canonicals = sorted({c for c, _ in entries})

    def canonicalize(self, name: str) -> str | None:
        return self._lookup.get(basic_normalize(name))

    def normalize(self, name: str) -> tuple[str, str, bool]:
        """Returns (display_name, normalized_key, in_taxonomy)."""
        canonical = self.canonicalize(name)
        if canonical:
            return canonical, basic_normalize(canonical), True
        clean = re.sub(r"\s+", " ", name.strip())[:120]
        return clean, basic_normalize(clean), False

    def find_in_text(self, text: str) -> list[SkillMatch]:
        found: dict[str, SkillMatch] = {}
        consumed: list[tuple[int, int]] = []
        for canonical, pat in self._patterns:
            for m in pat.finditer(text):
                span = m.span()
                if any(s < span[1] and span[0] < e for s, e in consumed):
                    continue
                consumed.append(span)
                if canonical not in found:
                    line_start = text.rfind("\n", 0, span[0]) + 1
                    line_end = text.find("\n", span[1])
                    context = text[line_start : line_end if line_end != -1 else len(text)].strip()[:300]
                    found[canonical] = SkillMatch(canonical, m.group(0), context)
        return list(found.values())

    def mentioned(self, canonical: str, text: str) -> bool:
        return any(m.canonical == canonical for m in self.find_in_text(text))


_cache: tuple[float, SkillNormalizer] | None = None
_lock = threading.Lock()
_static = SkillNormalizer([(c, a) for c, _, a in SKILLS])


def static_normalizer() -> SkillNormalizer:
    return _static


def get_normalizer(db: Session | None = None, ttl: float = 300.0) -> SkillNormalizer:
    """Normalizer built from the DB taxonomy (admin-managed), cached; falls back to the seed list."""
    global _cache
    if db is None:
        return _static
    with _lock:
        if _cache and time.monotonic() - _cache[0] < ttl:
            return _cache[1]
    from careerpilot.models import SkillTaxonomy

    rows = db.execute(
        select(SkillTaxonomy.canonical_name, SkillTaxonomy.aliases).where(SkillTaxonomy.is_active.is_(True))
    ).all()
    normalizer = SkillNormalizer([(r[0], list(r[1] or [])) for r in rows]) if rows else _static
    with _lock:
        _cache = (time.monotonic(), normalizer)
    return normalizer


def invalidate_normalizer_cache() -> None:
    global _cache
    with _lock:
        _cache = None
