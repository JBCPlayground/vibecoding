"""Pydantic schemas for reading challenges."""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChallengeType(str, Enum):
    """Type of reading challenge."""

    BOOKS = "books"  # Count number of books
    PAGES = "pages"  # Count total pages
    HOURS = "hours"  # Count reading hours
    SERIES = "series"  # Complete a series
    AUTHOR = "author"  # Read books by an author
    GENRE = "genre"  # Read books in a genre


class ChallengeStatus(str, Enum):
    """Status of a challenge."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class ChallengeCriteria(BaseModel):
    """Optional criteria for filtering books that count toward a challenge."""

    # Filter by status (books must have this status to count)
    status: Optional[str] = None

    # Filter by tags/genres
    tags: Optional[list[str]] = None
    require_all_tags: bool = False

    # Filter by author
    author: Optional[str] = None

    # Filter by series
    series: Optional[str] = None

    # Filter by publication year range
    min_year: Optional[int] = None
    max_year: Optional[int] = None

    # Minimum page count
    min_pages: Optional[int] = None

    # Finish date must be within challenge period
    require_finish_in_period: bool = True


class ChallengeBase(BaseModel):
    """Base challenge fields."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    challenge_type: ChallengeType = ChallengeType.BOOKS
    target: int = Field(..., ge=1, description="Target number to reach")
    start_date: date
    end_date: date
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=20)

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v, info):
        """Validate end date is after start date."""
        if "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class ChallengeCreate(ChallengeBase):
    """Schema for creating a challenge."""

    criteria: Optional[ChallengeCriteria] = None
    auto_count: bool = True


class ChallengeUpdate(BaseModel):
    """Schema for updating a challenge."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    target: Optional[int] = Field(None, ge=1)
    end_date: Optional[date] = None
    status: Optional[ChallengeStatus] = None
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=20)
    criteria: Optional[ChallengeCriteria] = None


class ChallengeProgress(BaseModel):
    """Progress information for a challenge."""

    current: int
    target: int
    percent: float
    remaining: int
    days_remaining: int
    books_counted: int
    on_track: bool
    pace_needed: float  # Items per day needed to complete
    current_pace: float  # Current items per day


class ChallengeResponse(ChallengeBase):
    """Schema for challenge responses."""

    id: UUID
    current: int
    status: ChallengeStatus
    auto_count: bool
    criteria: Optional[ChallengeCriteria] = None
    progress: ChallengeProgress
    is_complete: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ChallengeSummary(BaseModel):
    """Summary of a challenge for listing."""

    id: UUID
    name: str
    challenge_type: ChallengeType
    current: int
    target: int
    percent: float
    status: ChallengeStatus
    days_remaining: int
    is_active: bool


class ChallengeBookAdd(BaseModel):
    """Schema for adding a book to a challenge."""

    book_id: UUID
    value: Optional[int] = None  # Override default value
    notes: Optional[str] = None


class ChallengeBookResponse(BaseModel):
    """Schema for challenge book responses."""

    id: UUID
    challenge_id: UUID
    book_id: UUID
    value: int
    counted_at: datetime
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class YearlyChallenge(BaseModel):
    """Preset for a yearly reading challenge."""

    year: int
    target: int
    name: Optional[str] = None
    challenge_type: ChallengeType = ChallengeType.BOOKS
