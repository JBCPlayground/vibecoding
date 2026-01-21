"""Tests for Goodreads importer."""

import csv
import pytest
from pathlib import Path

from vibecoding.booktracker.imports.goodreads import GoodreadsImporter
from vibecoding.booktracker.imports.base import DuplicateHandling
from vibecoding.booktracker.db.schemas import BookStatus


class TestGoodreadsImporter:
    """Tests for GoodreadsImporter class."""

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
        return GoodreadsImporter(db)

    @pytest.fixture
    def goodreads_csv(self, tmp_path):
        """Create a sample Goodreads CSV file."""
        csv_path = tmp_path / "goodreads_export.csv"

        headers = [
            "Book Id", "Title", "Author", "Author l-f", "Additional Authors",
            "ISBN", "ISBN13", "My Rating", "Average Rating", "Publisher",
            "Binding", "Number of Pages", "Year Published",
            "Original Publication Year", "Date Read", "Date Added",
            "Bookshelves", "Bookshelves with positions", "Exclusive Shelf",
            "My Review", "Spoiler", "Private Notes", "Read Count", "Owned Copies"
        ]

        rows = [
            {
                "Book Id": "1",
                "Title": "The Great Gatsby",
                "Author": "Fitzgerald, F. Scott",
                "Author l-f": "Fitzgerald, F. Scott",
                "ISBN": '="0743273567"',
                "ISBN13": '="9780743273565"',
                "My Rating": "5",
                "Average Rating": "3.91",
                "Publisher": "Scribner",
                "Number of Pages": "180",
                "Year Published": "2004",
                "Original Publication Year": "1925",
                "Date Read": "2024/01/15",
                "Date Added": "2023/12/01",
                "Bookshelves": "classics, favorites",
                "Exclusive Shelf": "read",
                "My Review": "A masterpiece!",
                "Private Notes": "Gift from dad",
            },
            {
                "Book Id": "2",
                "Title": "1984",
                "Author": "Orwell, George",
                "ISBN": '="0451524934"',
                "ISBN13": '="9780451524935"',
                "My Rating": "4",
                "Number of Pages": "328",
                "Year Published": "1961",
                "Original Publication Year": "1949",
                "Date Added": "2024/01/01",
                "Bookshelves": "dystopian, classics",
                "Exclusive Shelf": "currently-reading",
            },
            {
                "Book Id": "3",
                "Title": "Dune",
                "Author": "Herbert, Frank",
                "ISBN": "",
                "My Rating": "0",
                "Number of Pages": "688",
                "Date Added": "2024/01/10",
                "Exclusive Shelf": "to-read",
            },
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                # Fill in empty values for missing keys
                full_row = {h: row.get(h, "") for h in headers}
                writer.writerow(full_row)

        return csv_path

    def test_validate_valid_file(self, importer, goodreads_csv):
        """Test validation of valid Goodreads file."""
        is_valid, error = importer.validate_file(goodreads_csv)
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

    def test_validate_missing_columns(self, importer, tmp_path):
        """Test validation with missing required columns."""
        csv_path = tmp_path / "incomplete.csv"
        with open(csv_path, "w") as f:
            f.write("SomeColumn,OtherColumn\n")
            f.write("value1,value2\n")

        is_valid, error = importer.validate_file(csv_path)
        assert is_valid is False
        assert "missing" in error.lower()

    def test_parse_file(self, importer, goodreads_csv):
        """Test parsing Goodreads file."""
        records = importer.parse_file(goodreads_csv)

        assert len(records) == 3

        # Check first record
        gatsby = records[0]
        assert gatsby.title == "The Great Gatsby"
        assert gatsby.author == "F. Scott Fitzgerald"  # Should be normalized
        assert gatsby.isbn == "0743273567"
        assert gatsby.isbn13 == "9780743273565"
        assert gatsby.rating == 5
        assert gatsby.page_count == 180
        assert gatsby.status == BookStatus.COMPLETED
        assert gatsby.publication_year == 1925
        assert "Classics" in gatsby.tags
        assert "Favorites" in gatsby.tags
        assert "masterpiece" in gatsby.comments.lower()

    def test_parse_author_normalization(self, importer, goodreads_csv):
        """Test author name normalization."""
        records = importer.parse_file(goodreads_csv)

        # "Fitzgerald, F. Scott" -> "F. Scott Fitzgerald"
        assert records[0].author == "F. Scott Fitzgerald"
        # "Orwell, George" -> "George Orwell"
        assert records[1].author == "George Orwell"
        # "Herbert, Frank" -> "Frank Herbert"
        assert records[2].author == "Frank Herbert"

    def test_parse_status_mapping(self, importer, goodreads_csv):
        """Test status mapping from shelves."""
        records = importer.parse_file(goodreads_csv)

        assert records[0].status == BookStatus.COMPLETED  # read
        assert records[1].status == BookStatus.READING  # currently-reading
        assert records[2].status == BookStatus.WISHLIST  # to-read

    def test_parse_rating_zero_as_none(self, importer, goodreads_csv):
        """Test that rating 0 is treated as no rating."""
        records = importer.parse_file(goodreads_csv)

        # Dune has rating "0" which means not rated
        dune = records[2]
        assert dune.rating is None

    def test_import_file(self, importer, goodreads_csv):
        """Test full import."""
        result = importer.import_file(goodreads_csv)

        assert result.success is True
        assert result.imported == 3
        assert result.errors == 0

    def test_import_dry_run(self, importer, goodreads_csv, db):
        """Test dry run import."""
        result = importer.import_file(goodreads_csv, dry_run=True)

        assert result.success is True
        assert result.imported == 3

        # Verify nothing was actually imported
        from sqlalchemy import select, func
        from vibecoding.booktracker.db.models import Book

        with db.get_session() as session:
            count = session.execute(select(func.count()).select_from(Book)).scalar()
            assert count == 0

    def test_import_skip_duplicates(self, importer, goodreads_csv, db):
        """Test skipping duplicate books."""
        # Import once
        result1 = importer.import_file(goodreads_csv)
        assert result1.imported == 3

        # Import again with SKIP mode
        result2 = importer.import_file(
            goodreads_csv,
            duplicate_handling=DuplicateHandling.SKIP,
        )
        assert result2.imported == 0
        assert result2.skipped == 3

    def test_import_update_duplicates(self, importer, goodreads_csv, db):
        """Test updating duplicate books."""
        # Import once
        importer.import_file(goodreads_csv)

        # Import again with UPDATE mode
        result = importer.import_file(
            goodreads_csv,
            duplicate_handling=DuplicateHandling.UPDATE,
        )
        assert result.updated == 3
        assert result.imported == 0

    def test_preview_import(self, importer, goodreads_csv):
        """Test import preview."""
        preview = importer.preview_import(goodreads_csv)

        assert preview["valid"] is True
        assert preview["total_records"] == 3
        assert preview["new_books"] == 3
        assert preview["existing_books"] == 0
        assert "source_type" in preview

    def test_isbn_cleaning(self, importer, goodreads_csv):
        """Test ISBN cleaning from Goodreads format."""
        records = importer.parse_file(goodreads_csv)

        # ISBN should have quotes and equals removed
        assert records[0].isbn == "0743273567"
        assert records[0].isbn13 == "9780743273565"

    def test_date_parsing(self, importer, goodreads_csv):
        """Test date parsing."""
        records = importer.parse_file(goodreads_csv)

        assert records[0].date_finished == "2024-01-15"
        assert records[0].date_added == "2023-12-01"

    def test_tags_exclude_standard_shelves(self, importer, goodreads_csv):
        """Test that standard shelves are excluded from tags."""
        records = importer.parse_file(goodreads_csv)

        # "read", "currently-reading", "to-read" should not be in tags
        for record in records:
            tags_lower = [t.lower() for t in record.tags]
            assert "read" not in tags_lower
            assert "currently-reading" not in tags_lower
            assert "to-read" not in tags_lower
