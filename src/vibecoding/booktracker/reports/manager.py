"""Manager for reports and data visualization."""

import calendar
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import func, extract

from ..db.sqlite import Database
from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from .schemas import (
    TimeFrame,
    HeatmapDay,
    HeatmapWeek,
    HeatmapMonth,
    HeatmapYear,
    ChartDataPoint,
    PieChartData,
    BarChartData,
    LineChartData,
    LineChartPoint,
    RatingDistribution,
    GenreBreakdown,
    MonthlyProgress,
    AuthorStats,
    BookHighlight,
    YearlyRecap,
    ReadingGoalProgress,
    RecentActivity,
    DashboardData,
    ExportFormat,
    ReportExport,
)


class ReportManager:
    """Manager for generating reports and visualization data."""

    def __init__(self, db: Database):
        """Initialize the report manager.

        Args:
            db: Database instance
        """
        self.db = db

    # ========================================================================
    # Heatmap Generation
    # ========================================================================

    def get_year_heatmap(self, year: int) -> HeatmapYear:
        """Generate a year heatmap of reading activity.

        Args:
            year: Year to generate heatmap for

        Returns:
            Year heatmap data
        """
        with self.db.get_session() as session:
            # Get all reading logs for the year
            start_date = f"{year}-01-01"
            end_date = f"{year}-12-31"

            logs = session.query(ReadingLog).filter(
                ReadingLog.date >= start_date,
                ReadingLog.date <= end_date,
            ).all()

            # Get completed books for the year
            completed = session.query(Book).filter(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= start_date,
                Book.date_finished <= end_date,
            ).all()

            # Aggregate by date
            daily_data = defaultdict(lambda: {"pages": 0, "minutes": 0})
            for log in logs:
                daily_data[log.date]["pages"] += log.pages_read or 0
                daily_data[log.date]["minutes"] += log.duration_minutes or 0

            # Count books finished per date
            books_by_date = Counter()
            for book in completed:
                if book.date_finished:
                    books_by_date[book.date_finished] += 1

            # Build months
            months = []
            total_reading_days = 0
            total_pages = 0
            total_minutes = 0

            for month in range(1, 13):
                month_data = self._build_month_heatmap(
                    year, month, daily_data, books_by_date
                )
                months.append(month_data)
                total_reading_days += month_data.total_reading_days
                total_pages += month_data.total_pages
                total_minutes += month_data.total_minutes

            # Get streak info
            longest_streak, current_streak = self._calculate_streaks(daily_data, year)

            return HeatmapYear(
                year=year,
                months=months,
                total_reading_days=total_reading_days,
                total_pages=total_pages,
                total_minutes=total_minutes,
                books_completed=len(completed),
                longest_streak=longest_streak,
                current_streak=current_streak,
            )

    def get_month_heatmap(self, year: int, month: int) -> HeatmapMonth:
        """Generate a month heatmap.

        Args:
            year: Year
            month: Month (1-12)

        Returns:
            Month heatmap data
        """
        with self.db.get_session() as session:
            start_date = f"{year}-{month:02d}-01"
            _, last_day = calendar.monthrange(year, month)
            end_date = f"{year}-{month:02d}-{last_day:02d}"

            logs = session.query(ReadingLog).filter(
                ReadingLog.date >= start_date,
                ReadingLog.date <= end_date,
            ).all()

            completed = session.query(Book).filter(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= start_date,
                Book.date_finished <= end_date,
            ).all()

            daily_data = defaultdict(lambda: {"pages": 0, "minutes": 0})
            for log in logs:
                daily_data[log.date]["pages"] += log.pages_read or 0
                daily_data[log.date]["minutes"] += log.duration_minutes or 0

            books_by_date = Counter()
            for book in completed:
                if book.date_finished:
                    books_by_date[book.date_finished] += 1

            return self._build_month_heatmap(year, month, daily_data, books_by_date)

    def _build_month_heatmap(
        self,
        year: int,
        month: int,
        daily_data: dict,
        books_by_date: Counter,
    ) -> HeatmapMonth:
        """Build heatmap data for a month."""
        _, last_day = calendar.monthrange(year, month)
        month_name = calendar.month_name[month]

        # Calculate max values for intensity scaling
        max_pages = max((d["pages"] for d in daily_data.values()), default=1) or 1

        weeks = []
        current_week_days = []
        week_number = 1
        total_reading_days = 0
        total_pages = 0
        total_minutes = 0
        books_completed = 0

        for day in range(1, last_day + 1):
            day_date = date(year, month, day)
            date_str = day_date.isoformat()
            data = daily_data.get(date_str, {"pages": 0, "minutes": 0})

            pages = data["pages"]
            minutes = data["minutes"]
            books = books_by_date.get(date_str, 0)

            # Calculate intensity (0-4)
            if pages == 0 and minutes == 0:
                intensity = 0
            elif pages < max_pages * 0.25:
                intensity = 1
            elif pages < max_pages * 0.5:
                intensity = 2
            elif pages < max_pages * 0.75:
                intensity = 3
            else:
                intensity = 4

            heatmap_day = HeatmapDay(
                date=day_date,
                books_read=books,
                pages_read=pages,
                minutes_read=minutes,
                intensity=intensity,
            )

            current_week_days.append(heatmap_day)

            if pages > 0 or minutes > 0:
                total_reading_days += 1
            total_pages += pages
            total_minutes += minutes
            books_completed += books

            # Check if end of week (Sunday) or end of month
            if day_date.weekday() == 6 or day == last_day:
                week_pages = sum(d.pages_read for d in current_week_days)
                week_minutes = sum(d.minutes_read for d in current_week_days)

                weeks.append(HeatmapWeek(
                    week_number=week_number,
                    days=current_week_days,
                    total_pages=week_pages,
                    total_minutes=week_minutes,
                ))
                current_week_days = []
                week_number += 1

        return HeatmapMonth(
            year=year,
            month=month,
            month_name=month_name,
            weeks=weeks,
            total_reading_days=total_reading_days,
            total_pages=total_pages,
            total_minutes=total_minutes,
            books_completed=books_completed,
        )

    def _calculate_streaks(self, daily_data: dict, year: int) -> tuple[int, int]:
        """Calculate longest and current streak for a year."""
        dates = sorted([
            date.fromisoformat(d) for d in daily_data.keys()
            if d.startswith(str(year))
        ])

        if not dates:
            return 0, 0

        longest = 1
        current = 1
        streak = 1

        for i in range(1, len(dates)):
            if (dates[i] - dates[i-1]).days == 1:
                streak += 1
                longest = max(longest, streak)
            else:
                streak = 1

        # Check if current streak extends to today
        today = date.today()
        if dates and (today - dates[-1]).days <= 1:
            current = streak
        else:
            current = 0

        return longest, current

    # ========================================================================
    # Chart Data Generation
    # ========================================================================

    def get_genre_chart(self, year: Optional[int] = None) -> PieChartData:
        """Generate genre distribution pie chart data.

        Args:
            year: Optional year filter

        Returns:
            Pie chart data for genres
        """
        with self.db.get_session() as session:
            query = session.query(Book).filter(
                Book.status == BookStatus.COMPLETED.value,
                Book.genres.isnot(None),
            )

            if year:
                query = query.filter(
                    Book.date_finished >= f"{year}-01-01",
                    Book.date_finished <= f"{year}-12-31",
                )

            books = query.all()

            genre_counts = Counter()
            for book in books:
                for genre in book.get_genres():
                    genre_counts[genre] += 1

            total = sum(genre_counts.values())
            colors = ["#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0", "#9966FF",
                      "#FF9F40", "#FF6384", "#C9CBCF"]

            data = []
            for i, (genre, count) in enumerate(genre_counts.most_common(8)):
                data.append(ChartDataPoint(
                    label=genre,
                    value=count,
                    color=colors[i % len(colors)],
                ))

            return PieChartData(
                title="Books by Genre",
                data=data,
                total=total,
            )

    def get_rating_chart(self, year: Optional[int] = None) -> BarChartData:
        """Generate rating distribution bar chart data.

        Args:
            year: Optional year filter

        Returns:
            Bar chart data for ratings
        """
        with self.db.get_session() as session:
            query = session.query(Book).filter(
                Book.status == BookStatus.COMPLETED.value,
                Book.rating.isnot(None),
            )

            if year:
                query = query.filter(
                    Book.date_finished >= f"{year}-01-01",
                    Book.date_finished <= f"{year}-12-31",
                )

            books = query.all()

            rating_counts = Counter(book.rating for book in books)

            data = []
            for rating in range(1, 6):
                data.append(ChartDataPoint(
                    label=f"{rating} star{'s' if rating > 1 else ''}",
                    value=rating_counts.get(rating, 0),
                ))

            return BarChartData(
                title="Rating Distribution",
                x_label="Rating",
                y_label="Number of Books",
                data=data,
            )

    def get_monthly_progress_chart(self, year: int) -> LineChartData:
        """Generate monthly reading progress line chart.

        Args:
            year: Year to chart

        Returns:
            Line chart data for monthly progress
        """
        with self.db.get_session() as session:
            books = session.query(Book).filter(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= f"{year}-01-01",
                Book.date_finished <= f"{year}-12-31",
            ).all()

            monthly = defaultdict(int)
            for book in books:
                if book.date_finished:
                    month = date.fromisoformat(book.date_finished).month
                    monthly[month] += 1

            series = []
            for month in range(1, 13):
                series.append(LineChartPoint(
                    x=calendar.month_abbr[month],
                    y=monthly.get(month, 0),
                ))

            return LineChartData(
                title=f"Books Read in {year}",
                x_label="Month",
                y_label="Books Completed",
                series=series,
            )

    def get_pages_over_time_chart(self, year: int) -> LineChartData:
        """Generate cumulative pages over time chart.

        Args:
            year: Year to chart

        Returns:
            Line chart data for cumulative pages
        """
        with self.db.get_session() as session:
            logs = session.query(ReadingLog).filter(
                ReadingLog.date >= f"{year}-01-01",
                ReadingLog.date <= f"{year}-12-31",
            ).order_by(ReadingLog.date).all()

            # Aggregate by month
            monthly_pages = defaultdict(int)
            for log in logs:
                if log.date:
                    month = date.fromisoformat(log.date).month
                    monthly_pages[month] += log.pages_read or 0

            # Create cumulative series
            cumulative = 0
            series = []
            for month in range(1, 13):
                cumulative += monthly_pages.get(month, 0)
                series.append(LineChartPoint(
                    x=calendar.month_abbr[month],
                    y=cumulative,
                ))

            return LineChartData(
                title=f"Cumulative Pages Read in {year}",
                x_label="Month",
                y_label="Total Pages",
                series=series,
            )

    # ========================================================================
    # Yearly Recap
    # ========================================================================

    def get_yearly_recap(self, year: int) -> YearlyRecap:
        """Generate a complete yearly reading recap.

        Args:
            year: Year to recap

        Returns:
            Complete yearly recap data
        """
        with self.db.get_session() as session:
            # Get completed books
            completed = session.query(Book).filter(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= f"{year}-01-01",
                Book.date_finished <= f"{year}-12-31",
            ).all()

            # Get reading logs
            logs = session.query(ReadingLog).filter(
                ReadingLog.date >= f"{year}-01-01",
                ReadingLog.date <= f"{year}-12-31",
            ).all()

            # Basic stats
            books_completed = len(completed)
            total_pages = sum(book.page_count or 0 for book in completed)
            total_minutes = sum(log.duration_minutes or 0 for log in logs)
            reading_days = len(set(log.date for log in logs))

            # Averages
            rated_books = [b for b in completed if b.rating]
            average_rating = (
                sum(b.rating for b in rated_books) / len(rated_books)
                if rated_books else None
            )
            average_pages = total_pages / books_completed if books_completed else 0
            average_per_month = books_completed / 12
            pages_per_day = total_pages / 365

            # Highlights
            highest_rated = self._get_highest_rated_books(completed, 5)
            longest = self._get_extreme_book(completed, "longest")
            shortest = self._get_extreme_book(completed, "shortest")
            first = self._get_extreme_book(completed, "first")
            last = self._get_extreme_book(completed, "last")

            # Monthly breakdown
            books_by_month = self._get_monthly_breakdown(completed, year)

            # Genre breakdown
            top_genres = self._get_genre_breakdown(completed)

            # Author stats
            top_authors = self._get_author_stats(completed)

            # Rating distribution
            rating_dist = self._get_rating_distribution(completed)

            # Streaks
            daily_data = defaultdict(lambda: {"pages": 0, "minutes": 0})
            for log in logs:
                daily_data[log.date]["pages"] += log.pages_read or 0
            longest_streak, current_streak = self._calculate_streaks(daily_data, year)

            # Previous year comparison
            prev_year = year - 1
            prev_completed = session.query(Book).filter(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= f"{prev_year}-01-01",
                Book.date_finished <= f"{prev_year}-12-31",
            ).all()

            books_vs_last = None
            pages_vs_last = None
            if prev_completed:
                books_vs_last = books_completed - len(prev_completed)
                prev_pages = sum(b.page_count or 0 for b in prev_completed)
                pages_vs_last = total_pages - prev_pages

            # Fun facts
            fun_facts = self._generate_fun_facts(
                completed, books_completed, total_pages, reading_days,
                longest_streak, top_genres, top_authors
            )

            return YearlyRecap(
                year=year,
                books_completed=books_completed,
                total_pages=total_pages,
                total_reading_minutes=total_minutes,
                reading_days=reading_days,
                average_rating=average_rating,
                average_pages_per_book=average_pages,
                average_books_per_month=average_per_month,
                pages_per_day=pages_per_day,
                highest_rated_books=highest_rated,
                longest_book=longest,
                shortest_book=shortest,
                first_book=first,
                last_book=last,
                books_by_month=books_by_month,
                top_genres=top_genres,
                top_authors=top_authors,
                rating_distribution=rating_dist,
                longest_streak=longest_streak,
                current_streak=current_streak,
                total_streaks=0,  # Would need more tracking
                books_vs_last_year=books_vs_last,
                pages_vs_last_year=pages_vs_last,
                fun_facts=fun_facts,
            )

    def _get_highest_rated_books(
        self, books: list[Book], limit: int
    ) -> list[BookHighlight]:
        """Get highest rated books."""
        rated = sorted(
            [b for b in books if b.rating],
            key=lambda x: (x.rating, x.page_count or 0),
            reverse=True,
        )[:limit]

        return [
            BookHighlight(
                book_id=UUID(b.id),
                title=b.title,
                author=b.author,
                rating=b.rating,
                date_finished=date.fromisoformat(b.date_finished) if b.date_finished else None,
                pages=b.page_count,
                highlight_reason=f"Rated {b.rating}/5",
            )
            for b in rated
        ]

    def _get_extreme_book(
        self, books: list[Book], extreme: str
    ) -> Optional[BookHighlight]:
        """Get extreme book (longest, shortest, first, last)."""
        if not books:
            return None

        if extreme == "longest":
            book = max(
                [b for b in books if b.page_count],
                key=lambda x: x.page_count,
                default=None,
            )
            reason = f"Longest at {book.page_count} pages" if book else ""
        elif extreme == "shortest":
            book = min(
                [b for b in books if b.page_count],
                key=lambda x: x.page_count,
                default=None,
            )
            reason = f"Shortest at {book.page_count} pages" if book else ""
        elif extreme == "first":
            book = min(
                [b for b in books if b.date_finished],
                key=lambda x: x.date_finished,
                default=None,
            )
            reason = "First book of the year"
        elif extreme == "last":
            book = max(
                [b for b in books if b.date_finished],
                key=lambda x: x.date_finished,
                default=None,
            )
            reason = "Last book of the year"
        else:
            return None

        if not book:
            return None

        return BookHighlight(
            book_id=UUID(book.id),
            title=book.title,
            author=book.author,
            rating=book.rating,
            date_finished=date.fromisoformat(book.date_finished) if book.date_finished else None,
            pages=book.page_count,
            highlight_reason=reason,
        )

    def _get_monthly_breakdown(
        self, books: list[Book], year: int
    ) -> list[MonthlyProgress]:
        """Get monthly reading breakdown."""
        monthly = defaultdict(lambda: {"count": 0, "pages": 0, "ratings": []})

        for book in books:
            if book.date_finished:
                month = date.fromisoformat(book.date_finished).month
                monthly[month]["count"] += 1
                monthly[month]["pages"] += book.page_count or 0
                if book.rating:
                    monthly[month]["ratings"].append(book.rating)

        result = []
        for month in range(1, 13):
            data = monthly[month]
            avg_rating = None
            if data["ratings"]:
                avg_rating = sum(data["ratings"]) / len(data["ratings"])

            result.append(MonthlyProgress(
                month=f"{year}-{month:02d}",
                month_name=f"{calendar.month_name[month]} {year}",
                books_completed=data["count"],
                pages_read=data["pages"],
                average_rating=avg_rating,
            ))

        return result

    def _get_genre_breakdown(self, books: list[Book]) -> list[GenreBreakdown]:
        """Get genre breakdown from books."""
        genre_data = defaultdict(lambda: {"count": 0, "pages": 0, "ratings": []})

        for book in books:
            if book.genres:
                for genre in book.get_genres():
                    genre_data[genre]["count"] += 1
                    genre_data[genre]["pages"] += book.page_count or 0
                    if book.rating:
                        genre_data[genre]["ratings"].append(book.rating)

        total = sum(d["count"] for d in genre_data.values())

        result = []
        for genre, data in sorted(
            genre_data.items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )[:10]:
            avg_rating = None
            if data["ratings"]:
                avg_rating = sum(data["ratings"]) / len(data["ratings"])

            result.append(GenreBreakdown(
                genre=genre,
                count=data["count"],
                percentage=data["count"] / total * 100 if total else 0,
                average_rating=avg_rating,
                pages_read=data["pages"],
            ))

        return result

    def _get_author_stats(self, books: list[Book]) -> list[AuthorStats]:
        """Get author statistics."""
        author_data = defaultdict(lambda: {"count": 0, "pages": 0, "ratings": []})

        for book in books:
            if book.author:
                author_data[book.author]["count"] += 1
                author_data[book.author]["pages"] += book.page_count or 0
                if book.rating:
                    author_data[book.author]["ratings"].append(book.rating)

        result = []
        for author, data in sorted(
            author_data.items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )[:10]:
            avg_rating = None
            if data["ratings"]:
                avg_rating = sum(data["ratings"]) / len(data["ratings"])

            result.append(AuthorStats(
                author=author,
                books_read=data["count"],
                total_pages=data["pages"],
                average_rating=avg_rating,
                favorite=avg_rating is not None and avg_rating >= 4,
            ))

        return result

    def _get_rating_distribution(self, books: list[Book]) -> RatingDistribution:
        """Get rating distribution."""
        ratings = Counter(book.rating for book in books if book.rating)

        total = sum(ratings.values())
        average = 0.0
        if total:
            average = sum(r * c for r, c in ratings.items()) / total

        mode = None
        if ratings:
            mode = ratings.most_common(1)[0][0]

        return RatingDistribution(
            ratings=dict(ratings),
            average=average,
            total_rated=total,
            mode=mode,
        )

    def _generate_fun_facts(
        self,
        books: list[Book],
        total_books: int,
        total_pages: int,
        reading_days: int,
        longest_streak: int,
        genres: list[GenreBreakdown],
        authors: list[AuthorStats],
    ) -> list[str]:
        """Generate fun facts about the year."""
        facts = []

        if total_pages > 0:
            # Pages facts
            facts.append(f"You read {total_pages:,} pages - that's about {total_pages // 250} average-length novels!")

            # Hours estimate (assuming 250 words per page, 250 words per minute)
            hours = total_pages * 250 / 250 / 60
            facts.append(f"Estimated reading time: {hours:.0f} hours")

        if total_books > 0:
            facts.append(f"You finished a book every {365 // total_books:.0f} days on average")

        if reading_days > 0:
            facts.append(f"You read on {reading_days} days this year ({reading_days / 365 * 100:.0f}% of days)")

        if longest_streak > 7:
            facts.append(f"Your longest reading streak was {longest_streak} days!")

        if genres and len(genres) > 0:
            top_genre = genres[0]
            facts.append(f"Your favorite genre was {top_genre.genre} ({top_genre.count} books)")

        if authors and len(authors) > 0 and authors[0].books_read > 1:
            top_author = authors[0]
            facts.append(f"You read {top_author.books_read} books by {top_author.author}")

        return facts

    # ========================================================================
    # Dashboard Data
    # ========================================================================

    def get_dashboard(self, year: Optional[int] = None) -> DashboardData:
        """Generate dashboard data.

        Args:
            year: Year for stats (defaults to current year)

        Returns:
            Dashboard data
        """
        if year is None:
            year = date.today().year

        with self.db.get_session() as session:
            # Currently reading
            currently_reading = session.query(Book).filter(
                Book.status == BookStatus.READING.value,
            ).count()

            # Books this year
            books_this_year = session.query(Book).filter(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= f"{year}-01-01",
            ).count()

            # Pages this year
            completed = session.query(Book).filter(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= f"{year}-01-01",
            ).all()
            pages_this_year = sum(b.page_count or 0 for b in completed)

            # Current streak
            logs = session.query(ReadingLog).filter(
                ReadingLog.date >= f"{year}-01-01",
            ).all()
            daily_data = defaultdict(lambda: {"pages": 0})
            for log in logs:
                daily_data[log.date]["pages"] += log.pages_read or 0
            _, current_streak = self._calculate_streaks(daily_data, year)

            # Average rating
            rated = [b for b in completed if b.rating]
            avg_rating = sum(b.rating for b in rated) / len(rated) if rated else None

            # Books per month
            today = date.today()
            months_elapsed = today.month if today.year == year else 12
            books_per_month = books_this_year / months_elapsed if months_elapsed else 0

            # Favorite genre and author
            genre_counts = Counter()
            author_ratings = defaultdict(list)
            for book in completed:
                if book.genres:
                    for g in book.get_genres():
                        genre_counts[g] += 1
                if book.author and book.rating:
                    author_ratings[book.author].append(book.rating)

            fav_genre = genre_counts.most_common(1)[0][0] if genre_counts else None
            fav_author = None
            if author_ratings:
                fav_author = max(
                    author_ratings.keys(),
                    key=lambda a: sum(author_ratings[a]) / len(author_ratings[a])
                    if author_ratings[a] else 0
                )

            # Recent activity (last 10)
            recent = session.query(Book).filter(
                Book.date_finished.isnot(None),
            ).order_by(Book.date_finished.desc()).limit(10).all()

            recent_activity = [
                RecentActivity(
                    date=date.fromisoformat(b.date_finished),
                    activity_type="completed",
                    book_title=b.title,
                    book_author=b.author,
                    details=f"Rated {b.rating}/5" if b.rating else None,
                )
                for b in recent if b.date_finished
            ]

            # Charts
            books_chart = self.get_monthly_progress_chart(year)
            genre_chart = self.get_genre_chart(year)

            return DashboardData(
                currently_reading=currently_reading,
                books_this_year=books_this_year,
                pages_this_year=pages_this_year,
                current_streak=current_streak,
                goals=[],  # Would need goals module
                recent_activity=recent_activity,
                average_rating=avg_rating,
                books_per_month=books_per_month,
                favorite_genre=fav_genre,
                favorite_author=fav_author,
                books_by_month_chart=BarChartData(
                    title=books_chart.title,
                    x_label=books_chart.x_label,
                    y_label=books_chart.y_label,
                    data=[ChartDataPoint(label=p.x, value=p.y) for p in books_chart.series],
                ),
                genre_pie_chart=genre_chart,
            )

    # ========================================================================
    # Export
    # ========================================================================

    def export_recap(
        self, year: int, format: ExportFormat = ExportFormat.MARKDOWN
    ) -> ReportExport:
        """Export yearly recap in specified format.

        Args:
            year: Year to export
            format: Export format

        Returns:
            Exported report
        """
        recap = self.get_yearly_recap(year)
        generated_at = datetime.now().isoformat()

        if format == ExportFormat.JSON:
            content = recap.model_dump_json(indent=2)
        elif format == ExportFormat.MARKDOWN:
            content = self._recap_to_markdown(recap)
        elif format == ExportFormat.CSV:
            content = self._recap_to_csv(recap)
        else:
            content = self._recap_to_markdown(recap)

        return ReportExport(
            title=f"Reading Recap {year}",
            generated_at=generated_at,
            format=format,
            content=content,
        )

    def _recap_to_markdown(self, recap: YearlyRecap) -> str:
        """Convert recap to markdown."""
        lines = [
            f"# Reading Recap {recap.year}",
            "",
            "## Overview",
            f"- **Books Completed:** {recap.books_completed}",
            f"- **Total Pages:** {recap.total_pages:,}",
            f"- **Reading Days:** {recap.reading_days}",
            f"- **Average Rating:** {recap.average_rating:.1f}/5" if recap.average_rating else "- **Average Rating:** N/A",
            "",
            "## Monthly Breakdown",
            "| Month | Books | Pages |",
            "|-------|-------|-------|",
        ]

        for month in recap.books_by_month:
            lines.append(f"| {month.month_name.split()[0]} | {month.books_completed} | {month.pages_read:,} |")

        lines.extend([
            "",
            "## Top Genres",
        ])
        for genre in recap.top_genres[:5]:
            lines.append(f"- {genre.genre}: {genre.count} books ({genre.percentage:.0f}%)")

        lines.extend([
            "",
            "## Top Authors",
        ])
        for author in recap.top_authors[:5]:
            lines.append(f"- {author.author}: {author.books_read} books")

        if recap.highest_rated_books:
            lines.extend([
                "",
                "## Highest Rated Books",
            ])
            for book in recap.highest_rated_books:
                lines.append(f"- **{book.title}** by {book.author or 'Unknown'} - {book.rating}/5")

        if recap.fun_facts:
            lines.extend([
                "",
                "## Fun Facts",
            ])
            for fact in recap.fun_facts:
                lines.append(f"- {fact}")

        return "\n".join(lines)

    def _recap_to_csv(self, recap: YearlyRecap) -> str:
        """Convert recap monthly data to CSV."""
        lines = ["Month,Books Completed,Pages Read,Average Rating"]

        for month in recap.books_by_month:
            rating = f"{month.average_rating:.1f}" if month.average_rating else ""
            lines.append(f"{month.month_name},{month.books_completed},{month.pages_read},{rating}")

        return "\n".join(lines)
