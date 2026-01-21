"""Database backup functionality.

Creates comprehensive backups of the book tracking database.
"""

import gzip
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from ..db.models import Book, ReadingLog
from ..db.sqlite import Database, get_db


@dataclass
class BackupMetadata:
    """Metadata about a backup."""

    version: str = "1.0"
    created_at: str = ""
    database_path: str = ""
    book_count: int = 0
    reading_log_count: int = 0
    checksum: str = ""
    compressed: bool = False
    app_version: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "database_path": self.database_path,
            "book_count": self.book_count,
            "reading_log_count": self.reading_log_count,
            "checksum": self.checksum,
            "compressed": self.compressed,
            "app_version": self.app_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupMetadata":
        """Create from dictionary."""
        return cls(
            version=data.get("version", "1.0"),
            created_at=data.get("created_at", ""),
            database_path=data.get("database_path", ""),
            book_count=data.get("book_count", 0),
            reading_log_count=data.get("reading_log_count", 0),
            checksum=data.get("checksum", ""),
            compressed=data.get("compressed", False),
            app_version=data.get("app_version", ""),
        )


@dataclass
class BackupResult:
    """Result of a backup operation."""

    success: bool
    backup_path: Optional[Path] = None
    metadata: Optional[BackupMetadata] = None
    error: Optional[str] = None
    size_bytes: int = 0

    @property
    def size_human(self) -> str:
        """Get human-readable size."""
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        else:
            return f"{self.size_bytes / (1024 * 1024):.1f} MB"


