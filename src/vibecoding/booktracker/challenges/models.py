"""SQLAlchemy models for reading challenges.

Tables:
- challenges: Reading challenge definitions
- challenge_books: Books counted toward challenges
"""

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.models import Base, Book


def generate_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid4())


class Challenge(Base):
    """Challenge model - stores reading challenge definitions."""

    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Challenge type: books, pages, or custom
    challenge_type: Mapped[str] = mapped_column(String(20), default="books")

    # Target and current progress
    target: Mapped[int] = mapped_column(Integer, nullable=False)
    current: Mapped[int] = mapped_column(Integer, default=0)

    # Time period
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO date
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO date

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active")

    # Optional criteria (JSON) for filtering which books count
    criteria: Mapped[Optional[str]] = mapped_column(Text)

    # Auto-count books or manual tracking
    auto_count: Mapped[bool] = mapped_column(Boolean, default=True)

    # Display settings
    icon: Mapped[Optional[str]] = mapped_column(String(50))
    color: Mapped[Optional[str]] = mapped_column(String(20))

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: Mapped[str] = mapped_column(
        String(26),
        default=lambda: datetime.now(timezone.utc).isoformat(),
        onupdate=lambda: datetime.now(timezone.utc).isoformat(),
    )
    completed_at: Mapped[Optional[str]] = mapped_column(String(26))

    # Relationships
    challenge_books: Mapped[list["ChallengeBook"]] = relationship(
        "ChallengeBook", back_populates="challenge", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Challenge(id={self.id}, name='{self.name}', {self.current}/{self.target})>"

    def get_criteria(self) -> Optional[dict]:
        """Get criteria as dict."""
        if self.criteria:
            return json.loads(self.criteria)
        return None

    def set_criteria(self, criteria: dict) -> None:
        """Set criteria from dict."""
        self.criteria = json.dumps(criteria) if criteria else None

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.target <= 0:
            return 0.0
        return min(100.0, (self.current / self.target) * 100)

    @property
    def is_complete(self) -> bool:
        """Check if challenge is complete."""
        return self.current >= self.target

    @property
    def is_active(self) -> bool:
        """Check if challenge is currently active."""
        if self.status != "active":
            return False
        today = datetime.now().date().isoformat()
        return self.start_date <= today <= self.end_date

    @property
    def days_remaining(self) -> int:
        """Calculate days remaining in challenge."""
        from datetime import date

        today = date.today()
        end = date.fromisoformat(self.end_date)
        delta = (end - today).days
        return max(0, delta)

    @property
    def remaining(self) -> int:
        """Calculate remaining items to reach target."""
        return max(0, self.target - self.current)


class ChallengeBook(Base):
    """Association table for challenge-book relationship."""

    __tablename__ = "challenge_books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    challenge_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("challenges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # When the book was counted toward the challenge
    counted_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Value contributed (1 for books, page count for pages, etc.)
    value: Mapped[int] = mapped_column(Integer, default=1)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    challenge: Mapped["Challenge"] = relationship(
        "Challenge", back_populates="challenge_books"
    )
    book: Mapped["Book"] = relationship("Book")

    # Unique constraint: a book can only count once per challenge
    __table_args__ = (
        UniqueConstraint("challenge_id", "book_id", name="uq_challenge_book"),
    )

    def __repr__(self) -> str:
        return f"<ChallengeBook(challenge_id={self.challenge_id}, book_id={self.book_id})>"
