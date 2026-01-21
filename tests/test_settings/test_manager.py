"""Tests for SettingsManager."""

import json
import pytest

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.settings import (
    SettingsManager,
    SettingCategory,
    SettingUpdate,
    ThemeMode,
    DateFormat,
    ExportFormat,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a SettingsManager with test database."""
    return SettingsManager(db)


class TestGetSetting:
    """Tests for getting settings."""

    def test_get_default_setting(self, manager):
        """Test getting a setting that hasn't been set."""
        setting = manager.get_setting(SettingCategory.DISPLAY, "theme")
        assert setting is not None
        assert setting.value == ThemeMode.AUTO.value
        assert setting.default_value == ThemeMode.AUTO.value

    def test_get_nonexistent_setting(self, manager):
        """Test getting a setting that doesn't exist."""
        setting = manager.get_setting(SettingCategory.DISPLAY, "nonexistent")
        assert setting is None

    def test_get_setting_with_description(self, manager):
        """Test that settings have descriptions."""
        setting = manager.get_setting(SettingCategory.DISPLAY, "theme")
        assert setting.description is not None
        assert len(setting.description) > 0


class TestSetSetting:
    """Tests for setting values."""

    def test_set_string_setting(self, manager):
        """Test setting a string value."""
        update = SettingUpdate(
            category=SettingCategory.READING,
            key="default_book_status",
            value="reading",
        )
        result = manager.set_setting(update)
        assert result.value == "reading"

        # Verify it persists
        setting = manager.get_setting(SettingCategory.READING, "default_book_status")
        assert setting.value == "reading"

    def test_set_boolean_setting(self, manager):
        """Test setting a boolean value."""
        update = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="compact_mode",
            value="true",
        )
        result = manager.set_setting(update)
        assert result.value == "true"

    def test_set_integer_setting(self, manager):
        """Test setting an integer value."""
        update = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="items_per_page",
            value="50",
        )
        result = manager.set_setting(update)
        assert result.value == "50"

    def test_set_enum_setting(self, manager):
        """Test setting an enum value."""
        update = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="dark",
        )
        result = manager.set_setting(update)
        assert result.value == "dark"

    def test_set_invalid_boolean(self, manager):
        """Test setting an invalid boolean value."""
        update = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="compact_mode",
            value="invalid",
        )
        with pytest.raises(ValueError):
            manager.set_setting(update)

    def test_set_invalid_integer(self, manager):
        """Test setting an invalid integer value."""
        update = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="items_per_page",
            value="abc",
        )
        with pytest.raises(ValueError):
            manager.set_setting(update)

    def test_set_integer_below_min(self, manager):
        """Test setting an integer below minimum."""
        update = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="items_per_page",
            value="1",
        )
        with pytest.raises(ValueError):
            manager.set_setting(update)

    def test_set_integer_above_max(self, manager):
        """Test setting an integer above maximum."""
        update = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="items_per_page",
            value="999",
        )
        with pytest.raises(ValueError):
            manager.set_setting(update)

    def test_set_invalid_enum(self, manager):
        """Test setting an invalid enum value."""
        update = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="invalid_theme",
        )
        with pytest.raises(ValueError):
            manager.set_setting(update)

    def test_set_nonexistent_setting(self, manager):
        """Test setting a nonexistent setting."""
        update = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="nonexistent",
            value="value",
        )
        with pytest.raises(ValueError):
            manager.set_setting(update)

    def test_update_existing_setting(self, manager):
        """Test updating an existing setting."""
        # Set initial value
        update1 = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="dark",
        )
        manager.set_setting(update1)

        # Update value
        update2 = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="light",
        )
        result = manager.set_setting(update2)
        assert result.value == "light"


