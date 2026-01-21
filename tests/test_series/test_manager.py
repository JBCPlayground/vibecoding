"""Tests for SeriesManager."""

import pytest
from uuid import UUID, uuid4

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus
from vibecoding.booktracker.series.manager import SeriesManager
from vibecoding.booktracker.series.schemas import (
    SeriesCreate,
    SeriesUpdate,
    SeriesBookCreate,
    SeriesBookUpdate,
    SeriesStatus,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a SeriesManager with test database."""
    return SeriesManager(db)


@pytest.fixture
def sample_books(db):
    """Create sample books for testing."""
    books = []
    for i in range(5):
        book = db.create_book(BookCreate(
            title=f"Book {i + 1}",
            author="Test Author",
            status=BookStatus.WISHLIST,
        ))
        books.append(book)
    return books


class TestSeriesCRUD:
    """Tests for series CRUD operations."""

    def test_create_series(self, manager):
        """Test creating a series."""
        series = SeriesCreate(
            name="The Lord of the Rings",
            author="J.R.R. Tolkien",
            total_books=3,
            is_complete=True,
        )
        result = manager.create_series(series)

        assert result is not None
        assert result.name == "The Lord of the Rings"
        assert result.author == "J.R.R. Tolkien"
        assert result.total_books == 3
        assert result.is_complete is True
        assert result.status == SeriesStatus.NOT_STARTED

    def test_create_series_minimal(self, manager):
        """Test creating series with only name."""
        series = SeriesCreate(name="Unknown Series")
        result = manager.create_series(series)

        assert result is not None
        assert result.name == "Unknown Series"
        assert result.author is None
        assert result.total_books is None

    def test_get_series(self, manager):
        """Test getting a series by ID."""
        series = SeriesCreate(name="Test Series")
        created = manager.create_series(series)

        result = manager.get_series(created.id)

        assert result is not None
        assert result.id == created.id
        assert result.name == "Test Series"

    def test_get_series_not_found(self, manager):
        """Test getting non-existent series."""
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        result = manager.get_series(fake_id)

        assert result is None

    def test_update_series(self, manager):
        """Test updating a series."""
        series = SeriesCreate(name="Original Name")
        created = manager.create_series(series)

        update = SeriesUpdate(
            name="Updated Name",
            author="New Author",
            total_books=5,
        )
        result = manager.update_series(created.id, update)

        assert result is not None
        assert result.name == "Updated Name"
        assert result.author == "New Author"
        assert result.total_books == 5

    def test_update_series_partial(self, manager):
        """Test partial update of a series."""
        series = SeriesCreate(
            name="Test Series",
            author="Test Author",
            total_books=3,
        )
        created = manager.create_series(series)

        update = SeriesUpdate(total_books=5)
        result = manager.update_series(created.id, update)

        assert result.name == "Test Series"  # Unchanged
        assert result.author == "Test Author"  # Unchanged
        assert result.total_books == 5  # Changed

    def test_update_series_status(self, manager):
        """Test updating series status."""
        series = SeriesCreate(name="Test Series")
        created = manager.create_series(series)

        update = SeriesUpdate(status=SeriesStatus.IN_PROGRESS)
        result = manager.update_series(created.id, update)

        assert result.status == SeriesStatus.IN_PROGRESS
        assert result.status_display == "In Progress"

    def test_delete_series(self, manager):
        """Test deleting a series."""
        series = SeriesCreate(name="To Delete")
        created = manager.create_series(series)

        success = manager.delete_series(created.id)
        assert success is True

        result = manager.get_series(created.id)
        assert result is None

    def test_delete_series_not_found(self, manager):
        """Test deleting non-existent series."""
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        success = manager.delete_series(fake_id)

        assert success is False


class TestSeriesListing:
    """Tests for listing series."""

    def test_list_series_empty(self, manager):
        """Test listing empty series."""
        series_list = manager.list_series()
        assert series_list == []

    def test_list_series_ordered_by_name(self, manager):
        """Test series are ordered by name."""
        manager.create_series(SeriesCreate(name="Zebra Series"))
        manager.create_series(SeriesCreate(name="Alpha Series"))
        manager.create_series(SeriesCreate(name="Middle Series"))

        series_list = manager.list_series()

        assert len(series_list) == 3
        assert series_list[0].name == "Alpha Series"
        assert series_list[1].name == "Middle Series"
        assert series_list[2].name == "Zebra Series"

    def test_list_series_filter_by_status(self, manager):
        """Test filtering by status."""
        manager.create_series(SeriesCreate(
            name="Series 1", status=SeriesStatus.IN_PROGRESS
        ))
        manager.create_series(SeriesCreate(
            name="Series 2", status=SeriesStatus.COMPLETED
        ))
        manager.create_series(SeriesCreate(
            name="Series 3", status=SeriesStatus.IN_PROGRESS
        ))

        result = manager.list_series(status=SeriesStatus.IN_PROGRESS)

        assert len(result) == 2

    def test_list_series_filter_by_author(self, manager):
        """Test filtering by author."""
        manager.create_series(SeriesCreate(name="Series 1", author="Brandon Sanderson"))
        manager.create_series(SeriesCreate(name="Series 2", author="Stephen King"))
        manager.create_series(SeriesCreate(name="Series 3", author="Brandon Sanderson"))

        result = manager.list_series(author="Sanderson")

        assert len(result) == 2

    def test_list_series_search(self, manager):
        """Test search functionality."""
        manager.create_series(SeriesCreate(name="Harry Potter"))
        manager.create_series(SeriesCreate(name="The Witcher"))
        manager.create_series(SeriesCreate(name="Wheel of Time"))

        result = manager.list_series(search="Witch")

        assert len(result) == 1
        assert result[0].name == "The Witcher"

    def test_list_series_filter_by_complete(self, manager):
        """Test filtering by completion status."""
        manager.create_series(SeriesCreate(name="Finished", is_complete=True))
        manager.create_series(SeriesCreate(name="Ongoing", is_complete=False))

        result = manager.list_series(is_complete=True)

        assert len(result) == 1
        assert result[0].name == "Finished"


class TestSeriesBooks:
    """Tests for series book operations."""

    def test_add_book_to_series(self, manager, sample_books):
        """Test adding a book to a series."""
        series = manager.create_series(SeriesCreate(name="Test Series"))
        book = sample_books[0]

        entry = SeriesBookCreate(
            book_id=UUID(book.id),
            position=1,
        )
        result = manager.add_book_to_series(series.id, entry)

        assert result is not None
        assert result.book_id == UUID(book.id)
        assert result.position == 1
        assert result.position_display == "Book 1"

    def test_add_book_with_position_label(self, manager, sample_books):
        """Test adding book with custom position label."""
        series = manager.create_series(SeriesCreate(name="Test Series"))
        book = sample_books[0]

        entry = SeriesBookCreate(
            book_id=UUID(book.id),
            position=0.5,
            position_label="Prequel",
        )
        result = manager.add_book_to_series(series.id, entry)

        assert result.position == 0.5
        assert result.position_display == "Prequel"

    def test_add_book_optional(self, manager, sample_books):
        """Test adding an optional book."""
        series = manager.create_series(SeriesCreate(name="Test Series"))
        book = sample_books[0]

        entry = SeriesBookCreate(
            book_id=UUID(book.id),
            position=1.5,
            is_optional=True,
        )
        result = manager.add_book_to_series(series.id, entry)

        assert result.is_optional is True

    def test_add_book_already_read(self, manager, sample_books):
        """Test adding a book marked as already read."""
        series = manager.create_series(SeriesCreate(name="Test Series"))
        book = sample_books[0]

        entry = SeriesBookCreate(
            book_id=UUID(book.id),
            position=1,
            is_read=True,
            is_owned=True,
        )
        result = manager.add_book_to_series(series.id, entry)

        assert result.is_read is True
        assert result.is_owned is True

    def test_add_book_updates_series_counts(self, manager, sample_books):
        """Test that adding books updates series counts."""
        series = manager.create_series(SeriesCreate(name="Test Series", total_books=3))

        for i, book in enumerate(sample_books[:3]):
            entry = SeriesBookCreate(
                book_id=UUID(book.id),
                position=i + 1,
                is_owned=True,
                is_read=(i < 2),  # First 2 are read
            )
            manager.add_book_to_series(series.id, entry)

        result = manager.get_series(series.id)

        assert result.books_owned == 3
        assert result.books_read == 2
        assert result.completion_percentage == pytest.approx(66.67, rel=0.1)

    def test_get_series_books(self, manager, sample_books):
        """Test getting all books in a series."""
        series = manager.create_series(SeriesCreate(name="Test Series"))

        for i, book in enumerate(sample_books[:3]):
            entry = SeriesBookCreate(
                book_id=UUID(book.id),
                position=i + 1,
            )
            manager.add_book_to_series(series.id, entry)

        books = manager.get_series_books(series.id)

        assert len(books) == 3
        assert books[0].position == 1
        assert books[1].position == 2
        assert books[2].position == 3

    def test_get_series_books_excludes_optional(self, manager, sample_books):
        """Test excluding optional books."""
        series = manager.create_series(SeriesCreate(name="Test Series"))

        # Add main book and optional book
        manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[0].id),
            position=1,
        ))
        manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[1].id),
            position=1.5,
            is_optional=True,
        ))

        books = manager.get_series_books(series.id, include_optional=False)

        assert len(books) == 1

    def test_update_series_book(self, manager, sample_books):
        """Test updating a series book entry."""
        series = manager.create_series(SeriesCreate(name="Test Series"))
        entry = manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[0].id),
            position=1,
        ))

        update = SeriesBookUpdate(
            is_read=True,
            notes="Great book!",
        )
        result = manager.update_series_book(entry.id, update)

        assert result.is_read is True
        assert result.notes == "Great book!"

    def test_remove_book_from_series(self, manager, sample_books):
        """Test removing a book from a series."""
        series = manager.create_series(SeriesCreate(name="Test Series"))
        entry = manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[0].id),
            position=1,
        ))

        success = manager.remove_book_from_series(entry.id)
        assert success is True

        books = manager.get_series_books(series.id)
        assert len(books) == 0


class TestMarkBookRead:
    """Tests for marking books as read."""

    def test_mark_book_read(self, manager, sample_books):
        """Test marking a book as read."""
        series = manager.create_series(SeriesCreate(name="Test Series"))
        book = sample_books[0]

        manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(book.id),
            position=1,
        ))

        result = manager.mark_book_read(series.id, UUID(book.id), is_read=True)

        assert result is not None
        assert result.is_read is True

    def test_mark_book_unread(self, manager, sample_books):
        """Test marking a book as unread."""
        series = manager.create_series(SeriesCreate(name="Test Series"))
        book = sample_books[0]

        manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(book.id),
            position=1,
            is_read=True,
        ))

        result = manager.mark_book_read(series.id, UUID(book.id), is_read=False)

        assert result.is_read is False

    def test_mark_read_updates_series_status(self, manager, sample_books):
        """Test that marking read updates series status."""
        series = manager.create_series(SeriesCreate(
            name="Test Series",
            total_books=2,
            is_complete=True,
        ))

        for i in range(2):
            manager.add_book_to_series(series.id, SeriesBookCreate(
                book_id=UUID(sample_books[i].id),
                position=i + 1,
            ))

        # Read first book
        manager.mark_book_read(series.id, UUID(sample_books[0].id), is_read=True)
        result = manager.get_series(series.id)
        assert result.status == SeriesStatus.IN_PROGRESS

        # Read second book - series should be completed
        manager.mark_book_read(series.id, UUID(sample_books[1].id), is_read=True)
        result = manager.get_series(series.id)
        assert result.status == SeriesStatus.COMPLETED


class TestSeriesWithBooks:
    """Tests for series with books."""

    def test_get_series_with_books(self, manager, sample_books):
        """Test getting series with all books."""
        series = manager.create_series(SeriesCreate(name="Test Series", total_books=3))

        for i in range(3):
            manager.add_book_to_series(series.id, SeriesBookCreate(
                book_id=UUID(sample_books[i].id),
                position=i + 1,
                is_read=(i == 0),  # Only first is read
            ))

        result = manager.get_series_with_books(series.id)

        assert result is not None
        assert result.series.name == "Test Series"
        assert len(result.books) == 3
        assert result.next_to_read is not None
        assert result.next_to_read.position == 2  # Second book is next

    def test_get_series_with_books_all_read(self, manager, sample_books):
        """Test series with all books read has no next."""
        series = manager.create_series(SeriesCreate(name="Test Series"))

        for i in range(2):
            manager.add_book_to_series(series.id, SeriesBookCreate(
                book_id=UUID(sample_books[i].id),
                position=i + 1,
                is_read=True,
            ))

        result = manager.get_series_with_books(series.id)

        assert result.next_to_read is None

    def test_get_series_with_books_skips_optional(self, manager, sample_books):
        """Test next to read skips optional books."""
        series = manager.create_series(SeriesCreate(name="Test Series"))

        # Book 1 (read)
        manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[0].id),
            position=1,
            is_read=True,
        ))
        # Book 1.5 (optional, unread)
        manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[1].id),
            position=1.5,
            is_optional=True,
        ))
        # Book 2 (unread)
        manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[2].id),
            position=2,
        ))

        result = manager.get_series_with_books(series.id)

        # Should recommend Book 2, not the optional Book 1.5
        assert result.next_to_read.position == 2


class TestNextInSeries:
    """Tests for next in series recommendations."""

    def test_get_next_in_series_empty(self, manager):
        """Test recommendations with no in-progress series."""
        result = manager.get_next_in_series()
        assert result == []

    def test_get_next_in_series(self, manager, sample_books):
        """Test getting next book recommendations."""
        series = manager.create_series(SeriesCreate(
            name="Test Series",
            status=SeriesStatus.IN_PROGRESS,
        ))

        manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[0].id),
            position=1,
            is_read=True,
        ))
        manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[1].id),
            position=2,
        ))

        result = manager.get_next_in_series()

        assert len(result) == 1
        assert result[0].series_name == "Test Series"
        assert result[0].book_entry.position == 2


class TestFindSeriesForBook:
    """Tests for finding series a book belongs to."""

    def test_find_series_for_book(self, manager, sample_books):
        """Test finding series for a book."""
        series1 = manager.create_series(SeriesCreate(name="Series 1"))
        series2 = manager.create_series(SeriesCreate(name="Series 2"))

        book = sample_books[0]

        # Add book to both series
        manager.add_book_to_series(series1.id, SeriesBookCreate(
            book_id=UUID(book.id),
            position=1,
        ))
        manager.add_book_to_series(series2.id, SeriesBookCreate(
            book_id=UUID(book.id),
            position=5,
        ))

        result = manager.find_series_for_book(UUID(book.id))

        assert len(result) == 2

    def test_find_series_for_book_none(self, manager, sample_books):
        """Test finding series for book not in any series."""
        book = sample_books[0]
        result = manager.find_series_for_book(UUID(book.id))

        assert result == []


class TestSeriesStats:
    """Tests for series statistics."""

    def test_stats_empty(self, manager):
        """Test stats with no series."""
        stats = manager.get_stats()

        assert stats.total_series == 0
        assert stats.by_status == {}
        assert stats.completed_series == 0

    def test_stats_with_data(self, manager, sample_books):
        """Test stats with series data."""
        # Create series with different statuses
        s1 = manager.create_series(SeriesCreate(
            name="Completed Series",
            total_books=2,
            status=SeriesStatus.COMPLETED,
        ))
        s2 = manager.create_series(SeriesCreate(
            name="In Progress Series",
            total_books=3,
            status=SeriesStatus.IN_PROGRESS,
        ))

        # Add some books
        for i in range(2):
            manager.add_book_to_series(s1.id, SeriesBookCreate(
                book_id=UUID(sample_books[i].id),
                position=i + 1,
                is_read=True,
            ))

        manager.add_book_to_series(s2.id, SeriesBookCreate(
            book_id=UUID(sample_books[2].id),
            position=1,
            is_read=True,
        ))

        stats = manager.get_stats()

        assert stats.total_series == 2
        assert stats.completed_series == 1
        assert stats.in_progress_series == 1
        assert stats.total_series_books == 3
        assert stats.series_books_read == 3


class TestModelProperties:
    """Tests for model properties."""

    def test_completion_percentage_with_total(self, manager, sample_books):
        """Test completion percentage with known total."""
        series = manager.create_series(SeriesCreate(
            name="Test",
            total_books=4,
        ))

        for i in range(2):
            manager.add_book_to_series(series.id, SeriesBookCreate(
                book_id=UUID(sample_books[i].id),
                position=i + 1,
                is_read=True,
            ))

        result = manager.get_series(series.id)

        assert result.completion_percentage == 50.0

    def test_completion_percentage_without_total(self, manager, sample_books):
        """Test completion percentage based on owned books."""
        series = manager.create_series(SeriesCreate(name="Test"))

        for i in range(4):
            manager.add_book_to_series(series.id, SeriesBookCreate(
                book_id=UUID(sample_books[i].id),
                position=i + 1,
                is_owned=True,
                is_read=(i < 2),  # 2 of 4 read
            ))

        result = manager.get_series(series.id)

        assert result.completion_percentage == 50.0

    def test_books_remaining(self, manager, sample_books):
        """Test books remaining calculation."""
        series = manager.create_series(SeriesCreate(
            name="Test",
            total_books=5,
        ))

        for i in range(2):
            manager.add_book_to_series(series.id, SeriesBookCreate(
                book_id=UUID(sample_books[i].id),
                position=i + 1,
                is_read=True,
            ))

        result = manager.get_series(series.id)

        assert result.books_remaining == 3

    def test_status_display(self, manager):
        """Test status display strings."""
        statuses = [
            (SeriesStatus.NOT_STARTED, "Not Started"),
            (SeriesStatus.IN_PROGRESS, "In Progress"),
            (SeriesStatus.COMPLETED, "Completed"),
            (SeriesStatus.ON_HOLD, "On Hold"),
            (SeriesStatus.ABANDONED, "Abandoned"),
        ]

        for status, expected_display in statuses:
            series = manager.create_series(SeriesCreate(
                name=f"Test {status.value}",
                status=status,
            ))
            assert series.status_display == expected_display

    def test_position_display_integer(self, manager, sample_books):
        """Test position display for whole numbers."""
        series = manager.create_series(SeriesCreate(name="Test"))
        entry = manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[0].id),
            position=1,
        ))

        assert entry.position_display == "Book 1"

    def test_position_display_decimal(self, manager, sample_books):
        """Test position display for decimals (novellas)."""
        series = manager.create_series(SeriesCreate(name="Test"))
        entry = manager.add_book_to_series(series.id, SeriesBookCreate(
            book_id=UUID(sample_books[0].id),
            position=1.5,
        ))

        assert entry.position_display == "Book 1.5"
