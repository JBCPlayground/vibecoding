"""Tests for Open Library API client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.vibecoding.booktracker.api.openlibrary import (
    OpenLibraryClient,
    OpenLibraryError,
    OpenLibraryRateLimitError,
    BookResult,
)
from src.vibecoding.booktracker.db.schemas import BookStatus, BookSource


class TestBookResult:
    """Tests for BookResult dataclass."""

    def test_basic_book_result(self):
        """Test creating a basic BookResult."""
        result = BookResult(
            title="The Great Gatsby",
            author="F. Scott Fitzgerald",
        )

        assert result.title == "The Great Gatsby"
        assert result.author == "F. Scott Fitzgerald"
        assert result.isbn is None
        assert result.authors == []

    def test_book_result_with_all_fields(self):
        """Test BookResult with all fields populated."""
        result = BookResult(
            title="1984",
            author="George Orwell",
            authors=["George Orwell"],
            isbn="0451524934",
            isbn13="9780451524935",
            olid="OL1168083W",
            cover_id=8575141,
            cover_url="https://covers.openlibrary.org/b/id/8575141-M.jpg",
            first_publish_year=1949,
            publisher="Signet Classic",
            publishers=["Signet Classic", "Penguin"],
            page_count=328,
            subjects=["Dystopian fiction", "Political fiction"],
            description="A dystopian novel...",
            language="eng",
        )

        assert result.isbn == "0451524934"
        assert result.isbn13 == "9780451524935"
        assert result.olid == "OL1168083W"
        assert result.first_publish_year == 1949
        assert len(result.subjects) == 2

    def test_to_book_create_basic(self):
        """Test converting BookResult to BookCreate."""
        result = BookResult(
            title="Test Book",
            author="Test Author",
            isbn="1234567890",
        )

        book = result.to_book_create()

        assert book.title == "Test Book"
        assert book.author == "Test Author"
        assert book.isbn == "1234567890"
        assert book.status == BookStatus.WISHLIST
        assert BookSource.OPENLIBRARY in book.sources

    def test_to_book_create_with_status(self):
        """Test converting with custom status."""
        result = BookResult(
            title="Test Book",
            author="Test Author",
        )

        book = result.to_book_create(status=BookStatus.READING)

        assert book.status == BookStatus.READING

    def test_to_book_create_with_multiple_authors(self):
        """Test converting with multiple authors."""
        result = BookResult(
            title="Test Book",
            author="Author One",
            authors=["Author One", "Author Two", "Author Three"],
        )

        book = result.to_book_create()

        assert book.author == "Author One"
        assert book.additional_authors == "Author Two, Author Three"

    def test_to_book_create_with_olid(self):
        """Test that OLID is stored in source_ids."""
        result = BookResult(
            title="Test Book",
            author="Test Author",
            olid="OL123456W",
        )

        book = result.to_book_create()

        assert book.source_ids["openlibrary"] == "OL123456W"

    def test_to_book_create_with_subjects(self):
        """Test that subjects are converted to tags (limited to 10)."""
        result = BookResult(
            title="Test Book",
            author="Test Author",
            subjects=[f"subject{i}" for i in range(15)],
        )

        book = result.to_book_create()

        assert len(book.tags) == 10
        assert book.tags[0] == "subject0"


class TestOpenLibraryClientInit:
    """Tests for OpenLibraryClient initialization."""

    def test_default_timeout(self):
        """Test default timeout value."""
        client = OpenLibraryClient()
        assert client.timeout == 10

    def test_custom_timeout(self):
        """Test custom timeout value."""
        client = OpenLibraryClient(timeout=30)
        assert client.timeout == 30

    def test_session_created(self):
        """Test that session is created with proper headers."""
        client = OpenLibraryClient()
        assert "User-Agent" in client._session.headers


class TestOpenLibraryClientSearch:
    """Tests for search functionality."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked session."""
        client = OpenLibraryClient()
        client._session = MagicMock()
        client._last_request_time = 0
        return client

    def test_search_returns_results(self, client):
        """Test basic search returns BookResults."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "docs": [
                {
                    "key": "/works/OL123W",
                    "title": "Test Book",
                    "author_name": ["Test Author"],
                    "first_publish_year": 2020,
                    "isbn": ["1234567890", "9781234567890"],
                    "cover_i": 12345,
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()
        client._session.get.return_value = mock_response

        results = client.search("test query")

        assert len(results) == 1
        assert results[0].title == "Test Book"
        assert results[0].author == "Test Author"
        assert results[0].isbn == "1234567890"
        assert results[0].isbn13 == "9781234567890"
        assert results[0].cover_id == 12345

    def test_search_with_author_filter(self, client):
        """Test search with author filter."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"docs": []}
        mock_response.raise_for_status = MagicMock()
        client._session.get.return_value = mock_response

        client.search("test", author="Test Author")

        call_args = client._session.get.call_args
        params = call_args[1]["params"]
        assert params["author"] == "Test Author"

    def test_search_empty_results(self, client):
        """Test search with no results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"docs": []}
        mock_response.raise_for_status = MagicMock()
        client._session.get.return_value = mock_response

        results = client.search("nonexistent book xyz123")

        assert results == []

    def test_search_handles_missing_fields(self, client):
        """Test search handles documents with missing fields."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "docs": [
                {
                    "key": "/works/OL456W",
                    "title": "Minimal Book",
                    # No author_name, no ISBN, no cover
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()
        client._session.get.return_value = mock_response

        results = client.search("minimal")

        assert len(results) == 1
        assert results[0].title == "Minimal Book"
        assert results[0].author == "Unknown Author"
        assert results[0].isbn is None

    def test_search_skips_documents_without_title(self, client):
        """Test that documents without title are skipped."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "docs": [
                {"key": "/works/OL789W"},  # No title
                {"key": "/works/OL101W", "title": "Valid Book"},
            ],
        }
        mock_response.raise_for_status = MagicMock()
        client._session.get.return_value = mock_response

        results = client.search("test")

        assert len(results) == 1
        assert results[0].title == "Valid Book"


class TestOpenLibraryClientISBN:
    """Tests for ISBN lookup."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked session."""
        client = OpenLibraryClient()
        client._session = MagicMock()
        client._last_request_time = 0
        return client

    def test_get_by_isbn_found(self, client):
        """Test ISBN lookup returns BookResult."""
        # Mock edition response
        edition_response = MagicMock()
        edition_response.json.return_value = {
            "key": "/books/OL123M",
            "title": "ISBN Book",
            "authors": [{"key": "/authors/OL456A"}],
            "isbn_10": ["1234567890"],
            "isbn_13": ["9781234567890"],
            "covers": [12345],
            "publishers": ["Test Publisher"],
            "number_of_pages": 200,
            "publish_date": "2020",
        }
        edition_response.raise_for_status = MagicMock()

        # Mock author response
        author_response = MagicMock()
        author_response.json.return_value = {"name": "Test Author"}
        author_response.raise_for_status = MagicMock()

        client._session.get.side_effect = [edition_response, author_response]

        result = client.get_by_isbn("1234567890")

        assert result is not None
        assert result.title == "ISBN Book"
        assert result.author == "Test Author"
        assert result.isbn == "1234567890"
        assert result.page_count == 200
        assert result.publisher == "Test Publisher"

    def test_get_by_isbn_not_found(self, client):
        """Test ISBN lookup returns None when not found."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=404)
        )
        client._session.get.return_value = mock_response

        result = client.get_by_isbn("0000000000")

        assert result is None

    def test_get_by_isbn_cleans_input(self, client):
        """Test that ISBN input is cleaned."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "key": "/books/OL123M",
            "title": "Test Book",
        }
        mock_response.raise_for_status = MagicMock()
        client._session.get.return_value = mock_response

        client.get_by_isbn("978-1-23456-789-0")

        call_url = client._session.get.call_args[0][0]
        assert "9781234567890" in call_url


