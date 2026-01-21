"""Manager for book series operations."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func, asc, desc
from sqlalchemy.orm import Session

from ..db.sqlite import Database
from ..db.models import Book
from .models import Series, SeriesBook
from .schemas import (
    SeriesCreate,
    SeriesUpdate,
    SeriesResponse,
    SeriesSummary,
    SeriesBookCreate,
    SeriesBookUpdate,
    SeriesBookResponse,
    SeriesBookWithDetails,
    SeriesWithBooks,
    SeriesStats,
    NextInSeries,
    SeriesStatus,
)


class SeriesManager:
    """Manager for book series operations."""

    def __init__(self, db: Database):
        """Initialize the series manager.

        Args:
            db: Database instance
        """
        self.db = db

    # ========================================================================
    # Series CRUD
    # ========================================================================

    def create_series(self, series: SeriesCreate) -> SeriesResponse:
        """Create a new series.

        Args:
            series: Series data to create

        Returns:
            Created series response
        """
        with self.db.get_session() as session:
            db_series = Series(
                name=series.name,
                author=series.author,
                description=series.description,
                total_books=series.total_books,
                is_complete=series.is_complete,
                genre=series.genre,
                status=series.status.value,
                goodreads_series_id=series.goodreads_series_id,
                goodreads_url=series.goodreads_url,
                notes=series.notes,
            )

            session.add(db_series)
            session.flush()

            return self._to_series_response(db_series)

    def get_series(self, series_id: UUID) -> Optional[SeriesResponse]:
        """Get a series by ID.

        Args:
            series_id: Series UUID

        Returns:
            Series response or None if not found
        """
        with self.db.get_session() as session:
            series = session.query(Series).filter(
                Series.id == str(series_id)
            ).first()

            if not series:
                return None

            return self._to_series_response(series)

    def update_series(
        self, series_id: UUID, updates: SeriesUpdate
    ) -> Optional[SeriesResponse]:
        """Update a series.

        Args:
            series_id: Series UUID
            updates: Fields to update

        Returns:
            Updated series response or None if not found
        """
        with self.db.get_session() as session:
            series = session.query(Series).filter(
                Series.id == str(series_id)
            ).first()

            if not series:
                return None

            update_data = updates.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if field == "status" and value is not None:
                    setattr(series, field, value.value if hasattr(value, 'value') else value)
                else:
                    setattr(series, field, value)

            session.flush()

            return self._to_series_response(series)

    def delete_series(self, series_id: UUID) -> bool:
        """Delete a series and its book links.

        Args:
            series_id: Series UUID

        Returns:
            True if deleted, False if not found
        """
        with self.db.get_session() as session:
            series = session.query(Series).filter(
                Series.id == str(series_id)
            ).first()

            if not series:
                return False

            # Delete all series book links
            session.query(SeriesBook).filter(
                SeriesBook.series_id == str(series_id)
            ).delete()

            session.delete(series)
            return True

    def list_series(
        self,
        status: Optional[SeriesStatus] = None,
        author: Optional[str] = None,
        search: Optional[str] = None,
        is_complete: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SeriesSummary]:
        """List series with optional filters.

        Args:
            status: Filter by reading status
            author: Filter by author
            search: Search in name
            is_complete: Filter by series completion status
            limit: Max items to return
            offset: Number of items to skip

        Returns:
            List of series summaries
        """
        with self.db.get_session() as session:
            query = session.query(Series)

            if status is not None:
                query = query.filter(Series.status == status.value)

            if author:
                query = query.filter(Series.author.ilike(f"%{author}%"))

            if search:
                query = query.filter(Series.name.ilike(f"%{search}%"))

            if is_complete is not None:
                query = query.filter(Series.is_complete == is_complete)

            query = query.order_by(asc(Series.name))
            series_list = query.offset(offset).limit(limit).all()

            return [self._to_series_summary(s) for s in series_list]

    # ========================================================================
    # Series Book Operations
    # ========================================================================

    def add_book_to_series(
        self, series_id: UUID, book_entry: SeriesBookCreate
    ) -> Optional[SeriesBookResponse]:
        """Add a book to a series.

        Args:
            series_id: Series UUID
            book_entry: Book entry data

        Returns:
            Created series book entry or None if series not found
        """
        with self.db.get_session() as session:
            series = session.query(Series).filter(
                Series.id == str(series_id)
            ).first()

            if not series:
                return None

            # Check if book is already in this series
            existing = session.query(SeriesBook).filter(
                SeriesBook.series_id == str(series_id),
                SeriesBook.book_id == str(book_entry.book_id),
            ).first()

            if existing:
                # Update existing entry instead
                return self._to_series_book_response(existing)

            db_entry = SeriesBook(
                series_id=str(series_id),
                book_id=str(book_entry.book_id),
                position=book_entry.position,
                position_label=book_entry.position_label,
                is_main_series=book_entry.is_main_series,
                is_optional=book_entry.is_optional,
                is_read=book_entry.is_read,
                is_owned=book_entry.is_owned,
                notes=book_entry.notes,
            )

            session.add(db_entry)
            session.flush()

            # Update series counts
            self._update_series_counts(session, series)

            return self._to_series_book_response(db_entry)

    def update_series_book(
        self, entry_id: UUID, updates: SeriesBookUpdate
    ) -> Optional[SeriesBookResponse]:
        """Update a series book entry.

        Args:
            entry_id: Series book entry UUID
            updates: Fields to update

        Returns:
            Updated entry or None if not found
        """
        with self.db.get_session() as session:
            entry = session.query(SeriesBook).filter(
                SeriesBook.id == str(entry_id)
            ).first()

            if not entry:
                return None

            update_data = updates.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                setattr(entry, field, value)

            session.flush()

            # Update series counts if read/owned status changed
            if "is_read" in update_data or "is_owned" in update_data:
                series = session.query(Series).filter(
                    Series.id == entry.series_id
                ).first()
                if series:
                    self._update_series_counts(session, series)

            return self._to_series_book_response(entry)

    def remove_book_from_series(self, entry_id: UUID) -> bool:
        """Remove a book from a series.

        Args:
            entry_id: Series book entry UUID

        Returns:
            True if removed, False if not found
        """
        with self.db.get_session() as session:
            entry = session.query(SeriesBook).filter(
                SeriesBook.id == str(entry_id)
            ).first()

            if not entry:
                return False

            series_id = entry.series_id
            session.delete(entry)
            session.flush()

            # Update series counts
            series = session.query(Series).filter(
                Series.id == series_id
            ).first()
            if series:
                self._update_series_counts(session, series)

            return True

    def get_series_books(
        self, series_id: UUID, include_optional: bool = True
    ) -> list[SeriesBookWithDetails]:
        """Get all books in a series.

        Args:
            series_id: Series UUID
            include_optional: Whether to include optional books

        Returns:
            List of series books with details
        """
        with self.db.get_session() as session:
            query = session.query(SeriesBook).filter(
                SeriesBook.series_id == str(series_id)
            )

            if not include_optional:
                query = query.filter(SeriesBook.is_optional == False)  # noqa: E712

            entries = query.order_by(asc(SeriesBook.position)).all()

            return [
                self._to_series_book_with_details(session, entry)
                for entry in entries
            ]

    def get_series_with_books(self, series_id: UUID) -> Optional[SeriesWithBooks]:
        """Get a series with all its books.

        Args:
            series_id: Series UUID

        Returns:
            Series with books or None if not found
        """
        with self.db.get_session() as session:
            series = session.query(Series).filter(
                Series.id == str(series_id)
            ).first()

            if not series:
                return None

            entries = session.query(SeriesBook).filter(
                SeriesBook.series_id == str(series_id)
            ).order_by(asc(SeriesBook.position)).all()

            books = [
                self._to_series_book_with_details(session, entry)
                for entry in entries
            ]

            # Find next to read
            next_to_read = None
            for book in books:
                if not book.is_read and not book.is_optional:
                    next_to_read = book
                    break

            return SeriesWithBooks(
                series=self._to_series_response(series),
                books=books,
                next_to_read=next_to_read,
            )

    def mark_book_read(
        self, series_id: UUID, book_id: UUID, is_read: bool = True
    ) -> Optional[SeriesBookResponse]:
        """Mark a book in a series as read/unread.

        Args:
            series_id: Series UUID
            book_id: Book UUID
            is_read: Read status

        Returns:
            Updated entry or None if not found
        """
        with self.db.get_session() as session:
            entry = session.query(SeriesBook).filter(
                SeriesBook.series_id == str(series_id),
                SeriesBook.book_id == str(book_id),
            ).first()

            if not entry:
                return None

            entry.is_read = is_read
            session.flush()

            # Update series counts and status
            series = session.query(Series).filter(
                Series.id == str(series_id)
            ).first()
            if series:
                self._update_series_counts(session, series)
                self._auto_update_series_status(session, series)

            return self._to_series_book_response(entry)

    # ========================================================================
    # Series Discovery and Recommendations
    # ========================================================================

    def get_next_in_series(self, limit: int = 5) -> list[NextInSeries]:
        """Get recommendations for next books to read in series.

        Args:
            limit: Max recommendations

        Returns:
            List of next book recommendations
        """
        with self.db.get_session() as session:
            # Get series that are in progress
            in_progress = session.query(Series).filter(
                Series.status == SeriesStatus.IN_PROGRESS.value
            ).all()

            recommendations = []

            for series in in_progress:
                # Get first unread, non-optional book
                next_book = session.query(SeriesBook).filter(
                    SeriesBook.series_id == series.id,
                    SeriesBook.is_read == False,  # noqa: E712
                    SeriesBook.is_optional == False,  # noqa: E712
                ).order_by(asc(SeriesBook.position)).first()

                if next_book:
                    recommendations.append(NextInSeries(
                        series_id=UUID(series.id),
                        series_name=series.name,
                        book_entry=self._to_series_book_with_details(session, next_book),
                        books_read_in_series=series.books_read,
                        total_in_series=series.total_books,
                    ))

                if len(recommendations) >= limit:
                    break

            return recommendations

    def find_series_for_book(self, book_id: UUID) -> list[SeriesSummary]:
        """Find all series a book belongs to.

        Args:
            book_id: Book UUID

        Returns:
            List of series the book is in
        """
        with self.db.get_session() as session:
            entries = session.query(SeriesBook).filter(
                SeriesBook.book_id == str(book_id)
            ).all()

            series_ids = [entry.series_id for entry in entries]

            if not series_ids:
                return []

            series_list = session.query(Series).filter(
                Series.id.in_(series_ids)
            ).all()

            return [self._to_series_summary(s) for s in series_list]

    # ========================================================================
    # Statistics
    # ========================================================================

    def get_stats(self) -> SeriesStats:
        """Get series statistics.

        Returns:
            Statistics about series tracking
        """
        with self.db.get_session() as session:
            all_series = session.query(Series).all()

            if not all_series:
                return SeriesStats(
                    total_series=0,
                    by_status={},
                    completed_series=0,
                    in_progress_series=0,
                    total_series_books=0,
                    series_books_read=0,
                    overall_completion=0.0,
                    average_series_length=0.0,
                    longest_series=None,
                    most_read_series=None,
                )

            # Count by status
            by_status = {}
            for series in all_series:
                status_display = series.status_display
                by_status[status_display] = by_status.get(status_display, 0) + 1

            completed = sum(1 for s in all_series if s.status == SeriesStatus.COMPLETED.value)
            in_progress = sum(1 for s in all_series if s.status == SeriesStatus.IN_PROGRESS.value)

            # Book counts
            total_books = session.query(SeriesBook).count()
            books_read = session.query(SeriesBook).filter(
                SeriesBook.is_read == True  # noqa: E712
            ).count()

            # Overall completion
            overall_completion = (books_read / total_books * 100) if total_books > 0 else 0.0

            # Average series length
            series_with_totals = [s for s in all_series if s.total_books]
            avg_length = (
                sum(s.total_books for s in series_with_totals) / len(series_with_totals)
                if series_with_totals else 0.0
            )

            # Longest series
            longest = max(
                (s for s in all_series if s.total_books),
                key=lambda s: s.total_books,
                default=None
            )
            longest_name = longest.name if longest else None

            # Most read series
            most_read = max(all_series, key=lambda s: s.books_read, default=None)
            most_read_name = most_read.name if most_read and most_read.books_read > 0 else None

            return SeriesStats(
                total_series=len(all_series),
                by_status=by_status,
                completed_series=completed,
                in_progress_series=in_progress,
                total_series_books=total_books,
                series_books_read=books_read,
                overall_completion=overall_completion,
                average_series_length=avg_length,
                longest_series=longest_name,
                most_read_series=most_read_name,
            )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _update_series_counts(self, session: Session, series: Series) -> None:
        """Update the books_read and books_owned counts for a series."""
        entries = session.query(SeriesBook).filter(
            SeriesBook.series_id == series.id
        ).all()

        series.books_read = sum(1 for e in entries if e.is_read)
        series.books_owned = sum(1 for e in entries if e.is_owned)

        # Update average rating from book ratings
        book_ids = [e.book_id for e in entries if e.is_read]
        if book_ids:
            books = session.query(Book).filter(
                Book.id.in_(book_ids),
                Book.rating.isnot(None),
            ).all()
            if books:
                series.average_rating = sum(b.rating for b in books) / len(books)

    def _auto_update_series_status(self, session: Session, series: Series) -> None:
        """Automatically update series status based on reading progress."""
        # Count main series books (non-optional)
        main_books = session.query(SeriesBook).filter(
            SeriesBook.series_id == series.id,
            SeriesBook.is_optional == False,  # noqa: E712
        ).all()

        read_main = sum(1 for b in main_books if b.is_read)
        total_main = len(main_books)

        if total_main == 0:
            return

        # Auto-update status
        if read_main == 0:
            if series.status != SeriesStatus.ON_HOLD.value:
                series.status = SeriesStatus.NOT_STARTED.value
        elif read_main == total_main:
            # Check if we know the series is complete and we've read all known books
            if series.is_complete or (series.total_books and read_main >= series.total_books):
                series.status = SeriesStatus.COMPLETED.value
            else:
                # Still in progress if series might have more books
                series.status = SeriesStatus.IN_PROGRESS.value
        else:
            if series.status not in (SeriesStatus.ON_HOLD.value, SeriesStatus.ABANDONED.value):
                series.status = SeriesStatus.IN_PROGRESS.value

    def _to_series_response(self, series: Series) -> SeriesResponse:
        """Convert model to response schema."""
        return SeriesResponse(
            id=UUID(series.id),
            name=series.name,
            author=series.author,
            description=series.description,
            total_books=series.total_books,
            is_complete=series.is_complete,
            genre=series.genre,
            status=SeriesStatus(series.status),
            status_display=series.status_display,
            books_owned=series.books_owned,
            books_read=series.books_read,
            completion_percentage=series.completion_percentage,
            books_remaining=series.books_remaining,
            average_rating=series.average_rating,
            goodreads_series_id=series.goodreads_series_id,
            goodreads_url=series.goodreads_url,
            notes=series.notes,
            created_at=datetime.fromisoformat(series.created_at),
            updated_at=datetime.fromisoformat(series.updated_at),
        )

    def _to_series_summary(self, series: Series) -> SeriesSummary:
        """Convert model to summary schema."""
        return SeriesSummary(
            id=UUID(series.id),
            name=series.name,
            author=series.author,
            status=SeriesStatus(series.status),
            status_display=series.status_display,
            total_books=series.total_books,
            books_read=series.books_read,
            completion_percentage=series.completion_percentage,
            is_complete=series.is_complete,
        )

    def _to_series_book_response(self, entry: SeriesBook) -> SeriesBookResponse:
        """Convert model to response schema."""
        return SeriesBookResponse(
            id=UUID(entry.id),
            series_id=UUID(entry.series_id),
            book_id=UUID(entry.book_id),
            position=entry.position,
            position_display=entry.position_display,
            position_label=entry.position_label,
            is_main_series=entry.is_main_series,
            is_optional=entry.is_optional,
            is_read=entry.is_read,
            is_owned=entry.is_owned,
            notes=entry.notes,
            created_at=datetime.fromisoformat(entry.created_at),
            updated_at=datetime.fromisoformat(entry.updated_at),
        )

    def _to_series_book_with_details(
        self, session: Session, entry: SeriesBook
    ) -> SeriesBookWithDetails:
        """Convert model to response with book details."""
        # Get book details
        book = session.query(Book).filter(Book.id == entry.book_id).first()

        return SeriesBookWithDetails(
            id=UUID(entry.id),
            series_id=UUID(entry.series_id),
            book_id=UUID(entry.book_id),
            position=entry.position,
            position_display=entry.position_display,
            position_label=entry.position_label,
            is_main_series=entry.is_main_series,
            is_optional=entry.is_optional,
            is_read=entry.is_read,
            is_owned=entry.is_owned,
            notes=entry.notes,
            book_title=book.title if book else None,
            book_author=book.author if book else None,
            book_rating=book.rating if book else None,
            book_status=book.status if book else None,
        )
