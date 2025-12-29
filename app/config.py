"""Application configuration using Pydantic Settings."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App Configuration
    app_name: str = "Alima"
    secret_key: str = ""
    domain: str = "http://localhost:8000"
    environment: str = "development"

    # Database
    database_url: str = "sqlite:///data/db/alima.db"

    # Paths
    audiobooks_path: Path = Path("/app/data/audiobooks")
    covers_path: Path = Path("/app/data/covers")
    audible_auth_path: Path = Path("/app/data/audible_auth")
    temp_path: Path = Path("/app/data/temp")

    # Email (optional)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    # Sync Settings
    sync_interval_hours: int = 6
    download_quality: Literal["High", "Normal"] = "High"
    max_concurrent_downloads: int = 3

    # Session
    session_expire_hours: int = 12410  # 365 days
    invite_expire_days: int = 7

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
