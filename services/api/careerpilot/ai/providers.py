"""Provider-independent AI interfaces and implementations.

LLMProvider implementations:
  - MockLLMProvider: DETERMINISTIC TEST DOUBLE. Uses heuristics/templates, never calls a model.
    Its responses carry model name "mock-deterministic-v1" so they are never mistaken for real AI output.
    Refused in staging/production unless ALLOW_MOCK_AI_IN_PRODUCTION is explicitly set.
  - AnthropicLLMProvider: Claude via the official Anthropic SDK with structured outputs.

EmbeddingProvider implementations:
  - HashingEmbeddingProvider: local, deterministic lexical feature-hashing embedder. No external calls.
    It is a real but low-quality baseline (captures token/skill overlap, not deep semantics).
  - OpenAICompatibleEmbeddingProvider: any service exposing POST {base}/embeddings in the common
    `{"model", "input"} -> {"data": [{"embedding": [...]}]}` format (e.g. Voyage AI, self-hosted servers).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from careerpilot.config import get_settings


class AIError(Exception):
    """Normalized provider error. `code` is one of: timeout, rate_limited, refusal, invalid_output,
    truncated, provider_error, unavailable, circuit_open, not_configured."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class LLMRequest:
    operation: str  # resume_extraction | job_extraction | cover_letter | ...
    system: str
    prompt: str
    schema: type[BaseModel] | None = None
    prompt_version: str = "v1"
    max_output_tokens: int | None = None
    # Structured context that a deterministic mock may use instead of parsing the prompt.
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


# ---------------------------------------------------------------------------------------------- mock
class MockLLMProvider:
    name = "mock"
    model = "mock-deterministic-v1"

    def complete(self, request: LLMRequest) -> LLMResponse:
        from careerpilot.ai import mock_outputs

        handler = getattr(mock_outputs, request.operation, None)
        if handler is None:
            raise AIError("not_configured", f"mock has no handler for {request.operation}")
        payload = handler(request)
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            input_tokens=len(request.prompt) // 4,
            output_tokens=len(text) // 4,
        )


# ----------------------------------------------------------------------------------------- anthropic
class AnthropicLLMProvider:
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        s = get_settings()
        if s.anthropic_api_key is None:
            raise AIError("not_configured", "ANTHROPIC_API_KEY is not set")
        self.model = s.llm_model
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(
            api_key=s.anthropic_api_key.get_secret_value(),
            timeout=s.llm_timeout_seconds,
            max_retries=s.llm_max_retries,  # SDK retries 408/409/429/5xx with backoff (bounded)
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        from careerpilot.ai.schemas import strict_json_schema

        s = get_settings()
        output_config: dict[str, Any] = {"effort": s.llm_effort}
        if request.schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": strict_json_schema(request.schema)}
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_output_tokens or s.llm_max_output_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.prompt}],
            "output_config": output_config,
        }
        a = self._anthropic
        try:
            if s.llm_fallbacks == "default":
                # Server-side fallback: if the model declines on a safety-classifier refusal, the API
                # retries on a fallback model within the same call.
                response = self._client.beta.messages.create(
                    **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = self._client.messages.create(**kwargs)
        except a.APITimeoutError as exc:
            raise AIError("timeout") from exc
        except a.RateLimitError as exc:
            raise AIError("rate_limited") from exc
        except a.AuthenticationError as exc:
            raise AIError("not_configured", "authentication failed") from exc
        except a.BadRequestError as exc:
            raise AIError("provider_error", "request rejected") from exc
        except a.APIStatusError as exc:
            raise AIError("unavailable" if exc.status_code >= 500 else "provider_error") from exc
        except a.APIConnectionError as exc:
            raise AIError("unavailable") from exc

        if response.stop_reason == "refusal":
            raise AIError("refusal")
        if response.stop_reason == "max_tokens":
            raise AIError("truncated")
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage
        return LLMResponse(
            text=text,
            model=response.model,
            provider=self.name,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
        )


# ------------------------------------------------------------------------------------------ embedding
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.]*")


class HashingEmbeddingProvider:
    name = "hashing"

    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions
        self.model = f"hashing-v1-{dimensions}"

    def _features(self, text: str) -> list[tuple[str, float]]:
        tokens = [t.strip(".") for t in _TOKEN.findall(text.lower())]
        tokens = [t for t in tokens if len(t) > 1 or t in {"c", "r"}]
        feats: list[tuple[str, float]] = [(t, 1.0) for t in tokens]
        feats += [(f"{a}_{b}", 0.5) for a, b in itertools.pairwise(tokens)]
        return feats

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dimensions
            for feat, weight in self._features(text):
                digest = hashlib.blake2b(feat.encode(), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "little") % self.dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                vec[idx] += sign * weight
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class OpenAICompatibleEmbeddingProvider:
    name = "openai_compatible"

    def __init__(self) -> None:
        s = get_settings()
        self.model = s.embedding_model
        self.dimensions = s.embedding_dimensions
        self._base = (s.embedding_api_base or "").rstrip("/")
        self._key = s.embedding_api_key.get_secret_value() if s.embedding_api_key else None
        self._timeout = s.llm_timeout_seconds

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        from careerpilot.security.urls import assert_safe_outbound_url

        url = assert_safe_outbound_url(f"{self._base}/embeddings")
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        try:
            resp = httpx.post(
                url,
                json={"model": self.model, "input": texts},
                headers=headers,
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise AIError("timeout") from exc
        except httpx.HTTPError as exc:
            raise AIError("unavailable") from exc
        if resp.status_code == 429:
            raise AIError("rate_limited")
        if resp.status_code >= 400:
            raise AIError("provider_error")
        try:
            data = resp.json()["data"]
            vectors = [list(map(float, item["embedding"])) for item in data]
        except (KeyError, TypeError, ValueError) as exc:
            raise AIError("invalid_output") from exc
        if len(vectors) != len(texts):
            raise AIError("invalid_output")
        return vectors


# ------------------------------------------------------------------------------------------ factories
_llm: LLMProvider | None = None
_embedder: EmbeddingProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = AnthropicLLMProvider() if get_settings().llm_provider == "anthropic" else MockLLMProvider()
    return _llm


def get_embedding_provider() -> EmbeddingProvider:
    global _embedder
    if _embedder is None:
        s = get_settings()
        _embedder = (
            OpenAICompatibleEmbeddingProvider()
            if s.embedding_provider == "openai_compatible"
            else HashingEmbeddingProvider(s.embedding_dimensions)
        )
    return _embedder


def set_providers(llm: LLMProvider | None = None, embedder: EmbeddingProvider | None = None) -> None:
    global _llm, _embedder
    _llm, _embedder = llm, embedder
