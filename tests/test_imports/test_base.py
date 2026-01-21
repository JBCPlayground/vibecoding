"""Tests for base importer functionality."""

import pytest
from datetime import date

from vibecoding.booktracker.imports.base import (
    BaseImporter,
    ImportRecord,
    ImportResult,
    DuplicateHandling,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus


class TestImportRecord:
    """Tests for ImportRecord dataclass."""

    def test_create_record(self):
        """Test creating an import record."""
        record = ImportRecord(
            title="Test Book",
            author="Test Author",
            isbn="1234567890",
            status=BookStatus.COMPLETED,
            rating=5,
        )
        assert record.title == "Test Book"
        assert record.author == "Test Author"
        assert record.status == BookStatus.COMPLETED

    def test_to_book_create(self):
        """Test converting to BookCreate schema."""
        record = ImportRecord(
            title="Test Book",
            author="Test Author",
            isbn="1234567890",
            status=BookStatus.READING,
            rating=4,
            tags=["fiction", "fantasy"],
        )

        book_create = record.to_book_create()

        assert isinstance(book_create, BookCreate)
        assert book_create.title == "Test Book"
        assert book_create.author == "Test Author"
        assert book_create.status == BookStatus.READING
        assert book_create.rating == 4
        assert "fiction" in book_create.tags

    def test_default_status(self):
        """Test default status is WISHLIST."""
        record = ImportRecord(
            title="Test Book",
            author="Test Author",
        )

        book_create = record.to_book_create()
        assert book_create.status == BookStatus.WISHLIST


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_summary(self):
        """Test result summary."""
        result = ImportResult(
            success=True,
            total_records=100,
            imported=80,
            skipped=15,
            updated=5,
            errors=0,
        )

        summary = result.summary
        assert "Imported: 80" in summary
        assert "Skipped: 15" in summary
        assert "Updated: 5" in summary

    def test_default_values(self):
        """Test default values."""
        result = ImportResult(success=True)
        assert result.imported == 0
        assert result.skipped == 0
        assert result.errors == 0
        assert result.error_messages == []


class TestDuplicateHandling:
    """Tests for DuplicateHandling enum."""

    def test_values(self):
        """Test enum values."""
        assert DuplicateHandling.SKIP.value == "skip"
        assert DuplicateHandling.UPDATE.value == "update"
        assert DuplicateHandling.REPLACE.value == "replace"
        assert DuplicateHandling.CREATE_NEW.value == "create_new"
