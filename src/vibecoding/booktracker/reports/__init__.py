"""Reports module for data visualization and analytics."""

from vibecoding.booktracker.reports.manager import ReportManager
from vibecoding.booktracker.reports.schemas import (
    AuthorStats,
    BarChartData,
    BookHighlight,
    ChartDataPoint,
    DashboardData,
    ExportFormat,
    GenreBreakdown,
    HeatmapDay,
    HeatmapMonth,
    HeatmapWeek,
    HeatmapYear,
    LineChartData,
    LineChartPoint,
    MonthlyProgress,
    PieChartData,
    RatingDistribution,
    ReadingGoalProgress,
    RecentActivity,
    ReportExport,
    TimeFrame,
    YearlyRecap,
)

__all__ = [
    # Manager
    "ReportManager",
    # Enums
    "TimeFrame",
    "ExportFormat",
    # Heatmap schemas
    "HeatmapDay",
    "HeatmapWeek",
    "HeatmapMonth",
    "HeatmapYear",
    # Chart schemas
    "ChartDataPoint",
    "PieChartData",
    "BarChartData",
    "LineChartPoint",
    "LineChartData",
    # Stats schemas
    "RatingDistribution",
    "GenreBreakdown",
    "MonthlyProgress",
    "AuthorStats",
    # Recap schemas
    "BookHighlight",
    "YearlyRecap",
    # Dashboard schemas
    "ReadingGoalProgress",
    "RecentActivity",
    "DashboardData",
    # Export
    "ReportExport",
]
