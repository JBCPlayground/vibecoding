"""Tests for Pydantic schemas."""

from datetime import date

import pytest
from pydantic import ValidationError

from src.vibecoding.booktracker.db.schemas import (
    BookCreate,
    BookResponse,
    BookStatus,
    BookSource,
    BookUpdate,
    ReadingLogCreate,
)


class TestBookCreate:
    """Tests for BookCreate schema."""

    def test_create_minimal_book(self):
        """Test creating a book with only required fields."""
        book = BookCreate(title="Test Book", author="Test Author")
        assert book.title == "Test Book"
        assert book.author == "Test Author"
        assert book.status == BookStatus.WISHLIST  # default
        assert book.rating is None
        assert book.sources == [BookSource.MANUAL]

    def test_create_full_book(self, sample_book_data):
        """Test creating a book with all fields."""
        assert sample_book_data.title == "The Great Gatsby"
        assert sample_book_data.author == "F. Scott Fitzgerald"
        assert sample_book_data.status == BookStatus.COMPLETED
        assert sample_book_data.rating == 5
        assert sample_book_data.isbn == "9780743273565"

    def test_empty_title_rejected(self):
        """Test that empty title is rejected."""
        with pytest.raises(ValidationError):
            BookCreate(title="", author="Test Author")

    def test_empty_author_rejected(self):
        """Test that empty author is rejected."""
        with pytest.raises(ValidationError):
            BookCreate(title="Test Book", author="")

    def test_rating_bounds(self):
        """Test that rating must be 1-5 (or normalized from Calibre 0-10 scale)."""
        # Valid ratings
        for rating in [1, 2, 3, 4, 5]:
            book = BookCreate(title="Test", author="Author", rating=rating)
            assert book.rating == rating

        # Rating 0 is normalized to None (Calibre compatibility)
        book = BookCreate(title="Test", author="Author", rating=0)
        assert book.rating is None

        # Ratings > 5 are normalized using Calibre scale (v // 2)
        book = BookCreate(title="Test", author="Author", rating=11)
        assert book.rating == 5  # 11 // 2 = 5

    def test_isbn_cleaning_goodreads_format(self):
        """Test that Goodreads ISBN format is cleaned."""
        book = BookCreate(
            title="Test",
            author="Author",
            isbn='="0385350597"',
            isbn13='="9780385350594"',
        )
        assert book.isbn == "0385350597"
        assert book.isbn13 == "9780385350594"

    def test_isbn_cleaning_normal_format(self):
        """Test that normal ISBNs are preserved."""
        book = BookCreate(
            title="Test",
            author="Author",
            isbn="0385350597",
        )
        assert book.isbn == "0385350597"

    def test_isbn_cleaning_empty(self):
        """Test that empty ISBNs become None."""
        book = BookCreate(
            title="Test",
            author="Author",
            isbn="",
        )
        assert book.isbn is None

    def test_rating_normalization_calibre_scale(self):
        """Test that Calibre 0-10 ratings are normalized to 1-5."""
        # Calibre rating 8 should become 4
        book = BookCreate(title="Test", author="Author", rating=8)
        assert book.rating == 4

        # Calibre rating 10 should become 5
        book = BookCreate(title="Test", author="Author", rating=10)
        assert book.rating == 5

        # Zero should become None
        book = BookCreate(title="Test", author="Author", rating=0)
        assert book.rating is None


class TestBookUpdate:
    """Tests for BookUpdate schema."""

    def test_all_fields_optional(self):
        """Test that all fields are optional for updates."""
        update = BookUpdate()
        assert update.title is None
        assert update.author is None
        assert update.status is None

    def test_partial_update(self):
        """Test partial update with some fields."""
        update = BookUpdate(status=BookStatus.COMPLETED, rating=5)
        assert update.status == BookStatus.COMPLETED
        assert update.rating == 5
        assert update.title is None


class TestReadingLogCreate:
    """Tests for ReadingLogCreate schema."""

    def test_create_minimal_log(self):
        """Test creating a log with only required fields."""
        from uuid import uuid4

        book_id = uuid4()
        log = ReadingLogCreate(book_id=book_id, date=date.today())
        assert log.book_id == book_id
        assert log.date == date.today()
        assert log.pages_read is None

    def test_create_full_log(self):
        """Test creating a log with all fields."""
        from uuid import uuid4

        book_id = uuid4()
        log = ReadingLogCreate(
            book_id=book_id,
            date=date(2025, 1, 15),
            pages_read=50,
            start_page=100,
            end_page=150,
            duration_minutes=60,
            location="home",
            notes="Great chapter!",
        )
        assert log.pages_read == 50
        assert log.location == "home"

    def test_negative_pages_rejected(self):
        """Test that negative page counts are rejected."""
        from uuid import uuid4

        with pytest.raises(ValidationError):
            ReadingLogCreate(
                book_id=uuid4(),
                date=date.today(),
                pages_read=-5,
            )


class TestBookStatus:
    """Tests for BookStatus enum."""

    def test_all_statuses_defined(self):
        """Test that all expected statuses are defined."""
        statuses = [s.value for s in BookStatus]
        assert "reading" in statuses
        assert "completed" in statuses
        assert "wishlist" in statuses
        assert "on_hold" in statuses
        assert "dnf" in statuses
        assert "skimmed" in statuses
        assert "owned" in statuses
