"""Pydantic schemas for book series management."""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SeriesStatus(str, Enum):
    """Reading status for a series."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    ABANDONED = "abandoned"


class SeriesBase(BaseModel):
    """Base series fields."""

    name: str = Field(..., min_length=1, max_length=500)
    author: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    total_books: Optional[int] = Field(None, ge=1)
    is_complete: bool = False
    genre: Optional[str] = Field(None, max_length=100)
    goodreads_series_id: Optional[str] = Field(None, max_length=50)
    goodreads_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class SeriesCreate(SeriesBase):
    """Schema for creating a series."""

    status: SeriesStatus = SeriesStatus.NOT_STARTED


class SeriesUpdate(BaseModel):
    """Schema for updating a series."""

    name: Optional[str] = Field(None, min_length=1, max_length=500)
    author: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    total_books: Optional[int] = Field(None, ge=1)
    is_complete: Optional[bool] = None
    genre: Optional[str] = Field(None, max_length=100)
    status: Optional[SeriesStatus] = None
    goodreads_series_id: Optional[str] = Field(None, max_length=50)
    goodreads_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class SeriesResponse(BaseModel):
    """Schema for series response."""

    id: UUID
    name: str
    author: Optional[str]
    description: Optional[str]
    total_books: Optional[int]
    is_complete: bool
    genre: Optional[str]
    status: SeriesStatus
    status_display: str
    books_owned: int
    books_read: int
    completion_percentage: float
    books_remaining: Optional[int]
    average_rating: Optional[float]
    goodreads_series_id: Optional[str]
    goodreads_url: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SeriesSummary(BaseModel):
    """Summary of a series for listing."""

    id: UUID
    name: str
    author: Optional[str]
    status: SeriesStatus
    status_display: str
    total_books: Optional[int]
    books_read: int
    completion_percentage: float
    is_complete: bool


class SeriesBookBase(BaseModel):
    """Base series book fields."""

    position: float = Field(..., ge=0)
    position_label: Optional[str] = Field(None, max_length=50)
    is_main_series: bool = True
    is_optional: bool = False
    notes: Optional[str] = None


class SeriesBookCreate(SeriesBookBase):
    """Schema for adding a book to a series."""

    book_id: UUID
    is_read: bool = False
    is_owned: bool = False


class SeriesBookUpdate(BaseModel):
    """Schema for updating a series book entry."""

    position: Optional[float] = Field(None, ge=0)
    position_label: Optional[str] = Field(None, max_length=50)
    is_main_series: Optional[bool] = None
    is_optional: Optional[bool] = None
    is_read: Optional[bool] = None
    is_owned: Optional[bool] = None
    notes: Optional[str] = None


class SeriesBookResponse(BaseModel):
    """Schema for series book response."""

    id: UUID
    series_id: UUID
    book_id: UUID
    position: float
    position_display: str
    position_label: Optional[str]
    is_main_series: bool
    is_optional: bool
    is_read: bool
    is_owned: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SeriesBookWithDetails(BaseModel):
    """Series book entry with book details."""

    id: UUID
    series_id: UUID
    book_id: UUID
    position: float
    position_display: str
    position_label: Optional[str]
    is_main_series: bool
    is_optional: bool
    is_read: bool
    is_owned: bool
    notes: Optional[str]
    # Book details (populated from book table)
    book_title: Optional[str]
    book_author: Optional[str]
    book_rating: Optional[int]
    book_status: Optional[str]


class SeriesWithBooks(BaseModel):
    """Series with all its books."""

    series: SeriesResponse
    books: list[SeriesBookWithDetails]
    next_to_read: Optional[SeriesBookWithDetails]


class SeriesStats(BaseModel):
    """Statistics about series tracking."""

    total_series: int
    by_status: dict[str, int]
    completed_series: int
    in_progress_series: int
    total_series_books: int
    series_books_read: int
    overall_completion: float
    average_series_length: float
    longest_series: Optional[str]
    most_read_series: Optional[str]


class NextInSeries(BaseModel):
    """Recommendation for next book in a series."""

    series_id: UUID
    series_name: str
    book_entry: SeriesBookWithDetails
    books_read_in_series: int
    total_in_series: Optional[int]
