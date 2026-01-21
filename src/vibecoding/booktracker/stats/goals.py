"""Reading goals tracking.

Supports yearly, monthly, and custom reading goals with progress tracking.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


class GoalType(str, Enum):
    """Type of reading goal."""

    BOOKS = "books"  # Number of books to read
    PAGES = "pages"  # Number of pages to read
    MINUTES = "minutes"  # Time spent reading


@dataclass
class ReadingGoal:
    """A reading goal."""

    goal_type: GoalType
    target: int
    year: int
    month: Optional[int] = None  # None = yearly goal
    current: int = 0
    created_at: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.target <= 0:
            return 0.0
        return min(100.0, round((self.current / self.target) * 100, 1))

    @property
    def remaining(self) -> int:
        """Calculate remaining to reach goal."""
        return max(0, self.target - self.current)

    @property
    def is_complete(self) -> bool:
        """Check if goal is complete."""
        return self.current >= self.target

    @property
    def period_label(self) -> str:
        """Get human-readable period label."""
        if self.month:
            import calendar
            return f"{calendar.month_name[self.month]} {self.year}"
        return str(self.year)

    def to_dict(self) -> dict:
        """Convert to dictionary for persistence."""
        return {
            "goal_type": self.goal_type.value,
            "target": self.target,
            "year": self.year,
            "month": self.month,
            "created_at": self.created_at or datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReadingGoal":
        """Create from dictionary."""
        return cls(
            goal_type=GoalType(data["goal_type"]),
            target=data["target"],
            year=data["year"],
            month=data.get("month"),
            created_at=data.get("created_at"),
        )


class GoalTracker:
    """Tracks and manages reading goals."""

    def __init__(
        self,
        db: Optional[Database] = None,
        goals_file: Optional[Path] = None,
    ):
        """Initialize goal tracker.

        Args:
            db: Database instance
            goals_file: Path to persist goals (default: ~/.booktracker_goals.json)
        """
        self.db = db or get_db()
        self.goals_file = goals_file or Path.home() / ".booktracker_goals.json"
        self._goals: list[ReadingGoal] = []
        self._load_goals()

    def _load_goals(self) -> None:
        """Load goals from file."""
        if self.goals_file.exists():
            try:
                with open(self.goals_file, "r") as f:
                    data = json.load(f)
                    self._goals = [ReadingGoal.from_dict(g) for g in data]
            except (json.JSONDecodeError, KeyError):
                self._goals = []

    def _save_goals(self) -> None:
        """Save goals to file."""
        with open(self.goals_file, "w") as f:
            json.dump([g.to_dict() for g in self._goals], f, indent=2)

    def set_goal(
        self,
        goal_type: GoalType,
        target: int,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> ReadingGoal:
        """Set a reading goal.

        Args:
            goal_type: Type of goal (books, pages, minutes)
            target: Target number
            year: Year for goal (default: current year)
            month: Month for goal (None = yearly goal)

        Returns:
            The created/updated goal
        """
        if year is None:
            year = date.today().year

        # Remove existing goal for same period/type
        self._goals = [
            g for g in self._goals
            if not (g.year == year and g.month == month and g.goal_type == goal_type)
        ]

        goal = ReadingGoal(
            goal_type=goal_type,
            target=target,
            year=year,
            month=month,
        )

        self._goals.append(goal)
        self._save_goals()

        # Calculate current progress
        self._update_goal_progress(goal)

        return goal

    def get_goal(
        self,
        goal_type: GoalType,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> Optional[ReadingGoal]:
        """Get a specific goal.

        Args:
            goal_type: Type of goal
            year: Year (default: current)
            month: Month (None = yearly)

        Returns:
            Goal if found, None otherwise
        """
        if year is None:
            year = date.today().year

        for goal in self._goals:
            if goal.year == year and goal.month == month and goal.goal_type == goal_type:
                self._update_goal_progress(goal)
                return goal
        return None

    def get_current_goals(self) -> list[ReadingGoal]:
        """Get all goals for current year/month.

        Returns:
            List of current goals with updated progress
        """
        today = date.today()
        current_goals = [
            g for g in self._goals
            if g.year == today.year and (g.month is None or g.month == today.month)
        ]

        for goal in current_goals:
            self._update_goal_progress(goal)

        return current_goals

    def get_all_goals(self) -> list[ReadingGoal]:
        """Get all goals.

        Returns:
            List of all goals with updated progress
        """
        for goal in self._goals:
            self._update_goal_progress(goal)
        return self._goals

    def delete_goal(
        self,
        goal_type: GoalType,
        year: int,
        month: Optional[int] = None,
    ) -> bool:
        """Delete a goal.

        Args:
            goal_type: Type of goal
            year: Year
            month: Month (None = yearly)

        Returns:
            True if deleted, False if not found
        """
        initial_count = len(self._goals)
        self._goals = [
            g for g in self._goals
            if not (g.year == year and g.month == month and g.goal_type == goal_type)
        ]

        if len(self._goals) < initial_count:
            self._save_goals()
            return True
        return False

    def _update_goal_progress(self, goal: ReadingGoal) -> None:
        """Update goal's current progress from database.

        Args:
            goal: Goal to update
        """
        with self.db.get_session() as session:
            # Determine date range
            if goal.month:
                start_date = f"{goal.year}-{goal.month:02d}-01"
                if goal.month == 12:
                    end_date = f"{goal.year + 1}-01-01"
                else:
                    end_date = f"{goal.year}-{goal.month + 1:02d}-01"
            else:
                start_date = f"{goal.year}-01-01"
                end_date = f"{goal.year + 1}-01-01"

            if goal.goal_type == GoalType.BOOKS:
                # Count books finished in period
                stmt = select(Book).where(
                    Book.date_finished >= start_date,
                    Book.date_finished < end_date,
                    Book.status == BookStatus.COMPLETED.value,
                )
                books = list(session.execute(stmt).scalars().all())
                goal.current = len(books)

            elif goal.goal_type == GoalType.PAGES:
                # Sum pages from reading logs
                stmt = select(ReadingLog).where(
                    ReadingLog.date >= start_date,
                    ReadingLog.date < end_date,
                )
                logs = list(session.execute(stmt).scalars().all())
                goal.current = sum(log.pages_read or 0 for log in logs)

            elif goal.goal_type == GoalType.MINUTES:
                # Sum reading time from logs
                stmt = select(ReadingLog).where(
                    ReadingLog.date >= start_date,
                    ReadingLog.date < end_date,
                )
                logs = list(session.execute(stmt).scalars().all())
                goal.current = sum(log.duration_minutes or 0 for log in logs)

    def get_progress_summary(self) -> dict:
        """Get a summary of all current goal progress.

        Returns:
            Dictionary with progress info for display
        """
        goals = self.get_current_goals()

        summary = {
            "goals": [],
            "on_track_count": 0,
            "behind_count": 0,
            "complete_count": 0,
        }

        today = date.today()
        day_of_year = today.timetuple().tm_yday
        days_in_year = 366 if today.year % 4 == 0 else 365

        for goal in goals:
            # Calculate expected progress
            if goal.month:
                import calendar
                days_in_month = calendar.monthrange(goal.year, goal.month)[1]
                expected_pct = (today.day / days_in_month) * 100
            else:
                expected_pct = (day_of_year / days_in_year) * 100

            actual_pct = goal.progress_percent
            is_on_track = actual_pct >= expected_pct * 0.9  # 10% buffer

            status = "complete" if goal.is_complete else ("on_track" if is_on_track else "behind")

            if goal.is_complete:
                summary["complete_count"] += 1
            elif is_on_track:
                summary["on_track_count"] += 1
            else:
                summary["behind_count"] += 1

            summary["goals"].append({
                "goal": goal,
                "expected_percent": round(expected_pct, 1),
                "actual_percent": actual_pct,
                "status": status,
                "is_on_track": is_on_track,
            })

        return summary

    def calculate_required_pace(self, goal: ReadingGoal) -> dict:
        """Calculate required pace to meet goal.

        Args:
            goal: Goal to analyze

        Returns:
            Dictionary with pace requirements
        """
        self._update_goal_progress(goal)

        today = date.today()

        # Calculate remaining days
        if goal.month:
            import calendar
            days_in_month = calendar.monthrange(goal.year, goal.month)[1]
            if goal.year == today.year and goal.month == today.month:
                remaining_days = days_in_month - today.day
            elif (goal.year, goal.month) > (today.year, today.month):
                remaining_days = days_in_month
            else:
                remaining_days = 0
        else:
            if goal.year == today.year:
                end_of_year = date(goal.year, 12, 31)
                remaining_days = (end_of_year - today).days
            elif goal.year > today.year:
                remaining_days = 365
            else:
                remaining_days = 0

        remaining = goal.remaining

        if remaining_days <= 0 or remaining <= 0:
            per_day = 0
            per_week = 0
        else:
            per_day = remaining / remaining_days
            per_week = per_day * 7

        unit = goal.goal_type.value
        if unit == "minutes":
            unit = "min"

        return {
            "remaining": remaining,
            "remaining_days": remaining_days,
            "per_day": round(per_day, 1),
            "per_week": round(per_week, 1),
            "unit": unit,
            "is_achievable": remaining_days > 0 and per_day < goal.target,
        }
