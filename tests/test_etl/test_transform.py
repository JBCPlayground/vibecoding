"""Tests for data transformation."""

import pytest

from src.vibecoding.booktracker.db.schemas import BookSource, BookStatus
from src.vibecoding.booktracker.etl.transform import (
    transform_calibre_row,
    transform_goodreads_row,
    transform_notion_row,
    transform_row,
    _clean_isbn,
    _parse_date,
    _parse_rating,
)


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_clean_isbn_goodreads_format(self):
        """Test cleaning Goodreads ="" wrapper."""
        assert _clean_isbn('="0385350597"') == "0385350597"
        assert _clean_isbn('="9780385350594"') == "9780385350594"

    def test_clean_isbn_normal(self):
        """Test normal ISBN is preserved."""
        assert _clean_isbn("0385350597") == "0385350597"
        assert _clean_isbn("9780385350594") == "9780385350594"

    def test_clean_isbn_empty(self):
        """Test empty ISBN returns None."""
        assert _clean_isbn("") is None
        assert _clean_isbn(None) is None
        assert _clean_isbn("  ") is None

    def test_parse_date_various_formats(self):
        """Test parsing dates in various formats."""
        from datetime import date

        assert _parse_date("2025-01-15") == date(2025, 1, 15)
        assert _parse_date("2025/01/15") == date(2025, 1, 15)
        assert _parse_date("01/15/2025") == date(2025, 1, 15)
        assert _parse_date("") is None
        assert _parse_date(None) is None

    def test_parse_rating_standard_scale(self):
        """Test parsing ratings on 1-5 scale."""
        assert _parse_rating("5") == 5
        assert _parse_rating("3") == 3
        assert _parse_rating("0") is None
        assert _parse_rating("") is None

    def test_parse_rating_calibre_scale(self):
        """Test normalizing Calibre 0-10 scale."""
        assert _parse_rating("10", scale_max=10) == 5
        assert _parse_rating("8", scale_max=10) == 4
        assert _parse_rating("6", scale_max=10) == 3
        assert _parse_rating("0", scale_max=10) is None


class TestTransformNotion:
    """Tests for Notion row transformation."""

    def test_transform_notion_basic(self):
        """Test basic Notion transformation."""
        raw = {
            "Title": "The Great Gatsby",
            "Author": "F. Scott Fitzgerald",
            "Status": "Read",
            "Rating": "5",
            "ISBN": "0743273567",
            "ISBN-13": "9780743273565",
            "Pages": "180",
            "Added": "2025-01-01",
        }
        book = transform_notion_row(raw)

        assert book.title == "The Great Gatsby"
        assert book.author == "F. Scott Fitzgerald"
        assert book.status == BookStatus.COMPLETED
        assert book.rating == 5
        assert book.isbn == "0743273567"
        assert book.isbn13 == "9780743273565"
        assert book.page_count == 180
        assert BookSource.NOTION in book.sources

    def test_transform_notion_status_mapping(self):
        """Test Notion status value mapping."""
        statuses = [
            ("Read", BookStatus.COMPLETED),
            ("Skimmed", BookStatus.SKIMMED),
            ("Borrowed", BookStatus.READING),
            ("Want to Read", BookStatus.WISHLIST),
            ("On Hold", BookStatus.ON_HOLD),
            ("", BookStatus.WISHLIST),
        ]

        for raw_status, expected in statuses:
            book = transform_notion_row({"Title": "Test", "Author": "Author", "Status": raw_status})
            assert book.status == expected, f"Status '{raw_status}' should map to {expected}"

    def test_transform_notion_read_next_checkbox(self):
        """Test Read Next checkbox parsing."""
        for true_value in ["true", "True", "yes", "1", "checked"]:
            book = transform_notion_row({
                "Title": "Test",
                "Author": "Author",
                "Read Next": true_value,
            })
            assert book.read_next is True

        for false_value in ["false", "False", "no", "0", ""]:
            book = transform_notion_row({
                "Title": "Test",
                "Author": "Author",
                "Read Next": false_value,
            })
            assert book.read_next is False