class TestCategorySettings:
    """Tests for category settings."""

    def test_get_category_settings(self, manager):
        """Test getting all settings in a category."""
        settings = manager.get_category_settings(SettingCategory.DISPLAY)
        assert len(settings.settings) > 0
        assert settings.category == SettingCategory.DISPLAY

    def test_category_includes_custom_values(self, manager):
        """Test that category settings include custom values."""
        # Set a custom value
        update = SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="dark",
        )
        manager.set_setting(update)

        # Get category settings
        settings = manager.get_category_settings(SettingCategory.DISPLAY)
        theme_setting = next(
            (s for s in settings.settings if s.key == "theme"), None
        )
        assert theme_setting is not None
        assert theme_setting.value == "dark"


class TestAllSettings:
    """Tests for getting all settings."""

    def test_get_all_settings(self, manager):
        """Test getting all settings as structured object."""
        settings = manager.get_all_settings()

        # Check all categories exist
        assert settings.display is not None
        assert settings.reading is not None
        assert settings.export is not None
        assert settings.notifications is not None
        assert settings.privacy is not None
        assert settings.integrations is not None

    def test_all_settings_with_custom_values(self, manager):
        """Test that all settings include custom values."""
        # Set some custom values
        manager.set_setting(SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="dark",
        ))
        manager.set_setting(SettingUpdate(
            category=SettingCategory.READING,
            key="yearly_book_goal",
            value="24",
        ))

        settings = manager.get_all_settings()
        assert settings.display.theme == ThemeMode.DARK
        assert settings.reading.yearly_book_goal == 24


class TestResetSettings:
    """Tests for resetting settings."""

    def test_reset_single_setting(self, manager):
        """Test resetting a single setting."""
        # Set a custom value
        manager.set_setting(SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="dark",
        ))

        # Reset it
        result = manager.reset_setting(SettingCategory.DISPLAY, "theme")
        assert result.value == ThemeMode.AUTO.value

    def test_reset_category(self, manager):
        """Test resetting an entire category."""
        # Set multiple custom values
        manager.set_setting(SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="dark",
        ))
        manager.set_setting(SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="compact_mode",
            value="true",
        ))

        # Reset category
        settings = manager.reset_category(SettingCategory.DISPLAY)

        # Verify all are back to defaults
        theme = next(s for s in settings.settings if s.key == "theme")
        compact = next(s for s in settings.settings if s.key == "compact_mode")
        assert theme.value == theme.default_value
        assert compact.value == compact.default_value

    def test_reset_all_settings(self, manager):
        """Test resetting all settings."""
        # Set values in multiple categories
        manager.set_setting(SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="dark",
        ))
        manager.set_setting(SettingUpdate(
            category=SettingCategory.READING,
            key="yearly_book_goal",
            value="50",
        ))

        # Reset all
        manager.reset_all()

        # Verify defaults
        settings = manager.get_all_settings()
        assert settings.display.theme == ThemeMode.AUTO
        assert settings.reading.yearly_book_goal == 12


class TestExportImport:
    """Tests for export and import."""

    def test_export_settings(self, manager):
        """Test exporting settings."""
        export = manager.export_settings()
        assert export.version == "1.0"
        assert export.exported_at is not None
        assert export.settings is not None

    def test_import_settings(self, manager):
        """Test importing settings."""
        # Set some custom values
        manager.set_setting(SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="dark",
        ))

        # Export
        export = manager.export_settings()
        export_json = export.model_dump_json()

        # Reset
        manager.reset_all()

        # Import
        data = json.loads(export_json)
        manager.import_settings(data)

        # Verify
        settings = manager.get_all_settings()
        assert settings.display.theme == ThemeMode.DARK

    def test_import_invalid_format(self, manager):
        """Test importing invalid format."""
        with pytest.raises(ValueError):
            manager.import_settings({"invalid": "data"})


