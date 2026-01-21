"""Collection manager for CRUD operations on collections."""

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.orm import Session

from ..db.models import Book
from ..db.sqlite import Database, get_db
from .models import Collection, CollectionBook, SmartCollectionCriteria
from .schemas import (
    CollectionCreate,
    CollectionUpdate,
    CollectionType,
    FilterOperator,
    SmartCriteria,
    CollectionBookAdd,
    CollectionBookUpdate,
)


class CollectionManager:
    """Manages collection operations."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize collection manager.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def create_collection(self, data: CollectionCreate) -> Collection:
        """Create a new collection.

        Args:
            data: Collection creation data

        Returns:
            Created collection
        """
        with self.db.get_session() as session:
            # Get max sort order
            max_order = session.execute(
                select(func.max(Collection.sort_order))
            ).scalar() or 0

            collection = Collection(
                name=data.name,
                description=data.description,
                collection_type=data.collection_type.value,
                icon=data.icon,
                color=data.color,
                is_pinned=data.is_pinned,
                sort_order=max_order + 1,
            )

            if data.smart_criteria:
                collection.set_smart_criteria(data.smart_criteria.model_dump())

            session.add(collection)
            session.commit()
            session.refresh(collection)
            session.expunge(collection)

            return collection

    def get_collection(self, collection_id: str) -> Optional[Collection]:
        """Get a collection by ID.

        Args:
            collection_id: Collection ID

        Returns:
            Collection or None
        """
        with self.db.get_session() as session:
            stmt = select(Collection).where(Collection.id == collection_id)
            collection = session.execute(stmt).scalar_one_or_none()
            if collection:
                session.expunge(collection)
            return collection

    def get_collection_by_name(self, name: str) -> Optional[Collection]:
        """Get a collection by name.

        Args:
            name: Collection name

        Returns:
            Collection or None
        """
        with self.db.get_session() as session:
            stmt = select(Collection).where(func.lower(Collection.name) == name.lower())
            collection = session.execute(stmt).scalar_one_or_none()
            if collection:
                session.expunge(collection)
            return collection

    def list_collections(
        self,
        collection_type: Optional[CollectionType] = None,
        pinned_only: bool = False,
    ) -> list[Collection]:
        """List all collections.

        Args:
            collection_type: Filter by type
            pinned_only: Only return pinned collections

        Returns:
            List of collections
        """
        with self.db.get_session() as session:
            stmt = select(Collection)

            if collection_type:
                stmt = stmt.where(Collection.collection_type == collection_type.value)
            if pinned_only:
                stmt = stmt.where(Collection.is_pinned == True)

            stmt = stmt.order_by(Collection.is_pinned.desc(), Collection.sort_order)

            collections = session.execute(stmt).scalars().all()
            for c in collections:
                session.expunge(c)
            return list(collections)

    def update_collection(
        self,
        collection_id: str,
        data: CollectionUpdate,
    ) -> Optional[Collection]:
        """Update a collection.

        Args:
            collection_id: Collection ID
            data: Update data

        Returns:
            Updated collection or None
        """
        with self.db.get_session() as session:
            stmt = select(Collection).where(Collection.id == collection_id)
            collection = session.execute(stmt).scalar_one_or_none()

            if not collection:
                return None

            update_data = data.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if field == "smart_criteria" and value is not None:
                    collection.set_smart_criteria(value)
                elif hasattr(collection, field):
                    setattr(collection, field, value)

            collection.updated_at = datetime.now(timezone.utc).isoformat()
            session.commit()
            session.refresh(collection)
            session.expunge(collection)

            return collection

    def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection.

        Args:
            collection_id: Collection ID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            stmt = select(Collection).where(Collection.id == collection_id)
            collection = session.execute(stmt).scalar_one_or_none()

            if not collection:
                return False

            # Don't allow deleting default collections
            if collection.is_default:
                raise ValueError("Cannot delete default collection")

            session.delete(collection)
            session.commit()
            return True

    def add_book_to_collection(
        self,
        collection_id: str,
        data: CollectionBookAdd,
    ) -> Optional[CollectionBook]:
        """Add a book to a collection.

        Args:
            collection_id: Collection ID
            data: Book addition data

        Returns:
            CollectionBook or None
        """
        with self.db.get_session() as session:
            # Verify collection exists and is manual
            stmt = select(Collection).where(Collection.id == collection_id)
            collection = session.execute(stmt).scalar_one_or_none()

            if not collection:
                return None

            if collection.collection_type == "smart":
                raise ValueError("Cannot manually add books to smart collections")

            # Check if book already in collection
            existing = session.execute(
                select(CollectionBook).where(
                    CollectionBook.collection_id == collection_id,
                    CollectionBook.book_id == str(data.book_id),
                )
            ).scalar_one_or_none()

            if existing:
                raise ValueError("Book is already in this collection")

            # Get max position if not specified
            if data.position is None:
                max_pos = session.execute(
                    select(func.max(CollectionBook.position)).where(
                        CollectionBook.collection_id == collection_id
                    )
                ).scalar() or 0
                position = max_pos + 1
            else:
                position = data.position

            cb = CollectionBook(
                collection_id=collection_id,
                book_id=str(data.book_id),
                position=position,
                notes=data.notes,
            )

            session.add(cb)
            session.commit()
            session.refresh(cb)
            session.expunge(cb)

            return cb

    def remove_book_from_collection(
        self,
        collection_id: str,
        book_id: str,
    ) -> bool:
        """Remove a book from a collection.

        Args:
            collection_id: Collection ID
            book_id: Book ID

        Returns:
            True if removed
        """
        with self.db.get_session() as session:
            stmt = select(CollectionBook).where(
                CollectionBook.collection_id == collection_id,
                CollectionBook.book_id == book_id,
            )
            cb = session.execute(stmt).scalar_one_or_none()

            if not cb:
                return False

            session.delete(cb)
            session.commit()
            return True

    def update_book_in_collection(
        self,
        collection_id: str,
        book_id: str,
        data: CollectionBookUpdate,
    ) -> Optional[CollectionBook]:
        """Update a book's position/notes in a collection.

        Args:
            collection_id: Collection ID
            book_id: Book ID
            data: Update data

        Returns:
            Updated CollectionBook or None
        """
        with self.db.get_session() as session:
            stmt = select(CollectionBook).where(
                CollectionBook.collection_id == collection_id,
                CollectionBook.book_id == book_id,
            )
            cb = session.execute(stmt).scalar_one_or_none()

            if not cb:
                return None

            if data.position is not None:
                cb.position = data.position
            if data.notes is not None:
                cb.notes = data.notes

            session.commit()
            session.refresh(cb)
            session.expunge(cb)

            return cb

    def get_collection_books(
        self,
        collection_id: str,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[Book]:
        """Get books in a collection.

        For manual collections, returns books in order.
        For smart collections, evaluates criteria dynamically.

        Args:
            collection_id: Collection ID
            limit: Max books to return
            offset: Offset for pagination

        Returns:
            List of books
        """
        with self.db.get_session() as session:
            # Get collection
            stmt = select(Collection).where(Collection.id == collection_id)
            collection = session.execute(stmt).scalar_one_or_none()

            if not collection:
                return []

            if collection.collection_type == "smart":
                return self._get_smart_collection_books(
                    session, collection, limit, offset
                )
            else:
                return self._get_manual_collection_books(
                    session, collection_id, limit, offset
                )

    def _get_manual_collection_books(
        self,
        session: Session,
        collection_id: str,
        limit: Optional[int],
        offset: int,
    ) -> list[Book]:
        """Get books from a manual collection."""
        stmt = (
            select(Book)
            .join(CollectionBook, Book.id == CollectionBook.book_id)
            .where(CollectionBook.collection_id == collection_id)
            .order_by(CollectionBook.position)
            .offset(offset)
        )

        if limit:
            stmt = stmt.limit(limit)

        books = session.execute(stmt).scalars().all()
        for book in books:
            session.expunge(book)
        return list(books)

    def _get_smart_collection_books(
        self,
        session: Session,
        collection: Collection,
        limit: Optional[int],
        offset: int,
    ) -> list[Book]:
        """Get books from a smart collection by evaluating criteria."""
        criteria_dict = collection.get_smart_criteria()
        if not criteria_dict:
            return []

        criteria = SmartCollectionCriteria.from_dict(criteria_dict)
        stmt = select(Book)

        # Build filter conditions
        conditions = []
        for f in criteria.filters:
            condition = self._build_filter_condition(f)
            if condition is not None:
                if f.get("negate"):
                    condition = ~condition
                conditions.append(condition)

        if conditions:
            if criteria.match_mode == "any":
                stmt = stmt.where(or_(*conditions))
            else:
                stmt = stmt.where(and_(*conditions))

        # Apply sorting
        if criteria.sort_by:
            sort_col = getattr(Book, criteria.sort_by, None)
            if sort_col is not None:
                if criteria.sort_order == "desc":
                    stmt = stmt.order_by(desc(sort_col))
                else:
                    stmt = stmt.order_by(asc(sort_col))

        # Apply limit/offset
        stmt = stmt.offset(offset)
        if criteria.limit:
            stmt = stmt.limit(min(limit, criteria.limit) if limit else criteria.limit)
        elif limit:
            stmt = stmt.limit(limit)

        books = session.execute(stmt).scalars().all()
        for book in books:
            session.expunge(book)
        return list(books)

    def _build_filter_condition(self, filter_dict: dict):
        """Build SQLAlchemy filter condition from filter dict."""
        field = filter_dict.get("field")
        operator = filter_dict.get("operator")
        value = filter_dict.get("value")

        col = getattr(Book, field, None)
        if col is None:
            return None

        if operator == "eq":
            return col == value
        elif operator == "ne":
            return col != value
        elif operator == "gt":
            return col > value
        elif operator == "lt":
            return col < value
        elif operator == "gte":
            return col >= value
        elif operator == "lte":
            return col <= value
        elif operator == "contains":
            if field == "tags":
                # For JSON array field, use LIKE with the value
                return col.like(f"%{value}%")
            return col.contains(value)
        elif operator == "in":
            return col.in_(value)
        elif operator == "between":
            if isinstance(value, list) and len(value) == 2:
                return col.between(value[0], value[1])
        elif operator == "is_null":
            return col.is_(None)
        elif operator == "is_not_null":
            return col.isnot(None)

        return None

    def get_book_count(self, collection_id: str) -> int:
        """Get the number of books in a collection.

        Args:
            collection_id: Collection ID

        Returns:
            Book count
        """
        with self.db.get_session() as session:
            # Check collection type
            stmt = select(Collection).where(Collection.id == collection_id)
            collection = session.execute(stmt).scalar_one_or_none()

            if not collection:
                return 0

            if collection.collection_type == "smart":
                # For smart collections, we need to evaluate the criteria
                books = self._get_smart_collection_books(session, collection, None, 0)
                return len(books)
            else:
                # For manual collections, count the associations
                count = session.execute(
                    select(func.count()).where(
                        CollectionBook.collection_id == collection_id
                    )
                ).scalar()
                return count or 0

    def reorder_books(
        self,
        collection_id: str,
        book_ids: list[str],
    ) -> bool:
        """Reorder books in a collection.

        Args:
            collection_id: Collection ID
            book_ids: List of book IDs in desired order

        Returns:
            True if successful
        """
        with self.db.get_session() as session:
            for position, book_id in enumerate(book_ids):
                stmt = (
                    select(CollectionBook)
                    .where(
                        CollectionBook.collection_id == collection_id,
                        CollectionBook.book_id == book_id,
                    )
                )
                cb = session.execute(stmt).scalar_one_or_none()
                if cb:
                    cb.position = position

            session.commit()
            return True

    def get_collections_for_book(self, book_id: str) -> list[Collection]:
        """Get all collections containing a book.

        Args:
            book_id: Book ID

        Returns:
            List of collections
        """
        with self.db.get_session() as session:
            stmt = (
                select(Collection)
                .join(CollectionBook, Collection.id == CollectionBook.collection_id)
                .where(CollectionBook.book_id == book_id)
            )
            collections = session.execute(stmt).scalars().all()
            for c in collections:
                session.expunge(c)
            return list(collections)

    def create_default_collections(self) -> list[Collection]:
        """Create default collections for common use cases.

        Returns:
            List of created collections
        """
        defaults = [
            {
                "name": "Favorites",
                "description": "Books rated 5 stars",
                "collection_type": "smart",
                "icon": "star",
                "color": "gold",
                "criteria": SmartCollectionCriteria().rating_gte(5).to_dict(),
            },
            {
                "name": "Currently Reading",
                "description": "Books you're reading now",
                "collection_type": "smart",
                "icon": "book-open",
                "color": "blue",
                "criteria": SmartCollectionCriteria().status_is("reading").to_dict(),
            },
            {
                "name": "To Read",
                "description": "Your reading wishlist",
                "collection_type": "smart",
                "icon": "list",
                "color": "green",
                "criteria": SmartCollectionCriteria().status_is("wishlist").to_dict(),
            },
            {
                "name": "Completed This Year",
                "description": "Books finished this year",
                "collection_type": "smart",
                "icon": "check",
                "color": "purple",
                "criteria": SmartCollectionCriteria()
                    .status_is("completed")
                    .finished_in_year(datetime.now().year)
                    .to_dict(),
            },
        ]

        created = []
        for default in defaults:
            # Check if already exists
            existing = self.get_collection_by_name(default["name"])
            if existing:
                continue

            with self.db.get_session() as session:
                collection = Collection(
                    name=default["name"],
                    description=default["description"],
                    collection_type=default["collection_type"],
                    icon=default.get("icon"),
                    color=default.get("color"),
                    is_default=True,
                    is_pinned=True,
                )
                if default.get("criteria"):
                    collection.set_smart_criteria(default["criteria"])

                session.add(collection)
                session.commit()
                session.refresh(collection)
                session.expunge(collection)
                created.append(collection)

        return created
