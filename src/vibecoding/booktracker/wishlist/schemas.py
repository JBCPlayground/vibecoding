"""Pydantic schemas for wishlist management."""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class Priority(int, Enum):
    """Priority levels for wishlist items."""

    MUST_READ = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    SOMEDAY = 5


class WishlistSource(str, Enum):
    """Common sources for recommendations."""

    FRIEND = "friend"
    FAMILY = "family"
    BOOK_CLUB = "book_club"
    BLOG = "blog"
    PODCAST = "podcast"
    SOCIAL_MEDIA = "social_media"
    BESTSELLER = "bestseller"
    AWARD = "award"
    SERIES = "series"  # Next in a series
    AUTHOR = "author"  # Same author I like
    OTHER = "other"


class WishlistItemBase(BaseModel):
    """Base wishlist item fields."""

    title: str = Field(..., min_length=1, max_length=500)
    author: Optional[str] = Field(None, max_length=300)
    isbn: Optional[str] = Field(None, max_length=20)
    priority: Priority = Priority.MEDIUM
    source: Optional[WishlistSource] = None
    recommended_by: Optional[str] = Field(None, max_length=200)
    recommendation_url: Optional[str] = Field(None, max_length=500)
    reason: Optional[str] = None
    estimated_pages: Optional[int] = Field(None, ge=1)
    estimated_hours: Optional[float] = Field(None, ge=0.1)
    genre: Optional[str] = Field(None, max_length=100)
    target_date: Optional[date] = None
    is_available: bool = False
    is_on_hold: bool = False
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


class WishlistItemCreate(WishlistItemBase):
    """Schema for creating a wishlist item."""

    book_id: Optional[UUID] = None  # If linking to existing book


class WishlistItemUpdate(BaseModel):
    """Schema for updating a wishlist item."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    author: Optional[str] = Field(None, max_length=300)
    isbn: Optional[str] = Field(None, max_length=20)
    priority: Optional[Priority] = None
    position: Optional[int] = Field(None, ge=0)
    source: Optional[WishlistSource] = None
    recommended_by: Optional[str] = Field(None, max_length=200)
    recommendation_url: Optional[str] = Field(None, max_length=500)
    reason: Optional[str] = None
    estimated_pages: Optional[int] = Field(None, ge=1)
    estimated_hours: Optional[float] = Field(None, ge=0.1)
    genre: Optional[str] = Field(None, max_length=100)
    target_date: Optional[date] = None
    is_available: Optional[bool] = None
    is_on_hold: Optional[bool] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    book_id: Optional[UUID] = None


class WishlistItemResponse(BaseModel):
    """Schema for wishlist item response."""

    id: UUID
    title: str
    author: Optional[str]
    isbn: Optional[str]
    book_id: Optional[UUID]
    priority: Priority
    priority_display: str
    position: int
    source: Optional[WishlistSource]
    recommended_by: Optional[str]
    recommendation_url: Optional[str]
    reason: Optional[str]
    estimated_pages: Optional[int]
    estimated_hours: Optional[float]
    genre: Optional[str]
    date_added: date
    target_date: Optional[date]
    is_available: bool
    is_on_hold: bool
    is_in_library: bool
    tags: list[str]
    notes: Optional[str]
    display_title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WishlistSummary(BaseModel):
    """Summary of a wishlist item for listing."""

    id: UUID
    title: str
    author: Optional[str]
    priority: Priority
    priority_display: str
    position: int
    source: Optional[WishlistSource]
    date_added: date
    is_available: bool
    is_in_library: bool


class WishlistStats(BaseModel):
    """Statistics about the wishlist."""

    total_items: int
    by_priority: dict[str, int]
    by_source: dict[str, int]
    available_count: int
    on_hold_count: int
    in_library_count: int
    total_estimated_pages: int
    total_estimated_hours: float
    oldest_item_date: Optional[date]
    items_with_target_date: int
    overdue_targets: int  # Past target date


class NextUpRecommendation(BaseModel):
    """Recommendation for what to read next."""

    item: WishlistSummary
    reason: str  # Why this is recommended


class WishlistByPriority(BaseModel):
    """Wishlist items grouped by priority."""

    priority: Priority
    priority_display: str
    items: list[WishlistSummary]
    count: int
