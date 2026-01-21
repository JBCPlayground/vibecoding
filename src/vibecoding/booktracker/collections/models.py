"""SQLAlchemy models for collections.

Tables:
- collections: User-defined book collections
- collection_books: Many-to-many relationship between collections and books
"""

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.models import Base, Book


def generate_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid4())


class Collection(Base):
    """Collection model - stores custom book collections."""

    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Collection type: manual or smart
    collection_type: Mapped[str] = mapped_column(String(20), default="manual")

    # Smart collection criteria (JSON)
    smart_criteria: Mapped[Optional[str]] = mapped_column(Text)

    # Display settings
    icon: Mapped[Optional[str]] = mapped_column(String(50))
    color: Mapped[Optional[str]] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Visibility
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: Mapped[str] = mapped_column(
        String(26),
        default=lambda: datetime.now(timezone.utc).isoformat(),
        onupdate=lambda: datetime.now(timezone.utc).isoformat(),
    )

    # Relationships
    collection_books: Mapped[list["CollectionBook"]] = relationship(
        "CollectionBook", back_populates="collection", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Collection(id={self.id}, name='{self.name}', type={self.collection_type})>"

    def get_smart_criteria(self) -> Optional[dict]:
        """Get smart criteria as dict."""
        if self.smart_criteria:
            return json.loads(self.smart_criteria)
        return None

    def set_smart_criteria(self, criteria: dict) -> None:
        """Set smart criteria from dict."""
        self.smart_criteria = json.dumps(criteria) if criteria else None

    @property
    def is_smart(self) -> bool:
        """Check if this is a smart collection."""
        return self.collection_type == "smart"


class CollectionBook(Base):
    """Association table for collection-book many-to-many relationship."""

    __tablename__ = "collection_books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    collection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Position within collection (for manual ordering)
    position: Mapped[int] = mapped_column(Integer, default=0)

    # When the book was added to collection
    added_at: Mapped[str] = mapped_column(
        String(26), default=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Notes specific to this book in this collection
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    collection: Mapped["Collection"] = relationship(
        "Collection", back_populates="collection_books"
    )
    book: Mapped["Book"] = relationship("Book")

    # Unique constraint: a book can only be in a collection once
    __table_args__ = (
        UniqueConstraint("collection_id", "book_id", name="uq_collection_book"),
    )

    def __repr__(self) -> str:
        return f"<CollectionBook(collection_id={self.collection_id}, book_id={self.book_id})>"


class SmartCollectionCriteria:
    """Helper class for building smart collection criteria."""

    def __init__(self):
        self.filters: list[dict] = []
        self.match_mode: str = "all"  # "all" or "any"
        self.sort_by: Optional[str] = None
        self.sort_order: str = "asc"
        self.limit: Optional[int] = None

    def add_filter(
        self,
        field: str,
        operator: str,
        value,
        negate: bool = False,
    ) -> "SmartCollectionCriteria":
        """Add a filter condition.

        Args:
            field: Field to filter on (e.g., "status", "rating", "author")
            operator: Comparison operator (eq, ne, gt, lt, gte, lte, contains, in, between)
            value: Value to compare against
            negate: If True, negate the condition

        Returns:
            Self for chaining
        """
        self.filters.append({
            "field": field,
            "operator": operator,
            "value": value,
            "negate": negate,
        })
        return self

    def status_is(self, status: str) -> "SmartCollectionCriteria":
        """Filter by status equals."""
        return self.add_filter("status", "eq", status)

    def status_in(self, statuses: list[str]) -> "SmartCollectionCriteria":
        """Filter by status in list."""
        return self.add_filter("status", "in", statuses)

    def rating_gte(self, rating: int) -> "SmartCollectionCriteria":
        """Filter by rating greater than or equal."""
        return self.add_filter("rating", "gte", rating)

    def author_is(self, author: str) -> "SmartCollectionCriteria":
        """Filter by author equals."""
        return self.add_filter("author", "eq", author)

    def author_contains(self, text: str) -> "SmartCollectionCriteria":
        """Filter by author contains."""
        return self.add_filter("author", "contains", text)

    def tag_has(self, tag: str) -> "SmartCollectionCriteria":
        """Filter by has tag."""
        return self.add_filter("tags", "contains", tag)

    def series_is(self, series: str) -> "SmartCollectionCriteria":
        """Filter by series equals."""
        return self.add_filter("series", "eq", series)

    def year_between(self, start: int, end: int) -> "SmartCollectionCriteria":
        """Filter by publication year between."""
        return self.add_filter("publication_year", "between", [start, end])

    def added_after(self, date: str) -> "SmartCollectionCriteria":
        """Filter by added after date."""
        return self.add_filter("date_added", "gt", date)

    def finished_in_year(self, year: int) -> "SmartCollectionCriteria":
        """Filter by finished in specific year."""
        return self.add_filter("date_finished", "between", [f"{year}-01-01", f"{year}-12-31"])

    def has_rating(self) -> "SmartCollectionCriteria":
        """Filter by has a rating."""
        return self.add_filter("rating", "ne", None)

    def no_rating(self) -> "SmartCollectionCriteria":
        """Filter by no rating."""
        return self.add_filter("rating", "eq", None)

    def set_match_mode(self, mode: str) -> "SmartCollectionCriteria":
        """Set match mode ('all' or 'any')."""
        self.match_mode = mode
        return self

    def set_sort(self, field: str, order: str = "asc") -> "SmartCollectionCriteria":
        """Set sort order."""
        self.sort_by = field
        self.sort_order = order
        return self

    def set_limit(self, limit: int) -> "SmartCollectionCriteria":
        """Set result limit."""
        self.limit = limit
        return self

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "filters": self.filters,
            "match_mode": self.match_mode,
            "sort_by": self.sort_by,
            "sort_order": self.sort_order,
            "limit": self.limit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SmartCollectionCriteria":
        """Create from dictionary."""
        criteria = cls()
        criteria.filters = data.get("filters", [])
        criteria.match_mode = data.get("match_mode", "all")
        criteria.sort_by = data.get("sort_by")
        criteria.sort_order = data.get("sort_order", "asc")
        criteria.limit = data.get("limit")
        return criteria
