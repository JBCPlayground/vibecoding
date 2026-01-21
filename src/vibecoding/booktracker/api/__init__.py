"""API module for external book metadata services.

Provides clients for book metadata lookup from various sources.
"""

from .openlibrary import (
    OpenLibraryClient,
    OpenLibraryError,
    OpenLibraryRateLimitError,
    BookResult,
)

__all__ = [
    "OpenLibraryClient",
    "OpenLibraryError",
    "OpenLibraryRateLimitError",
    "BookResult",
]
