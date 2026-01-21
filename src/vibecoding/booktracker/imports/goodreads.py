"""Goodreads CSV importer.

Imports books from Goodreads export CSV files.
"""

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..db.schemas import BookStatus
from .base import BaseImporter, ImportRecord, ImportError


class GoodreadsImporter(BaseImporter):
    """Imports books from Goodreads CSV export."""

    source_name = "goodreads"

    # Expected Goodreads CSV columns
    REQUIRED_COLUMNS = {"Title", "Author"}
    EXPECTED_COLUMNS = {
        "Title",
        "Author",
        "ISBN",
        "ISBN13",
        "My Rating",
        "Average Rating",
        "Publisher",
        "Binding",
        "Number of Pages",
        "Year Published",
        "Original Publication Year",
        "Date Read",
        "Date Added",
        "Bookshelves",
        "Exclusive Shelf",
        "My Review",
        "Private Notes",
        "Read Count",
        "Owned Copies",
    }

    # Mapping from Goodreads shelf to BookStatus
    SHELF_TO_STATUS = {
        "read": BookStatus.COMPLETED,
        "currently-reading": BookStatus.READING,
        "to-read": BookStatus.WISHLIST,
        "on-hold": BookStatus.ON_HOLD,
        "did-not-finish": BookStatus.DNF,
    }

    def validate_file(self, file_path: Path) -> tuple[bool, Optional[str]]:
        """Validate Goodreads CSV file."""
        if not file_path.exists():
            return False, f"File not found: {file_path}"

        if not file_path.suffix.lower() == ".csv":
            return False, "File must be a CSV file"

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                columns = set(reader.fieldnames or [])

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
        """Parse Goodreads CSV file."""
        records = []

        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                record = self._parse_row(row)
                if record:
                    records.append(record)

        return records

    def _parse_row(self, row: dict) -> Optional[ImportRecord]:
        """Parse a single CSV row into ImportRecord."""
        title = row.get("Title", "").strip()
        author = row.get("Author", "").strip()

        if not title or not author:
            return None

        # Clean up author (Goodreads uses "Last, First" format)
        author = self._normalize_author(author)

        # Parse ISBN
        isbn = self._clean_isbn(row.get("ISBN", ""))
        isbn13 = self._clean_isbn(row.get("ISBN13", ""))

        # Parse rating
        rating = self._parse_rating(row.get("My Rating", ""))

        # Parse page count
        page_count = self._parse_int(row.get("Number of Pages", ""))

        # Parse status from shelf
        status = self._parse_status(row.get("Exclusive Shelf", ""))

        # Parse dates
        date_added = self._parse_date(row.get("Date Added", ""))
        date_finished = self._parse_date(row.get("Date Read", ""))

        # Parse publication year (prefer original publication year)
        pub_year = self._parse_int(row.get("Original Publication Year", ""))
        if not pub_year:
            pub_year = self._parse_int(row.get("Year Published", ""))

        # Parse tags from bookshelves
        tags = self._parse_shelves(row.get("Bookshelves", ""))

        # Combine review and notes
        comments = self._combine_notes(
            row.get("My Review", ""),
            row.get("Private Notes", ""),
        )

        return ImportRecord(
            title=title,
            author=author,
            isbn=isbn,
            isbn13=isbn13,
            status=status,
            rating=rating,
            page_count=page_count,
            date_added=date_added,
            date_finished=date_finished,
            tags=tags,
            comments=comments,
            publisher=row.get("Publisher", "").strip() or None,
            publication_year=pub_year,
            source="goodreads",
            source_id=row.get("Book Id", ""),
            raw_data=dict(row),
        )

    def _normalize_author(self, author: str) -> str:
        """Normalize author name from Goodreads format.

        Goodreads uses "Last, First" format. Convert to "First Last".
        """
        if "," in author:
            parts = author.split(",", 1)
            if len(parts) == 2:
                return f"{parts[1].strip()} {parts[0].strip()}"
        return author

    def _clean_isbn(self, isbn: str) -> Optional[str]:
        """Clean ISBN value."""
        if not isbn:
            return None

        # Remove quotes and equals sign (Goodreads format: ="1234567890")
        isbn = isbn.strip().strip('"').strip("'").lstrip("=").strip('"')

        # Remove hyphens and spaces
        isbn = re.sub(r"[\s-]", "", isbn)

        if not isbn or isbn == "":
            return None

        return isbn if isbn.isdigit() or (isbn[:-1].isdigit() and isbn[-1] in "0123456789X") else None

    def _parse_rating(self, rating_str: str) -> Optional[int]:
        """Parse rating (0 means not rated in Goodreads)."""
        try:
            rating = int(rating_str)
            return rating if rating > 0 else None
        except (ValueError, TypeError):
            return None

    def _parse_int(self, value: str) -> Optional[int]:
        """Parse integer value."""
        try:
            return int(value) if value else None
        except (ValueError, TypeError):
            return None

    def _parse_status(self, shelf: str) -> BookStatus:
        """Parse status from Goodreads exclusive shelf."""
        shelf = shelf.lower().strip()
        return self.SHELF_TO_STATUS.get(shelf, BookStatus.WISHLIST)

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date from Goodreads format."""
        if not date_str:
            return None

        # Goodreads uses various formats
        formats = [
            "%Y/%m/%d",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%d/%m/%Y",
            "%B %d, %Y",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.date().isoformat()
            except ValueError:
                continue

        return None

    def _parse_shelves(self, shelves_str: str) -> list[str]:
        """Parse bookshelves into tags.

        Excludes the standard Goodreads shelves.
        """
        if not shelves_str:
            return []

        # Standard shelves to exclude
        standard = {"read", "currently-reading", "to-read", "on-hold"}

        tags = []
        for shelf in shelves_str.split(","):
            shelf = shelf.strip().lower()
            if shelf and shelf not in standard:
                # Clean up shelf name for tag
                tag = shelf.replace("-", " ").title()
                tags.append(tag)

        return tags

    def _combine_notes(self, review: str, notes: str) -> Optional[str]:
        """Combine review and private notes."""
        parts = []

        if review and review.strip():
            parts.append(f"Review:\n{review.strip()}")

        if notes and notes.strip():
            parts.append(f"Notes:\n{notes.strip()}")

        return "\n\n".join(parts) if parts else None
