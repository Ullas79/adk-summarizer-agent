"""
config.py — Centralised settings loaded from environment variables.
All Vertex AI / Cloud Run config lives here.
"""

from functools import lru_cache

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── Google Cloud ──────────────────────────────────────────────────────────
    google_cloud_project: str
    google_cloud_location: str = "us-central1"

    # ── ADK / Gemini ──────────────────────────────────────────────────────────
    # Tells google-genai SDK to route through Vertex AI instead of AI Studio
    google_genai_use_vertexai: str = "1"
    gemini_model: str = "gemini-2.5-flash"

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "adk-summarizer-agent"
    port: int = 8080
    log_level: str = "INFO"

    # ── Feature flags / runtime controls ─────────────────────────────────────
    max_input_chars: int = 50_000  # guard against runaway payloads
    summary_min_sentences: int = 3
    summary_max_sentences: int = 5
    cors_allow_origins: str = "*"  # "*" or comma-separated origins
    strict_json_output: bool = True  # fail request if model output is invalid JSON

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("port must be between 1 and 65535")
        return v

    @field_validator("max_input_chars")
    @classmethod
    def validate_max_input_chars(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_input_chars must be >= 1")
        return v

    @field_validator("summary_min_sentences", "summary_max_sentences")
    @classmethod
    def validate_sentence_bounds_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("summary sentence bounds must be >= 1")
        return v

    @field_validator("summary_max_sentences")
    @classmethod
    def validate_sentence_bounds_order(cls, v: int, info: ValidationInfo) -> int:
        min_val = info.data.get("summary_min_sentences")
        if min_val is not None and v < min_val:
            raise ValueError("summary_max_sentences must be >= summary_min_sentences")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        level = v.upper()
        if level not in allowed:
            raise ValueError(f"log_level must be one of: {', '.join(sorted(allowed))}")
        return level

    @field_validator("google_genai_use_vertexai")
    @classmethod
    def validate_vertex_flag(cls, v: str) -> str:
        normalized = v.strip()
        if normalized not in {"0", "1", "true", "false", "TRUE", "FALSE"}:
            raise ValueError(
                "google_genai_use_vertexai must be one of: 0, 1, true, false"
            )
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()