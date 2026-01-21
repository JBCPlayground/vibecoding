"""CSV extraction for Notion, Calibre, and Goodreads exports.

Each extractor reads raw CSV data and yields dictionaries with original column names.
Transformation to unified schema happens in transform.py.
"""

import csv
from pathlib import Path
from typing import Iterator, Optional

import pandas as pd
from tqdm import tqdm


class ExtractionError(Exception):
    """Raised when CSV extraction fails."""

    pass


def _detect_encoding(file_path: Path) -> str:
    """Detect file encoding, defaulting to utf-8."""
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                f.read(1024)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def extract_notion_csv(
    file_path: Path | str,
    show_progress: bool = True,
) -> Iterator[dict]:
    """Extract books from Notion CSV export.

    Notion CSV has 31 fields including: Title, Author, Status, Rating,
    Added, Date Started, Date Finished, ISBN, etc.

    Args:
        file_path: Path to Notion CSV file
        show_progress: Show tqdm progress bar

    Yields:
        Dictionary with raw Notion column values
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise ExtractionError(f"File not found: {file_path}")

    encoding = _detect_encoding(file_path)

    # Read CSV with pandas for better handling of complex fields
    try:
        df = pd.read_csv(file_path, encoding=encoding, dtype=str, na_values=[""])
        df = df.fillna("")
    except Exception as e:
        raise ExtractionError(f"Failed to read Notion CSV: {e}")

    rows = df.to_dict("records")
    iterator = tqdm(rows, desc="Reading Notion CSV", disable=not show_progress)

    for row in iterator:
        # Skip empty rows
        if not row.get("Title", "").strip():
            continue
        yield {
            "source": "notion",
            "raw": row,
        }


def extract_calibre_csv(
    file_path: Path | str,
    show_progress: bool = True,
) -> Iterator[dict]:
    """Extract books from Calibre CSV export.

    Calibre CSV has 22 fields including: title, authors, rating (0-10 scale),
    uuid, formats, identifiers, etc.

    Args:
        file_path: Path to Calibre CSV file
        show_progress: Show tqdm progress bar

    Yields:
        Dictionary with raw Calibre column values
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise ExtractionError(f"File not found: {file_path}")

    encoding = _detect_encoding(file_path)

    try:
        df = pd.read_csv(file_path, encoding=encoding, dtype=str, na_values=[""])
        df = df.fillna("")
    except Exception as e:
        raise ExtractionError(f"Failed to read Calibre CSV: {e}")

    rows = df.to_dict("records")
    iterator = tqdm(rows, desc="Reading Calibre CSV", disable=not show_progress)

    for row in iterator:
        # Skip empty rows
        if not row.get("title", "").strip():
            continue
        yield {
            "source": "calibre",
            "raw": row,
        }


def extract_goodreads_csv(
    file_path: Path | str,
    show_progress: bool = True,
) -> Iterator[dict]:
    """Extract books from Goodreads CSV export.

    Goodreads CSV has 24 fields including: Title, Author, ISBN (with ="..." wrapper),
    My Rating, Exclusive Shelf (status), etc.

    Args:
        file_path: Path to Goodreads CSV file
        show_progress: Show tqdm progress bar

    Yields:
        Dictionary with raw Goodreads column values
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise ExtractionError(f"File not found: {file_path}")

    encoding = _detect_encoding(file_path)

    try:
        df = pd.read_csv(file_path, encoding=encoding, dtype=str, na_values=[""])
        df = df.fillna("")
    except Exception as e:
        raise ExtractionError(f"Failed to read Goodreads CSV: {e}")

    rows = df.to_dict("records")
    iterator = tqdm(rows, desc="Reading Goodreads CSV", disable=not show_progress)

    for row in iterator:
        # Skip empty rows
        if not row.get("Title", "").strip():
            continue
        yield {
            "source": "goodreads",
            "raw": row,
        }


def extract_all(
    notion_path: Optional[Path | str] = None,
    calibre_path: Optional[Path | str] = None,
    goodreads_path: Optional[Path | str] = None,
    show_progress: bool = True,
) -> Iterator[dict]:
    """Extract books from all provided CSV sources.

    Args:
        notion_path: Path to Notion CSV (optional)
        calibre_path: Path to Calibre CSV (optional)
        goodreads_path: Path to Goodreads CSV (optional)
        show_progress: Show progress bars

    Yields:
        Dictionary with source and raw data for each book
    """
    if notion_path:
        yield from extract_notion_csv(notion_path, show_progress)

    if calibre_path:
        yield from extract_calibre_csv(calibre_path, show_progress)

    if goodreads_path:
        yield from extract_goodreads_csv(goodreads_path, show_progress)


def count_rows(file_path: Path | str) -> int:
    """Count rows in a CSV file (excluding header)."""
    file_path = Path(file_path)
    if not file_path.exists():
        return 0

    encoding = _detect_encoding(file_path)
    with open(file_path, "r", encoding=encoding) as f:
        return sum(1 for _ in f) - 1  # Subtract header row
