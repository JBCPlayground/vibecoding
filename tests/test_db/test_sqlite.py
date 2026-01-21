"""Tests for SQLite database operations."""

from datetime import date
from uuid import UUID

import pytest

from src.vibecoding.booktracker.db.models import Book, ReadingLog, SyncQueueItem
from src.vibecoding.booktracker.db.schemas import (
    BookCreate,
    BookStatus,
    BookUpdate,
    ReadingLogCreate,
    SyncStatus,
)
from src.vibecoding.booktracker.db.sqlite import Database


class TestDatabaseCreation:
    """Tests for database initialization."""

    def test_database_creates_tables(self, db: Database):
        """Test that database creates all required tables."""
        # Tables should exist after initialization
        with db.get_session() as session:
            # These queries should not raise
            session.query(Book).first()
            session.query(ReadingLog).first()
            session.query(SyncQueueItem).first()

    def test_database_path_created(self, db: Database):
        """Test that database file is created."""
        assert db.db_path.exists()


class TestBookCRUD:
    """Tests for Book CRUD operations."""

    def test_create_book(self, db: Database, sample_book_data: BookCreate):
        """Test creating a book."""
        book = db.create_book(sample_book_data)

        assert book.id is not None
        assert book.title == "The Great Gatsby"
        assert book.author == "F. Scott Fitzgerald"
        assert book.status == BookStatus.COMPLETED.value
        assert book.rating == 5

    def test_create_book_generates_uuid(self, db: Database, sample_book_minimal: BookCreate):
        """Test that creating a book generates a valid UUID."""
        book = db.create_book(sample_book_minimal)

        # Should be a valid UUID string
        uuid = UUID(book.id)
        assert str(uuid) == book.id

    def test_create_book_adds_to_sync_queue(self, db: Database, sample_book_data: BookCreate):
        """Test that creating a book adds it to sync queue."""
        book = db.create_book(sample_book_data)

        pending = db.get_pending_sync_items()
        assert len(pending) == 1
        assert pending[0].entity_type == "book"
        assert pending[0].entity_id == book.id
        assert pending[0].operation == "create"

    def test_get_book_by_id(self, db: Database, created_book: Book):
        """Test retrieving a book by ID."""
        book = db.get_book(created_book.id)

        assert book is not None
        assert book.id == created_book.id
        assert book.title == created_book.title

    def test_get_nonexistent_book(self, db: Database):
        """Test that getting a nonexistent book returns None."""
        book = db.get_book("nonexistent-id")
        assert book is None

    def test_get_book_by_isbn(self, db: Database, sample_book_data: BookCreate):
        """Test retrieving a book by ISBN."""
        created = db.create_book(sample_book_data)
        book = db.get_book_by_isbn(sample_book_data.isbn)

        assert book is not None
        assert book.id == created.id

    def test_get_book_by_isbn13(self, db: Database, sample_book_data: BookCreate):
        """Test retrieving a book by ISBN-13."""
        created = db.create_book(sample_book_data)
        book = db.get_book_by_isbn(sample_book_data.isbn13)

        assert book is not None
        assert book.id == created.id

    def test_get_books_by_status(self, db: Database, multiple_books: list[Book]):
        """Test filtering books by status."""
        completed = db.get_books_by_status(BookStatus.COMPLETED.value)
        assert len(completed) == 2

        reading = db.get_books_by_status(BookStatus.READING.value)
        assert len(reading) == 1

        wishlist = db.get_books_by_status(BookStatus.WISHLIST.value)
        assert len(wishlist) == 1

    def test_search_books_by_title(self, db: Database, multiple_books: list[Book]):
        """Test searching books by title."""
        results = db.search_books("Book")
        assert len(results) == 4  # All have "Book" in title

        results = db.search_books("One")
        assert len(results) == 1
        assert results[0].title == "Book One"

    def test_search_books_by_author(self, db: Database, multiple_books: list[Book]):
        """Test searching books by author."""
        results = db.search_books("Author A")
        assert len(results) == 2

    def test_search_books_case_insensitive(self, db: Database, multiple_books: list[Book]):
        """Test that search is case insensitive."""
        results = db.search_books("book")
        assert len(results) == 4

        results = db.search_books("AUTHOR")
        assert len(results) == 4

    def test_get_all_books(self, db: Database, multiple_books: list[Book]):
        """Test getting all books."""
        books = db.get_all_books()
        assert len(books) == 4

    def test_update_book(self, db: Database, created_book: Book):
        """Test updating a book."""
        update = BookUpdate(rating=3, status=BookStatus.READING)
        updated = db.update_book(created_book.id, update)

        assert updated is not None
        assert updated.rating == 3
        assert updated.status == BookStatus.READING.value

    def test_update_book_adds_to_sync_queue(self, db: Database, created_book: Book):
        """Test that updating a book adds to sync queue."""
        # Clear the create operation from queue
        db.mark_sync_item_completed(db.get_pending_sync_items()[0].id)

        update = BookUpdate(rating=3)
        db.update_book(created_book.id, update)

        pending = db.get_pending_sync_items()
        assert len(pending) == 1
        assert pending[0].operation == "update"

    def test_update_nonexistent_book(self, db: Database):
        """Test that updating a nonexistent book returns None."""
        update = BookUpdate(rating=3)
        result = db.update_book("nonexistent-id", update)
        assert result is None

    def test_delete_book(self, db: Database, created_book: Book):
        """Test deleting a book."""
        # First sync the book so it has a notion_page_id
        with db.get_session() as session:
            book = session.get(Book, created_book.id)
            book.notion_page_id = "test-notion-id"

        result = db.delete_book(created_book.id)
        assert result is True

        # Book should be gone
        book = db.get_book(created_book.id)
        assert book is None

    def test_delete_nonexistent_book(self, db: Database):
        """Test that deleting a nonexistent book returns False."""
        result = db.delete_book("nonexistent-id")
        assert result is False


