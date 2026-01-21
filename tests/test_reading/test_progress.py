"""Tests for reading progress tracking."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.vibecoding.booktracker.db.schemas import BookStatus
from src.vibecoding.booktracker.reading.progress import (
    ProgressTracker,
    ReadingStats,
    calculate_reading_speed,
)


class TestReadingStats:
    """Tests for ReadingStats dataclass."""

    def test_default_values(self):
        """Test default values for ReadingStats."""
        stats = ReadingStats()

        assert stats.total_pages == 0
        assert stats.total_minutes == 0
        assert stats.total_sessions == 0
        assert stats.avg_reading_speed == 0.0
        assert stats.pages_by_location == {}

    def test_with_values(self):
        """Test ReadingStats with provided values."""
        stats = ReadingStats(
            total_pages=500,
            total_minutes=600,
            total_sessions=10,
            avg_pages_per_session=50.0,
            pages_by_location={"home": 300, "commute": 200},
        )

        assert stats.total_pages == 500
        assert stats.total_minutes == 600
        assert stats.avg_pages_per_session == 50.0
        assert stats.pages_by_location["home"] == 300


class TestProgressTracker:
    """Tests for ProgressTracker."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        return MagicMock()

    @pytest.fixture
    def tracker(self, mock_db):
        """Create a progress tracker with mocked database."""
        return ProgressTracker(db=mock_db)

    def test_get_book_progress(self, tracker, mock_db):
        """Test getting progress for a specific book."""
        # Mock book
        mock_book = MagicMock()
        mock_book.title = "Test Book"
        mock_book.page_count = 300

        # Mock reading logs
        mock_log1 = MagicMock()
        mock_log1.pages_read = 50
        mock_log1.end_page = 50
        mock_log1.duration_minutes = 60

        mock_log2 = MagicMock()
        mock_log2.pages_read = 30
        mock_log2.end_page = 80
        mock_log2.duration_minutes = 45

        # Setup session context
        mock_session = MagicMock()
        mock_session.get.return_value = mock_book
        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            mock_log1, mock_log2
        ]

        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        progress = tracker.get_book_progress("book-123")

        assert progress["book_title"] == "Test Book"
        assert progress["total_pages"] == 300
        assert progress["pages_read"] == 80  # 50 + 30
        assert progress["current_page"] == 80  # max end_page
        assert progress["time_spent_minutes"] == 105  # 60 + 45
        assert progress["sessions_count"] == 2
        assert progress["progress_percent"] == 26  # 80/300 * 100

    def test_get_book_progress_not_found(self, tracker, mock_db):
        """Test get_book_progress with invalid book ID."""
        mock_session = MagicMock()
        mock_session.get.return_value = None

        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="Book not found"):
            tracker.get_book_progress("invalid-id")

    def test_get_book_progress_no_page_count(self, tracker, mock_db):
        """Test progress when book has no page count."""
        mock_book = MagicMock()
        mock_book.title = "Test Book"
        mock_book.page_count = None

        mock_log = MagicMock()
        mock_log.pages_read = 50
        mock_log.end_page = None
        mock_log.duration_minutes = 60

        mock_session = MagicMock()
        mock_session.get.return_value = mock_book
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_log]

        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        progress = tracker.get_book_progress("book-123")

        assert progress["total_pages"] is None
        assert progress["progress_percent"] == 0
        assert progress["estimated_time_remaining"] is None

    def test_get_reading_history(self, tracker, mock_db):
        """Test getting reading history."""
        mock_book = MagicMock()
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"

        mock_log = MagicMock()
        mock_log.id = "log-123"
        mock_log.book_id = "book-123"
        mock_log.date = "2025-01-15"
        mock_log.pages_read = 30
        mock_log.start_page = 10
        mock_log.end_page = 40
        mock_log.duration_minutes = 45
        mock_log.location = "home"
        mock_log.notes = "Good chapter"

        mock_session = MagicMock()
        mock_session.execute.return_value.all.return_value = [(mock_log, mock_book)]

        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        history = tracker.get_reading_history()

        assert len(history) == 1
        assert history[0]["book_title"] == "Test Book"
        assert history[0]["pages_read"] == 30
        assert history[0]["location"] == "home"

    def test_get_stats_empty(self, tracker, mock_db):
        """Test get_stats with no reading logs."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        stats = tracker.get_stats()

        assert stats.total_pages == 0
        assert stats.total_sessions == 0

    def test_get_stats_with_logs(self, tracker, mock_db):
        """Test get_stats with reading logs."""
        mock_log1 = MagicMock()
        mock_log1.book_id = "book-1"
        mock_log1.pages_read = 50
        mock_log1.duration_minutes = 60
        mock_log1.location = "home"
        mock_log1.date = (date.today() - timedelta(days=1)).isoformat()

        mock_log2 = MagicMock()
        mock_log2.book_id = "book-1"
        mock_log2.pages_read = 30
        mock_log2.duration_minutes = 45
        mock_log2.location = "commute"
        mock_log2.date = date.today().isoformat()

        mock_session = MagicMock()
        # First call for reading logs, second for finished books
        mock_session.execute.return_value.scalars.return_value.all.side_effect = [
            [mock_log1, mock_log2],  # Reading logs
            [],  # Finished books
        ]

        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        stats = tracker.get_stats()

        assert stats.total_pages == 80  # 50 + 30
        assert stats.total_minutes == 105  # 60 + 45
        assert stats.total_sessions == 2
        assert stats.total_books == 1  # Same book
        assert stats.avg_pages_per_session == 40.0  # 80 / 2
        assert stats.pages_by_location["home"] == 50
        assert stats.pages_by_location["commute"] == 30

    def test_get_currently_reading(self, tracker, mock_db):
        """Test getting currently reading books."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.page_count = 300
        mock_book.progress = "25%"

        mock_log = MagicMock()
        mock_log.end_page = 75
        mock_log.date = "2025-01-15"

        mock_session = MagicMock()
        # First call for books, second for latest log
        mock_session.execute.side_effect = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_book])))),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_log)),
        ]

        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        currently_reading = tracker.get_currently_reading()

        assert len(currently_reading) == 1
        assert currently_reading[0]["title"] == "Test Book"
        assert currently_reading[0]["current_page"] == 75
        assert currently_reading[0]["progress_percent"] == 25