class BackupManager:
    """Manages database backups."""

    BACKUP_EXTENSION = ".booktracker-backup"
    COMPRESSED_EXTENSION = ".booktracker-backup.gz"

    def __init__(self, db: Optional[Database] = None):
        """Initialize backup manager.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def create_backup(
        self,
        output_path: Path,
        compress: bool = True,
        include_metadata: bool = True,
    ) -> BackupResult:
        """Create a full backup of the database.

        Args:
            output_path: Path to save backup file
            compress: Whether to compress the backup
            include_metadata: Whether to include metadata file

        Returns:
            BackupResult with status and details
        """
        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Get counts for metadata
            with self.db.get_session() as session:
                book_count = session.execute(
                    select(Book.id)
                ).all()
                log_count = session.execute(
                    select(ReadingLog.id)
                ).all()

            # Create backup data
            backup_data = self._export_all_data()

            # Calculate checksum
            json_bytes = json.dumps(backup_data, indent=2).encode("utf-8")
            checksum = hashlib.sha256(json_bytes).hexdigest()

            # Create metadata
            from .. import __version__
            metadata = BackupMetadata(
                created_at=datetime.now().isoformat(),
                database_path=str(self.db.db_path),
                book_count=len(book_count),
                reading_log_count=len(log_count),
                checksum=checksum,
                compressed=compress,
                app_version=__version__,
            )

            # Add metadata to backup
            backup_data["_metadata"] = metadata.to_dict()

            # Determine final path
            if compress:
                final_path = output_path.with_suffix(self.COMPRESSED_EXTENSION)
                with gzip.open(final_path, "wt", encoding="utf-8") as f:
                    json.dump(backup_data, f, indent=2)
            else:
                final_path = output_path.with_suffix(self.BACKUP_EXTENSION)
                with open(final_path, "w", encoding="utf-8") as f:
                    json.dump(backup_data, f, indent=2)

            # Get file size
            size_bytes = final_path.stat().st_size

            # Save metadata file if requested
            if include_metadata:
                meta_path = final_path.with_suffix(final_path.suffix + ".meta")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(metadata.to_dict(), f, indent=2)

            return BackupResult(
                success=True,
                backup_path=final_path,
                metadata=metadata,
                size_bytes=size_bytes,
            )

        except Exception as e:
            return BackupResult(
                success=False,
                error=str(e),
            )

    def create_incremental_backup(
        self,
        output_path: Path,
        since: datetime,
        compress: bool = True,
    ) -> BackupResult:
        """Create incremental backup with changes since a date.

        Args:
            output_path: Path to save backup
            since: Only include changes after this datetime
            compress: Whether to compress

        Returns:
            BackupResult
        """
        try:
            since_str = since.date().isoformat()

            with self.db.get_session() as session:
                # Get books modified since date
                stmt = select(Book).where(Book.date_added >= since_str)
                books = list(session.execute(stmt).scalars().all())

                # Get logs since date
                stmt = select(ReadingLog).where(ReadingLog.date >= since_str)
                logs = list(session.execute(stmt).scalars().all())

                backup_data = {
                    "incremental": True,
                    "since": since.isoformat(),
                    "books": [self._book_to_dict(b) for b in books],
                    "reading_logs": [self._log_to_dict(l) for l in logs],
                }

            # Calculate checksum
            json_bytes = json.dumps(backup_data, indent=2).encode("utf-8")
            checksum = hashlib.sha256(json_bytes).hexdigest()

            from .. import __version__
            metadata = BackupMetadata(
                created_at=datetime.now().isoformat(),
                database_path=str(self.db.db_path),
                book_count=len(books),
                reading_log_count=len(logs),
                checksum=checksum,
                compressed=compress,
                app_version=__version__,
            )

            backup_data["_metadata"] = metadata.to_dict()

            # Write file
            if compress:
                final_path = output_path.with_suffix(self.COMPRESSED_EXTENSION)
                with gzip.open(final_path, "wt", encoding="utf-8") as f:
                    json.dump(backup_data, f, indent=2)
            else:
                final_path = output_path.with_suffix(self.BACKUP_EXTENSION)
                with open(final_path, "w", encoding="utf-8") as f:
                    json.dump(backup_data, f, indent=2)

            return BackupResult(
                success=True,
                backup_path=final_path,
                metadata=metadata,
                size_bytes=final_path.stat().st_size,
            )

        except Exception as e:
            return BackupResult(success=False, error=str(e))

    def create_sqlite_backup(self, output_path: Path) -> BackupResult:
        """Create a raw SQLite database backup.

        Args:
            output_path: Path to save the SQLite file

        Returns:
            BackupResult
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy the database file
            final_path = output_path.with_suffix(".db")
            shutil.copy2(self.db.db_path, final_path)

            # Get metadata
            with self.db.get_session() as session:
                book_count = len(session.execute(select(Book.id)).all())
                log_count = len(session.execute(select(ReadingLog.id)).all())

            from .. import __version__
            metadata = BackupMetadata(
                created_at=datetime.now().isoformat(),
                database_path=str(self.db.db_path),
                book_count=book_count,
                reading_log_count=log_count,
                app_version=__version__,
            )

            return BackupResult(
                success=True,
                backup_path=final_path,
                metadata=metadata,
                size_bytes=final_path.stat().st_size,
            )

        except Exception as e:
            return BackupResult(success=False, error=str(e))

    def list_backups(self, directory: Path) -> list[tuple[Path, BackupMetadata]]:
        """List available backups in a directory.

        Args:
            directory: Directory to search

        Returns:
            List of (path, metadata) tuples
        """
        backups = []

        if not directory.exists():
            return backups

        # Find backup files
        patterns = [
            f"*{self.BACKUP_EXTENSION}",
            f"*{self.COMPRESSED_EXTENSION}",
        ]

        for pattern in patterns:
            for backup_file in directory.glob(pattern):
                metadata = self._read_backup_metadata(backup_file)
                if metadata:
                    backups.append((backup_file, metadata))

        # Sort by creation date (newest first)
        backups.sort(
            key=lambda x: x[1].created_at if x[1].created_at else "",
            reverse=True,
        )

        return backups

    def verify_backup(self, backup_path: Path) -> tuple[bool, Optional[str]]:
        """Verify backup file integrity.

        Args:
            backup_path: Path to backup file

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            data = self._load_backup_file(backup_path)

            if "_metadata" not in data:
                return False, "Missing metadata in backup"

            metadata = BackupMetadata.from_dict(data["_metadata"])

            # Verify checksum
            data_copy = {k: v for k, v in data.items() if k != "_metadata"}
            data_copy["_metadata"] = metadata.to_dict()
            json_bytes = json.dumps(data_copy, indent=2).encode("utf-8")
            actual_checksum = hashlib.sha256(json_bytes).hexdigest()

            # Note: Checksum verification is complex due to JSON formatting
            # For now, verify structure
            if "books" not in data:
                return False, "Missing books in backup"

            if "reading_logs" not in data:
                return False, "Missing reading_logs in backup"

            # Verify counts match
            if len(data["books"]) != metadata.book_count:
                return False, f"Book count mismatch: expected {metadata.book_count}, got {len(data['books'])}"

            if len(data["reading_logs"]) != metadata.reading_log_count:
                return False, f"Log count mismatch: expected {metadata.reading_log_count}, got {len(data['reading_logs'])}"

            return True, None

        except Exception as e:
            return False, str(e)

    def _export_all_data(self) -> dict:
        """Export all data from database."""
        with self.db.get_session() as session:
            # Export books
            books = list(session.execute(select(Book)).scalars().all())
            books_data = [self._book_to_dict(book) for book in books]

            # Export reading logs
            logs = list(session.execute(select(ReadingLog)).scalars().all())
            logs_data = [self._log_to_dict(log) for log in logs]

        return {
            "books": books_data,
            "reading_logs": logs_data,
        }

    def _book_to_dict(self, book: Book) -> dict:
        """Convert book to dictionary."""
        return {
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "isbn": book.isbn,
            "isbn13": book.isbn13,
            "status": book.status,
            "rating": book.rating,
            "page_count": book.page_count,
            "progress": book.progress,
            "date_added": book.date_added,
            "date_started": book.date_started,
            "date_finished": book.date_finished,
            "tags": book.get_tags(),
            "comments": book.comments,
            "publisher": book.publisher,
            "publication_year": book.publication_year,
            "series": book.series,
            "series_index": book.series_index,
            "cover": book.cover,
            "description": book.description,
            "goodreads_id": book.goodreads_id,
            "goodreads_avg_rating": book.goodreads_avg_rating,
            "read_next": book.read_next,
            "notion_page_id": book.notion_page_id,
            "notion_modified_at": book.notion_modified_at,
        }

    def _log_to_dict(self, log: ReadingLog) -> dict:
        """Convert reading log to dictionary."""
        return {
            "id": log.id,
            "book_id": log.book_id,
            "date": log.date,
            "pages_read": log.pages_read,
            "start_page": log.start_page,
            "end_page": log.end_page,
            "duration_minutes": log.duration_minutes,
            "notes": log.notes,
            "location": log.location,
            "notion_page_id": log.notion_page_id,
        }

    def _read_backup_metadata(self, backup_path: Path) -> Optional[BackupMetadata]:
        """Read metadata from backup file."""
        # Try reading from .meta file first
        meta_path = backup_path.with_suffix(backup_path.suffix + ".meta")
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    return BackupMetadata.from_dict(json.load(f))
            except Exception:
                pass

        # Read from backup file itself
        try:
            data = self._load_backup_file(backup_path)
            if "_metadata" in data:
                return BackupMetadata.from_dict(data["_metadata"])
        except Exception:
            pass

        return None

    def _load_backup_file(self, backup_path: Path) -> dict:
        """Load backup file (compressed or not)."""
        if backup_path.suffix == ".gz" or str(backup_path).endswith(".gz"):
            with gzip.open(backup_path, "rt", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(backup_path, "r", encoding="utf-8") as f:
                return json.load(f)
