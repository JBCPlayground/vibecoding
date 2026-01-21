"""Tests for Calibre importer."""

import csv
import sqlite3
import pytest
from pathlib import Path

from vibecoding.booktracker.imports.calibre import CalibreImporter, CalibreLibraryImporter
from vibecoding.booktracker.imports.base import DuplicateHandling
from vibecoding.booktracker.db.schemas import BookStatus


class TestCalibreImporter:
    """Tests for CalibreImporter (CSV export)."""

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
        return CalibreImporter(db)

    @pytest.fixture
    def calibre_csv(self, tmp_path):
        """Create a sample Calibre CSV export file."""
        csv_path = tmp_path / "calibre_export.csv"

        headers = [
            "id", "title", "authors", "author_sort", "rating", "timestamp",
            "pubdate", "publisher", "isbn", "series", "series_index",
            "tags", "comments", "size", "formats", "identifiers",
            "languages", "library_name"
        ]

        rows = [
            {
                "id": "1",
                "title": "The Hobbit",
                "authors": "J.R.R. Tolkien",
                "author_sort": "Tolkien, J.R.R.",
                "rating": "10",  # Calibre uses 0-10 scale
                "timestamp": "2024-01-15T10:30:00+00:00",
                "pubdate": "1937-09-21T00:00:00+00:00",
                "publisher": "George Allen & Unwin",
                "isbn": "9780547928227",
                "series": "Middle-earth",
                "series_index": "0.5",
                "tags": "fantasy, adventure, classic",
                "comments": "<p>A great adventure story!</p>",
                "formats": "EPUB, MOBI",
                "identifiers": "isbn:9780547928227",
            },
            {
                "id": "2",
                "title": "Foundation",
                "authors": "Isaac Asimov",
                "rating": "8",
                "timestamp": "2024-01-10T08:00:00+00:00",
                "pubdate": "1951-01-01T00:00:00+00:00",
                "isbn": "9780553293357",
                "series": "Foundation",
                "series_index": "1",
                "tags": "science fiction, space opera",
            },
            {
                "id": "3",
                "title": "Neuromancer",
                "authors": "William Gibson",
                "rating": "0",  # Not rated
                "timestamp": "2024-01-05T12:00:00+00:00",
                "tags": "cyberpunk, science fiction",
            },
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                full_row = {h: row.get(h, "") for h in headers}
                writer.writerow(full_row)

        return csv_path

    def test_validate_valid_file(self, importer, calibre_csv):
        """Test validation of valid Calibre file."""
        is_valid, error = importer.validate_file(calibre_csv)
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

    def test_parse_file(self, importer, calibre_csv):
        """Test parsing Calibre file."""
        records = importer.parse_file(calibre_csv)

        assert len(records) == 3

        # Check first record
        hobbit = records[0]
        assert hobbit.title == "The Hobbit"
        assert hobbit.author == "J.R.R. Tolkien"
        # ISBN13 goes in isbn13 field, not isbn
        assert hobbit.isbn13 == "9780547928227"
        assert hobbit.rating == 5  # 10/2 = 5
        assert hobbit.series == "Middle-earth"
        assert hobbit.series_index == 0.5
        assert "Fantasy" in hobbit.tags or "fantasy" in [t.lower() for t in hobbit.tags]

    def test_rating_conversion(self, importer, calibre_csv):
        """Test Calibre rating (0-10) converts to 1-5 scale."""
        records = importer.parse_file(calibre_csv)

        # Rating 10 -> 5
        assert records[0].rating == 5
        # Rating 8 -> 4
        assert records[1].rating == 4
        # Rating 0 -> None
        assert records[2].rating is None

    def test_html_comment_cleaning(self, importer, calibre_csv):
        """Test HTML tags are stripped from comments (stored in description)."""
        records = importer.parse_file(calibre_csv)

        # "<p>A great adventure story!</p>" -> "A great adventure story!"
        # Calibre stores cleaned comments in description field
        assert "<p>" not in (records[0].description or "")
        assert "great adventure" in (records[0].description or "").lower()

    def test_series_parsing(self, importer, calibre_csv):
        """Test series and series index parsing."""
        records = importer.parse_file(calibre_csv)

        assert records[0].series == "Middle-earth"
        assert records[0].series_index == 0.5
        assert records[1].series == "Foundation"
        assert records[1].series_index == 1.0

    def test_import_file(self, importer, calibre_csv):
        """Test full import."""
        result = importer.import_file(calibre_csv)

        assert result.success is True
        assert result.imported == 3
        assert result.errors == 0

    def test_import_dry_run(self, importer, calibre_csv, db):
        """Test dry run import."""
        result = importer.import_file(calibre_csv, dry_run=True)

        assert result.success is True
        assert result.imported == 3

        # Verify nothing was actually imported
        from sqlalchemy import select, func
        from vibecoding.booktracker.db.models import Book

        with db.get_session() as session:
            count = session.execute(select(func.count()).select_from(Book)).scalar()
            assert count == 0


class TestCalibreLibraryImporter:
    """Tests for CalibreLibraryImporter (direct database access)."""

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
        return CalibreLibraryImporter(db)

    @pytest.fixture
    def calibre_db(self, tmp_path):
        """Create a mock Calibre library directory with metadata.db database."""
        library_path = tmp_path / "calibre_library"
        library_path.mkdir(parents=True, exist_ok=True)
        db_path = library_path / "metadata.db"

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create minimal Calibre schema
        cursor.execute("""
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                sort TEXT,
                timestamp TEXT,
                pubdate TEXT,
                series_index REAL,
                isbn TEXT,
                path TEXT,
                uuid TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE authors (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                sort TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE books_authors_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                author INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE books_tags_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                tag INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE series (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE books_series_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                series INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE publishers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE books_publishers_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                publisher INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE ratings (
                id INTEGER PRIMARY KEY,
                rating INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE books_ratings_link (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                rating INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE comments (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                text TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE identifiers (
                id INTEGER PRIMARY KEY,
                book INTEGER NOT NULL,
                type TEXT NOT NULL,
                val TEXT NOT NULL
            )
        """)

        # Insert test data
        # Books
        cursor.execute(
            "INSERT INTO books (id, title, sort, timestamp, pubdate, series_index, isbn, path, uuid) VALUES (1, 'The Hobbit', 'Hobbit, The', '2024-01-15', '1937-09-21', 0.5, '9780547928227', 'Tolkien/Hobbit', 'uuid-1')"
        )
        cursor.execute(
            "INSERT INTO books (id, title, sort, timestamp, pubdate, series_index, isbn, path, uuid) VALUES (2, 'Foundation', 'Foundation', '2024-01-10', '1951-01-01', 1.0, NULL, 'Asimov/Foundation', 'uuid-2')"
        )

        # Authors
        cursor.execute("INSERT INTO authors VALUES (1, 'J.R.R. Tolkien', 'Tolkien, J.R.R.')")
        cursor.execute("INSERT INTO authors VALUES (2, 'Isaac Asimov', 'Asimov, Isaac')")
        cursor.execute("INSERT INTO books_authors_link VALUES (1, 1, 1)")
        cursor.execute("INSERT INTO books_authors_link VALUES (2, 2, 2)")

        # Tags
        cursor.execute("INSERT INTO tags VALUES (1, 'Fantasy')")
        cursor.execute("INSERT INTO tags VALUES (2, 'Science Fiction')")
        cursor.execute("INSERT INTO books_tags_link VALUES (1, 1, 1)")
        cursor.execute("INSERT INTO books_tags_link VALUES (2, 2, 2)")

        # Series
        cursor.execute("INSERT INTO series VALUES (1, 'Middle-earth')")
        cursor.execute("INSERT INTO series VALUES (2, 'Foundation')")
        cursor.execute("INSERT INTO books_series_link VALUES (1, 1, 1)")
        cursor.execute("INSERT INTO books_series_link VALUES (2, 2, 2)")

        # Publishers
        cursor.execute("INSERT INTO publishers VALUES (1, 'George Allen & Unwin')")
        cursor.execute("INSERT INTO books_publishers_link VALUES (1, 1, 1)")

        # Ratings (Calibre uses 0-10 scale, stores as * 2)
        cursor.execute("INSERT INTO ratings VALUES (1, 10)")
        cursor.execute("INSERT INTO ratings VALUES (2, 8)")
        cursor.execute("INSERT INTO books_ratings_link VALUES (1, 1, 1)")
        cursor.execute("INSERT INTO books_ratings_link VALUES (2, 2, 2)")

        # Comments
        cursor.execute("INSERT INTO comments VALUES (1, 1, '<p>A classic adventure!</p>')")

        # Identifiers
        cursor.execute("INSERT INTO identifiers VALUES (1, 1, 'isbn', '9780547928227')")
        cursor.execute("INSERT INTO identifiers VALUES (2, 2, 'isbn', '9780553293357')")

        conn.commit()
        conn.close()

        # Return library directory path (not metadata.db path)
        return library_path

    def test_validate_valid_library(self, importer, calibre_db):
        """Test validation of valid Calibre library."""
        is_valid, error = importer.validate_file(calibre_db)
        assert is_valid is True
        assert error is None

    def test_validate_missing_file(self, importer, tmp_path):
        """Test validation of missing library."""
        is_valid, error = importer.validate_file(tmp_path / "nonexistent" / "metadata.db")
        assert is_valid is False
        assert "not found" in error.lower()

    def test_validate_wrong_file(self, importer, tmp_path):
        """Test validation of wrong file type."""
        txt_file = tmp_path / "metadata.txt"
        txt_file.write_text("test")

        is_valid, error = importer.validate_file(txt_file)
        assert is_valid is False

    def test_parse_file(self, importer, calibre_db):
        """Test parsing Calibre library."""
        records = importer.parse_file(calibre_db)

        assert len(records) == 2

        # Check records (order may vary)
        titles = {r.title for r in records}
        assert "The Hobbit" in titles
        assert "Foundation" in titles

    def test_author_extraction(self, importer, calibre_db):
        """Test author extraction from library."""
        records = importer.parse_file(calibre_db)

        record_map = {r.title: r for r in records}
        assert record_map["The Hobbit"].author == "J.R.R. Tolkien"
        assert record_map["Foundation"].author == "Isaac Asimov"

    def test_series_extraction(self, importer, calibre_db):
        """Test series extraction from library."""
        records = importer.parse_file(calibre_db)

        record_map = {r.title: r for r in records}
        assert record_map["The Hobbit"].series == "Middle-earth"
        assert record_map["The Hobbit"].series_index == 0.5
        assert record_map["Foundation"].series == "Foundation"
        assert record_map["Foundation"].series_index == 1.0

    def test_tags_extraction(self, importer, calibre_db):
        """Test tags extraction from library."""
        records = importer.parse_file(calibre_db)

        record_map = {r.title: r for r in records}
        assert "Fantasy" in record_map["The Hobbit"].tags
        assert "Science Fiction" in record_map["Foundation"].tags

    def test_rating_conversion(self, importer, calibre_db):
        """Test rating conversion from Calibre scale."""
        records = importer.parse_file(calibre_db)

        record_map = {r.title: r for r in records}
        # Rating 10 -> 5
        assert record_map["The Hobbit"].rating == 5
        # Rating 8 -> 4
        assert record_map["Foundation"].rating == 4

    def test_import_file(self, importer, calibre_db):
        """Test full import from library."""
        result = importer.import_file(calibre_db)

        assert result.success is True
        assert result.imported == 2
        assert result.errors == 0

    def test_preview_import(self, importer, calibre_db):
        """Test import preview."""
        preview = importer.preview_import(calibre_db)

        assert preview["valid"] is True
        assert preview["total_records"] == 2
        assert preview["new_books"] == 2
