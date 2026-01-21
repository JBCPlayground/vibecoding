"""ETL module for importing book data from multiple sources.

This module handles extraction, transformation, and loading of book data
from Notion CSV, Calibre CSV, and Goodreads CSV exports.
"""

from .extract import (
    extract_notion_csv,
    extract_calibre_csv,
    extract_goodreads_csv,
    extract_all,
    ExtractionError,
)
from .transform import (
    transform_notion_row,
    transform_calibre_row,
    transform_goodreads_row,
    transform_row,
    TransformError,
)
from .dedupe import (
    find_duplicates,
    merge_book_records,
    deduplicate_books,
    DuplicateMatch,
    DedupeResult,
    MatchType,
)
from .load import (
    load_books,
    import_from_csv,
    import_notion,
    import_calibre,
    import_goodreads,
    ImportResult,
)
from .interactive import (
    resolve_conflict_interactive,
    show_import_preview,
    show_import_results,
    show_book_comparison,
    show_dry_run_results,
    ConflictResolution,
)

__all__ = [
    # Extract
    "extract_notion_csv",
    "extract_calibre_csv",
    "extract_goodreads_csv",
    "extract_all",
    "ExtractionError",
    # Transform
    "transform_notion_row",
    "transform_calibre_row",
    "transform_goodreads_row",
    "transform_row",
    "TransformError",
    # Dedupe
    "find_duplicates",
    "merge_book_records",
    "deduplicate_books",
    "DuplicateMatch",
    "DedupeResult",
    "MatchType",
    # Load
    "load_books",
    "import_from_csv",
    "import_notion",
    "import_calibre",
    "import_goodreads",
    "ImportResult",
    # Interactive
    "resolve_conflict_interactive",
    "show_import_preview",
    "show_import_results",
    "show_book_comparison",
    "show_dry_run_results",
    "ConflictResolution",
]
