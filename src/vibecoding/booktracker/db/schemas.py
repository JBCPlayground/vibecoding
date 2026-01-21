"""Pydantic schemas for data validation.

These schemas define the structure for book data across all sources
(Notion, Calibre, Goodreads) with a unified output schema.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class BookStatus(str, Enum):
    """Unified status enum across all sources."""

    READING = "reading"
    COMPLETED = "completed"
    SKIMMED = "skimmed"
    ON_HOLD = "on_hold"  # Library hold
    WISHLIST = "wishlist"  # Want to read
    DNF = "dnf"  # Did not finish
    OWNED = "owned"  # In Calibre library, not yet read


class BookSource(str, Enum):
    """Source of book data."""

    NOTION = "notion"
    CALIBRE = "calibre"
    GOODREADS = "goodreads"
    MANUAL = "manual"
    OPENLIBRARY = "openlibrary"


class SyncStatus(str, Enum):
    """Status of sync queue items."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICT = "conflict"


class SyncOperation(str, Enum):
    """Type of sync operation."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


# ============================================================================
# Base Schemas
# ============================================================================


class BookBase(BaseModel):
    """Base book fields common to create/update operations."""

    # Core fields
    title: str = Field(..., min_length=1, description="Book title")
    title_sort: Optional[str] = Field(None, description="Title for sorting")
    author: str = Field(..., min_length=1, description="Primary author")
    author_sort: Optional[str] = Field(None, description="Author name (Last, First)")
    status: BookStatus = Field(default=BookStatus.WISHLIST)
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating 1-5")

    # Dates
    date_added: Optional[date] = None
    date_started: Optional[date] = None
    date_finished: Optional[date] = None

    # Identifiers
    isbn: Optional[str] = Field(None, max_length=13)
    isbn13: Optional[str] = Field(None, max_length=13)

    # Metadata
    page_count: Optional[int] = Field(None, ge=0)
    description: Optional[str] = None
    cover: Optional[str] = Field(None, description="Cover image URL or base64")
    cover_base64: Optional[str] = Field(None, description="Cover as base64 for offline")
    publisher: Optional[str] = None
    tags: Optional[list[str]] = Field(default_factory=list)

    # Series
    series: Optional[str] = None
    series_index: Optional[float] = None

    # Publication
    publication_date: Optional[date] = None
    publication_year: Optional[int] = None
    original_publication_year: Optional[int] = None
    language: Optional[str] = None

    # Format
    format: Optional[str] = Field(None, description="Binding: Kindle, Paperback, etc.")
    file_formats: Optional[list[str]] = Field(default_factory=list, description="epub, mobi, etc.")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    library_source: Optional[str] = Field(None, description="Calibre Library, Public Library")

    # Notion-specific
    amazon_url: Optional[str] = None
    goodreads_url: Optional[str] = None
    library_url: Optional[str] = None
    comments: Optional[str] = None
    progress: Optional[str] = Field(None, description="Reading progress e.g. '33%'")
    read_next: bool = False
    recommended_by: Optional[str] = None
    genres: Optional[list[str]] = Field(default_factory=list)

    # Goodreads-specific
    goodreads_id: Optional[int] = None
    additional_authors: Optional[str] = None
    goodreads_avg_rating: Optional[float] = None
    goodreads_shelves: Optional[str] = None
    goodreads_shelf_positions: Optional[str] = None
    review: Optional[str] = None
    review_spoiler: Optional[str] = None
    notes: Optional[str] = None
    read_count: Optional[int] = Field(None, ge=0)
    owned_copies: Optional[int] = Field(None, ge=0)

    # Calibre-specific
    calibre_id: Optional[int] = None
    calibre_uuid: Optional[str] = None
    calibre_library: Optional[str] = None
    identifiers: Optional[dict[str, str]] = Field(default_factory=dict)
    custom_text: Optional[str] = None

    # Library tracking
    library_hold_date: Optional[date] = None
    library_due_date: Optional[date] = None
    pickup_location: Optional[str] = None
    renewals: Optional[int] = Field(None, ge=0)

    @field_validator("isbn", "isbn13", mode="before")
    @classmethod
    def clean_isbn(cls, v: Optional[str]) -> Optional[str]:
        """Clean ISBN values (strip Goodreads ="" wrapper)."""
        if v is None:
            return None
        v = str(v).strip()
        # Handle Goodreads format: ="0385350597"
        if v.startswith('="') and v.endswith('"'):
            v = v[2:-1]
        # Remove any remaining quotes
        v = v.strip('"').strip("'")
        return v if v else None

    @field_validator("rating", mode="before")
    @classmethod
    def normalize_rating(cls, v) -> Optional[int]:
        """Normalize rating to 1-5 scale."""
        if v is None or v == 0:
            return None
        v = int(v)
        # Handle Calibre 0-10 scale
        if v > 5:
            v = max(1, min(5, v // 2))
        return v


class BookCreate(BookBase):
    """Schema for creating a new book."""

    sources: list[BookSource] = Field(default_factory=lambda: [BookSource.MANUAL])
    source_ids: dict[str, str] = Field(default_factory=dict)


class BookUpdate(BaseModel):
    """Schema for updating an existing book. All fields optional."""

    title: Optional[str] = Field(None, min_length=1)
    title_sort: Optional[str] = None
    author: Optional[str] = Field(None, min_length=1)
    author_sort: Optional[str] = None
    status: Optional[BookStatus] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    date_added: Optional[date] = None
    date_started: Optional[date] = None
    date_finished: Optional[date] = None
    isbn: Optional[str] = None
    isbn13: Optional[str] = None
    page_count: Optional[int] = Field(None, ge=0)
    description: Optional[str] = None
    cover: Optional[str] = None
    cover_base64: Optional[str] = None
    publisher: Optional[str] = None
    tags: Optional[list[str]] = None
    series: Optional[str] = None
    series_index: Optional[float] = None
    publication_date: Optional[date] = None
    publication_year: Optional[int] = None
    original_publication_year: Optional[int] = None
    language: Optional[str] = None
    format: Optional[str] = None
    file_formats: Optional[list[str]] = None
    file_size: Optional[int] = None
    library_source: Optional[str] = None
    amazon_url: Optional[str] = None
    goodreads_url: Optional[str] = None
    library_url: Optional[str] = None
    comments: Optional[str] = None
    progress: Optional[str] = None
    read_next: Optional[bool] = None
    recommended_by: Optional[str] = None
    genres: Optional[list[str]] = None
    goodreads_id: Optional[int] = None
    additional_authors: Optional[str] = None
    goodreads_avg_rating: Optional[float] = None
    goodreads_shelves: Optional[str] = None
    goodreads_shelf_positions: Optional[str] = None
    review: Optional[str] = None
    review_spoiler: Optional[str] = None
    notes: Optional[str] = None
    read_count: Optional[int] = None
    owned_copies: Optional[int] = None
    calibre_id: Optional[int] = None
    calibre_uuid: Optional[str] = None
    calibre_library: Optional[str] = None
    identifiers: Optional[dict[str, str]] = None
    custom_text: Optional[str] = None
    library_hold_date: Optional[date] = None
    library_due_date: Optional[date] = None
    pickup_location: Optional[str] = None
    renewals: Optional[int] = None


class BookResponse(BookBase):
    """Schema for book responses (includes DB-generated fields)."""

    id: UUID
    sources: list[BookSource] = Field(default_factory=list)
    source_ids: dict[str, str] = Field(default_factory=dict)
    import_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    local_modified_at: datetime
    notion_modified_at: Optional[datetime] = None
    notion_page_id: Optional[str] = None

    model_config = {"from_attributes": True}


# ============================================================================
# Reading Log Schemas
# ============================================================================


class ReadingLogBase(BaseModel):
    """Base reading log fields."""

    book_id: UUID
    date: date
    pages_read: Optional[int] = Field(None, ge=0)
    start_page: Optional[int] = Field(None, ge=0)
    end_page: Optional[int] = Field(None, ge=0)
    duration_minutes: Optional[int] = Field(None, ge=0)
    location: Optional[str] = Field(None, description="home, commute, vacation, etc.")
    notes: Optional[str] = None


class ReadingLogCreate(ReadingLogBase):
    """Schema for creating a reading log entry."""

    pass


class ReadingLogResponse(ReadingLogBase):
    """Schema for reading log responses."""

    id: UUID
    created_at: datetime
    notion_page_id: Optional[str] = None

    model_config = {"from_attributes": True}


# ============================================================================
# Sync Queue Schemas
# ============================================================================


class SyncQueueItemBase(BaseModel):
    """Base sync queue item fields."""

    entity_type: str = Field(..., description="book or reading_log")
    entity_id: UUID
    operation: SyncOperation
    payload: Optional[dict] = None


class SyncQueueItemCreate(SyncQueueItemBase):
    """Schema for creating a sync queue item."""

    pass


class SyncQueueItemResponse(SyncQueueItemBase):
    """Schema for sync queue item responses."""

    id: UUID
    status: SyncStatus
    retry_count: int = 0
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
