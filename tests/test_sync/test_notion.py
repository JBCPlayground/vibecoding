"""Tests for Notion API client."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.vibecoding.booktracker.db.schemas import BookCreate, BookStatus, BookSource
from src.vibecoding.booktracker.sync.notion import (
    NotionClient,
    NotionConfigError,
    NotionPage,
    STATUS_TO_NOTION,
    NOTION_TO_STATUS,
)


class TestStatusMapping:
    """Tests for status mapping between local and Notion."""

    def test_local_to_notion_mapping(self):
        """Test mapping local status to Notion status."""
        assert STATUS_TO_NOTION[BookStatus.READING] == "Borrowed"
        assert STATUS_TO_NOTION[BookStatus.COMPLETED] == "Read"
        assert STATUS_TO_NOTION[BookStatus.WISHLIST] == "Want to Read"
        assert STATUS_TO_NOTION[BookStatus.ON_HOLD] == "On Hold"

    def test_notion_to_local_mapping(self):
        """Test mapping Notion status to local status."""
        assert NOTION_TO_STATUS["Borrowed"] == BookStatus.READING
        assert NOTION_TO_STATUS["Read"] == BookStatus.COMPLETED
        assert NOTION_TO_STATUS["Want to Read"] == BookStatus.WISHLIST
        assert NOTION_TO_STATUS["On Hold"] == BookStatus.ON_HOLD


class TestNotionPage:
    """Tests for NotionPage dataclass."""

    def test_from_api_response(self):
        """Test creating NotionPage from API response."""
        response = {
            "id": "page-123",
            "created_time": "2025-01-01T10:00:00.000Z",
            "last_edited_time": "2025-01-15T15:30:00.000Z",
            "properties": {
                "Title": {"title": [{"plain_text": "Test Book"}]},
                "Author": {"rich_text": [{"plain_text": "Test Author"}]},
                "Status": {"select": {"name": "Read"}},
                "Rating": {"number": 5},
            },
        }

        page = NotionPage.from_api_response(response)

        assert page.page_id == "page-123"
        assert page.title == "Test Book"
        assert page.author == "Test Author"
        assert page.last_edited_time.year == 2025
        assert page.last_edited_time.month == 1
        assert page.last_edited_time.day == 15

    def test_from_api_response_empty_properties(self):
        """Test creating NotionPage with minimal properties."""
        response = {
            "id": "page-456",
            "created_time": "2025-01-01T10:00:00.000Z",
            "last_edited_time": "2025-01-01T10:00:00.000Z",
            "properties": {},
        }

        page = NotionPage.from_api_response(response)

        assert page.page_id == "page-456"
        assert page.title == ""
        assert page.author == ""


class TestNotionClientInit:
    """Tests for NotionClient initialization."""

    def test_missing_api_key_raises_error(self):
        """Test that missing API key raises NotionConfigError."""
        with patch("src.vibecoding.booktracker.sync.notion.get_config") as mock_config:
            mock_config.return_value.notion_api_key = None
            mock_config.return_value.notion_database_id = "db-123"

            with pytest.raises(NotionConfigError, match="NOTION_API_KEY"):
                NotionClient()

    def test_missing_database_id_raises_error(self):
        """Test that missing database ID raises NotionConfigError."""
        with patch("src.vibecoding.booktracker.sync.notion.get_config") as mock_config:
            mock_config.return_value.notion_api_key = "secret_key"
            mock_config.return_value.notion_database_id = None

            with pytest.raises(NotionConfigError, match="NOTION_DATABASE_ID"):
                NotionClient()


class TestBookToProperties:
    """Tests for converting BookCreate to Notion properties."""

    @pytest.fixture
    def mock_notion_client(self):
        """Create a NotionClient with mocked dependencies."""
        with patch("src.vibecoding.booktracker.sync.notion.get_config") as mock_config:
            mock_config.return_value.notion_api_key = "secret_key"
            mock_config.return_value.notion_database_id = "db-123"
            mock_config.return_value.notion_reading_logs_db_id = None

            with patch("src.vibecoding.booktracker.sync.notion.Client"):
                client = NotionClient()
                return client

    def test_basic_book_properties(self, mock_notion_client):
        """Test converting basic book fields to Notion properties."""
        book = BookCreate(
            title="The Great Gatsby",
            author="F. Scott Fitzgerald",
            status=BookStatus.COMPLETED,
            rating=5,
        )

        props = mock_notion_client._book_to_properties(book)

        assert props["Title"]["title"][0]["text"]["content"] == "The Great Gatsby"
        assert props["Author"]["rich_text"][0]["text"]["content"] == "F. Scott Fitzgerald"
        assert props["Status"]["select"]["name"] == "Read"
        assert props["Rating"]["number"] == 5

    def test_book_with_dates(self, mock_notion_client):
        """Test converting book with dates."""
        from datetime import date

        book = BookCreate(
            title="Test Book",
            author="Author",
            date_added=date(2025, 1, 1),
            date_finished=date(2025, 1, 15),
        )

        props = mock_notion_client._book_to_properties(book)

        assert props["Added"]["date"]["start"] == "2025-01-01"
        assert props["Date Finished"]["date"]["start"] == "2025-01-15"

    def test_book_with_tags(self, mock_notion_client):
        """Test converting book with tags."""
        book = BookCreate(
            title="Test Book",
            author="Author",
            tags=["fiction", "classic", "american"],
        )

        props = mock_notion_client._book_to_properties(book)

        tag_names = [t["name"] for t in props["Tags"]["multi_select"]]
        assert "fiction" in tag_names
        assert "classic" in tag_names
        assert "american" in tag_names


class TestNotionPageToBook:
    """Tests for converting NotionPage to BookCreate."""

    @pytest.fixture
    def mock_notion_client(self):
        """Create a NotionClient with mocked dependencies."""
        with patch("src.vibecoding.booktracker.sync.notion.get_config") as mock_config:
            mock_config.return_value.notion_api_key = "secret_key"
            mock_config.return_value.notion_database_id = "db-123"
            mock_config.return_value.notion_reading_logs_db_id = None

            with patch("src.vibecoding.booktracker.sync.notion.Client"):
                client = NotionClient()
                return client

    def test_convert_basic_page(self, mock_notion_client):
        """Test converting basic Notion page to BookCreate."""
        page = NotionPage(
            page_id="page-123",
            title="Test Book",
            author="Test Author",
            properties={
                "Status": {"select": {"name": "Read"}},
                "Rating": {"number": 4},
                "ISBN": {"rich_text": [{"plain_text": "1234567890"}]},
            },
            last_edited_time=datetime(2025, 1, 15, tzinfo=timezone.utc),
            created_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

        book = mock_notion_client.notion_page_to_book(page)

        assert book.title == "Test Book"
        assert book.author == "Test Author"
        assert book.status == BookStatus.COMPLETED
        assert book.rating == 4
        assert book.isbn == "1234567890"
        assert BookSource.NOTION in book.sources
        assert book.source_ids["notion"] == "page-123"

    def test_convert_page_with_dates(self, mock_notion_client):
        """Test converting page with dates."""
        page = NotionPage(
            page_id="page-456",
            title="Book with Dates",
            author="Author",
            properties={
                "Added": {"date": {"start": "2025-01-01"}},
                "Date Started": {"date": {"start": "2025-01-05"}},
                "Date Finished": {"date": {"start": "2025-01-20"}},
            },
            last_edited_time=datetime(2025, 1, 20, tzinfo=timezone.utc),
            created_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

        book = mock_notion_client.notion_page_to_book(page)

        assert book.date_added.isoformat() == "2025-01-01"
        assert book.date_started.isoformat() == "2025-01-05"
        assert book.date_finished.isoformat() == "2025-01-20"
