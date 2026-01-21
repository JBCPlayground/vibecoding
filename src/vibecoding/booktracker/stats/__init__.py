"""Reading statistics and analytics."""

from .analytics import (
    ReadingAnalytics,
    YearlyStats,
    MonthlyStats,
    AuthorStats,
    GenreStats,
)
from .goals import (
    ReadingGoal,
    GoalTracker,
    GoalType,
)
from .insights import (
    InsightGenerator,
    Insight,
    InsightType,
)

__all__ = [
    "ReadingAnalytics",
    "YearlyStats",
    "MonthlyStats",
    "AuthorStats",
    "GenreStats",
    "ReadingGoal",
    "GoalTracker",
    "GoalType",
    "InsightGenerator",
    "Insight",
    "InsightType",
]
