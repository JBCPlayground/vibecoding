"""Tests for StreakManager."""

import pytest
from datetime import date, timedelta

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.streaks.manager import StreakManager
from vibecoding.booktracker.streaks.schemas import StreakStatus


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a StreakManager with test database."""
    return StreakManager(db)


class TestDailyReadingLogging:
    """Tests for daily reading logging."""

    def test_log_reading_today(self, manager):
        """Test logging reading for today."""
        daily = manager.log_reading(minutes=30, pages=20)

        assert daily is not None
        assert daily.minutes_read == 30
        assert daily.pages_read == 20
        assert daily.sessions_count == 1
        assert daily.reading_date == date.today().isoformat()

    def test_log_reading_specific_date(self, manager):
        """Test logging reading for a specific date."""
        yesterday = date.today() - timedelta(days=1)
        daily = manager.log_reading(
            reading_date=yesterday,
            minutes=45,
            pages=30,
        )

        assert daily.reading_date == yesterday.isoformat()
        assert daily.minutes_read == 45

    def test_log_reading_accumulates(self, manager):
        """Test that logging accumulates for same day."""
        manager.log_reading(minutes=20, pages=10)
        daily = manager.log_reading(minutes=30, pages=15)

        assert daily.minutes_read == 50
        assert daily.pages_read == 25
        assert daily.sessions_count == 2

    def test_log_reading_with_hour(self, manager):
        """Test logging with primary reading hour."""
        daily = manager.log_reading(minutes=30, primary_hour=21)

        assert daily.primary_hour == 21

    def test_log_reading_with_notes(self, manager):
        """Test logging with notes."""
        daily = manager.log_reading(minutes=30, notes="Great reading session")

        assert daily.notes == "Great reading session"

    def test_log_reading_notes_accumulate(self, manager):
        """Test that notes accumulate."""
        manager.log_reading(minutes=20, notes="First note")
        daily = manager.log_reading(minutes=20, notes="Second note")

        assert "First note" in daily.notes
        assert "Second note" in daily.notes

    def test_get_daily_reading(self, manager):
        """Test getting daily reading for a date."""
        today = date.today()
        manager.log_reading(minutes=30)

        daily = manager.get_daily_reading(today)

        assert daily is not None
        assert daily.minutes_read == 30

    def test_get_daily_reading_not_found(self, manager):
        """Test getting daily reading for date with no reading."""
        yesterday = date.today() - timedelta(days=1)
        daily = manager.get_daily_reading(yesterday)

        assert daily is None

    def test_get_reading_history(self, manager):
        """Test getting reading history."""
        # Log reading for multiple days
        for i in range(5):
            reading_date = date.today() - timedelta(days=i)
            manager.log_reading(reading_date=reading_date, minutes=30 + i * 10)

        history = manager.get_reading_history(limit=10)

        assert len(history) == 5
        # Should be in descending order
        assert history[0].minutes_read == 30  # Today

    def test_get_reading_history_with_date_range(self, manager):
        """Test getting reading history with date range."""
        today = date.today()
        for i in range(10):
            reading_date = today - timedelta(days=i)
            manager.log_reading(reading_date=reading_date, minutes=30)

        week_ago = today - timedelta(days=7)
        history = manager.get_reading_history(
            start_date=week_ago,
            end_date=today,
            limit=30,
        )

        assert len(history) == 8  # Today + 7 days back


class TestDailyGoals:
    """Tests for daily reading goals."""

    def test_set_daily_goal_minutes(self, manager):
        """Test setting daily minutes goal."""
        daily = manager.set_daily_goal(goal_minutes=60)

        assert daily.goal_minutes == 60
        assert daily.goal_met is False

    def test_set_daily_goal_pages(self, manager):
        """Test setting daily pages goal."""
        daily = manager.set_daily_goal(goal_pages=50)

        assert daily.goal_pages == 50

    def test_goal_met_on_logging(self, manager):
        """Test goal is marked met when achieved."""
        manager.set_daily_goal(goal_minutes=30)
        daily = manager.log_reading(minutes=35)

        assert daily.goal_met is True

    def test_goal_progress(self, manager):
        """Test goal progress calculation."""
        manager.set_daily_goal(goal_minutes=60)
        daily = manager.log_reading(minutes=30)

        assert daily.goal_progress == 0.5

    def test_goal_met_before_logging(self, manager):
        """Test setting goal when already met."""
        manager.log_reading(minutes=60)
        daily = manager.set_daily_goal(goal_minutes=30)

        assert daily.goal_met is True


class TestStreakManagement:
    """Tests for streak management."""

    def test_first_reading_creates_streak(self, manager):
        """Test that first reading creates a streak."""
        manager.log_reading(minutes=30)

        streak = manager.get_current_streak()

        assert streak is not None
        assert streak.length == 1
        assert streak.is_current is True

    def test_consecutive_days_extend_streak(self, manager):
        """Test that consecutive days extend streak."""
        today = date.today()

        # Log for 3 consecutive days
        for i in range(3):
            reading_date = today - timedelta(days=2-i)  # 2 days ago, yesterday, today
            manager.log_reading(reading_date=reading_date, minutes=30)

        streak = manager.get_current_streak()

        assert streak.length == 3

    def test_gap_ends_streak(self, manager):
        """Test that a gap ends the streak."""
        today = date.today()

        # Log 3 days ago
        manager.log_reading(reading_date=today - timedelta(days=3), minutes=30)

        # Log today (gap of 2 days)
        manager.log_reading(reading_date=today, minutes=30)

        streaks = manager.get_all_streaks()

        # Should have 2 streaks
        assert len(streaks) == 2
        # Current streak should be length 1
        current = manager.get_current_streak()
        assert current.length == 1

    def test_get_longest_streak(self, manager):
        """Test getting longest streak."""
        today = date.today()

        # Create a 5-day streak ending a week ago
        for i in range(5):
            reading_date = today - timedelta(days=12-i)
            manager.log_reading(reading_date=reading_date, minutes=30)

        # Create a 3-day current streak
        for i in range(3):
            reading_date = today - timedelta(days=2-i)
            manager.log_reading(reading_date=reading_date, minutes=30)

        longest = manager.get_longest_streak()

        assert longest.length == 5

    def test_streak_tracks_totals(self, manager):
        """Test that streak tracks total minutes/pages."""
        today = date.today()

        manager.log_reading(reading_date=today - timedelta(days=1), minutes=30, pages=20)
        manager.log_reading(reading_date=today, minutes=45, pages=30)

        streak = manager.get_current_streak()

        assert streak.total_minutes == 75
        assert streak.total_pages == 50

    def test_streak_average_calculations(self, manager):
        """Test streak average calculations."""
        today = date.today()

        manager.log_reading(reading_date=today - timedelta(days=1), minutes=30, pages=20)
        manager.log_reading(reading_date=today, minutes=50, pages=40)

        streak = manager.get_current_streak()

        assert streak.average_daily_minutes == 40.0
        assert streak.average_daily_pages == 30.0


class TestStreakStatus:
    """Tests for streak status."""

    def test_status_active_after_reading_today(self, manager):
        """Test status is active after reading today."""
        manager.log_reading(minutes=30)

        status = manager.get_streak_status()

        assert status == StreakStatus.ACTIVE

    def test_status_at_risk_no_reading_today(self, manager):
        """Test status is at_risk if no reading today but read yesterday."""
        yesterday = date.today() - timedelta(days=1)
        manager.log_reading(reading_date=yesterday, minutes=30)

        status = manager.get_streak_status()

        assert status == StreakStatus.AT_RISK

    def test_status_ended_no_streak(self, manager):
        """Test status is ended when no current streak."""
        status = manager.get_streak_status()

        assert status == StreakStatus.ENDED


class TestStatistics:
    """Tests for streak statistics."""

    def test_get_stats_empty(self, manager):
        """Test stats with no data."""
        stats = manager.get_stats()

        assert stats.current_streak == 0
        assert stats.longest_streak == 0
        assert stats.total_reading_days == 0
        assert stats.streak_status == StreakStatus.ENDED

    def test_get_stats_with_data(self, manager):
        """Test stats with reading data."""
        today = date.today()

        # Create a 5-day streak
        for i in range(5):
            reading_date = today - timedelta(days=4-i)
            manager.log_reading(
                reading_date=reading_date,
                minutes=30 + i * 10,
                pages=20 + i * 5,
            )

        stats = manager.get_stats()

        assert stats.current_streak == 5
        assert stats.longest_streak == 5
        assert stats.total_reading_days == 5
        assert stats.total_streaks == 1
        assert stats.current_streak_minutes == 250  # 30+40+50+60+70
        assert stats.average_daily_minutes > 0

    def test_best_day_tracking(self, manager):
        """Test best day is tracked correctly."""
        today = date.today()

        manager.log_reading(reading_date=today - timedelta(days=1), minutes=30, pages=20)
        manager.log_reading(reading_date=today, minutes=120, pages=80)

        stats = manager.get_stats()

        assert stats.best_day_minutes == 120
        assert stats.best_day_pages == 80
        assert stats.best_day_date == today


class TestHabitAnalysis:
    """Tests for reading habit analysis."""

    def test_get_reading_habits_empty(self, manager):
        """Test habits analysis with no data."""
        habits = manager.get_reading_habits()

        assert habits.reading_days_this_week == 0
        assert habits.reading_days_this_month == 0
        assert habits.consistency_score == 0

    def test_get_reading_habits_with_data(self, manager):
        """Test habits analysis with reading data."""
        today = date.today()

        # Log reading for multiple days with different hours
        for i in range(7):
            reading_date = today - timedelta(days=i)
            hour = 8 if i < 3 else 21  # Morning vs evening
            manager.log_reading(
                reading_date=reading_date,
                minutes=30,
                primary_hour=hour,
            )

        habits = manager.get_reading_habits()

        assert habits.reading_days_this_week == 7
        assert habits.consistency_score > 0
        assert len(habits.weekday_stats) == 7
        assert habits.most_productive_hour is not None

    def test_weekday_stats(self, manager):
        """Test weekday statistics."""
        today = date.today()

        # Log reading ensuring we hit multiple weekdays
        for i in range(14):
            reading_date = today - timedelta(days=i)
            manager.log_reading(reading_date=reading_date, minutes=30)

        habits = manager.get_reading_habits()

        # Should have stats for all weekdays
        assert len(habits.weekday_stats) == 7
        # At least some weekdays should have reading
        reading_weekdays = [ws for ws in habits.weekday_stats if ws.total_days > 0]
        assert len(reading_weekdays) == 7


class TestMilestones:
    """Tests for milestone achievements."""

    def test_get_milestones_none_achieved(self, manager):
        """Test milestones with no reading."""
        milestones = manager.get_milestones()

        assert len(milestones) > 0
        assert all(not m.achieved for m in milestones)

    def test_first_milestone_achieved(self, manager):
        """Test first milestone (1 day) is achieved."""
        manager.log_reading(minutes=30)

        milestones = manager.get_milestones()

        first = milestones[0]
        assert first.name == "First Step"
        assert first.achieved is True
        assert first.achieved_date is not None

    def test_week_milestone_achieved(self, manager):
        """Test 7-day milestone is achieved."""
        today = date.today()

        for i in range(7):
            reading_date = today - timedelta(days=6-i)
            manager.log_reading(reading_date=reading_date, minutes=30)

        milestones = manager.get_milestones()

        week_milestone = next(m for m in milestones if m.days_required == 7)
        assert week_milestone.achieved is True


class TestCalendar:
    """Tests for calendar view."""

    def test_get_calendar_current_month(self, manager):
        """Test getting calendar for current month."""
        today = date.today()

        # Log some reading this month
        manager.log_reading(minutes=30)

        cal = manager.get_calendar(today.year, today.month)

        assert cal.year == today.year
        assert cal.month == today.month
        assert cal.total_reading_days >= 1
        assert cal.days.get(today.day, False) is True

    def test_get_calendar_tracks_streak_days(self, manager):
        """Test calendar tracks streak lengths."""
        today = date.today()

        # Create a 3-day streak
        for i in range(3):
            reading_date = today - timedelta(days=2-i)
            if reading_date.month == today.month:
                manager.log_reading(reading_date=reading_date, minutes=30)

        cal = manager.get_calendar(today.year, today.month)

        # Today should show streak of 3 (if all in same month)
        if (today - timedelta(days=2)).month == today.month:
            assert cal.streak_days.get(today.day, 0) == 3

    def test_get_calendar_totals(self, manager):
        """Test calendar totals."""
        today = date.today()

        # Log reading
        manager.log_reading(minutes=60, pages=40)

        cal = manager.get_calendar(today.year, today.month)

        assert cal.total_minutes >= 60
        assert cal.total_pages >= 40


class TestModelProperties:
    """Tests for model properties."""

    def test_daily_reading_weekday_name(self, manager):
        """Test weekday name property."""
        # Monday = 0
        monday = date.today()
        while monday.weekday() != 0:
            monday -= timedelta(days=1)

        manager.log_reading(reading_date=monday, minutes=30)
        daily = manager.get_daily_reading(monday)

        assert daily.weekday_name == "Monday"

    def test_streak_is_active(self, manager):
        """Test streak is_active property."""
        manager.log_reading(minutes=30)

        streak = manager.get_current_streak()

        assert streak.is_active is True

    def test_streak_not_active_when_ended(self, manager):
        """Test streak is_active is False when ended."""
        # Create and end a streak
        three_days_ago = date.today() - timedelta(days=3)
        manager.log_reading(reading_date=three_days_ago, minutes=30)

        # Start a new streak (gaps the old one)
        manager.log_reading(minutes=30)

        streaks = manager.get_all_streaks()
        ended_streak = next(s for s in streaks if not s.is_current)

        assert ended_streak.is_active is False