class TestCalculateReadingSpeed:
    """Tests for calculate_reading_speed function."""

    def test_normal_speed(self):
        """Test calculating reading speed."""
        # 60 pages in 60 minutes = 60 pages/hour
        speed = calculate_reading_speed(pages=60, minutes=60)
        assert speed == 60.0

    def test_faster_speed(self):
        """Test faster reading speed."""
        # 30 pages in 15 minutes = 120 pages/hour
        speed = calculate_reading_speed(pages=30, minutes=15)
        assert speed == 120.0

    def test_zero_minutes(self):
        """Test with zero minutes."""
        speed = calculate_reading_speed(pages=50, minutes=0)
        assert speed == 0.0

    def test_negative_minutes(self):
        """Test with negative minutes."""
        speed = calculate_reading_speed(pages=50, minutes=-10)
        assert speed == 0.0


class TestStreakCalculation:
    """Tests for streak calculation logic."""

    @pytest.fixture
    def tracker(self):
        """Create a tracker for testing."""
        return ProgressTracker(db=MagicMock())

    def test_no_logs_no_streak(self, tracker):
        """Test streak is 0 with no logs."""
        current, longest = tracker._calculate_streaks([], date.today())

        assert current == 0
        assert longest == 0

    def test_single_day_streak(self, tracker):
        """Test streak with single day."""
        mock_log = MagicMock()
        mock_log.date = date.today().isoformat()

        current, longest = tracker._calculate_streaks([mock_log], date.today())

        assert current == 1
        assert longest == 1

    def test_consecutive_days_streak(self, tracker):
        """Test streak with consecutive days."""
        logs = []
        for i in range(5):
            log = MagicMock()
            log.date = (date.today() - timedelta(days=i)).isoformat()
            logs.append(log)

        current, longest = tracker._calculate_streaks(logs, date.today())

        assert current == 5
        assert longest == 5

    def test_broken_streak(self, tracker):
        """Test streak calculation with gap."""
        logs = []
        # Read today and yesterday
        logs.append(MagicMock(date=date.today().isoformat()))
        logs.append(MagicMock(date=(date.today() - timedelta(days=1)).isoformat()))
        # Gap of 2 days, then 3 consecutive days
        logs.append(MagicMock(date=(date.today() - timedelta(days=4)).isoformat()))
        logs.append(MagicMock(date=(date.today() - timedelta(days=5)).isoformat()))
        logs.append(MagicMock(date=(date.today() - timedelta(days=6)).isoformat()))

        current, longest = tracker._calculate_streaks(logs, date.today())

        assert current == 2  # Today and yesterday
        assert longest == 3  # The older 3-day streak

    def test_streak_allows_yesterday(self, tracker):
        """Test that streak counts if last read was yesterday."""
        mock_log = MagicMock()
        mock_log.date = (date.today() - timedelta(days=1)).isoformat()

        current, longest = tracker._calculate_streaks([mock_log], date.today())

        assert current == 1  # Still counts as current streak
