"""SQLAlchemy models for book lending.

Tables:
- contacts: People you lend to / borrow from
- loans: Individual loan records
"""

from datetime import datetime, timezone, date
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
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


class Contact(Base):
    """Contact model - people you lend to or borrow from."""

    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Statistics
    total_lent: Mapped[int] = mapped_column(Integer, default=0)
    total_borrowed: Mapped[int] = mapped_column(Integer, default=0)
    total_returned: Mapped[int] = mapped_column(Integer, default=0)
    total_unreturned: Mapped[int] = mapped_column(Integer, default=0)

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
    loans: Mapped[list["Loan"]] = relationship(
        "Loan", back_populates="contact", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Contact(id={self.id}, name='{self.name}')>"

    @property
    def active_loans(self) -> int:
        """Count of active loans."""
        return self.total_unreturned


class Loan(Base):
    """Loan model - tracks individual book loans."""

    __tablename__ = "loans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Book being lent/borrowed
    book_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Person lending to / borrowing from
    contact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Loan type: lent (you lent it out) or borrowed (you borrowed it)
    loan_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)

    # Dates
    loan_date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO date
    due_date: Mapped[Optional[str]] = mapped_column(String(10))  # ISO date
    return_date: Mapped[Optional[str]] = mapped_column(String(10))  # ISO date

    # Condition tracking
    condition_out: Mapped[Optional[str]] = mapped_column(String(50))
    condition_in: Mapped[Optional[str]] = mapped_column(String(50))

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Reminder settings
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_date: Mapped[Optional[str]] = mapped_column(String(10))

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
    contact: Mapped["Contact"] = relationship("Contact", back_populates="loans")

    def __repr__(self) -> str:
        return f"<Loan(id={self.id}, book_id={self.book_id}, type={self.loan_type}, status={self.status})>"

    @property
    def is_overdue(self) -> bool:
        """Check if loan is overdue."""
        if self.status != "active" or not self.due_date:
            return False
        return date.fromisoformat(self.due_date) < date.today()

    @property
    def days_until_due(self) -> Optional[int]:
        """Days until due (negative if overdue)."""
        if not self.due_date:
            return None
        due = date.fromisoformat(self.due_date)
        return (due - date.today()).days

    @property
    def days_overdue(self) -> int:
        """Days overdue (0 if not overdue)."""
        days = self.days_until_due
        if days is None or days >= 0:
            return 0
        return abs(days)

    @property
    def is_lent(self) -> bool:
        """Check if this is a lent book (you lent it to someone)."""
        return self.loan_type == "lent"

    @property
    def is_borrowed(self) -> bool:
        """Check if this is a borrowed book (you borrowed from someone)."""
        return self.loan_type == "borrowed"
