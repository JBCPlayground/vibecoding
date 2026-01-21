"""JSON export functionality.

Provides comprehensive data export for backup and portability.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select

from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


@dataclass
class JSONExportResult:
    """Result of a JSON export operation."""

    success: bool
    file_path: Optional[Path] = None
    books_exported: int = 0
    logs_exported: int = 0
    error: Optional[str] = None


class JSONExporter:
    """Exports book data to JSON format."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize exporter.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def export_all(
        self,
        output_path: Path,
        include_reading_logs: bool = True,
        pretty: bool = True,
    ) -> JSONExportResult:
        """Export all data to JSON file.

        Args:
            output_path: Path for output file
            include_reading_logs: Include reading log data
            pretty: Pretty-print JSON output

        Returns:
            JSONExportResult with success status
        """
        try:
            with self.db.get_session() as session:
                # Export books
                stmt = select(Book).order_by(Book.date_added.desc())
                books = list(session.execute(stmt).scalars().all())

                book_data = []
                for book in books:
                    session.expunge(book)
                    book_data.append(self._book_to_dict(book))

                # Export reading logs
                logs_data = []
                if include_reading_logs:
                    stmt = select(ReadingLog).order_by(ReadingLog.date.desc())
                    logs = list(session.execute(stmt).scalars().all())

                    for log in logs:
                        session.expunge(log)
                        logs_data.append(self._log_to_dict(log))

                # Build export structure
                export_data = {
                    "version": "1.0",
                    "exported_at": datetime.now().isoformat(),
                    "books": book_data,
                }

                if include_reading_logs:
                    export_data["reading_logs"] = logs_data

                # Write to file
                with open(output_path, "w", encoding="utf-8") as f:
                    if pretty:
                        json.dump(export_data, f, indent=2, ensure_ascii=False)
                    else:
                        json.dump(export_data, f, ensure_ascii=False)

                return JSONExportResult(
                    success=True,
                    file_path=output_path,
                    books_exported=len(book_data),
                    logs_exported=len(logs_data),
                )

        except Exception as e:
            return JSONExportResult(
                success=False,
                error=str(e),
            )

    def export_books(
        self,
        output_path: Path,
        status_filter: Optional[BookStatus] = None,
        pretty: bool = True,
    ) -> JSONExportResult:
        """Export books to JSON file.

        Args:
            output_path: Path for output file
            status_filter: Only export books with this status
            pretty: Pretty-print JSON output

        Returns:
            JSONExportResult with success status
        """
        try:
            with self.db.get_session() as session:
                stmt = select(Book)
                if status_filter:
                    stmt = stmt.where(Book.status == status_filter.value)
                stmt = stmt.order_by(Book.date_added.desc())

                books = list(session.execute(stmt).scalars().all())

                book_data = []
                for book in books:
                    session.expunge(book)
                    book_data.append(self._book_to_dict(book))

                export_data = {
                    "version": "1.0",
                    "exported_at": datetime.now().isoformat(),
                    "books": book_data,
                }

                with open(output_path, "w", encoding="utf-8") as f:
                    if pretty:
                        json.dump(export_data, f, indent=2, ensure_ascii=False)
                    else:
                        json.dump(export_data, f, ensure_ascii=False)

                return JSONExportResult(
                    success=True,
                    file_path=output_path,
                    books_exported=len(book_data),
                )

        except Exception as e:
            return JSONExportResult(
                success=False,
                error=str(e),
            )

    def export_to_string(
        self,
        include_reading_logs: bool = True,
        pretty: bool = True,
    ) -> str:
        """Export all data to JSON string.

        Args:
            include_reading_logs: Include reading log data
            pretty: Pretty-print JSON output

        Returns:
            JSON content as string
        """
        with self.db.get_session() as session:
            # Export books
            stmt = select(Book).order_by(Book.date_added.desc())
            books = list(session.execute(stmt).scalars().all())

            book_data = []
            for book in books:
                session.expunge(book)
                book_data.append(self._book_to_dict(book))

            # Export reading logs
            logs_data = []
            if include_reading_logs:
                stmt = select(ReadingLog).order_by(ReadingLog.date.desc())
                logs = list(session.execute(stmt).scalars().all())

                for log in logs:
                    session.expunge(log)
                    logs_data.append(self._log_to_dict(log))

            # Build export structure
            export_data = {
                "version": "1.0",
                "exported_at": datetime.now().isoformat(),
                "books": book_data,
            }

            if include_reading_logs:
                export_data["reading_logs"] = logs_data

            if pretty:
                return json.dumps(export_data, indent=2, ensure_ascii=False)
            return json.dumps(export_data, ensure_ascii=False)

    def export_book(self, book_id: str, include_logs: bool = True) -> Optional[dict]:
        """Export a single book with its reading logs.

        Args:
            book_id: Book ID to export
            include_logs: Include reading log data

        Returns:
            Book data as dictionary, or None if not found
        """
        with self.db.get_session() as session:
            stmt = select(Book).where(Book.id == book_id)
            book = session.execute(stmt).scalar_one_or_none()

            if not book:
                return None

            session.expunge(book)
            book_data = self._book_to_dict(book)

            if include_logs:
                stmt = select(ReadingLog).where(
                    ReadingLog.book_id == book_id
                ).order_by(ReadingLog.date.desc())
                logs = list(session.execute(stmt).scalars().all())

                book_data["reading_logs"] = [
                    self._log_to_dict(log) for log in logs
                ]

            return book_data

    def export_reading_logs(
        self,
        output_path: Path,
        book_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        pretty: bool = True,
    ) -> JSONExportResult:
        """Export reading logs to JSON.

        Args:
            output_path: Path for output file
            book_id: Filter by book ID
            start_date: Filter by start date
            end_date: Filter by end date
            pretty: Pretty-print JSON output

        Returns:
            JSONExportResult with success status
        """
        try:
            with self.db.get_session() as session:
                stmt = select(ReadingLog)

                if book_id:
                    stmt = stmt.where(ReadingLog.book_id == book_id)
                if start_date:
                    stmt = stmt.where(ReadingLog.date >= start_date.isoformat())
                if end_date:
                    stmt = stmt.where(ReadingLog.date <= end_date.isoformat())

                stmt = stmt.order_by(ReadingLog.date.desc())
                logs = list(session.execute(stmt).scalars().all())

                logs_data = []
                for log in logs:
                    session.expunge(log)
                    logs_data.append(self._log_to_dict(log))

                export_data = {
                    "version": "1.0",
                    "exported_at": datetime.now().isoformat(),
                    "reading_logs": logs_data,
                }

                with open(output_path, "w", encoding="utf-8") as f:
                    if pretty:
                        json.dump(export_data, f, indent=2, ensure_ascii=False)
                    else:
                        json.dump(export_data, f, ensure_ascii=False)

                return JSONExportResult(
                    success=True,
                    file_path=output_path,
                    logs_exported=len(logs_data),
                )

        except Exception as e:
            return JSONExportResult(
                success=False,
                error=str(e),
            )

    def _book_to_dict(self, book: Book) -> dict[str, Any]:
        """Convert a Book model to dictionary."""
        return {
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "isbn": book.isbn,
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
            "cover": book.cover,
            "notion_page_id": book.notion_page_id,
            "series": book.series,
            "series_index": book.series_index,
        }

    def _log_to_dict(self, log: ReadingLog) -> dict[str, Any]:
        """Convert a ReadingLog model to dictionary."""
        return {
            "id": log.id,
            "book_id": log.book_id,
            "date": log.date,
            "pages_read": log.pages_read,
            "start_page": log.start_page,
            "end_page": log.end_page,
            "duration_minutes": log.duration_minutes,
            "location": log.location,
            "notes": log.notes,
        }
