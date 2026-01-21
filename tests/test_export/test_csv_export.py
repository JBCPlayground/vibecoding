"""Tests for CSV export functionality."""

import csv
import pytest
from datetime import date, timedelta
from pathlib import Path

from vibecoding.booktracker.export.csv_export import (
    CSVExporter,
    ExportFormat,
    ExportResult,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus, ReadingLogCreate


class TestExportFormat:
    """Tests for ExportFormat enum."""

    def test_format_values(self):
        """Test format values."""
        assert ExportFormat.STANDARD.value == "standard"
        assert ExportFormat.GOODREADS.value == "goodreads"
        assert ExportFormat.NOTION.value == "notion"
        assert ExportFormat.CALIBRE.value == "calibre"

    def test_from_string(self):
        """Test creating from string."""
        assert ExportFormat("standard") == ExportFormat.STANDARD
        assert ExportFormat("goodreads") == ExportFormat.GOODREADS


class TestExportResult:
    """Tests for ExportResult dataclass."""

    def test_success_result(self, tmp_path):
        """Test success result."""
        result = ExportResult(
            success=True,
            file_path=tmp_path / "test.csv",
            records_exported=10,
            format=ExportFormat.STANDARD,
        )
        assert result.success is True
        assert result.records_exported == 10
        assert result.error is None

    def test_failure_result(self):
        """Test failure result."""
        result = ExportResult(
            success=False,
            error="Test error",
        )
        assert result.success is False
        assert result.error == "Test error"


class TestCSVExporter:
    """Tests for CSVExporter class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def exporter(self, db):
        """Create exporter instance."""
        return CSVExporter(db)

    @pytest.fixture
    def sample_books(self, db):
        """Create sample books."""
        today = date.today()
        books = []

        for i in range(5):
            book_data = BookCreate(
                title=f"Test Book {i+1}",
                author="Test Author" if i < 3 else "Other Author",
                isbn=f"123456789{i}",
                status=BookStatus.COMPLETED,
                page_count=200 + i * 50,
                rating=4 if i < 3 else 5,
                date_added=today - timedelta(days=30),
                date_started=today - timedelta(days=20+i),
                date_finished=today - timedelta(days=i),
                tags=["fiction", "fantasy"],
                comments="Test notes",
                publisher="Test Publisher",
                publication_year=2023,
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
                pages_read=30,
                duration_minutes=45,
                location="Home",
            )
            with db.get_session() as session:
                log = db.create_reading_log(log_data, session)
                logs.append(log)

        return logs

    def test_export_books_standard(self, exporter, sample_books, tmp_path):
        """Test standard format export."""
        output = tmp_path / "export.csv"
        result = exporter.export_books(output, format=ExportFormat.STANDARD)

        assert result.success is True
        assert result.records_exported == 5
        assert output.exists()

        # Verify content
        with open(output, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 5
        # Verify that all books are exported (order may vary based on date_added)
        titles = {row["title"] for row in rows}
        assert "Test Book 1" in titles
        assert "Test Book 5" in titles

    def test_export_books_goodreads(self, exporter, sample_books, tmp_path):
        """Test Goodreads format export."""
        output = tmp_path / "goodreads.csv"
        result = exporter.export_books(output, format=ExportFormat.GOODREADS)

        assert result.success is True

        with open(output, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 5
        assert "Title" in reader.fieldnames
        assert "My Rating" in reader.fieldnames
        assert "Exclusive Shelf" in reader.fieldnames

    def test_export_books_notion(self, exporter, sample_books, tmp_path):
        """Test Notion format export."""
        output = tmp_path / "notion.csv"
        result = exporter.export_books(output, format=ExportFormat.NOTION)

        assert result.success is True

        with open(output, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 5
        assert "Name" in reader.fieldnames
        assert "Status" in reader.fieldnames

    def test_export_books_calibre(self, exporter, sample_books, tmp_path):
        """Test Calibre format export."""
        output = tmp_path / "calibre.csv"
        result = exporter.export_books(output, format=ExportFormat.CALIBRE)

        assert result.success is True

        with open(output, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 5
        assert "authors" in reader.fieldnames
        assert "pubdate" in reader.fieldnames

    def test_export_with_status_filter(self, exporter, db, tmp_path):
        """Test export with status filter."""
        # Add a wishlist book
        db.create_book(BookCreate(
            title="Wishlist Book",
            author="Author",
            status=BookStatus.WISHLIST,
        ))

        output = tmp_path / "filtered.csv"
        result = exporter.export_books(
            output,
            status_filter=BookStatus.WISHLIST,
        )

        assert result.success is True
        assert result.records_exported == 1

    def test_export_empty_database(self, exporter, tmp_path):
        """Test export with no books."""
        output = tmp_path / "empty.csv"
        result = exporter.export_books(output)

        assert result.success is True
        assert result.records_exported == 0

    def test_export_to_string(self, exporter, sample_books):
        """Test export to string."""
        csv_str = exporter.export_to_string(format=ExportFormat.STANDARD)

        assert csv_str
        assert "Test Book" in csv_str
        assert "Test Author" in csv_str

    def test_export_reading_logs(self, exporter, sample_books, sample_logs, tmp_path):
        """Test reading logs export."""
        output = tmp_path / "logs.csv"
        result = exporter.export_reading_logs(output)

        assert result.success is True
        assert result.records_exported == 10
        assert output.exists()

        with open(output, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 10
        assert "pages_read" in reader.fieldnames

    def test_export_reading_logs_filtered(self, exporter, sample_books, sample_logs, tmp_path):
        """Test reading logs export with filter."""
        output = tmp_path / "logs_filtered.csv"
        start_date = date.today() - timedelta(days=5)

        result = exporter.export_reading_logs(
            output,
            start_date=start_date,
        )

        assert result.success is True
        assert result.records_exported <= 10

    def test_export_standard_columns(self, exporter, sample_books, tmp_path):
        """Test that standard export includes all expected columns."""
        output = tmp_path / "standard.csv"
        exporter.export_books(output, format=ExportFormat.STANDARD)

        with open(output, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)

        expected = ["id", "title", "author", "isbn", "isbn13", "status", "rating"]
        for col in expected:
            assert col in headers

    def test_export_preserves_tags(self, exporter, sample_books, tmp_path):
        """Test that tags are preserved in export."""
        output = tmp_path / "with_tags.csv"
        exporter.export_books(output, format=ExportFormat.STANDARD)

        with open(output, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Tags should be comma-separated
        assert "fiction" in rows[0]["tags"]
        assert "fantasy" in rows[0]["tags"]

    def test_export_error_handling(self, exporter, sample_books):
        """Test error handling for invalid path."""
        # Need books in DB for export to actually try writing
        result = exporter.export_books(Path("/nonexistent/path/file.csv"))

        assert result.success is False
        assert result.error is not None

    def test_goodreads_shelf_mapping(self, db, tmp_path):
        """Test that status maps correctly to Goodreads shelves."""
        # Create books with different statuses
        db.create_book(BookCreate(
            title="Reading Book",
            author="Author",
            status=BookStatus.READING,
        ))
        db.create_book(BookCreate(
            title="Wishlist Book",
            author="Author",
            status=BookStatus.WISHLIST,
        ))

        exporter = CSVExporter(db)
        output = tmp_path / "goodreads.csv"
        exporter.export_books(output, format=ExportFormat.GOODREADS)

        with open(output, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        shelves = {row["Title"]: row["Exclusive Shelf"] for row in rows}
        assert shelves.get("Reading Book") == "currently-reading"
        assert shelves.get("Wishlist Book") == "to-read"

    def test_calibre_rating_conversion(self, db, tmp_path):
        """Test that Calibre export converts 5-star to 10-star rating."""
        db.create_book(BookCreate(
            title="Rated Book",
            author="Author",
            status=BookStatus.COMPLETED,
            rating=5,
        ))

        exporter = CSVExporter(db)
        output = tmp_path / "calibre.csv"
        exporter.export_books(output, format=ExportFormat.CALIBRE)

        with open(output, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)

        # Calibre uses 10-star rating
        assert row["rating"] == "10"
