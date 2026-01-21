"""Reading notes and quotes module."""

from .manager import NotesManager
from .models import CollectionQuote, Note, Quote, QuoteCollection
from .schemas import (
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
    CollectionWithQuotes,
    HighlightColor,
    NoteCreate,
    NoteResponse,
    NoteSummary,
    NotesStats,
    NoteType,
    NoteUpdate,
    QuoteCreate,
    QuoteResponse,
    QuoteStats,
    QuoteSummary,
    QuoteType,
    QuoteUpdate,
)

__all__ = [
    "NotesManager",
    "Note",
    "Quote",
    "QuoteCollection",
    "CollectionQuote",
    "NoteCreate",
    "NoteUpdate",
    "NoteResponse",
    "NoteType",
    "QuoteCreate",
    "QuoteUpdate",
    "QuoteResponse",
    "QuoteType",
    "HighlightColor",
    "NoteSummary",
    "QuoteSummary",
    "NotesStats",
    "QuoteStats",
    "CollectionCreate",
    "CollectionUpdate",
    "CollectionResponse",
    "CollectionWithQuotes",
]
