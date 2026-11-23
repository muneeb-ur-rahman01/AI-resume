"""Guarded LLM invocation: bounded concurrency, circuit breaker, schema validation with one repair
retry, usage/cost recording, and normalized errors. Prompts and outputs are never logged."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from careerpilot.ai.providers import AIError, LLMRequest, LLMResponse, get_llm_provider
from careerpilot.config import get_settings
from careerpilot.models import AIUsageRecord

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class CircuitBreaker:
    def __init__(self, threshold: int = 5, cooldown_seconds: float = 60.0) -> None:
        self.threshold = threshold
        self.cooldown = cooldown_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            if self._opened_at and time.monotonic() - self._opened_at < self.cooldown:
                raise AIError("circuit_open", "AI provider temporarily disabled after repeated failures")
            if self._opened_at:
                self._opened_at = None  # half-open: allow a trial request

    def record(self, ok: bool) -> None:
        with self._lock:
            if ok:
                self._failures = 0
            else:
                self._failures += 1
                if self._failures >= self.threshold:
                    self._opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self._failures, self._opened_at = 0, None


breaker = CircuitBreaker()
_semaphore = threading.BoundedSemaphore(max(1, get_settings().llm_max_concurrency))
_TRANSIENT = {"timeout", "unavailable", "rate_limited"}


def _record_usage(
    db: Session,
    user_id: uuid.UUID | None,
    req: LLMRequest,
    resp: LLMResponse | None,
    provider: str,
    model: str,
    started: float,
    error: str | None,
) -> None:
    s = get_settings()
    in_tok = resp.input_tokens if resp else 0
    out_tok = resp.output_tokens if resp else 0
    cost = (
        0.0
        if provider == "mock"
        else (in_tok * s.llm_input_cost_per_mtok + out_tok * s.llm_output_cost_per_mtok) / 1_000_000
    )
    db.add(
        AIUsageRecord(
            user_id=user_id,
            provider=provider,
            model=resp.model if resp else model,
            operation=req.operation,
            prompt_version=req.prompt_version,
            input_tokens=in_tok,
            output_tokens=out_tok,
            estimated_cost_usd=round(cost, 6),
            latency_ms=int((time.monotonic() - started) * 1000),
            success=error is None,
            error_code=error,
        )
    )


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text


def run_structured(
    db: Session, request: LLMRequest, schema: type[T], *, user_id: uuid.UUID | None = None, max_attempts: int = 2
) -> tuple[T, LLMResponse]:
    """Call the configured LLM and return a validated instance of `schema`.

    Retries at most `max_attempts` times in total on invalid output or transient errors (the SDK itself
    also performs bounded HTTP retries). Raises AIError on failure. Never retries indefinitely.
    """
    request.schema = schema
    provider = get_llm_provider()
    last_error: AIError | None = None
    for attempt in range(1, max_attempts + 1):
        breaker.check()
        started = time.monotonic()
        response: LLMResponse | None = None
        if not _semaphore.acquire(timeout=get_settings().llm_timeout_seconds):
            raise AIError("unavailable", "AI concurrency limit reached")
        try:
            response = provider.complete(request)
            parsed = schema.model_validate(json.loads(_extract_json(response.text)))
            breaker.record(True)
            _record_usage(db, user_id, request, response, provider.name, provider.model, started, None)
            return parsed, response
        except (json.JSONDecodeError, ValidationError):
            last_error = AIError("invalid_output", "model output failed schema validation")
            breaker.record(True)  # provider is healthy; output was bad
        except AIError as exc:
            last_error = exc
            # Refusals/bad output mean the provider is reachable; only availability errors trip the breaker.
            breaker.record(exc.code in {"refusal", "invalid_output", "truncated"})
        finally:
            _semaphore.release()
        _record_usage(db, user_id, request, response, provider.name, provider.model, started, last_error.code)
        logger.warning(
            "llm_call_failed", extra={"operation": request.operation, "error_code": last_error.code, "attempt": attempt}
        )
        if last_error.code not in _TRANSIENT | {"invalid_output"}:
            break
        if last_error.code in _TRANSIENT and attempt < max_attempts:
            time.sleep(min(2.0 * attempt, 5.0))
    assert last_error is not None
    raise last_error
