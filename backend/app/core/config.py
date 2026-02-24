from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Wishwave API"
    api_v1_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://wishlist:wishlist@localhost:5432/wishlist"

    jwt_secret: str = Field(default="change-me-in-production", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    default_currency: str = "RUB"
    default_min_contribution_cents: int = 100

    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/oauth/google/callback"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
