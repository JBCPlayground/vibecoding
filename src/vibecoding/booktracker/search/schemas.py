"""Schemas for advanced search functionality."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SearchScope(str, Enum):
    """Scope of search - which entities to search."""

    ALL = "all"
    BOOKS = "books"
    NOTES = "notes"
    QUOTES = "quotes"
    REVIEWS = "reviews"
    COLLECTIONS = "collections"
    LISTS = "lists"
    TAGS = "tags"
    AUTHORS = "authors"


class ResultType(str, Enum):
    """Type of search result."""

    BOOK = "book"
    NOTE = "note"
    QUOTE = "quote"
    REVIEW = "review"
    COLLECTION = "collection"
    LIST = "list"
    TAG = "tag"
    AUTHOR = "author"


class SortBy(str, Enum):
    """Sort options for search results."""

    RELEVANCE = "relevance"
    DATE = "date"
    TITLE = "title"
    AUTHOR = "author"


class SortOrder(str, Enum):
    """Sort order for results."""

    ASC = "asc"
    DESC = "desc"


# --- Search Query Schemas ---


class SearchQuery(BaseModel):
    """Schema for a search query."""

    query: str = Field(..., min_length=1, max_length=500)
    scope: list[SearchScope] = Field(default=[SearchScope.ALL])
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort_by: SortBy = SortBy.RELEVANCE
    sort_order: SortOrder = SortOrder.DESC

    # Filters
    book_status: Optional[str] = None  # read, reading, to-read
    genre: Optional[str] = None
    author: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    favorites_only: bool = False
    min_rating: Optional[float] = Field(None, ge=0, le=5)


class AdvancedSearchQuery(BaseModel):
    """Schema for advanced search with field-specific queries."""

    # Field-specific searches
    title: Optional[str] = None
    author: Optional[str] = None
    content: Optional[str] = None  # For notes, reviews, quotes
    tag: Optional[str] = None
    genre: Optional[str] = None

    # Boolean operators
    must_include: list[str] = Field(default_factory=list)  # AND
    should_include: list[str] = Field(default_factory=list)  # OR
    must_exclude: list[str] = Field(default_factory=list)  # NOT

    # Options
    scope: list[SearchScope] = Field(default=[SearchScope.ALL])
    limit: int = Field(default=50, ge=1, le=200)
    sort_by: SortBy = SortBy.RELEVANCE
    sort_order: SortOrder = SortOrder.DESC


# --- Search Result Schemas ---


class SearchResult(BaseModel):
    """A single search result."""

    id: str
    result_type: ResultType
    title: str
    subtitle: Optional[str] = None  # Author for books, book title for notes/quotes
    snippet: str  # Highlighted text excerpt
    relevance_score: float = Field(ge=0, le=1)
    created_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)


class SearchResults(BaseModel):
    """Collection of search results."""

    query: str
    total_count: int
    results: list[SearchResult]
    has_more: bool
    facets: dict[str, dict[str, int]] = Field(default_factory=dict)
    search_time_ms: float


class BookSearchResult(BaseModel):
    """Search result for a book."""

    id: str
    title: str
    author: Optional[str]
    genres: Optional[str]  # JSON string of genres
    status: str
    rating: Optional[float]
    snippet: str
    relevance_score: float


class NoteSearchResult(BaseModel):
    """Search result for a note."""

    id: str
    book_id: str
    book_title: str
    note_type: str
    title: Optional[str]
    snippet: str
    relevance_score: float


class QuoteSearchResult(BaseModel):
    """Search result for a quote."""

    id: str
    book_id: str
    book_title: str
    text_snippet: str
    speaker: Optional[str]
    relevance_score: float


class ReviewSearchResult(BaseModel):
    """Search result for a review."""

    id: str
    book_id: str
    book_title: str
    rating: Optional[float]
    snippet: str
    relevance_score: float


# --- Suggestion Schemas ---


class SearchSuggestion(BaseModel):
    """A search suggestion for autocomplete."""

    text: str
    result_type: ResultType
    count: int  # Number of matching items


class SearchSuggestions(BaseModel):
    """Collection of search suggestions."""

    query: str
    suggestions: list[SearchSuggestion]


# --- Search History ---


class SearchHistoryItem(BaseModel):
    """An item in search history."""

    query: str
    scope: list[SearchScope]
    result_count: int
    searched_at: datetime


class RecentSearches(BaseModel):
    """Recent search history."""

    searches: list[SearchHistoryItem]
    total_searches: int
