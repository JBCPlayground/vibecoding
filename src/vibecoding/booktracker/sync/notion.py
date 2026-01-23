"""Notion API client wrapper for book database operations.

Handles all Notion API interactions with proper error handling,
rate limiting, and data mapping between local and Notion schemas.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from notion_client import Client
from notion_client.errors import APIResponseError

from ..config import get_config
from ..db.schemas import BookCreate, BookSource, BookStatus, BookUpdate


class NotionError(Exception):
    """Base exception for Notion API errors."""

    pass


class NotionConfigError(NotionError):
    """Raised when Notion is not properly configured."""

    pass


class NotionRateLimitError(NotionError):
    """Raised when rate limited by Notion API."""

    def __init__(self, retry_after: int = 1):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s")


@dataclass
class NotionPage:
    """Represents a Notion page (book record)."""

    page_id: str
    title: str
    author: str
    properties: dict[str, Any]
    last_edited_time: datetime
    created_time: datetime

    @classmethod
    def from_api_response(cls, page: dict) -> "NotionPage":
        """Create NotionPage from API response."""
        props = page.get("properties", {})

        # Extract title
        title = ""
        title_prop = props.get("Title", {})
        if title_prop.get("title"):
            title = "".join(t.get("plain_text", "") for t in title_prop["title"])

        # Extract author
        author = ""
        author_prop = props.get("Author", {})
        if author_prop.get("rich_text"):
            author = "".join(t.get("plain_text", "") for t in author_prop["rich_text"])

        return cls(
            page_id=page["id"],
            title=title,
            author=author,
            properties=props,
            last_edited_time=datetime.fromisoformat(
                page["last_edited_time"].replace("Z", "+00:00")
            ),
            created_time=datetime.fromisoformat(
                page["created_time"].replace("Z", "+00:00")
            ),
        )


# Status mapping: Local -> Notion
STATUS_TO_NOTION = {
    BookStatus.READING: "Borrowed",
    BookStatus.COMPLETED: "Read",
    BookStatus.SKIMMED: "Skimmed",
    BookStatus.ON_HOLD: "On Hold",
    BookStatus.WISHLIST: "Want to Read",
    BookStatus.DNF: "DNF",
    BookStatus.OWNED: "Owned",
}

# Status mapping: Notion -> Local
NOTION_TO_STATUS = {
    "Borrowed": BookStatus.READING,
    "Read": BookStatus.COMPLETED,
    "Skimmed": BookStatus.SKIMMED,
    "On Hold": BookStatus.ON_HOLD,
    "Want to Read": BookStatus.WISHLIST,
    "DNF": BookStatus.DNF,
    "Owned": BookStatus.OWNED,
}


class NotionClient:
    """Client for interacting with Notion Books database."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        database_id: Optional[str] = None,
        reading_logs_db_id: Optional[str] = None,
    ):
        """Initialize Notion client.

        Args:
            api_key: Notion API key (uses config if not provided)
            database_id: Books database ID (uses config if not provided)
            reading_logs_db_id: Reading logs database ID (uses config if not provided)
        """
        config = get_config()

        self.api_key = api_key or config.notion_api_key
        self.database_id = database_id or config.notion_database_id
        self.reading_logs_db_id = reading_logs_db_id or config.notion_reading_logs_db_id

        if not self.api_key:
            raise NotionConfigError("NOTION_API_KEY not set")
        if not self.database_id:
            raise NotionConfigError("NOTION_DATABASE_ID not set")

        self._client = Client(auth=self.api_key)
        self._last_request_time = 0.0
        self._min_request_interval = 0.35  # ~3 requests per second (Notion limit)

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _handle_api_error(self, e: APIResponseError) -> None:
        """Handle Notion API errors."""
        if e.status == 429:
            retry_after = int(e.headers.get("Retry-After", 1))
            raise NotionRateLimitError(retry_after)
        # Message is stored in args[0], not as .message attribute
        error_msg = str(e.args[0]) if e.args else "Unknown error"
        raise NotionError(f"Notion API error: {e.code} - {error_msg}")

    # ========================================================================
    # Query Operations
    # ========================================================================

    def query_all_books(self, page_size: int = 100) -> list[NotionPage]:
        """Query all books from the Notion database.

        Args:
            page_size: Number of results per page (max 100)

        Returns:
            List of NotionPage objects
        """
        books = []
        start_cursor = None

        while True:
            self._rate_limit()
            try:
                response = self._client.data_sources.query(
                    data_source_id=self.database_id,
                    page_size=page_size,
                    start_cursor=start_cursor,
                )
            except APIResponseError as e:
                self._handle_api_error(e)
                raise

            for page in response.get("results", []):
                books.append(NotionPage.from_api_response(page))

            if not response.get("has_more"):
                break

            start_cursor = response.get("next_cursor")

        return books

    def get_page(self, page_id: str) -> NotionPage:
        """Get a single page by ID.

        Args:
            page_id: Notion page ID

        Returns:
            NotionPage object
        """
        self._rate_limit()
        try:
            response = self._client.pages.retrieve(page_id=page_id)
            return NotionPage.from_api_response(response)
        except APIResponseError as e:
            self._handle_api_error(e)
            raise

    def query_books_modified_since(
        self, since: datetime, page_size: int = 100
    ) -> list[NotionPage]:
        """Query books modified since a given timestamp.

        Args:
            since: Only return books modified after this time
            page_size: Number of results per page

        Returns:
            List of NotionPage objects
        """
        books = []
        start_cursor = None

        while True:
            self._rate_limit()
            try:
                response = self._client.data_sources.query(
                    data_source_id=self.database_id,
                    page_size=page_size,
                    start_cursor=start_cursor,
                    filter={
                        "timestamp": "last_edited_time",
                        "last_edited_time": {
                            "after": since.isoformat(),
                        },
                    },
                )
            except APIResponseError as e:
                self._handle_api_error(e)
                raise

            for page in response.get("results", []):
                books.append(NotionPage.from_api_response(page))

            if not response.get("has_more"):
                break

            start_cursor = response.get("next_cursor")

        return books

    # ========================================================================
    # Create Operations
    # ========================================================================

    def create_book(self, book: BookCreate) -> str:
        """Create a new book in Notion.

        Args:
            book: BookCreate schema with book data

        Returns:
            Notion page ID of created book
        """
        properties = self._book_to_properties(book)

        self._rate_limit()
        try:
            response = self._client.pages.create(
                parent={"data_source_id": self.database_id},
                properties=properties,
            )
            return response["id"]
        except APIResponseError as e:
            self._handle_api_error(e)
            raise

    def _book_to_properties(self, book: BookCreate) -> dict[str, Any]:
        """Convert BookCreate to Notion properties format."""
        props: dict[str, Any] = {}

        # Title (required)
        props["Title"] = {"title": [{"text": {"content": book.title}}]}

        # Author
        if book.author:
            props["Author"] = {"rich_text": [{"text": {"content": book.author}}]}

        # Author Sort
        if book.author_sort:
            props["Author Sort"] = {
                "rich_text": [{"text": {"content": book.author_sort}}]
            }

        # Title Sort
        if book.title_sort:
            props["Title Sort"] = {
                "rich_text": [{"text": {"content": book.title_sort}}]
            }

        # Status
        notion_status = STATUS_TO_NOTION.get(book.status, "Want to Read")
        props["Status"] = {"select": {"name": notion_status}}

        # Rating
        if book.rating:
            props["Rating"] = {"number": book.rating}

        # Dates
        if book.date_added:
            props["Date Added"] = {"date": {"start": book.date_added.isoformat()}}

        if book.date_started:
            props["Date Started"] = {"date": {"start": book.date_started.isoformat()}}

        if book.date_finished:
            props["Date Finished"] = {
                "date": {"start": book.date_finished.isoformat()}
            }

        # ISBN
        if book.isbn:
            props["ISBN"] = {"rich_text": [{"text": {"content": book.isbn}}]}

        if book.isbn13:
            props["ISBN13"] = {"rich_text": [{"text": {"content": book.isbn13}}]}

        # Page Count
        if book.page_count:
            props["Page Count"] = {"number": book.page_count}

        # Publisher
        if book.publisher:
            props["Publisher"] = {"rich_text": [{"text": {"content": book.publisher}}]}

        # Publication Year
        if book.publication_year:
            props["Publication Year"] = {"number": book.publication_year}

        # Series
        if book.series:
            props["Series"] = {"rich_text": [{"text": {"content": book.series}}]}

        if book.series_index:
            props["Series Index"] = {"number": book.series_index}

        # Format
        if book.format:
            props["Format"] = {"select": {"name": book.format}}

        # URLs
        if book.amazon_url:
            props["Amazon URL"] = {"url": book.amazon_url}

        if book.goodreads_url:
            props["Goodreads URL"] = {"url": book.goodreads_url}

        if book.library_url:
            props["Library URL"] = {"url": book.library_url}

        # Description
        if book.description:
            # Truncate to Notion's limit (2000 chars for rich_text)
            desc = book.description[:2000]
            props["Description"] = {"rich_text": [{"text": {"content": desc}}]}

        # Notes
        if book.comments:
            comments = book.comments[:2000]
            props["Notes"] = {"rich_text": [{"text": {"content": comments}}]}

        # Progress
        if book.progress:
            props["Progress"] = {"rich_text": [{"text": {"content": book.progress}}]}

        # Read Next
        if book.read_next is not None:
            props["Read Next"] = {"checkbox": book.read_next}

        # Recommended By
        if book.recommended_by:
            props["Recommended By"] = {
                "rich_text": [{"text": {"content": book.recommended_by}}]
            }

        # Library Source
        if book.library_source:
            props["Library Source"] = {"select": {"name": book.library_source}}

        # Tags (multi-select)
        if book.tags:
            props["Tags"] = {"multi_select": [{"name": tag} for tag in book.tags[:10]]}

        return props

    # ========================================================================
    # Update Operations
    # ========================================================================

    def update_book(self, page_id: str, update: BookUpdate) -> None:
        """Update an existing book in Notion.

        Args:
            page_id: Notion page ID to update
            update: BookUpdate with fields to change
        """
        properties = self._update_to_properties(update)

        if not properties:
            return  # Nothing to update

        self._rate_limit()
        try:
            self._client.pages.update(
                page_id=page_id,
                properties=properties,
            )
        except APIResponseError as e:
            self._handle_api_error(e)
            raise

    def _update_to_properties(self, update: BookUpdate) -> dict[str, Any]:
        """Convert BookUpdate to Notion properties format."""
        props: dict[str, Any] = {}
        update_data = update.model_dump(exclude_unset=True)

        if "title" in update_data and update_data["title"]:
            props["Title"] = {"title": [{"text": {"content": update_data["title"]}}]}

        if "author" in update_data and update_data["author"]:
            props["Author"] = {
                "rich_text": [{"text": {"content": update_data["author"]}}]
            }

        if "status" in update_data and update_data["status"]:
            notion_status = STATUS_TO_NOTION.get(update_data["status"], "Want to Read")
            props["Status"] = {"select": {"name": notion_status}}

        if "rating" in update_data:
            if update_data["rating"] is not None:
                props["Rating"] = {"number": update_data["rating"]}
            else:
                props["Rating"] = {"number": None}

        if "date_finished" in update_data:
            if update_data["date_finished"]:
                props["Date Finished"] = {
                    "date": {"start": update_data["date_finished"].isoformat()}
                }
            else:
                props["Date Finished"] = {"date": None}

        if "progress" in update_data:
            if update_data["progress"]:
                props["Progress"] = {
                    "rich_text": [{"text": {"content": update_data["progress"]}}]
                }
            else:
                props["Progress"] = {"rich_text": []}

        if "library_due_date" in update_data:
            if update_data["library_due_date"]:
                # Store in a custom property or Comments
                pass  # Notion schema may need adjustment

        if "pickup_location" in update_data:
            if update_data["pickup_location"]:
                # Store in a custom property
                pass

        return props

    # ========================================================================
    # Delete Operations
    # ========================================================================

    def archive_book(self, page_id: str) -> None:
        """Archive (soft delete) a book in Notion.

        Args:
            page_id: Notion page ID to archive
        """
        self._rate_limit()
        try:
            self._client.pages.update(
                page_id=page_id,
                archived=True,
            )
        except APIResponseError as e:
            self._handle_api_error(e)
            raise

    # ========================================================================
    # Conversion Helpers
    # ========================================================================

    def notion_page_to_book(self, page: NotionPage) -> BookCreate:
        """Convert a NotionPage to BookCreate schema.

        Args:
            page: NotionPage from API

        Returns:
            BookCreate with data from Notion
        """
        props = page.properties

        # Extract status
        status = BookStatus.WISHLIST
        status_prop = props.get("Status", {})
        if status_prop.get("select"):
            notion_status = status_prop["select"].get("name", "")
            status = NOTION_TO_STATUS.get(notion_status, BookStatus.WISHLIST)

        # Extract rating
        rating = None
        rating_prop = props.get("Rating", {})
        if rating_prop.get("number") is not None:
            rating = int(rating_prop["number"])

        # Extract dates
        date_added = None
        added_prop = props.get("Date Added", {})
        if added_prop.get("date"):
            date_added = self._parse_notion_date(added_prop["date"].get("start"))

        date_started = None
        started_prop = props.get("Date Started", {})
        if started_prop.get("date"):
            date_started = self._parse_notion_date(started_prop["date"].get("start"))

        date_finished = None
        finished_prop = props.get("Date Finished", {})
        if finished_prop.get("date"):
            date_finished = self._parse_notion_date(finished_prop["date"].get("start"))

        # Extract text fields
        def get_rich_text(prop_name: str) -> Optional[str]:
            prop = props.get(prop_name, {})
            if prop.get("rich_text"):
                return "".join(t.get("plain_text", "") for t in prop["rich_text"])
            return None

        # Extract numbers
        def get_number(prop_name: str) -> Optional[int]:
            prop = props.get(prop_name, {})
            val = prop.get("number")
            return int(val) if val is not None else None

        # Extract select
        def get_select(prop_name: str) -> Optional[str]:
            prop = props.get(prop_name, {})
            if prop.get("select"):
                return prop["select"].get("name")
            return None

        # Extract URL
        def get_url(prop_name: str) -> Optional[str]:
            prop = props.get(prop_name, {})
            return prop.get("url")

        # Extract checkbox
        def get_checkbox(prop_name: str) -> bool:
            prop = props.get(prop_name, {})
            return prop.get("checkbox", False)

        # Extract multi-select
        def get_multi_select(prop_name: str) -> list[str]:
            prop = props.get(prop_name, {})
            if prop.get("multi_select"):
                return [item.get("name", "") for item in prop["multi_select"]]
            return []

        return BookCreate(
            title=page.title,
            title_sort=get_rich_text("Title Sort"),
            author=page.author,
            author_sort=get_rich_text("Author Sort"),
            status=status,
            rating=rating,
            date_added=date_added,
            date_started=date_started,
            date_finished=date_finished,
            isbn=get_rich_text("ISBN"),
            isbn13=get_rich_text("ISBN13"),
            page_count=get_number("Page Count"),
            description=get_rich_text("Description"),
            publisher=get_rich_text("Publisher"),
            publication_year=get_number("Publication Year"),
            series=get_rich_text("Series"),
            series_index=get_number("Series Index"),
            format=get_select("Format"),
            library_source=get_select("Library Source"),
            amazon_url=get_url("Amazon URL"),
            goodreads_url=get_url("Goodreads URL"),
            library_url=get_url("Library URL"),
            comments=get_rich_text("Notes"),
            progress=get_rich_text("Progress"),
            read_next=get_checkbox("Read Next"),
            recommended_by=get_rich_text("Recommended By"),
            tags=get_multi_select("Tags"),
            sources=[BookSource.NOTION],
            source_ids={"notion": page.page_id},
        )

    def _parse_notion_date(self, date_str: Optional[str]) -> Optional[Any]:
        """Parse Notion date string to date object."""
        if not date_str:
            return None
        try:
            from datetime import date

            # Notion dates can be "YYYY-MM-DD" or full ISO
            if "T" in date_str:
                return datetime.fromisoformat(
                    date_str.replace("Z", "+00:00")
                ).date()
            return date.fromisoformat(date_str)
        except ValueError:
            return None
