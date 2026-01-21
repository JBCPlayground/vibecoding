"""Schemas for reading locations."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LocationType(str, Enum):
    """Types of reading locations."""

    HOME = "home"
    OFFICE = "office"
    CAFE = "cafe"
    LIBRARY = "library"
    PARK = "park"
    COMMUTE = "commute"
    BEACH = "beach"
    TRAVEL = "travel"
    BOOKSTORE = "bookstore"
    OTHER = "other"


# --- Create Schemas ---


class LocationCreate(BaseModel):
    """Schema for creating a reading location."""

    name: str = Field(..., min_length=1, max_length=100)
    location_type: LocationType = LocationType.OTHER
    description: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = Field(None, max_length=200)
    icon: Optional[str] = Field(None, max_length=50)
    is_favorite: bool = False


class LocationUpdate(BaseModel):
    """Schema for updating a reading location."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    location_type: Optional[LocationType] = None
    description: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = Field(None, max_length=200)
    icon: Optional[str] = Field(None, max_length=50)
    is_favorite: Optional[bool] = None


class LocationSessionCreate(BaseModel):
    """Schema for logging a reading session at a location."""

    location_id: str
    book_id: Optional[str] = None
    minutes_read: int = Field(..., ge=1)
    pages_read: int = Field(0, ge=0)
    notes: Optional[str] = Field(None, max_length=500)
    session_date: Optional[datetime] = None  # Defaults to now


# --- Response Schemas ---


class LocationResponse(BaseModel):
    """Schema for location responses."""

    id: str
    name: str
    location_type: LocationType
    description: Optional[str]
    address: Optional[str]
    icon: Optional[str]
    is_favorite: bool
    total_sessions: int
    total_minutes: int
    total_pages: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LocationSummary(BaseModel):
    """Minimal location info for lists."""

    id: str
    name: str
    location_type: LocationType
    icon: Optional[str]
    total_sessions: int
    total_minutes: int

    model_config = {"from_attributes": True}


class LocationSessionResponse(BaseModel):
    """Schema for location session responses."""

    id: str
    location_id: str
    location_name: str
    book_id: Optional[str]
    book_title: Optional[str]
    minutes_read: int
    pages_read: int
    notes: Optional[str]
    session_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Stats Schemas ---


class LocationStats(BaseModel):
    """Statistics about reading locations."""

    total_locations: int
    total_sessions: int
    total_minutes: int
    total_pages: int
    favorite_location: Optional[str]
    most_used_location: Optional[str]
    minutes_by_type: dict[str, int]
    sessions_by_type: dict[str, int]
    top_locations: list[LocationSummary]
    reading_by_hour: dict[int, int]  # Hour of day -> minutes


class LocationBreakdown(BaseModel):
    """Reading breakdown for a specific location."""

    location_id: str
    location_name: str
    total_sessions: int
    total_minutes: int
    total_pages: int
    average_session_minutes: float
    books_read_here: list[str]
    most_recent_session: Optional[datetime]
    favorite_time_of_day: Optional[str]
