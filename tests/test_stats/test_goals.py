"""Tests for reading goals."""

import pytest
from datetime import date, timedelta
from pathlib import Path
import json

from vibecoding.booktracker.stats.goals import (
    ReadingGoal,
    GoalTracker,
    GoalType,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus, ReadingLogCreate


class TestGoalType:
    """Tests for GoalType enum."""

    def test_goal_types(self):
        """Test goal type values."""
        assert GoalType.BOOKS.value == "books"
        assert GoalType.PAGES.value == "pages"
        assert GoalType.MINUTES.value == "minutes"

    def test_from_string(self):
        """Test creating from string."""
        assert GoalType("books") == GoalType.BOOKS
        assert GoalType("pages") == GoalType.PAGES
        assert GoalType("minutes") == GoalType.MINUTES


class TestReadingGoal:
    """Tests for ReadingGoal dataclass."""

    def test_default_values(self):
        """Test default values."""
        goal = ReadingGoal(
            goal_type=GoalType.BOOKS,
            target=12,
            year=2025,
        )
        assert goal.goal_type == GoalType.BOOKS
        assert goal.target == 12
        assert goal.year == 2025
        assert goal.month is None
        assert goal.current == 0

    def test_progress_percent_zero_target(self):
        """Test progress with zero target."""
        goal = ReadingGoal(GoalType.BOOKS, 0, 2025)
        assert goal.progress_percent == 0.0

    def test_progress_percent_partial(self):
        """Test partial progress."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, current=5)
        assert goal.progress_percent == 50.0

    def test_progress_percent_complete(self):
        """Test complete progress."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, current=10)
        assert goal.progress_percent == 100.0

    def test_progress_percent_over_target(self):
        """Test progress over target (capped at 100%)."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, current=15)
        assert goal.progress_percent == 100.0

    def test_remaining(self):
        """Test remaining calculation."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, current=3)
        assert goal.remaining == 7

    def test_remaining_complete(self):
        """Test remaining when complete."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, current=10)
        assert goal.remaining == 0

    def test_remaining_over_target(self):
        """Test remaining when over target."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, current=15)
        assert goal.remaining == 0

    def test_is_complete_false(self):
        """Test is_complete when not complete."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, current=5)
        assert goal.is_complete is False

    def test_is_complete_true(self):
        """Test is_complete when complete."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, current=10)
        assert goal.is_complete is True

    def test_is_complete_over(self):
        """Test is_complete when over target."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, current=15)
        assert goal.is_complete is True

    def test_period_label_yearly(self):
        """Test yearly period label."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025)
        assert goal.period_label == "2025"

    def test_period_label_monthly(self):
        """Test monthly period label."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, month=3)
        assert goal.period_label == "March 2025"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        goal = ReadingGoal(GoalType.BOOKS, 10, 2025, month=6)
        d = goal.to_dict()

        assert d["goal_type"] == "books"
        assert d["target"] == 10
        assert d["year"] == 2025
        assert d["month"] == 6
        assert "created_at" in d

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "goal_type": "pages",
            "target": 5000,
            "year": 2025,
            "month": None,
            "created_at": "2025-01-01T00:00:00",
        }
        goal = ReadingGoal.from_dict(data)

        assert goal.goal_type == GoalType.PAGES
        assert goal.target == 5000
        assert goal.year == 2025
        assert goal.month is None

    def test_roundtrip(self):
        """Test to_dict and from_dict roundtrip."""
        original = ReadingGoal(GoalType.MINUTES, 1000, 2025, month=9)
        data = original.to_dict()
        restored = ReadingGoal.from_dict(data)

        assert restored.goal_type == original.goal_type
        assert restored.target == original.target
        assert restored.year == original.year
        assert restored.month == original.month


class TestGoalTracker:
    """Tests for GoalTracker class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def goals_file(self, tmp_path):
        """Create a temporary goals file path."""
        return tmp_path / "goals.json"

    @pytest.fixture
    def tracker(self, db, goals_file):
        """Create tracker instance."""
        return GoalTracker(db, goals_file)

    @pytest.fixture
    def sample_books(self, db):
        """Create sample completed books."""
        today = date.today()
        books = []

        for i in range(5):
            book_data = BookCreate(
                title=f"Test Book {i+1}",
                author="Test Author",
                status=BookStatus.COMPLETED,
                page_count=250,
                date_finished=(today - timedelta(days=i)).isoformat(),
            )
            book = db.create_book(book_data)
            books.append(book)

        return books

    @pytest.fixture
    def sample_logs(self, db, sample_books):
        """Create sample reading logs."""
        today = date.today()
        logs = []

        for i in range(10):
            log_data = ReadingLogCreate(
                book_id=sample_books[0].id,
                date=(today - timedelta(days=i)).isoformat(),
                pages_read=50,
                duration_minutes=60,
            )
            with db.get_session() as session:
                log = db.create_reading_log(log_data, session)
                logs.append(log)

        return logs

    def test_set_goal_books(self, tracker):
        """Test setting a books goal."""
        goal = tracker.set_goal(GoalType.BOOKS, 12)

        assert goal.goal_type == GoalType.BOOKS
        assert goal.target == 12
        assert goal.year == date.today().year

    def test_set_goal_pages(self, tracker):
        """Test setting a pages goal."""
        goal = tracker.set_goal(GoalType.PAGES, 5000, year=2025)

        assert goal.goal_type == GoalType.PAGES
        assert goal.target == 5000
        assert goal.year == 2025

    def test_set_goal_monthly(self, tracker):
        """Test setting a monthly goal."""
        goal = tracker.set_goal(GoalType.BOOKS, 3, year=2025, month=6)

        assert goal.goal_type == GoalType.BOOKS
        assert goal.target == 3
        assert goal.month == 6

    def test_set_goal_replaces_existing(self, tracker):
        """Test that setting goal replaces existing for same period."""
        tracker.set_goal(GoalType.BOOKS, 10)
        tracker.set_goal(GoalType.BOOKS, 12)

        goals = tracker.get_all_goals()
        book_goals = [g for g in goals if g.goal_type == GoalType.BOOKS and g.month is None]
        assert len(book_goals) == 1
        assert book_goals[0].target == 12

    def test_set_goal_persists(self, db, goals_file):
        """Test that goals are persisted."""
        tracker1 = GoalTracker(db, goals_file)
        tracker1.set_goal(GoalType.BOOKS, 10)

        # Create new tracker instance
        tracker2 = GoalTracker(db, goals_file)
        goals = tracker2.get_all_goals()

        assert len(goals) == 1
        assert goals[0].target == 10

    def test_get_goal_found(self, tracker):
        """Test getting existing goal."""
        tracker.set_goal(GoalType.BOOKS, 10, year=2025)
        goal = tracker.get_goal(GoalType.BOOKS, year=2025)

        assert goal is not None
        assert goal.target == 10

    def test_get_goal_not_found(self, tracker):
        """Test getting non-existent goal."""
        goal = tracker.get_goal(GoalType.PAGES, year=2025)
        assert goal is None

    def test_get_goal_monthly(self, tracker):
        """Test getting monthly goal."""
        tracker.set_goal(GoalType.BOOKS, 3, year=2025, month=6)
        goal = tracker.get_goal(GoalType.BOOKS, year=2025, month=6)

        assert goal is not None
        assert goal.target == 3

    def test_get_current_goals(self, tracker):
        """Test getting current goals."""
        today = date.today()
        tracker.set_goal(GoalType.BOOKS, 12, year=today.year)
        tracker.set_goal(GoalType.PAGES, 5000, year=today.year)
        tracker.set_goal(GoalType.BOOKS, 10, year=today.year - 1)  # Old goal

        goals = tracker.get_current_goals()

        # Should only have current year goals
        assert len(goals) >= 2
        assert all(g.year == today.year for g in goals)

    def test_get_current_goals_includes_monthly(self, tracker):
        """Test that current goals includes current month goals."""
        today = date.today()
        tracker.set_goal(GoalType.BOOKS, 12, year=today.year)
        tracker.set_goal(GoalType.BOOKS, 3, year=today.year, month=today.month)

        goals = tracker.get_current_goals()

        # Should include both yearly and current month
        assert len(goals) >= 2

    def test_get_all_goals(self, tracker):
        """Test getting all goals."""
        tracker.set_goal(GoalType.BOOKS, 12, year=2025)
        tracker.set_goal(GoalType.PAGES, 5000, year=2025)
        tracker.set_goal(GoalType.BOOKS, 10, year=2024)

        goals = tracker.get_all_goals()

        assert len(goals) == 3

    def test_delete_goal_success(self, tracker):
        """Test deleting a goal."""
        tracker.set_goal(GoalType.BOOKS, 12, year=2025)
        result = tracker.delete_goal(GoalType.BOOKS, 2025)

        assert result is True
        assert tracker.get_goal(GoalType.BOOKS, year=2025) is None

    def test_delete_goal_not_found(self, tracker):
        """Test deleting non-existent goal."""
        result = tracker.delete_goal(GoalType.BOOKS, 2025)
        assert result is False

    def test_delete_goal_monthly(self, tracker):
        """Test deleting monthly goal."""
        tracker.set_goal(GoalType.BOOKS, 3, year=2025, month=6)
        result = tracker.delete_goal(GoalType.BOOKS, 2025, month=6)

        assert result is True

    def test_goal_progress_books(self, tracker, sample_books):
        """Test that goal progress updates from database."""
        goal = tracker.set_goal(GoalType.BOOKS, 10)

        # Progress should reflect completed books
        assert goal.current == 5

    def test_goal_progress_pages(self, tracker, sample_books, sample_logs):
        """Test pages goal progress."""
        goal = tracker.set_goal(GoalType.PAGES, 1000)

        # Progress should reflect pages from logs
        assert goal.current >= 500  # 10 logs * 50 pages

    def test_goal_progress_minutes(self, tracker, sample_books, sample_logs):
        """Test minutes goal progress."""
        goal = tracker.set_goal(GoalType.MINUTES, 1000)

        # Progress should reflect minutes from logs
        assert goal.current >= 600  # 10 logs * 60 minutes

    def test_get_progress_summary(self, tracker, sample_books):
        """Test progress summary."""
        today = date.today()
        tracker.set_goal(GoalType.BOOKS, 10, year=today.year)

        summary = tracker.get_progress_summary()

        assert "goals" in summary
        assert "on_track_count" in summary
        assert "behind_count" in summary
        assert "complete_count" in summary

    def test_calculate_required_pace(self, tracker, sample_books):
        """Test pace calculation."""
        goal = tracker.set_goal(GoalType.BOOKS, 20)
        pace = tracker.calculate_required_pace(goal)

        assert "remaining" in pace
        assert "remaining_days" in pace
        assert "per_day" in pace
        assert "per_week" in pace
        assert "unit" in pace
        assert "is_achievable" in pace

    def test_calculate_required_pace_complete(self, tracker, sample_books):
        """Test pace for completed goal."""
        goal = tracker.set_goal(GoalType.BOOKS, 3)  # Already have 5 books
        pace = tracker.calculate_required_pace(goal)

        assert pace["remaining"] == 0
        assert pace["per_day"] == 0

    def test_calculate_required_pace_monthly(self, tracker, sample_books):
        """Test pace for monthly goal."""
        today = date.today()
        goal = tracker.set_goal(GoalType.BOOKS, 10, year=today.year, month=today.month)
        pace = tracker.calculate_required_pace(goal)

        assert pace["remaining_days"] >= 0
        assert pace["remaining_days"] <= 31

    def test_load_corrupted_goals_file(self, db, tmp_path):
        """Test loading corrupted goals file."""
        goals_file = tmp_path / "goals.json"
        goals_file.write_text("not valid json")

        tracker = GoalTracker(db, goals_file)
        goals = tracker.get_all_goals()

        # Should handle gracefully
        assert goals == []

    def test_goal_different_types_same_period(self, tracker):
        """Test multiple goal types for same period."""
        tracker.set_goal(GoalType.BOOKS, 12)
        tracker.set_goal(GoalType.PAGES, 5000)
        tracker.set_goal(GoalType.MINUTES, 6000)

        goals = tracker.get_current_goals()

        # Should have all three
        types = {g.goal_type for g in goals}
        assert GoalType.BOOKS in types
        assert GoalType.PAGES in types
        assert GoalType.MINUTES in types

    def test_goal_status_on_track(self, tracker, sample_books):
        """Test on-track status calculation."""
        # Set a low goal that should be on track
        today = date.today()
        tracker.set_goal(GoalType.BOOKS, 1, year=today.year)

        summary = tracker.get_progress_summary()

        # Should be complete or on track
        assert summary["complete_count"] > 0 or summary["on_track_count"] > 0
