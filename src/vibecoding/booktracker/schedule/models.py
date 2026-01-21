"""SQLAlchemy models for reading schedules and planning."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.models import Base


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid4())


class ReadingPlan(Base):
    """A reading plan with target dates and books."""

    __tablename__ = "reading_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    start_date: Mapped[Optional[str]] = mapped_column(String(10))  # ISO date
    end_date: Mapped[Optional[str]] = mapped_column(String(10))
    target_books: Mapped[Optional[int]] = mapped_column(Integer)
    target_pages: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now().isoformat()
    )
    updated_at: Mapped[Optional[str]] = mapped_column(String(30))

    # Relationships
    planned_books: Mapped[list["PlannedBook"]] = relationship(
        "PlannedBook", back_populates="plan", cascade="all, delete-orphan"
    )
    reminders: Mapped[list["Reminder"]] = relationship(
        "Reminder", back_populates="plan", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        """Check if plan is active."""
        return self.status == "active"

    @property
    def books_count(self) -> int:
        """Get count of books in plan."""
        return len(self.planned_books) if self.planned_books else 0


class PlannedBook(Base):
    """A book scheduled in a reading plan."""

    __tablename__ = "planned_books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reading_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=1, index=True)
    target_start_date: Mapped[Optional[str]] = mapped_column(String(10))
    target_end_date: Mapped[Optional[str]] = mapped_column(String(10))
    actual_start_date: Mapped[Optional[str]] = mapped_column(String(10))
    actual_end_date: Mapped[Optional[str]] = mapped_column(String(10))
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1-5, 1=highest
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now().isoformat()
    )

    # Relationships
    plan: Mapped["ReadingPlan"] = relationship("ReadingPlan", back_populates="planned_books")
    book: Mapped["Book"] = relationship("Book")

    @property
    def is_completed(self) -> bool:
        """Check if book is completed."""
        return self.actual_end_date is not None


# Import Book for relationship (avoid circular import)
from ..db.models import Book  # noqa: E402


class ScheduleEntry(Base):
    """A recurring reading schedule entry."""

    __tablename__ = "schedule_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), default="daily")
    days_of_week: Mapped[Optional[str]] = mapped_column(String(20))  # JSON list like "[0,2,4]"
    preferred_time: Mapped[Optional[str]] = mapped_column(String(8))  # HH:MM:SS
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    book_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now().isoformat()
    )

    # Relationships
    book: Mapped[Optional["Book"]] = relationship("Book")

    def get_days_of_week(self) -> list[int]:
        """Get days of week as list."""
        if not self.days_of_week:
            return []
        import json
        try:
            return json.loads(self.days_of_week)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_days_of_week(self, days: list[int]) -> None:
        """Set days of week from list."""
        import json
        self.days_of_week = json.dumps(days) if days else None


class Reminder(Base):
    """A reading reminder."""

    __tablename__ = "reading_reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    reminder_type: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(String(500))
    reminder_time: Mapped[str] = mapped_column(String(8), nullable=False)  # HH:MM:SS
    days_of_week: Mapped[Optional[str]] = mapped_column(String(20))  # JSON list
    book_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="SET NULL")
    )
    plan_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("reading_plans.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now().isoformat()
    )

    # Relationships
    book: Mapped[Optional["Book"]] = relationship("Book")
    plan: Mapped[Optional["ReadingPlan"]] = relationship("ReadingPlan", back_populates="reminders")

    def get_days_of_week(self) -> list[int]:
        """Get days of week as list."""
        if not self.days_of_week:
            return list(range(7))  # Default to every day
        import json
        try:
            return json.loads(self.days_of_week)
        except (json.JSONDecodeError, TypeError):
            return list(range(7))

    def set_days_of_week(self, days: list[int]) -> None:
        """Set days of week from list."""
        import json
        self.days_of_week = json.dumps(days) if days else None
