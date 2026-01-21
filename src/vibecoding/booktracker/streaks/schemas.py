"""Pydantic schemas for reading streaks and habits."""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class StreakStatus(str, Enum):
    """Status of a streak."""

    ACTIVE = "active"
    ENDED = "ended"
    AT_RISK = "at_risk"  # No reading today yet


class DailyReadingCreate(BaseModel):
    """Schema for creating/updating daily reading."""

    reading_date: date
    minutes_read: int = Field(0, ge=0)
    pages_read: int = Field(0, ge=0)
    sessions_count: int = Field(0, ge=0)
    books_read: int = Field(0, ge=0)
    books_completed: int = Field(0, ge=0)
    goal_minutes: Optional[int] = Field(None, ge=0)
    goal_pages: Optional[int] = Field(None, ge=0)
    primary_hour: Optional[int] = Field(None, ge=0, le=23)
    notes: Optional[str] = None


class DailyReadingResponse(BaseModel):
    """Schema for daily reading response."""

    id: UUID
    reading_date: date
    minutes_read: int
    pages_read: int
    sessions_count: int
    books_read: int
    books_completed: int
    goal_minutes: Optional[int]
    goal_pages: Optional[int]
    goal_met: bool
    goal_progress: Optional[float]
    primary_hour: Optional[int]
    weekday: int
    weekday_name: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StreakResponse(BaseModel):
    """Schema for streak response."""

    id: UUID
    start_date: date
    end_date: Optional[date]
    length: int
    is_current: bool
    is_active: bool
    total_minutes: int
    total_pages: int
    books_completed: int
    average_daily_minutes: float
    average_daily_pages: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StreakStats(BaseModel):
    """Overall streak statistics."""

    current_streak: int
    longest_streak: int
    total_streaks: int
    total_reading_days: int
    streak_status: StreakStatus

    # Current streak details
    current_streak_start: Optional[date]
    current_streak_minutes: int
    current_streak_pages: int
    current_streak_books: int

    # Averages
    average_streak_length: float
    average_daily_minutes: float
    average_daily_pages: float

    # Records
    best_day_minutes: int
    best_day_pages: int
    best_day_date: Optional[date]


class WeekdayStats(BaseModel):
    """Reading statistics by weekday."""

    weekday: int  # 0-6
    weekday_name: str
    total_days: int
    total_minutes: int
    total_pages: int
    average_minutes: float
    average_pages: float
    reading_frequency: float  # Percentage of weeks with reading on this day


class HourlyStats(BaseModel):
    """Reading statistics by hour of day."""

    hour: int  # 0-23
    sessions_count: int
    percentage: float  # Of total sessions


class ReadingHabits(BaseModel):
    """Analysis of reading habits."""

    # Best times
    most_productive_weekday: Optional[str]
    most_productive_hour: Optional[int]
    least_productive_weekday: Optional[str]

    # Patterns
    weekday_stats: list[WeekdayStats]
    hourly_distribution: list[HourlyStats]

    # Consistency
    reading_days_this_week: int
    reading_days_this_month: int
    consistency_score: float  # 0-100

    # Trends
    minutes_trend: str  # "increasing", "decreasing", "stable"
    pages_trend: str


class StreakMilestone(BaseModel):
    """A streak milestone achievement."""

    name: str
    description: str
    days_required: int
    achieved: bool
    achieved_date: Optional[date]


class StreakCalendar(BaseModel):
    """Calendar view of reading activity."""

    year: int
    month: int
    days: dict[int, bool]  # day -> has_reading
    streak_days: dict[int, int]  # day -> streak_length at that day
    total_reading_days: int
    total_minutes: int
    total_pages: int
