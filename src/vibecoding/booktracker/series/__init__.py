"""Book series management module."""

from .manager import SeriesManager
from .models import Series, SeriesBook
from .schemas import (
    SeriesCreate,
    SeriesUpdate,
    SeriesResponse,
    SeriesSummary,
    SeriesBookCreate,
    SeriesBookUpdate,
    SeriesBookResponse,
    SeriesBookWithDetails,
    SeriesWithBooks,
    SeriesStats,
    NextInSeries,
    SeriesStatus,
)

__all__ = [
    "SeriesManager",
    "Series",
    "SeriesBook",
    "SeriesCreate",
    "SeriesUpdate",
    "SeriesResponse",
    "SeriesSummary",
    "SeriesBookCreate",
    "SeriesBookUpdate",
    "SeriesBookResponse",
    "SeriesBookWithDetails",
    "SeriesWithBooks",
    "SeriesStats",
    "NextInSeries",
    "SeriesStatus",
]
