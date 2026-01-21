"""Pydantic schemas for book reviews."""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ReviewBase(BaseModel):
    """Base review fields."""

    rating: Optional[float] = Field(None, ge=0.5, le=5.0)
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    review_date: Optional[date] = None
    started_date: Optional[date] = None
    finished_date: Optional[date] = None

    # Detailed ratings
    plot_rating: Optional[float] = Field(None, ge=0.5, le=5.0)
    characters_rating: Optional[float] = Field(None, ge=0.5, le=5.0)
    writing_rating: Optional[float] = Field(None, ge=0.5, le=5.0)
    pacing_rating: Optional[float] = Field(None, ge=0.5, le=5.0)
    enjoyment_rating: Optional[float] = Field(None, ge=0.5, le=5.0)

    # Flags
    contains_spoilers: bool = False
    is_favorite: bool = False
    would_recommend: Optional[bool] = None
    would_reread: Optional[bool] = None

    # Tags
    tags: Optional[list[str]] = None

    # Private notes
    private_notes: Optional[str] = None

    @field_validator("rating", "plot_rating", "characters_rating",
                     "writing_rating", "pacing_rating", "enjoyment_rating")
    @classmethod
    def validate_rating(cls, v):
        """Validate rating is in 0.5 increments."""
        if v is not None:
            # Round to nearest 0.5
            v = round(v * 2) / 2
            if v < 0.5:
                v = 0.5
            elif v > 5.0:
                v = 5.0
        return v

    @field_validator("finished_date")
    @classmethod
    def finished_after_started(cls, v, info):
        """Validate finished date is after started date."""
        if v and "started_date" in info.data and info.data["started_date"]:
            if v < info.data["started_date"]:
                raise ValueError("finished_date must be after started_date")
        return v


class ReviewCreate(ReviewBase):
    """Schema for creating a review."""

    book_id: UUID


class ReviewUpdate(BaseModel):
    """Schema for updating a review."""

    rating: Optional[float] = Field(None, ge=0.5, le=5.0)
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    review_date: Optional[date] = None
    started_date: Optional[date] = None
    finished_date: Optional[date] = None

    # Detailed ratings
    plot_rating: Optional[float] = Field(None, ge=0.5, le=5.0)
    characters_rating: Optional[float] = Field(None, ge=0.5, le=5.0)
    writing_rating: Optional[float] = Field(None, ge=0.5, le=5.0)
    pacing_rating: Optional[float] = Field(None, ge=0.5, le=5.0)
    enjoyment_rating: Optional[float] = Field(None, ge=0.5, le=5.0)

    # Flags
    contains_spoilers: Optional[bool] = None
    is_favorite: Optional[bool] = None
    would_recommend: Optional[bool] = None
    would_reread: Optional[bool] = None

    # Tags
    tags: Optional[list[str]] = None

    # Private notes
    private_notes: Optional[str] = None

    @field_validator("rating", "plot_rating", "characters_rating",
                     "writing_rating", "pacing_rating", "enjoyment_rating")
    @classmethod
    def validate_rating(cls, v):
        """Validate rating is in 0.5 increments."""
        if v is not None:
            v = round(v * 2) / 2
            if v < 0.5:
                v = 0.5
            elif v > 5.0:
                v = 5.0
        return v


class ReviewResponse(BaseModel):
    """Schema for review responses."""

    id: UUID
    book_id: UUID
    rating: Optional[float]
    title: Optional[str]
    content: Optional[str]
    review_date: Optional[date]
    started_date: Optional[date]
    finished_date: Optional[date]

    # Detailed ratings
    plot_rating: Optional[float]
    characters_rating: Optional[float]
    writing_rating: Optional[float]
    pacing_rating: Optional[float]
    enjoyment_rating: Optional[float]

    # Flags
    contains_spoilers: bool
    is_favorite: bool
    would_recommend: Optional[bool]
    would_reread: Optional[bool]

    # Tags
    tags: list[str]

    # Computed
    star_display: str
    has_detailed_ratings: bool
    average_detailed_rating: Optional[float]

    # Related
    book_title: Optional[str] = None
    book_author: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewSummary(BaseModel):
    """Summary of a review for listing."""

    id: UUID
    book_id: UUID
    book_title: str
    book_author: str
    rating: Optional[float]
    title: Optional[str]
    is_favorite: bool
    review_date: Optional[date]
    star_display: str


class RatingDistribution(BaseModel):
    """Distribution of ratings."""

    one_star: int = 0
    two_star: int = 0
    three_star: int = 0
    four_star: int = 0
    five_star: int = 0

    @property
    def total(self) -> int:
        """Total number of ratings."""
        return self.one_star + self.two_star + self.three_star + self.four_star + self.five_star


class BookRatingStats(BaseModel):
    """Statistics about book ratings."""

    total_reviews: int
    total_rated: int
    average_rating: Optional[float]
    distribution: RatingDistribution
    total_favorites: int
    would_recommend_count: int
    would_reread_count: int

    # Detailed rating averages
    avg_plot_rating: Optional[float]
    avg_characters_rating: Optional[float]
    avg_writing_rating: Optional[float]
    avg_pacing_rating: Optional[float]
    avg_enjoyment_rating: Optional[float]


class TopRatedBook(BaseModel):
    """A top rated book entry."""

    book_id: UUID
    book_title: str
    book_author: str
    rating: float
    review_title: Optional[str]
    is_favorite: bool


class ReviewsByRating(BaseModel):
    """Reviews grouped by rating."""

    rating: float
    count: int
    reviews: list[ReviewSummary]
