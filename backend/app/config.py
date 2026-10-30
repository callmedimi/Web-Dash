"""Central configuration using pydantic-settings.
Supports environment variables prefixed with WEBDASH_ with legacy fallbacks.
"""
import os
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEBDASH_",
        env_file=".env",
        extra="ignore",
    )

    env: str = Field(default="production")
    debug: bool = Field(default=False)
    data_dir: str = Field(default="./data")
    database_url: Optional[str] = Field(default=None)
    secret_key: Optional[str] = Field(default=None)
    max_ssh_workers: int = Field(default=20)
    job_event_retention_days: int = Field(default=30)
    read_only_mode: bool = Field(default=False)
    vault_key: Optional[str] = Field(default=None)

    def get_vault_key(self) -> Optional[str]:
        key = self.vault_key or os.environ.get("WEBDASH_VAULT_KEY") or os.environ.get("VAULT_KEY")
        if key:
            key_str = str(key).strip()
            if os.path.isfile(key_str):
                with open(key_str, "r", encoding="utf-8") as f:
                    return f.read().strip()
            return key_str
        return None

    def get_data_dir(self) -> str:
        if os.environ.get("WEBDASH_DATA_DIR"):
            data_dir = os.environ["WEBDASH_DATA_DIR"]
        elif os.environ.get("DATA_DIR"):
            data_dir = os.environ["DATA_DIR"]
        else:
            data_dir = self.data_dir or "./data"
        os.makedirs(data_dir, exist_ok=True)
        return os.path.abspath(data_dir)

    def get_database_url(self) -> str:
        # Check priority: self.database_url -> DATABASE_URL env var -> fallback SQLite
        url = self.database_url or os.environ.get("DATABASE_URL")
        if url:
            # Normalize postgres:// to postgresql+psycopg:// if needed
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg://", 1)
            elif url.startswith("postgresql://") and not (
                "psycopg" in url or "asyncpg" in url or "pg8000" in url
            ):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url

        # Default: SQLite in data_dir
        db_path = os.path.join(self.get_data_dir(), "webdash.db")
        return f"sqlite:///{db_path}"

    def is_sqlite(self) -> bool:
        return self.get_database_url().startswith("sqlite")


# Global singleton instance
settings = AppConfig()
