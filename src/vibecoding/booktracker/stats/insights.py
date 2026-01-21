"""Reading insights and trend analysis.

Generates personalized insights based on reading patterns and habits.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional

from sqlalchemy import select

from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


class InsightType(str, Enum):
    """Type of reading insight."""

    ACHIEVEMENT = "achievement"  # Milestone reached
    TREND = "trend"  # Pattern identified
    RECOMMENDATION = "recommendation"  # Suggested action
    STREAK = "streak"  # Streak-related
    COMPARISON = "comparison"  # vs previous period
    MILESTONE = "milestone"  # Approaching milestone


@dataclass
class Insight:
    """A reading insight."""

    insight_type: InsightType
    title: str
    message: str
    priority: int = 5  # 1-10, higher = more important
    data: dict = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class InsightGenerator:
    """Generates personalized reading insights."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize insight generator.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def generate_all_insights(self) -> list[Insight]:
        """Generate all relevant insights.

        Returns:
            List of insights sorted by priority
        """
        insights = []

        # Gather various insights
        insights.extend(self._check_streaks())
        insights.extend(self._check_milestones())
        insights.extend(self._check_pace_trends())
        insights.extend(self._check_genre_patterns())
        insights.extend(self._check_achievements())
        insights.extend(self._compare_to_previous())

        # Sort by priority (highest first)
        insights.sort(key=lambda x: x.priority, reverse=True)

        return insights

    def _check_streaks(self) -> list[Insight]:
        """Check for streak-related insights."""
        insights = []

        with self.db.get_session() as session:
            # Get recent reading logs
            thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()
            stmt = select(ReadingLog).where(ReadingLog.date >= thirty_days_ago)
            logs = list(session.execute(stmt).scalars().all())

            if not logs:
                insights.append(Insight(
                    insight_type=InsightType.RECOMMENDATION,
                    title="Start Reading",
                    message="No reading activity in the past 30 days. Time to pick up a book!",
                    priority=8,
                ))
                return insights

            # Calculate current streak
            reading_dates = sorted(set(log.date for log in logs), reverse=True)
            current_streak = 0
            expected_date = date.today()

            for log_date in reading_dates:
                log_date_obj = date.fromisoformat(log_date)
                if log_date_obj == expected_date:
                    current_streak += 1
                    expected_date = expected_date - timedelta(days=1)
                elif log_date_obj == expected_date - timedelta(days=1):
                    # Allow one day gap
                    expected_date = log_date_obj
                    current_streak += 1
                    expected_date = expected_date - timedelta(days=1)
                else:
                    break

            if current_streak >= 7:
                insights.append(Insight(
                    insight_type=InsightType.STREAK,
                    title="Reading Streak!",
                    message=f"You're on a {current_streak}-day reading streak! Keep it up!",
                    priority=7,
                    data={"streak_days": current_streak},
                ))
            elif current_streak >= 3:
                insights.append(Insight(
                    insight_type=InsightType.STREAK,
                    title="Building Momentum",
                    message=f"{current_streak} days in a row! A few more days and you'll hit a week!",
                    priority=5,
                    data={"streak_days": current_streak},
                ))

            # Check if streak is at risk
            if current_streak > 0:
                today_str = date.today().isoformat()
                read_today = any(log.date == today_str for log in logs)
                if not read_today:
                    insights.append(Insight(
                        insight_type=InsightType.RECOMMENDATION,
                        title="Keep Your Streak",
                        message=f"Read today to maintain your {current_streak}-day streak!",
                        priority=9,
                        data={"streak_days": current_streak},
                    ))

        return insights

    def _check_milestones(self) -> list[Insight]:
        """Check for upcoming milestones."""
        insights = []

        with self.db.get_session() as session:
            # Count completed books
            stmt = select(Book).where(Book.status == BookStatus.COMPLETED.value)
            completed = list(session.execute(stmt).scalars().all())
            book_count = len(completed)

            # Check proximity to round numbers
            milestones = [10, 25, 50, 75, 100, 150, 200, 250, 500, 1000]
            for milestone in milestones:
                remaining = milestone - book_count
                if 0 < remaining <= 3:
                    insights.append(Insight(
                        insight_type=InsightType.MILESTONE,
                        title=f"Almost at {milestone} Books!",
                        message=f"You've read {book_count} books. Just {remaining} more to reach {milestone}!",
                        priority=6,
                        data={"current": book_count, "target": milestone},
                    ))
                    break
                elif remaining == 0:
                    insights.append(Insight(
                        insight_type=InsightType.ACHIEVEMENT,
                        title=f"{milestone} Books Read!",
                        message=f"Congratulations! You've read {milestone} books!",
                        priority=10,
                        data={"milestone": milestone},
                    ))
                    break

            # Check total pages milestone
            total_pages = sum(b.page_count or 0 for b in completed)
            page_milestones = [1000, 5000, 10000, 25000, 50000, 100000]
            for milestone in page_milestones:
                remaining = milestone - total_pages
                if 0 < remaining <= 500:
                    insights.append(Insight(
                        insight_type=InsightType.MILESTONE,
                        title=f"Almost {milestone:,} Pages!",
                        message=f"You've read {total_pages:,} pages. Just {remaining:,} more!",
                        priority=5,
                        data={"current": total_pages, "target": milestone},
                    ))
                    break

        return insights

    def _check_pace_trends(self) -> list[Insight]:
        """Check reading pace trends."""
        insights = []

        with self.db.get_session() as session:
            today = date.today()

            # Get this month's activity
            month_start = date(today.year, today.month, 1).isoformat()
            stmt = select(ReadingLog).where(ReadingLog.date >= month_start)
            this_month_logs = list(session.execute(stmt).scalars().all())

            # Get last month's activity
            if today.month == 1:
                last_month_start = date(today.year - 1, 12, 1)
                last_month_end = date(today.year - 1, 12, 31)
            else:
                last_month_start = date(today.year, today.month - 1, 1)
                if today.month == 2:
                    last_month_end = date(today.year, today.month - 1, 28)
                else:
                    last_month_end = date(today.year, today.month - 1, 30)

            stmt = select(ReadingLog).where(
                ReadingLog.date >= last_month_start.isoformat(),
                ReadingLog.date <= last_month_end.isoformat(),
            )
            last_month_logs = list(session.execute(stmt).scalars().all())

            if this_month_logs and last_month_logs:
                this_month_pages = sum(log.pages_read or 0 for log in this_month_logs)
                last_month_pages = sum(log.pages_read or 0 for log in last_month_logs)

                # Normalize by days elapsed
                days_this_month = today.day
                this_month_rate = this_month_pages / days_this_month if days_this_month > 0 else 0
                last_month_rate = last_month_pages / 30  # approximate

                if this_month_rate > last_month_rate * 1.2:
                    insights.append(Insight(
                        insight_type=InsightType.TREND,
                        title="Reading More!",
                        message=f"You're reading {round(this_month_rate, 1)} pages/day, up from {round(last_month_rate, 1)} last month!",
                        priority=6,
                        data={
                            "current_rate": round(this_month_rate, 1),
                            "previous_rate": round(last_month_rate, 1),
                        },
                    ))
                elif this_month_rate < last_month_rate * 0.8 and last_month_rate > 0:
                    insights.append(Insight(
                        insight_type=InsightType.TREND,
                        title="Reading Less",
                        message=f"Your pace is down to {round(this_month_rate, 1)} pages/day from {round(last_month_rate, 1)} last month.",
                        priority=4,
                        data={
                            "current_rate": round(this_month_rate, 1),
                            "previous_rate": round(last_month_rate, 1),
                        },
                    ))

        return insights

    def _check_genre_patterns(self) -> list[Insight]:
        """Check genre/reading pattern insights."""
        insights = []

        with self.db.get_session() as session:
            # Get recent completed books
            three_months_ago = (date.today() - timedelta(days=90)).isoformat()
            stmt = select(Book).where(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= three_months_ago,
            )
            recent_books = list(session.execute(stmt).scalars().all())

            if len(recent_books) >= 3:
                # Check for author patterns
                from collections import Counter
                authors = Counter(book.author for book in recent_books)
                top_author, count = authors.most_common(1)[0]
                if count >= 3:
                    insights.append(Insight(
                        insight_type=InsightType.TREND,
                        title=f"Fan of {top_author}!",
                        message=f"You've read {count} books by {top_author} recently.",
                        priority=4,
                        data={"author": top_author, "count": count},
                    ))

                # Check for genre patterns
                genre_counts = Counter()
                for book in recent_books:
                    tags = book.get_tags()
                    genre_counts.update(tags)

                if genre_counts:
                    top_genre, count = genre_counts.most_common(1)[0]
                    if count >= 3:
                        insights.append(Insight(
                            insight_type=InsightType.TREND,
                            title=f"Loving {top_genre}",
                            message=f"You've read {count} {top_genre} books recently. Try mixing it up?",
                            priority=3,
                            data={"genre": top_genre, "count": count},
                        ))

        return insights

    def _check_achievements(self) -> list[Insight]:
        """Check for recent achievements."""
        insights = []

        with self.db.get_session() as session:
            today = date.today()

            # Books finished this year
            year_start = f"{today.year}-01-01"
            stmt = select(Book).where(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= year_start,
            )
            year_books = list(session.execute(stmt).scalars().all())

            if year_books:
                # Check for year milestones
                count = len(year_books)
                if count == 12:
                    insights.append(Insight(
                        insight_type=InsightType.ACHIEVEMENT,
                        title="Book a Month!",
                        message="You've read 12 books this year - that's a book a month!",
                        priority=8,
                        data={"books_this_year": count},
                    ))
                elif count == 52:
                    insights.append(Insight(
                        insight_type=InsightType.ACHIEVEMENT,
                        title="Book a Week!",
                        message="Amazing! You've read 52 books this year - one per week!",
                        priority=10,
                        data={"books_this_year": count},
                    ))

                # Check for longest book
                longest = max(year_books, key=lambda b: b.page_count or 0)
                if longest.page_count and longest.page_count >= 500:
                    insights.append(Insight(
                        insight_type=InsightType.ACHIEVEMENT,
                        title="Long Read Complete",
                        message=f"You finished '{longest.title}' ({longest.page_count} pages) this year!",
                        priority=5,
                        data={"book": longest.title, "pages": longest.page_count},
                    ))

        return insights

    def _compare_to_previous(self) -> list[Insight]:
        """Compare current year to previous year."""
        insights = []

        with self.db.get_session() as session:
            today = date.today()

            # This year's books (up to today's date)
            year_start = f"{today.year}-01-01"
            today_str = today.isoformat()
            stmt = select(Book).where(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= year_start,
                Book.date_finished <= today_str,
            )
            this_year = list(session.execute(stmt).scalars().all())

            # Last year's books (same period)
            last_year_start = f"{today.year - 1}-01-01"
            last_year_same_date = f"{today.year - 1}-{today.month:02d}-{today.day:02d}"
            stmt = select(Book).where(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= last_year_start,
                Book.date_finished <= last_year_same_date,
            )
            last_year = list(session.execute(stmt).scalars().all())

            if last_year:
                this_count = len(this_year)
                last_count = len(last_year)

                if this_count > last_count:
                    diff = this_count - last_count
                    insights.append(Insight(
                        insight_type=InsightType.COMPARISON,
                        title="Ahead of Last Year!",
                        message=f"You've read {this_count} books, {diff} more than this time last year!",
                        priority=6,
                        data={
                            "this_year": this_count,
                            "last_year": last_count,
                            "difference": diff,
                        },
                    ))
                elif this_count < last_count:
                    diff = last_count - this_count
                    insights.append(Insight(
                        insight_type=InsightType.COMPARISON,
                        title="Behind Last Year",
                        message=f"You've read {this_count} books, {diff} fewer than this time last year.",
                        priority=4,
                        data={
                            "this_year": this_count,
                            "last_year": last_count,
                            "difference": -diff,
                        },
                    ))

        return insights

    def get_dashboard_insights(self, limit: int = 5) -> list[Insight]:
        """Get top insights for dashboard display.

        Args:
            limit: Maximum number of insights to return

        Returns:
            List of top priority insights
        """
        all_insights = self.generate_all_insights()
        return all_insights[:limit]

    def get_insights_by_type(self, insight_type: InsightType) -> list[Insight]:
        """Get insights of a specific type.

        Args:
            insight_type: Type of insights to get

        Returns:
            List of matching insights
        """
        all_insights = self.generate_all_insights()
        return [i for i in all_insights if i.insight_type == insight_type]
