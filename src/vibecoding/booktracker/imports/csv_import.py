"""Generic CSV importer with field mapping.

Allows importing from any CSV file with customizable field mapping.
"""

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from ..db.schemas import BookStatus
from .base import BaseImporter, ImportRecord, ImportError


@dataclass
class FieldMapping:
    """Mapping configuration for CSV fields."""

    # Required field mappings (CSV column name -> internal field)
    title: str = "title"
    author: str = "author"

    # Optional field mappings
    isbn: Optional[str] = None
    isbn13: Optional[str] = None
    status: Optional[str] = None
    rating: Optional[str] = None
    page_count: Optional[str] = None
    date_added: Optional[str] = None
    date_started: Optional[str] = None
    date_finished: Optional[str] = None
    tags: Optional[str] = None
    comments: Optional[str] = None
    publisher: Optional[str] = None
    publication_year: Optional[str] = None
    series: Optional[str] = None
    series_index: Optional[str] = None
    cover_url: Optional[str] = None
    description: Optional[str] = None

    # Status value mapping
    status_mapping: dict[str, BookStatus] = field(default_factory=lambda: {
        "read": BookStatus.COMPLETED,
        "completed": BookStatus.COMPLETED,
        "done": BookStatus.COMPLETED,
        "finished": BookStatus.COMPLETED,
        "reading": BookStatus.READING,
        "currently reading": BookStatus.READING,
        "in progress": BookStatus.READING,
        "to read": BookStatus.WISHLIST,
        "to-read": BookStatus.WISHLIST,
        "want to read": BookStatus.WISHLIST,
        "wishlist": BookStatus.WISHLIST,
        "tbr": BookStatus.WISHLIST,
        "on hold": BookStatus.ON_HOLD,
        "on-hold": BookStatus.ON_HOLD,
        "paused": BookStatus.ON_HOLD,
        "dnf": BookStatus.DNF,
        "did not finish": BookStatus.DNF,
        "abandoned": BookStatus.DNF,
    })

    # Date format (for parsing dates)
    date_format: str = "%Y-%m-%d"

    # Tag separator (for multi-value tag fields)
    tag_separator: str = ","

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "author": self.author,
            "isbn": self.isbn,
            "isbn13": self.isbn13,
            "status": self.status,
            "rating": self.rating,
            "page_count": self.page_count,
            "date_added": self.date_added,
            "date_started": self.date_started,
            "date_finished": self.date_finished,
            "tags": self.tags,
            "comments": self.comments,
            "publisher": self.publisher,
            "publication_year": self.publication_year,
            "series": self.series,
            "series_index": self.series_index,
            "cover_url": self.cover_url,
            "description": self.description,
            "date_format": self.date_format,
            "tag_separator": self.tag_separator,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FieldMapping":
        """Create from dictionary."""
        return cls(
            title=data.get("title", "title"),
            author=data.get("author", "author"),
            isbn=data.get("isbn"),
            isbn13=data.get("isbn13"),
            status=data.get("status"),
            rating=data.get("rating"),
            page_count=data.get("page_count"),
            date_added=data.get("date_added"),
            date_started=data.get("date_started"),
            date_finished=data.get("date_finished"),
            tags=data.get("tags"),
            comments=data.get("comments"),
            publisher=data.get("publisher"),
            publication_year=data.get("publication_year"),
            series=data.get("series"),
            series_index=data.get("series_index"),
            cover_url=data.get("cover_url"),
            description=data.get("description"),
            date_format=data.get("date_format", "%Y-%m-%d"),
            tag_separator=data.get("tag_separator", ","),
        )

    @classmethod
    def auto_detect(cls, columns: list[str]) -> "FieldMapping":
        """Auto-detect field mappings from column names.

        Args:
            columns: List of CSV column names

        Returns:
            FieldMapping with detected mappings
        """
        mapping = cls()
        columns_lower = {c.lower(): c for c in columns}

        # Common column name variations
        field_variations = {
            "title": ["title", "book title", "name", "book name", "book"],
            "author": ["author", "authors", "writer", "by", "book author"],
            "isbn": ["isbn", "isbn10", "isbn-10"],
            "isbn13": ["isbn13", "isbn-13", "ean"],
            "status": ["status", "shelf", "reading status", "state"],
            "rating": ["rating", "my rating", "stars", "score"],
            "page_count": ["pages", "page count", "number of pages", "length"],
            "date_added": ["date added", "added", "add date", "date"],
            "date_started": ["date started", "started", "start date", "began"],
            "date_finished": ["date finished", "finished", "date read", "read date", "completed"],
            "tags": ["tags", "genres", "shelves", "categories", "bookshelves"],
            "comments": ["comments", "notes", "review", "my review", "thoughts"],
            "publisher": ["publisher", "publishing", "pub"],
            "publication_year": ["year", "publication year", "pub year", "year published"],
            "series": ["series", "series name"],
            "series_index": ["series index", "series #", "book #", "number in series"],
            "cover_url": ["cover", "cover url", "image", "image url"],
            "description": ["description", "summary", "synopsis", "about"],
        }

        for field_name, variations in field_variations.items():
            for variation in variations:
                if variation in columns_lower:
                    setattr(mapping, field_name, columns_lower[variation])
                    break

        return mapping


