"""Tests for CSV extraction."""

import tempfile
from pathlib import Path

import pytest

from src.vibecoding.booktracker.etl.extract import (
    ExtractionError,
    extract_calibre_csv,
    extract_goodreads_csv,
    extract_notion_csv,
    extract_all,
)


class TestExtractNotion:
    """Tests for Notion CSV extraction."""

    def test_extract_notion_basic(self, notion_csv_file):
        """Test extracting books from Notion CSV."""
        rows = list(extract_notion_csv(notion_csv_file, show_progress=False))
        assert len(rows) == 2
        assert rows[0]["source"] == "notion"
        assert rows[0]["raw"]["Title"] == "The Great Gatsby"
        assert rows[1]["raw"]["Title"] == "1984"

    def test_extract_notion_file_not_found(self):
        """Test that missing file raises error."""
        with pytest.raises(ExtractionError, match="File not found"):
            list(extract_notion_csv("/nonexistent/file.csv"))

    def test_extract_notion_skips_empty_rows(self, tmp_path):
        """Test that rows with empty titles are skipped."""
        csv_content = "Title,Author,Status\nBook One,Author One,Read\n,Empty Author,Read\n"
        csv_file = tmp_path / "notion.csv"
        csv_file.write_text(csv_content)

        rows = list(extract_notion_csv(csv_file, show_progress=False))
        assert len(rows) == 1
        assert rows[0]["raw"]["Title"] == "Book One"


class TestExtractCalibre:
    """Tests for Calibre CSV extraction."""

    def test_extract_calibre_basic(self, calibre_csv_file):
        """Test extracting books from Calibre CSV."""
        rows = list(extract_calibre_csv(calibre_csv_file, show_progress=False))
        assert len(rows) == 2
        assert rows[0]["source"] == "calibre"
        assert rows[0]["raw"]["title"] == "Dune"

    def test_extract_calibre_file_not_found(self):
        """Test that missing file raises error."""
        with pytest.raises(ExtractionError, match="File not found"):
            list(extract_calibre_csv("/nonexistent/file.csv"))


class TestExtractGoodreads:
    """Tests for Goodreads CSV extraction."""

    def test_extract_goodreads_basic(self, goodreads_csv_file):
        """Test extracting books from Goodreads CSV."""
        rows = list(extract_goodreads_csv(goodreads_csv_file, show_progress=False))
        assert len(rows) == 2
        assert rows[0]["source"] == "goodreads"
        assert rows[0]["raw"]["Title"] == "Project Hail Mary"

    def test_extract_goodreads_file_not_found(self):
        """Test that missing file raises error."""
        with pytest.raises(ExtractionError, match="File not found"):
            list(extract_goodreads_csv("/nonexistent/file.csv"))


class TestExtractAll:
    """Tests for combined extraction."""

    def test_extract_all_sources(
        self, notion_csv_file, calibre_csv_file, goodreads_csv_file
    ):
        """Test extracting from all sources."""
        rows = list(
            extract_all(
                notion_path=notion_csv_file,
                calibre_path=calibre_csv_file,
                goodreads_path=goodreads_csv_file,
                show_progress=False,
            )
        )
        # 2 + 2 + 2 = 6 total books
        assert len(rows) == 6
        sources = [r["source"] for r in rows]
        assert sources.count("notion") == 2
        assert sources.count("calibre") == 2
        assert sources.count("goodreads") == 2

    def test_extract_partial_sources(self, notion_csv_file, calibre_csv_file):
        """Test extracting from subset of sources."""
        rows = list(
            extract_all(
                notion_path=notion_csv_file,
                calibre_path=calibre_csv_file,
                show_progress=False,
            )
        )
        assert len(rows) == 4


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def notion_csv_file(tmp_path):
    """Create a sample Notion CSV file."""
    content = """Title,Author,Status,Rating,ISBN,ISBN-13,Pages,Added
The Great Gatsby,F. Scott Fitzgerald,Read,5,0743273567,9780743273565,180,2025-01-01
1984,George Orwell,Want to Read,,0451524934,9780451524935,328,2025-01-02
"""
    csv_file = tmp_path / "notion.csv"
    csv_file.write_text(content)
    return csv_file


@pytest.fixture
def calibre_csv_file(tmp_path):
    """Create a sample Calibre CSV file."""
    content = """title,authors,rating,isbn,uuid,formats,timestamp,identifiers
Dune,Frank Herbert,10,9780441172719,abc-123,epub;mobi,2024-01-01,goodreads:234225
Neuromancer,William Gibson,8,0441569595,def-456,epub,2024-02-01,
"""
    csv_file = tmp_path / "calibre.csv"
    csv_file.write_text(content)
    return csv_file


@pytest.fixture
def goodreads_csv_file(tmp_path):
    """Create a sample Goodreads CSV file."""
    content = """Book Id,Title,Author,ISBN,ISBN13,My Rating,Exclusive Shelf,Date Read
54493401,Project Hail Mary,Andy Weir,="0593135202",="9780593135204",5,read,2024-06-15
18007564,The Martian,Andy Weir,="0553418025",="9780553418026",4,read,2024-01-10
"""
    csv_file = tmp_path / "goodreads.csv"
    csv_file.write_text(content)
    return csv_file
