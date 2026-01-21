"""Open Library API client for book metadata lookup.

Open Library (openlibrary.org) provides free book metadata including:
- Search by title/author
- ISBN lookup
- Cover images
- Book descriptions
- Author information

No API key required.
"""

import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus

import requests

from ..db.schemas import BookCreate, BookSource, BookStatus


class OpenLibraryError(Exception):
    """Base exception for Open Library API errors."""

    pass


class OpenLibraryRateLimitError(OpenLibraryError):
    """Raised when rate limited by Open Library."""

    pass


@dataclass
class BookResult:
    """A book result from Open Library search."""

    title: str
    author: str
    authors: list[str] = field(default_factory=list)
    isbn: Optional[str] = None
    isbn13: Optional[str] = None
    olid: Optional[str] = None  # Open Library ID (e.g., OL123456W)
    cover_id: Optional[int] = None
    cover_url: Optional[str] = None
    first_publish_year: Optional[int] = None
    publisher: Optional[str] = None
    publishers: list[str] = field(default_factory=list)
    page_count: Optional[int] = None
    subjects: list[str] = field(default_factory=list)
    description: Optional[str] = None
    language: Optional[str] = None

    def to_book_create(self, status: BookStatus = BookStatus.WISHLIST) -> BookCreate:
        """Convert to BookCreate schema."""
        return BookCreate(
            title=self.title,
            author=self.author,
            additional_authors=", ".join(self.authors[1:]) if len(self.authors) > 1 else None,
            isbn=self.isbn,
            isbn13=self.isbn13,
            cover=self.cover_url,
            publication_year=self.first_publish_year,
            publisher=self.publisher or (self.publishers[0] if self.publishers else None),
            page_count=self.page_count,
            description=self.description,
            language=self.language,
            tags=self.subjects[:10] if self.subjects else None,
            status=status,
            sources=[BookSource.OPENLIBRARY],
            source_ids={"openlibrary": self.olid} if self.olid else {},
        )