class GenericCSVImporter(BaseImporter):
    """Imports books from any CSV file with customizable field mapping."""

    source_name = "csv"

    def __init__(self, db=None, mapping: Optional[FieldMapping] = None):
        """Initialize importer.

        Args:
            db: Database instance
            mapping: Field mapping configuration
        """
        super().__init__(db)
        self.mapping = mapping

    def validate_file(self, file_path: Path) -> tuple[bool, Optional[str]]:
        """Validate CSV file."""
        if not file_path.exists():
            return False, f"File not found: {file_path}"

        if not file_path.suffix.lower() == ".csv":
            return False, "File must be a CSV file"

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                columns = reader.fieldnames or []

                if not columns:
                    return False, "CSV file has no columns"

                # Auto-detect mapping if not provided
                if not self.mapping:
                    self.mapping = FieldMapping.auto_detect(columns)

                # Check for required columns
                if self.mapping.title not in columns:
                    return False, f"Title column '{self.mapping.title}' not found"
                if self.mapping.author not in columns:
                    return False, f"Author column '{self.mapping.author}' not found"

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
        """Parse CSV file."""
        records = []

        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            # Auto-detect mapping if not set
            if not self.mapping:
                self.mapping = FieldMapping.auto_detect(reader.fieldnames or [])

            for row in reader:
                record = self._parse_row(row)
                if record:
                    records.append(record)

        return records

    def _parse_row(self, row: dict) -> Optional[ImportRecord]:
        """Parse a single CSV row into ImportRecord."""
        m = self.mapping

        title = self._get_field(row, m.title, "").strip()
        author = self._get_field(row, m.author, "").strip()

        if not title or not author:
            return None

        return ImportRecord(
            title=title,
            author=author,
            isbn=self._get_field(row, m.isbn),
            isbn13=self._get_field(row, m.isbn13),
            status=self._parse_status(self._get_field(row, m.status)),
            rating=self._parse_int(self._get_field(row, m.rating)),
            page_count=self._parse_int(self._get_field(row, m.page_count)),
            date_added=self._parse_date(self._get_field(row, m.date_added)),
            date_started=self._parse_date(self._get_field(row, m.date_started)),
            date_finished=self._parse_date(self._get_field(row, m.date_finished)),
            tags=self._parse_tags(self._get_field(row, m.tags)),
            comments=self._get_field(row, m.comments),
            publisher=self._get_field(row, m.publisher),
            publication_year=self._parse_int(self._get_field(row, m.publication_year)),
            series=self._get_field(row, m.series),
            series_index=self._parse_float(self._get_field(row, m.series_index)),
            cover_url=self._get_field(row, m.cover_url),
            description=self._get_field(row, m.description),
            source="csv",
            raw_data=dict(row),
        )

    def _get_field(
        self,
        row: dict,
        field_name: Optional[str],
        default: Optional[str] = None,
    ) -> Optional[str]:
        """Get field value from row."""
        if not field_name:
            return default

        value = row.get(field_name, default)
        if value is not None:
            value = str(value).strip()
            return value if value else default
        return default

    def _parse_status(self, value: Optional[str]) -> BookStatus:
        """Parse status value using mapping."""
        if not value:
            return BookStatus.WISHLIST

        value_lower = value.lower().strip()
        return self.mapping.status_mapping.get(value_lower, BookStatus.WISHLIST)

    def _parse_int(self, value: Optional[str]) -> Optional[int]:
        """Parse integer value."""
        if not value:
            return None
        try:
            # Handle ratings like "4.5" by rounding
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        """Parse float value."""
        if not value:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _parse_date(self, value: Optional[str]) -> Optional[str]:
        """Parse date value."""
        if not value:
            return None

        # Try multiple common formats
        formats = [
            self.mapping.date_format,
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%d/%m/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%Y-%m-%dT%H:%M:%S",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return dt.date().isoformat()
            except ValueError:
                continue

        return None

    def _parse_tags(self, value: Optional[str]) -> list[str]:
        """Parse tags from string."""
        if not value:
            return []

        tags = []
        for tag in value.split(self.mapping.tag_separator):
            tag = tag.strip()
            if tag:
                tags.append(tag)

        return tags

    def get_columns(self, file_path: Path) -> list[str]:
        """Get column names from CSV file.

        Args:
            file_path: Path to CSV file

        Returns:
            List of column names
        """
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                return list(reader.fieldnames or [])
        except Exception:
            return []

    def get_sample_data(self, file_path: Path, rows: int = 5) -> list[dict]:
        """Get sample data from CSV file.

        Args:
            file_path: Path to CSV file
            rows: Number of rows to return

        Returns:
            List of row dictionaries
        """
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                return [dict(row) for row in list(reader)[:rows]]
        except Exception:
            return []
