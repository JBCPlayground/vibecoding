"""Tests for JSON export functionality."""

import json
import pytest
from datetime import date, timedelta
from pathlib import Path

from vibecoding.booktracker.export.json_export import (
    JSONExporter,
    JSONExportResult,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus, ReadingLogCreate


class TestJSONExportResult:
    """Tests for JSONExportResult dataclass."""

    def test_success_result(self, tmp_path):
        """Test success result."""
        result = JSONExportResult(
            success=True,
            file_path=tmp_path / "test.json",
            books_exported=10,
            logs_exported=50,
        )
        assert result.success is True
        assert result.books_exported == 10
        assert result.logs_exported == 50

    def test_failure_result(self):
        """Test failure result."""
        result = JSONExportResult(
            success=False,
            error="Test error",
        )
        assert result.success is False
        assert result.error == "Test error"


class TestJSONExporter:
    """Tests for JSONExporter class."""

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
        return JSONExporter(db)

    @pytest.fixture
    def sample_books(self, db):
        """Create sample books."""
        today = date.today()
        books = []

        for i in range(5):
            book_data = BookCreate(
                title=f"Test Book {i+1}",
                author="Test Author",
                isbn=f"123456789{i}",
                status=BookStatus.COMPLETED,
                page_count=250,
                rating=4,
                date_finished=(today - timedelta(days=i)).isoformat(),
                tags=["fiction"],
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
            )
            with db.get_session() as session:
                log = db.create_reading_log(log_data, session)
                logs.append(log)

        return logs

    def test_export_all(self, exporter, sample_books, sample_logs, tmp_path):
        """Test full export with books and logs."""
        output = tmp_path / "export.json"
        result = exporter.export_all(output)

        assert result.success is True
        assert result.books_exported == 5
        assert result.logs_exported == 10
        assert output.exists()

        # Verify JSON structure
        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "version" in data
        assert "exported_at" in data
        assert "books" in data
        assert "reading_logs" in data
        assert len(data["books"]) == 5
        assert len(data["reading_logs"]) == 10

    def test_export_all_without_logs(self, exporter, sample_books, tmp_path):
        """Test export without reading logs."""
        output = tmp_path / "books_only.json"
        result = exporter.export_all(output, include_reading_logs=False)

        assert result.success is True
        assert result.books_exported == 5
        assert result.logs_exported == 0

        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "reading_logs" not in data

    def test_export_books(self, exporter, sample_books, tmp_path):
        """Test books-only export."""
        output = tmp_path / "books.json"
        result = exporter.export_books(output)

        assert result.success is True
        assert result.books_exported == 5

        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["books"]) == 5

    def test_export_books_with_filter(self, exporter, db, tmp_path):
        """Test export with status filter."""
        # Add wishlist book
        db.create_book(BookCreate(
            title="Wishlist Book",
            author="Author",
            status=BookStatus.WISHLIST,
        ))

        output = tmp_path / "wishlist.json"
        result = exporter.export_books(output, status_filter=BookStatus.WISHLIST)

        assert result.success is True
        assert result.books_exported == 1

    def test_export_compact(self, exporter, sample_books, tmp_path):
        """Test compact JSON export."""
        output = tmp_path / "compact.json"
        exporter.export_books(output, pretty=False)

        content = output.read_text()

        # Compact JSON should not have newlines (except maybe at end)
        assert content.count("\n") <= 1

    def test_export_pretty(self, exporter, sample_books, tmp_path):
        """Test pretty-printed JSON export."""
        output = tmp_path / "pretty.json"
        exporter.export_books(output, pretty=True)

        content = output.read_text()

        # Pretty JSON should have multiple lines
        assert content.count("\n") > 5

    def test_export_to_string(self, exporter, sample_books):
        """Test export to string."""
        json_str = exporter.export_to_string()

        assert json_str
        data = json.loads(json_str)
        assert "books" in data
        assert len(data["books"]) == 5

    def test_export_single_book(self, exporter, sample_books, sample_logs):
        """Test exporting a single book."""
        book_data = exporter.export_book(sample_books[0].id)

        assert book_data is not None
        assert book_data["title"] == "Test Book 1"
        assert "reading_logs" in book_data
        assert len(book_data["reading_logs"]) == 10

    def test_export_single_book_without_logs(self, exporter, sample_books, sample_logs):
        """Test exporting single book without logs."""
        book_data = exporter.export_book(sample_books[0].id, include_logs=False)

        assert book_data is not None
        assert "reading_logs" not in book_data

    def test_export_single_book_not_found(self, exporter):
        """Test exporting non-existent book."""
        book_data = exporter.export_book("nonexistent-id")
        assert book_data is None

    def test_export_reading_logs(self, exporter, sample_books, sample_logs, tmp_path):
        """Test reading logs export."""
        output = tmp_path / "logs.json"
        result = exporter.export_reading_logs(output)

        assert result.success is True
        assert result.logs_exported == 10

        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "reading_logs" in data
        assert len(data["reading_logs"]) == 10

    def test_export_reading_logs_filtered(self, exporter, sample_books, sample_logs, tmp_path):
        """Test filtered reading logs export."""
        output = tmp_path / "logs_filtered.json"
        start_date = date.today() - timedelta(days=5)

        result = exporter.export_reading_logs(output, start_date=start_date)

        assert result.success is True
        assert result.logs_exported <= 10

    def test_export_book_fields(self, exporter, sample_books, tmp_path):
        """Test that book export includes all expected fields."""
        output = tmp_path / "books.json"
        exporter.export_books(output)

        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)

        book = data["books"][0]
        expected_fields = [
            "id", "title", "author", "isbn", "status",
            "rating", "page_count", "progress", "date_added",
            "date_started", "date_finished", "tags", "comments"
        ]

        for field in expected_fields:
            assert field in book

    def test_export_preserves_tags_as_list(self, exporter, sample_books, tmp_path):
        """Test that tags are exported as list."""
        output = tmp_path / "books.json"
        exporter.export_books(output)

        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)

        book = data["books"][0]
        assert isinstance(book["tags"], list)

    def test_export_log_fields(self, exporter, sample_books, sample_logs, tmp_path):
        """Test that log export includes all expected fields."""
        output = tmp_path / "logs.json"
        exporter.export_reading_logs(output)

        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)

        log = data["reading_logs"][0]
        expected_fields = [
            "id", "book_id", "date", "pages_read",
            "start_page", "end_page", "duration_minutes"
        ]

        for field in expected_fields:
            assert field in log

    def test_export_empty_database(self, exporter, tmp_path):
        """Test export with no data."""
        output = tmp_path / "empty.json"
        result = exporter.export_all(output)

        assert result.success is True
        assert result.books_exported == 0
        assert result.logs_exported == 0

        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["books"] == []

    def test_export_error_handling(self, exporter):
        """Test error handling for invalid path."""
        result = exporter.export_all(Path("/nonexistent/path/file.json"))

        assert result.success is False
        assert result.error is not None

    def test_export_unicode(self, db, tmp_path):
        """Test that unicode characters are preserved."""
        db.create_book(BookCreate(
            title="日本語の本",
            author="作家名",
            status=BookStatus.COMPLETED,
        ))

        exporter = JSONExporter(db)
        output = tmp_path / "unicode.json"
        exporter.export_books(output)

        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["books"][0]["title"] == "日本語の本"
        assert data["books"][0]["author"] == "作家名"
