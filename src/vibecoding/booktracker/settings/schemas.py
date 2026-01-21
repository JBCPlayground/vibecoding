"""Schemas for user settings and preferences."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ThemeMode(str, Enum):
    """Display theme mode."""

    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class DateFormat(str, Enum):
    """Date display format."""

    ISO = "YYYY-MM-DD"
    US = "MM/DD/YYYY"
    EU = "DD/MM/YYYY"
    LONG = "Month DD, YYYY"


class TimeFormat(str, Enum):
    """Time display format."""

    H12 = "12h"
    H24 = "24h"


class SortOrder(str, Enum):
    """Default sort order."""

    ASC = "asc"
    DESC = "desc"


class DefaultBookView(str, Enum):
    """Default view for book lists."""

    TABLE = "table"
    GRID = "grid"
    LIST = "list"
    COMPACT = "compact"


class ExportFormat(str, Enum):
    """Export file format."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class SettingCategory(str, Enum):
    """Setting category."""

    DISPLAY = "display"
    READING = "reading"
    EXPORT = "export"
    NOTIFICATIONS = "notifications"
    PRIVACY = "privacy"
    INTEGRATIONS = "integrations"


# --- Display Settings ---


class DisplaySettings(BaseModel):
    """Display and UI preferences."""

    theme: ThemeMode = ThemeMode.AUTO
    date_format: DateFormat = DateFormat.ISO
    time_format: TimeFormat = TimeFormat.H24
    items_per_page: int = Field(default=20, ge=5, le=100)
    default_book_view: DefaultBookView = DefaultBookView.TABLE
    show_reading_progress: bool = True
    show_page_numbers: bool = True
    compact_mode: bool = False
    show_covers: bool = True


# --- Reading Settings ---


class ReadingSettings(BaseModel):
    """Reading habit preferences."""

    daily_reading_goal_minutes: int = Field(default=30, ge=0, le=1440)
    daily_reading_goal_pages: int = Field(default=20, ge=0, le=500)
    yearly_book_goal: int = Field(default=12, ge=0, le=365)
    default_reading_speed_wpm: int = Field(default=250, ge=50, le=1000)
    track_reading_sessions: bool = True
    auto_pause_session_minutes: int = Field(default=60, ge=5, le=480)
    default_book_status: str = "to-read"
    remind_unfinished_books_days: int = Field(default=14, ge=0, le=365)
    show_streak_notifications: bool = True


# --- Export Settings ---


class ExportSettings(BaseModel):
    """Export and backup preferences."""

    default_export_format: ExportFormat = ExportFormat.JSON
    include_notes_in_export: bool = True
    include_quotes_in_export: bool = True
    include_reading_sessions: bool = True
    auto_backup_enabled: bool = False
    backup_frequency_days: int = Field(default=7, ge=1, le=30)
    backup_location: Optional[str] = None
    max_backups_to_keep: int = Field(default=5, ge=1, le=50)


# --- Notification Settings ---


class NotificationSettings(BaseModel):
    """Notification preferences."""

    enable_notifications: bool = True
    goal_reminders: bool = True
    streak_reminders: bool = True
    reading_reminders: bool = False
    reminder_time: str = "20:00"  # HH:MM format
    weekly_summary: bool = True
    monthly_summary: bool = True


# --- Privacy Settings ---


class PrivacySettings(BaseModel):
    """Privacy preferences."""

    default_note_visibility: str = "private"  # private, public
    default_review_visibility: str = "private"
    share_reading_activity: bool = False
    show_reading_stats: bool = True
    anonymous_mode: bool = False


# --- Integration Settings ---


class IntegrationSettings(BaseModel):
    """External integration settings."""

    goodreads_sync_enabled: bool = False
    goodreads_user_id: Optional[str] = None
    notion_sync_enabled: bool = False
    notion_database_id: Optional[str] = None
    calibre_library_path: Optional[str] = None
    sync_on_startup: bool = False


# --- Complete User Settings ---


class UserSettings(BaseModel):
    """Complete user settings."""

    display: DisplaySettings = Field(default_factory=DisplaySettings)
    reading: ReadingSettings = Field(default_factory=ReadingSettings)
    export: ExportSettings = Field(default_factory=ExportSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)
    updated_at: Optional[datetime] = None


# --- Setting Operations ---


class SettingUpdate(BaseModel):
    """Update a single setting."""

    category: SettingCategory
    key: str
    value: str  # Will be parsed based on setting type


class SettingResponse(BaseModel):
    """Response for a single setting."""

    category: SettingCategory
    key: str
    value: str
    description: Optional[str] = None
    default_value: str
    value_type: str  # bool, int, str, enum


class CategorySettings(BaseModel):
    """All settings in a category."""

    category: SettingCategory
    settings: list[SettingResponse]


class SettingsExport(BaseModel):
    """Exported settings."""

    version: str = "1.0"
    exported_at: datetime
    settings: UserSettings


class BackupResponse(BaseModel):
    """Response for a settings backup."""

    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