class TestBackups:
    """Tests for settings backups."""

    def test_create_backup(self, manager):
        """Test creating a backup."""
        backup = manager.create_backup("Test Backup", "Test description")
        assert backup.id is not None
        assert backup.name == "Test Backup"
        assert backup.description == "Test description"

    def test_list_backups(self, manager):
        """Test listing backups."""
        manager.create_backup("Backup 1")
        manager.create_backup("Backup 2")

        backups = manager.list_backups()
        assert len(backups) >= 2

    def test_restore_backup(self, manager):
        """Test restoring a backup."""
        # Set initial value
        manager.set_setting(SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="dark",
        ))

        # Create backup
        backup = manager.create_backup("Before change")

        # Change value
        manager.set_setting(SettingUpdate(
            category=SettingCategory.DISPLAY,
            key="theme",
            value="light",
        ))

        # Restore backup
        manager.restore_backup(backup.id)

        # Verify original value
        settings = manager.get_all_settings()
        assert settings.display.theme == ThemeMode.DARK

    def test_restore_nonexistent_backup(self, manager):
        """Test restoring a nonexistent backup."""
        with pytest.raises(ValueError):
            manager.restore_backup(99999)

    def test_delete_backup(self, manager):
        """Test deleting a backup."""
        backup = manager.create_backup("To Delete")
        result = manager.delete_backup(backup.id)
        assert result is True

        # Verify it's gone
        backups = manager.list_backups()
        assert not any(b.id == backup.id for b in backups)


class TestSearchSettings:
    """Tests for searching settings."""

    def test_search_by_key(self, manager):
        """Test searching settings by key."""
        results = manager.search_settings("theme")
        assert len(results) >= 1
        assert any("theme" in r.key for r in results)

    def test_search_by_description(self, manager):
        """Test searching settings by description."""
        results = manager.search_settings("goal")
        assert len(results) >= 1

    def test_search_no_results(self, manager):
        """Test search with no results."""
        results = manager.search_settings("xyznonexistent123")
        assert len(results) == 0


class TestGetSettingValue:
    """Tests for getting parsed setting values."""

    def test_get_boolean_value(self, manager):
        """Test getting a boolean value."""
        value = manager.get_setting_value(SettingCategory.DISPLAY, "compact_mode")
        assert isinstance(value, bool)
        assert value is False

    def test_get_integer_value(self, manager):
        """Test getting an integer value."""
        value = manager.get_setting_value(SettingCategory.DISPLAY, "items_per_page")
        assert isinstance(value, int)
        assert value == 20

    def test_get_string_value(self, manager):
        """Test getting a string value."""
        value = manager.get_setting_value(SettingCategory.DISPLAY, "theme")
        assert isinstance(value, str)
        assert value == "auto"


class TestSettingCategories:
    """Tests for setting categories."""

    def test_display_settings(self, manager):
        """Test display settings category."""
        settings = manager.get_category_settings(SettingCategory.DISPLAY)
        keys = [s.key for s in settings.settings]
        assert "theme" in keys
        assert "date_format" in keys
        assert "items_per_page" in keys

    def test_reading_settings(self, manager):
        """Test reading settings category."""
        settings = manager.get_category_settings(SettingCategory.READING)
        keys = [s.key for s in settings.settings]
        assert "daily_reading_goal_minutes" in keys
        assert "yearly_book_goal" in keys

    def test_export_settings(self, manager):
        """Test export settings category."""
        settings = manager.get_category_settings(SettingCategory.EXPORT)
        keys = [s.key for s in settings.settings]
        assert "default_export_format" in keys
        assert "auto_backup_enabled" in keys

    def test_notification_settings(self, manager):
        """Test notification settings category."""
        settings = manager.get_category_settings(SettingCategory.NOTIFICATIONS)
        keys = [s.key for s in settings.settings]
        assert "enable_notifications" in keys
        assert "goal_reminders" in keys

    def test_privacy_settings(self, manager):
        """Test privacy settings category."""
        settings = manager.get_category_settings(SettingCategory.PRIVACY)
        keys = [s.key for s in settings.settings]
        assert "default_note_visibility" in keys
        assert "anonymous_mode" in keys

    def test_integration_settings(self, manager):
        """Test integration settings category."""
        settings = manager.get_category_settings(SettingCategory.INTEGRATIONS)
        keys = [s.key for s in settings.settings]
        assert "goodreads_sync_enabled" in keys
        assert "notion_sync_enabled" in keys
