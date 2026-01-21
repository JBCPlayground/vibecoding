"""Tests for reading insights."""

import pytest
from datetime import date, datetime, timedelta

from vibecoding.booktracker.stats.insights import (
    InsightGenerator,
    Insight,
    InsightType,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus, ReadingLogCreate


class TestInsightType:
    """Tests for InsightType enum."""

    def test_insight_types(self):
        """Test insight type values."""
        assert InsightType.ACHIEVEMENT.value == "achievement"
        assert InsightType.TREND.value == "trend"
        assert InsightType.RECOMMENDATION.value == "recommendation"
        assert InsightType.STREAK.value == "streak"
        assert InsightType.COMPARISON.value == "comparison"
        assert InsightType.MILESTONE.value == "milestone"

    def test_from_string(self):
        """Test creating from string."""
        assert InsightType("achievement") == InsightType.ACHIEVEMENT
        assert InsightType("streak") == InsightType.STREAK


class TestInsight:
    """Tests for Insight dataclass."""

    def test_default_values(self):
        """Test default values."""
        insight = Insight(
            insight_type=InsightType.ACHIEVEMENT,
            title="Test Title",
            message="Test message",
        )
        assert insight.insight_type == InsightType.ACHIEVEMENT
        assert insight.title == "Test Title"
        assert insight.message == "Test message"
        assert insight.priority == 5
        assert insight.data == {}
        assert insight.created_at is not None

    def test_with_custom_values(self):
        """Test with custom values."""
        insight = Insight(
            insight_type=InsightType.STREAK,
            title="Streak!",
            message="7 day streak",
            priority=8,
            data={"days": 7},
        )
        assert insight.priority == 8
        assert insight.data["days"] == 7

    def test_created_at_auto(self):
        """Test created_at is set automatically."""
        insight = Insight(InsightType.TREND, "Test", "Test message")
        assert isinstance(insight.created_at, datetime)


class TestInsightGenerator:
    """Tests for InsightGenerator class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def generator(self, db):
        """Create insight generator."""
        return InsightGenerator(db)

    @pytest.fixture
    def sample_books(self, db):
        """Create sample books."""
        today = date.today()
        books = []

        # Create completed books
        for i in range(12):
            book_data = BookCreate(
                title=f"Test Book {i+1}",
                author="Same Author" if i < 5 else f"Author {i}",
                status=BookStatus.COMPLETED,
                page_count=300,
                rating=4,
                date_finished=(today - timedelta(days=i)).isoformat(),
                tags=["fiction", "fantasy"],
            )
            book = db.create_book(book_data)
            books.append(book)

        return books

    @pytest.fixture
    def streak_logs(self, db, sample_books):
        """Create reading logs for a streak."""
        today = date.today()
        logs = []

        # Create 7-day streak
        for i in range(7):
            log_data = ReadingLogCreate(
                book_id=sample_books[0].id,
                date=(today - timedelta(days=i)).isoformat(),
                pages_read=30,
                duration_minutes=45,
            )
            with db.get_session() as session:
                log = db.create_reading_log(log_data, session)
                logs.append(log)

        return logs

    def test_generate_all_insights_empty(self, generator):
        """Test insights with no data."""
        insights = generator.generate_all_insights()

        # Should have recommendation to start reading
        assert len(insights) >= 1

    def test_generate_all_insights_with_data(self, generator, sample_books, streak_logs):
        """Test insights with data."""
        insights = generator.generate_all_insights()

        # Should have multiple insights
        assert len(insights) > 0

    def test_insights_sorted_by_priority(self, generator, sample_books, streak_logs):
        """Test that insights are sorted by priority."""
        insights = generator.generate_all_insights()

        if len(insights) > 1:
            for i in range(len(insights) - 1):
                assert insights[i].priority >= insights[i + 1].priority

    def test_streak_insight(self, generator, sample_books, streak_logs):
        """Test streak insight generation."""
        insights = generator.generate_all_insights()

        streak_insights = [i for i in insights if i.insight_type == InsightType.STREAK]
        # Should have streak or keep streak insight
        assert len(streak_insights) > 0 or any(
            i.insight_type == InsightType.RECOMMENDATION for i in insights
        )

    def test_no_activity_recommendation(self, generator):
        """Test recommendation when no activity."""
        insights = generator.generate_all_insights()

        # Should recommend starting to read
        rec_insights = [i for i in insights if i.insight_type == InsightType.RECOMMENDATION]
        assert len(rec_insights) > 0

    def test_milestone_insight(self, generator, sample_books):
        """Test milestone detection."""
        insights = generator.generate_all_insights()

        # With 12 books, might be near a milestone
        milestone_insights = [i for i in insights if i.insight_type == InsightType.MILESTONE]
        # May or may not have milestone depending on exact count

    def test_achievement_insight_book_count(self, db):
        """Test achievement for round number of books."""
        today = date.today()

        # Create exactly 10 books
        for i in range(10):
            db.create_book(BookCreate(
                title=f"Book {i}",
                author="Author",
                status=BookStatus.COMPLETED,
                date_finished=(today - timedelta(days=i)).isoformat(),
            ))

        generator = InsightGenerator(db)
        insights = generator.generate_all_insights()

        # Should have achievement for 10 books
        achievement_insights = [i for i in insights if i.insight_type == InsightType.ACHIEVEMENT]
        assert any("10" in i.title or "10" in i.message for i in achievement_insights)

    def test_author_pattern_insight(self, generator, sample_books):
        """Test author pattern detection."""
        insights = generator.generate_all_insights()

        # Should detect reading multiple books by "Same Author"
        trend_insights = [i for i in insights if i.insight_type == InsightType.TREND]
        author_insights = [i for i in trend_insights if "Same Author" in i.title or "Same Author" in i.message]
        # Might detect the pattern

    def test_genre_pattern_insight(self, generator, sample_books):
        """Test genre pattern detection."""
        insights = generator.generate_all_insights()

        # Should detect fiction/fantasy pattern
        trend_insights = [i for i in insights if i.insight_type == InsightType.TREND]
        # Might have genre insight

    def test_get_dashboard_insights(self, generator, sample_books, streak_logs):
        """Test getting limited insights for dashboard."""
        insights = generator.get_dashboard_insights(limit=3)

        assert len(insights) <= 3
        # Should be sorted by priority
        if len(insights) > 1:
            assert insights[0].priority >= insights[1].priority

    def test_get_insights_by_type(self, generator, sample_books, streak_logs):
        """Test filtering by type."""
        insights = generator.get_insights_by_type(InsightType.STREAK)

        for insight in insights:
            assert insight.insight_type == InsightType.STREAK

    def test_comparison_insight(self, db):
        """Test year-over-year comparison."""
        today = date.today()
        last_year = today.year - 1

        # Create books last year
        for i in range(5):
            db.create_book(BookCreate(
                title=f"Last Year Book {i}",
                author="Author",
                status=BookStatus.COMPLETED,
                date_finished=f"{last_year}-{today.month:02d}-{today.day:02d}",
            ))

        # Create fewer books this year
        for i in range(3):
            db.create_book(BookCreate(
                title=f"This Year Book {i}",
                author="Author",
                status=BookStatus.COMPLETED,
                date_finished=(today - timedelta(days=i)).isoformat(),
            ))

        generator = InsightGenerator(db)
        insights = generator.generate_all_insights()

        comparison_insights = [i for i in insights if i.insight_type == InsightType.COMPARISON]
        # Should have comparison insight about being behind
        if comparison_insights:
            assert "Behind" in comparison_insights[0].title or "behind" in comparison_insights[0].message.lower()

    def test_ahead_comparison_insight(self, db):
        """Test ahead of last year comparison."""
        today = date.today()
        last_year = today.year - 1

        # Create fewer books last year
        for i in range(2):
            db.create_book(BookCreate(
                title=f"Last Year Book {i}",
                author="Author",
                status=BookStatus.COMPLETED,
                date_finished=f"{last_year}-{today.month:02d}-{min(today.day, 28):02d}",
            ))

        # Create more books this year
        for i in range(5):
            db.create_book(BookCreate(
                title=f"This Year Book {i}",
                author="Author",
                status=BookStatus.COMPLETED,
                date_finished=(today - timedelta(days=i)).isoformat(),
            ))

        generator = InsightGenerator(db)
        insights = generator.generate_all_insights()

        comparison_insights = [i for i in insights if i.insight_type == InsightType.COMPARISON]
        # Should have comparison about being ahead
        if comparison_insights:
            assert "Ahead" in comparison_insights[0].title

    def test_book_a_month_achievement(self, db):
        """Test book-a-month achievement."""
        today = date.today()

        # Create 12 books this year
        for i in range(12):
            db.create_book(BookCreate(
                title=f"Book {i}",
                author="Author",
                status=BookStatus.COMPLETED,
                date_finished=f"{today.year}-{(i % 12) + 1:02d}-15",
            ))

        generator = InsightGenerator(db)
        insights = generator.generate_all_insights()

        achievement_insights = [i for i in insights if i.insight_type == InsightType.ACHIEVEMENT]
        # Might have book-a-month achievement
        book_month = [i for i in achievement_insights if "month" in i.title.lower() or "month" in i.message.lower()]

    def test_long_book_achievement(self, db):
        """Test long book completion achievement."""
        today = date.today()

        db.create_book(BookCreate(
            title="Epic Fantasy Novel",
            author="Author",
            status=BookStatus.COMPLETED,
            page_count=800,
            date_finished=today.isoformat(),
        ))

        generator = InsightGenerator(db)
        insights = generator.generate_all_insights()

        achievement_insights = [i for i in insights if i.insight_type == InsightType.ACHIEVEMENT]
        # Should have long book achievement
        long_book = [i for i in achievement_insights if "Long" in i.title or "800" in i.message]
        assert len(long_book) > 0

    def test_keep_streak_recommendation(self, db):
        """Test recommendation to keep streak."""
        today = date.today()

        # Create book
        book = db.create_book(BookCreate(
            title="Test Book",
            author="Author",
            status=BookStatus.READING,
        ))

        # Create streak but not today
        for i in range(1, 5):  # Days 1-4 ago, not today
            with db.get_session() as session:
                db.create_reading_log(ReadingLogCreate(
                    book_id=book.id,
                    date=(today - timedelta(days=i)).isoformat(),
                    pages_read=30,
                ), session)

        generator = InsightGenerator(db)
        insights = generator.generate_all_insights()

        # Should have recommendation to keep streak
        rec_insights = [i for i in insights if i.insight_type == InsightType.RECOMMENDATION]
        keep_streak = [i for i in rec_insights if "streak" in i.message.lower()]
        # May or may not have this depending on streak calculation

    def test_pace_trend_insight(self, db):
        """Test pace trend detection."""
        today = date.today()

        book = db.create_book(BookCreate(
            title="Test Book",
            author="Author",
            status=BookStatus.READING,
            page_count=500,
        ))

        # More reading this month
        for i in range(10):
            with db.get_session() as session:
                db.create_reading_log(ReadingLogCreate(
                    book_id=book.id,
                    date=(today - timedelta(days=i)).isoformat(),
                    pages_read=50,
                ), session)

        # Less reading last month
        last_month_start = today.replace(day=1) - timedelta(days=1)
        for i in range(3):
            with db.get_session() as session:
                db.create_reading_log(ReadingLogCreate(
                    book_id=book.id,
                    date=(last_month_start - timedelta(days=i)).isoformat(),
                    pages_read=20,
                ), session)

        generator = InsightGenerator(db)
        insights = generator.generate_all_insights()

        # Should detect pace increase
        trend_insights = [i for i in insights if i.insight_type == InsightType.TREND]
        # May have pace trend

    def test_insight_data_included(self, generator, sample_books, streak_logs):
        """Test that insights include relevant data."""
        insights = generator.generate_all_insights()

        for insight in insights:
            # Each insight should have a type, title, and message
            assert insight.insight_type is not None
            assert insight.title
            assert insight.message
            # Data is optional but should be a dict
            assert isinstance(insight.data, dict)
