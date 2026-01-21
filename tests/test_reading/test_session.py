"""Tests for reading session management."""

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.vibecoding.booktracker.db.schemas import BookCreate, BookStatus
from src.vibecoding.booktracker.reading.session import (
    ReadingSession,
    SessionManager,
    reset_session_manager,
)

# Test UUID to use consistently - must be valid UUID for ReadingLogCreate
TEST_BOOK_UUID = str(uuid4())


class TestReadingSession:
    """Tests for ReadingSession dataclass."""

    def test_create_session(self):
        """Test creating a basic reading session."""
        session = ReadingSession(
            book_id="test-id",
            book_title="Test Book",
            start_time=datetime.now(timezone.utc),
        )

        assert session.book_id == "test-id"
        assert session.book_title == "Test Book"
        assert session.start_page is None
        assert session.notes == []

    def test_duration_minutes(self):
        """Test calculating session duration."""
        start_time = datetime.now(timezone.utc)
        session = ReadingSession(
            book_id="test-id",
            book_title="Test Book",
            start_time=start_time,
        )

        # Duration should be close to 0 for a new session
        assert session.duration_minutes() >= 0
        assert session.duration_minutes() < 1

    def test_pages_read(self):
        """Test calculating pages read."""
        session = ReadingSession(
            book_id="test-id",
            book_title="Test Book",
            start_time=datetime.now(timezone.utc),
            start_page=10,
            current_page=50,
        )

        assert session.pages_read() == 40

    def test_pages_read_none_if_missing_pages(self):
        """Test pages_read returns None if page info is missing."""
        session = ReadingSession(
            book_id="test-id",
            book_title="Test Book",
            start_time=datetime.now(timezone.utc),
        )

        assert session.pages_read() is None

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        original = ReadingSession(
            book_id="test-id",
            book_title="Test Book",
            start_time=datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc),
            start_page=10,
            current_page=50,
            notes=["Note 1", "Note 2"],
            location="home",
        )

        data = original.to_dict()
        restored = ReadingSession.from_dict(data)

        assert restored.book_id == original.book_id
        assert restored.book_title == original.book_title
        assert restored.start_time == original.start_time
        assert restored.start_page == original.start_page
        assert restored.current_page == original.current_page
        assert restored.notes == original.notes
        assert restored.location == original.location


