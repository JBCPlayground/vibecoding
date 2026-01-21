"""Base importer functionality.

Provides common infrastructure for all book importers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..db.models import Book
from ..db.schemas import BookCreate, BookStatus
from ..db.sqlite import Database, get_db


class ImportError(Exception):
    """Import-specific error."""

    pass


class DuplicateHandling(str, Enum):
    """How to handle duplicate books."""

    SKIP = "skip"  # Skip duplicates
    UPDATE = "update"  # Update existing with import data
    REPLACE = "replace"  # Replace existing entirely
    CREATE_NEW = "create_new"  # Create new entry anyway


@dataclass
class ImportRecord:
    """A single record from import source."""

    title: str
    author: str
    isbn: Optional[str] = None
    isbn13: Optional[str] = None
    status: Optional[BookStatus] = None
    rating: Optional[int] = None
    page_count: Optional[int] = None
    date_added: Optional[str] = None
    date_started: Optional[str] = None
    date_finished: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    comments: Optional[str] = None
    publisher: Optional[str] = None
    publication_year: Optional[int] = None
    series: Optional[str] = None
    series_index: Optional[float] = None
    cover_url: Optional[str] = None
    description: Optional[str] = None

    # Source-specific fields
    source: Optional[str] = None
    source_id: Optional[str] = None
    raw_data: dict = field(default_factory=dict)

    def to_book_create(self) -> BookCreate:
        """Convert to BookCreate schema."""
        return BookCreate(
            title=self.title,
            author=self.author,
            isbn=self.isbn,
            isbn13=self.isbn13,
            status=self.status or BookStatus.WISHLIST,
            rating=self.rating,
            page_count=self.page_count,
            date_added=self.date_added,
            date_started=self.date_started,
            date_finished=self.date_finished,
            tags=self.tags,
            comments=self.comments,
            publisher=self.publisher,
            publication_year=self.publication_year,
            series=self.series,
            series_index=self.series_index,
            cover=self.cover_url,
            description=self.description,
        )


@dataclass
class ImportResult:
    """Result of an import operation."""

    success: bool
    source_file: Optional[Path] = None
    source_type: Optional[str] = None
    total_records: int = 0
    imported: int = 0
    skipped: int = 0
    updated: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    imported_books: list[Book] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Get summary string."""
        return (
            f"Imported: {self.imported}, "
            f"Skipped: {self.skipped}, "
            f"Updated: {self.updated}, "
            f"Errors: {self.errors}"
        )


