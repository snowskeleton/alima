"""Application configuration using Pydantic Settings."""

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App Configuration
    app_name: str = "Alima"
    secret_key: str = ""
    domain: str = "http://localhost:8000"
    environment: str = "development"

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Ensure SECRET_KEY is set and meets minimum security requirements."""
        if not v or len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long. "
                "Set the SECRET_KEY environment variable with a strong random key. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        return v

    # Database
    # Plain "postgresql://" resolves to psycopg2, which is what requirements.txt
    # pins. Do not use "postgresql+psycopg://" (psycopg 3) here unless psycopg is
    # added to requirements.txt — it is not installed in the Docker image, so the
    # fallback would fail at startup whenever DATABASE_URL is unset.
    database_url: str = "postgresql://alima:changeme@postgres:5432/alima"

    # Paths
    audiobooks_path: Path = Path("/app/data/audiobooks")
    covers_path: Path = Path("/app/data/covers")
    audible_auth_path: Path = Path("/app/data/audible_auth")
    temp_path: Path = Path("/app/data/temp")

    # Note: Email, sync, and session settings should be configured via
    # Admin → Server Settings. These are not read from .env.

    # Replication Mode
    replication_mode: Literal["standalone", "master", "slave"] = "standalone"

    # Master Configuration (for slave instances)
    master_url: str | None = None
    master_api_key: str | None = None

    # Slave Configuration (for master instances)
    slave_instances: str | None = None  # Comma-separated URLs

    # Replication Sync Settings
    replication_sync_interval_minutes: int = 15
    replication_method: Literal["http", "rsync"] = "http"

    # Optional: rsync configuration
    rsync_user: str | None = None
    rsync_host: str | None = None
    rsync_path: str | None = None

    # Backblaze B2 Storage
    b2_enabled: bool = False
    b2_bucket_name: str | None = None
    b2_endpoint_url: str | None = None  # https://{accountId}.s3.{region}.backblazeb2.com
    b2_access_key_id: str | None = None
    b2_secret_access_key: str | None = None
    b2_signed_url_ttl_seconds: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def get_slave_urls(self) -> list[str]:
        """Parse comma-separated slave instances into a list."""
        if not self.slave_instances:
            return []
        return [url.strip() for url in self.slave_instances.split(",")]


# Global settings instance
settings = Settings()
