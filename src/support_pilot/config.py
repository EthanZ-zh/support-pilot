from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def is_beijing_qwen_base_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = parsed.hostname or ""
    allowed_host = hostname == "dashscope.aliyuncs.com" or hostname.endswith(
        ".cn-beijing.maas.aliyuncs.com"
    )
    return (
        parsed.scheme == "https"
        and allowed_host
        and parsed.path.rstrip("/") == "/compatible-mode/v1"
        and not parsed.query
        and not parsed.fragment
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SUPPORT_PILOT_",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "SupportPilot"
    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://support_pilot:support_pilot@localhost:54329/support_pilot"
    )
    agent_provider: str = "deterministic"
    jwt_secret: SecretStr | None = None
    jwt_issuer: str = "support-pilot"
    jwt_audience: str = "support-pilot-api"
    jwt_access_token_minutes: int = Field(default=30, ge=5, le=1440)
    allow_legacy_user_header: bool = False
    otel_enabled: bool = False
    otel_service_name: str = "support-pilot-api"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318/v1/traces"
    agent_max_attempts: int = Field(default=2, ge=1, le=3)
    qwen_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUPPORT_PILOT_QWEN_API_KEY",
            "DASHSCOPE_API_KEY",
        ),
    )
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.7-plus"
    qwen_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    qwen_enable_thinking: bool = False
    qwen_input_price_per_million_cny: float = Field(default=2.0, ge=0.0)
    qwen_output_price_per_million_cny: float = Field(default=8.0, ge=0.0)
    retrieval_provider: str = "deterministic"
    model_cache_dir: Path = Path("D:/model-cache/support-pilot/huggingface")
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"

    @field_validator("agent_provider")
    @classmethod
    def validate_agent_provider(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"deterministic", "qwen"}:
            raise ValueError("agent_provider must be 'deterministic' or 'qwen'")
        return normalized

    @field_validator("qwen_base_url")
    @classmethod
    def validate_qwen_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not is_beijing_qwen_base_url(normalized):
            raise ValueError("qwen_base_url must be a Beijing Model Studio compatible endpoint")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
