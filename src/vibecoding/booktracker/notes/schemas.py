"""Pydantic schemas for reading notes and quotes."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NoteType(str, Enum):
    """Types of notes."""

    NOTE = "note"  # General note
    THOUGHT = "thought"  # Personal thought/reflection
    SUMMARY = "summary"  # Chapter/section summary
    QUESTION = "question"  # Question to explore
    INSIGHT = "insight"  # Key insight or takeaway
    CRITIQUE = "critique"  # Critical analysis
    CONNECTION = "connection"  # Connection to other works/ideas
    VOCABULARY = "vocabulary"  # New word or term
    RESEARCH = "research"  # Something to research further


class QuoteType(str, Enum):
    """Types of quotes."""

    QUOTE = "quote"  # Direct quote from the book
    HIGHLIGHT = "highlight"  # Highlighted passage
    EXCERPT = "excerpt"  # Longer excerpt
    PARAPHRASE = "paraphrase"  # Paraphrased passage


class HighlightColor(str, Enum):
    """Colors for highlights."""

    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    PINK = "pink"
    PURPLE = "purple"
    ORANGE = "orange"


class NoteBase(BaseModel):
    """Base note fields."""

    note_type: NoteType = NoteType.NOTE
    title: Optional[str] = Field(None, max_length=200)
    content: str = Field(..., min_length=1)
    chapter: Optional[str] = Field(None, max_length=100)
    page_number: Optional[int] = Field(None, ge=1)
    location: Optional[str] = Field(None, max_length=50)
    tags: Optional[list[str]] = None
    is_private: bool = False
    is_favorite: bool = False


class NoteCreate(NoteBase):
    """Schema for creating a note."""

    book_id: UUID


class NoteUpdate(BaseModel):
    """Schema for updating a note."""

    note_type: Optional[NoteType] = None
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    chapter: Optional[str] = Field(None, max_length=100)
    page_number: Optional[int] = Field(None, ge=1)
    location: Optional[str] = Field(None, max_length=50)
    tags: Optional[list[str]] = None
    is_private: Optional[bool] = None
    is_favorite: Optional[bool] = None


class NoteResponse(BaseModel):
    """Schema for note responses."""

    id: UUID
    book_id: UUID
    note_type: NoteType
    title: Optional[str]
    content: str
    chapter: Optional[str]
    page_number: Optional[int]
    location: Optional[str]
    tags: list[str]
    is_private: bool
    is_favorite: bool
    location_display: str
    short_content: str

    # Related
    book_title: Optional[str] = None
    book_author: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteSummary(BaseModel):
    """Summary of a note for listing."""

    id: UUID
    book_id: UUID
    book_title: str
    note_type: NoteType
    title: Optional[str]
    short_content: str
    location_display: str
    is_favorite: bool
    created_at: datetime


class QuoteBase(BaseModel):
    """Base quote fields."""

    text: str = Field(..., min_length=1)
    quote_type: QuoteType = QuoteType.QUOTE
    color: Optional[HighlightColor] = None
    speaker: Optional[str] = Field(None, max_length=200)
    context: Optional[str] = None
    chapter: Optional[str] = Field(None, max_length=100)
    page_number: Optional[int] = Field(None, ge=1)
    location: Optional[str] = Field(None, max_length=50)
    tags: Optional[list[str]] = None
    is_favorite: bool = False


class QuoteCreate(QuoteBase):
    """Schema for creating a quote."""

    book_id: UUID


class QuoteUpdate(BaseModel):
    """Schema for updating a quote."""

    text: Optional[str] = Field(None, min_length=1)
    quote_type: Optional[QuoteType] = None
    color: Optional[HighlightColor] = None
    speaker: Optional[str] = Field(None, max_length=200)
    context: Optional[str] = None
    chapter: Optional[str] = Field(None, max_length=100)
    page_number: Optional[int] = Field(None, ge=1)
    location: Optional[str] = Field(None, max_length=50)
    tags: Optional[list[str]] = None
    is_favorite: Optional[bool] = None


class QuoteResponse(BaseModel):
    """Schema for quote responses."""

    id: UUID
    book_id: UUID
    text: str
    quote_type: QuoteType
    color: Optional[HighlightColor]
    speaker: Optional[str]
    context: Optional[str]
    chapter: Optional[str]
    page_number: Optional[int]
    location: Optional[str]
    tags: list[str]
    is_favorite: bool
    location_display: str
    short_text: str
    attribution: str

    # Related
    book_title: Optional[str] = None
    book_author: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QuoteSummary(BaseModel):
    """Summary of a quote for listing."""

    id: UUID
    book_id: UUID
    book_title: str
    book_author: str
    short_text: str
    quote_type: QuoteType
    color: Optional[HighlightColor]
    speaker: Optional[str]
    location_display: str
    is_favorite: bool
    created_at: datetime


class NotesStats(BaseModel):
    """Statistics about notes and quotes."""

    total_notes: int
    total_quotes: int
    notes_by_type: dict[str, int]
    favorite_notes: int
    favorite_quotes: int
    books_with_notes: int
    books_with_quotes: int
    total_tags: int
    most_used_tags: list[tuple[str, int]]


class BookAnnotations(BaseModel):
    """All annotations for a specific book."""

    book_id: UUID
    book_title: str
    book_author: str
    notes: list[NoteSummary]
    quotes: list[QuoteSummary]
    total_notes: int
    total_quotes: int


# --- Quote Collection Schemas ---


class CollectionCreate(BaseModel):
    """Schema for creating a quote collection."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    is_public: bool = False


class CollectionUpdate(BaseModel):
    """Schema for updating a quote collection."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    is_public: Optional[bool] = None


class CollectionResponse(BaseModel):
    """Schema for collection responses."""

    id: UUID
    name: str
    description: Optional[str]
    icon: Optional[str]
    is_public: bool
    quote_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionWithQuotes(BaseModel):
    """Collection with its quotes."""

    id: UUID
    name: str
    description: Optional[str]
    icon: Optional[str]
    is_public: bool
    quotes: list[QuoteSummary]
    created_at: datetime


# --- Extended Stats Schemas ---


class QuoteStats(BaseModel):
    """Detailed statistics about quotes."""

    total_quotes: int
    total_highlights: int
    total_excerpts: int
    favorites_count: int
    quotes_by_book: dict[str, int]
    quotes_by_color: dict[str, int]
    quotes_by_type: dict[str, int]
    most_quoted_book: Optional[str]
    most_used_tags: list[tuple[str, int]]
    collections_count: int