class TestReadingLogCRUD:
    """Tests for ReadingLog CRUD operations."""

    def test_create_reading_log(self, db: Database, created_book: Book):
        """Test creating a reading log."""
        log_data = ReadingLogCreate(
            book_id=UUID(created_book.id),
            date=date.today(),
            pages_read=50,
            location="home",
        )
        log = db.create_reading_log(log_data)

        assert log.id is not None
        assert log.book_id == created_book.id
        assert log.pages_read == 50
        assert log.location == "home"

    def test_create_reading_log_adds_to_sync_queue(self, db: Database, created_book: Book):
        """Test that creating a reading log adds to sync queue."""
        # Clear existing queue items
        for item in db.get_pending_sync_items():
            db.mark_sync_item_completed(item.id)

        log_data = ReadingLogCreate(
            book_id=UUID(created_book.id),
            date=date.today(),
        )
        log = db.create_reading_log(log_data)

        pending = db.get_pending_sync_items()
        assert len(pending) == 1
        assert pending[0].entity_type == "reading_log"
        assert pending[0].entity_id == log.id

    def test_get_reading_logs_for_book(self, db: Database, created_book: Book):
        """Test getting reading logs for a book."""
        # Create multiple logs
        for i in range(3):
            log_data = ReadingLogCreate(
                book_id=UUID(created_book.id),
                date=date(2025, 1, i + 1),
                pages_read=50 * (i + 1),
            )
            db.create_reading_log(log_data)

        logs = db.get_reading_logs_for_book(created_book.id)
        assert len(logs) == 3

        # Should be ordered by date descending
        assert logs[0].date == "2025-01-03"
        assert logs[2].date == "2025-01-01"


class TestSyncQueue:
    """Tests for sync queue operations."""

    def test_pending_items_count(self, db: Database, multiple_books: list[Book]):
        """Test counting pending sync items."""
        count = db.count_pending_sync_items()
        assert count == 4  # One for each book created

    def test_mark_item_completed(self, db: Database, created_book: Book):
        """Test marking a sync item as completed."""
        pending = db.get_pending_sync_items()
        assert len(pending) == 1

        db.mark_sync_item_completed(pending[0].id)

        pending = db.get_pending_sync_items()
        assert len(pending) == 0

    def test_mark_item_failed(self, db: Database, created_book: Book):
        """Test marking a sync item as failed."""
        pending = db.get_pending_sync_items()
        item_id = pending[0].id

        db.mark_sync_item_failed(item_id, "Connection error")

        # Item should no longer be pending
        pending = db.get_pending_sync_items()
        assert len(pending) == 0

        # But it should exist with failed status
        with db.get_session() as session:
            item = session.get(SyncQueueItem, item_id)
            assert item.status == SyncStatus.FAILED.value
            assert item.last_error == "Connection error"
            assert item.retry_count == 1

    def test_duplicate_operations_merged(self, db: Database, created_book: Book):
        """Test that duplicate operations for same entity are merged."""
        # Update the book multiple times
        db.update_book(created_book.id, BookUpdate(rating=3))
        db.update_book(created_book.id, BookUpdate(rating=4))
        db.update_book(created_book.id, BookUpdate(rating=5))

        # Should only have one pending item (original create, updated to latest)
        pending = db.get_pending_sync_items()
        assert len(pending) == 1


class TestJSONFields:
    """Tests for JSON field serialization."""

    def test_tags_serialization(self, db: Database, sample_book_data: BookCreate):
        """Test that tags are properly serialized and deserialized."""
        book = db.create_book(sample_book_data)

        # Retrieve and check
        retrieved = db.get_book(book.id)
        tags = retrieved.get_tags()
        assert "american-literature" in tags
        assert "jazz-age" in tags

    def test_sources_serialization(self, db: Database, sample_book_data: BookCreate):
        """Test that sources are properly serialized and deserialized."""
        book = db.create_book(sample_book_data)

        retrieved = db.get_book(book.id)
        sources = retrieved.get_sources()
        assert "manual" in sources

    def test_identifiers_serialization(self, db: Database, sample_calibre_book: BookCreate):
        """Test that identifiers dict is properly serialized."""
        book = db.create_book(sample_calibre_book)

        retrieved = db.get_book(book.id)
        identifiers = retrieved.get_identifiers()
        assert identifiers["goodreads"] == "234225"
        assert identifiers["mobi-asin"] == "B00B7NPRY8"
