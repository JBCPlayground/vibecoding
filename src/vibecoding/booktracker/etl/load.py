"""Load transformed books into SQLite database.

Handles bulk insertion with progress reporting and error handling.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from ..db.schemas import BookCreate
from ..db.sqlite import Database, get_db
from .dedupe import DuplicateMatch, deduplicate_books, DedupeResult
from .extract import extract_all
from .interactive import (
    ConflictResolution,
    resolve_conflict_interactive,
    show_dry_run_results,
    show_import_preview,
    show_import_results,
)
from .transform import transform_row


@dataclass
class ImportResult:
    """Result of an import operation."""

    imported: int = 0
    skipped: int = 0
    merged: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return self.imported + self.skipped + len(self.errors)


def load_books(
    books: list[BookCreate],
    db: Optional[Database] = None,
    show_progress: bool = True,
) -> ImportResult:
    """Load a list of books into the database.

    Args:
        books: List of BookCreate objects to import
        db: Database instance (uses global if not provided)
        show_progress: Show tqdm progress bar

    Returns:
        ImportResult with counts and errors
    """
    if db is None:
        db = get_db()

    result = ImportResult()
    iterator = tqdm(books, desc="Importing books", disable=not show_progress)

    for book in iterator:
        try:
            # Check for existing book by ISBN
            existing = None
            if book.isbn:
                existing = db.get_book_by_isbn(book.isbn)
            if not existing and book.isbn13:
                existing = db.get_book_by_isbn(book.isbn13)

            if existing:
                # Book already exists - skip
                result.skipped += 1
                continue

            # Create new book
            db.create_book(book)
            result.imported += 1

        except Exception as e:
            result.errors.append((book.title, str(e)))

    return result


def import_from_csv(
    notion_path: Optional[Path | str] = None,
    calibre_path: Optional[Path | str] = None,
    goodreads_path: Optional[Path | str] = None,
    db: Optional[Database] = None,
    dry_run: bool = False,
    interactive: bool = True,
    show_progress: bool = True,
    auto_merge_threshold: float = 0.95,
) -> ImportResult:
    """Import books from CSV files with full ETL pipeline.

    Args:
        notion_path: Path to Notion CSV export
        calibre_path: Path to Calibre CSV export
        goodreads_path: Path to Goodreads CSV export
        db: Database instance (uses global if not provided)
        dry_run: If True, don't actually import, just show what would happen
        interactive: If True, prompt for conflict resolution
        show_progress: Show progress bars
        auto_merge_threshold: Confidence threshold for auto-merging duplicates

    Returns:
        ImportResult with counts and errors
    """
    if db is None:
        db = get_db()

    result = ImportResult()
    transformed_books: list[BookCreate] = []
    transform_errors: list[tuple[str, str]] = []

    # Extract and transform
    print("\n[1/4] Extracting and transforming...")
    for extracted in extract_all(
        notion_path=notion_path,
        calibre_path=calibre_path,
        goodreads_path=goodreads_path,
        show_progress=show_progress,
    ):
        try:
            book = transform_row(extracted)
            transformed_books.append(book)
        except Exception as e:
            title = extracted.get("raw", {}).get("Title", "") or extracted.get(
                "raw", {}
            ).get("title", "Unknown")
            transform_errors.append((title, str(e)))

    if transform_errors:
        print(f"[yellow]Warning: {len(transform_errors)} transform errors[/yellow]")
        result.errors.extend(transform_errors)

    # Get existing books for deduplication
    print("\n[2/4] Checking for duplicates...")
    existing_books = [
        BookCreate(
            title=book.title,
            author=book.author,
            isbn=book.isbn,
            isbn13=book.isbn13,
            status=book.status,
            sources=[],
            source_ids={},
        )
        for book in db.get_all_books()
    ]

    # Deduplicate
    dedupe_result = deduplicate_books(
        transformed_books,
        existing_books=existing_books,
        auto_merge_threshold=auto_merge_threshold,
    )

    # Books to import
    books_to_import = dedupe_result.unique_books + dedupe_result.merged_books
    result.merged = len(dedupe_result.merged_books)

    # Dry run mode
    if dry_run:
        show_dry_run_results(
            books_to_import,
            dedupe_result.duplicates,
            dedupe_result.conflicts,
        )
        return result

    # Handle conflicts interactively
    if interactive and dedupe_result.conflicts:
        print(f"\n[3/4] Resolving {len(dedupe_result.conflicts)} conflicts...")
        for conflict in dedupe_result.conflicts:
            resolution, merged_book = resolve_conflict_interactive(conflict)

            if resolution == ConflictResolution.MERGE and merged_book:
                books_to_import.append(merged_book)
            elif resolution == ConflictResolution.KEEP_FIRST:
                books_to_import.append(conflict.book1)
            elif resolution == ConflictResolution.KEEP_SECOND:
                books_to_import.append(conflict.book2)
            elif resolution == ConflictResolution.KEEP_BOTH:
                books_to_import.append(conflict.book1)
                books_to_import.append(conflict.book2)
            else:  # SKIP
                result.skipped += 2
    else:
        # Non-interactive: auto-merge conflicts
        for conflict in dedupe_result.conflicts:
            # Default to merging
            from .dedupe import merge_book_records

            merged = merge_book_records([conflict.book1, conflict.book2])
            books_to_import.append(merged)

    # Show preview and confirm
    if interactive:
        if not show_import_preview(
            books_to_import,
            duplicates_count=len(dedupe_result.duplicates),
            conflicts_count=len(dedupe_result.conflicts),
        ):
            print("\n[yellow]Import cancelled by user[/yellow]")
            return result

    # Load into database
    print("\n[4/4] Importing to database...")
    load_result = load_books(books_to_import, db=db, show_progress=show_progress)

    result.imported = load_result.imported
    result.skipped += load_result.skipped
    result.errors.extend(load_result.errors)

    # Show results
    if interactive:
        show_import_results(result.imported, result.skipped, result.errors)

    return result


def import_notion(
    file_path: Path | str,
    db: Optional[Database] = None,
    dry_run: bool = False,
    interactive: bool = True,
) -> ImportResult:
    """Import books from Notion CSV export.

    Args:
        file_path: Path to Notion CSV file
        db: Database instance
        dry_run: Preview without importing
        interactive: Prompt for conflict resolution

    Returns:
        ImportResult
    """
    return import_from_csv(
        notion_path=file_path,
        db=db,
        dry_run=dry_run,
        interactive=interactive,
    )


def import_calibre(
    file_path: Path | str,
    db: Optional[Database] = None,
    dry_run: bool = False,
    interactive: bool = True,
) -> ImportResult:
    """Import books from Calibre CSV export.

    Args:
        file_path: Path to Calibre CSV file
        db: Database instance
        dry_run: Preview without importing
        interactive: Prompt for conflict resolution

    Returns:
        ImportResult
    """
    return import_from_csv(
        calibre_path=file_path,
        db=db,
        dry_run=dry_run,
        interactive=interactive,
    )


def import_goodreads(
    file_path: Path | str,
    db: Optional[Database] = None,
    dry_run: bool = False,
    interactive: bool = True,
) -> ImportResult:
    """Import books from Goodreads CSV export.

    Args:
        file_path: Path to Goodreads CSV file
        db: Database instance
        dry_run: Preview without importing
        interactive: Prompt for conflict resolution

    Returns:
        ImportResult
    """
    return import_from_csv(
        goodreads_path=file_path,
        db=db,
        dry_run=dry_run,
        interactive=interactive,
    )
