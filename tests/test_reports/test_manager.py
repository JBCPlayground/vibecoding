"""Tests for ReportManager."""

from datetime import date, timedelta
import pytest

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus, ReadingLogCreate
from vibecoding.booktracker.reports.manager import ReportManager
from vibecoding.booktracker.reports.schemas import (
    ExportFormat,
    TimeFrame,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a ReportManager with test database."""
    return ReportManager(db)


@pytest.fixture
def books_with_data(db):
    """Create sample books with reading data for reports."""
    current_year = date.today().year
    books = []

    # Completed books in current year
    for i in range(5):
        book = db.create_book(BookCreate(
            title=f"Completed Book {i + 1}",
            author=f"Author {chr(65 + i % 3)}",  # Author A, B, C
            status=BookStatus.COMPLETED,
            rating=3 + (i % 3),  # Ratings 3-5
            genres=["Fantasy", "Adventure"] if i % 2 == 0 else ["Mystery", "Thriller"],
            page_count=200 + i * 50,
            date_finished=f"{current_year}-{(i % 6) + 1:02d}-15",
        ))
        books.append(book)

    # Currently reading
    book = db.create_book(BookCreate(
        title="Currently Reading",
        author="Author A",
        status=BookStatus.READING,
        page_count=300,
    ))
    books.append(book)

    # Wishlist
    book = db.create_book(BookCreate(
        title="Wishlist Book",
        author="Author B",
        status=BookStatus.WISHLIST,
        genres=["Sci-Fi"],
    ))
    books.append(book)

    return books


@pytest.fixture
def books_with_logs(db):
    """Create books with reading logs for heatmap tests."""
    current_year = date.today().year
    books = []

    book = db.create_book(BookCreate(
        title="Book with Logs",
        author="Test Author",
        status=BookStatus.COMPLETED,
        page_count=300,
        date_finished=f"{current_year}-03-15",
    ))
    books.append(book)

    # Create reading logs across different dates
    log_dates = [
        f"{current_year}-01-10",
        f"{current_year}-01-11",
        f"{current_year}-01-12",  # 3-day streak
        f"{current_year}-02-15",
        f"{current_year}-03-10",
        f"{current_year}-03-11",
    ]

    for log_date in log_dates:
        db.create_reading_log(ReadingLogCreate(
            book_id=book.id,
            date=log_date,
            pages_read=30,
            duration_minutes=60,
        ))

    return books


@pytest.fixture
def last_year_books(db):
    """Create books from last year for comparison tests."""
    last_year = date.today().year - 1
    books = []

    for i in range(3):
        book = db.create_book(BookCreate(
            title=f"Last Year Book {i + 1}",
            author="Old Author",
            status=BookStatus.COMPLETED,
            rating=4,
            page_count=250,
            date_finished=f"{last_year}-06-{15 + i:02d}",
        ))
        books.append(book)

    return books


class TestHeatmapGeneration:
    """Tests for heatmap generation."""

    def test_get_year_heatmap_empty(self, manager):
        """Test year heatmap with no data."""
        current_year = date.today().year
        heatmap = manager.get_year_heatmap(current_year)

        assert heatmap.year == current_year
        assert len(heatmap.months) == 12
        assert heatmap.total_reading_days == 0
        assert heatmap.total_pages == 0
        assert heatmap.books_completed == 0

    def test_get_year_heatmap_with_data(self, manager, books_with_logs):
        """Test year heatmap with reading logs."""
        current_year = date.today().year
        heatmap = manager.get_year_heatmap(current_year)

        assert heatmap.year == current_year
        assert heatmap.total_reading_days > 0
        assert heatmap.total_pages > 0
        assert heatmap.books_completed == 1

    def test_get_year_heatmap_has_all_months(self, manager, books_with_logs):
        """Test that year heatmap has all 12 months."""
        current_year = date.today().year
        heatmap = manager.get_year_heatmap(current_year)

        assert len(heatmap.months) == 12
        month_numbers = [m.month for m in heatmap.months]
        assert month_numbers == list(range(1, 13))

    def test_get_month_heatmap(self, manager, books_with_logs):
        """Test month heatmap generation."""
        current_year = date.today().year
        heatmap = manager.get_month_heatmap(current_year, 1)

        assert heatmap.year == current_year
        assert heatmap.month == 1
        assert heatmap.month_name == "January"
        assert heatmap.total_reading_days > 0

    def test_get_month_heatmap_has_weeks(self, manager):
        """Test month heatmap has week data."""
        current_year = date.today().year
        heatmap = manager.get_month_heatmap(current_year, 6)

        assert len(heatmap.weeks) > 0
        for week in heatmap.weeks:
            assert len(week.days) > 0

    def test_heatmap_intensity_levels(self, manager, db):
        """Test that heatmap intensity is calculated correctly."""
        current_year = date.today().year

        book = db.create_book(BookCreate(
            title="Intensive Reading",
            author="Author",
            status=BookStatus.READING,
            page_count=500,
        ))

        # Create logs with varying page counts
        for i in range(4):
            db.create_reading_log(ReadingLogCreate(
                book_id=book.id,
                date=f"{current_year}-05-{10 + i:02d}",
                pages_read=25 * (i + 1),  # 25, 50, 75, 100 pages
                duration_minutes=30,
            ))

        heatmap = manager.get_month_heatmap(current_year, 5)

        # Check that we have varying intensities
        intensities = set()
        for week in heatmap.weeks:
            for day in week.days:
                intensities.add(day.intensity)

        # Should have at least 2 different intensity levels
        assert len(intensities) >= 2

    def test_streak_calculation(self, manager, books_with_logs):
        """Test streak calculation in heatmap."""
        current_year = date.today().year
        heatmap = manager.get_year_heatmap(current_year)

        # We created a 3-day streak in January
        assert heatmap.longest_streak >= 3


class TestChartGeneration:
    """Tests for chart data generation."""

    def test_get_genre_chart_empty(self, manager):
        """Test genre chart with no books."""
        chart = manager.get_genre_chart()

        assert chart.title == "Books by Genre"
        assert len(chart.data) == 0

    def test_get_genre_chart_with_data(self, manager, books_with_data):
        """Test genre chart with completed books."""
        chart = manager.get_genre_chart()

        assert chart.title == "Books by Genre"
        assert len(chart.data) > 0
        assert chart.total > 0

    def test_get_genre_chart_year_filter(self, manager, books_with_data):
        """Test genre chart with year filter."""
        current_year = date.today().year
        chart = manager.get_genre_chart(year=current_year)

        assert len(chart.data) > 0

    def test_get_rating_chart_empty(self, manager):
        """Test rating chart with no rated books."""
        chart = manager.get_rating_chart()

        assert chart.title == "Rating Distribution"
        assert len(chart.data) == 5  # Always has 1-5 stars

    def test_get_rating_chart_with_data(self, manager, books_with_data):
        """Test rating chart with rated books."""
        chart = manager.get_rating_chart()

        assert len(chart.data) == 5
        # Check that at least some ratings have values
        total = sum(p.value for p in chart.data)
        assert total > 0

    def test_get_rating_chart_labels(self, manager, books_with_data):
        """Test rating chart has correct labels."""
        chart = manager.get_rating_chart()

        labels = [p.label for p in chart.data]
        assert "1 star" in labels
        assert "5 stars" in labels

    def test_get_monthly_progress_chart(self, manager, books_with_data):
        """Test monthly progress chart."""
        current_year = date.today().year
        chart = manager.get_monthly_progress_chart(current_year)

        assert chart.title == f"Books Read in {current_year}"
        assert len(chart.series) == 12
        assert chart.x_label == "Month"
        assert chart.y_label == "Books Completed"

    def test_get_monthly_progress_chart_months(self, manager, books_with_data):
        """Test monthly progress chart has all month abbreviations."""
        current_year = date.today().year
        chart = manager.get_monthly_progress_chart(current_year)

        month_labels = [p.x for p in chart.series]
        assert "Jan" in month_labels
        assert "Dec" in month_labels

    def test_get_pages_over_time_chart(self, manager, books_with_logs):
        """Test cumulative pages chart."""
        current_year = date.today().year
        chart = manager.get_pages_over_time_chart(current_year)

        assert "Cumulative" in chart.title
        assert len(chart.series) == 12

    def test_pages_over_time_is_cumulative(self, manager, books_with_logs):
        """Test that pages chart values are cumulative."""
        current_year = date.today().year
        chart = manager.get_pages_over_time_chart(current_year)

        # Each value should be >= the previous
        for i in range(1, len(chart.series)):
            assert chart.series[i].y >= chart.series[i - 1].y


class TestYearlyRecap:
    """Tests for yearly recap generation."""

    def test_get_yearly_recap_empty(self, manager):
        """Test yearly recap with no data."""
        current_year = date.today().year
        recap = manager.get_yearly_recap(current_year)

        assert recap.year == current_year
        assert recap.books_completed == 0
        assert recap.total_pages == 0

    def test_get_yearly_recap_with_data(self, manager, books_with_data):
        """Test yearly recap with completed books."""
        current_year = date.today().year
        recap = manager.get_yearly_recap(current_year)

        assert recap.books_completed == 5
        assert recap.total_pages > 0
        assert recap.average_rating is not None

    def test_yearly_recap_averages(self, manager, books_with_data):
        """Test yearly recap averages are calculated."""
        current_year = date.today().year
        recap = manager.get_yearly_recap(current_year)

        assert recap.average_pages_per_book > 0
        assert recap.average_books_per_month > 0
        assert recap.pages_per_day >= 0

    def test_yearly_recap_highlights(self, manager, books_with_data):
        """Test yearly recap highlights."""
        current_year = date.today().year
        recap = manager.get_yearly_recap(current_year)

        assert len(recap.highest_rated_books) > 0
        assert recap.longest_book is not None
        assert recap.shortest_book is not None
        assert recap.first_book is not None
        assert recap.last_book is not None

    def test_yearly_recap_monthly_breakdown(self, manager, books_with_data):
        """Test yearly recap monthly breakdown."""
        current_year = date.today().year
        recap = manager.get_yearly_recap(current_year)

        assert len(recap.books_by_month) == 12

        # At least some months should have books
        months_with_books = [m for m in recap.books_by_month if m.books_completed > 0]
        assert len(months_with_books) > 0

    def test_yearly_recap_genre_breakdown(self, manager, books_with_data):
        """Test yearly recap genre breakdown."""
        current_year = date.today().year
        recap = manager.get_yearly_recap(current_year)

        assert len(recap.top_genres) > 0
        for genre in recap.top_genres:
            assert genre.count > 0
            assert 0 <= genre.percentage <= 100

    def test_yearly_recap_author_stats(self, manager, books_with_data):
        """Test yearly recap author statistics."""
        current_year = date.today().year
        recap = manager.get_yearly_recap(current_year)

        assert len(recap.top_authors) > 0
        for author in recap.top_authors:
            assert author.books_read > 0

    def test_yearly_recap_rating_distribution(self, manager, books_with_data):
        """Test yearly recap rating distribution."""
        current_year = date.today().year
        recap = manager.get_yearly_recap(current_year)

        assert recap.rating_distribution.total_rated > 0
        assert recap.rating_distribution.average > 0

    def test_yearly_recap_comparison(self, manager, books_with_data, last_year_books):
        """Test yearly recap year-over-year comparison."""
        current_year = date.today().year
        recap = manager.get_yearly_recap(current_year)

        # With last year books, we should have comparison data
        assert recap.books_vs_last_year is not None
        assert recap.pages_vs_last_year is not None

    def test_yearly_recap_fun_facts(self, manager, books_with_data):
        """Test yearly recap generates fun facts."""
        current_year = date.today().year
        recap = manager.get_yearly_recap(current_year)

        assert len(recap.fun_facts) > 0


class TestDashboard:
    """Tests for dashboard data generation."""

    def test_get_dashboard_empty(self, manager):
        """Test dashboard with no data."""
        dashboard = manager.get_dashboard()

        assert dashboard.currently_reading == 0
        assert dashboard.books_this_year == 0
        assert dashboard.pages_this_year == 0

    def test_get_dashboard_with_data(self, manager, books_with_data):
        """Test dashboard with books."""
        dashboard = manager.get_dashboard()

        assert dashboard.currently_reading == 1
        assert dashboard.books_this_year == 5
        assert dashboard.pages_this_year > 0

    def test_dashboard_average_rating(self, manager, books_with_data):
        """Test dashboard average rating."""
        dashboard = manager.get_dashboard()

        assert dashboard.average_rating is not None
        assert 1 <= dashboard.average_rating <= 5

    def test_dashboard_books_per_month(self, manager, books_with_data):
        """Test dashboard books per month calculation."""
        dashboard = manager.get_dashboard()

        assert dashboard.books_per_month >= 0

    def test_dashboard_favorite_genre(self, manager, books_with_data):
        """Test dashboard favorite genre."""
        dashboard = manager.get_dashboard()

        assert dashboard.favorite_genre is not None

    def test_dashboard_recent_activity(self, manager, books_with_data):
        """Test dashboard recent activity."""
        dashboard = manager.get_dashboard()

        assert len(dashboard.recent_activity) > 0
        for activity in dashboard.recent_activity:
            assert activity.activity_type == "completed"
            assert activity.book_title is not None

    def test_dashboard_charts(self, manager, books_with_data):
        """Test dashboard includes chart data."""
        dashboard = manager.get_dashboard()

        assert dashboard.books_by_month_chart is not None
        assert len(dashboard.books_by_month_chart.data) == 12

        assert dashboard.genre_pie_chart is not None

    def test_dashboard_year_filter(self, manager, books_with_data):
        """Test dashboard with specific year filter."""
        current_year = date.today().year
        dashboard = manager.get_dashboard(year=current_year)

        assert dashboard.books_this_year == 5

    def test_dashboard_future_year(self, manager, books_with_data):
        """Test dashboard with future year returns zero."""
        future_year = date.today().year + 10
        dashboard = manager.get_dashboard(year=future_year)

        assert dashboard.books_this_year == 0


class TestExport:
    """Tests for report export functionality."""

    def test_export_recap_json(self, manager, books_with_data):
        """Test exporting recap as JSON."""
        current_year = date.today().year
        export = manager.export_recap(current_year, ExportFormat.JSON)

        assert export.format == ExportFormat.JSON
        assert export.title == f"Reading Recap {current_year}"
        assert export.content is not None
        assert "books_completed" in export.content

    def test_export_recap_markdown(self, manager, books_with_data):
        """Test exporting recap as Markdown."""
        current_year = date.today().year
        export = manager.export_recap(current_year, ExportFormat.MARKDOWN)

        assert export.format == ExportFormat.MARKDOWN
        assert "# Reading Recap" in export.content
        assert "## Overview" in export.content

    def test_export_recap_csv(self, manager, books_with_data):
        """Test exporting recap as CSV."""
        current_year = date.today().year
        export = manager.export_recap(current_year, ExportFormat.CSV)

        assert export.format == ExportFormat.CSV
        assert "Month,Books Completed" in export.content

    def test_export_has_generated_timestamp(self, manager, books_with_data):
        """Test that exports include generation timestamp."""
        current_year = date.today().year
        export = manager.export_recap(current_year)

        assert export.generated_at is not None
        assert len(export.generated_at) > 0

    def test_export_markdown_sections(self, manager, books_with_data):
        """Test markdown export has all sections."""
        current_year = date.today().year
        export = manager.export_recap(current_year, ExportFormat.MARKDOWN)

        assert "## Monthly Breakdown" in export.content
        assert "## Top Genres" in export.content
        assert "## Top Authors" in export.content


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_heatmap_leap_year(self, manager):
        """Test heatmap handles leap year correctly."""
        # 2024 is a leap year
        heatmap = manager.get_month_heatmap(2024, 2)

        # February 2024 has 29 days
        total_days = sum(len(week.days) for week in heatmap.weeks)
        assert total_days == 29

    def test_recap_no_rated_books(self, manager, db):
        """Test recap handles books without ratings."""
        current_year = date.today().year
        db.create_book(BookCreate(
            title="Unrated Book",
            author="Author",
            status=BookStatus.COMPLETED,
            page_count=200,
            date_finished=f"{current_year}-06-15",
        ))

        recap = manager.get_yearly_recap(current_year)

        assert recap.books_completed == 1
        assert recap.average_rating is None

    def test_recap_no_genres(self, manager, db):
        """Test recap handles books without genres."""
        current_year = date.today().year
        db.create_book(BookCreate(
            title="No Genre Book",
            author="Author",
            status=BookStatus.COMPLETED,
            page_count=200,
            date_finished=f"{current_year}-06-15",
        ))

        recap = manager.get_yearly_recap(current_year)

        assert recap.books_completed == 1
        assert len(recap.top_genres) == 0

    def test_genre_chart_multiple_genres_per_book(self, manager, db):
        """Test genre chart counts multiple genres correctly."""
        current_year = date.today().year
        db.create_book(BookCreate(
            title="Multi-genre Book",
            author="Author",
            status=BookStatus.COMPLETED,
            genres=["Fantasy", "Adventure", "Romance"],
            date_finished=f"{current_year}-06-15",
        ))

        chart = manager.get_genre_chart(current_year)

        # Each genre should be counted once
        assert chart.total == 3

    def test_streak_single_day(self, manager, db):
        """Test streak with single reading day."""
        current_year = date.today().year

        book = db.create_book(BookCreate(
            title="Single Day Book",
            author="Author",
            status=BookStatus.READING,
        ))

        db.create_reading_log(ReadingLogCreate(
            book_id=book.id,
            date=f"{current_year}-06-15",
            pages_read=50,
        ))

        heatmap = manager.get_year_heatmap(current_year)

        assert heatmap.longest_streak == 1

    def test_recap_book_without_pages(self, manager, db):
        """Test recap handles books without page counts."""
        current_year = date.today().year
        db.create_book(BookCreate(
            title="No Pages Book",
            author="Author",
            status=BookStatus.COMPLETED,
            date_finished=f"{current_year}-06-15",
        ))

        recap = manager.get_yearly_recap(current_year)

        assert recap.books_completed == 1
        assert recap.total_pages == 0

    def test_empty_year_heatmap(self, manager):
        """Test heatmap for year with no activity."""
        heatmap = manager.get_year_heatmap(1999)

        assert heatmap.total_reading_days == 0
        assert heatmap.total_pages == 0
        assert heatmap.books_completed == 0
        assert heatmap.longest_streak == 0
        assert heatmap.current_streak == 0
