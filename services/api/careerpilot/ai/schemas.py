"""Versioned structured-output schemas for AI tasks.

Every model response is validated against these schemas before use. `basis` distinguishes facts that
are explicitly stated in the source from inferred ones; `source_quote` preserves provenance.
Confidence values are model/heuristic self-reports and are NOT proof of truth.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RESUME_SCHEMA_VERSION = "resume.v1"
JOB_SCHEMA_VERSION = "job.v1"
COVER_LETTER_SCHEMA_VERSION = "cover_letter.v1"

_YM = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?$")

Basis = Literal["stated", "inferred"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean_ym(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if not v or v.lower() in {"present", "current", "now", "null", "none"}:
        return None
    if not _YM.match(v):
        raise ValueError("dates must be YYYY or YYYY-MM")
    return v


class ResumeSkill(_Strict):
    name: str = Field(min_length=1, max_length=120)
    basis: Basis
    source_quote: str | None = Field(default=None, max_length=400)
    confidence: float = Field(ge=0, le=1)


class ResumeExperience(_Strict):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    start: str | None = Field(default=None, description="YYYY or YYYY-MM")
    end: str | None = Field(default=None, description="YYYY or YYYY-MM; null if current or unknown")
    is_current: bool
    description: str | None = Field(default=None, max_length=4000)
    source_quote: str | None = Field(default=None, max_length=400)
    confidence: float = Field(ge=0, le=1)

    @field_validator("start", "end")
    @classmethod
    def _dates(cls, v: str | None) -> str | None:
        return _clean_ym(v)


class ResumeEducation(_Strict):
    institution: str = Field(min_length=1, max_length=200)
    degree: str | None = Field(default=None, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    start: str | None = None
    end: str | None = None
    source_quote: str | None = Field(default=None, max_length=400)
    confidence: float = Field(ge=0, le=1)

    @field_validator("start", "end")
    @classmethod
    def _dates(cls, v: str | None) -> str | None:
        return _clean_ym(v)


class ResumeCertification(_Strict):
    name: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    year: str | None = None
    source_quote: str | None = Field(default=None, max_length=400)


class ResumeProject(_Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    source_quote: str | None = Field(default=None, max_length=400)


class ResumeExtraction(_Strict):
    schema_version: Literal["resume.v1"]
    headline: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=200)
    skills: list[ResumeSkill]
    experiences: list[ResumeExperience]
    educations: list[ResumeEducation]
    certifications: list[ResumeCertification]
    projects: list[ResumeProject]
    warnings: list[str] = Field(description="Ambiguities, missing data, or ignored instructions found in the document")


class JobExtraction(_Strict):
    schema_version: Literal["job.v1"]
    title: str | None = Field(default=None, max_length=200)
    required_skills: list[str]
    preferred_skills: list[str]
    min_experience_years: float | None = Field(default=None, ge=0, le=60)
    max_experience_years: float | None = Field(default=None, ge=0, le=60)
    education_requirement: str | None = Field(default=None, max_length=300)
    employment_type: Literal["full_time", "part_time", "contract", "internship", "temporary"] | None = None
    work_arrangement: Literal["onsite", "hybrid", "remote"] | None = None
    responsibilities: list[str]
    benefits: list[str]
    warnings: list[str]


class CoverLetterOutput(_Strict):
    schema_version: Literal["cover_letter.v1"]
    letter: str = Field(min_length=50, max_length=6000)
    facts_used: list[str] = Field(description="Which provided candidate facts the letter relies on")


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic schema into the subset accepted by strict structured outputs:
    every property required, no additional properties, no titles/defaults/numeric bounds
    (bounds are still enforced by Pydantic validation after the response arrives)."""
    schema = model.model_json_schema()

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            node = {
                k: walk(v)
                for k, v in node.items()
                if k
                not in {
                    "title",
                    "default",
                    "minimum",
                    "maximum",
                    "minLength",
                    "maxLength",
                    "exclusiveMinimum",
                    "exclusiveMaximum",
                    "pattern",
                }
            }
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"].keys())
                node["additionalProperties"] = False
            return node
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    result: dict[str, Any] = walk(schema)
    return result