class BaseImporter(ABC):
    """Base class for all book importers."""

    source_name: str = "unknown"

    def __init__(self, db: Optional[Database] = None):
        """Initialize importer.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    @abstractmethod
    def parse_file(self, file_path: Path) -> list[ImportRecord]:
        """Parse source file into import records.

        Args:
            file_path: Path to source file

        Returns:
            List of ImportRecord objects
        """
        pass

    @abstractmethod
    def validate_file(self, file_path: Path) -> tuple[bool, Optional[str]]:
        """Validate that file is correct format for this importer.

        Args:
            file_path: Path to file

        Returns:
            Tuple of (is_valid, error_message)
        """
        pass

    def import_file(
        self,
        file_path: Path,
        duplicate_handling: DuplicateHandling = DuplicateHandling.SKIP,
        dry_run: bool = False,
    ) -> ImportResult:
        """Import books from file.

        Args:
            file_path: Path to import file
            duplicate_handling: How to handle duplicates
            dry_run: If True, don't actually import

        Returns:
            ImportResult with status and counts
        """
        result = ImportResult(
            success=False,
            source_file=file_path,
            source_type=self.source_name,
        )

        # Validate file
        is_valid, error = self.validate_file(file_path)
        if not is_valid:
            result.error_messages.append(f"Invalid file: {error}")
            return result

        # Parse records
        try:
            records = self.parse_file(file_path)
        except Exception as e:
            result.error_messages.append(f"Failed to parse file: {e}")
            return result

        result.total_records = len(records)

        # Import each record
        for record in records:
            try:
                book, action = self._import_record(
                    record, duplicate_handling, dry_run
                )
                if action == "imported":
                    result.imported += 1
                    if book:
                        result.imported_books.append(book)
                elif action == "skipped":
                    result.skipped += 1
                elif action == "updated":
                    result.updated += 1
            except Exception as e:
                result.errors += 1
                result.error_messages.append(
                    f"Error importing '{record.title}': {e}"
                )

        result.success = result.errors == 0 or result.imported > 0
        return result

    def _import_record(
        self,
        record: ImportRecord,
        duplicate_handling: DuplicateHandling,
        dry_run: bool,
    ) -> tuple[Optional[Book], str]:
        """Import a single record.

        Args:
            record: Record to import
            duplicate_handling: Duplicate handling mode
            dry_run: If True, don't actually import

        Returns:
            Tuple of (Book or None, action taken)
        """
        # Check for existing book
        existing = self._find_existing_book(record)

        if existing:
            if duplicate_handling == DuplicateHandling.SKIP:
                return None, "skipped"
            elif duplicate_handling == DuplicateHandling.UPDATE:
                if not dry_run:
                    self._update_book(existing, record)
                return existing, "updated"
            elif duplicate_handling == DuplicateHandling.REPLACE:
                if not dry_run:
                    self._delete_book(existing)
                    book = self._create_book(record)
                    return book, "imported"
                return None, "imported"
            # CREATE_NEW falls through to create new

        if dry_run:
            return None, "imported"

        book = self._create_book(record)
        return book, "imported"

    def _find_existing_book(self, record: ImportRecord) -> Optional[Book]:
        """Find existing book matching the record.

        Matches by ISBN first, then by title+author.
        """
        from sqlalchemy import select, func

        with self.db.get_session() as session:
            existing = None

            # Try ISBN match first
            if record.isbn:
                stmt = select(Book).where(Book.isbn == record.isbn)
                existing = session.execute(stmt).scalar_one_or_none()

            if not existing and record.isbn13:
                stmt = select(Book).where(Book.isbn13 == record.isbn13)
                existing = session.execute(stmt).scalar_one_or_none()

            # Try title + author match
            if not existing:
                stmt = select(Book).where(
                    func.lower(Book.title) == record.title.lower(),
                    func.lower(Book.author) == record.author.lower(),
                )
                existing = session.execute(stmt).scalar_one_or_none()

            # Expunge from session so it can be used after session closes
            if existing:
                session.expunge(existing)

            return existing

    def _create_book(self, record: ImportRecord) -> Book:
        """Create a new book from record."""
        book_create = record.to_book_create()
        return self.db.create_book(book_create)

    def _update_book(self, book: Book, record: ImportRecord) -> None:
        """Update existing book with record data."""
        from ..db.schemas import BookUpdate

        update_data = {}

        # Only update fields that have values in the import
        if record.rating and not book.rating:
            update_data["rating"] = record.rating
        if record.page_count and not book.page_count:
            update_data["page_count"] = record.page_count
        if record.date_started and not book.date_started:
            update_data["date_started"] = record.date_started
        if record.date_finished and not book.date_finished:
            update_data["date_finished"] = record.date_finished
        if record.tags and not book.get_tags():
            update_data["tags"] = record.tags
        if record.comments and not book.comments:
            update_data["comments"] = record.comments
        if record.cover_url and not book.cover:
            update_data["cover"] = record.cover_url
        if record.description and not book.description:
            update_data["description"] = record.description
        if record.series and not book.series:
            update_data["series"] = record.series
            if record.series_index:
                update_data["series_index"] = record.series_index

        if update_data:
            book_update = BookUpdate(**update_data)
            self.db.update_book(book.id, book_update)

    def _delete_book(self, book: Book) -> None:
        """Delete a book."""
        self.db.delete_book(book.id)

    def preview_import(self, file_path: Path) -> dict:
        """Preview what would be imported.

        Args:
            file_path: Path to import file

        Returns:
            Dictionary with preview information
        """
        is_valid, error = self.validate_file(file_path)
        if not is_valid:
            return {"valid": False, "error": error}

        try:
            records = self.parse_file(file_path)
        except Exception as e:
            return {"valid": False, "error": str(e)}

        # Count existing matches
        new_count = 0
        existing_count = 0
        statuses = {}
        authors = {}

        for record in records:
            existing = self._find_existing_book(record)
            if existing:
                existing_count += 1
            else:
                new_count += 1

            # Count statuses
            status = record.status.value if record.status else "unknown"
            statuses[status] = statuses.get(status, 0) + 1

            # Count authors
            authors[record.author] = authors.get(record.author, 0) + 1

        # Top authors
        top_authors = sorted(
            authors.items(), key=lambda x: x[1], reverse=True
        )[:5]

        return {
            "valid": True,
            "total_records": len(records),
            "new_books": new_count,
            "existing_books": existing_count,
            "statuses": statuses,
            "top_authors": top_authors,
            "source_type": self.source_name,
        }
