"""Tests for reading analytics."""

import pytest
from datetime import date, timedelta
from uuid import uuid4

from vibecoding.booktracker.stats.analytics import (
    ReadingAnalytics,
    YearlyStats,
    MonthlyStats,
    AuthorStats,
    GenreStats,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus, ReadingLogCreate


class TestYearlyStats:
    """Tests for YearlyStats dataclass."""

    def test_default_values(self):
        """Test default values."""
        stats = YearlyStats(year=2025)
        assert stats.year == 2025
        assert stats.books_finished == 0
        assert stats.books_started == 0
        assert stats.total_pages == 0
        assert stats.avg_rating == 0.0
        assert stats.books_by_month == {}
        assert stats.top_authors == []

    def test_with_values(self):
        """Test with custom values."""
        stats = YearlyStats(
            year=2025,
            books_finished=12,
            total_pages=3600,
            avg_rating=4.2,
        )
        assert stats.books_finished == 12
        assert stats.total_pages == 3600
        assert stats.avg_rating == 4.2


class TestMonthlyStats:
    """Tests for MonthlyStats dataclass."""

    def test_default_values(self):
        """Test default values."""
        stats = MonthlyStats(year=2025, month=3)
        assert stats.year == 2025
        assert stats.month == 3
        assert stats.books_finished == 0
        assert stats.pages_read == 0

    def test_with_values(self):
        """Test with custom values."""
        stats = MonthlyStats(
            year=2025,
            month=6,
            books_finished=3,
            pages_read=800,
            reading_sessions=15,
        )
        assert stats.books_finished == 3
        assert stats.pages_read == 800
        assert stats.reading_sessions == 15


class TestAuthorStats:
    """Tests for AuthorStats dataclass."""

    def test_default_values(self):
        """Test default values."""
        stats = AuthorStats(author="Test Author")
        assert stats.author == "Test Author"
        assert stats.books_read == 0
        assert stats.total_pages == 0
        assert stats.avg_rating == 0.0

    def test_with_values(self):
        """Test with custom values."""
        stats = AuthorStats(
            author="Brandon Sanderson",
            books_read=5,
            total_pages=4000,
            avg_rating=4.8,
        )
        assert stats.books_read == 5
        assert stats.total_pages == 4000


class TestGenreStats:
    """Tests for GenreStats dataclass."""

    def test_default_values(self):
        """Test default values."""
        stats = GenreStats(genre="Fantasy")
        assert stats.genre == "Fantasy"
        assert stats.books_count == 0
        assert stats.avg_rating == 0.0

    def test_with_values(self):
        """Test with custom values."""
        stats = GenreStats(
            genre="Science Fiction",
            books_count=10,
            avg_rating=4.3,
            total_pages=3500,
        )
        assert stats.books_count == 10


class TestReadingAnalytics:
    """Tests for ReadingAnalytics class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def analytics(self, db):
        """Create analytics instance."""
        return ReadingAnalytics(db)

    @pytest.fixture
    def sample_books(self, db):
        """Create sample books."""
        today = date.today()
        books = []

        # Completed books
        for i in range(5):
            book_data = BookCreate(
                title=f"Test Book {i+1}",
                author="Test Author" if i < 3 else "Other Author",
                status=BookStatus.COMPLETED,
                page_count=200 + i * 50,
                rating=4 if i < 3 else 5,
                date_started=(today - timedelta(days=30+i)).isoformat(),
                date_finished=(today - timedelta(days=i)).isoformat(),
                tags=["fiction", "fantasy"] if i % 2 == 0 else ["scifi"],
            )
            book = db.create_book(book_data)
            books.append(book)

        # Reading book
        reading_book = db.create_book(BookCreate(
            title="Currently Reading",
            author="Another Author",
            status=BookStatus.READING,
            page_count=400,
            date_started=today.isoformat(),
        ))
        books.append(reading_book)

        return books

    @pytest.fixture
    def sample_logs(self, db, sample_books):
        """Create sample reading logs."""
        logs = []
        today = date.today()

        for i in range(10):
            log_data = ReadingLogCreate(
                book_id=sample_books[0].id,
                date=(today - timedelta(days=i)).isoformat(),
                pages_read=30,
                duration_minutes=45,
                location="Home" if i % 2 == 0 else "Office",
            )
            with db.get_session() as session:
                log = db.create_reading_log(log_data, session)
                logs.append(log)

        return logs

    def test_get_yearly_stats_empty(self, analytics):
        """Test yearly stats with no data."""
        stats = analytics.get_yearly_stats()
        assert stats.books_finished == 0
        assert stats.books_started == 0

    def test_get_yearly_stats_with_books(self, analytics, sample_books):
        """Test yearly stats with books."""
        stats = analytics.get_yearly_stats()

        assert stats.books_finished == 5
        assert stats.books_started >= 1
        assert stats.total_pages > 0
        assert stats.avg_rating > 0

    def test_get_yearly_stats_top_authors(self, analytics, sample_books):
        """Test top authors in yearly stats."""
        stats = analytics.get_yearly_stats()

        assert len(stats.top_authors) > 0
        top_author = stats.top_authors[0]
        assert top_author[0] == "Test Author"
        assert top_author[1] == 3

    def test_get_yearly_stats_books_by_month(self, analytics, sample_books):
        """Test books by month in yearly stats."""
        stats = analytics.get_yearly_stats()

        # All books finished in current month
        current_month = date.today().month
        assert current_month in stats.books_by_month or len(stats.books_by_month) > 0

    def test_get_monthly_stats(self, analytics, sample_books, sample_logs):
        """Test monthly stats."""
        today = date.today()
        stats = analytics.get_monthly_stats(today.year, today.month)

        assert stats.year == today.year
        assert stats.month == today.month
        assert stats.books_finished >= 0
        assert stats.pages_read >= 0
        assert stats.reading_sessions >= 0

    def test_get_monthly_stats_december(self, analytics):
        """Test monthly stats for December (edge case)."""
        stats = analytics.get_monthly_stats(2025, 12)
        assert stats.year == 2025
        assert stats.month == 12

    def test_get_author_stats(self, analytics, sample_books):
        """Test author stats."""
        stats = analytics.get_author_stats()

        assert len(stats) > 0
        # Should be sorted by books read
        assert stats[0].books_read >= stats[-1].books_read

    def test_get_author_stats_filtered(self, analytics, sample_books):
        """Test author stats with filter."""
        stats = analytics.get_author_stats("Test")

        assert len(stats) > 0
        assert all("test" in s.author.lower() for s in stats)

    def test_get_genre_stats(self, analytics, sample_books):
        """Test genre stats."""
        stats = analytics.get_genre_stats()

        assert len(stats) > 0
        # Should include fiction and scifi tags
        genres = [s.genre for s in stats]
        assert "fiction" in genres or "fantasy" in genres or "scifi" in genres

    def test_get_reading_pace(self, analytics, sample_logs):
        """Test reading pace calculation."""
        pace = analytics.get_reading_pace(days=30)

        assert pace["period_days"] == 30
        assert pace["total_pages"] > 0
        assert pace["reading_sessions"] > 0
        assert pace["pages_per_day"] > 0

    def test_get_reading_pace_empty(self, analytics):
        """Test reading pace with no data."""
        pace = analytics.get_reading_pace(days=30)

        assert pace["total_pages"] == 0
        assert pace["reading_sessions"] == 0

    def test_get_all_time_stats(self, analytics, sample_books):
        """Test all-time stats."""
        stats = analytics.get_all_time_stats()

        assert stats["total_books"] >= 5
        assert stats["books_completed"] == 5
        assert stats["total_pages"] > 0
        assert stats["avg_rating"] > 0

    def test_get_all_time_stats_empty(self, analytics):
        """Test all-time stats with no data."""
        stats = analytics.get_all_time_stats()

        assert stats["total_books"] == 0
        assert stats["books_completed"] == 0

    def test_get_rating_analysis(self, analytics, sample_books):
        """Test rating analysis."""
        analysis = analytics.get_rating_analysis()

        assert analysis["total_rated"] > 0
        assert analysis["avg_rating"] > 0
        assert analysis["mode_rating"] is not None
        assert 4 in analysis["distribution"] or 5 in analysis["distribution"]

    def test_get_rating_analysis_empty(self, analytics):
        """Test rating analysis with no data."""
        analysis = analytics.get_rating_analysis()

        assert analysis["total_rated"] == 0
        assert analysis["avg_rating"] == 0

    def test_yearly_stats_rating_distribution(self, analytics, sample_books):
        """Test rating distribution in yearly stats."""
        stats = analytics.get_yearly_stats()

        assert len(stats.rating_distribution) > 0
        # Should have ratings 4 and 5
        assert 4 in stats.rating_distribution or 5 in stats.rating_distribution

    def test_yearly_stats_avg_days_to_finish(self, analytics, sample_books):
        """Test average days to finish calculation."""
        stats = analytics.get_yearly_stats()

        # All books have start and finish dates
        assert stats.avg_days_to_finish >= 0

    def test_monthly_stats_avg_pages_per_day(self, analytics, sample_books, sample_logs):
        """Test average pages per day."""
        today = date.today()
        stats = analytics.get_monthly_stats(today.year, today.month)

        if stats.pages_read > 0:
            assert stats.avg_pages_per_day > 0

    def test_author_stats_includes_book_details(self, analytics, sample_books):
        """Test that author stats include book details."""
        stats = analytics.get_author_stats()

        for stat in stats:
            assert len(stat.books) == stat.books_read
            for book in stat.books:
                assert "title" in book
                assert "rating" in book
