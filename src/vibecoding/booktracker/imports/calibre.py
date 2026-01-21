"""Calibre library importer.

Imports books from Calibre CSV exports or directly from Calibre library.
"""

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..db.schemas import BookStatus
from .base import BaseImporter, ImportRecord, ImportError


class CalibreImporter(BaseImporter):
    """Imports books from Calibre CSV export or library database."""

    source_name = "calibre"

    # Required columns for Calibre CSV
    REQUIRED_COLUMNS = {"title", "authors"}

    # Common Calibre CSV columns
    EXPECTED_COLUMNS = {
        "title",
        "authors",
        "author_sort",
        "publisher",
        "rating",
        "timestamp",
        "pubdate",
        "series",
        "series_index",
        "tags",
        "comments",
        "isbn",
        "identifiers",
        "formats",
        "cover",
        "languages",
        "id",
        "uuid",
    }

    def validate_file(self, file_path: Path) -> tuple[bool, Optional[str]]:
        """Validate Calibre CSV file."""
        if not file_path.exists():
            return False, f"File not found: {file_path}"

        suffix = file_path.suffix.lower()
        if suffix not in [".csv"]:
            return False, "File must be a CSV file"

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                columns = {c.lower() for c in (reader.fieldnames or [])}

                # Check for required columns
                missing = self.REQUIRED_COLUMNS - columns
                if missing:
                    return False, f"Missing required columns: {missing}"

                # Read first row to verify data
                first_row = next(reader, None)
                if first_row is None:
                    return False, "CSV file is empty"

            return True, None

        except csv.Error as e:
            return False, f"CSV parsing error: {e}"
        except Exception as e:
            return False, f"Error reading file: {e}"

    def parse_file(self, file_path: Path) -> list[ImportRecord]:
        """Parse Calibre CSV file."""
        records = []

        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            # Normalize column names to lowercase
            if reader.fieldnames:
                field_map = {name: name.lower() for name in reader.fieldnames}
            else:
                field_map = {}

            for row in reader:
                # Normalize row keys
                normalized_row = {
                    field_map.get(k, k.lower()): v for k, v in row.items()
                }
                record = self._parse_row(normalized_row)
                if record:
                    records.append(record)

        return records

    def _parse_row(self, row: dict) -> Optional[ImportRecord]:
        """Parse a single CSV row into ImportRecord."""
        title = row.get("title", "").strip()
        authors = row.get("authors", "").strip()

        if not title or not authors:
            return None

        # Parse author (Calibre uses "Author1 & Author2" format)
        author = self._normalize_authors(authors)

        # Parse ISBN from identifiers or isbn field
        isbn, isbn13 = self._parse_isbn(row)

        # Parse rating (Calibre uses 0-10 scale)
        rating = self._parse_rating(row.get("rating", ""))

        # Parse page count (if available in custom columns)
        page_count = self._parse_int(row.get("pages", row.get("#pages", "")))

        # Parse series
        series = row.get("series", "").strip() or None
        series_index = self._parse_float(row.get("series_index", ""))

        # Parse dates
        date_added = self._parse_date(row.get("timestamp", ""))
        pub_date = self._parse_date(row.get("pubdate", ""))

        # Extract publication year
        pub_year = None
        if pub_date:
            try:
                pub_year = int(pub_date[:4])
            except (ValueError, TypeError):
                pass

        # Parse tags
        tags = self._parse_tags(row.get("tags", ""))

        # Parse comments/description
        description = self._clean_html(row.get("comments", ""))

        # Parse cover
        cover_url = row.get("cover", "").strip() or None

        # Parse formats
        formats = row.get("formats", "").strip() or None

        return ImportRecord(
            title=title,
            author=author,
            isbn=isbn,
            isbn13=isbn13,
            status=BookStatus.WISHLIST,  # Calibre doesn't track reading status
            rating=rating,
            page_count=page_count,
            date_added=date_added,
            tags=tags,
            publisher=row.get("publisher", "").strip() or None,
            publication_year=pub_year,
            series=series,
            series_index=series_index,
            cover_url=cover_url,
            description=description,
            source="calibre",
            source_id=row.get("uuid", row.get("id", "")),
            raw_data={
                **row,
                "formats": formats,
                "identifiers": row.get("identifiers", ""),
            },
        )

    def _normalize_authors(self, authors: str) -> str:
        """Normalize author names from Calibre format.

        Calibre uses "Author1 & Author2" format.
        """
        # Handle multiple authors
        if " & " in authors:
            # Take primary author only
            authors = authors.split(" & ")[0]

        return authors.strip()

    def _parse_isbn(self, row: dict) -> tuple[Optional[str], Optional[str]]:
        """Parse ISBN from Calibre row."""
        isbn = None
        isbn13 = None

        # Try direct ISBN field
        isbn_field = row.get("isbn", "").strip()
        if isbn_field:
            cleaned = re.sub(r"[\s-]", "", isbn_field)
            if len(cleaned) == 10:
                isbn = cleaned
            elif len(cleaned) == 13:
                isbn13 = cleaned

        # Try identifiers field (format: "isbn:1234567890,amazon:B0123456")
        identifiers = row.get("identifiers", "")
        if identifiers:
            for ident in identifiers.split(","):
                if ":" in ident:
                    key, value = ident.split(":", 1)
                    key = key.strip().lower()
                    value = re.sub(r"[\s-]", "", value.strip())

                    if key == "isbn" and len(value) == 10:
                        isbn = value
                    elif key == "isbn13" or (key == "isbn" and len(value) == 13):
                        isbn13 = value

        return isbn, isbn13

    def _parse_rating(self, rating_str: str) -> Optional[int]:
        """Parse rating (Calibre uses 0-10 scale, convert to 1-5)."""
        try:
            rating = float(rating_str) if rating_str else 0
            if rating > 0:
                # Convert 0-10 to 1-5
                return max(1, min(5, round(rating / 2)))
            return None
        except (ValueError, TypeError):
            return None

    def _parse_int(self, value: str) -> Optional[int]:
        """Parse integer value."""
        try:
            return int(float(value)) if value else None
        except (ValueError, TypeError):
            return None

    def _parse_float(self, value: str) -> Optional[float]:
        """Parse float value."""
        try:
            return float(value) if value else None
        except (ValueError, TypeError):
            return None

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date from Calibre format."""
        if not date_str:
            return None

        # Calibre uses ISO format
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        # Handle timezone offset format
        date_str = date_str.replace("+00:00", "").replace("Z", "")

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip()[:19], fmt[:19].replace("%z", ""))
                return dt.date().isoformat()
            except ValueError:
                continue

        return None

    def _parse_tags(self, tags_str: str) -> list[str]:
        """Parse tags from Calibre format."""
        if not tags_str:
            return []

        # Calibre uses comma-separated tags
        tags = []
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag:
                tags.append(tag)

        return tags

    def _clean_html(self, html: str) -> Optional[str]:
        """Remove HTML tags from text."""
        if not html:
            return None

        # Simple HTML tag removal
        text = re.sub(r"<[^>]+>", "", html)
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')

        return text.strip() or None


class CalibreLibraryImporter(BaseImporter):
    """Imports books directly from Calibre library database."""

    source_name = "calibre_library"

    def validate_file(self, file_path: Path) -> tuple[bool, Optional[str]]:
        """Validate Calibre library path."""
        if not file_path.exists():
            return False, f"Path not found: {file_path}"

        # Check for metadata.db
        metadata_db = file_path / "metadata.db"
        if not metadata_db.exists():
            return False, "Not a valid Calibre library (missing metadata.db)"

        return True, None

    def parse_file(self, file_path: Path) -> list[ImportRecord]:
        """Parse Calibre library database."""
        import sqlite3

        records = []
        metadata_db = file_path / "metadata.db"

        try:
            conn = sqlite3.connect(str(metadata_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Query books with authors
            cursor.execute("""
                SELECT
                    b.id,
                    b.title,
                    b.sort as title_sort,
                    b.timestamp,
                    b.pubdate,
                    b.series_index,
                    b.path,
                    b.uuid,
                    GROUP_CONCAT(DISTINCT a.name) as authors,
                    s.name as series,
                    r.rating,
                    p.name as publisher,
                    GROUP_CONCAT(DISTINCT t.name) as tags,
                    c.text as comments
                FROM books b
                LEFT JOIN books_authors_link bal ON b.id = bal.book
                LEFT JOIN authors a ON bal.author = a.id
                LEFT JOIN books_series_link bsl ON b.id = bsl.book
                LEFT JOIN series s ON bsl.series = s.id
                LEFT JOIN books_ratings_link brl ON b.id = brl.book
                LEFT JOIN ratings r ON brl.rating = r.id
                LEFT JOIN books_publishers_link bpl ON b.id = bpl.book
                LEFT JOIN publishers p ON bpl.publisher = p.id
                LEFT JOIN books_tags_link btl ON b.id = btl.book
                LEFT JOIN tags t ON btl.tag = t.id
                LEFT JOIN comments c ON b.id = c.book
                GROUP BY b.id
            """)

            for row in cursor.fetchall():
                record = self._parse_db_row(dict(row))
                if record:
                    records.append(record)

            # Get identifiers separately
            cursor.execute("""
                SELECT book, type, val FROM identifiers
            """)
            identifiers = {}
            for row in cursor.fetchall():
                book_id = row["book"]
                if book_id not in identifiers:
                    identifiers[book_id] = {}
                identifiers[book_id][row["type"]] = row["val"]

            # Add ISBNs to records
            for record in records:
                book_id = int(record.raw_data.get("id", 0))
                if book_id in identifiers:
                    if "isbn" in identifiers[book_id]:
                        isbn = identifiers[book_id]["isbn"]
                        if len(isbn) == 10:
                            record.isbn = isbn
                        elif len(isbn) == 13:
                            record.isbn13 = isbn

            conn.close()

        except sqlite3.Error as e:
            raise ImportError(f"Database error: {e}")

        return records

    def _parse_db_row(self, row: dict) -> Optional[ImportRecord]:
        """Parse a database row into ImportRecord."""
        title = row.get("title", "").strip()
        authors = row.get("authors", "").strip()

        if not title or not authors:
            return None

        # Take first author
        author = authors.split(",")[0].strip()

        # Parse rating (Calibre uses 0-10)
        rating = None
        if row.get("rating"):
            rating = max(1, min(5, round(row["rating"] / 2)))

        # Parse dates
        date_added = None
        if row.get("timestamp"):
            try:
                date_added = row["timestamp"][:10]
            except (TypeError, IndexError):
                pass

        pub_year = None
        if row.get("pubdate"):
            try:
                pub_year = int(row["pubdate"][:4])
            except (TypeError, ValueError, IndexError):
                pass

        # Parse tags
        tags = []
        if row.get("tags"):
            tags = [t.strip() for t in row["tags"].split(",") if t.strip()]

        # Clean comments
        description = None
        if row.get("comments"):
            description = re.sub(r"<[^>]+>", "", row["comments"]).strip()

        return ImportRecord(
            title=title,
            author=author,
            status=BookStatus.WISHLIST,
            rating=rating,
            date_added=date_added,
            publication_year=pub_year,
            series=row.get("series"),
            series_index=row.get("series_index"),
            tags=tags,
            publisher=row.get("publisher"),
            description=description,
            source="calibre_library",
            source_id=row.get("uuid", str(row.get("id", ""))),
            raw_data=row,
        )
