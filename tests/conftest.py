"""Pytest configuration and shared fixtures.

This module provides fixtures for testing the booktracker application,
including mock databases, sample data, and Notion API mocks.
"""

import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Generator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.vibecoding.booktracker.db.models import Base, Book, ReadingLog, SyncQueueItem
from src.vibecoding.booktracker.db.schemas import BookCreate, BookStatus, BookSource
from src.vibecoding.booktracker.db.sqlite import Database, reset_db
from src.vibecoding.booktracker.config import reset_config


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def temp_db_path() -> Generator[Path, None, None]:
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture(scope="function")
def db(temp_db_path: Path) -> Generator[Database, None, None]:
    """Create a test database instance."""
    # Reset any global state
    reset_db()
    reset_config()

    # Set environment variable for test database
    os.environ["BOOKTRACKER_DB_PATH"] = str(temp_db_path)

    database = Database(str(temp_db_path))
    database.create_tables()
    yield database

    # Cleanup
    reset_db()
    if "BOOKTRACKER_DB_PATH" in os.environ:
        del os.environ["BOOKTRACKER_DB_PATH"]


@pytest.fixture(scope="function")
def session(db: Database) -> Generator[Session, None, None]:
    """Create a database session for testing."""
    with db.get_session() as sess:
        yield sess


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_book_data() -> BookCreate:
    """Create sample book data for testing."""
    return BookCreate(
        title="The Great Gatsby",
        author="F. Scott Fitzgerald",
        status=BookStatus.COMPLETED,
        rating=5,
        isbn="9780743273565",
        isbn13="9780743273565",
        page_count=180,
        date_added=date(2025, 1, 1),
        date_finished=date(2025, 1, 15),
        publisher="Scribner",
        publication_year=1925,
        format="Paperback",
        genres=["Fiction", "Classic"],
        tags=["american-literature", "jazz-age"],
        sources=[BookSource.MANUAL],
        source_ids={},
    )


@pytest.fixture
def sample_book_minimal() -> BookCreate:
    """Create minimal book data (only required fields)."""
    return BookCreate(
        title="Minimal Book",
        author="Test Author",
    )


@pytest.fixture
def sample_goodreads_book() -> BookCreate:
    """Create sample book data mimicking Goodreads import."""
    return BookCreate(
        title="Project Hail Mary",
        author="Andy Weir",
        status=BookStatus.COMPLETED,
        rating=5,
        isbn="0593135202",
        isbn13="9780593135204",
        page_count=496,
        date_added=date(2024, 6, 1),
        date_finished=date(2024, 6, 15),
        publisher="Ballantine Books",
        publication_year=2021,
        original_publication_year=2021,
        format="Hardcover",
        goodreads_id=54493401,
        goodreads_avg_rating=4.52,
        goodreads_shelves="read, sci-fi, favorites",
        read_count=1,
        sources=[BookSource.GOODREADS],
        source_ids={"goodreads": "54493401"},
    )


@pytest.fixture
def sample_calibre_book() -> BookCreate:
    """Create sample book data mimicking Calibre import."""
    return BookCreate(
        title="Dune",
        author="Frank Herbert",
        author_sort="Herbert, Frank",
        title_sort="Dune",
        status=BookStatus.OWNED,
        rating=5,
        isbn="9780441172719",
        page_count=688,
        publisher="Ace",
        publication_year=1965,
        language="eng",
        file_formats=["epub", "mobi"],
        file_size=2500000,
        calibre_id=42,
        calibre_uuid="abc123-def456",
        calibre_library="Calibre Library",
        identifiers={"goodreads": "234225", "mobi-asin": "B00B7NPRY8"},
        tags=["RIPPED"],
        sources=[BookSource.CALIBRE],
        source_ids={"calibre": "42"},
    )


@pytest.fixture
def sample_notion_book() -> BookCreate:
    """Create sample book data mimicking Notion import."""
    return BookCreate(
        title="Atomic Habits",
        author="James Clear",
        status=BookStatus.COMPLETED,
        rating=4,
        isbn13="9780735211292",
        page_count=320,
        date_added=date(2024, 3, 1),
        date_started=date(2024, 3, 5),
        date_finished=date(2024, 3, 20),
        publisher="Avery",
        publication_year=2018,
        format="Kindle",
        library_source="Calibre Library",
        amazon_url="https://amazon.com/dp/0735211299",
        goodreads_url="https://goodreads.com/book/show/40121378",
        progress="100%",
        recommended_by="Friend",
        genres=["Self-Help", "Productivity"],
        sources=[BookSource.NOTION],
        source_ids={"notion": "page-id-123"},
    )


@pytest.fixture
def created_book(db: Database, sample_book_data: BookCreate) -> Book:
    """Create and return a book in the database."""
    return db.create_book(sample_book_data)


@pytest.fixture
def multiple_books(db: Database) -> list[Book]:
    """Create multiple books in the database."""
    books_data = [
        BookCreate(
            title="Book One",
            author="Author A",
            status=BookStatus.COMPLETED,
            rating=4,
        ),
        BookCreate(
            title="Book Two",
            author="Author B",
            status=BookStatus.READING,
            rating=None,
        ),
        BookCreate(
            title="Book Three",
            author="Author A",
            status=BookStatus.WISHLIST,
        ),
        BookCreate(
            title="Another Book",
            author="Author C",
            status=BookStatus.COMPLETED,
            rating=5,
        ),
    ]
    return [db.create_book(data) for data in books_data]


# ============================================================================
# Mock Notion API Fixtures
# ============================================================================


@pytest.fixture
def mock_notion_responses():
    """Fixture providing mock Notion API responses."""
    return {
        "database_query": {
            "results": [],
            "has_more": False,
            "next_cursor": None,
        },
        "page_create": {
            "id": str(uuid4()),
            "created_time": "2025-01-20T10:00:00.000Z",
            "last_edited_time": "2025-01-20T10:00:00.000Z",
        },
        "page_update": {
            "id": str(uuid4()),
            "last_edited_time": "2025-01-20T11:00:00.000Z",
        },
    }


# ============================================================================
# CLI Testing Fixtures
# ============================================================================


@pytest.fixture
def cli_runner():
    """Create a Typer CLI test runner."""
    from typer.testing import CliRunner
    return CliRunner()


@pytest.fixture
def cli_app():
    """Get the CLI app for testing."""
    from src.vibecoding.booktracker.cli import app
    return app
