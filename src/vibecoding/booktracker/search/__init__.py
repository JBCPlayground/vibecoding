"""Advanced search module."""

from .manager import SearchManager
from .schemas import (
    AdvancedSearchQuery,
    BookSearchResult,
    NoteSearchResult,
    QuoteSearchResult,
    ResultType,
    ReviewSearchResult,
    SearchQuery,
    SearchResult,
    SearchResults,
    SearchScope,
    SearchSuggestion,
    SearchSuggestions,
    SortBy,
    SortOrder,
)

__all__ = [
    "SearchManager",
    "SearchQuery",
    "AdvancedSearchQuery",
    "SearchResult",
    "SearchResults",
    "SearchScope",
    "ResultType",
    "SortBy",
    "SortOrder",
    "BookSearchResult",
    "NoteSearchResult",
    "QuoteSearchResult",
    "ReviewSearchResult",
    "SearchSuggestion",
    "SearchSuggestions",
]
