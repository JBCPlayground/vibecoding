"""Reading reports generation.

Creates formatted reading reports including Year in Review and Monthly summaries.
"""

import calendar
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select

from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


@dataclass
class BookSummary:
    """Summary of a book for reports."""

    title: str
    author: str
    rating: Optional[int] = None
    page_count: Optional[int] = None
    date_finished: Optional[str] = None
    tags: list[str] = field(default_factory=list)


@dataclass
class MonthlyReport:
    """Monthly reading report."""

    year: int
    month: int
    month_name: str
    books_finished: int = 0
    pages_read: int = 0
    reading_time_minutes: int = 0
    reading_sessions: int = 0
    books: list[BookSummary] = field(default_factory=list)
    avg_rating: float = 0.0
    active_days: int = 0


@dataclass
class YearInReview:
    """Comprehensive year-end reading summary."""

    year: int

    # Basic stats
    books_finished: int = 0
    books_started: int = 0
    total_pages: int = 0
    total_reading_time_minutes: int = 0
    total_reading_sessions: int = 0

    # Averages
    avg_rating: float = 0.0
    avg_book_length: float = 0.0
    avg_days_to_finish: float = 0.0
    avg_pages_per_day: float = 0.0

    # Records
    longest_book: Optional[BookSummary] = None
    shortest_book: Optional[BookSummary] = None
    highest_rated_book: Optional[BookSummary] = None
    fastest_read: Optional[BookSummary] = None

    # Breakdowns
    books_by_month: dict[int, int] = field(default_factory=dict)
    pages_by_month: dict[int, int] = field(default_factory=dict)
    rating_distribution: dict[int, int] = field(default_factory=dict)

    # Top lists
    top_authors: list[tuple[str, int]] = field(default_factory=list)
    top_genres: list[tuple[str, int]] = field(default_factory=list)
    five_star_books: list[BookSummary] = field(default_factory=list)

    # Monthly summaries
    monthly_summaries: list[MonthlyReport] = field(default_factory=list)

    # Reading habits
    most_productive_month: Optional[str] = None
    favorite_reading_location: Optional[str] = None
    reading_streak_days: int = 0
    active_reading_days: int = 0

    # Comparisons (if previous year data exists)
    books_vs_last_year: Optional[int] = None
    pages_vs_last_year: Optional[int] = None


