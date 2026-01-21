"""CSV export functionality.

Supports multiple export formats for compatibility with different applications.
"""

import csv
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


class ExportFormat(str, Enum):
    """Export format options."""

    STANDARD = "standard"  # Our standard format
    GOODREADS = "goodreads"  # Goodreads-compatible
    NOTION = "notion"  # Notion-compatible
    CALIBRE = "calibre"  # Calibre-compatible


@dataclass
class ExportResult:
    """Result of an export operation."""

    success: bool
    file_path: Optional[Path] = None
    records_exported: int = 0
    format: Optional[ExportFormat] = None
    error: Optional[str] = None


class CSVExporter:
    """Exports book data to CSV format."""

    # Standard column headers
    STANDARD_COLUMNS = [
        "id",
        "title",
        "author",
        "isbn",
        "isbn13",
        "status",
        "rating",
        "page_count",
        "progress",
        "date_added",
        "date_started",
        "date_finished",
        "tags",
        "comments",
        "publisher",
        "publication_year",
        "cover",
    ]

    # Goodreads-compatible columns
    GOODREADS_COLUMNS = [
        "Book Id",
        "Title",
        "Author",
        "ISBN",
        "ISBN13",
        "My Rating",
        "Number of Pages",
        "Date Read",
        "Date Added",
        "Bookshelves",
        "Exclusive Shelf",
        "My Review",
    ]

    # Notion-compatible columns
    NOTION_COLUMNS = [
        "Name",
        "Author",
        "Status",
        "Rating",
        "Pages",
        "Started",
        "Finished",
        "Tags",
        "Notes",
        "ISBN",
    ]

    # Calibre-compatible columns
    CALIBRE_COLUMNS = [
        "title",
        "authors",
        "isbn",
        "publisher",
        "pubdate",
        "tags",
        "rating",
        "comments",
    ]

    def __init__(self, db: Optional[Database] = None):
        """Initialize exporter.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def export_books(
        self,
        output_path: Path,
        format: ExportFormat = ExportFormat.STANDARD,
        status_filter: Optional[BookStatus] = None,
        include_reading_logs: bool = False,
    ) -> ExportResult:
        """Export books to CSV file.

        Args:
            output_path: Path for output file
            format: Export format to use
            status_filter: Only export books with this status
            include_reading_logs: Include reading log data

        Returns:
            ExportResult with success status and details
        """
        try:
            with self.db.get_session() as session:
                stmt = select(Book)
                if status_filter:
                    stmt = stmt.where(Book.status == status_filter.value)
                stmt = stmt.order_by(Book.date_added.desc())

                books = list(session.execute(stmt).scalars().all())

                if not books:
                    return ExportResult(
                        success=True,
                        file_path=output_path,
                        records_exported=0,
                        format=format,
                    )

                # Convert to appropriate format
                if format == ExportFormat.STANDARD:
                    rows = self._to_standard_format(books, session)
                    columns = self.STANDARD_COLUMNS
                elif format == ExportFormat.GOODREADS:
                    rows = self._to_goodreads_format(books)
                    columns = self.GOODREADS_COLUMNS
                elif format == ExportFormat.NOTION:
                    rows = self._to_notion_format(books)
                    columns = self.NOTION_COLUMNS
                elif format == ExportFormat.CALIBRE:
                    rows = self._to_calibre_format(books)
                    columns = self.CALIBRE_COLUMNS
                else:
                    rows = self._to_standard_format(books, session)
                    columns = self.STANDARD_COLUMNS

                # Write to file
                with open(output_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(rows)

                return ExportResult(
                    success=True,
                    file_path=output_path,
                    records_exported=len(books),
                    format=format,
                )

        except Exception as e:
            return ExportResult(
                success=False,
                error=str(e),
            )

    def export_to_string(
        self,
        format: ExportFormat = ExportFormat.STANDARD,
        status_filter: Optional[BookStatus] = None,
    ) -> str:
        """Export books to CSV string.

        Args:
            format: Export format to use
            status_filter: Only export books with this status

        Returns:
            CSV content as string
        """
        with self.db.get_session() as session:
            stmt = select(Book)
            if status_filter:
                stmt = stmt.where(Book.status == status_filter.value)
            stmt = stmt.order_by(Book.date_added.desc())

            books = list(session.execute(stmt).scalars().all())

            if not books:
                return ""

            # Convert to appropriate format
            if format == ExportFormat.STANDARD:
                rows = self._to_standard_format(books, session)
                columns = self.STANDARD_COLUMNS
            elif format == ExportFormat.GOODREADS:
                rows = self._to_goodreads_format(books)
                columns = self.GOODREADS_COLUMNS
            elif format == ExportFormat.NOTION:
                rows = self._to_notion_format(books)
                columns = self.NOTION_COLUMNS
            elif format == ExportFormat.CALIBRE:
                rows = self._to_calibre_format(books)
                columns = self.CALIBRE_COLUMNS
            else:
                rows = self._to_standard_format(books, session)
                columns = self.STANDARD_COLUMNS

            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

            return output.getvalue()

    def export_reading_logs(
        self,
        output_path: Path,
        book_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> ExportResult:
        """Export reading logs to CSV.

        Args:
            output_path: Path for output file
            book_id: Filter by book ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            ExportResult with success status
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

                if not logs:
                    return ExportResult(
                        success=True,
                        file_path=output_path,
                        records_exported=0,
                    )

                # Get book titles for display
                book_ids = {log.book_id for log in logs}
                book_stmt = select(Book).where(Book.id.in_(book_ids))
                books = {b.id: b for b in session.execute(book_stmt).scalars().all()}

                rows = []
                for log in logs:
                    book = books.get(log.book_id)
                    rows.append({
                        "id": log.id,
                        "book_id": log.book_id,
                        "book_title": book.title if book else "",
                        "date": log.date,
                        "pages_read": log.pages_read or "",
                        "start_page": log.start_page or "",
                        "end_page": log.end_page or "",
                        "duration_minutes": log.duration_minutes or "",
                        "location": log.location or "",
                        "notes": log.notes or "",
                    })

                columns = [
                    "id", "book_id", "book_title", "date", "pages_read",
                    "start_page", "end_page", "duration_minutes", "location", "notes"
                ]

                with open(output_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(rows)

                return ExportResult(
                    success=True,
                    file_path=output_path,
                    records_exported=len(logs),
                )

        except Exception as e:
            return ExportResult(
                success=False,
                error=str(e),
            )

    def _to_standard_format(self, books: list[Book], session) -> list[dict]:
        """Convert books to standard format."""
        rows = []
        for book in books:
            session.expunge(book)
            rows.append({
                "id": book.id,
                "title": book.title,
                "author": book.author,
                "isbn": book.isbn or "",
                "isbn13": book.isbn13 or "",
                "status": book.status,
                "rating": book.rating or "",
                "page_count": book.page_count or "",
                "progress": book.progress or "",
                "date_added": book.date_added or "",
                "date_started": book.date_started or "",
                "date_finished": book.date_finished or "",
                "tags": ",".join(book.get_tags()) if book.tags else "",
                "comments": book.comments or "",
                "publisher": book.publisher or "",
                "publication_year": book.publication_year or "",
                "cover": book.cover or "",
            })
        return rows

    def _to_goodreads_format(self, books: list[Book]) -> list[dict]:
        """Convert books to Goodreads format."""
        rows = []
        for book in books:
            # Map status to Goodreads shelves
            shelf_map = {
                BookStatus.COMPLETED.value: "read",
                BookStatus.READING.value: "currently-reading",
                BookStatus.WISHLIST.value: "to-read",
                BookStatus.ON_HOLD.value: "to-read",
                BookStatus.DNF.value: "did-not-finish",
            }
            exclusive_shelf = shelf_map.get(book.status, "to-read")

            # Get additional bookshelves from tags
            tags = book.get_tags()
            bookshelves = ", ".join([exclusive_shelf] + tags)

            rows.append({
                "Book Id": book.id[:8],  # Shortened ID
                "Title": book.title,
                "Author": book.author,
                "ISBN": book.isbn or "",
                "ISBN13": book.isbn13 or "",
                "My Rating": book.rating or 0,
                "Number of Pages": book.page_count or "",
                "Date Read": book.date_finished or "",
                "Date Added": book.date_added or "",
                "Bookshelves": bookshelves,
                "Exclusive Shelf": exclusive_shelf,
                "My Review": book.comments or "",
            })
        return rows

    def _to_notion_format(self, books: list[Book]) -> list[dict]:
        """Convert books to Notion format."""
        rows = []
        for book in books:
            # Map status to Notion format
            status_map = {
                BookStatus.COMPLETED.value: "Completed",
                BookStatus.READING.value: "Reading",
                BookStatus.WISHLIST.value: "Want to Read",
                BookStatus.ON_HOLD.value: "On Hold",
                BookStatus.DNF.value: "Did Not Finish",
            }
            status = status_map.get(book.status, book.status)

            rows.append({
                "Name": book.title,
                "Author": book.author,
                "Status": status,
                "Rating": book.rating or "",
                "Pages": book.page_count or "",
                "Started": book.date_started or "",
                "Finished": book.date_finished or "",
                "Tags": ",".join(book.get_tags()) if book.tags else "",
                "Notes": book.comments or "",
                "ISBN": book.isbn13 or book.isbn or "",
            })
        return rows

    def _to_calibre_format(self, books: list[Book]) -> list[dict]:
        """Convert books to Calibre format."""
        rows = []
        for book in books:
            # Calibre uses rating out of 10, we use out of 5
            calibre_rating = book.rating * 2 if book.rating else ""

            rows.append({
                "title": book.title,
                "authors": book.author,
                "isbn": book.isbn13 or book.isbn or "",
                "publisher": book.publisher or "",
                "pubdate": f"{book.publication_year}-01-01" if book.publication_year else "",
                "tags": ",".join(book.get_tags()) if book.tags else "",
                "rating": calibre_rating,
                "comments": book.comments or "",
            })
        return rows
