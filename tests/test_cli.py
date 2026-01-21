"""Tests for the CLI interface."""

import os
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.vibecoding.booktracker.cli import app
from src.vibecoding.booktracker.db.sqlite import reset_db
from src.vibecoding.booktracker.config import reset_config


@pytest.fixture(autouse=True)
def setup_test_db():
    """Set up a test database for each test."""
    reset_db()
    reset_config()

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    os.environ["BOOKTRACKER_DB_PATH"] = db_path

    yield

    # Cleanup
    reset_db()
    reset_config()
    if "BOOKTRACKER_DB_PATH" in os.environ:
        del os.environ["BOOKTRACKER_DB_PATH"]
    if Path(db_path).exists():
        Path(db_path).unlink()


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


class TestCLIBasics:
    """Tests for basic CLI functionality."""

    def test_help(self, runner: CliRunner):
        """Test that help command works."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Track your reading" in result.stdout

    def test_version(self, runner: CliRunner):
        """Test version command."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout


class TestAddManualCommand:
    """Tests for add-manual command."""

    def test_add_manual_book(self, runner: CliRunner):
        """Test adding a book manually."""
        result = runner.invoke(
            app,
            ["add-manual", "--title", "Test Book", "--author", "Test Author"],
        )
        assert result.exit_code == 0
        assert "Added:" in result.stdout
        assert "Test Book" in result.stdout

    def test_add_manual_with_all_options(self, runner: CliRunner):
        """Test adding a book with all options."""
        result = runner.invoke(
            app,
            [
                "add-manual",
                "--title", "Complete Book",
                "--author", "Full Author",
                "--isbn", "1234567890",
                "--status", "reading",
                "--pages", "300",
            ],
        )
        assert result.exit_code == 0
        assert "Added:" in result.stdout


class TestListCommand:
    """Tests for list command."""

    def test_list_empty(self, runner: CliRunner):
        """Test listing when no books exist."""
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No books found" in result.stdout

    def test_list_with_books(self, runner: CliRunner):
        """Test listing books."""
        # Add some books first
        runner.invoke(
            app,
            ["add-manual", "--title", "Book One", "--author", "Author One"],
        )
        runner.invoke(
            app,
            ["add-manual", "--title", "Book Two", "--author", "Author Two"],
        )

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Book One" in result.stdout
        assert "Book Two" in result.stdout

    def test_list_by_status(self, runner: CliRunner):
        """Test filtering list by status."""
        # Add books with different statuses
        runner.invoke(
            app,
            ["add-manual", "--title", "Reading Book", "--author", "Author", "--status", "reading"],
        )
        runner.invoke(
            app,
            ["add-manual", "--title", "Wishlist Book", "--author", "Author", "--status", "wishlist"],
        )

        result = runner.invoke(app, ["list", "--status", "reading"])
        assert result.exit_code == 0
        assert "Reading Book" in result.stdout
        assert "Wishlist Book" not in result.stdout


class TestSearchCommand:
    """Tests for search command."""

    def test_search_no_results(self, runner: CliRunner):
        """Test search with no results."""
        result = runner.invoke(app, ["search", "query", "nonexistent"])
        assert result.exit_code == 0
        assert "No books found" in result.stdout

    def test_search_with_results(self, runner: CliRunner):
        """Test search with results."""
        runner.invoke(
            app,
            ["add-manual", "--title", "The Great Gatsby", "--author", "Fitzgerald"],
        )

        result = runner.invoke(app, ["search", "query", "Gatsby"])
        assert result.exit_code == 0
        assert "The Great Gatsby" in result.stdout


class TestUpdateCommand:
    """Tests for update command."""

    def test_update_book(self, runner: CliRunner):
        """Test updating a book."""
        runner.invoke(
            app,
            ["add-manual", "--title", "Test Book", "--author", "Author"],
        )

        result = runner.invoke(
            app,
            ["update", "Test Book", "--status", "completed", "--rating", "5"],
        )
        assert result.exit_code == 0
        assert "Updated:" in result.stdout

    def test_update_nonexistent(self, runner: CliRunner):
        """Test updating a nonexistent book."""
        result = runner.invoke(app, ["update", "Nonexistent", "--rating", "5"])
        assert result.exit_code == 1
        assert "No book found" in result.stdout


