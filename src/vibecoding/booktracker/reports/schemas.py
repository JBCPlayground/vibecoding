"""Pydantic schemas for reports and data visualization."""

from datetime import date
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TimeFrame(str, Enum):
    """Time frame for reports."""

    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    ALL_TIME = "all_time"


# ============================================================================
# Heatmap Data
# ============================================================================


class HeatmapDay(BaseModel):
    """Data for a single day in the heatmap."""

    date: date
    books_read: int = 0
    pages_read: int = 0
    minutes_read: int = 0
    intensity: int = Field(ge=0, le=4)  # 0=none, 1=light, 2=medium, 3=high, 4=very high


class HeatmapWeek(BaseModel):
    """Data for a week in the heatmap."""

    week_number: int
    days: list[HeatmapDay]
    total_pages: int
    total_minutes: int


class HeatmapMonth(BaseModel):
    """Data for a month heatmap."""

    year: int
    month: int
    month_name: str
    weeks: list[HeatmapWeek]
    total_reading_days: int
    total_pages: int
    total_minutes: int
    books_completed: int


class HeatmapYear(BaseModel):
    """Full year heatmap data."""

    year: int
    months: list[HeatmapMonth]
    total_reading_days: int
    total_pages: int
    total_minutes: int
    books_completed: int
    longest_streak: int
    current_streak: int


# ============================================================================
# Chart Data
# ============================================================================


class ChartDataPoint(BaseModel):
    """A single data point for charts."""

    label: str
    value: float
    color: Optional[str] = None


class PieChartData(BaseModel):
    """Data for a pie chart."""

    title: str
    data: list[ChartDataPoint]
    total: float


class BarChartData(BaseModel):
    """Data for a bar chart."""

    title: str
    x_label: str
    y_label: str
    data: list[ChartDataPoint]


class LineChartPoint(BaseModel):
    """A point on a line chart."""

    x: str  # Date or label
    y: float


class LineChartData(BaseModel):
    """Data for a line chart."""

    title: str
    x_label: str
    y_label: str
    series: list[LineChartPoint]


class RatingDistribution(BaseModel):
    """Distribution of book ratings."""

    ratings: dict[int, int]  # rating -> count
    average: float
    total_rated: int
    mode: Optional[int]  # Most common rating


class GenreBreakdown(BaseModel):
    """Breakdown of books by genre."""

    genre: str
    count: int
    percentage: float
    average_rating: Optional[float]
    pages_read: int


class MonthlyProgress(BaseModel):
    """Monthly reading progress."""

    month: str  # "2024-01"
    month_name: str  # "January 2024"
    books_completed: int
    pages_read: int
    average_rating: Optional[float]


class AuthorStats(BaseModel):
    """Statistics for an author."""

    author: str
    books_read: int
    total_pages: int
    average_rating: Optional[float]
    favorite: bool  # Rating >= 4


# ============================================================================
# Yearly Recap
# ============================================================================


class BookHighlight(BaseModel):
    """A highlighted book for the recap."""

    book_id: UUID
    title: str
    author: Optional[str]
    rating: Optional[int]
    date_finished: Optional[date]
    pages: Optional[int]
    highlight_reason: str  # "Highest rated", "Longest", "First of year", etc.


class YearlyRecap(BaseModel):
    """Complete yearly reading recap."""

    year: int

    # Overall stats
    books_completed: int
    total_pages: int
    total_reading_minutes: int
    reading_days: int

    # Averages
    average_rating: Optional[float]
    average_pages_per_book: float
    average_books_per_month: float
    pages_per_day: float

    # Highlights
    highest_rated_books: list[BookHighlight]
    longest_book: Optional[BookHighlight]
    shortest_book: Optional[BookHighlight]
    first_book: Optional[BookHighlight]
    last_book: Optional[BookHighlight]

    # Breakdowns
    books_by_month: list[MonthlyProgress]
    top_genres: list[GenreBreakdown]
    top_authors: list[AuthorStats]
    rating_distribution: RatingDistribution

    # Streaks
    longest_streak: int
    current_streak: int
    total_streaks: int

    # Comparisons (if previous year data available)
    books_vs_last_year: Optional[int]  # +/- difference
    pages_vs_last_year: Optional[int]

    # Fun facts
    fun_facts: list[str]


# ============================================================================
# Dashboard Data
# ============================================================================


class ReadingGoalProgress(BaseModel):
    """Progress toward a reading goal."""

    goal_type: str  # "books", "pages", "minutes"
    target: int
    current: int
    percentage: float
    on_track: bool
    projected_completion: Optional[date]


class RecentActivity(BaseModel):
    """Recent reading activity item."""

    date: date
    activity_type: str  # "completed", "started", "logged"
    book_title: str
    book_author: Optional[str]
    details: Optional[str]  # "Finished in 3 days", "Read 50 pages"


class DashboardData(BaseModel):
    """Data for a reading dashboard."""

    # Current status
    currently_reading: int
    books_this_year: int
    pages_this_year: int
    current_streak: int

    # Goals
    goals: list[ReadingGoalProgress]

    # Recent activity
    recent_activity: list[RecentActivity]

    # Quick stats
    average_rating: Optional[float]
    books_per_month: float
    favorite_genre: Optional[str]
    favorite_author: Optional[str]

    # Mini charts data
    books_by_month_chart: BarChartData
    genre_pie_chart: PieChartData


# ============================================================================
# Export Formats
# ============================================================================


class ExportFormat(str, Enum):
    """Supported export formats."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"
    HTML = "html"


class ReportExport(BaseModel):
    """Exported report data."""

    title: str
    generated_at: str
    format: ExportFormat
    content: str  # The actual export content
