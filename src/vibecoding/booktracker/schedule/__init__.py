"""Schedule module for reading planning and deadlines."""

from vibecoding.booktracker.schedule.manager import ScheduleManager
from vibecoding.booktracker.schedule.models import (
    PlannedBook,
    ReadingPlan,
    Reminder,
    ScheduleEntry,
)
from vibecoding.booktracker.schedule.schemas import (
    PlanProgress,
    PlanStatus,
    PlannedBookCreate,
    PlannedBookResponse,
    PlannedBookUpdate,
    ReadingPlanCreate,
    ReadingPlanResponse,
    ReadingPlanUpdate,
    ReminderCreate,
    ReminderResponse,
    ReminderType,
    ReminderUpdate,
    ScheduleEntryCreate,
    ScheduleEntryResponse,
    ScheduleEntryUpdate,
    ScheduleFrequency,
    ScheduleSummary,
    UpcomingDeadline,
    WeeklySchedule,
)

__all__ = [
    # Manager
    "ScheduleManager",
    # Models
    "ReadingPlan",
    "PlannedBook",
    "ScheduleEntry",
    "Reminder",
    # Enums
    "PlanStatus",
    "ScheduleFrequency",
    "ReminderType",
    # Plan schemas
    "ReadingPlanCreate",
    "ReadingPlanUpdate",
    "ReadingPlanResponse",
    # Planned book schemas
    "PlannedBookCreate",
    "PlannedBookUpdate",
    "PlannedBookResponse",
    # Schedule entry schemas
    "ScheduleEntryCreate",
    "ScheduleEntryUpdate",
    "ScheduleEntryResponse",
    # Reminder schemas
    "ReminderCreate",
    "ReminderUpdate",
    "ReminderResponse",
    # Analytics schemas
    "PlanProgress",
    "WeeklySchedule",
    "UpcomingDeadline",
    "ScheduleSummary",
]
