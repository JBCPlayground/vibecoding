"""Sync module for Notion API integration.

Handles bidirectional sync between local SQLite database and Notion,
including conflict detection and resolution.
"""

from .notion import (
    NotionClient,
    NotionError,
    NotionConfigError,
    NotionRateLimitError,
    NotionPage,
    STATUS_TO_NOTION,
    NOTION_TO_STATUS,
)
from .conflict import (
    ConflictType,
    ConflictResolution,
    SyncConflict,
    detect_conflict,
    resolve_conflict_interactive,
)
from .queue import (
    SyncProcessor,
    SyncResult,
)

__all__ = [
    # Notion client
    "NotionClient",
    "NotionError",
    "NotionConfigError",
    "NotionRateLimitError",
    "NotionPage",
    "STATUS_TO_NOTION",
    "NOTION_TO_STATUS",
    # Conflict handling
    "ConflictType",
    "ConflictResolution",
    "SyncConflict",
    "detect_conflict",
    "resolve_conflict_interactive",
    # Sync processor
    "SyncProcessor",
    "SyncResult",
]
