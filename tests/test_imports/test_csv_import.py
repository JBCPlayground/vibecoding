"""Tests for generic CSV importer."""

import csv
import pytest
from pathlib import Path

from vibecoding.booktracker.imports.csv_import import GenericCSVImporter, FieldMapping
from vibecoding.booktracker.imports.base import DuplicateHandling
from vibecoding.booktracker.db.schemas import BookStatus


class TestFieldMapping:
    """Tests for FieldMapping dataclass."""

    def test_default_values(self):
        """Test default field mapping values."""
        mapping = FieldMapping()
        assert mapping.title == "title"
        assert mapping.author == "author"
        assert mapping.isbn is None
        assert mapping.date_format == "%Y-%m-%d"
        assert mapping.tag_separator == ","

    def test_status_mapping(self):
        """Test default status mapping."""
        mapping = FieldMapping()
        assert mapping.status_mapping["read"] == BookStatus.COMPLETED
        assert mapping.status_mapping["reading"] == BookStatus.READING
        assert mapping.status_mapping["to read"] == BookStatus.WISHLIST
        assert mapping.status_mapping["dnf"] == BookStatus.DNF

    def test_to_dict(self):
        """Test conversion to dictionary."""
        mapping = FieldMapping(title="book_title", author="book_author")
        d = mapping.to_dict()

        assert d["title"] == "book_title"
        assert d["author"] == "book_author"
        assert "date_format" in d
        assert "tag_separator" in d

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "title": "book_title",
            "author": "book_author",
            "isbn": "book_isbn",
            "date_format": "%d/%m/%Y",
        }
        mapping = FieldMapping.from_dict(data)

        assert mapping.title == "book_title"
        assert mapping.author == "book_author"
        assert mapping.isbn == "book_isbn"
        assert mapping.date_format == "%d/%m/%Y"

    def test_auto_detect_standard_columns(self):
        """Test auto-detection with standard column names."""
        columns = ["title", "author", "isbn", "rating", "status"]
        mapping = FieldMapping.auto_detect(columns)

        assert mapping.title == "title"
        assert mapping.author == "author"
        assert mapping.isbn == "isbn"
        assert mapping.rating == "rating"
        assert mapping.status == "status"

    def test_auto_detect_alternative_names(self):
        """Test auto-detection with alternative column names."""
        columns = ["Book Title", "Writer", "ISBN-13", "Stars", "Reading Status"]
        mapping = FieldMapping.auto_detect(columns)

        # Should detect despite different names
        assert mapping.title is not None
        assert mapping.author is not None

    def test_auto_detect_case_insensitive(self):
        """Test auto-detection is case insensitive."""
        columns = ["TITLE", "AUTHOR", "ISBN", "RATING"]
        mapping = FieldMapping.auto_detect(columns)

        assert mapping.title == "TITLE"
        assert mapping.author == "AUTHOR"

    def test_auto_detect_date_columns(self):
        """Test auto-detection of date columns."""
        columns = ["title", "author", "date added", "date finished", "date started"]
        mapping = FieldMapping.auto_detect(columns)

        assert mapping.date_added == "date added"
        assert mapping.date_finished == "date finished"
        assert mapping.date_started == "date started"


