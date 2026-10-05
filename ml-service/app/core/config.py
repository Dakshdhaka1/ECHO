from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ML_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    demo_mode: bool = True
    model_dir: Path = ML_ROOT / "artifacts"
    data_dir: Path = ML_ROOT.parent / "data"
    explanation_provider: str = "template"
    sec_user_agent: str = ""
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_enabled: bool = True
    alpha_vantage_api_key: str = ""
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5-5"
    news_window_days: int = 90
    http_timeout_seconds: float = 20.0
    monitoring_db: Path = ML_ROOT / "artifacts" / "monitoring" / "inference_log.sqlite"
    admin_token: str = ""

    @property
    def sample_dir(self) -> Path:
        return self.data_dir / "sample"


@lru_cache
def get_settings() -> Settings:
    return Settings()
