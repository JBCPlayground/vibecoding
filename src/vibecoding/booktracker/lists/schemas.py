"""Pydantic schemas for reading lists and recommendations."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ListType(str, Enum):
    """Type of reading list."""

    CUSTOM = "custom"
    SEASONAL = "seasonal"
    THEMED = "themed"
    AUTO = "auto"


class AutoListType(str, Enum):
    """Types of auto-generated lists."""

    HIGHLY_RATED_UNREAD = "highly_rated_unread"
    UNFINISHED_SERIES = "unfinished_series"
    LONG_ON_WISHLIST = "long_on_wishlist"
    FAVORITE_AUTHORS = "favorite_authors"
    QUICK_READS = "quick_reads"
    BY_GENRE = "by_genre"
    RECENTLY_ADDED = "recently_added"
    ABANDONED_WORTH_RETRY = "abandoned_worth_retry"


class ReadingListBase(BaseModel):
    """Base reading list fields."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    list_type: ListType = ListType.CUSTOM
    is_public: bool = False
    is_pinned: bool = False
    color: Optional[str] = Field(None, max_length=20)
    icon: Optional[str] = Field(None, max_length=50)


class ReadingListCreate(ReadingListBase):
    """Schema for creating a reading list."""

    pass


class ReadingListUpdate(BaseModel):
    """Schema for updating a reading list."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    list_type: Optional[ListType] = None
    is_public: Optional[bool] = None
    is_pinned: Optional[bool] = None
    color: Optional[str] = Field(None, max_length=20)
    icon: Optional[str] = Field(None, max_length=50)


class ReadingListResponse(BaseModel):
    """Schema for reading list response."""

    id: UUID
    name: str
    description: Optional[str]
    list_type: ListType
    type_display: str
    is_public: bool
    is_pinned: bool
    is_auto: bool
    color: Optional[str]
    icon: Optional[str]
    book_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReadingListSummary(BaseModel):
    """Summary of a reading list for listing."""

    id: UUID
    name: str
    list_type: ListType
    type_display: str
    is_pinned: bool
    book_count: int
    icon: Optional[str]


class ListBookCreate(BaseModel):
    """Schema for adding a book to a list."""

    book_id: UUID
    note: Optional[str] = None


class ListBookResponse(BaseModel):
    """Schema for list book response."""

    id: UUID
    list_id: UUID
    book_id: UUID
    position: int
    note: Optional[str]
    added_at: datetime

    model_config = {"from_attributes": True}


class ListBookWithDetails(BaseModel):
    """List book entry with book details."""

    id: UUID
    list_id: UUID
    book_id: UUID
    position: int
    note: Optional[str]
    added_at: datetime
    # Book details
    book_title: Optional[str]
    book_author: Optional[str]
    book_status: Optional[str]
    book_rating: Optional[int]


class ReadingListWithBooks(BaseModel):
    """Reading list with all its books."""

    list: ReadingListResponse
    books: list[ListBookWithDetails]


# ============================================================================
# Recommendation Schemas
# ============================================================================


class RecommendationReason(str, Enum):
    """Why a book is being recommended."""

    HIGHLY_RATED_GENRE = "highly_rated_genre"
    FAVORITE_AUTHOR = "favorite_author"
    SIMILAR_TO_LIKED = "similar_to_liked"
    POPULAR_IN_GENRE = "popular_in_genre"
    COMPLETE_SERIES = "complete_series"
    QUICK_READ = "quick_read"
    LONG_WISHLIST = "long_wishlist"
    ABANDONED_RETRY = "abandoned_retry"


class BookRecommendation(BaseModel):
    """A book recommendation."""

    book_id: UUID
    book_title: str
    book_author: Optional[str]
    reason: RecommendationReason
    reason_display: str
    confidence: float = Field(ge=0.0, le=1.0)  # How confident we are in this rec
    context: Optional[str] = None  # Additional context (e.g., "You rated 3 books by this author 5 stars")


class RecommendationSet(BaseModel):
    """A set of recommendations with a theme."""

    title: str
    description: Optional[str]
    recommendations: list[BookRecommendation]


class SimilarBook(BaseModel):
    """A book similar to another."""

    book_id: UUID
    book_title: str
    book_author: Optional[str]
    similarity_score: float
    shared_genres: list[str]
    same_author: bool


class GenreRecommendations(BaseModel):
    """Recommendations for a specific genre."""

    genre: str
    top_rated: list[BookRecommendation]
    unread_count: int
    average_rating: Optional[float]


class AuthorRecommendations(BaseModel):
    """Recommendations for books by an author."""

    author: str
    books_read: int
    average_rating: float
    unread_books: list[BookRecommendation]


class RecommendationStats(BaseModel):
    """Statistics about recommendations."""

    total_unread: int
    highly_rated_unread: int
    favorite_genres: list[str]
    favorite_authors: list[str]
    series_to_continue: int
    quick_reads_available: int