class TestGenericCSVImporter:
    """Tests for GenericCSVImporter class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def importer(self, db):
        """Create importer instance."""
        return GenericCSVImporter(db)

    @pytest.fixture
    def standard_csv(self, tmp_path):
        """Create a CSV with standard column names."""
        csv_path = tmp_path / "books.csv"

        headers = ["title", "author", "isbn", "rating", "status", "tags", "date added"]

        rows = [
            {
                "title": "Test Book 1",
                "author": "Author One",
                "isbn": "1234567890",
                "rating": "5",
                "status": "read",
                "tags": "fiction, test",
                "date added": "2024-01-15",
            },
            {
                "title": "Test Book 2",
                "author": "Author Two",
                "isbn": "0987654321",
                "rating": "4",
                "status": "reading",
                "tags": "non-fiction",
                "date added": "2024-01-10",
            },
            {
                "title": "Test Book 3",
                "author": "Author Three",
                "rating": "",
                "status": "to read",
                "date added": "2024-01-05",
            },
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                full_row = {h: row.get(h, "") for h in headers}
                writer.writerow(full_row)

        return csv_path

    @pytest.fixture
    def custom_csv(self, tmp_path):
        """Create a CSV with custom column names."""
        csv_path = tmp_path / "my_books.csv"

        headers = ["Book Name", "Writer", "Book Number", "My Score", "State", "Categories"]

        rows = [
            {
                "Book Name": "Custom Book",
                "Writer": "Custom Author",
                "Book Number": "1111111111",
                "My Score": "5",
                "State": "completed",
                "Categories": "genre1; genre2",
            },
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        return csv_path

    def test_validate_valid_file(self, importer, standard_csv):
        """Test validation of valid CSV file."""
        is_valid, error = importer.validate_file(standard_csv)
        assert is_valid is True
        assert error is None

    def test_validate_missing_file(self, importer, tmp_path):
        """Test validation of missing file."""
        is_valid, error = importer.validate_file(tmp_path / "nonexistent.csv")
        assert is_valid is False
        assert "not found" in error.lower()

    def test_validate_wrong_extension(self, importer, tmp_path):
        """Test validation of non-CSV file."""
        txt_file = tmp_path / "file.txt"
        txt_file.write_text("test")

        is_valid, error = importer.validate_file(txt_file)
        assert is_valid is False
        assert "csv" in error.lower()

    def test_validate_empty_file(self, importer, tmp_path):
        """Test validation of empty CSV file."""
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("title,author\n")  # Header but no data

        is_valid, error = importer.validate_file(csv_path)
        assert is_valid is False
        assert "empty" in error.lower()

    def test_parse_file_auto_detect(self, importer, standard_csv):
        """Test parsing with auto-detected field mapping."""
        records = importer.parse_file(standard_csv)

        assert len(records) == 3

        # Check first record
        assert records[0].title == "Test Book 1"
        assert records[0].author == "Author One"
        assert records[0].isbn == "1234567890"
        assert records[0].rating == 5

    def test_parse_file_custom_mapping(self, db, custom_csv):
        """Test parsing with custom field mapping."""
        mapping = FieldMapping(
            title="Book Name",
            author="Writer",
            isbn="Book Number",
            rating="My Score",
            status="State",
            tags="Categories",
            tag_separator=";",
        )
        importer = GenericCSVImporter(db, mapping=mapping)

        records = importer.parse_file(custom_csv)

        assert len(records) == 1
        assert records[0].title == "Custom Book"
        assert records[0].author == "Custom Author"
        assert records[0].isbn == "1111111111"
        assert records[0].rating == 5
        assert "genre1" in records[0].tags
        assert "genre2" in records[0].tags

    def test_status_parsing(self, importer, standard_csv):
        """Test status value parsing."""
        records = importer.parse_file(standard_csv)

        assert records[0].status == BookStatus.COMPLETED  # "read"
        assert records[1].status == BookStatus.READING  # "reading"
        assert records[2].status == BookStatus.WISHLIST  # "to read"

    def test_tags_parsing(self, importer, standard_csv):
        """Test tags parsing with default separator."""
        records = importer.parse_file(standard_csv)

        assert "fiction" in records[0].tags
        assert "test" in records[0].tags
        assert "non-fiction" in records[1].tags

    def test_date_parsing_iso_format(self, importer, standard_csv):
        """Test ISO date format parsing."""
        records = importer.parse_file(standard_csv)

        assert records[0].date_added == "2024-01-15"

    def test_date_parsing_various_formats(self, db, tmp_path):
        """Test parsing various date formats."""
        csv_path = tmp_path / "dates.csv"

        headers = ["title", "author", "date added"]
        rows = [
            {"title": "Book 1", "author": "Author", "date added": "2024-01-15"},
            {"title": "Book 2", "author": "Author", "date added": "2024/01/15"},
            {"title": "Book 3", "author": "Author", "date added": "01/15/2024"},
            {"title": "Book 4", "author": "Author", "date added": "January 15, 2024"},
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        importer = GenericCSVImporter(db)
        records = importer.parse_file(csv_path)

        # All should parse to valid dates
        for record in records:
            assert record.date_added is not None
            assert "2024" in record.date_added

    def test_empty_rating_is_none(self, importer, standard_csv):
        """Test empty rating becomes None."""
        records = importer.parse_file(standard_csv)

        assert records[2].rating is None

    def test_import_file(self, importer, standard_csv):
        """Test full import."""
        result = importer.import_file(standard_csv)

        assert result.success is True
        assert result.imported == 3
        assert result.errors == 0

    def test_import_dry_run(self, importer, standard_csv, db):
        """Test dry run import."""
        result = importer.import_file(standard_csv, dry_run=True)

        assert result.success is True
        assert result.imported == 3

        # Verify nothing was actually imported
        from sqlalchemy import select, func
        from vibecoding.booktracker.db.models import Book

        with db.get_session() as session:
            count = session.execute(select(func.count()).select_from(Book)).scalar()
            assert count == 0

    def test_import_skip_duplicates(self, importer, standard_csv):
        """Test skipping duplicate books."""
        # Import once
        result1 = importer.import_file(standard_csv)
        assert result1.imported == 3

        # Import again with SKIP mode
        result2 = importer.import_file(
            standard_csv,
            duplicate_handling=DuplicateHandling.SKIP,
        )
        assert result2.imported == 0
        assert result2.skipped == 3

    def test_get_columns(self, importer, standard_csv):
        """Test getting column names from file."""
        columns = importer.get_columns(standard_csv)

        assert "title" in columns
        assert "author" in columns
        assert "isbn" in columns

    def test_get_sample_data(self, importer, standard_csv):
        """Test getting sample data from file."""
        samples = importer.get_sample_data(standard_csv, rows=2)

        assert len(samples) == 2
        assert samples[0]["title"] == "Test Book 1"
        assert samples[1]["title"] == "Test Book 2"

    def test_preview_import(self, importer, standard_csv):
        """Test import preview."""
        preview = importer.preview_import(standard_csv)

        assert preview["valid"] is True
        assert preview["total_records"] == 3
        assert preview["new_books"] == 3

    def test_skip_rows_without_title(self, db, tmp_path):
        """Test rows without title are skipped."""
        csv_path = tmp_path / "incomplete.csv"

        headers = ["title", "author"]
        rows = [
            {"title": "Valid Book", "author": "Valid Author"},
            {"title": "", "author": "No Title Author"},
            {"title": "Another Book", "author": ""},
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        importer = GenericCSVImporter(db)
        records = importer.parse_file(csv_path)

        # Only the first row should be valid
        assert len(records) == 1
        assert records[0].title == "Valid Book"

    def test_utf8_bom_handling(self, db, tmp_path):
        """Test handling of UTF-8 BOM in CSV files."""
        csv_path = tmp_path / "bom.csv"

        # Write with BOM
        with open(csv_path, "w", encoding="utf-8-sig") as f:
            f.write("title,author\n")
            f.write("BOM Book,BOM Author\n")

        importer = GenericCSVImporter(db)
        records = importer.parse_file(csv_path)

        assert len(records) == 1
        assert records[0].title == "BOM Book"

    def test_series_parsing(self, db, tmp_path):
        """Test series and series index parsing."""
        csv_path = tmp_path / "series.csv"

        headers = ["title", "author", "series", "series index"]
        rows = [
            {"title": "Book 1", "author": "Author", "series": "My Series", "series index": "1"},
            {"title": "Book 2", "author": "Author", "series": "My Series", "series index": "2.5"},
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        mapping = FieldMapping(
            title="title",
            author="author",
            series="series",
            series_index="series index",
        )
        importer = GenericCSVImporter(db, mapping=mapping)
        records = importer.parse_file(csv_path)

        assert records[0].series == "My Series"
        assert records[0].series_index == 1.0
        assert records[1].series_index == 2.5
