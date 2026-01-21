"""SQLAlchemy models for reading locations."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.models import Base


def generate_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid4())


class ReadingLocation(Base):
    """A reading location (home, cafe, library, etc.)."""

    __tablename__ = "reading_locations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location_type: Mapped[str] = mapped_column(String(20), default="other", index=True)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    address: Mapped[Optional[str]] = mapped_column(String(200))
    icon: Mapped[Optional[str]] = mapped_column(String(50))
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: Mapped[str] = mapped_column(
        String(26),
        default=lambda: datetime.now(timezone.utc).isoformat(),
        onupdate=lambda: datetime.now(timezone.utc).isoformat(),
    )

    # Relationships
    sessions: Mapped[list["LocationSession"]] = relationship(
        "LocationSession", back_populates="location", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ReadingLocation(id={self.id}, name={self.name})>"

    @property
    def total_sessions(self) -> int:
        """Get total number of sessions at this location."""
        return len(self.sessions)

    @property
    def total_minutes(self) -> int:
        """Get total minutes read at this location."""
        return sum(s.minutes_read for s in self.sessions)

    @property
    def total_pages(self) -> int:
        """Get total pages read at this location."""
        return sum(s.pages_read for s in self.sessions)


class LocationSession(Base):
    """A reading session at a specific location."""

    __tablename__ = "location_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reading_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("books.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    minutes_read: Mapped[int] = mapped_column(Integer, nullable=False)
    pages_read: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Session date/time
    session_date: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat(), index=True
    )

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Relationships
    location: Mapped["ReadingLocation"] = relationship(
        "ReadingLocation", back_populates="sessions"
    )
    book: Mapped[Optional["Book"]] = relationship("Book")  # noqa: F821

    def __repr__(self) -> str:
        return f"<LocationSession(id={self.id}, location_id={self.location_id})>"

    @property
    def session_hour(self) -> int:
        """Get the hour of the session."""
        dt = datetime.fromisoformat(self.session_date)
        return dt.hour
