"""Manager for user settings and preferences."""

import json
from datetime import datetime
from typing import Any, Optional

from ..db.sqlite import Database
from .models import Setting, SettingsBackup
from .schemas import (
    BackupResponse,
    CategorySettings,
    DateFormat,
    DefaultBookView,
    DisplaySettings,
    ExportFormat,
    ExportSettings,
    IntegrationSettings,
    NotificationSettings,
    PrivacySettings,
    ReadingSettings,
    SettingCategory,
    SettingResponse,
    SettingsExport,
    SettingUpdate,
    ThemeMode,
    TimeFormat,
    UserSettings,
)


# Default settings with descriptions
SETTINGS_METADATA = {
    SettingCategory.DISPLAY: {
        "theme": {
            "type": "enum",
            "default": ThemeMode.AUTO.value,
            "options": [e.value for e in ThemeMode],
            "description": "Color theme mode",
        },
        "date_format": {
            "type": "enum",
            "default": DateFormat.ISO.value,
            "options": [e.value for e in DateFormat],
            "description": "Date display format",
        },
        "time_format": {
            "type": "enum",
            "default": TimeFormat.H24.value,
            "options": [e.value for e in TimeFormat],
            "description": "Time display format (12h or 24h)",
        },
        "items_per_page": {
            "type": "int",
            "default": "20",
            "min": 5,
            "max": 100,
            "description": "Items shown per page",
        },
        "default_book_view": {
            "type": "enum",
            "default": DefaultBookView.TABLE.value,
            "options": [e.value for e in DefaultBookView],
            "description": "Default view for book lists",
        },
        "show_reading_progress": {
            "type": "bool",
            "default": "true",
            "description": "Show reading progress bars",
        },
        "show_page_numbers": {
            "type": "bool",
            "default": "true",
            "description": "Show page numbers in lists",
        },
        "compact_mode": {
            "type": "bool",
            "default": "false",
            "description": "Use compact display mode",
        },
        "show_covers": {
            "type": "bool",
            "default": "true",
            "description": "Show book covers when available",
        },
    },
    SettingCategory.READING: {
        "daily_reading_goal_minutes": {
            "type": "int",
            "default": "30",
            "min": 0,
            "max": 1440,
            "description": "Daily reading goal (minutes)",
        },
        "daily_reading_goal_pages": {
            "type": "int",
            "default": "20",
            "min": 0,
            "max": 500,
            "description": "Daily reading goal (pages)",
        },
        "yearly_book_goal": {
            "type": "int",
            "default": "12",
            "min": 0,
            "max": 365,
            "description": "Yearly book reading goal",
        },
        "default_reading_speed_wpm": {
            "type": "int",
            "default": "250",
            "min": 50,
            "max": 1000,
            "description": "Default reading speed (words per minute)",
        },
        "track_reading_sessions": {
            "type": "bool",
            "default": "true",
            "description": "Track reading sessions automatically",
        },
        "auto_pause_session_minutes": {
            "type": "int",
            "default": "60",
            "min": 5,
            "max": 480,
            "description": "Auto-pause session after inactivity (minutes)",
        },
        "default_book_status": {
            "type": "str",
            "default": "to-read",
            "description": "Default status for new books",
        },
        "remind_unfinished_books_days": {
            "type": "int",
            "default": "14",
            "min": 0,
            "max": 365,
            "description": "Remind about unfinished books after (days)",
        },
        "show_streak_notifications": {
            "type": "bool",
            "default": "true",
            "description": "Show reading streak notifications",
        },
    },
    SettingCategory.EXPORT: {
        "default_export_format": {
            "type": "enum",
            "default": ExportFormat.JSON.value,
            "options": [e.value for e in ExportFormat],
            "description": "Default export file format",
        },
        "include_notes_in_export": {
            "type": "bool",
            "default": "true",
            "description": "Include notes in exports",
        },
        "include_quotes_in_export": {
            "type": "bool",
            "default": "true",
            "description": "Include quotes in exports",
        },
        "include_reading_sessions": {
            "type": "bool",
            "default": "true",
            "description": "Include reading sessions in exports",
        },
        "auto_backup_enabled": {
            "type": "bool",
            "default": "false",
            "description": "Enable automatic backups",
        },
        "backup_frequency_days": {
            "type": "int",
            "default": "7",
            "min": 1,
            "max": 30,
            "description": "Backup frequency (days)",
        },
        "backup_location": {
            "type": "str",
            "default": "",
            "description": "Backup file location",
        },
        "max_backups_to_keep": {
            "type": "int",
            "default": "5",
            "min": 1,
            "max": 50,
            "description": "Maximum number of backups to keep",
        },
    },
    SettingCategory.NOTIFICATIONS: {
        "enable_notifications": {
            "type": "bool",
            "default": "true",
            "description": "Enable all notifications",
        },
        "goal_reminders": {
            "type": "bool",
            "default": "true",
            "description": "Remind about reading goals",
        },
        "streak_reminders": {
            "type": "bool",
            "default": "true",
            "description": "Remind about reading streaks",
        },
        "reading_reminders": {
            "type": "bool",
            "default": "false",
            "description": "Daily reading reminders",
        },
        "reminder_time": {
            "type": "str",
            "default": "20:00",
            "description": "Time for reminders (HH:MM)",
        },
        "weekly_summary": {
            "type": "bool",
            "default": "true",
            "description": "Receive weekly reading summary",
        },
        "monthly_summary": {
            "type": "bool",
            "default": "true",
            "description": "Receive monthly reading summary",
        },
    },
    SettingCategory.PRIVACY: {
        "default_note_visibility": {
            "type": "str",
            "default": "private",
            "description": "Default visibility for notes",
        },
        "default_review_visibility": {
            "type": "str",
            "default": "private",
            "description": "Default visibility for reviews",
        },
        "share_reading_activity": {
            "type": "bool",
            "default": "false",
            "description": "Share reading activity",
        },
        "show_reading_stats": {
            "type": "bool",
            "default": "true",
            "description": "Show reading statistics",
        },
        "anonymous_mode": {
            "type": "bool",
            "default": "false",
            "description": "Enable anonymous mode",
        },
    },
    SettingCategory.INTEGRATIONS: {
        "goodreads_sync_enabled": {
            "type": "bool",
            "default": "false",
            "description": "Enable Goodreads sync",
        },
        "goodreads_user_id": {
            "type": "str",
            "default": "",
            "description": "Goodreads user ID",
        },
        "notion_sync_enabled": {
            "type": "bool",
            "default": "false",
            "description": "Enable Notion sync",
        },
        "notion_database_id": {
            "type": "str",
            "default": "",
            "description": "Notion database ID",
        },
        "calibre_library_path": {
            "type": "str",
            "default": "",
            "description": "Path to Calibre library",
        },
        "sync_on_startup": {
            "type": "bool",
            "default": "false",
            "description": "Sync on application startup",
        },
    },
}


