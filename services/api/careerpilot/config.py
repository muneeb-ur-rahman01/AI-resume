"""Typed, validated configuration loaded from environment variables.

All secrets come from the environment (or a secret manager that injects env vars).
Unsafe combinations are rejected at startup for staging/production.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]

_INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me"  # noqa: S105 - documented placeholder


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- application ---
    app_name: str = "CareerPilot AI"
    environment: Environment = "development"
    debug: bool = False
    secret_key: SecretStr = SecretStr(_INSECURE_DEFAULT_SECRET)
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    log_level: str = "INFO"
    max_request_body_mb: int = 12

    # --- database / cache ---
    database_url: str = "postgresql+psycopg://careerpilot:careerpilot@localhost:5432/careerpilot"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    redis_url: str | None = None

    # --- sessions / cookies ---
    session_cookie_name: str = "cp_session"
    csrf_cookie_name: str = "cp_csrf"
    session_ttl_hours: int = 24 * 7
    session_idle_timeout_hours: int = 24
    cookie_secure: bool = False
    email_verification_ttl_minutes: int = 60 * 24
    password_reset_ttl_minutes: int = 30
    login_max_failures: int = 10
    login_lockout_minutes: int = 15

    # --- background tasks ---
    # inline: run tasks synchronously in-process (dev/test); celery: enqueue to Redis broker.
    task_mode: Literal["inline", "celery"] = "inline"

    # --- email ---
    email_provider: Literal["console", "smtp"] = "console"
    email_from: str = "CareerPilot AI <no-reply@careerpilot.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False

    # --- object storage ---
    storage_provider: Literal["local", "s3"] = "local"
    local_storage_path: str = "./.data/storage"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "careerpilot-private"
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    signed_url_ttl_seconds: int = 300
    max_upload_mb: int = 10

    # --- document processing ---
    ocr_provider: Literal["none", "tesseract"] = "none"
    malware_scanner: Literal["none", "clamav"] = "none"
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    min_text_chars_before_ocr: int = 200
    max_pdf_pages: int = 30

    # --- AI providers ---
    llm_provider: Literal["mock", "anthropic"] = "mock"
    llm_model: str = "claude-opus-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_fallbacks: Literal["default", "off"] = "default"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    llm_max_output_tokens: int = 16000
    llm_max_input_chars: int = 40000
    llm_max_concurrency: int = 4
    llm_input_cost_per_mtok: float = 4.0
    llm_output_cost_per_mtok: float = 20.0
    anthropic_api_key: SecretStr | None = None
    allow_mock_ai_in_production: bool = False

    embedding_provider: Literal["hashing", "openai_compatible"] = "hashing"
    embedding_model: str = "hashing-v1"
    embedding_dimensions: int = 512
    embedding_api_base: str | None = None
    embedding_api_key: SecretStr | None = None

    reranker_provider: Literal["none"] = "none"

    # --- product policy ---
    require_verified_company_to_publish: bool = True
    job_moderation_enabled: bool = False
    auto_verify_company_domain_match: bool = False
    recommendation_limit: int = 20
    retrieval_candidate_pool: int = 200

    @model_validator(mode="after")
    def _check_production_safety(self) -> Settings:
        if self.environment in ("staging", "production"):
            problems: list[str] = []
            if (
                self.secret_key.get_secret_value() == _INSECURE_DEFAULT_SECRET
                or len(self.secret_key.get_secret_value()) < 32
            ):
                problems.append("SECRET_KEY must be set to a random value of at least 32 characters")
            if self.debug:
                problems.append("DEBUG must be false")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true")
            if self.llm_provider == "mock" and not self.allow_mock_ai_in_production:
                problems.append("LLM_PROVIDER=mock is not allowed outside development/test")
            if self.email_provider == "console":
                problems.append("EMAIL_PROVIDER=console is not allowed outside development/test")
            if self.storage_provider == "local" and self.environment == "production":
                problems.append("STORAGE_PROVIDER=local is not allowed in production")
            if problems:
                raise ValueError("Unsafe configuration: " + "; ".join(problems))
        if self.llm_provider == "anthropic" and self.anthropic_api_key is None:
            # The SDK can also resolve credentials from other sources; we require the explicit key so that
            # misconfiguration is detected at startup instead of on the first resume upload.
            raise ValueError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        if self.embedding_provider == "openai_compatible" and not self.embedding_api_base:
            raise ValueError("EMBEDDING_PROVIDER=openai_compatible requires EMBEDDING_API_BASE")
        return self

    @property
    def is_production_like(self) -> bool:
        return self.environment in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
