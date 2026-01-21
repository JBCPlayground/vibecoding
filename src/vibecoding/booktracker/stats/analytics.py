"""Reading analytics and statistics calculations.

Provides detailed statistics about reading habits, including:
- Yearly and monthly breakdowns
- Author and genre statistics
- Rating distributions
- Reading pace analysis
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, func

from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


@dataclass
class YearlyStats:
    """Statistics for a specific year."""

    year: int
    books_finished: int = 0
    books_started: int = 0
    total_pages: int = 0
    total_reading_time: int = 0  # minutes
    avg_rating: float = 0.0
    avg_pages_per_book: float = 0.0
    avg_days_to_finish: float = 0.0
    books_by_month: dict[int, int] = field(default_factory=dict)
    pages_by_month: dict[int, int] = field(default_factory=dict)
    top_authors: list[tuple[str, int]] = field(default_factory=list)
    top_genres: list[tuple[str, int]] = field(default_factory=list)
    rating_distribution: dict[int, int] = field(default_factory=dict)


@dataclass
class MonthlyStats:
    """Statistics for a specific month."""

    year: int
    month: int
    books_finished: int = 0
    pages_read: int = 0
    reading_sessions: int = 0
    reading_time: int = 0  # minutes
    avg_pages_per_day: float = 0.0
    books: list[dict] = field(default_factory=list)


@dataclass
class AuthorStats:
    """Statistics for a specific author."""

    author: str
    books_read: int = 0
    total_pages: int = 0
    avg_rating: float = 0.0
    books: list[dict] = field(default_factory=list)


@dataclass
class GenreStats:
    """Statistics for genres/tags."""

    genre: str
    books_count: int = 0
    avg_rating: float = 0.0
    total_pages: int = 0


class ReadingAnalytics:
    """Calculates reading analytics and statistics."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize analytics.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def get_yearly_stats(self, year: Optional[int] = None) -> YearlyStats:
        """Get comprehensive statistics for a year.

        Args:
            year: Year to analyze (default: current year)

        Returns:
            YearlyStats with all metrics
        """
        if year is None:
            year = date.today().year

        with self.db.get_session() as session:
            # Get books finished this year
            year_start = f"{year}-01-01"
            year_end = f"{year}-12-31"

            stmt = select(Book).where(
                Book.date_finished >= year_start,
                Book.date_finished <= year_end,
            )
            finished_books = list(session.execute(stmt).scalars().all())

            # Get books started this year
            stmt = select(Book).where(
                Book.date_started >= year_start,
                Book.date_started <= year_end,
            )
            started_books = list(session.execute(stmt).scalars().all())

            # Get reading logs for the year
            stmt = select(ReadingLog).where(
                ReadingLog.date >= year_start,
                ReadingLog.date <= year_end,
            )
            logs = list(session.execute(stmt).scalars().all())

            # Calculate basic stats
            books_finished = len(finished_books)
            books_started = len(started_books)

            total_pages = sum(book.page_count or 0 for book in finished_books)
            total_reading_time = sum(log.duration_minutes or 0 for log in logs)

            # Average rating
            rated_books = [b for b in finished_books if b.rating]
            avg_rating = (
                sum(b.rating for b in rated_books) / len(rated_books)
                if rated_books else 0.0
            )

            # Average pages per book
            avg_pages = total_pages / books_finished if books_finished > 0 else 0.0

            # Average days to finish
            days_to_finish = []
            for book in finished_books:
                if book.date_started and book.date_finished:
                    start = date.fromisoformat(book.date_started)
                    end = date.fromisoformat(book.date_finished)
                    days = (end - start).days
                    if days >= 0:
                        days_to_finish.append(days)
            avg_days = sum(days_to_finish) / len(days_to_finish) if days_to_finish else 0.0

            # Books by month
            books_by_month = defaultdict(int)
            for book in finished_books:
                month = int(book.date_finished[5:7])
                books_by_month[month] += 1

            # Pages by month (from reading logs)
            pages_by_month = defaultdict(int)
            for log in logs:
                month = int(log.date[5:7])
                pages_by_month[month] += log.pages_read or 0

            # Top authors
            author_counts = Counter(book.author for book in finished_books)
            top_authors = author_counts.most_common(10)

            # Top genres (from tags)
            genre_counts = Counter()
            for book in finished_books:
                tags = book.get_tags()
                genre_counts.update(tags)
            top_genres = genre_counts.most_common(10)

            # Rating distribution
            rating_dist = Counter(book.rating for book in finished_books if book.rating)

            return YearlyStats(
                year=year,
                books_finished=books_finished,
                books_started=books_started,
                total_pages=total_pages,
                total_reading_time=total_reading_time,
                avg_rating=round(avg_rating, 2),
                avg_pages_per_book=round(avg_pages, 1),
                avg_days_to_finish=round(avg_days, 1),
                books_by_month=dict(books_by_month),
                pages_by_month=dict(pages_by_month),
                top_authors=top_authors,
                top_genres=top_genres,
                rating_distribution=dict(rating_dist),
            )

    def get_monthly_stats(self, year: int, month: int) -> MonthlyStats:
        """Get statistics for a specific month.

        Args:
            year: Year
            month: Month (1-12)

        Returns:
            MonthlyStats for the month
        """
        with self.db.get_session() as session:
            month_start = f"{year}-{month:02d}-01"
            if month == 12:
                month_end = f"{year + 1}-01-01"
            else:
                month_end = f"{year}-{month + 1:02d}-01"

            # Get books finished this month
            stmt = select(Book).where(
                Book.date_finished >= month_start,
                Book.date_finished < month_end,
            )
            finished_books = list(session.execute(stmt).scalars().all())

            # Get reading logs for the month
            stmt = select(ReadingLog).where(
                ReadingLog.date >= month_start,
                ReadingLog.date < month_end,
            )
            logs = list(session.execute(stmt).scalars().all())

            # Calculate stats
            pages_read = sum(log.pages_read or 0 for log in logs)
            reading_time = sum(log.duration_minutes or 0 for log in logs)

            # Days in month
            import calendar
            days_in_month = calendar.monthrange(year, month)[1]
            avg_pages_per_day = pages_read / days_in_month if days_in_month > 0 else 0

            # Book details
            books = []
            for book in finished_books:
                session.expunge(book)
                books.append({
                    "title": book.title,
                    "author": book.author,
                    "rating": book.rating,
                    "pages": book.page_count,
                    "date_finished": book.date_finished,
                })

            return MonthlyStats(
                year=year,
                month=month,
                books_finished=len(finished_books),
                pages_read=pages_read,
                reading_sessions=len(logs),
                reading_time=reading_time,
                avg_pages_per_day=round(avg_pages_per_day, 1),
                books=books,
            )

    def get_author_stats(self, author: Optional[str] = None) -> list[AuthorStats]:
        """Get statistics by author.

        Args:
            author: Specific author to query (None for all)

        Returns:
            List of AuthorStats
        """
        with self.db.get_session() as session:
            stmt = select(Book).where(Book.status == BookStatus.COMPLETED.value)
            if author:
                stmt = stmt.where(Book.author.ilike(f"%{author}%"))

            books = list(session.execute(stmt).scalars().all())

            # Group by author
            author_books = defaultdict(list)
            for book in books:
                session.expunge(book)
                author_books[book.author].append(book)

            stats = []
            for auth, auth_books in author_books.items():
                total_pages = sum(b.page_count or 0 for b in auth_books)
                rated = [b for b in auth_books if b.rating]
                avg_rating = sum(b.rating for b in rated) / len(rated) if rated else 0

                stats.append(AuthorStats(
                    author=auth,
                    books_read=len(auth_books),
                    total_pages=total_pages,
                    avg_rating=round(avg_rating, 2),
                    books=[{
                        "title": b.title,
                        "rating": b.rating,
                        "pages": b.page_count,
                        "date_finished": b.date_finished,
                    } for b in auth_books],
                ))

            # Sort by books read
            stats.sort(key=lambda x: x.books_read, reverse=True)
            return stats

    def get_genre_stats(self) -> list[GenreStats]:
        """Get statistics by genre/tag.

        Returns:
            List of GenreStats sorted by count
        """
        with self.db.get_session() as session:
            stmt = select(Book).where(Book.status == BookStatus.COMPLETED.value)
            books = list(session.execute(stmt).scalars().all())

            # Collect genre data
            genre_data = defaultdict(lambda: {"count": 0, "ratings": [], "pages": 0})

            for book in books:
                tags = book.get_tags()
                for tag in tags:
                    genre_data[tag]["count"] += 1
                    if book.rating:
                        genre_data[tag]["ratings"].append(book.rating)
                    genre_data[tag]["pages"] += book.page_count or 0

            stats = []
            for genre, data in genre_data.items():
                avg_rating = (
                    sum(data["ratings"]) / len(data["ratings"])
                    if data["ratings"] else 0
                )
                stats.append(GenreStats(
                    genre=genre,
                    books_count=data["count"],
                    avg_rating=round(avg_rating, 2),
                    total_pages=data["pages"],
                ))

            stats.sort(key=lambda x: x.books_count, reverse=True)
            return stats

    def get_reading_pace(self, days: int = 30) -> dict:
        """Calculate recent reading pace.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with pace metrics
        """
        with self.db.get_session() as session:
            start_date = (date.today() - timedelta(days=days)).isoformat()

            # Get reading logs
            stmt = select(ReadingLog).where(ReadingLog.date >= start_date)
            logs = list(session.execute(stmt).scalars().all())

            # Get books finished
            stmt = select(Book).where(
                Book.date_finished >= start_date,
                Book.status == BookStatus.COMPLETED.value,
            )
            finished = list(session.execute(stmt).scalars().all())

            total_pages = sum(log.pages_read or 0 for log in logs)
            total_time = sum(log.duration_minutes or 0 for log in logs)
            sessions = len(logs)

            # Active reading days
            reading_days = len(set(log.date for log in logs))

            return {
                "period_days": days,
                "books_finished": len(finished),
                "total_pages": total_pages,
                "total_time_minutes": total_time,
                "reading_sessions": sessions,
                "active_days": reading_days,
                "pages_per_day": round(total_pages / days, 1) if days > 0 else 0,
                "pages_per_session": round(total_pages / sessions, 1) if sessions > 0 else 0,
                "avg_session_length": round(total_time / sessions, 1) if sessions > 0 else 0,
                "reading_frequency": round(reading_days / days * 100, 1) if days > 0 else 0,
            }

    def get_all_time_stats(self) -> dict:
        """Get all-time reading statistics.

        Returns:
            Dictionary with comprehensive all-time stats
        """
        with self.db.get_session() as session:
            # All completed books
            stmt = select(Book).where(Book.status == BookStatus.COMPLETED.value)
            completed = list(session.execute(stmt).scalars().all())

            # All books
            stmt = select(Book)
            all_books = list(session.execute(stmt).scalars().all())

            # All reading logs
            stmt = select(ReadingLog)
            all_logs = list(session.execute(stmt).scalars().all())

            # Basic counts
            total_books = len(all_books)
            completed_count = len(completed)
            total_pages = sum(b.page_count or 0 for b in completed)

            # Reading time
            total_time = sum(log.duration_minutes or 0 for log in all_logs)
            hours = total_time // 60
            days_reading = total_time / (24 * 60) if total_time > 0 else 0

            # Ratings
            rated = [b for b in completed if b.rating]
            avg_rating = sum(b.rating for b in rated) / len(rated) if rated else 0

            # First and last book
            finished_dates = [b.date_finished for b in completed if b.date_finished]
            first_book_date = min(finished_dates) if finished_dates else None
            last_book_date = max(finished_dates) if finished_dates else None

            # Years active
            years = set(d[:4] for d in finished_dates) if finished_dates else set()

            # Longest book
            longest = max(completed, key=lambda b: b.page_count or 0) if completed else None

            # Highest rated
            if rated:
                five_stars = [b for b in rated if b.rating == 5]
            else:
                five_stars = []

            return {
                "total_books": total_books,
                "books_completed": completed_count,
                "total_pages": total_pages,
                "total_reading_hours": hours,
                "days_spent_reading": round(days_reading, 1),
                "avg_rating": round(avg_rating, 2),
                "books_rated": len(rated),
                "five_star_books": len(five_stars),
                "years_active": len(years),
                "first_book_date": first_book_date,
                "last_book_date": last_book_date,
                "longest_book": {
                    "title": longest.title,
                    "pages": longest.page_count,
                } if longest and longest.page_count else None,
                "avg_book_length": round(total_pages / completed_count, 0) if completed_count > 0 else 0,
            }

    def get_rating_analysis(self) -> dict:
        """Analyze rating patterns.

        Returns:
            Dictionary with rating analysis
        """
        with self.db.get_session() as session:
            stmt = select(Book).where(
                Book.status == BookStatus.COMPLETED.value,
                Book.rating.isnot(None),
            )
            rated_books = list(session.execute(stmt).scalars().all())

            if not rated_books:
                return {
                    "total_rated": 0,
                    "distribution": {},
                    "avg_rating": 0,
                    "mode_rating": None,
                }

            # Distribution
            distribution = Counter(b.rating for b in rated_books)

            # Calculate percentages
            total = len(rated_books)
            dist_pct = {
                rating: round(count / total * 100, 1)
                for rating, count in distribution.items()
            }

            # Average
            avg = sum(b.rating for b in rated_books) / total

            # Mode (most common)
            mode = distribution.most_common(1)[0][0] if distribution else None

            # Harshest and most generous periods
            # (could expand to track rating trends over time)

            return {
                "total_rated": total,
                "distribution": dict(distribution),
                "distribution_percent": dist_pct,
                "avg_rating": round(avg, 2),
                "mode_rating": mode,
            }
