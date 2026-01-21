"""Database models for user settings."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..db.models import Base


class Setting(Base):
    """Model for storing individual user settings."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    key: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[str] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(20))  # bool, int, str, enum
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("category", "key", name="uq_setting_category_key"),
    )


class SettingsBackup(Base):
    """Model for storing settings backups."""

    __tablename__ = "settings_backups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    settings_json: Mapped[str] = mapped_column(Text)  # Full settings as JSON
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
