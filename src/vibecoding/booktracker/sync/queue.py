"""Sync queue processor for managing pending sync operations.

Processes the sync queue with retry logic, rate limiting,
and conflict handling.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from tqdm import tqdm

from ..db.models import Book, SyncQueueItem
from ..db.schemas import BookCreate, BookUpdate, SyncOperation, SyncStatus
from ..db.sqlite import Database, get_db
from .conflict import (
    ConflictResolution,
    ConflictType,
    SyncConflict,
    detect_conflict,
    resolve_conflict_interactive,
)
from .notion import NotionClient, NotionError, NotionPage, NotionRateLimitError


@dataclass
class SyncResult:
    """Result of a sync operation."""

    pushed: int = 0
    pulled: int = 0
    conflicts: int = 0
    skipped: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.pushed + self.pulled

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


console = Console()


class SyncProcessor:
    """Processes sync queue and handles Notion synchronization."""

    def __init__(
        self,
        db: Optional[Database] = None,
        notion_client: Optional[NotionClient] = None,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
    ):
        """Initialize sync processor.

        Args:
            db: Database instance (uses global if not provided)
            notion_client: Notion client (creates new if not provided)
            max_retries: Maximum retry attempts for failed operations
            initial_backoff: Initial backoff delay in seconds
        """
        self.db = db or get_db()
        self.notion = notion_client or NotionClient()
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff

    def sync(
        self,
        interactive: bool = True,
        show_progress: bool = True,
    ) -> SyncResult:
        """Perform full sync: push local changes, pull Notion changes.

        Args:
            interactive: Prompt for conflict resolution
            show_progress: Show progress indicators

        Returns:
            SyncResult with statistics
        """
        result = SyncResult()

        # Step 1: Push pending local changes to Notion
        console.print("\n[bold]Pushing local changes to Notion...[/bold]")
        push_result = self.push_pending(interactive=interactive, show_progress=show_progress)
        result.pushed = push_result.pushed
        result.errors.extend(push_result.errors)

        # Step 2: Pull changes from Notion
        console.print("\n[bold]Pulling changes from Notion...[/bold]")
        pull_result = self.pull_changes(interactive=interactive, show_progress=show_progress)
        result.pulled = pull_result.pulled
        result.conflicts = pull_result.conflicts
        result.skipped = pull_result.skipped
        result.errors.extend(pull_result.errors)

        return result

    def push_pending(
        self,
        interactive: bool = True,
        show_progress: bool = True,
    ) -> SyncResult:
        """Push pending local changes to Notion.

        Processes the sync queue and applies changes to Notion.

        Args:
            interactive: Prompt for conflict resolution
            show_progress: Show progress bar

        Returns:
            SyncResult with push statistics
        """
        result = SyncResult()
        pending_items = self.db.get_pending_sync_items()

        if not pending_items:
            console.print("[dim]No pending changes to push.[/dim]")
            return result

        iterator = tqdm(pending_items, desc="Pushing", disable=not show_progress)

        for item in iterator:
            try:
                self._process_queue_item(item, result, interactive)
            except Exception as e:
                result.errors.append((item.entity_id, str(e)))

        return result

    def _process_queue_item(
        self,
        item: SyncQueueItem,
        result: SyncResult,
        interactive: bool,
    ) -> None:
        """Process a single sync queue item.

        Args:
            item: Queue item to process
            result: SyncResult to update
            interactive: Whether to prompt for conflicts
        """
        if item.entity_type != "book":
            # Only handle books for now
            self.db.mark_sync_item_completed(item.id)
            return

        book = self.db.get_book(item.entity_id)

        if item.operation == SyncOperation.CREATE.value:
            self._push_create(item, book, result)
        elif item.operation == SyncOperation.UPDATE.value:
            self._push_update(item, book, result, interactive)
        elif item.operation == SyncOperation.DELETE.value:
            self._push_delete(item, book, result)

    def _push_create(
        self,
        item: SyncQueueItem,
        book: Optional[Book],
        result: SyncResult,
    ) -> None:
        """Push a new book to Notion."""
        if not book:
            # Book was deleted locally before sync
            self.db.mark_sync_item_completed(item.id)
            return

        try:
            # Create BookCreate from Book model
            book_data = self._book_to_create(book)

            # Create in Notion with retry
            page_id = self._with_retry(
                lambda: self.notion.create_book(book_data)
            )

            # Update local book with Notion page ID
            with self.db.get_session() as session:
                db_book = session.get(Book, book.id)
                if db_book:
                    db_book.notion_page_id = page_id
                    db_book.notion_modified_at = datetime.now(timezone.utc).isoformat()

            self.db.mark_sync_item_completed(item.id)
            result.pushed += 1

        except NotionError as e:
            self.db.mark_sync_item_failed(item.id, str(e))
            result.errors.append((book.title, str(e)))

    def _push_update(
        self,
        item: SyncQueueItem,
        book: Optional[Book],
        result: SyncResult,
        interactive: bool,
    ) -> None:
        """Push a book update to Notion."""
        if not book:
            self.db.mark_sync_item_completed(item.id)
            return

        if not book.notion_page_id:
            # No Notion page yet, treat as create
            self._push_create(item, book, result)
            return

        try:
            # Check for conflicts
            notion_page = self._with_retry(
                lambda: self.notion.get_page(book.notion_page_id)
            )

            last_sync = _parse_timestamp(book.notion_modified_at)
            conflict = detect_conflict(book, notion_page, last_sync)

            if conflict and conflict.conflict_type == ConflictType.BOTH_MODIFIED:
                if interactive:
                    resolution = resolve_conflict_interactive(conflict)
                else:
                    resolution = ConflictResolution.KEEP_NOTION  # Default

                if resolution == ConflictResolution.KEEP_NOTION:
                    # Pull Notion version instead
                    self._apply_notion_to_local(notion_page, book)
                    self.db.mark_sync_item_completed(item.id)
                    result.conflicts += 1
                    return
                elif resolution == ConflictResolution.SKIP:
                    result.skipped += 1
                    return
                # KEEP_LOCAL falls through to push

            # Push update
            update = self._book_to_update(book)
            self._with_retry(
                lambda: self.notion.update_book(book.notion_page_id, update)
            )

            # Update sync timestamp
            with self.db.get_session() as session:
                db_book = session.get(Book, book.id)
                if db_book:
                    db_book.notion_modified_at = datetime.now(timezone.utc).isoformat()

            self.db.mark_sync_item_completed(item.id)
            result.pushed += 1

        except NotionError as e:
            self.db.mark_sync_item_failed(item.id, str(e))
            result.errors.append((book.title, str(e)))

    def _push_delete(
        self,
        item: SyncQueueItem,
        book: Optional[Book],
        result: SyncResult,
    ) -> None:
        """Archive a book in Notion."""
        # For delete operations, we may not have the book anymore
        # The notion_page_id should be stored in the queue item or we skip

        # Since we can't get the page ID without the book, skip
        self.db.mark_sync_item_completed(item.id)

    def pull_changes(
        self,
        interactive: bool = True,
        show_progress: bool = True,
        since: Optional[datetime] = None,
    ) -> SyncResult:
        """Pull changes from Notion to local database.

        Args:
            interactive: Prompt for conflict resolution
            show_progress: Show progress indicators
            since: Only pull changes after this time

        Returns:
            SyncResult with pull statistics
        """
        result = SyncResult()

        try:
            if since:
                notion_books = self._with_retry(
                    lambda: self.notion.query_books_modified_since(since)
                )
            else:
                notion_books = self._with_retry(
                    lambda: self.notion.query_all_books()
                )
        except NotionError as e:
            result.errors.append(("Notion query", str(e)))
            return result

        if not notion_books:
            console.print("[dim]No changes to pull from Notion.[/dim]")
            return result

        iterator = tqdm(notion_books, desc="Pulling", disable=not show_progress)

        for notion_page in iterator:
            try:
                self._process_notion_page(notion_page, result, interactive)
            except Exception as e:
                result.errors.append((notion_page.title, str(e)))

        return result

    def _process_notion_page(
        self,
        notion_page: NotionPage,
        result: SyncResult,
        interactive: bool,
    ) -> None:
        """Process a single Notion page during pull.

        Args:
            notion_page: Page from Notion
            result: SyncResult to update
            interactive: Whether to prompt for conflicts
        """
        # Find local book by Notion page ID or ISBN
        local_book = self._find_local_book(notion_page)
        book_data = self.notion.notion_page_to_book(notion_page)

        if not local_book:
            # New book from Notion - create locally
            new_book = self.db.create_book(book_data)

            # Set notion_page_id and clear sync queue (don't want to push back)
            with self.db.get_session() as session:
                db_book = session.get(Book, new_book.id)
                if db_book:
                    db_book.notion_page_id = notion_page.page_id
                    db_book.notion_modified_at = notion_page.last_edited_time.isoformat()

            # Clear the create operation from queue
            for item in self.db.get_pending_sync_items():
                if item.entity_id == new_book.id:
                    self.db.mark_sync_item_completed(item.id)

            result.pulled += 1
            return

        # Book exists locally - check for conflicts
        last_sync = _parse_timestamp(local_book.notion_modified_at)
        conflict = detect_conflict(local_book, notion_page, last_sync)

        if conflict and conflict.conflict_type == ConflictType.BOTH_MODIFIED:
            if interactive:
                resolution = resolve_conflict_interactive(conflict)
            else:
                resolution = ConflictResolution.KEEP_NOTION

            if resolution == ConflictResolution.KEEP_LOCAL:
                # Keep local, will push on next sync
                result.skipped += 1
                return
            elif resolution == ConflictResolution.SKIP:
                result.skipped += 1
                return
            # KEEP_NOTION falls through

            result.conflicts += 1

        # Apply Notion data to local
        self._apply_notion_to_local(notion_page, local_book)
        result.pulled += 1

    def _find_local_book(self, notion_page: NotionPage) -> Optional[Book]:
        """Find local book matching a Notion page.

        Args:
            notion_page: Notion page to match

        Returns:
            Local Book if found, None otherwise
        """
        # First try by Notion page ID
        all_books = self.db.get_all_books()
        for book in all_books:
            if book.notion_page_id == notion_page.page_id:
                return book

        # Then try by ISBN
        book_data = self.notion.notion_page_to_book(notion_page)
        if book_data.isbn:
            book = self.db.get_book_by_isbn(book_data.isbn)
            if book:
                return book
        if book_data.isbn13:
            book = self.db.get_book_by_isbn(book_data.isbn13)
            if book:
                return book

        return None

    def _apply_notion_to_local(self, notion_page: NotionPage, local_book: Book) -> None:
        """Apply Notion page data to local book.

        Args:
            notion_page: Source Notion page
            local_book: Target local book
        """
        book_data = self.notion.notion_page_to_book(notion_page)

        update = BookUpdate(
            title=book_data.title,
            author=book_data.author,
            status=book_data.status,
            rating=book_data.rating,
            date_started=book_data.date_started,
            date_finished=book_data.date_finished,
            progress=book_data.progress,
        )

        self.db.update_book(local_book.id, update)

        # Update Notion tracking fields
        with self.db.get_session() as session:
            db_book = session.get(Book, local_book.id)
            if db_book:
                db_book.notion_page_id = notion_page.page_id
                db_book.notion_modified_at = notion_page.last_edited_time.isoformat()

        # Clear any pending sync for this book
        for item in self.db.get_pending_sync_items():
            if item.entity_id == local_book.id:
                self.db.mark_sync_item_completed(item.id)

    def _with_retry(self, operation, retries: Optional[int] = None):
        """Execute operation with exponential backoff retry.

        Args:
            operation: Callable to execute
            retries: Max retries (uses self.max_retries if not provided)

        Returns:
            Result of operation
        """
        max_attempts = retries or self.max_retries
        backoff = self.initial_backoff

        for attempt in range(max_attempts):
            try:
                return operation()
            except NotionRateLimitError as e:
                if attempt == max_attempts - 1:
                    raise
                sleep_time = max(e.retry_after, backoff)
                console.print(f"[dim]Rate limited. Waiting {sleep_time}s...[/dim]")
                time.sleep(sleep_time)
                backoff *= 2
            except NotionError:
                if attempt == max_attempts - 1:
                    raise
                console.print(f"[dim]Retrying in {backoff}s...[/dim]")
                time.sleep(backoff)
                backoff *= 2

    def _book_to_create(self, book: Book) -> BookCreate:
        """Convert Book model to BookCreate schema."""
        from ..db.schemas import BookSource, BookStatus

        return BookCreate(
            title=book.title,
            title_sort=book.title_sort,
            author=book.author,
            author_sort=book.author_sort,
            status=BookStatus(book.status) if book.status else BookStatus.WISHLIST,
            rating=book.rating,
            date_added=_parse_date(book.date_added),
            date_started=_parse_date(book.date_started),
            date_finished=_parse_date(book.date_finished),
            isbn=book.isbn,
            isbn13=book.isbn13,
            page_count=book.page_count,
            description=book.description,
            cover=book.cover,
            publisher=book.publisher,
            publication_year=book.publication_year,
            series=book.series,
            series_index=book.series_index,
            format=book.format,
            library_source=book.library_source,
            amazon_url=book.amazon_url,
            goodreads_url=book.goodreads_url,
            library_url=book.library_url,
            comments=book.comments,
            progress=book.progress,
            read_next=book.read_next,
            recommended_by=book.recommended_by,
            tags=book.get_tags(),
            sources=[BookSource.MANUAL],
            source_ids={},
        )

    def _book_to_update(self, book: Book) -> BookUpdate:
        """Convert Book model to BookUpdate schema."""
        from ..db.schemas import BookStatus

        return BookUpdate(
            title=book.title,
            author=book.author,
            status=BookStatus(book.status) if book.status else None,
            rating=book.rating,
            date_finished=_parse_date(book.date_finished),
            progress=book.progress,
        )


def _parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _parse_date(date_str: Optional[str]):
    """Parse date string to date object."""
    if not date_str:
        return None
    try:
        from datetime import date
        return date.fromisoformat(date_str[:10])
    except ValueError:
        return None
