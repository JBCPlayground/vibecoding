"""SQLAlchemy models for book reviews.

Tables:
- reviews: Book reviews with ratings and text
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.models import Base, Book


def generate_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid4())


class Review(Base):
    """Review model - book reviews with ratings."""

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Book being reviewed
    book_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One review per book
        index=True,
    )

    # Rating (1-5 stars, supports half stars)
    rating: Mapped[Optional[float]] = mapped_column(Float)

    # Review text
    title: Mapped[Optional[str]] = mapped_column(String(200))
    content: Mapped[Optional[str]] = mapped_column(Text)

    # Review metadata
    review_date: Mapped[Optional[str]] = mapped_column(String(10))  # ISO date
    started_date: Mapped[Optional[str]] = mapped_column(String(10))  # When started reading
    finished_date: Mapped[Optional[str]] = mapped_column(String(10))  # When finished

    # Detailed ratings (optional, 1-5)
    plot_rating: Mapped[Optional[float]] = mapped_column(Float)
    characters_rating: Mapped[Optional[float]] = mapped_column(Float)
    writing_rating: Mapped[Optional[float]] = mapped_column(Float)
    pacing_rating: Mapped[Optional[float]] = mapped_column(Float)
    enjoyment_rating: Mapped[Optional[float]] = mapped_column(Float)

    # Flags
    contains_spoilers: Mapped[bool] = mapped_column(Boolean, default=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    would_recommend: Mapped[Optional[bool]] = mapped_column(Boolean)
    would_reread: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Tags for categorizing reviews
    tags: Mapped[Optional[str]] = mapped_column(Text)  # Comma-separated

    # Private notes (not for sharing)
    private_notes: Mapped[Optional[str]] = mapped_column(Text)

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
    book: Mapped["Book"] = relationship("Book")

    def __repr__(self) -> str:
        return f"<Review(id={self.id}, book_id={self.book_id}, rating={self.rating})>"

    @property
    def tag_list(self) -> list[str]:
        """Get tags as a list."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def has_detailed_ratings(self) -> bool:
        """Check if review has any detailed ratings."""
        return any([
            self.plot_rating,
            self.characters_rating,
            self.writing_rating,
            self.pacing_rating,
            self.enjoyment_rating,
        ])

    @property
    def average_detailed_rating(self) -> Optional[float]:
        """Calculate average of detailed ratings."""
        ratings = [r for r in [
            self.plot_rating,
            self.characters_rating,
            self.writing_rating,
            self.pacing_rating,
            self.enjoyment_rating,
        ] if r is not None]

        if not ratings:
            return None
        return sum(ratings) / len(ratings)

    @property
    def star_display(self) -> str:
        """Get star rating display string."""
        if self.rating is None:
            return "No rating"

        full_stars = int(self.rating)
        half_star = self.rating - full_stars >= 0.5
        empty_stars = 5 - full_stars - (1 if half_star else 0)

        return "★" * full_stars + ("½" if half_star else "") + "☆" * empty_stars
