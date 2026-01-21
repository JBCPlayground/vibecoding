"""Database restore functionality.

Restores data from backups with various merge strategies.
"""

import gzip
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from sqlalchemy import select, delete

from ..db.models import Book, ReadingLog
from ..db.schemas import BookCreate, BookStatus, ReadingLogCreate
from ..db.sqlite import Database, get_db


class RestoreMode(str, Enum):
    """Restore mode options."""

    REPLACE = "replace"  # Clear database and restore
    MERGE = "merge"  # Add new records, skip existing
    UPDATE = "update"  # Add new records, update existing
    INCREMENTAL = "incremental"  # Apply incremental backup


@dataclass
class RestoreResult:
    """Result of a restore operation."""

    success: bool
    mode: RestoreMode = RestoreMode.REPLACE
    books_restored: int = 0
    books_skipped: int = 0
    books_updated: int = 0
    logs_restored: int = 0
    logs_skipped: int = 0
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def total_restored(self) -> int:
        """Total records restored."""
        return self.books_restored + self.logs_restored


class RestoreManager:
    """Manages database restoration from backups."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize restore manager.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def restore(
        self,
        backup_path: Path,
        mode: RestoreMode = RestoreMode.REPLACE,
        dry_run: bool = False,
    ) -> RestoreResult:
        """Restore database from backup.

        Args:
            backup_path: Path to backup file
            mode: Restore mode (replace, merge, update)
            dry_run: If True, don't actually restore, just simulate

        Returns:
            RestoreResult with status and counts
        """
        try:
            # Load backup data
            data = self._load_backup_file(backup_path)

            # Check for incremental backup
            if data.get("incremental"):
                if mode != RestoreMode.INCREMENTAL:
                    mode = RestoreMode.INCREMENTAL

            # Validate backup structure
            if "books" not in data:
                return RestoreResult(
                    success=False,
                    error="Invalid backup: missing books data",
                )

            if mode == RestoreMode.REPLACE:
                return self._restore_replace(data, dry_run)
            elif mode == RestoreMode.MERGE:
                return self._restore_merge(data, dry_run)
            elif mode == RestoreMode.UPDATE:
                return self._restore_update(data, dry_run)
            elif mode == RestoreMode.INCREMENTAL:
                return self._restore_incremental(data, dry_run)
            else:
                return RestoreResult(
                    success=False,
                    error=f"Unknown restore mode: {mode}",
                )

        except Exception as e:
            return RestoreResult(
                success=False,
                error=str(e),
            )

    def restore_sqlite(
        self,
        backup_path: Path,
        target_path: Optional[Path] = None,
    ) -> RestoreResult:
        """Restore from SQLite backup file.

        Args:
            backup_path: Path to SQLite backup
            target_path: Target database path (uses current db if None)

        Returns:
            RestoreResult
        """
        try:
            target = target_path or Path(self.db.db_path)

            # Create backup of current database
            if target.exists():
                backup = target.with_suffix(".db.bak")
                shutil.copy2(target, backup)

            # Copy backup to target
            shutil.copy2(backup_path, target)

            # Count records in restored database
            restored_db = Database(str(target))
            with restored_db.get_session() as session:
                book_count = len(session.execute(select(Book.id)).all())
                log_count = len(session.execute(select(ReadingLog.id)).all())

            return RestoreResult(
                success=True,
                mode=RestoreMode.REPLACE,
                books_restored=book_count,
                logs_restored=log_count,
            )

        except Exception as e:
            return RestoreResult(
                success=False,
                error=str(e),
            )

    def preview_restore(self, backup_path: Path) -> dict:
        """Preview what would be restored.

        Args:
            backup_path: Path to backup file

        Returns:
            Dictionary with preview information
        """
        try:
            data = self._load_backup_file(backup_path)

            metadata = data.get("_metadata", {})
            books = data.get("books", [])
            logs = data.get("reading_logs", [])

            # Get current database counts
            with self.db.get_session() as session:
                current_books = len(session.execute(select(Book.id)).all())
                current_logs = len(session.execute(select(ReadingLog.id)).all())

            # Find overlaps
            backup_book_ids = {b["id"] for b in books}
            with self.db.get_session() as session:
                existing_ids = {
                    row[0] for row in session.execute(select(Book.id)).all()
                }

            overlap_count = len(backup_book_ids & existing_ids)
            new_count = len(backup_book_ids - existing_ids)

            return {
                "backup_created": metadata.get("created_at"),
                "backup_version": metadata.get("version"),
                "backup_books": len(books),
                "backup_logs": len(logs),
                "current_books": current_books,
                "current_logs": current_logs,
                "overlapping_books": overlap_count,
                "new_books": new_count,
                "is_incremental": data.get("incremental", False),
            }

        except Exception as e:
            return {"error": str(e)}

    def _restore_replace(self, data: dict, dry_run: bool) -> RestoreResult:
        """Restore by replacing all data."""
        result = RestoreResult(success=True, mode=RestoreMode.REPLACE)
        warnings = []

        books = data.get("books", [])
        logs = data.get("reading_logs", [])

        if dry_run:
            result.books_restored = len(books)
            result.logs_restored = len(logs)
            return result

        with self.db.get_session() as session:
            # Clear existing data
            session.execute(delete(ReadingLog))
            session.execute(delete(Book))
            session.commit()

            # Restore books
            for book_data in books:
                try:
                    book = self._create_book_from_dict(book_data)
                    session.add(book)
                    result.books_restored += 1
                except Exception as e:
                    warnings.append(f"Failed to restore book '{book_data.get('title')}': {e}")

            session.commit()

            # Restore reading logs
            for log_data in logs:
                try:
                    log = self._create_log_from_dict(log_data)
                    session.add(log)
                    result.logs_restored += 1
                except Exception as e:
                    warnings.append(f"Failed to restore log: {e}")

            session.commit()

        result.warnings = warnings
        return result

    def _restore_merge(self, data: dict, dry_run: bool) -> RestoreResult:
        """Restore by merging with existing data (skip existing)."""
        result = RestoreResult(success=True, mode=RestoreMode.MERGE)
        warnings = []

        books = data.get("books", [])
        logs = data.get("reading_logs", [])

        with self.db.get_session() as session:
            # Get existing IDs
            existing_book_ids = {
                row[0] for row in session.execute(select(Book.id)).all()
            }
            existing_log_ids = {
                row[0] for row in session.execute(select(ReadingLog.id)).all()
            }

            if dry_run:
                for book_data in books:
                    if book_data["id"] in existing_book_ids:
                        result.books_skipped += 1
                    else:
                        result.books_restored += 1

                for log_data in logs:
                    if log_data["id"] in existing_log_ids:
                        result.logs_skipped += 1
                    else:
                        result.logs_restored += 1

                return result

            # Restore new books only
            for book_data in books:
                if book_data["id"] in existing_book_ids:
                    result.books_skipped += 1
                    continue

                try:
                    book = self._create_book_from_dict(book_data)
                    session.add(book)
                    result.books_restored += 1
                except Exception as e:
                    warnings.append(f"Failed to restore book '{book_data.get('title')}': {e}")

            session.commit()

            # Restore new logs only
            for log_data in logs:
                if log_data["id"] in existing_log_ids:
                    result.logs_skipped += 1
                    continue

                try:
                    log = self._create_log_from_dict(log_data)
                    session.add(log)
                    result.logs_restored += 1
                except Exception as e:
                    warnings.append(f"Failed to restore log: {e}")

            session.commit()

        result.warnings = warnings
        return result

    def _restore_update(self, data: dict, dry_run: bool) -> RestoreResult:
        """Restore by updating existing and adding new."""
        result = RestoreResult(success=True, mode=RestoreMode.UPDATE)
        warnings = []

        books = data.get("books", [])
        logs = data.get("reading_logs", [])

        with self.db.get_session() as session:
            existing_book_ids = {
                row[0] for row in session.execute(select(Book.id)).all()
            }

            if dry_run:
                for book_data in books:
                    if book_data["id"] in existing_book_ids:
                        result.books_updated += 1
                    else:
                        result.books_restored += 1
                result.logs_restored = len(logs)
                return result

            # Process books
            for book_data in books:
                book_id = book_data["id"]

                if book_id in existing_book_ids:
                    # Update existing book
                    try:
                        existing = session.get(Book, book_id)
                        if existing:
                            self._update_book_from_dict(existing, book_data)
                            result.books_updated += 1
                    except Exception as e:
                        warnings.append(f"Failed to update book '{book_data.get('title')}': {e}")
                else:
                    # Add new book
                    try:
                        book = self._create_book_from_dict(book_data)
                        session.add(book)
                        result.books_restored += 1
                    except Exception as e:
                        warnings.append(f"Failed to restore book '{book_data.get('title')}': {e}")

            session.commit()

            # Process logs (replace all for updated books)
            for log_data in logs:
                try:
                    # Delete existing log if it exists
                    existing_log = session.get(ReadingLog, log_data["id"])
                    if existing_log:
                        session.delete(existing_log)

                    log = self._create_log_from_dict(log_data)
                    session.add(log)
                    result.logs_restored += 1
                except Exception as e:
                    warnings.append(f"Failed to restore log: {e}")

            session.commit()

        result.warnings = warnings
        return result

    def _restore_incremental(self, data: dict, dry_run: bool) -> RestoreResult:
        """Apply incremental backup."""
        # Incremental uses update mode logic
        return self._restore_update(data, dry_run)

    def _create_book_from_dict(self, data: dict) -> Book:
        """Create Book model from dictionary."""
        tags = data.get("tags", [])
        if isinstance(tags, list):
            tags_json = json.dumps(tags)
        else:
            tags_json = tags

        book = Book(
            id=data["id"],
            title=data["title"],
            author=data.get("author"),
            isbn=data.get("isbn"),
            isbn13=data.get("isbn13"),
            status=data.get("status", BookStatus.WISHLIST.value),
            rating=data.get("rating"),
            page_count=data.get("page_count"),
            progress=data.get("progress"),
            date_added=data.get("date_added"),
            date_started=data.get("date_started"),
            date_finished=data.get("date_finished"),
            tags=tags_json,
            comments=data.get("comments"),
            publisher=data.get("publisher"),
            publication_year=data.get("publication_year"),
            series=data.get("series"),
            series_index=data.get("series_index"),
            cover=data.get("cover"),
            description=data.get("description"),
            goodreads_id=data.get("goodreads_id"),
            goodreads_avg_rating=data.get("goodreads_avg_rating"),
            read_next=data.get("read_next", False),
            notion_page_id=data.get("notion_page_id"),
            notion_modified_at=data.get("notion_modified_at"),
        )
        return book

    def _update_book_from_dict(self, book: Book, data: dict) -> None:
        """Update existing book from dictionary."""
        tags = data.get("tags", [])
        if isinstance(tags, list):
            tags_json = json.dumps(tags)
        else:
            tags_json = tags

        book.title = data["title"]
        book.author = data.get("author")
        book.isbn = data.get("isbn")
        book.isbn13 = data.get("isbn13")
        book.status = data.get("status", BookStatus.WISHLIST.value)
        book.rating = data.get("rating")
        book.page_count = data.get("page_count")
        book.progress = data.get("progress")
        book.date_added = data.get("date_added")
        book.date_started = data.get("date_started")
        book.date_finished = data.get("date_finished")
        book.tags = tags_json
        book.comments = data.get("comments")
        book.publisher = data.get("publisher")
        book.publication_year = data.get("publication_year")
        book.series = data.get("series")
        book.series_index = data.get("series_index")
        book.cover = data.get("cover")
        book.description = data.get("description")
        book.goodreads_id = data.get("goodreads_id")
        book.goodreads_avg_rating = data.get("goodreads_avg_rating")
        book.read_next = data.get("read_next", False)
        book.notion_page_id = data.get("notion_page_id")
        book.notion_modified_at = data.get("notion_modified_at")

    def _create_log_from_dict(self, data: dict) -> ReadingLog:
        """Create ReadingLog model from dictionary."""
        return ReadingLog(
            id=data["id"],
            book_id=data["book_id"],
            date=data.get("date"),
            pages_read=data.get("pages_read"),
            start_page=data.get("start_page"),
            end_page=data.get("end_page"),
            duration_minutes=data.get("duration_minutes"),
            notes=data.get("notes"),
            location=data.get("location"),
            notion_page_id=data.get("notion_page_id"),
        )

    def _load_backup_file(self, backup_path: Path) -> dict:
        """Load backup file (compressed or not)."""
        if backup_path.suffix == ".gz" or str(backup_path).endswith(".gz"):
            with gzip.open(backup_path, "rt", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(backup_path, "r", encoding="utf-8") as f:
                return json.load(f)