class SettingsManager:
    """Manager for user settings and preferences."""

    def __init__(self, db: Database):
        """Initialize settings manager."""
        self.db = db

    def _parse_value(self, value: str, value_type: str) -> Any:
        """Parse string value to appropriate type."""
        if value_type == "bool":
            return value.lower() in ("true", "1", "yes")
        elif value_type == "int":
            return int(value)
        else:
            return value

    def _serialize_value(self, value: Any) -> str:
        """Serialize value to string for storage."""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def get_setting(
        self, category: SettingCategory, key: str
    ) -> Optional[SettingResponse]:
        """Get a single setting."""
        metadata = SETTINGS_METADATA.get(category, {}).get(key)
        if not metadata:
            return None

        with self.db.get_session() as session:
            setting = (
                session.query(Setting)
                .filter(Setting.category == category.value, Setting.key == key)
                .first()
            )

            value = setting.value if setting else metadata["default"]

            return SettingResponse(
                category=category,
                key=key,
                value=value,
                description=metadata.get("description"),
                default_value=metadata["default"],
                value_type=metadata["type"],
            )

    def set_setting(self, update: SettingUpdate) -> SettingResponse:
        """Set a single setting."""
        metadata = SETTINGS_METADATA.get(update.category, {}).get(update.key)
        if not metadata:
            raise ValueError(f"Unknown setting: {update.category.value}.{update.key}")

        # Validate value
        value_type = metadata["type"]
        if value_type == "bool":
            if update.value.lower() not in ("true", "false", "1", "0", "yes", "no"):
                raise ValueError(f"Invalid boolean value: {update.value}")
        elif value_type == "int":
            try:
                int_val = int(update.value)
                if "min" in metadata and int_val < metadata["min"]:
                    raise ValueError(
                        f"Value must be at least {metadata['min']}"
                    )
                if "max" in metadata and int_val > metadata["max"]:
                    raise ValueError(
                        f"Value must be at most {metadata['max']}"
                    )
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid integer value: {update.value}") from e
        elif value_type == "enum":
            if update.value not in metadata.get("options", []):
                raise ValueError(
                    f"Invalid value. Options: {metadata.get('options', [])}"
                )

        with self.db.get_session() as session:
            setting = (
                session.query(Setting)
                .filter(
                    Setting.category == update.category.value,
                    Setting.key == update.key,
                )
                .first()
            )

            if setting:
                setting.value = update.value
            else:
                setting = Setting(
                    category=update.category.value,
                    key=update.key,
                    value=update.value,
                    value_type=value_type,
                )
                session.add(setting)

            session.commit()

            return SettingResponse(
                category=update.category,
                key=update.key,
                value=update.value,
                description=metadata.get("description"),
                default_value=metadata["default"],
                value_type=value_type,
            )

    def get_category_settings(self, category: SettingCategory) -> CategorySettings:
        """Get all settings in a category."""
        category_metadata = SETTINGS_METADATA.get(category, {})
        settings = []

        with self.db.get_session() as session:
            db_settings = (
                session.query(Setting)
                .filter(Setting.category == category.value)
                .all()
            )
            db_values = {s.key: s.value for s in db_settings}

            for key, metadata in category_metadata.items():
                value = db_values.get(key, metadata["default"])
                settings.append(
                    SettingResponse(
                        category=category,
                        key=key,
                        value=value,
                        description=metadata.get("description"),
                        default_value=metadata["default"],
                        value_type=metadata["type"],
                    )
                )

        return CategorySettings(category=category, settings=settings)

    def get_all_settings(self) -> UserSettings:
        """Get all user settings as structured objects."""
        display = self._get_settings_object(SettingCategory.DISPLAY, DisplaySettings)
        reading = self._get_settings_object(SettingCategory.READING, ReadingSettings)
        export = self._get_settings_object(SettingCategory.EXPORT, ExportSettings)
        notifications = self._get_settings_object(
            SettingCategory.NOTIFICATIONS, NotificationSettings
        )
        privacy = self._get_settings_object(SettingCategory.PRIVACY, PrivacySettings)
        integrations = self._get_settings_object(
            SettingCategory.INTEGRATIONS, IntegrationSettings
        )

        return UserSettings(
            display=display,
            reading=reading,
            export=export,
            notifications=notifications,
            privacy=privacy,
            integrations=integrations,
            updated_at=datetime.now(),
        )

    def _get_settings_object(self, category: SettingCategory, model_class: type) -> Any:
        """Get settings as a Pydantic model object."""
        category_settings = self.get_category_settings(category)
        data = {}

        for setting in category_settings.settings:
            value = self._parse_value(setting.value, setting.value_type)
            data[setting.key] = value

        return model_class(**data)

    def reset_setting(self, category: SettingCategory, key: str) -> SettingResponse:
        """Reset a setting to its default value."""
        metadata = SETTINGS_METADATA.get(category, {}).get(key)
        if not metadata:
            raise ValueError(f"Unknown setting: {category.value}.{key}")

        with self.db.get_session() as session:
            session.query(Setting).filter(
                Setting.category == category.value,
                Setting.key == key,
            ).delete()
            session.commit()

        return SettingResponse(
            category=category,
            key=key,
            value=metadata["default"],
            description=metadata.get("description"),
            default_value=metadata["default"],
            value_type=metadata["type"],
        )

    def reset_category(self, category: SettingCategory) -> CategorySettings:
        """Reset all settings in a category to defaults."""
        with self.db.get_session() as session:
            session.query(Setting).filter(
                Setting.category == category.value
            ).delete()
            session.commit()

        return self.get_category_settings(category)

    def reset_all(self) -> UserSettings:
        """Reset all settings to defaults."""
        with self.db.get_session() as session:
            session.query(Setting).delete()
            session.commit()

        return self.get_all_settings()

    def export_settings(self) -> SettingsExport:
        """Export all settings."""
        settings = self.get_all_settings()
        return SettingsExport(
            exported_at=datetime.now(),
            settings=settings,
        )

    def import_settings(self, data: dict) -> UserSettings:
        """Import settings from exported data."""
        # Validate structure
        if "settings" not in data:
            raise ValueError("Invalid settings export format")

        with self.db.get_session() as session:
            # Clear existing settings
            session.query(Setting).delete()

            settings_data = data["settings"]

            # Import each category
            for category in SettingCategory:
                category_key = category.value
                if category_key in settings_data:
                    category_data = settings_data[category_key]
                    for key, value in category_data.items():
                        metadata = SETTINGS_METADATA.get(category, {}).get(key)
                        if metadata:
                            setting = Setting(
                                category=category.value,
                                key=key,
                                value=self._serialize_value(value),
                                value_type=metadata["type"],
                            )
                            session.add(setting)

            session.commit()

        return self.get_all_settings()

    def create_backup(
        self, name: str, description: Optional[str] = None
    ) -> BackupResponse:
        """Create a settings backup."""
        settings = self.get_all_settings()
        settings_json = settings.model_dump_json()

        with self.db.get_session() as session:
            backup = SettingsBackup(
                name=name,
                description=description,
                settings_json=settings_json,
            )
            session.add(backup)
            session.commit()
            session.refresh(backup)

            # Build response before leaving session
            return BackupResponse(
                id=backup.id,
                name=backup.name,
                description=backup.description,
                created_at=backup.created_at,
            )

    def list_backups(self) -> list[BackupResponse]:
        """List all settings backups."""
        with self.db.get_session() as session:
            backups = (
                session.query(SettingsBackup)
                .order_by(SettingsBackup.created_at.desc())
                .all()
            )
            # Build response before leaving session
            result = []
            for b in backups:
                result.append(
                    BackupResponse(
                        id=b.id,
                        name=b.name,
                        description=b.description,
                        created_at=b.created_at,
                    )
                )
            return result

    def restore_backup(self, backup_id: int) -> UserSettings:
        """Restore settings from a backup."""
        with self.db.get_session() as session:
            backup = (
                session.query(SettingsBackup)
                .filter(SettingsBackup.id == backup_id)
                .first()
            )

            if not backup:
                raise ValueError(f"Backup not found: {backup_id}")

            settings_data = json.loads(backup.settings_json)
            return self.import_settings({"settings": settings_data})

    def delete_backup(self, backup_id: int) -> bool:
        """Delete a settings backup."""
        with self.db.get_session() as session:
            deleted = (
                session.query(SettingsBackup)
                .filter(SettingsBackup.id == backup_id)
                .delete()
            )
            session.commit()
            return deleted > 0

    def search_settings(self, query: str) -> list[SettingResponse]:
        """Search settings by key or description."""
        query_lower = query.lower()
        results = []

        for category, settings in SETTINGS_METADATA.items():
            for key, metadata in settings.items():
                if (
                    query_lower in key.lower()
                    or query_lower in metadata.get("description", "").lower()
                ):
                    setting = self.get_setting(category, key)
                    if setting:
                        results.append(setting)

        return results

    def get_setting_value(self, category: SettingCategory, key: str) -> Any:
        """Get the parsed value of a setting."""
        setting = self.get_setting(category, key)
        if not setting:
            return None
        return self._parse_value(setting.value, setting.value_type)
