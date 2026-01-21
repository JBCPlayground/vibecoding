"""Configuration management for booktracker.

Loads configuration from environment variables and provides defaults.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


@dataclass
class Config:
    """Application configuration."""

    # Database
    db_path: Path

    # Notion
    notion_api_key: Optional[str]
    notion_database_id: Optional[str]
    notion_reading_logs_db_id: Optional[str]

    # Cache
    cache_ttl: int  # seconds

    # Sync
    sync_retry_max: int
    sync_retry_base_delay: float  # seconds

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        # Database path
        db_path_str = os.environ.get(
            "BOOKTRACKER_DB_PATH",
            str(Path.home() / "OneDrive" / "booktracker" / "books.db"),
        )
        db_path = Path(db_path_str).expanduser()

        return cls(
            db_path=db_path,
            notion_api_key=os.environ.get("NOTION_API_KEY"),
            notion_database_id=os.environ.get("NOTION_DATABASE_ID"),
            notion_reading_logs_db_id=os.environ.get("NOTION_READING_LOGS_DB_ID"),
            cache_ttl=int(os.environ.get("BOOKTRACKER_CACHE_TTL", "3600")),
            sync_retry_max=int(os.environ.get("BOOKTRACKER_SYNC_RETRY_MAX", "5")),
            sync_retry_base_delay=float(
                os.environ.get("BOOKTRACKER_SYNC_RETRY_DELAY", "1.0")
            ),
        )

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []

        # Check database directory is writable
        if not self.db_path.parent.exists():
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                errors.append(f"Cannot create database directory: {self.db_path.parent}")

        return errors

    def has_notion_config(self) -> bool:
        """Check if Notion configuration is present."""
        return bool(self.notion_api_key and self.notion_database_id)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global config instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config() -> None:
    """Reset the global config instance. Used for testing."""
    global _config
    _config = None