class TestTransformCalibre:
    """Tests for Calibre row transformation."""

    def test_transform_calibre_basic(self):
        """Test basic Calibre transformation."""
        raw = {
            "title": "Dune",
            "authors": "Frank Herbert",
            "rating": "10",
            "isbn": "9780441172719",
            "uuid": "abc-123",
            "formats": "epub,mobi",
            "id": "42",
            "identifiers": "goodreads:234225,mobi-asin:B00B7NPRY8",
        }
        book = transform_calibre_row(raw)

        assert book.title == "Dune"
        assert book.author == "Frank Herbert"
        assert book.rating == 5  # Normalized from 10
        assert book.isbn == "9780441172719"
        assert book.calibre_uuid == "abc-123"
        assert book.calibre_id == 42
        assert "epub" in book.file_formats
        assert "mobi" in book.file_formats
        assert book.identifiers["goodreads"] == "234225"
        assert BookSource.CALIBRE in book.sources

    def test_transform_calibre_rating_normalization(self):
        """Test Calibre 0-10 to 1-5 rating conversion."""
        ratings = [
            ("10", 5),
            ("8", 4),
            ("6", 3),
            ("4", 2),
            ("2", 1),
            ("0", None),
        ]

        for raw_rating, expected in ratings:
            book = transform_calibre_row({
                "title": "Test",
                "authors": "Author",
                "rating": raw_rating,
            })
            assert book.rating == expected

    def test_transform_calibre_identifiers_parsing(self):
        """Test parsing Calibre identifiers string."""
        raw = {
            "title": "Test",
            "authors": "Author",
            "identifiers": "goodreads:123,isbn:978123,mobi-asin:B00ABC",
        }
        book = transform_calibre_row(raw)

        assert book.identifiers["goodreads"] == "123"
        assert book.identifiers["isbn"] == "978123"
        assert book.identifiers["mobi-asin"] == "B00ABC"


class TestTransformGoodreads:
    """Tests for Goodreads row transformation."""

    def test_transform_goodreads_basic(self):
        """Test basic Goodreads transformation."""
        raw = {
            "Title": "Project Hail Mary",
            "Author": "Andy Weir",
            "My Rating": "5",
            "ISBN": '="0593135202"',
            "ISBN13": '="9780593135204"',
            "Book Id": "54493401",
            "Exclusive Shelf": "read",
            "Date Read": "2024-06-15",
        }
        book = transform_goodreads_row(raw)

        assert book.title == "Project Hail Mary"
        assert book.author == "Andy Weir"
        assert book.rating == 5
        assert book.isbn == "0593135202"  # Cleaned
        assert book.isbn13 == "9780593135204"  # Cleaned
        assert book.goodreads_id == 54493401
        assert book.status == BookStatus.COMPLETED
        assert BookSource.GOODREADS in book.sources

    def test_transform_goodreads_status_mapping(self):
        """Test Goodreads Exclusive Shelf mapping."""
        statuses = [
            ("read", BookStatus.COMPLETED),
            ("currently-reading", BookStatus.READING),
            ("to-read", BookStatus.WISHLIST),
            ("", BookStatus.WISHLIST),
        ]

        for raw_status, expected in statuses:
            book = transform_goodreads_row({
                "Title": "Test",
                "Author": "Author",
                "Exclusive Shelf": raw_status,
            })
            assert book.status == expected

    def test_transform_goodreads_isbn_cleaning(self):
        """Test that Goodreads ISBN wrapper is cleaned."""
        raw = {
            "Title": "Test",
            "Author": "Author",
            "ISBN": '="0385350597"',
            "ISBN13": '="9780385350594"',
        }
        book = transform_goodreads_row(raw)

        assert book.isbn == "0385350597"
        assert book.isbn13 == "9780385350594"


class TestTransformRow:
    """Tests for the generic transform_row function."""

    def test_transform_row_dispatches_correctly(self):
        """Test that transform_row dispatches to correct transformer."""
        notion = {"source": "notion", "raw": {"Title": "Notion Book", "Author": "Author"}}
        calibre = {"source": "calibre", "raw": {"title": "Calibre Book", "authors": "Author"}}
        goodreads = {"source": "goodreads", "raw": {"Title": "Goodreads Book", "Author": "Author"}}

        assert transform_row(notion).title == "Notion Book"
        assert transform_row(calibre).title == "Calibre Book"
        assert transform_row(goodreads).title == "Goodreads Book"
