"""Conflict detection and resolution for sync operations.

Detects when both local and Notion versions have been modified since
the last sync, and provides resolution strategies.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from ..db.models import Book
from ..db.schemas import BookUpdate
from .notion import NotionPage


class ConflictType(str, Enum):
    """Type of sync conflict."""

    BOTH_MODIFIED = "both_modified"  # Both local and Notion changed
    LOCAL_DELETED = "local_deleted"  # Local deleted, Notion modified
    NOTION_DELETED = "notion_deleted"  # Notion deleted, local modified
    NEW_LOCAL = "new_local"  # New local book, not in Notion
    NEW_NOTION = "new_notion"  # New Notion book, not in local


class ConflictResolution(str, Enum):
    """Resolution strategy for conflicts."""

    KEEP_LOCAL = "keep_local"  # Use local version
    KEEP_NOTION = "keep_notion"  # Use Notion version (default, Notion wins)
    MERGE = "merge"  # Merge both versions
    SKIP = "skip"  # Skip this item, resolve later


@dataclass
class SyncConflict:
    """Represents a sync conflict between local and Notion versions."""

    book_id: str
    conflict_type: ConflictType
    local_book: Optional[Book]
    notion_page: Optional[NotionPage]
    local_modified: Optional[datetime]
    notion_modified: Optional[datetime]
    last_sync: Optional[datetime]

    def __repr__(self) -> str:
        title = self.local_book.title if self.local_book else "Unknown"
        return f"SyncConflict({title!r}, type={self.conflict_type.value})"


def detect_conflict(
    local_book: Optional[Book],
    notion_page: Optional[NotionPage],
    last_sync_time: Optional[datetime] = None,
) -> Optional[SyncConflict]:
    """Detect if there's a conflict between local and Notion versions.

    Args:
        local_book: Local database book (or None if deleted/not exists)
        notion_page: Notion page (or None if deleted/not exists)
        last_sync_time: When this book was last synced

    Returns:
        SyncConflict if conflict detected, None otherwise
    """
    # Case 1: New local book (not yet in Notion)
    if local_book and not notion_page and not local_book.notion_page_id:
        return SyncConflict(
            book_id=local_book.id,
            conflict_type=ConflictType.NEW_LOCAL,
            local_book=local_book,
            notion_page=None,
            local_modified=_parse_timestamp(local_book.local_modified_at),
            notion_modified=None,
            last_sync=last_sync_time,
        )

    # Case 2: New Notion book (not in local)
    if notion_page and not local_book:
        return SyncConflict(
            book_id=notion_page.page_id,
            conflict_type=ConflictType.NEW_NOTION,
            local_book=None,
            notion_page=notion_page,
            local_modified=None,
            notion_modified=notion_page.last_edited_time,
            last_sync=last_sync_time,
        )

    # Case 3: Both exist - check for modifications
    if local_book and notion_page:
        local_modified = _parse_timestamp(local_book.local_modified_at)
        notion_modified = notion_page.last_edited_time

        # If no last sync time, assume first sync
        if last_sync_time is None:
            last_sync_time = datetime.min.replace(tzinfo=timezone.utc)

        local_changed = local_modified and local_modified > last_sync_time
        notion_changed = notion_modified and notion_modified > last_sync_time

        if local_changed and notion_changed:
            return SyncConflict(
                book_id=local_book.id,
                conflict_type=ConflictType.BOTH_MODIFIED,
                local_book=local_book,
                notion_page=notion_page,
                local_modified=local_modified,
                notion_modified=notion_modified,
                last_sync=last_sync_time,
            )

    # Case 4: Local deleted but Notion modified
    if not local_book and notion_page:
        # This is handled as NEW_NOTION above
        pass

    # Case 5: Notion deleted but local modified
    if local_book and local_book.notion_page_id and not notion_page:
        return SyncConflict(
            book_id=local_book.id,
            conflict_type=ConflictType.NOTION_DELETED,
            local_book=local_book,
            notion_page=None,
            local_modified=_parse_timestamp(local_book.local_modified_at),
            notion_modified=None,
            last_sync=last_sync_time,
        )

    return None


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


console = Console()


def resolve_conflict_interactive(conflict: SyncConflict) -> ConflictResolution:
    """Interactively resolve a sync conflict.

    Args:
        conflict: The conflict to resolve

    Returns:
        User's chosen resolution
    """
    console.print("\n" + "=" * 60)
    console.print(f"[bold yellow]SYNC CONFLICT: {conflict.conflict_type.value}[/bold yellow]")
    console.print("=" * 60 + "\n")

    if conflict.conflict_type == ConflictType.BOTH_MODIFIED:
        _show_both_modified_conflict(conflict)
    elif conflict.conflict_type == ConflictType.NEW_LOCAL:
        console.print(f"[cyan]New local book:[/cyan] {conflict.local_book.title}")
        console.print("This book hasn't been synced to Notion yet.")
    elif conflict.conflict_type == ConflictType.NEW_NOTION:
        console.print(f"[cyan]New Notion book:[/cyan] {conflict.notion_page.title}")
        console.print("This book exists in Notion but not locally.")
    elif conflict.conflict_type == ConflictType.NOTION_DELETED:
        console.print(f"[cyan]Book:[/cyan] {conflict.local_book.title}")
        console.print("[red]This book was deleted from Notion but modified locally.[/red]")

    console.print("\n[bold]Resolution Options:[/bold]")
    console.print("  [cyan]1[/cyan] - Keep Notion version (Notion wins)")
    console.print("  [cyan]2[/cyan] - Keep local version")
    console.print("  [cyan]3[/cyan] - Skip (resolve later)")

    choice = Prompt.ask(
        "\nYour choice",
        choices=["1", "2", "3"],
        default="1",
    )

    resolution_map = {
        "1": ConflictResolution.KEEP_NOTION,
        "2": ConflictResolution.KEEP_LOCAL,
        "3": ConflictResolution.SKIP,
    }

    resolution = resolution_map[choice]
    console.print(f"\n[green]Resolution: {resolution.value}[/green]")
    return resolution


def _show_both_modified_conflict(conflict: SyncConflict) -> None:
    """Display side-by-side comparison for both-modified conflict."""
    table = Table(title="Version Comparison", show_header=True)
    table.add_column("Field", style="cyan", width=15)
    table.add_column("Local", width=30)
    table.add_column("Notion", width=30)

    local = conflict.local_book
    notion = conflict.notion_page

    # Compare key fields
    fields = [
        ("Title", local.title if local else "-", notion.title if notion else "-"),
        ("Author", local.author if local else "-", notion.author if notion else "-"),
        ("Status", local.status if local else "-", _get_notion_status(notion)),
        ("Rating", str(local.rating) if local and local.rating else "-",
         _get_notion_rating(notion)),
        ("Modified", conflict.local_modified.isoformat() if conflict.local_modified else "-",
         conflict.notion_modified.isoformat() if conflict.notion_modified else "-"),
    ]

    for field, local_val, notion_val in fields:
        # Highlight differences
        if local_val != notion_val:
            table.add_row(field, f"[yellow]{local_val}[/yellow]", f"[cyan]{notion_val}[/cyan]")
        else:
            table.add_row(field, local_val, notion_val)

    console.print(table)


def _get_notion_status(page: Optional[NotionPage]) -> str:
    """Extract status from Notion page."""
    if not page:
        return "-"
    status_prop = page.properties.get("Status", {})
    if status_prop.get("select"):
        return status_prop["select"].get("name", "-")
    return "-"


def _get_notion_rating(page: Optional[NotionPage]) -> str:
    """Extract rating from Notion page."""
    if not page:
        return "-"
    rating_prop = page.properties.get("Rating", {})
    rating = rating_prop.get("number")
    return str(int(rating)) if rating is not None else "-"