class TestSessionManager:
    """Tests for SessionManager."""

    @pytest.fixture
    def temp_session_file(self):
        """Create a temporary session file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        yield path
        if path.exists():
            path.unlink()

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        return db

    @pytest.fixture
    def manager(self, mock_db, temp_session_file):
        """Create a session manager with mocked dependencies."""
        reset_session_manager()
        return SessionManager(db=mock_db, session_file=temp_session_file)

    def test_no_active_session_initially(self, manager):
        """Test that there's no active session initially."""
        assert manager.active_session is None
        assert not manager.has_active_session()

    def test_start_session(self, manager, mock_db):
        """Test starting a reading session."""
        mock_book = MagicMock()
        mock_book.id = TEST_BOOK_UUID
        mock_book.title = "Test Book"
        mock_book.status = BookStatus.WISHLIST.value
        mock_db.get_book.return_value = mock_book

        session = manager.start_session(
            book_id=TEST_BOOK_UUID,
            start_page=10,
            location="home",
        )

        assert session.book_id == TEST_BOOK_UUID
        assert session.book_title == "Test Book"
        assert session.start_page == 10
        assert session.location == "home"
        assert manager.has_active_session()

    def test_start_session_updates_book_status(self, manager, mock_db):
        """Test that starting a session updates book status to reading."""
        mock_book = MagicMock()
        mock_book.id = TEST_BOOK_UUID
        mock_book.title = "Test Book"
        mock_book.status = BookStatus.WISHLIST.value
        mock_db.get_book.return_value = mock_book

        manager.start_session(book_id=TEST_BOOK_UUID)

        # Should have called update_book to change status
        mock_db.update_book.assert_called_once()

    def test_cannot_start_two_sessions(self, manager, mock_db):
        """Test that you can't start a session while one is active."""
        mock_book = MagicMock()
        mock_book.id = TEST_BOOK_UUID
        mock_book.title = "Test Book"
        mock_book.status = BookStatus.READING.value
        mock_db.get_book.return_value = mock_book

        manager.start_session(book_id=TEST_BOOK_UUID)

        with pytest.raises(ValueError, match="Already reading"):
            manager.start_session(book_id="book-456")

    def test_start_session_book_not_found(self, manager, mock_db):
        """Test starting a session with invalid book ID."""
        mock_db.get_book.return_value = None

        with pytest.raises(ValueError, match="Book not found"):
            manager.start_session(book_id="invalid-id")

    def test_update_progress(self, manager, mock_db):
        """Test updating progress in active session."""
        mock_book = MagicMock()
        mock_book.id = TEST_BOOK_UUID
        mock_book.title = "Test Book"
        mock_book.status = BookStatus.READING.value
        mock_db.get_book.return_value = mock_book

        manager.start_session(book_id=TEST_BOOK_UUID, start_page=1)

        session = manager.update_progress(current_page=50, note="Great chapter!")

        assert session.current_page == 50
        assert "Great chapter!" in session.notes

    def test_update_progress_no_active_session(self, manager):
        """Test update_progress returns None with no active session."""
        result = manager.update_progress(current_page=50)
        assert result is None

    def test_stop_session(self, manager, mock_db):
        """Test stopping a session."""
        mock_book = MagicMock()
        mock_book.id = TEST_BOOK_UUID
        mock_book.title = "Test Book"
        mock_book.status = BookStatus.READING.value
        mock_book.page_count = 200
        mock_db.get_book.return_value = mock_book

        manager.start_session(book_id=TEST_BOOK_UUID, start_page=1)
        manager.update_progress(current_page=50)

        log_entry = manager.stop_session(end_page=75, final_note="Done for now")

        assert log_entry is not None
        assert log_entry.start_page == 1
        assert log_entry.end_page == 75
        assert not manager.has_active_session()
        mock_db.create_reading_log.assert_called_once()

    def test_stop_session_no_active_session(self, manager):
        """Test stop_session returns None with no active session."""
        result = manager.stop_session()
        assert result is None

    def test_cancel_session(self, manager, mock_db):
        """Test cancelling a session without logging."""
        mock_book = MagicMock()
        mock_book.id = TEST_BOOK_UUID
        mock_book.title = "Test Book"
        mock_book.status = BookStatus.READING.value
        mock_db.get_book.return_value = mock_book

        manager.start_session(book_id=TEST_BOOK_UUID)
        assert manager.has_active_session()

        result = manager.cancel_session()

        assert result is True
        assert not manager.has_active_session()
        mock_db.create_reading_log.assert_not_called()

    def test_cancel_session_no_active_session(self, manager):
        """Test cancel_session returns False with no active session."""
        result = manager.cancel_session()
        assert result is False

    def test_log_session_manual(self, manager, mock_db):
        """Test logging a session manually."""
        mock_book = MagicMock()
        mock_book.id = TEST_BOOK_UUID
        mock_book.title = "Test Book"
        mock_book.page_count = 200
        mock_db.get_book.return_value = mock_book

        log_entry = manager.log_session(
            book_id=TEST_BOOK_UUID,
            pages_read=30,
            start_page=10,
            end_page=40,
            duration_minutes=45,
            location="commute",
            notes="Good reading session",
        )

        assert log_entry.pages_read == 30
        assert log_entry.start_page == 10
        assert log_entry.end_page == 40
        assert log_entry.duration_minutes == 45
        mock_db.create_reading_log.assert_called_once()

    def test_log_session_calculates_pages(self, manager, mock_db):
        """Test that log_session calculates pages from start/end."""
        mock_book = MagicMock()
        mock_book.id = TEST_BOOK_UUID
        mock_book.page_count = None
        mock_db.get_book.return_value = mock_book

        log_entry = manager.log_session(
            book_id=TEST_BOOK_UUID,
            start_page=10,
            end_page=40,
        )

        assert log_entry.pages_read == 30

    def test_log_session_book_not_found(self, manager, mock_db):
        """Test log_session with invalid book ID."""
        mock_db.get_book.return_value = None

        with pytest.raises(ValueError, match="Book not found"):
            manager.log_session(book_id="invalid-id")

    def test_session_persisted_to_file(self, manager, mock_db, temp_session_file):
        """Test that session is saved to file."""
        mock_book = MagicMock()
        mock_book.id = TEST_BOOK_UUID
        mock_book.title = "Test Book"
        mock_book.status = BookStatus.READING.value
        mock_db.get_book.return_value = mock_book

        manager.start_session(book_id=TEST_BOOK_UUID)

        # Check file was created
        assert temp_session_file.exists()

        # Read and verify contents
        with open(temp_session_file) as f:
            data = json.load(f)
            assert data["book_id"] == TEST_BOOK_UUID
            assert data["book_title"] == "Test Book"

    def test_session_loaded_from_file(self, mock_db, temp_session_file):
        """Test that session is loaded from existing file."""
        # Write a session to file
        session_data = {
            "book_id": TEST_BOOK_UUID,
            "book_title": "Test Book",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "start_page": 10,
            "notes": [],
        }
        with open(temp_session_file, "w") as f:
            json.dump(session_data, f)

        # Create manager - should load session
        reset_session_manager()
        manager = SessionManager(db=mock_db, session_file=temp_session_file)

        assert manager.has_active_session()
        assert manager.active_session.book_id == TEST_BOOK_UUID

    def test_session_file_deleted_on_stop(self, manager, mock_db, temp_session_file):
        """Test that session file is deleted when session stops."""
        mock_book = MagicMock()
        mock_book.id = TEST_BOOK_UUID
        mock_book.title = "Test Book"
        mock_book.status = BookStatus.READING.value
        mock_book.page_count = None
        mock_db.get_book.return_value = mock_book

        manager.start_session(book_id=TEST_BOOK_UUID)
        assert temp_session_file.exists()

        manager.stop_session()
        assert not temp_session_file.exists()
