"""Pydantic schemas for reading schedules and planning."""

from datetime import date, time
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PlanStatus(str, Enum):
    """Status of a reading plan."""

    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ScheduleFrequency(str, Enum):
    """Frequency for scheduled reading."""

    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    WEEKLY = "weekly"
    CUSTOM = "custom"


class ReminderType(str, Enum):
    """Type of reading reminder."""

    READING_TIME = "reading_time"
    DEADLINE = "deadline"
    GOAL_CHECK = "goal_check"
    STREAK = "streak"


# ============================================================================
# Reading Plan Schemas
# ============================================================================


class ReadingPlanCreate(BaseModel):
    """Schema for creating a reading plan."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_books: Optional[int] = Field(None, ge=1)
    target_pages: Optional[int] = Field(None, ge=1)


class ReadingPlanUpdate(BaseModel):
    """Schema for updating a reading plan."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_books: Optional[int] = Field(None, ge=1)
    target_pages: Optional[int] = Field(None, ge=1)
    status: Optional[PlanStatus] = None


class ReadingPlanResponse(BaseModel):
    """Response schema for a reading plan."""

    id: UUID
    name: str
    description: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    target_books: Optional[int]
    target_pages: Optional[int]
    status: PlanStatus
    books_planned: int
    books_completed: int
    pages_planned: int
    pages_read: int
    progress_percentage: float
    days_remaining: Optional[int]
    on_track: bool
    created_at: str
    updated_at: Optional[str]

    model_config = {"from_attributes": True}


# ============================================================================
# Planned Book Schemas
# ============================================================================


class PlannedBookCreate(BaseModel):
    """Schema for adding a book to a plan."""

    book_id: UUID
    plan_id: UUID
    position: int = Field(default=1, ge=1)
    target_start_date: Optional[date] = None
    target_end_date: Optional[date] = None
    priority: int = Field(default=2, ge=1, le=5)  # 1=highest, 5=lowest
    notes: Optional[str] = None


class PlannedBookUpdate(BaseModel):
    """Schema for updating a planned book."""

    position: Optional[int] = Field(None, ge=1)
    target_start_date: Optional[date] = None
    target_end_date: Optional[date] = None
    priority: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None


class PlannedBookResponse(BaseModel):
    """Response schema for a planned book."""

    id: UUID
    book_id: UUID
    plan_id: UUID
    book_title: str
    book_author: Optional[str]
    position: int
    target_start_date: Optional[date]
    target_end_date: Optional[date]
    actual_start_date: Optional[date]
    actual_end_date: Optional[date]
    priority: int
    notes: Optional[str]
    is_completed: bool
    is_overdue: bool
    days_until_deadline: Optional[int]
    page_count: Optional[int]

    model_config = {"from_attributes": True}


# ============================================================================
# Schedule Entry Schemas
# ============================================================================


class ScheduleEntryCreate(BaseModel):
    """Schema for creating a schedule entry."""

    name: str = Field(..., min_length=1, max_length=100)
    frequency: ScheduleFrequency = ScheduleFrequency.DAILY
    days_of_week: Optional[list[int]] = None  # 0=Monday, 6=Sunday
    preferred_time: Optional[time] = None
    duration_minutes: int = Field(default=30, ge=5, le=480)
    book_id: Optional[UUID] = None  # Optional specific book


class ScheduleEntryUpdate(BaseModel):
    """Schema for updating a schedule entry."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    frequency: Optional[ScheduleFrequency] = None
    days_of_week: Optional[list[int]] = None
    preferred_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(None, ge=5, le=480)
    book_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class ScheduleEntryResponse(BaseModel):
    """Response schema for a schedule entry."""

    id: UUID
    name: str
    frequency: ScheduleFrequency
    days_of_week: Optional[list[int]]
    preferred_time: Optional[time]
    duration_minutes: int
    book_id: Optional[UUID]
    book_title: Optional[str]
    is_active: bool
    next_occurrence: Optional[date]
    created_at: str

    model_config = {"from_attributes": True}


# ============================================================================
# Reminder Schemas
# ============================================================================


class ReminderCreate(BaseModel):
    """Schema for creating a reminder."""

    reminder_type: ReminderType
    message: Optional[str] = None
    reminder_time: time
    days_of_week: Optional[list[int]] = None  # None = every day
    book_id: Optional[UUID] = None
    plan_id: Optional[UUID] = None


class ReminderUpdate(BaseModel):
    """Schema for updating a reminder."""

    message: Optional[str] = None
    reminder_time: Optional[time] = None
    days_of_week: Optional[list[int]] = None
    is_active: Optional[bool] = None


class ReminderResponse(BaseModel):
    """Response schema for a reminder."""

    id: UUID
    reminder_type: ReminderType
    message: Optional[str]
    reminder_time: time
    days_of_week: Optional[list[int]]
    book_id: Optional[UUID]
    plan_id: Optional[UUID]
    is_active: bool
    created_at: str

    model_config = {"from_attributes": True}


# ============================================================================
# Planning Analytics
# ============================================================================


class PlanProgress(BaseModel):
    """Progress report for a reading plan."""

    plan_id: UUID
    plan_name: str
    total_books: int
    completed_books: int
    in_progress_books: int
    not_started_books: int
    total_pages: int
    pages_read: int
    days_elapsed: int
    days_remaining: int
    books_per_day_needed: float
    pages_per_day_needed: float
    current_pace_books: float
    current_pace_pages: float
    projected_completion: Optional[date]
    on_track: bool


class WeeklySchedule(BaseModel):
    """Weekly reading schedule summary."""

    week_start: date
    entries: list[ScheduleEntryResponse]
    total_planned_minutes: int
    completed_minutes: int
    books_scheduled: int
    completion_rate: float


class UpcomingDeadline(BaseModel):
    """An upcoming book deadline."""

    book_id: UUID
    book_title: str
    book_author: Optional[str]
    deadline: date
    days_remaining: int
    pages_remaining: Optional[int]
    is_at_risk: bool  # Behind pace to finish


class ScheduleSummary(BaseModel):
    """Summary of reading schedule and plans."""

    active_plans: int
    books_in_plans: int
    upcoming_deadlines: list[UpcomingDeadline]
    this_week_schedule: WeeklySchedule
    reading_time_today: Optional[time]
    current_book: Optional[str]