class ReportGenerator:
    """Generates reading reports."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize report generator.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def generate_year_in_review(self, year: Optional[int] = None) -> YearInReview:
        """Generate a comprehensive year in review report.

        Args:
            year: Year to generate report for (default: current year)

        Returns:
            YearInReview with all statistics and summaries
        """
        if year is None:
            year = date.today().year

        review = YearInReview(year=year)

        with self.db.get_session() as session:
            year_start = f"{year}-01-01"
            year_end = f"{year}-12-31"

            # Get finished books
            stmt = select(Book).where(
                Book.date_finished >= year_start,
                Book.date_finished <= year_end,
            )
            finished_books = list(session.execute(stmt).scalars().all())

            # Get started books
            stmt = select(Book).where(
                Book.date_started >= year_start,
                Book.date_started <= year_end,
            )
            started_books = list(session.execute(stmt).scalars().all())

            # Get reading logs
            stmt = select(ReadingLog).where(
                ReadingLog.date >= year_start,
                ReadingLog.date <= year_end,
            )
            logs = list(session.execute(stmt).scalars().all())

            # Basic stats
            review.books_finished = len(finished_books)
            review.books_started = len(started_books)
            review.total_pages = sum(b.page_count or 0 for b in finished_books)
            review.total_reading_time_minutes = sum(log.duration_minutes or 0 for log in logs)
            review.total_reading_sessions = len(logs)

            # Active days
            reading_dates = set(log.date for log in logs)
            review.active_reading_days = len(reading_dates)

            # Averages
            if finished_books:
                rated_books = [b for b in finished_books if b.rating]
                if rated_books:
                    review.avg_rating = round(
                        sum(b.rating for b in rated_books) / len(rated_books), 2
                    )

                review.avg_book_length = round(
                    review.total_pages / len(finished_books), 0
                )

                # Average days to finish
                days_list = []
                for book in finished_books:
                    if book.date_started and book.date_finished:
                        start = date.fromisoformat(book.date_started)
                        end = date.fromisoformat(book.date_finished)
                        days = (end - start).days
                        if days >= 0:
                            days_list.append(days)
                if days_list:
                    review.avg_days_to_finish = round(sum(days_list) / len(days_list), 1)

            # Average pages per day
            days_in_year = 366 if calendar.isleap(year) else 365
            today = date.today()
            if year == today.year:
                days_elapsed = today.timetuple().tm_yday
            else:
                days_elapsed = days_in_year
            review.avg_pages_per_day = round(review.total_pages / days_elapsed, 1)

            # Records
            if finished_books:
                # Longest book
                books_with_pages = [b for b in finished_books if b.page_count]
                if books_with_pages:
                    longest = max(books_with_pages, key=lambda b: b.page_count)
                    review.longest_book = self._book_to_summary(longest)

                    shortest = min(books_with_pages, key=lambda b: b.page_count)
                    review.shortest_book = self._book_to_summary(shortest)

                # Highest rated
                if rated_books:
                    highest = max(rated_books, key=lambda b: b.rating)
                    review.highest_rated_book = self._book_to_summary(highest)

                # Fastest read
                fastest_days = None
                fastest_book = None
                for book in finished_books:
                    if book.date_started and book.date_finished and book.page_count:
                        start = date.fromisoformat(book.date_started)
                        end = date.fromisoformat(book.date_finished)
                        days = (end - start).days
                        if days > 0 and book.page_count >= 100:  # Meaningful reads only
                            pages_per_day = book.page_count / days
                            if fastest_days is None or pages_per_day > fastest_days:
                                fastest_days = pages_per_day
                                fastest_book = book
                if fastest_book:
                    review.fastest_read = self._book_to_summary(fastest_book)

            # Books by month
            books_by_month = defaultdict(int)
            for book in finished_books:
                month = int(book.date_finished[5:7])
                books_by_month[month] += 1
            review.books_by_month = dict(books_by_month)

            # Pages by month (from logs)
            pages_by_month = defaultdict(int)
            for log in logs:
                month = int(log.date[5:7])
                pages_by_month[month] += log.pages_read or 0
            review.pages_by_month = dict(pages_by_month)

            # Rating distribution
            rating_dist = Counter(b.rating for b in finished_books if b.rating)
            review.rating_distribution = dict(rating_dist)

            # Top authors
            author_counts = Counter(b.author for b in finished_books)
            review.top_authors = author_counts.most_common(10)

            # Top genres
            genre_counts = Counter()
            for book in finished_books:
                tags = book.get_tags()
                genre_counts.update(tags)
            review.top_genres = genre_counts.most_common(10)

            # Five star books
            review.five_star_books = [
                self._book_to_summary(b) for b in finished_books
                if b.rating == 5
            ]

            # Most productive month
            if books_by_month:
                best_month = max(books_by_month, key=books_by_month.get)
                review.most_productive_month = calendar.month_name[best_month]

            # Favorite reading location
            location_counts = Counter(log.location for log in logs if log.location)
            if location_counts:
                review.favorite_reading_location = location_counts.most_common(1)[0][0]

            # Reading streak
            review.reading_streak_days = self._calculate_max_streak(reading_dates)

            # Monthly summaries
            for month in range(1, 13):
                monthly = self.generate_monthly_report(year, month)
                review.monthly_summaries.append(monthly)

            # Year-over-year comparison
            prev_year = year - 1
            prev_year_start = f"{prev_year}-01-01"
            prev_year_end = f"{prev_year}-12-31"

            stmt = select(Book).where(
                Book.date_finished >= prev_year_start,
                Book.date_finished <= prev_year_end,
            )
            prev_finished = list(session.execute(stmt).scalars().all())

            if prev_finished:
                review.books_vs_last_year = review.books_finished - len(prev_finished)
                prev_pages = sum(b.page_count or 0 for b in prev_finished)
                review.pages_vs_last_year = review.total_pages - prev_pages

        return review

    def generate_monthly_report(self, year: int, month: int) -> MonthlyReport:
        """Generate a monthly reading report.

        Args:
            year: Year
            month: Month (1-12)

        Returns:
            MonthlyReport with statistics
        """
        month_name = calendar.month_name[month]
        report = MonthlyReport(year=year, month=month, month_name=month_name)

        with self.db.get_session() as session:
            month_start = f"{year}-{month:02d}-01"
            if month == 12:
                month_end = f"{year + 1}-01-01"
            else:
                month_end = f"{year}-{month + 1:02d}-01"

            # Get finished books
            stmt = select(Book).where(
                Book.date_finished >= month_start,
                Book.date_finished < month_end,
            )
            finished_books = list(session.execute(stmt).scalars().all())

            # Get reading logs
            stmt = select(ReadingLog).where(
                ReadingLog.date >= month_start,
                ReadingLog.date < month_end,
            )
            logs = list(session.execute(stmt).scalars().all())

            # Stats
            report.books_finished = len(finished_books)
            report.pages_read = sum(log.pages_read or 0 for log in logs)
            report.reading_time_minutes = sum(log.duration_minutes or 0 for log in logs)
            report.reading_sessions = len(logs)

            # Active days
            reading_dates = set(log.date for log in logs)
            report.active_days = len(reading_dates)

            # Book summaries
            for book in finished_books:
                session.expunge(book)
                report.books.append(self._book_to_summary(book))

            # Average rating
            rated = [b for b in finished_books if b.rating]
            if rated:
                report.avg_rating = round(
                    sum(b.rating for b in rated) / len(rated), 2
                )

        return report

    def generate_reading_stats_text(self, year: Optional[int] = None) -> str:
        """Generate a text-based reading statistics summary.

        Args:
            year: Year to summarize (default: current year)

        Returns:
            Formatted text summary
        """
        review = self.generate_year_in_review(year)

        lines = [
            f"📚 Year in Review: {review.year}",
            "=" * 40,
            "",
            "📊 Overview",
            f"  Books Finished: {review.books_finished}",
            f"  Books Started: {review.books_started}",
            f"  Total Pages: {review.total_pages:,}",
        ]

        if review.total_reading_time_minutes:
            hours = review.total_reading_time_minutes // 60
            lines.append(f"  Reading Time: {hours} hours")

        lines.append(f"  Reading Sessions: {review.total_reading_sessions}")
        lines.append(f"  Active Reading Days: {review.active_reading_days}")
        lines.append("")

        lines.append("📈 Averages")
        if review.avg_rating > 0:
            lines.append(f"  Average Rating: {review.avg_rating}/5")
        lines.append(f"  Average Book Length: {review.avg_book_length:.0f} pages")
        if review.avg_days_to_finish > 0:
            lines.append(f"  Average Days to Finish: {review.avg_days_to_finish:.1f}")
        lines.append(f"  Pages per Day: {review.avg_pages_per_day:.1f}")
        lines.append("")

        lines.append("🏆 Records")
        if review.longest_book:
            lines.append(f"  Longest Book: {review.longest_book.title} ({review.longest_book.page_count} pages)")
        if review.shortest_book:
            lines.append(f"  Shortest Book: {review.shortest_book.title} ({review.shortest_book.page_count} pages)")
        if review.highest_rated_book:
            lines.append(f"  Highest Rated: {review.highest_rated_book.title}")
        lines.append("")

        if review.top_authors:
            lines.append("✍️ Top Authors")
            for author, count in review.top_authors[:5]:
                lines.append(f"  {author}: {count} book(s)")
            lines.append("")

        if review.top_genres:
            lines.append("🏷️ Top Genres")
            for genre, count in review.top_genres[:5]:
                lines.append(f"  {genre}: {count} book(s)")
            lines.append("")

        if review.five_star_books:
            lines.append("⭐ Five-Star Books")
            for book in review.five_star_books[:5]:
                lines.append(f"  • {book.title} by {book.author}")
            lines.append("")

        if review.books_by_month:
            lines.append("📅 Books by Month")
            for month in range(1, 13):
                count = review.books_by_month.get(month, 0)
                bar = "█" * count if count else "░"
                lines.append(f"  {calendar.month_abbr[month]}: {bar} {count}")
            lines.append("")

        if review.most_productive_month:
            lines.append("🎯 Highlights")
            lines.append(f"  Most Productive Month: {review.most_productive_month}")
        if review.favorite_reading_location:
            lines.append(f"  Favorite Reading Spot: {review.favorite_reading_location}")
        if review.reading_streak_days > 1:
            lines.append(f"  Longest Reading Streak: {review.reading_streak_days} days")

        if review.books_vs_last_year is not None:
            lines.append("")
            lines.append("📊 Year-over-Year")
            if review.books_vs_last_year >= 0:
                lines.append(f"  Books: +{review.books_vs_last_year} vs last year")
            else:
                lines.append(f"  Books: {review.books_vs_last_year} vs last year")
            if review.pages_vs_last_year is not None:
                if review.pages_vs_last_year >= 0:
                    lines.append(f"  Pages: +{review.pages_vs_last_year:,} vs last year")
                else:
                    lines.append(f"  Pages: {review.pages_vs_last_year:,} vs last year")

        return "\n".join(lines)

    def _book_to_summary(self, book: Book) -> BookSummary:
        """Convert a Book to BookSummary."""
        return BookSummary(
            title=book.title,
            author=book.author,
            rating=book.rating,
            page_count=book.page_count,
            date_finished=book.date_finished,
            tags=book.get_tags(),
        )

    def _calculate_max_streak(self, reading_dates: set[str]) -> int:
        """Calculate the longest reading streak from dates."""
        if not reading_dates:
            return 0

        # Convert to date objects and sort
        dates = sorted(date.fromisoformat(d) for d in reading_dates)

        max_streak = 1
        current_streak = 1

        for i in range(1, len(dates)):
            if (dates[i] - dates[i-1]).days == 1:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            elif (dates[i] - dates[i-1]).days > 1:
                current_streak = 1

        return max_streak
