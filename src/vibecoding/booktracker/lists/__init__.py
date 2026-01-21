"""Reading lists and recommendations module."""

from .manager import ReadingListManager
from .models import ReadingList, ReadingListBook
from .schemas import (
    ReadingListCreate,
    ReadingListUpdate,
    ReadingListResponse,
    ReadingListSummary,
    ListBookCreate,
    ListBookResponse,
    ListBookWithDetails,
    ReadingListWithBooks,
    ListType,
    AutoListType,
    BookRecommendation,
    RecommendationReason,
    RecommendationSet,
    SimilarBook,
    GenreRecommendations,
    AuthorRecommendations,
    RecommendationStats,
)

__all__ = [
    "ReadingListManager",
    "ReadingList",
    "ReadingListBook",
    "ReadingListCreate",
    "ReadingListUpdate",
    "ReadingListResponse",
    "ReadingListSummary",
    "ListBookCreate",
    "ListBookResponse",
    "ListBookWithDetails",
    "ReadingListWithBooks",
    "ListType",
    "AutoListType",
    "BookRecommendation",
    "RecommendationReason",
    "RecommendationSet",
    "SimilarBook",
    "GenreRecommendations",
    "AuthorRecommendations",
    "RecommendationStats",
]
