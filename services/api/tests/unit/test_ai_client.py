"""AI client robustness: invalid output, bounded retries, circuit breaker, usage recording."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from careerpilot.ai import providers
from careerpilot.ai.client import breaker, run_structured
from careerpilot.ai.providers import AIError, LLMRequest, LLMResponse
from careerpilot.ai.schemas import JobExtraction
from careerpilot.models import AIUsageRecord


class ScriptedProvider:
    name = "scripted"
    model = "scripted-1"

    def __init__(self, outputs: list[str | Exception]) -> None:
        self.outputs = outputs
        self.calls = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        if isinstance(out, Exception):
            raise out
        return LLMResponse(text=out, model=self.model, provider=self.name, input_tokens=10, output_tokens=5)


VALID = (
    '{"schema_version": "job.v1", "title": null, "required_skills": ["Python"], "preferred_skills": [], '
    '"min_experience_years": null, "max_experience_years": null, "education_requirement": null, '
    '"employment_type": null, "work_arrangement": null, "responsibilities": [], "benefits": [], "warnings": []}'
)


def _req() -> LLMRequest:
    return LLMRequest(operation="job_extraction", system="s", prompt="p")


def test_malformed_then_valid_output_recovers(db) -> None:  # type: ignore[no-untyped-def]
    p = ScriptedProvider(["not json at all", VALID])
    providers.set_providers(p, None)
    result, _ = run_structured(db, _req(), JobExtraction)
    assert result.required_skills == ["Python"] and p.calls == 2
    db.commit()
    usage = db.scalars(select(AIUsageRecord)).all()
    assert [u.success for u in usage] == [False, True]
    assert usage[0].error_code == "invalid_output"


def test_retries_are_bounded(db) -> None:  # type: ignore[no-untyped-def]
    p = ScriptedProvider(['{"schema_version": "job.v1"}'])
    providers.set_providers(p, None)
    with pytest.raises(AIError) as exc:
        run_structured(db, _req(), JobExtraction)
    assert exc.value.code == "invalid_output" and p.calls == 2


def test_refusal_is_not_retried(db) -> None:  # type: ignore[no-untyped-def]
    p = ScriptedProvider([AIError("refusal")])
    providers.set_providers(p, None)
    with pytest.raises(AIError):
        run_structured(db, _req(), JobExtraction)
    assert p.calls == 1


def test_circuit_breaker_opens_after_repeated_failures(db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("careerpilot.ai.client.time.sleep", lambda _s: None)
    p = ScriptedProvider([AIError("unavailable")])
    providers.set_providers(p, None)
    for _ in range(3):
        with pytest.raises(AIError):
            run_structured(db, _req(), JobExtraction)
    with pytest.raises(AIError) as exc:
        run_structured(db, _req(), JobExtraction)
    assert exc.value.code == "circuit_open"
    breaker.reset()


def test_mock_provider_is_labeled() -> None:
    p = providers.MockLLMProvider()
    assert p.model == "mock-deterministic-v1"


def test_production_rejects_mock_ai(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from careerpilot.config import Settings

    with pytest.raises(ValueError, match="mock"):
        Settings(
            environment="production",
            secret_key="x" * 40,
            cookie_secure=True,
            llm_provider="mock",
            email_provider="smtp",
            storage_provider="s3",
        )
