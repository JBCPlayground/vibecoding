"""Reading progress tracking and statistics.

Calculates reading stats, progress percentages, and provides
analytics on reading habits.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func

from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


@dataclass
class ReadingStats:
    """Reading statistics for a time period."""

    # Totals
    total_pages: int = 0
    total_minutes: int = 0
    total_sessions: int = 0
    total_books: int = 0
    books_finished: int = 0

    # Averages
    avg_pages_per_session: float = 0.0
    avg_minutes_per_session: float = 0.0
    avg_pages_per_day: float = 0.0
    avg_reading_speed: float = 0.0  # pages per hour

    # Streaks
    current_streak_days: int = 0
    longest_streak_days: int = 0

    # By location
    pages_by_location: dict[str, int] = None

    def __post_init__(self):
        if self.pages_by_location is None:
            self.pages_by_location = {}


class ProgressTracker:
    """Tracks and calculates reading progress."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize progress tracker.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def get_book_progress(self, book_id: str) -> dict:
        """Get progress info for a specific book.

        Args:
            book_id: Book ID

        Returns:
            Dictionary with progress info:
            - current_page: Last recorded page
            - total_pages: Book's page count
            - progress_percent: Percentage complete
            - pages_read: Total pages read across sessions
            - time_spent_minutes: Total reading time
            - sessions_count: Number of reading sessions
            - estimated_time_remaining: Minutes to finish at current pace
        """
        with self.db.get_session() as session:
            book = session.get(Book, book_id)
            if not book:
                raise ValueError(f"Book not found: {book_id}")

            # Get all reading logs for this book
            stmt = select(ReadingLog).where(ReadingLog.book_id == book_id)
            logs = list(session.execute(stmt).scalars().all())

            # Calculate totals
            total_pages_read = sum(log.pages_read or 0 for log in logs)
            total_minutes = sum(log.duration_minutes or 0 for log in logs)
            sessions_count = len(logs)

            # Get current page (highest end_page)
            current_page = max((log.end_page or 0 for log in logs), default=0)

            # Calculate progress percentage
            progress_percent = 0
            if book.page_count and book.page_count > 0:
                progress_percent = min(100, int((current_page / book.page_count) * 100))

            # Estimate remaining time
            estimated_remaining = None
            if total_pages_read > 0 and total_minutes > 0 and book.page_count:
                pages_per_minute = total_pages_read / total_minutes
                remaining_pages = max(0, book.page_count - current_page)
                if pages_per_minute > 0:
                    estimated_remaining = int(remaining_pages / pages_per_minute)

            return {
                "book_id": book_id,
                "book_title": book.title,
                "current_page": current_page,
                "total_pages": book.page_count,
                "progress_percent": progress_percent,
                "pages_read": total_pages_read,
                "time_spent_minutes": total_minutes,
                "sessions_count": sessions_count,
                "estimated_time_remaining": estimated_remaining,
            }

    def get_reading_history(
        self,
        book_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get reading history.

        Args:
            book_id: Filter by book ID (optional)
            start_date: Start date filter (optional)
            end_date: End date filter (optional)
            limit: Maximum results to return

        Returns:
            List of reading log entries with book info
        """
        with self.db.get_session() as session:
            stmt = select(ReadingLog, Book).join(Book)

            if book_id:
                stmt = stmt.where(ReadingLog.book_id == book_id)

            if start_date:
                stmt = stmt.where(ReadingLog.date >= start_date.isoformat())

            if end_date:
                stmt = stmt.where(ReadingLog.date <= end_date.isoformat())

            stmt = stmt.order_by(ReadingLog.date.desc()).limit(limit)

            results = session.execute(stmt).all()

            history = []
            for log, book in results:
                history.append({
                    "id": log.id,
                    "book_id": log.book_id,
                    "book_title": book.title,
                    "book_author": book.author,
                    "date": log.date,
                    "pages_read": log.pages_read,
                    "start_page": log.start_page,
                    "end_page": log.end_page,
                    "duration_minutes": log.duration_minutes,
                    "location": log.location,
                    "notes": log.notes,
                })

            return history

    def get_stats(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> ReadingStats:
        """Get reading statistics for a time period.

        Args:
            start_date: Start of period (default: 30 days ago)
            end_date: End of period (default: today)

        Returns:
            ReadingStats with calculated metrics
        """
        if start_date is None:
            start_date = date.today() - timedelta(days=30)
        if end_date is None:
            end_date = date.today()

        with self.db.get_session() as session:
            # Get logs in date range
            stmt = select(ReadingLog).where(
                ReadingLog.date >= start_date.isoformat(),
                ReadingLog.date <= end_date.isoformat(),
            )
            logs = list(session.execute(stmt).scalars().all())

            if not logs:
                return ReadingStats()

            # Calculate totals
            total_pages = sum(log.pages_read or 0 for log in logs)
            total_minutes = sum(log.duration_minutes or 0 for log in logs)
            total_sessions = len(logs)

            # Count unique books read
            book_ids = set(log.book_id for log in logs)
            total_books = len(book_ids)

            # Count books finished in period
            stmt = select(Book).where(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= start_date.isoformat(),
                Book.date_finished <= end_date.isoformat(),
            )
            finished_books = len(list(session.execute(stmt).scalars().all()))

            # Calculate averages
            avg_pages_per_session = total_pages / total_sessions if total_sessions > 0 else 0
            avg_minutes_per_session = total_minutes / total_sessions if total_sessions > 0 else 0

            # Days in period
            days_in_period = (end_date - start_date).days + 1
            avg_pages_per_day = total_pages / days_in_period if days_in_period > 0 else 0

            # Reading speed (pages per hour)
            avg_reading_speed = (total_pages / total_minutes * 60) if total_minutes > 0 else 0

            # Pages by location
            pages_by_location = {}
            for log in logs:
                loc = log.location or "Unknown"
                pages_by_location[loc] = pages_by_location.get(loc, 0) + (log.pages_read or 0)

            # Calculate streaks
            current_streak, longest_streak = self._calculate_streaks(logs, end_date)

            return ReadingStats(
                total_pages=total_pages,
                total_minutes=total_minutes,
                total_sessions=total_sessions,
                total_books=total_books,
                books_finished=finished_books,
                avg_pages_per_session=round(avg_pages_per_session, 1),
                avg_minutes_per_session=round(avg_minutes_per_session, 1),
                avg_pages_per_day=round(avg_pages_per_day, 1),
                avg_reading_speed=round(avg_reading_speed, 1),
                current_streak_days=current_streak,
                longest_streak_days=longest_streak,
                pages_by_location=pages_by_location,
            )

    def _calculate_streaks(self, logs: list[ReadingLog], end_date: date) -> tuple[int, int]:
        """Calculate reading streaks from logs.

        Args:
            logs: List of reading logs
            end_date: End date of period

        Returns:
            Tuple of (current_streak, longest_streak)
        """
        if not logs:
            return 0, 0

        # Get unique dates with reading activity
        reading_dates = sorted(set(
            date.fromisoformat(log.date) for log in logs
        ), reverse=True)

        if not reading_dates:
            return 0, 0

        # Calculate current streak (consecutive days ending today or yesterday)
        current_streak = 0
        check_date = end_date

        # Allow for yesterday if not read today
        if reading_dates[0] == check_date - timedelta(days=1):
            check_date = check_date - timedelta(days=1)

        for reading_date in reading_dates:
            if reading_date == check_date:
                current_streak += 1
                check_date -= timedelta(days=1)
            elif reading_date < check_date:
                break

        # Calculate longest streak
        longest_streak = 1
        current_run = 1
        sorted_dates = sorted(reading_dates)

        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
                current_run += 1
                longest_streak = max(longest_streak, current_run)
            else:
                current_run = 1

        return current_streak, longest_streak

    def get_currently_reading(self) -> list[dict]:
        """Get books currently being read with progress.

        Returns:
            List of books with status 'reading' and their progress
        """
        with self.db.get_session() as session:
            stmt = select(Book).where(Book.status == BookStatus.READING.value)
            books = list(session.execute(stmt).scalars().all())

            result = []
            for book in books:
                # Get latest reading log
                log_stmt = (
                    select(ReadingLog)
                    .where(ReadingLog.book_id == book.id)
                    .order_by(ReadingLog.date.desc())
                    .limit(1)
                )
                latest_log = session.execute(log_stmt).scalar_one_or_none()

                current_page = None
                last_read_date = None

                if latest_log:
                    current_page = latest_log.end_page
                    last_read_date = latest_log.date

                progress_percent = 0
                if book.page_count and current_page:
                    progress_percent = min(100, int((current_page / book.page_count) * 100))

                result.append({
                    "book_id": book.id,
                    "title": book.title,
                    "author": book.author,
                    "current_page": current_page,
                    "total_pages": book.page_count,
                    "progress_percent": progress_percent,
                    "progress_str": book.progress,
                    "last_read_date": last_read_date,
                })

            return result


def calculate_reading_speed(pages: int, minutes: int) -> float:
    """Calculate reading speed in pages per hour.

    Args:
        pages: Number of pages read
        minutes: Time spent reading

    Returns:
        Pages per hour
    """
    if minutes <= 0:
        return 0.0
    return round((pages / minutes) * 60, 1)