class OpenLibraryClient:
    """Client for Open Library API."""

    BASE_URL = "https://openlibrary.org"
    COVERS_URL = "https://covers.openlibrary.org"

    def __init__(self, timeout: int = 10):
        """Initialize client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "BookTracker/1.0 (https://github.com/user/booktracker)"
        })
        self._last_request_time = 0.0
        self._min_request_interval = 0.5  # Be nice to free API

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        """Make GET request with error handling."""
        self._rate_limit()
        try:
            response = self._session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            raise OpenLibraryError("Request timed out")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                raise OpenLibraryRateLimitError("Rate limited by Open Library")
            raise OpenLibraryError(f"HTTP error: {e.response.status_code}")
        except requests.exceptions.RequestException as e:
            raise OpenLibraryError(f"Request failed: {e}")

    # ========================================================================
    # Search Operations
    # ========================================================================

    def search(
        self,
        query: str,
        author: Optional[str] = None,
        limit: int = 10,
    ) -> list[BookResult]:
        """Search for books by title (and optionally author).

        Args:
            query: Search query (title or general search)
            author: Filter by author name
            limit: Maximum results to return

        Returns:
            List of BookResult objects
        """
        params = {
            "q": query,
            "limit": limit,
            "fields": "key,title,author_name,first_publish_year,isbn,publisher,cover_i,number_of_pages_median,subject,language",
        }

        if author:
            params["author"] = author

        url = f"{self.BASE_URL}/search.json"
        data = self._get(url, params)

        results = []
        for doc in data.get("docs", []):
            result = self._doc_to_result(doc)
            if result:
                results.append(result)

        return results

    def search_by_title(self, title: str, limit: int = 10) -> list[BookResult]:
        """Search for books by exact title.

        Args:
            title: Book title to search
            limit: Maximum results

        Returns:
            List of BookResult objects
        """
        params = {
            "title": title,
            "limit": limit,
            "fields": "key,title,author_name,first_publish_year,isbn,publisher,cover_i,number_of_pages_median,subject,language",
        }

        url = f"{self.BASE_URL}/search.json"
        data = self._get(url, params)

        results = []
        for doc in data.get("docs", []):
            result = self._doc_to_result(doc)
            if result:
                results.append(result)

        return results

    def search_by_author(self, author: str, limit: int = 10) -> list[BookResult]:
        """Search for books by author.

        Args:
            author: Author name
            limit: Maximum results

        Returns:
            List of BookResult objects
        """
        params = {
            "author": author,
            "limit": limit,
            "fields": "key,title,author_name,first_publish_year,isbn,publisher,cover_i,number_of_pages_median,subject,language",
        }

        url = f"{self.BASE_URL}/search.json"
        data = self._get(url, params)

        results = []
        for doc in data.get("docs", []):
            result = self._doc_to_result(doc)
            if result:
                results.append(result)

        return results

    def _doc_to_result(self, doc: dict) -> Optional[BookResult]:
        """Convert search document to BookResult."""
        title = doc.get("title")
        if not title:
            return None

        authors = doc.get("author_name", [])
        author = authors[0] if authors else "Unknown Author"

        # Extract ISBNs
        isbns = doc.get("isbn", [])
        isbn = None
        isbn13 = None
        for i in isbns:
            if len(i) == 10 and not isbn:
                isbn = i
            elif len(i) == 13 and not isbn13:
                isbn13 = i
            if isbn and isbn13:
                break

        # Extract Open Library ID from key (e.g., "/works/OL123456W")
        key = doc.get("key", "")
        olid = key.split("/")[-1] if key else None

        # Cover URL
        cover_id = doc.get("cover_i")
        cover_url = None
        if cover_id:
            cover_url = f"{self.COVERS_URL}/b/id/{cover_id}-M.jpg"

        # Subjects/tags
        subjects = doc.get("subject", [])[:20]

        # Languages
        languages = doc.get("language", [])
        language = languages[0] if languages else None

        return BookResult(
            title=title,
            author=author,
            authors=authors,
            isbn=isbn,
            isbn13=isbn13,
            olid=olid,
            cover_id=cover_id,
            cover_url=cover_url,
            first_publish_year=doc.get("first_publish_year"),
            publishers=doc.get("publisher", []),
            page_count=doc.get("number_of_pages_median"),
            subjects=subjects,
            language=language,
        )

    # ========================================================================
    # ISBN Lookup
    # ========================================================================

    def get_by_isbn(self, isbn: str) -> Optional[BookResult]:
        """Look up a book by ISBN.

        Args:
            isbn: ISBN-10 or ISBN-13

        Returns:
            BookResult if found, None otherwise
        """
        # Clean ISBN
        isbn = isbn.replace("-", "").replace(" ", "")

        url = f"{self.BASE_URL}/isbn/{isbn}.json"
        try:
            data = self._get(url)
        except OpenLibraryError:
            return None

        if not data:
            return None

        return self._edition_to_result(data, isbn)

    def _edition_to_result(self, data: dict, isbn: str) -> BookResult:
        """Convert edition data to BookResult."""
        title = data.get("title", "Unknown Title")

        # Get authors (need to fetch from works or authors endpoint)
        author_keys = data.get("authors", [])
        authors = []
        for ak in author_keys[:3]:  # Limit API calls
            key = ak.get("key", "")
            if key:
                author_name = self._get_author_name(key)
                if author_name:
                    authors.append(author_name)

        author = authors[0] if authors else "Unknown Author"

        # Extract ISBNs from edition
        isbn10 = None
        isbn13 = None
        for i in data.get("isbn_10", []):
            isbn10 = i
            break
        for i in data.get("isbn_13", []):
            isbn13 = i
            break

        # Use provided ISBN if not found
        if len(isbn) == 10 and not isbn10:
            isbn10 = isbn
        elif len(isbn) == 13 and not isbn13:
            isbn13 = isbn

        # Cover
        covers = data.get("covers", [])
        cover_id = covers[0] if covers else None
        cover_url = f"{self.COVERS_URL}/b/id/{cover_id}-M.jpg" if cover_id else None

        # Publishers
        publishers = data.get("publishers", [])

        # Page count
        page_count = data.get("number_of_pages")

        # Publication year
        publish_date = data.get("publish_date", "")
        pub_year = None
        if publish_date:
            # Try to extract year from various formats
            import re
            match = re.search(r"\d{4}", publish_date)
            if match:
                pub_year = int(match.group())

        # Description
        description = None
        desc_data = data.get("description")
        if isinstance(desc_data, str):
            description = desc_data
        elif isinstance(desc_data, dict):
            description = desc_data.get("value")

        # Languages
        languages = data.get("languages", [])
        language = None
        if languages:
            lang_key = languages[0].get("key", "")
            language = lang_key.split("/")[-1] if lang_key else None

        # Subjects
        subjects = data.get("subjects", [])

        # Open Library ID
        key = data.get("key", "")
        olid = key.split("/")[-1] if key else None

        return BookResult(
            title=title,
            author=author,
            authors=authors,
            isbn=isbn10,
            isbn13=isbn13,
            olid=olid,
            cover_id=cover_id,
            cover_url=cover_url,
            first_publish_year=pub_year,
            publishers=publishers,
            publisher=publishers[0] if publishers else None,
            page_count=page_count,
            subjects=subjects[:20],
            description=description,
            language=language,
        )

    def _get_author_name(self, author_key: str) -> Optional[str]:
        """Fetch author name from Open Library.

        Args:
            author_key: Author key (e.g., "/authors/OL123456A")

        Returns:
            Author name or None
        """
        url = f"{self.BASE_URL}{author_key}.json"
        try:
            data = self._get(url)
            return data.get("name")
        except OpenLibraryError:
            return None

    # ========================================================================
    # Work/Edition Details
    # ========================================================================

    def get_work(self, work_id: str) -> Optional[BookResult]:
        """Get detailed work information.

        Args:
            work_id: Open Library work ID (e.g., "OL123456W")

        Returns:
            BookResult with full details
        """
        # Ensure proper format
        if not work_id.startswith("OL"):
            work_id = f"OL{work_id}"
        if not work_id.endswith("W"):
            work_id = f"{work_id}W"

        url = f"{self.BASE_URL}/works/{work_id}.json"
        try:
            data = self._get(url)
        except OpenLibraryError:
            return None

        if not data:
            return None

        title = data.get("title", "Unknown Title")

        # Get authors
        author_keys = data.get("authors", [])
        authors = []
        for ak in author_keys[:3]:
            key = ak.get("author", {}).get("key", "")
            if key:
                author_name = self._get_author_name(key)
                if author_name:
                    authors.append(author_name)

        author = authors[0] if authors else "Unknown Author"

        # Covers
        covers = data.get("covers", [])
        cover_id = covers[0] if covers else None
        cover_url = f"{self.COVERS_URL}/b/id/{cover_id}-M.jpg" if cover_id else None

        # Description
        description = None
        desc_data = data.get("description")
        if isinstance(desc_data, str):
            description = desc_data
        elif isinstance(desc_data, dict):
            description = desc_data.get("value")

        # Subjects
        subjects = data.get("subjects", [])

        return BookResult(
            title=title,
            author=author,
            authors=authors,
            olid=work_id,
            cover_id=cover_id,
            cover_url=cover_url,
            first_publish_year=data.get("first_publish_date"),
            subjects=subjects[:20],
            description=description,
        )

    # ========================================================================
    # Cover Images
    # ========================================================================

    def get_cover_url(
        self,
        isbn: Optional[str] = None,
        olid: Optional[str] = None,
        cover_id: Optional[int] = None,
        size: str = "M",
    ) -> Optional[str]:
        """Get cover image URL.

        Args:
            isbn: Book ISBN
            olid: Open Library ID
            cover_id: Cover ID from search results
            size: Image size - S (small), M (medium), L (large)

        Returns:
            Cover image URL or None
        """
        if cover_id:
            return f"{self.COVERS_URL}/b/id/{cover_id}-{size}.jpg"
        elif isbn:
            return f"{self.COVERS_URL}/b/isbn/{isbn}-{size}.jpg"
        elif olid:
            return f"{self.COVERS_URL}/b/olid/{olid}-{size}.jpg"
        return None

    def download_cover(
        self,
        url: str,
    ) -> Optional[bytes]:
        """Download cover image.

        Args:
            url: Cover image URL

        Returns:
            Image bytes or None
        """
        self._rate_limit()
        try:
            response = self._session.get(url, timeout=self.timeout)
            response.raise_for_status()
            # Check if we got a valid image (not placeholder)
            if len(response.content) < 1000:
                return None  # Likely a placeholder
            return response.content
        except requests.exceptions.RequestException:
            return None
