"""SQLAlchemy models for reading streaks and habits.

Tables:
- reading_streaks: Track streak records
- daily_readings: Track daily reading activity
"""

from datetime import datetime, timezone, date
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db.models import Base


def generate_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid4())


class ReadingStreak(Base):
    """Reading streak model - tracks streak records."""

    __tablename__ = "reading_streaks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Streak dates
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO date
    end_date: Mapped[Optional[str]] = mapped_column(String(10))  # ISO date, None if active

    # Streak length
    length: Mapped[int] = mapped_column(Integer, default=1)

    # Status
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Stats during streak
    total_minutes: Mapped[int] = mapped_column(Integer, default=0)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    books_completed: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: Mapped[str] = mapped_column(
        String(26),
        default=lambda: datetime.now(timezone.utc).isoformat(),
        onupdate=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def __repr__(self) -> str:
        return f"<ReadingStreak(id={self.id}, length={self.length}, current={self.is_current})>"

    @property
    def is_active(self) -> bool:
        """Check if streak is currently active."""
        return self.is_current and self.end_date is None

    @property
    def average_daily_minutes(self) -> float:
        """Average minutes per day during streak."""
        if self.length == 0:
            return 0.0
        return self.total_minutes / self.length

    @property
    def average_daily_pages(self) -> float:
        """Average pages per day during streak."""
        if self.length == 0:
            return 0.0
        return self.total_pages / self.length


class DailyReading(Base):
    """Daily reading model - tracks daily reading activity."""

    __tablename__ = "daily_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Date of reading (unique per day)
    reading_date: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)

    # Reading stats
    minutes_read: Mapped[int] = mapped_column(Integer, default=0)
    pages_read: Mapped[int] = mapped_column(Integer, default=0)
    sessions_count: Mapped[int] = mapped_column(Integer, default=0)

    # Books touched/completed
    books_read: Mapped[int] = mapped_column(Integer, default=0)  # Books touched
    books_completed: Mapped[int] = mapped_column(Integer, default=0)

    # Goal tracking
    goal_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    goal_pages: Mapped[Optional[int]] = mapped_column(Integer)
    goal_met: Mapped[bool] = mapped_column(Boolean, default=False)

    # Time of day info (for habit analysis)
    primary_hour: Mapped[Optional[int]] = mapped_column(Integer)  # Most reading hour (0-23)
    weekday: Mapped[int] = mapped_column(Integer)  # 0=Monday, 6=Sunday

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: Mapped[str] = mapped_column(
        String(26),
        default=lambda: datetime.now(timezone.utc).isoformat(),
        onupdate=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def __repr__(self) -> str:
        return f"<DailyReading(date={self.reading_date}, minutes={self.minutes_read})>"

    @property
    def goal_progress(self) -> Optional[float]:
        """Progress toward daily goal (0-1+)."""
        if self.goal_minutes and self.goal_minutes > 0:
            return self.minutes_read / self.goal_minutes
        if self.goal_pages and self.goal_pages > 0:
            return self.pages_read / self.goal_pages
        return None

    @property
    def weekday_name(self) -> str:
        """Get weekday name."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return days[self.weekday] if 0 <= self.weekday <= 6 else "Unknown"
