"""SQLite database operations.

Handles database connection, session management, and CRUD operations.
"""

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base, Book, ReadingLog, SyncQueueItem
from .schemas import (
    BookCreate,
    BookResponse,
    BookUpdate,
    ReadingLogCreate,
    ReadingLogResponse,
    SyncOperation,
    SyncQueueItemCreate,
    SyncQueueItemResponse,
    SyncStatus,
)


class Database:
    """Database connection and operations manager."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. If None, uses
                     BOOKTRACKER_DB_PATH env var or default location.
        """
        if db_path is None:
            db_path = os.environ.get(
                "BOOKTRACKER_DB_PATH",
                str(Path.home() / "OneDrive" / "booktracker" / "books.db"),
            )

        self.db_path = Path(db_path)
        self._is_memory = str(db_path) == ":memory:"

        if not self._is_memory:
            self._ensure_directory()

        # For in-memory databases, use StaticPool to reuse the same connection
        # This ensures all sessions share the same in-memory database
        if self._is_memory:
            self.engine = create_engine(
                "sqlite:///:memory:",
                echo=False,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            self.engine = create_engine(
                f"sqlite:///{self.db_path}",
                echo=False,
                connect_args={"check_same_thread": False},
            )
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

    def _ensure_directory(self) -> None:
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def create_tables(self) -> None:
        """Create all database tables."""
        # Import collection models to register them with Base
        from ..collections.models import Collection, CollectionBook  # noqa: F401
        # Import challenge models to register them with Base
        from ..challenges.models import Challenge, ChallengeBook  # noqa: F401
        # Import lending models to register them with Base
        from ..lending.models import Loan, Contact  # noqa: F401
        # Import review models to register them with Base
        from ..reviews.models import Review  # noqa: F401
        # Import notes models to register them with Base
        from ..notes.models import Note, Quote, QuoteCollection, CollectionQuote  # noqa: F401
        # Import streak models to register them with Base
        from ..streaks.models import ReadingStreak, DailyReading  # noqa: F401
        # Import wishlist models to register them with Base
        from ..wishlist.models import WishlistItem  # noqa: F401
        # Import series models to register them with Base
        from ..series.models import Series, SeriesBook  # noqa: F401
        # Import lists models to register them with Base
        from ..lists.models import ReadingList, ReadingListBook  # noqa: F401
        # Import schedule models to register them with Base
        from ..schedule.models import ReadingPlan, PlannedBook, ScheduleEntry, Reminder  # noqa: F401
        # Import tags models to register them with Base
        from ..tags.models import Tag, BookTag, CustomField, CustomFieldValue  # noqa: F401
        # Import locations models to register them with Base
        from ..locations.models import ReadingLocation, LocationSession  # noqa: F401
        # Import settings models to register them with Base
        from ..settings.models import Setting, SettingsBackup  # noqa: F401

        Base.metadata.create_all(self.engine)

    def drop_tables(self) -> None:
        """Drop all database tables. Use with caution!"""
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session context manager."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ========================================================================
    # Book Operations
    # ========================================================================

    def create_book(self, book: BookCreate, session: Optional[Session] = None) -> Book:
        """Create a new book record."""

        def _create(s: Session) -> Book:
            db_book = Book(
                title=book.title,
                title_sort=book.title_sort,
                author=book.author,
                author_sort=book.author_sort,
                status=book.status.value,
                rating=book.rating,
                date_added=book.date_added.isoformat() if book.date_added else None,
                date_started=book.date_started.isoformat() if book.date_started else None,
                date_finished=book.date_finished.isoformat() if book.date_finished else None,
                isbn=book.isbn,
                isbn13=book.isbn13,
                page_count=book.page_count,
                description=book.description,
                cover=book.cover,
                cover_base64=book.cover_base64,
                publisher=book.publisher,
                series=book.series,
                series_index=book.series_index,
                publication_date=(
                    book.publication_date.isoformat() if book.publication_date else None
                ),
                publication_year=book.publication_year,
                original_publication_year=book.original_publication_year,
                language=book.language,
                format=book.format,
                file_size=book.file_size,
                library_source=book.library_source,
                amazon_url=book.amazon_url,
                goodreads_url=book.goodreads_url,
                library_url=book.library_url,
                comments=book.comments,
                progress=book.progress,
                read_next=book.read_next,
                recommended_by=book.recommended_by,
                goodreads_id=book.goodreads_id,
                additional_authors=book.additional_authors,
                goodreads_avg_rating=book.goodreads_avg_rating,
                goodreads_shelves=book.goodreads_shelves,
                goodreads_shelf_positions=book.goodreads_shelf_positions,
                review=book.review,
                review_spoiler=book.review_spoiler,
                notes=book.notes,
                read_count=book.read_count,
                owned_copies=book.owned_copies,
                calibre_id=book.calibre_id,
                calibre_uuid=book.calibre_uuid,
                calibre_library=book.calibre_library,
                custom_text=book.custom_text,
                library_hold_date=(
                    book.library_hold_date.isoformat() if book.library_hold_date else None
                ),
                library_due_date=(
                    book.library_due_date.isoformat() if book.library_due_date else None
                ),
                pickup_location=book.pickup_location,
                renewals=book.renewals,
                import_date=datetime.now(timezone.utc).isoformat(),
            )
            # Set JSON fields
            db_book.set_tags(book.tags or [])
            db_book.set_file_formats(book.file_formats or [])
            db_book.set_genres(book.genres or [])
            db_book.set_sources([s.value for s in book.sources])
            db_book.set_source_ids(book.source_ids)
            db_book.set_identifiers(book.identifiers or {})

            s.add(db_book)
            s.flush()

            # Add to sync queue
            self._add_to_sync_queue(s, "book", db_book.id, SyncOperation.CREATE)

            return db_book

        if session:
            return _create(session)
        else:
            with self.get_session() as s:
                book = _create(s)
                s.expunge(book)
                return book

    def get_book(self, book_id: str, session: Optional[Session] = None) -> Optional[Book]:
        """Get a book by ID."""

        def _get(s: Session) -> Optional[Book]:
            return s.get(Book, book_id)

        if session:
            return _get(session)
        else:
            with self.get_session() as s:
                book = _get(s)
                if book:
                    s.expunge(book)
                return book

    def get_book_by_isbn(
        self, isbn: str, session: Optional[Session] = None
    ) -> Optional[Book]:
        """Get a book by ISBN (checks both isbn and isbn13)."""

        def _get(s: Session) -> Optional[Book]:
            stmt = select(Book).where((Book.isbn == isbn) | (Book.isbn13 == isbn))
            return s.execute(stmt).scalar_one_or_none()

        if session:
            return _get(session)
        else:
            with self.get_session() as s:
                book = _get(s)
                if book:
                    s.expunge(book)
                return book

    def get_books_by_status(
        self, status: str, session: Optional[Session] = None
    ) -> list[Book]:
        """Get all books with a given status."""

        def _get(s: Session) -> list[Book]:
            stmt = select(Book).where(Book.status == status).order_by(Book.title)
            return list(s.execute(stmt).scalars().all())

        if session:
            return _get(session)
        else:
            with self.get_session() as s:
                books = _get(s)
                for book in books:
                    s.expunge(book)
                return books

    def search_books(
        self, query: str, limit: int = 20, session: Optional[Session] = None
    ) -> list[Book]:
        """Search books by title or author."""

        def _search(s: Session) -> list[Book]:
            pattern = f"%{query}%"
            stmt = (
                select(Book)
                .where((Book.title.ilike(pattern)) | (Book.author.ilike(pattern)))
                .order_by(Book.title)
                .limit(limit)
            )
            return list(s.execute(stmt).scalars().all())

        if session:
            return _search(session)
        else:
            with self.get_session() as s:
                books = _search(s)
                for book in books:
                    s.expunge(book)
                return books

    def get_all_books(self, session: Optional[Session] = None) -> list[Book]:
        """Get all books."""

        def _get(s: Session) -> list[Book]:
            stmt = select(Book).order_by(Book.title)
            return list(s.execute(stmt).scalars().all())

        if session:
            return _get(session)
        else:
            with self.get_session() as s:
                books = _get(s)
                for book in books:
                    s.expunge(book)
                return books

    def update_book(
        self, book_id: str, update: BookUpdate, session: Optional[Session] = None
    ) -> Optional[Book]:
        """Update a book record."""

        def _update(s: Session) -> Optional[Book]:
            book = s.get(Book, book_id)
            if not book:
                return None

            update_data = update.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if field in ("tags", "file_formats", "genres"):
                    getattr(book, f"set_{field}")(value)
                elif field in ("sources", "source_ids", "identifiers"):
                    getattr(book, f"set_{field}")(value)
                elif field in (
                    "date_added",
                    "date_started",
                    "date_finished",
                    "publication_date",
                    "library_hold_date",
                    "library_due_date",
                ):
                    setattr(book, field, value.isoformat() if value else None)
                elif field == "status" and value:
                    setattr(book, field, value.value)
                else:
                    setattr(book, field, value)

            book.local_modified_at = datetime.now(timezone.utc).isoformat()
            book.updated_at = datetime.now(timezone.utc).isoformat()
            s.flush()

            # Add to sync queue
            self._add_to_sync_queue(s, "book", book.id, SyncOperation.UPDATE)

            return book

        if session:
            return _update(session)
        else:
            with self.get_session() as s:
                book = _update(s)
                if book:
                    s.expunge(book)
                return book

    def delete_book(self, book_id: str, session: Optional[Session] = None) -> bool:
        """Delete a book record."""

        def _delete(s: Session) -> bool:
            book = s.get(Book, book_id)
            if not book:
                return False

            # Add to sync queue before deleting
            if book.notion_page_id:
                self._add_to_sync_queue(s, "book", book.id, SyncOperation.DELETE)

            s.delete(book)
            return True

        if session:
            return _delete(session)
        else:
            with self.get_session() as s:
                return _delete(s)

    # ========================================================================
    # Reading Log Operations
    # ========================================================================

    def create_reading_log(
        self, log: ReadingLogCreate, session: Optional[Session] = None
    ) -> ReadingLog:
        """Create a new reading log entry."""

        def _create(s: Session) -> ReadingLog:
            db_log = ReadingLog(
                book_id=str(log.book_id),
                date=log.date.isoformat(),
                pages_read=log.pages_read,
                start_page=log.start_page,
                end_page=log.end_page,
                duration_minutes=log.duration_minutes,
                location=log.location,
                notes=log.notes,
            )
            s.add(db_log)
            s.flush()

            # Add to sync queue
            self._add_to_sync_queue(s, "reading_log", db_log.id, SyncOperation.CREATE)

            return db_log

        if session:
            return _create(session)
        else:
            with self.get_session() as s:
                log = _create(s)
                s.expunge(log)
                return log

    def get_reading_logs_for_book(
        self, book_id: str, session: Optional[Session] = None
    ) -> list[ReadingLog]:
        """Get all reading logs for a book."""

        def _get(s: Session) -> list[ReadingLog]:
            stmt = (
                select(ReadingLog)
                .where(ReadingLog.book_id == book_id)
                .order_by(ReadingLog.date.desc())
            )
            return list(s.execute(stmt).scalars().all())

        if session:
            return _get(session)
        else:
            with self.get_session() as s:
                logs = _get(s)
                for log in logs:
                    s.expunge(log)
                return logs

    def get_reading_log(
        self, log_id: str, session: Optional[Session] = None
    ) -> Optional[ReadingLog]:
        """Get a reading log by ID."""

        def _get(s: Session) -> Optional[ReadingLog]:
            return s.get(ReadingLog, log_id)

        if session:
            return _get(session)
        else:
            with self.get_session() as s:
                log = _get(s)
                if log:
                    s.expunge(log)
                return log

    def get_reading_logs_by_date_range(
        self,
        start_date: str,
        end_date: str,
        session: Optional[Session] = None,
    ) -> list[ReadingLog]:
        """Get reading logs within a date range.

        Args:
            start_date: Start date (ISO format YYYY-MM-DD)
            end_date: End date (ISO format YYYY-MM-DD)
        """

        def _get(s: Session) -> list[ReadingLog]:
            stmt = (
                select(ReadingLog)
                .where(
                    ReadingLog.date >= start_date,
                    ReadingLog.date <= end_date,
                )
                .order_by(ReadingLog.date.desc())
            )
            return list(s.execute(stmt).scalars().all())

        if session:
            return _get(session)
        else:
            with self.get_session() as s:
                logs = _get(s)
                for log in logs:
                    s.expunge(log)
                return logs

    def get_all_reading_logs(
        self, limit: int = 100, session: Optional[Session] = None
    ) -> list[ReadingLog]:
        """Get all reading logs, most recent first."""

        def _get(s: Session) -> list[ReadingLog]:
            stmt = select(ReadingLog).order_by(ReadingLog.date.desc()).limit(limit)
            return list(s.execute(stmt).scalars().all())

        if session:
            return _get(session)
        else:
            with self.get_session() as s:
                logs = _get(s)
                for log in logs:
                    s.expunge(log)
                return logs

    def update_reading_log(
        self,
        log_id: str,
        pages_read: Optional[int] = None,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
        duration_minutes: Optional[int] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> Optional[ReadingLog]:
        """Update a reading log entry."""

        def _update(s: Session) -> Optional[ReadingLog]:
            log = s.get(ReadingLog, log_id)
            if not log:
                return None

            if pages_read is not None:
                log.pages_read = pages_read
            if start_page is not None:
                log.start_page = start_page
            if end_page is not None:
                log.end_page = end_page
            if duration_minutes is not None:
                log.duration_minutes = duration_minutes
            if location is not None:
                log.location = location
            if notes is not None:
                log.notes = notes

            s.flush()

            # Add to sync queue
            self._add_to_sync_queue(s, "reading_log", log.id, SyncOperation.UPDATE)

            return log

        if session:
            return _update(session)
        else:
            with self.get_session() as s:
                log = _update(s)
                if log:
                    s.expunge(log)
                return log

    def delete_reading_log(self, log_id: str, session: Optional[Session] = None) -> bool:
        """Delete a reading log entry."""

        def _delete(s: Session) -> bool:
            log = s.get(ReadingLog, log_id)
            if not log:
                return False

            # Add to sync queue before deleting
            if log.notion_page_id:
                self._add_to_sync_queue(s, "reading_log", log.id, SyncOperation.DELETE)

            s.delete(log)
            return True

        if session:
            return _delete(session)
        else:
            with self.get_session() as s:
                return _delete(s)

    def get_reading_stats_for_book(
        self, book_id: str, session: Optional[Session] = None
    ) -> dict:
        """Get aggregated reading stats for a book."""

        def _get(s: Session) -> dict:
            logs = self.get_reading_logs_for_book(book_id, s)

            total_pages = sum(log.pages_read or 0 for log in logs)
            total_minutes = sum(log.duration_minutes or 0 for log in logs)
            session_count = len(logs)

            # Get current page (highest end_page)
            current_page = max((log.end_page or 0 for log in logs), default=0)

            return {
                "total_pages_read": total_pages,
                "total_minutes": total_minutes,
                "session_count": session_count,
                "current_page": current_page,
            }

        if session:
            return _get(session)
        else:
            with self.get_session() as s:
                return _get(s)

    # ========================================================================
    # Sync Queue Operations
    # ========================================================================

    def _add_to_sync_queue(
        self, session: Session, entity_type: str, entity_id: str, operation: SyncOperation
    ) -> SyncQueueItem:
        """Add an item to the sync queue."""
        # Check if there's already a pending item for this entity
        stmt = select(SyncQueueItem).where(
            SyncQueueItem.entity_type == entity_type,
            SyncQueueItem.entity_id == entity_id,
            SyncQueueItem.status == SyncStatus.PENDING.value,
        )
        existing = session.execute(stmt).scalar_one_or_none()

        if existing:
            # Update the existing item's operation if needed
            if operation == SyncOperation.DELETE:
                existing.operation = SyncOperation.DELETE.value
            existing.updated_at = datetime.now(timezone.utc).isoformat()
            return existing

        # Create new queue item
        queue_item = SyncQueueItem(
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation.value,
            status=SyncStatus.PENDING.value,
        )
        session.add(queue_item)
        return queue_item

    def get_pending_sync_items(
        self, session: Optional[Session] = None
    ) -> list[SyncQueueItem]:
        """Get all pending sync queue items."""

        def _get(s: Session) -> list[SyncQueueItem]:
            stmt = (
                select(SyncQueueItem)
                .where(SyncQueueItem.status == SyncStatus.PENDING.value)
                .order_by(SyncQueueItem.created_at)
            )
            return list(s.execute(stmt).scalars().all())

        if session:
            return _get(session)
        else:
            with self.get_session() as s:
                items = _get(s)
                for item in items:
                    s.expunge(item)
                return items

    def count_pending_sync_items(self, session: Optional[Session] = None) -> int:
        """Count pending sync queue items."""

        def _count(s: Session) -> int:
            stmt = select(SyncQueueItem).where(
                SyncQueueItem.status == SyncStatus.PENDING.value
            )
            return len(list(s.execute(stmt).scalars().all()))

        if session:
            return _count(session)
        else:
            with self.get_session() as s:
                return _count(s)

    def mark_sync_item_completed(
        self, item_id: str, session: Optional[Session] = None
    ) -> None:
        """Mark a sync queue item as completed."""

        def _mark(s: Session) -> None:
            item = s.get(SyncQueueItem, item_id)
            if item:
                item.status = SyncStatus.COMPLETED.value
                item.updated_at = datetime.now(timezone.utc).isoformat()

        if session:
            _mark(session)
        else:
            with self.get_session() as s:
                _mark(s)

    def mark_sync_item_failed(
        self, item_id: str, error: str, session: Optional[Session] = None
    ) -> None:
        """Mark a sync queue item as failed."""

        def _mark(s: Session) -> None:
            item = s.get(SyncQueueItem, item_id)
            if item:
                item.status = SyncStatus.FAILED.value
                item.last_error = error
                item.retry_count += 1
                item.updated_at = datetime.now(timezone.utc).isoformat()

        if session:
            _mark(session)
        else:
            with self.get_session() as s:
                _mark(s)


# Global database instance
_db: Optional[Database] = None


def get_db(db_path: Optional[str] = None) -> Database:
    """Get or create the global database instance."""
    global _db
    if _db is None:
        _db = Database(db_path)
        _db.create_tables()
    return _db


def reset_db() -> None:
    """Reset the global database instance. Used for testing."""
    global _db
    _db = None
