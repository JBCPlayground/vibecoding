"""SQLAlchemy ORM models for local SQLite database.

Tables:
- books: Main book records
- reading_logs: Individual reading session entries
- sync_queue: Pending sync operations to Notion
"""

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .schemas import BookSource, BookStatus, SyncOperation, SyncStatus


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


def generate_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid4())


class Book(Base):
    """Book model - stores all book data from unified schema."""

    __tablename__ = "books"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Core fields
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    title_sort: Mapped[Optional[str]] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    author_sort: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(20), default=BookStatus.WISHLIST.value, index=True
    )
    rating: Mapped[Optional[int]] = mapped_column(Integer)

    # Dates
    date_added: Mapped[Optional[str]] = mapped_column(String(10))  # ISO date
    date_started: Mapped[Optional[str]] = mapped_column(String(10))
    date_finished: Mapped[Optional[str]] = mapped_column(String(10))

    # Identifiers
    isbn: Mapped[Optional[str]] = mapped_column(String(13), index=True)
    isbn13: Mapped[Optional[str]] = mapped_column(String(13), index=True)

    # Metadata
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(Text)
    cover: Mapped[Optional[str]] = mapped_column(Text)  # URL
    cover_base64: Mapped[Optional[str]] = mapped_column(Text)  # Base64 encoded
    publisher: Mapped[Optional[str]] = mapped_column(String(500))
    tags: Mapped[Optional[str]] = mapped_column(Text)  # JSON array

    # Series
    series: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    series_index: Mapped[Optional[float]] = mapped_column(Float)

    # Publication
    publication_date: Mapped[Optional[str]] = mapped_column(String(10))
    publication_year: Mapped[Optional[int]] = mapped_column(Integer)
    original_publication_year: Mapped[Optional[int]] = mapped_column(Integer)
    language: Mapped[Optional[str]] = mapped_column(String(10))

    # Format
    format: Mapped[Optional[str]] = mapped_column(String(50))
    file_formats: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    library_source: Mapped[Optional[str]] = mapped_column(String(100))

    # Notion-specific
    amazon_url: Mapped[Optional[str]] = mapped_column(Text)
    goodreads_url: Mapped[Optional[str]] = mapped_column(Text)
    library_url: Mapped[Optional[str]] = mapped_column(Text)
    comments: Mapped[Optional[str]] = mapped_column(Text)
    progress: Mapped[Optional[str]] = mapped_column(String(20))
    read_next: Mapped[bool] = mapped_column(Boolean, default=False)
    recommended_by: Mapped[Optional[str]] = mapped_column(String(200))
    genres: Mapped[Optional[str]] = mapped_column(Text)  # JSON array

    # Goodreads-specific
    goodreads_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    additional_authors: Mapped[Optional[str]] = mapped_column(Text)
    goodreads_avg_rating: Mapped[Optional[float]] = mapped_column(Float)
    goodreads_shelves: Mapped[Optional[str]] = mapped_column(Text)
    goodreads_shelf_positions: Mapped[Optional[str]] = mapped_column(Text)
    review: Mapped[Optional[str]] = mapped_column(Text)
    review_spoiler: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    read_count: Mapped[Optional[int]] = mapped_column(Integer)
    owned_copies: Mapped[Optional[int]] = mapped_column(Integer)

    # Calibre-specific
    calibre_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    calibre_uuid: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    calibre_library: Mapped[Optional[str]] = mapped_column(String(200))
    identifiers: Mapped[Optional[str]] = mapped_column(Text)  # JSON dict
    custom_text: Mapped[Optional[str]] = mapped_column(Text)

    # Library tracking
    library_hold_date: Mapped[Optional[str]] = mapped_column(String(10))
    library_due_date: Mapped[Optional[str]] = mapped_column(String(10))
    pickup_location: Mapped[Optional[str]] = mapped_column(String(200))
    renewals: Mapped[Optional[int]] = mapped_column(Integer)

    # Source tracking
    sources: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of BookSource
    source_ids: Mapped[Optional[str]] = mapped_column(Text)  # JSON dict
    import_date: Mapped[Optional[str]] = mapped_column(String(26))  # ISO datetime

    # Sync tracking
    notion_page_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    local_modified_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )
    notion_modified_at: Mapped[Optional[str]] = mapped_column(String(26))

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
    reading_logs: Mapped[list["ReadingLog"]] = relationship(
        "ReadingLog", back_populates="book", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Book(id={self.id}, title='{self.title}', author='{self.author}')>"

    # Helper methods for JSON fields
    def get_tags(self) -> list[str]:
        """Get tags as list."""
        if self.tags:
            return json.loads(self.tags)
        return []

    def set_tags(self, tags: list[str]) -> None:
        """Set tags from list."""
        self.tags = json.dumps(tags) if tags else None

    def get_sources(self) -> list[str]:
        """Get sources as list."""
        if self.sources:
            return json.loads(self.sources)
        return []

    def set_sources(self, sources: list[str]) -> None:
        """Set sources from list."""
        self.sources = json.dumps(sources) if sources else None

    def get_source_ids(self) -> dict[str, str]:
        """Get source_ids as dict."""
        if self.source_ids:
            return json.loads(self.source_ids)
        return {}

    def set_source_ids(self, source_ids: dict[str, str]) -> None:
        """Set source_ids from dict."""
        self.source_ids = json.dumps(source_ids) if source_ids else None

    def get_identifiers(self) -> dict[str, str]:
        """Get identifiers as dict."""
        if self.identifiers:
            return json.loads(self.identifiers)
        return {}

    def set_identifiers(self, identifiers: dict[str, str]) -> None:
        """Set identifiers from dict."""
        self.identifiers = json.dumps(identifiers) if identifiers else None

    def get_file_formats(self) -> list[str]:
        """Get file_formats as list."""
        if self.file_formats:
            return json.loads(self.file_formats)
        return []

    def set_file_formats(self, formats: list[str]) -> None:
        """Set file_formats from list."""
        self.file_formats = json.dumps(formats) if formats else None

    def get_genres(self) -> list[str]:
        """Get genres as list."""
        if self.genres:
            return json.loads(self.genres)
        return []

    def set_genres(self, genres: list[str]) -> None:
        """Set genres from list."""
        self.genres = json.dumps(genres) if genres else None


class ReadingLog(Base):
    """Reading log model - tracks individual reading sessions."""

    __tablename__ = "reading_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # ISO date
    pages_read: Mapped[Optional[int]] = mapped_column(Integer)
    start_page: Mapped[Optional[int]] = mapped_column(Integer)
    end_page: Mapped[Optional[int]] = mapped_column(Integer)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    location: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Sync tracking
    notion_page_id: Mapped[Optional[str]] = mapped_column(String(36))

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book", back_populates="reading_logs")

    def __repr__(self) -> str:
        return f"<ReadingLog(id={self.id}, book_id={self.book_id}, date={self.date})>"


class SyncQueueItem(Base):
    """Sync queue item - tracks pending sync operations to Notion."""

    __tablename__ = "sync_queue"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)  # book, reading_log
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(10), nullable=False)  # create, update, delete
    status: Mapped[str] = mapped_column(
        String(20), default=SyncStatus.PENDING.value, index=True
    )
    payload: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

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
        return f"<SyncQueueItem(id={self.id}, entity={self.entity_type}/{self.entity_id}, op={self.operation})>"

    def get_payload(self) -> Optional[dict]:
        """Get payload as dict."""
        if self.payload:
            return json.loads(self.payload)
        return None

    def set_payload(self, payload: dict) -> None:
        """Set payload from dict."""
        self.payload = json.dumps(payload) if payload else None
