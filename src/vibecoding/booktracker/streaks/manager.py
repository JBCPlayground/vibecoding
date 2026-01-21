"""Streak manager for reading streaks and habits operations."""

from collections import defaultdict
from datetime import datetime, timezone, date, timedelta
from typing import Optional

from sqlalchemy import select, func, and_

from ..db.sqlite import Database, get_db
from .models import ReadingStreak, DailyReading
from .schemas import (
    StreakStatus,
    DailyReadingCreate,
    StreakStats,
    ReadingHabits,
    WeekdayStats,
    HourlyStats,
    StreakMilestone,
    StreakCalendar,
)


# Milestone definitions
MILESTONES = [
    ("First Step", "Read for 1 day", 1),
    ("Getting Started", "Read for 3 consecutive days", 3),
    ("One Week", "Read for 7 consecutive days", 7),
    ("Two Weeks", "Read for 14 consecutive days", 14),
    ("Monthly Reader", "Read for 30 consecutive days", 30),
    ("Dedicated Reader", "Read for 60 consecutive days", 60),
    ("Bookworm", "Read for 90 consecutive days", 90),
    ("Reading Master", "Read for 180 consecutive days", 180),
    ("Year of Reading", "Read for 365 consecutive days", 365),
]


class StreakManager:
    """Manages reading streaks and habit tracking."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize streak manager.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    # -------------------------------------------------------------------------
    # Daily Reading Management
    # -------------------------------------------------------------------------

    def log_reading(
        self,
        reading_date: Optional[date] = None,
        minutes: int = 0,
        pages: int = 0,
        sessions: int = 1,
        books_read: int = 0,
        books_completed: int = 0,
        primary_hour: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> DailyReading:
        """Log reading activity for a day.

        Args:
            reading_date: Date of reading (default: today)
            minutes: Minutes read
            pages: Pages read
            sessions: Number of reading sessions
            books_read: Number of books touched
            books_completed: Number of books completed
            primary_hour: Primary reading hour (0-23)
            notes: Optional notes

        Returns:
            Updated or created DailyReading
        """
        if reading_date is None:
            reading_date = date.today()

        with self.db.get_session() as session:
            # Check if entry exists
            stmt = select(DailyReading).where(
                DailyReading.reading_date == reading_date.isoformat()
            )
            daily = session.execute(stmt).scalar_one_or_none()

            if daily:
                # Update existing entry
                daily.minutes_read += minutes
                daily.pages_read += pages
                daily.sessions_count += sessions
                daily.books_read = max(daily.books_read, books_read)
                daily.books_completed += books_completed
                if primary_hour is not None:
                    daily.primary_hour = primary_hour
                if notes:
                    daily.notes = (daily.notes or "") + "\n" + notes if daily.notes else notes

                # Check goal
                if daily.goal_minutes and daily.minutes_read >= daily.goal_minutes:
                    daily.goal_met = True
                elif daily.goal_pages and daily.pages_read >= daily.goal_pages:
                    daily.goal_met = True

                daily.updated_at = datetime.now(timezone.utc).isoformat()
            else:
                # Create new entry
                daily = DailyReading(
                    reading_date=reading_date.isoformat(),
                    minutes_read=minutes,
                    pages_read=pages,
                    sessions_count=sessions,
                    books_read=books_read,
                    books_completed=books_completed,
                    primary_hour=primary_hour,
                    weekday=reading_date.weekday(),
                    notes=notes,
                )
                session.add(daily)

            session.commit()
            session.refresh(daily)
            session.expunge(daily)

            # Update streak
            self._update_streak(reading_date)

            return daily

    def get_daily_reading(self, reading_date: date) -> Optional[DailyReading]:
        """Get daily reading for a specific date.

        Args:
            reading_date: Date to get reading for

        Returns:
            DailyReading or None
        """
        with self.db.get_session() as session:
            stmt = select(DailyReading).where(
                DailyReading.reading_date == reading_date.isoformat()
            )
            daily = session.execute(stmt).scalar_one_or_none()
            if daily:
                session.expunge(daily)
            return daily

    def get_reading_history(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 30,
    ) -> list[DailyReading]:
        """Get reading history.

        Args:
            start_date: Start of range
            end_date: End of range
            limit: Maximum entries to return

        Returns:
            List of DailyReading entries
        """
        with self.db.get_session() as session:
            stmt = select(DailyReading)

            if start_date:
                stmt = stmt.where(DailyReading.reading_date >= start_date.isoformat())
            if end_date:
                stmt = stmt.where(DailyReading.reading_date <= end_date.isoformat())

            stmt = stmt.order_by(DailyReading.reading_date.desc()).limit(limit)

            readings = session.execute(stmt).scalars().all()
            for reading in readings:
                session.expunge(reading)
            return list(readings)

    def set_daily_goal(
        self,
        goal_minutes: Optional[int] = None,
        goal_pages: Optional[int] = None,
        reading_date: Optional[date] = None,
    ) -> DailyReading:
        """Set daily reading goal.

        Args:
            goal_minutes: Minutes goal
            goal_pages: Pages goal
            reading_date: Date (default: today)

        Returns:
            Updated DailyReading
        """
        if reading_date is None:
            reading_date = date.today()

        with self.db.get_session() as session:
            stmt = select(DailyReading).where(
                DailyReading.reading_date == reading_date.isoformat()
            )
            daily = session.execute(stmt).scalar_one_or_none()

            if not daily:
                daily = DailyReading(
                    reading_date=reading_date.isoformat(),
                    weekday=reading_date.weekday(),
                )
                session.add(daily)

            daily.goal_minutes = goal_minutes
            daily.goal_pages = goal_pages

            # Check if goal is already met
            minutes = daily.minutes_read or 0
            pages = daily.pages_read or 0
            if goal_minutes and minutes >= goal_minutes:
                daily.goal_met = True
            elif goal_pages and pages >= goal_pages:
                daily.goal_met = True

            session.commit()
            session.refresh(daily)
            session.expunge(daily)

            return daily

    # -------------------------------------------------------------------------
    # Streak Management
    # -------------------------------------------------------------------------

    def _update_streak(self, reading_date: date) -> None:
        """Update streak after logging reading.

        Args:
            reading_date: Date reading was logged
        """
        with self.db.get_session() as session:
            # Get current active streak
            stmt = select(ReadingStreak).where(ReadingStreak.is_current == True)  # noqa: E712
            current = session.execute(stmt).scalar_one_or_none()

            if current:
                start = date.fromisoformat(current.start_date)
                # Check if reading_date extends the streak
                expected_next = start + timedelta(days=current.length)

                if reading_date == expected_next:
                    # Extends streak
                    current.length += 1
                    daily = self.get_daily_reading(reading_date)
                    if daily:
                        current.total_minutes += daily.minutes_read
                        current.total_pages += daily.pages_read
                        current.books_completed += daily.books_completed
                elif reading_date > expected_next:
                    # Gap - end current streak
                    current.is_current = False
                    current.end_date = (expected_next - timedelta(days=1)).isoformat()

                    # Start new streak
                    daily = self.get_daily_reading(reading_date)
                    new_streak = ReadingStreak(
                        start_date=reading_date.isoformat(),
                        length=1,
                        is_current=True,
                        total_minutes=daily.minutes_read if daily else 0,
                        total_pages=daily.pages_read if daily else 0,
                        books_completed=daily.books_completed if daily else 0,
                    )
                    session.add(new_streak)
                # If reading_date < expected_next, it's a past day being filled in
                # Just update the totals if within streak range
                elif reading_date >= start:
                    daily = self.get_daily_reading(reading_date)
                    if daily:
                        current.total_minutes += daily.minutes_read
                        current.total_pages += daily.pages_read
                        current.books_completed += daily.books_completed
            else:
                # No current streak - start new one
                daily = self.get_daily_reading(reading_date)
                new_streak = ReadingStreak(
                    start_date=reading_date.isoformat(),
                    length=1,
                    is_current=True,
                    total_minutes=daily.minutes_read if daily else 0,
                    total_pages=daily.pages_read if daily else 0,
                    books_completed=daily.books_completed if daily else 0,
                )
                session.add(new_streak)

            session.commit()

    def get_current_streak(self) -> Optional[ReadingStreak]:
        """Get current active streak.

        Returns:
            Current ReadingStreak or None
        """
        with self.db.get_session() as session:
            stmt = select(ReadingStreak).where(ReadingStreak.is_current == True)  # noqa: E712
            streak = session.execute(stmt).scalar_one_or_none()
            if streak:
                session.expunge(streak)
            return streak

    def get_longest_streak(self) -> Optional[ReadingStreak]:
        """Get longest streak ever.

        Returns:
            Longest ReadingStreak or None
        """
        with self.db.get_session() as session:
            stmt = select(ReadingStreak).order_by(ReadingStreak.length.desc()).limit(1)
            streak = session.execute(stmt).scalar_one_or_none()
            if streak:
                session.expunge(streak)
            return streak

    def get_all_streaks(self, limit: int = 10) -> list[ReadingStreak]:
        """Get all streaks, ordered by length.

        Args:
            limit: Maximum streaks to return

        Returns:
            List of ReadingStreak
        """
        with self.db.get_session() as session:
            stmt = (
                select(ReadingStreak)
                .order_by(ReadingStreak.length.desc())
                .limit(limit)
            )
            streaks = session.execute(stmt).scalars().all()
            for streak in streaks:
                session.expunge(streak)
            return list(streaks)

    def get_streak_status(self) -> StreakStatus:
        """Get current streak status.

        Returns:
            StreakStatus indicating current state
        """
        current = self.get_current_streak()
        if not current:
            return StreakStatus.ENDED

        # Check if we've read today
        today = date.today()
        today_reading = self.get_daily_reading(today)

        if today_reading and today_reading.minutes_read > 0:
            return StreakStatus.ACTIVE

        # Check if streak is still valid (read yesterday)
        start = date.fromisoformat(current.start_date)
        expected_days = (today - start).days + 1

        if current.length >= expected_days - 1:
            return StreakStatus.AT_RISK  # Haven't read today yet

        return StreakStatus.ENDED

    def check_and_end_streak(self) -> bool:
        """Check if current streak should end and end it if needed.

        Returns:
            True if streak was ended
        """
        current = self.get_current_streak()
        if not current:
            return False

        today = date.today()
        yesterday = today - timedelta(days=1)

        # Check if we read yesterday
        yesterday_reading = self.get_daily_reading(yesterday)

        if not yesterday_reading or yesterday_reading.minutes_read == 0:
            # Streak broken - check when last reading was
            start = date.fromisoformat(current.start_date)
            last_day = start + timedelta(days=current.length - 1)

            if last_day < yesterday:
                with self.db.get_session() as session:
                    stmt = select(ReadingStreak).where(ReadingStreak.id == current.id)
                    streak = session.execute(stmt).scalar_one_or_none()
                    if streak:
                        streak.is_current = False
                        streak.end_date = last_day.isoformat()
                        session.commit()
                return True

        return False

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_stats(self) -> StreakStats:
        """Get overall streak statistics.

        Returns:
            StreakStats with all stats
        """
        with self.db.get_session() as session:
            # Count streaks
            total_streaks = session.execute(
                select(func.count()).select_from(ReadingStreak)
            ).scalar() or 0

            # Total reading days
            total_reading_days = session.execute(
                select(func.count()).select_from(DailyReading)
            ).scalar() or 0

            # Average streak length
            avg_streak = session.execute(
                select(func.avg(ReadingStreak.length))
            ).scalar() or 0

            # Average daily stats
            avg_minutes = session.execute(
                select(func.avg(DailyReading.minutes_read))
            ).scalar() or 0

            avg_pages = session.execute(
                select(func.avg(DailyReading.pages_read))
            ).scalar() or 0

            # Best day
            best_day = session.execute(
                select(DailyReading)
                .order_by(DailyReading.minutes_read.desc())
                .limit(1)
            ).scalar_one_or_none()

            # Extract best day values within session
            best_day_minutes = best_day.minutes_read if best_day else 0
            best_day_pages = best_day.pages_read if best_day else 0
            best_day_date = (
                date.fromisoformat(best_day.reading_date) if best_day else None
            )

        current = self.get_current_streak()
        longest = self.get_longest_streak()
        status = self.get_streak_status()

        return StreakStats(
            current_streak=current.length if current else 0,
            longest_streak=longest.length if longest else 0,
            total_streaks=total_streaks,
            total_reading_days=total_reading_days,
            streak_status=status,
            current_streak_start=(
                date.fromisoformat(current.start_date) if current else None
            ),
            current_streak_minutes=current.total_minutes if current else 0,
            current_streak_pages=current.total_pages if current else 0,
            current_streak_books=current.books_completed if current else 0,
            average_streak_length=round(avg_streak, 1),
            average_daily_minutes=round(avg_minutes, 1),
            average_daily_pages=round(avg_pages, 1),
            best_day_minutes=best_day_minutes,
            best_day_pages=best_day_pages,
            best_day_date=best_day_date,
        )

    # -------------------------------------------------------------------------
    # Habit Analysis
    # -------------------------------------------------------------------------

    def get_reading_habits(self) -> ReadingHabits:
        """Analyze reading habits.

        Returns:
            ReadingHabits with analysis
        """
        readings = self.get_reading_history(limit=365)

        # Weekday analysis
        weekday_data = defaultdict(lambda: {"days": 0, "minutes": 0, "pages": 0})
        hourly_data = defaultdict(int)

        for reading in readings:
            wd = reading.weekday
            weekday_data[wd]["days"] += 1
            weekday_data[wd]["minutes"] += reading.minutes_read
            weekday_data[wd]["pages"] += reading.pages_read

            if reading.primary_hour is not None:
                hourly_data[reading.primary_hour] += 1

        # Build weekday stats
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                         "Friday", "Saturday", "Sunday"]
        weekday_stats = []
        best_weekday = None
        best_weekday_avg = 0
        worst_weekday = None
        worst_weekday_avg = float("inf")

        for wd in range(7):
            data = weekday_data[wd]
            days = data["days"]
            if days > 0:
                avg_min = data["minutes"] / days
                avg_pages = data["pages"] / days

                if avg_min > best_weekday_avg:
                    best_weekday_avg = avg_min
                    best_weekday = weekday_names[wd]
                if avg_min < worst_weekday_avg:
                    worst_weekday_avg = avg_min
                    worst_weekday = weekday_names[wd]

                weekday_stats.append(WeekdayStats(
                    weekday=wd,
                    weekday_name=weekday_names[wd],
                    total_days=days,
                    total_minutes=data["minutes"],
                    total_pages=data["pages"],
                    average_minutes=round(avg_min, 1),
                    average_pages=round(avg_pages, 1),
                    reading_frequency=round(days / max(len(readings) / 7, 1) * 100, 1),
                ))
            else:
                weekday_stats.append(WeekdayStats(
                    weekday=wd,
                    weekday_name=weekday_names[wd],
                    total_days=0,
                    total_minutes=0,
                    total_pages=0,
                    average_minutes=0,
                    average_pages=0,
                    reading_frequency=0,
                ))

        # Build hourly stats
        total_sessions = sum(hourly_data.values()) or 1
        hourly_stats = []
        best_hour = None
        best_hour_count = 0

        for hour in range(24):
            count = hourly_data[hour]
            if count > best_hour_count:
                best_hour_count = count
                best_hour = hour
            if count > 0:
                hourly_stats.append(HourlyStats(
                    hour=hour,
                    sessions_count=count,
                    percentage=round(count / total_sessions * 100, 1),
                ))

        # Calculate consistency
        today = date.today()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        week_readings = [r for r in readings
                        if date.fromisoformat(r.reading_date) >= week_ago]
        month_readings = [r for r in readings
                         if date.fromisoformat(r.reading_date) >= month_ago]

        # Consistency score (percentage of days with reading in last 30 days)
        consistency = len(month_readings) / 30 * 100 if readings else 0

        # Trends (compare last 2 weeks)
        two_weeks_ago = today - timedelta(days=14)
        recent = [r for r in readings if date.fromisoformat(r.reading_date) >= week_ago]
        older = [r for r in readings
                 if week_ago > date.fromisoformat(r.reading_date) >= two_weeks_ago]

        recent_avg = sum(r.minutes_read for r in recent) / max(len(recent), 1)
        older_avg = sum(r.minutes_read for r in older) / max(len(older), 1)

        if recent_avg > older_avg * 1.1:
            minutes_trend = "increasing"
        elif recent_avg < older_avg * 0.9:
            minutes_trend = "decreasing"
        else:
            minutes_trend = "stable"

        recent_pages = sum(r.pages_read for r in recent) / max(len(recent), 1)
        older_pages = sum(r.pages_read for r in older) / max(len(older), 1)

        if recent_pages > older_pages * 1.1:
            pages_trend = "increasing"
        elif recent_pages < older_pages * 0.9:
            pages_trend = "decreasing"
        else:
            pages_trend = "stable"

        return ReadingHabits(
            most_productive_weekday=best_weekday,
            most_productive_hour=best_hour,
            least_productive_weekday=worst_weekday,
            weekday_stats=weekday_stats,
            hourly_distribution=hourly_stats,
            reading_days_this_week=len(week_readings),
            reading_days_this_month=len(month_readings),
            consistency_score=round(consistency, 1),
            minutes_trend=minutes_trend,
            pages_trend=pages_trend,
        )

    def get_milestones(self) -> list[StreakMilestone]:
        """Get milestone achievements.

        Returns:
            List of milestones with achievement status
        """
        longest = self.get_longest_streak()
        max_length = longest.length if longest else 0

        milestones = []
        for name, desc, days in MILESTONES:
            achieved = max_length >= days

            # Find achievement date
            achieved_date = None
            if achieved:
                with self.db.get_session() as session:
                    stmt = select(ReadingStreak).where(
                        ReadingStreak.length >= days
                    ).order_by(ReadingStreak.start_date).limit(1)
                    streak = session.execute(stmt).scalar_one_or_none()
                    if streak:
                        start = date.fromisoformat(streak.start_date)
                        achieved_date = start + timedelta(days=days - 1)

            milestones.append(StreakMilestone(
                name=name,
                description=desc,
                days_required=days,
                achieved=achieved,
                achieved_date=achieved_date,
            ))

        return milestones

    def get_calendar(self, year: int, month: int) -> StreakCalendar:
        """Get calendar view of reading activity.

        Args:
            year: Year
            month: Month (1-12)

        Returns:
            StreakCalendar with activity data
        """
        from calendar import monthrange

        _, days_in_month = monthrange(year, month)

        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)

        readings = self.get_reading_history(
            start_date=start_date,
            end_date=end_date,
            limit=31,
        )

        reading_dict = {
            date.fromisoformat(r.reading_date).day: r
            for r in readings
        }

        days = {}
        streak_days = {}
        total_minutes = 0
        total_pages = 0

        for day in range(1, days_in_month + 1):
            has_reading = day in reading_dict
            days[day] = has_reading

            if has_reading:
                reading = reading_dict[day]
                total_minutes += reading.minutes_read
                total_pages += reading.pages_read

            # Calculate streak length at this day
            if has_reading:
                streak_count = 1
                check_date = date(year, month, day) - timedelta(days=1)
                while True:
                    prev_reading = self.get_daily_reading(check_date)
                    if prev_reading and prev_reading.minutes_read > 0:
                        streak_count += 1
                        check_date -= timedelta(days=1)
                    else:
                        break
                streak_days[day] = streak_count
            else:
                streak_days[day] = 0

        return StreakCalendar(
            year=year,
            month=month,
            days=days,
            streak_days=streak_days,
            total_reading_days=len(reading_dict),
            total_minutes=total_minutes,
            total_pages=total_pages,
        )
