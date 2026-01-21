"""SQLAlchemy models for book series management.

Tables:
- series: Book series information
- series_books: Links books to series with position
"""

from datetime import datetime, timezone
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


class Series(Base):
    """Book series model."""

    __tablename__ = "series"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Series information
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    author: Mapped[Optional[str]] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Series metadata
    total_books: Mapped[Optional[int]] = mapped_column(Integer)  # Known total, if complete
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)  # Series finished by author
    genre: Mapped[Optional[str]] = mapped_column(String(100))

    # Reading status
    status: Mapped[str] = mapped_column(
        String(20), default="not_started", index=True
    )  # not_started, in_progress, completed, on_hold, abandoned

    # Progress tracking (calculated from series_books)
    books_owned: Mapped[int] = mapped_column(Integer, default=0)
    books_read: Mapped[int] = mapped_column(Integer, default=0)

    # Ratings
    average_rating: Mapped[Optional[float]] = mapped_column(Float)

    # External links
    goodreads_series_id: Mapped[Optional[str]] = mapped_column(String(50))
    goodreads_url: Mapped[Optional[str]] = mapped_column(String(500))

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
        return f"<Series(id={self.id}, name='{self.name}')>"

    @property
    def completion_percentage(self) -> float:
        """Calculate reading completion percentage."""
        if self.total_books and self.total_books > 0:
            return (self.books_read / self.total_books) * 100
        elif self.books_owned > 0:
            return (self.books_read / self.books_owned) * 100
        return 0.0

    @property
    def books_remaining(self) -> Optional[int]:
        """Get number of books left to read."""
        if self.total_books:
            return self.total_books - self.books_read
        return None

    @property
    def status_display(self) -> str:
        """Get display string for status."""
        statuses = {
            "not_started": "Not Started",
            "in_progress": "In Progress",
            "completed": "Completed",
            "on_hold": "On Hold",
            "abandoned": "Abandoned",
        }
        return statuses.get(self.status, "Unknown")


class SeriesBook(Base):
    """Link between a book and a series with position."""

    __tablename__ = "series_books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Foreign keys
    series_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    book_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Position in series
    position: Mapped[float] = mapped_column(
        Float, nullable=False, index=True
    )  # Float allows for 1.5, 2.5 (novellas, side stories)
    position_label: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # "Book 1", "Novella 1.5", "Prequel"

    # Book-specific series info
    is_main_series: Mapped[bool] = mapped_column(
        Boolean, default=True
    )  # vs spin-off, novella, etc.
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)  # Can be skipped

    # Reading status for this entry
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_owned: Mapped[bool] = mapped_column(Boolean, default=False)

    # Notes for this book in context of series
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
        return f"<SeriesBook(series_id={self.series_id}, book_id={self.book_id}, position={self.position})>"

    @property
    def position_display(self) -> str:
        """Get display string for position."""
        if self.position_label:
            return self.position_label
        # Format nicely - "1" instead of "1.0", "1.5" for novellas
        if self.position == int(self.position):
            return f"Book {int(self.position)}"
        return f"Book {self.position}"
