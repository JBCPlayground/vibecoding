"""SQLAlchemy models for wishlist management.

Tables:
- wishlist_items: Books to read (TBR list)
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


class WishlistItem(Base):
    """Wishlist item model - books to read."""

    __tablename__ = "wishlist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Book information (may not be in library yet)
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    author: Mapped[Optional[str]] = mapped_column(String(300))
    isbn: Mapped[Optional[str]] = mapped_column(String(20))

    # If book exists in library
    book_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)

    # Priority (1=highest, 5=lowest)
    priority: Mapped[int] = mapped_column(Integer, default=3, index=True)

    # Queue position (for ordering)
    position: Mapped[int] = mapped_column(Integer, default=0, index=True)

    # Source/recommendation
    source: Mapped[Optional[str]] = mapped_column(String(100))  # friend, blog, podcast, etc.
    recommended_by: Mapped[Optional[str]] = mapped_column(String(200))
    recommendation_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Why I want to read this
    reason: Mapped[Optional[str]] = mapped_column(Text)

    # Expected reading info
    estimated_pages: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float)
    genre: Mapped[Optional[str]] = mapped_column(String(100))

    # Dates
    date_added: Mapped[str] = mapped_column(
        String(10),
        default=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        index=True,
    )
    target_date: Mapped[Optional[str]] = mapped_column(String(10))  # When I want to read by

    # Status
    is_available: Mapped[bool] = mapped_column(Boolean, default=False)  # Own/have access
    is_on_hold: Mapped[bool] = mapped_column(Boolean, default=False)  # Library hold, etc.

    # Tags for categorization
    tags: Mapped[Optional[str]] = mapped_column(Text)  # Comma-separated

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
        return f"<WishlistItem(id={self.id}, title='{self.title}', priority={self.priority})>"

    @property
    def tag_list(self) -> list[str]:
        """Get tags as a list."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def priority_display(self) -> str:
        """Get priority as display string."""
        priorities = {
            1: "Must Read",
            2: "High",
            3: "Medium",
            4: "Low",
            5: "Someday",
        }
        return priorities.get(self.priority, "Unknown")

    @property
    def is_in_library(self) -> bool:
        """Check if book is already in library."""
        return self.book_id is not None

    @property
    def display_title(self) -> str:
        """Get display title with author."""
        if self.author:
            return f"{self.title} by {self.author}"
        return self.title