class TestOpenLibraryClientCover:
    """Tests for cover image functionality."""

    def test_get_cover_url_by_id(self):
        """Test getting cover URL by cover ID."""
        client = OpenLibraryClient()

        url = client.get_cover_url(cover_id=12345)

        assert url == "https://covers.openlibrary.org/b/id/12345-M.jpg"

    def test_get_cover_url_by_isbn(self):
        """Test getting cover URL by ISBN."""
        client = OpenLibraryClient()

        url = client.get_cover_url(isbn="1234567890")

        assert url == "https://covers.openlibrary.org/b/isbn/1234567890-M.jpg"

    def test_get_cover_url_by_olid(self):
        """Test getting cover URL by OLID."""
        client = OpenLibraryClient()

        url = client.get_cover_url(olid="OL123W")

        assert url == "https://covers.openlibrary.org/b/olid/OL123W-M.jpg"

    def test_get_cover_url_different_sizes(self):
        """Test different cover sizes."""
        client = OpenLibraryClient()

        small = client.get_cover_url(cover_id=12345, size="S")
        large = client.get_cover_url(cover_id=12345, size="L")

        assert "-S.jpg" in small
        assert "-L.jpg" in large

    def test_get_cover_url_none(self):
        """Test get_cover_url returns None with no identifiers."""
        client = OpenLibraryClient()

        url = client.get_cover_url()

        assert url is None


