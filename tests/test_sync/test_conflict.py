"""Tests for conflict detection logic."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from src.vibecoding.booktracker.sync.conflict import (
    ConflictType,
    SyncConflict,
    detect_conflict,
)
from src.vibecoding.booktracker.sync.notion import NotionPage


class TestDetectConflict:
    """Tests for conflict detection."""

    @pytest.fixture
    def mock_local_book(self):
        """Create a mock local book."""
        book = MagicMock()
        book.id = "local-123"
        book.title = "Test Book"
        book.author = "Test Author"
        book.status = "completed"
        book.rating = 5
        book.notion_page_id = "notion-page-123"
        book.local_modified_at = "2025-01-15T12:00:00+00:00"
        book.notion_modified_at = "2025-01-10T12:00:00+00:00"
        return book

    @pytest.fixture
    def mock_notion_page(self):
        """Create a mock Notion page."""
        return NotionPage(
            page_id="notion-page-123",
            title="Test Book",
            author="Test Author",
            properties={
                "Status": {"select": {"name": "Read"}},
                "Rating": {"number": 5},
            },
            last_edited_time=datetime(2025, 1, 15, 14, 0, tzinfo=timezone.utc),
            created_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    def test_new_local_book(self, mock_local_book):
        """Test detecting new local book (no Notion page)."""
        mock_local_book.notion_page_id = None

        conflict = detect_conflict(
            local_book=mock_local_book,
            notion_page=None,
            last_sync_time=None,
        )

        assert conflict is not None
        assert conflict.conflict_type == ConflictType.NEW_LOCAL
        assert conflict.local_book == mock_local_book

    def test_new_notion_book(self, mock_notion_page):
        """Test detecting new Notion book (not in local)."""
        conflict = detect_conflict(
            local_book=None,
            notion_page=mock_notion_page,
            last_sync_time=None,
        )

        assert conflict is not None
        assert conflict.conflict_type == ConflictType.NEW_NOTION
        assert conflict.notion_page == mock_notion_page

    def test_both_modified_conflict(self, mock_local_book, mock_notion_page):
        """Test detecting when both local and Notion were modified."""
        # Last sync was before both modifications
        last_sync = datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc)

        conflict = detect_conflict(
            local_book=mock_local_book,
            notion_page=mock_notion_page,
            last_sync_time=last_sync,
        )

        assert conflict is not None
        assert conflict.conflict_type == ConflictType.BOTH_MODIFIED
        assert conflict.local_book == mock_local_book
        assert conflict.notion_page == mock_notion_page

    def test_no_conflict_only_local_modified(self, mock_local_book, mock_notion_page):
        """Test no conflict when only local was modified."""
        # Notion wasn't modified after last sync
        mock_notion_page.last_edited_time = datetime(2025, 1, 8, tzinfo=timezone.utc)
        last_sync = datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc)

        conflict = detect_conflict(
            local_book=mock_local_book,
            notion_page=mock_notion_page,
            last_sync_time=last_sync,
        )

        # No conflict - local changes can be pushed
        assert conflict is None

    def test_no_conflict_only_notion_modified(self, mock_local_book, mock_notion_page):
        """Test no conflict when only Notion was modified."""
        # Local wasn't modified after last sync
        mock_local_book.local_modified_at = "2025-01-08T12:00:00+00:00"
        last_sync = datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc)

        conflict = detect_conflict(
            local_book=mock_local_book,
            notion_page=mock_notion_page,
            last_sync_time=last_sync,
        )

        # No conflict - Notion changes can be pulled
        assert conflict is None

    def test_notion_deleted_conflict(self, mock_local_book):
        """Test detecting when Notion page was deleted."""
        # Local book has notion_page_id but page doesn't exist
        conflict = detect_conflict(
            local_book=mock_local_book,
            notion_page=None,
            last_sync_time=datetime(2025, 1, 5, tzinfo=timezone.utc),
        )

        assert conflict is not None
        assert conflict.conflict_type == ConflictType.NOTION_DELETED

    def test_no_conflict_neither_modified(self, mock_local_book, mock_notion_page):
        """Test no conflict when neither was modified since sync."""
        # Both modified before last sync
        mock_local_book.local_modified_at = "2025-01-05T12:00:00+00:00"
        mock_notion_page.last_edited_time = datetime(2025, 1, 5, tzinfo=timezone.utc)
        last_sync = datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc)

        conflict = detect_conflict(
            local_book=mock_local_book,
            notion_page=mock_notion_page,
            last_sync_time=last_sync,
        )

        assert conflict is None


class TestSyncConflict:
    """Tests for SyncConflict dataclass."""

    def test_repr(self):
        """Test string representation."""
        book = MagicMock()
        book.title = "Test Book"

        conflict = SyncConflict(
            book_id="123",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_book=book,
            notion_page=None,
            local_modified=datetime.now(timezone.utc),
            notion_modified=None,
            last_sync=None,
        )

        assert "Test Book" in repr(conflict)
        assert "both_modified" in repr(conflict)