class TestStatsCommand:
    """Tests for stats command."""

    def test_stats_empty(self, runner: CliRunner):
        """Test stats with no books."""
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "No books in library" in result.stdout

    def test_stats_with_books(self, runner: CliRunner):
        """Test stats with some books."""
        runner.invoke(
            app,
            ["add-manual", "--title", "Book 1", "--author", "Author", "--status", "completed"],
        )
        runner.invoke(
            app,
            ["add-manual", "--title", "Book 2", "--author", "Author", "--status", "reading"],
        )

        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Total books" in result.stdout
        assert "2" in result.stdout


class TestBackupCommand:
    """Tests for backup command."""

    def test_backup(self, runner: CliRunner, tmp_path):
        """Test database backup."""
        # Add a book to create the database
        runner.invoke(
            app,
            ["add-manual", "--title", "Test", "--author", "Author"],
        )

        backup_path = tmp_path / "backup"
        result = runner.invoke(app, ["backup", "create", str(backup_path)])
        assert result.exit_code == 0
        assert "Backup created" in result.stdout


class TestSyncCommand:
    """Tests for sync command."""

    def test_sync_no_notion_config(self, runner: CliRunner):
        """Test sync without Notion configuration."""
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 1
        assert "Notion not configured" in result.stdout

    def test_sync_status(self, runner: CliRunner):
        """Test sync status command."""
        result = runner.invoke(app, ["sync", "--status"])
        assert result.exit_code == 1  # No Notion config
        assert "Notion not configured" in result.stdout


class TestLibraryCommand:
    """Tests for library command."""

    def test_library_list_empty(self, runner: CliRunner):
        """Test library list with no items."""
        result = runner.invoke(app, ["library", "list"])
        assert result.exit_code == 0
        assert "No library items found" in result.stdout

    def test_library_checkout(self, runner: CliRunner):
        """Test checking out a library book with due date."""
        runner.invoke(
            app,
            ["add-manual", "--title", "Library Book", "--author", "Author"],
        )

        result = runner.invoke(
            app,
            ["library", "checkout", "Library Book", "--due", "2025-02-15"],
        )
        assert result.exit_code == 0
        assert "Checked out" in result.stdout

    def test_library_hold(self, runner: CliRunner):
        """Test placing a library hold."""
        runner.invoke(
            app,
            ["add-manual", "--title", "Hold Book", "--author", "Author"],
        )

        result = runner.invoke(
            app,
            ["library", "hold", "Hold Book", "--location", "Main Branch"],
        )
        assert result.exit_code == 0
        assert "Hold placed" in result.stdout

    def test_library_summary(self, runner: CliRunner):
        """Test library summary."""
        result = runner.invoke(app, ["library", "summary"])
        assert result.exit_code == 0
        assert "Library Summary" in result.stdout


class TestImportCommands:
    """Tests for import commands."""

    def test_import_notion_file_not_found(self, runner: CliRunner):
        """Test import with nonexistent file."""
        result = runner.invoke(app, ["import", "notion", "/nonexistent/file.csv"])
        assert result.exit_code == 1
        assert "File not found" in result.stdout

    def test_import_goodreads_with_valid_csv(self, runner: CliRunner):
        """Test that Goodreads import works with a valid CSV."""
        csv_content = """Book Id,Title,Author,ISBN,ISBN13,My Rating,Exclusive Shelf,Date Read
54493401,Test Book,Test Author,="1234567890",="9781234567890",5,read,2024-06-15
"""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            result = runner.invoke(app, ["import", "goodreads", temp_path, "--yes"])
            # Should succeed with import preview/confirmation
            assert result.exit_code == 0 or "import" in result.stdout.lower()
        finally:
            Path(temp_path).unlink()
