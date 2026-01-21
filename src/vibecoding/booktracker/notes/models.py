"""SQLAlchemy models for reading notes and quotes.

Tables:
- notes: Reading notes and annotations
- quotes: Memorable quotes and passages
"""

from datetime import datetime, timezone
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


class Note(Base):
    """Note model - reading notes and annotations."""

    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Book this note belongs to
    book_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Note type (thought, summary, question, insight, etc.)
    note_type: Mapped[str] = mapped_column(String(50), default="note", index=True)

    # Note content
    title: Mapped[Optional[str]] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Location in book (optional)
    chapter: Mapped[Optional[str]] = mapped_column(String(100))
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    location: Mapped[Optional[str]] = mapped_column(String(50))  # For e-books

    # Tags for categorization
    tags: Mapped[Optional[str]] = mapped_column(Text)  # Comma-separated

    # Flags
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
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
    book: Mapped["Book"] = relationship("Book")

    def __repr__(self) -> str:
        return f"<Note(id={self.id}, book_id={self.book_id}, type={self.note_type})>"

    @property
    def tag_list(self) -> list[str]:
        """Get tags as a list."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def short_content(self) -> str:
        """Get truncated content for display."""
        if len(self.content) <= 100:
            return self.content
        return self.content[:97] + "..."

    @property
    def location_display(self) -> str:
        """Get formatted location string."""
        parts = []
        if self.chapter:
            parts.append(f"Ch. {self.chapter}")
        if self.page_number:
            parts.append(f"p. {self.page_number}")
        if self.location:
            parts.append(f"loc. {self.location}")
        return ", ".join(parts) if parts else ""


class Quote(Base):
    """Quote model - memorable quotes and passages."""

    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Book this quote belongs to
    book_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Quote content
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Quote type: quote, highlight, excerpt, paraphrase
    quote_type: Mapped[str] = mapped_column(String(20), default="quote", index=True)

    # Highlight color: yellow, green, blue, pink, purple, orange
    color: Mapped[Optional[str]] = mapped_column(String(20))

    # Attribution (if different from book author)
    speaker: Mapped[Optional[str]] = mapped_column(String(200))  # Character name or narrator

    # Context or personal note about the quote
    context: Mapped[Optional[str]] = mapped_column(Text)

    # Location in book
    chapter: Mapped[Optional[str]] = mapped_column(String(100))
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    location: Mapped[Optional[str]] = mapped_column(String(50))

    # Tags for categorization
    tags: Mapped[Optional[str]] = mapped_column(Text)  # Comma-separated

    # Flags
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
    book: Mapped["Book"] = relationship("Book")

    def __repr__(self) -> str:
        return f"<Quote(id={self.id}, book_id={self.book_id})>"

    @property
    def tag_list(self) -> list[str]:
        """Get tags as a list."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def short_text(self) -> str:
        """Get truncated text for display."""
        if len(self.text) <= 100:
            return self.text
        return self.text[:97] + "..."

    @property
    def location_display(self) -> str:
        """Get formatted location string."""
        parts = []
        if self.chapter:
            parts.append(f"Ch. {self.chapter}")
        if self.page_number:
            parts.append(f"p. {self.page_number}")
        if self.location:
            parts.append(f"loc. {self.location}")
        return ", ".join(parts) if parts else ""

    @property
    def attribution(self) -> str:
        """Get attribution string."""
        if self.speaker:
            return f"— {self.speaker}"
        return ""


class QuoteCollection(Base):
    """Collection of quotes organized by theme."""

    __tablename__ = "quote_collections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    icon: Mapped[Optional[str]] = mapped_column(String(50))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

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
    quotes: Mapped[list["CollectionQuote"]] = relationship(
        "CollectionQuote", back_populates="collection", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<QuoteCollection(id={self.id}, name={self.name})>"

    @property
    def quote_count(self) -> int:
        """Get number of quotes in collection."""
        return len(self.quotes)


class CollectionQuote(Base):
    """Association between quotes and collections."""

    __tablename__ = "collection_quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    collection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("quote_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Relationships
    collection: Mapped["QuoteCollection"] = relationship(
        "QuoteCollection", back_populates="quotes"
    )
    quote: Mapped["Quote"] = relationship("Quote")

    def __repr__(self) -> str:
        return f"<CollectionQuote(collection_id={self.collection_id}, quote_id={self.quote_id})>"
