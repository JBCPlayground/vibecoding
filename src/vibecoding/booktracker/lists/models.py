"""SQLAlchemy models for reading lists.

Tables:
- reading_lists: User-created reading lists
- reading_list_books: Books in reading lists
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db.models import Base


def generate_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid4())


class ReadingList(Base):
    """User-created reading list."""

    __tablename__ = "reading_lists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # List information
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # List type
    list_type: Mapped[str] = mapped_column(
        String(20), default="custom", index=True
    )  # custom, seasonal, themed, auto

    # Auto-list configuration (for auto-generated lists)
    auto_criteria: Mapped[Optional[str]] = mapped_column(Text)  # JSON criteria for auto lists

    # Display settings
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    color: Mapped[Optional[str]] = mapped_column(String(20))  # For UI display
    icon: Mapped[Optional[str]] = mapped_column(String(50))  # Emoji or icon name

    # Metadata
    book_count: Mapped[int] = mapped_column(Integer, default=0)

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
        return f"<ReadingList(id={self.id}, name='{self.name}')>"

    @property
    def is_auto(self) -> bool:
        """Check if this is an auto-generated list."""
        return self.list_type == "auto"

    @property
    def type_display(self) -> str:
        """Get display string for list type."""
        types = {
            "custom": "Custom",
            "seasonal": "Seasonal",
            "themed": "Themed",
            "auto": "Auto-Generated",
        }
        return types.get(self.list_type, "Custom")


class ReadingListBook(Base):
    """Book in a reading list with position."""

    __tablename__ = "reading_list_books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Foreign keys
    list_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    book_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Position in list
    position: Mapped[int] = mapped_column(Integer, default=0, index=True)

    # Optional note about why this book is in the list
    note: Mapped[Optional[str]] = mapped_column(Text)

    # Date added to list
    added_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __repr__(self) -> str:
        return f"<ReadingListBook(list_id={self.list_id}, book_id={self.book_id})>"
