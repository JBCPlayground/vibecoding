"""Tests for reading reports."""

import pytest
from datetime import date, timedelta

from vibecoding.booktracker.export.reports import (
    ReportGenerator,
    YearInReview,
    MonthlyReport,
    BookSummary,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus, ReadingLogCreate


class TestBookSummary:
    """Tests for BookSummary dataclass."""

    def test_default_values(self):
        """Test default values."""
        summary = BookSummary(title="Test", author="Author")
        assert summary.title == "Test"
        assert summary.author == "Author"
        assert summary.rating is None
        assert summary.page_count is None
        assert summary.tags == []

    def test_with_values(self):
        """Test with all values."""
        summary = BookSummary(
            title="Test Book",
            author="Test Author",
            rating=5,
            page_count=300,
            date_finished="2025-01-01",
            tags=["fiction", "fantasy"],
        )
        assert summary.rating == 5
        assert summary.page_count == 300
        assert len(summary.tags) == 2


class TestMonthlyReport:
    """Tests for MonthlyReport dataclass."""

    def test_default_values(self):
        """Test default values."""
        report = MonthlyReport(year=2025, month=1, month_name="January")
        assert report.year == 2025
        assert report.month == 1
        assert report.month_name == "January"
        assert report.books_finished == 0
        assert report.pages_read == 0

    def test_with_values(self):
        """Test with all values."""
        report = MonthlyReport(
            year=2025,
            month=6,
            month_name="June",
            books_finished=3,
            pages_read=900,
            reading_sessions=20,
        )
        assert report.books_finished == 3
        assert report.pages_read == 900


class TestYearInReview:
    """Tests for YearInReview dataclass."""

    def test_default_values(self):
        """Test default values."""
        review = YearInReview(year=2025)
        assert review.year == 2025
        assert review.books_finished == 0
        assert review.total_pages == 0
        assert review.top_authors == []

    def test_with_values(self):
        """Test with values."""
        review = YearInReview(
            year=2025,
            books_finished=24,
            total_pages=6000,
            avg_rating=4.2,
        )
        assert review.books_finished == 24
        assert review.total_pages == 6000
        assert review.avg_rating == 4.2


class TestReportGenerator:
    """Tests for ReportGenerator class."""

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
        """Create generator instance."""
        return ReportGenerator(db)

    @pytest.fixture
    def sample_books(self, db):
        """Create sample books for current year."""
        today = date.today()
        books = []

        for i in range(10):
            month = (i % 12) + 1
            finish_date = date(today.year, month, 15)

            # Skip future months
            if finish_date > today:
                continue

            book_data = BookCreate(
                title=f"Book {i+1}",
                author="Author A" if i < 5 else "Author B",
                status=BookStatus.COMPLETED,
                page_count=200 + i * 30,
                rating=3 + (i % 3),
                date_started=(finish_date - timedelta(days=10)).isoformat(),
                date_finished=finish_date.isoformat(),
                tags=["fiction"] if i % 2 == 0 else ["nonfiction"],
            )
            book = db.create_book(book_data)
            books.append(book)

        return books

    @pytest.fixture
    def sample_logs(self, db, sample_books):
        """Create sample reading logs."""
        if not sample_books:
            return []

        today = date.today()
        logs = []

        for i in range(30):
            log_data = ReadingLogCreate(
                book_id=sample_books[0].id,
                date=(today - timedelta(days=i)).isoformat(),
                pages_read=25,
                duration_minutes=30,
                location="Home" if i % 2 == 0 else "Office",
            )
            with db.get_session() as session:
                log = db.create_reading_log(log_data, session)
                logs.append(log)

        return logs

    def test_generate_year_in_review_empty(self, generator):
        """Test year in review with no data."""
        review = generator.generate_year_in_review()

        assert review.books_finished == 0
        assert review.total_pages == 0

    def test_generate_year_in_review_with_data(self, generator, sample_books, sample_logs):
        """Test year in review with data."""
        review = generator.generate_year_in_review()

        assert review.books_finished > 0
        assert review.total_pages > 0
        assert review.total_reading_sessions > 0

    def test_year_in_review_averages(self, generator, sample_books):
        """Test averages in year in review."""
        review = generator.generate_year_in_review()

        if review.books_finished > 0:
            assert review.avg_rating > 0
            assert review.avg_book_length > 0

    def test_year_in_review_records(self, generator, sample_books):
        """Test records in year in review."""
        review = generator.generate_year_in_review()

        if review.books_finished > 0:
            assert review.longest_book is not None
            assert review.shortest_book is not None

    def test_year_in_review_top_authors(self, generator, sample_books):
        """Test top authors list."""
        review = generator.generate_year_in_review()

        if review.books_finished > 0:
            assert len(review.top_authors) > 0
            # First author should have most books
            if len(review.top_authors) > 1:
                assert review.top_authors[0][1] >= review.top_authors[1][1]

    def test_year_in_review_top_genres(self, generator, sample_books):
        """Test top genres list."""
        review = generator.generate_year_in_review()

        if review.books_finished > 0:
            assert len(review.top_genres) > 0

    def test_year_in_review_books_by_month(self, generator, sample_books):
        """Test books by month breakdown."""
        review = generator.generate_year_in_review()

        if review.books_finished > 0:
            assert len(review.books_by_month) > 0
            # Total should match books_finished
            assert sum(review.books_by_month.values()) == review.books_finished

    def test_year_in_review_five_star_books(self, db, generator):
        """Test five-star books list."""
        today = date.today()

        # Create a 5-star book
        db.create_book(BookCreate(
            title="Amazing Book",
            author="Great Author",
            status=BookStatus.COMPLETED,
            rating=5,
            date_finished=today.isoformat(),
        ))

        review = generator.generate_year_in_review()

        assert len(review.five_star_books) == 1
        assert review.five_star_books[0].title == "Amazing Book"

    def test_year_in_review_monthly_summaries(self, generator, sample_books):
        """Test monthly summaries are generated."""
        review = generator.generate_year_in_review()

        # Should have 12 monthly summaries
        assert len(review.monthly_summaries) == 12

    def test_year_in_review_reading_streak(self, generator, sample_logs):
        """Test reading streak calculation."""
        review = generator.generate_year_in_review()

        # With 30 consecutive days of logs, should have a streak
        if sample_logs:
            assert review.reading_streak_days > 0

    def test_year_in_review_favorite_location(self, generator, sample_logs):
        """Test favorite reading location."""
        review = generator.generate_year_in_review()

        if sample_logs:
            assert review.favorite_reading_location is not None

    def test_year_in_review_comparison(self, db, generator):
        """Test year-over-year comparison."""
        today = date.today()
        last_year = today.year - 1

        # Create book last year
        db.create_book(BookCreate(
            title="Last Year Book",
            author="Author",
            status=BookStatus.COMPLETED,
            date_finished=f"{last_year}-06-15",
        ))

        # Create books this year
        for i in range(3):
            db.create_book(BookCreate(
                title=f"This Year Book {i}",
                author="Author",
                status=BookStatus.COMPLETED,
                date_finished=today.isoformat(),
            ))

        review = generator.generate_year_in_review()

        assert review.books_vs_last_year is not None
        assert review.books_vs_last_year == 2  # 3 this year - 1 last year

    def test_generate_monthly_report(self, generator, sample_books, sample_logs):
        """Test monthly report generation."""
        today = date.today()
        report = generator.generate_monthly_report(today.year, today.month)

        assert report.year == today.year
        assert report.month == today.month
        assert report.month_name

    def test_monthly_report_empty(self, generator):
        """Test monthly report with no data."""
        report = generator.generate_monthly_report(2020, 1)

        assert report.books_finished == 0
        assert report.pages_read == 0

    def test_monthly_report_stats(self, generator, sample_books, sample_logs):
        """Test monthly report statistics."""
        today = date.today()
        report = generator.generate_monthly_report(today.year, today.month)

        # Should have reading activity from logs
        if sample_logs:
            assert report.pages_read > 0
            assert report.reading_sessions > 0

    def test_monthly_report_books_list(self, db, generator):
        """Test books list in monthly report."""
        today = date.today()

        db.create_book(BookCreate(
            title="Monthly Book",
            author="Author",
            status=BookStatus.COMPLETED,
            rating=4,
            date_finished=today.isoformat(),
        ))

        report = generator.generate_monthly_report(today.year, today.month)

        assert report.books_finished == 1
        assert len(report.books) == 1
        assert report.books[0].title == "Monthly Book"

    def test_generate_reading_stats_text(self, generator, sample_books):
        """Test text report generation."""
        text = generator.generate_reading_stats_text()

        assert "Year in Review" in text
        assert str(date.today().year) in text

    def test_reading_stats_text_sections(self, generator, sample_books, sample_logs):
        """Test text report has all sections."""
        text = generator.generate_reading_stats_text()

        expected_sections = ["Overview", "Averages"]
        for section in expected_sections:
            assert section in text

    def test_specific_year_report(self, db, generator):
        """Test generating report for specific year."""
        # Create book in 2020
        db.create_book(BookCreate(
            title="2020 Book",
            author="Author",
            status=BookStatus.COMPLETED,
            page_count=300,
            date_finished="2020-06-15",
        ))

        review = generator.generate_year_in_review(2020)

        assert review.year == 2020
        assert review.books_finished == 1
        assert review.total_pages == 300

    def test_max_streak_calculation(self, generator):
        """Test max streak calculation helper."""
        # Test consecutive dates
        dates = {"2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"}
        streak = generator._calculate_max_streak(dates)
        assert streak == 4

    def test_max_streak_with_gaps(self, generator):
        """Test max streak with gaps."""
        dates = {"2025-01-01", "2025-01-02", "2025-01-05", "2025-01-06"}
        streak = generator._calculate_max_streak(dates)
        assert streak == 2

    def test_max_streak_empty(self, generator):
        """Test max streak with no dates."""
        streak = generator._calculate_max_streak(set())
        assert streak == 0

    def test_december_monthly_report(self, db, generator):
        """Test December edge case."""
        db.create_book(BookCreate(
            title="December Book",
            author="Author",
            status=BookStatus.COMPLETED,
            date_finished="2024-12-15",
        ))

        report = generator.generate_monthly_report(2024, 12)

        assert report.month == 12
        assert report.books_finished == 1

    def test_pages_per_day_calculation(self, db, generator):
        """Test pages per day average."""
        today = date.today()

        # Create a book with many pages
        db.create_book(BookCreate(
            title="Big Book",
            author="Author",
            status=BookStatus.COMPLETED,
            page_count=1000,
            date_finished=today.isoformat(),
        ))

        review = generator.generate_year_in_review()

        assert review.avg_pages_per_day > 0