class TestOpenLibraryClientErrors:
    """Tests for error handling."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked session."""
        client = OpenLibraryClient()
        client._session = MagicMock()
        client._last_request_time = 0
        return client

    def test_timeout_raises_error(self, client):
        """Test that timeout raises OpenLibraryError."""
        client._session.get.side_effect = requests.exceptions.Timeout()

        with pytest.raises(OpenLibraryError, match="timed out"):
            client.search("test")

    def test_rate_limit_raises_error(self, client):
        """Test that 429 response raises OpenLibraryRateLimitError."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        error = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = error
        client._session.get.return_value = mock_response

        with pytest.raises(OpenLibraryRateLimitError, match="Rate limited"):
            client.search("test")

    def test_http_error_raises_error(self, client):
        """Test that HTTP errors raise OpenLibraryError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        error = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = error
        client._session.get.return_value = mock_response

        with pytest.raises(OpenLibraryError, match="HTTP error"):
            client.search("test")

    def test_connection_error_raises_error(self, client):
        """Test that connection errors raise OpenLibraryError."""
        client._session.get.side_effect = requests.exceptions.ConnectionError()

        with pytest.raises(OpenLibraryError, match="Request failed"):
            client.search("test")


class TestOpenLibraryClientWork:
    """Tests for work lookup."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked session."""
        client = OpenLibraryClient()
        client._session = MagicMock()
        client._last_request_time = 0
        return client

    def test_get_work_found(self, client):
        """Test work lookup returns BookResult."""
        # Mock work response
        work_response = MagicMock()
        work_response.json.return_value = {
            "key": "/works/OL123W",
            "title": "Work Title",
            "authors": [{"author": {"key": "/authors/OL456A"}}],
            "covers": [12345],
            "description": "A great book about...",
            "subjects": ["Fiction", "Adventure"],
        }
        work_response.raise_for_status = MagicMock()

        # Mock author response
        author_response = MagicMock()
        author_response.json.return_value = {"name": "Work Author"}
        author_response.raise_for_status = MagicMock()

        client._session.get.side_effect = [work_response, author_response]

        result = client.get_work("OL123W")

        assert result is not None
        assert result.title == "Work Title"
        assert result.author == "Work Author"
        assert result.description == "A great book about..."
        assert "Fiction" in result.subjects

    def test_get_work_normalizes_id(self, client):
        """Test that work ID is normalized."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "key": "/works/OL123W",
            "title": "Test",
        }
        mock_response.raise_for_status = MagicMock()
        client._session.get.return_value = mock_response

        # Should add OL prefix and W suffix if missing
        client.get_work("123")

        call_url = client._session.get.call_args[0][0]
        assert "OL123W" in call_url

    def test_get_work_not_found(self, client):
        """Test work lookup returns None when not found."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=404)
        )
        client._session.get.return_value = mock_response

        result = client.get_work("OL99999999W")

        assert result is None


class TestOpenLibraryRateLimiting:
    """Tests for rate limiting behavior."""

    def test_rate_limit_enforced(self):
        """Test that requests are rate limited."""
        import time

        client = OpenLibraryClient()
        client._session = MagicMock()
        client._min_request_interval = 0.1  # Short interval for testing

        mock_response = MagicMock()
        mock_response.json.return_value = {"docs": []}
        mock_response.raise_for_status = MagicMock()
        client._session.get.return_value = mock_response

        start = time.time()

        # Make two requests
        client.search("test1")
        client.search("test2")

        elapsed = time.time() - start

        # Should have waited at least min_request_interval
        assert elapsed >= 0.1
