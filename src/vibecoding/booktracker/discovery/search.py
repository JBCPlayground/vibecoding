"""Advanced search functionality.

Provides powerful multi-criteria search for books.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from sqlalchemy import select, or_, and_, func

from ..db.models import Book
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


class SortOrder(str, Enum):
    """Sort order options."""

    TITLE_ASC = "title_asc"
    TITLE_DESC = "title_desc"
    AUTHOR_ASC = "author_asc"
    AUTHOR_DESC = "author_desc"
    DATE_ADDED_ASC = "date_added_asc"
    DATE_ADDED_DESC = "date_added_desc"
    DATE_FINISHED_ASC = "date_finished_asc"
    DATE_FINISHED_DESC = "date_finished_desc"
    RATING_ASC = "rating_asc"
    RATING_DESC = "rating_desc"
    PAGE_COUNT_ASC = "page_count_asc"
    PAGE_COUNT_DESC = "page_count_desc"


@dataclass
class SearchFilters:
    """Search filter criteria."""

    # Text search
    query: Optional[str] = None  # Search in title, author, description
    title: Optional[str] = None
    author: Optional[str] = None

    # Status filters
    status: Optional[BookStatus] = None
    statuses: Optional[list[BookStatus]] = None

    # Rating filters
    min_rating: Optional[int] = None
    max_rating: Optional[int] = None
    unrated_only: bool = False

    # Date filters
    added_after: Optional[date] = None
    added_before: Optional[date] = None
    finished_after: Optional[date] = None
    finished_before: Optional[date] = None
    started_after: Optional[date] = None
    started_before: Optional[date] = None

    # Page count filters
    min_pages: Optional[int] = None
    max_pages: Optional[int] = None

    # Tag/genre filters
    tags: Optional[list[str]] = None
    any_tag: bool = True  # True = OR, False = AND for tags

    # Series filter
    series: Optional[str] = None
    in_series: Optional[bool] = None  # True = has series, False = standalone

    # Other filters
    publisher: Optional[str] = None
    year_published: Optional[int] = None
    min_year_published: Optional[int] = None
    max_year_published: Optional[int] = None

    # Special filters
    has_cover: Optional[bool] = None
    has_isbn: Optional[bool] = None
    read_next: Optional[bool] = None

    # Sorting
    sort_by: SortOrder = SortOrder.DATE_ADDED_DESC

    # Pagination
    limit: int = 50
    offset: int = 0


@dataclass
class SearchResult:
    """Search result with metadata."""

    books: list[Book]
    total_count: int
    filters_applied: SearchFilters
    page: int = 1
    total_pages: int = 1

    @property
    def has_more(self) -> bool:
        """Check if there are more results."""
        return self.page < self.total_pages


class AdvancedSearch:
    """Advanced search engine for books."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize search engine.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def search(self, filters: SearchFilters) -> SearchResult:
        """Execute search with filters.

        Args:
            filters: Search criteria

        Returns:
            SearchResult with matching books
        """
        with self.db.get_session() as session:
            # Build base query
            stmt = select(Book)
            conditions = []

            # Text search
            if filters.query:
                query_lower = f"%{filters.query.lower()}%"
                conditions.append(or_(
                    func.lower(Book.title).like(query_lower),
                    func.lower(Book.author).like(query_lower),
                    func.lower(Book.description).like(query_lower),
                ))

            if filters.title:
                conditions.append(
                    func.lower(Book.title).like(f"%{filters.title.lower()}%")
                )

            if filters.author:
                conditions.append(
                    func.lower(Book.author).like(f"%{filters.author.lower()}%")
                )

            # Status filters
            if filters.status:
                conditions.append(Book.status == filters.status.value)
            elif filters.statuses:
                status_values = [s.value for s in filters.statuses]
                conditions.append(Book.status.in_(status_values))

            # Rating filters
            if filters.min_rating is not None:
                conditions.append(Book.rating >= filters.min_rating)
            if filters.max_rating is not None:
                conditions.append(Book.rating <= filters.max_rating)
            if filters.unrated_only:
                conditions.append(Book.rating.is_(None))

            # Date filters
            if filters.added_after:
                conditions.append(Book.date_added >= filters.added_after.isoformat())
            if filters.added_before:
                conditions.append(Book.date_added <= filters.added_before.isoformat())
            if filters.finished_after:
                conditions.append(Book.date_finished >= filters.finished_after.isoformat())
            if filters.finished_before:
                conditions.append(Book.date_finished <= filters.finished_before.isoformat())
            if filters.started_after:
                conditions.append(Book.date_started >= filters.started_after.isoformat())
            if filters.started_before:
                conditions.append(Book.date_started <= filters.started_before.isoformat())

            # Page count filters
            if filters.min_pages is not None:
                conditions.append(Book.page_count >= filters.min_pages)
            if filters.max_pages is not None:
                conditions.append(Book.page_count <= filters.max_pages)

            # Tag filters
            if filters.tags:
                tag_conditions = []
                for tag in filters.tags:
                    # Tags are stored as JSON array string
                    tag_conditions.append(
                        func.lower(Book.tags).like(f'%"{tag.lower()}"%')
                    )
                if filters.any_tag:
                    conditions.append(or_(*tag_conditions))
                else:
                    conditions.append(and_(*tag_conditions))

            # Series filters
            if filters.series:
                conditions.append(
                    func.lower(Book.series).like(f"%{filters.series.lower()}%")
                )
            if filters.in_series is not None:
                if filters.in_series:
                    conditions.append(Book.series.isnot(None))
                    conditions.append(Book.series != "")
                else:
                    conditions.append(or_(Book.series.is_(None), Book.series == ""))

            # Publisher filter
            if filters.publisher:
                conditions.append(
                    func.lower(Book.publisher).like(f"%{filters.publisher.lower()}%")
                )

            # Year published filters
            if filters.year_published:
                conditions.append(Book.publication_year == filters.year_published)
            if filters.min_year_published:
                conditions.append(Book.publication_year >= filters.min_year_published)
            if filters.max_year_published:
                conditions.append(Book.publication_year <= filters.max_year_published)

            # Special filters
            if filters.has_cover is not None:
                if filters.has_cover:
                    conditions.append(Book.cover.isnot(None))
                    conditions.append(Book.cover != "")
                else:
                    conditions.append(or_(Book.cover.is_(None), Book.cover == ""))

            if filters.has_isbn is not None:
                if filters.has_isbn:
                    conditions.append(Book.isbn.isnot(None))
                else:
                    conditions.append(Book.isbn.is_(None))

            if filters.read_next is not None:
                conditions.append(Book.read_next == filters.read_next)

            # Apply all conditions
            if conditions:
                stmt = stmt.where(and_(*conditions))

            # Get total count before pagination
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_count = session.execute(count_stmt).scalar() or 0

            # Apply sorting
            stmt = self._apply_sort(stmt, filters.sort_by)

            # Apply pagination
            stmt = stmt.offset(filters.offset).limit(filters.limit)

            # Execute query
            books = list(session.execute(stmt).scalars().all())

            # Detach from session
            for book in books:
                session.expunge(book)

            # Calculate pagination info
            total_pages = max(1, (total_count + filters.limit - 1) // filters.limit)
            current_page = (filters.offset // filters.limit) + 1

            return SearchResult(
                books=books,
                total_count=total_count,
                filters_applied=filters,
                page=current_page,
                total_pages=total_pages,
            )

    def quick_search(self, query: str, limit: int = 10) -> list[Book]:
        """Quick search by title or author.

        Args:
            query: Search text
            limit: Maximum results

        Returns:
            List of matching books
        """
        filters = SearchFilters(query=query, limit=limit)
        result = self.search(filters)
        return result.books

    def search_by_author(
        self,
        author: str,
        status: Optional[BookStatus] = None,
        limit: int = 50,
    ) -> list[Book]:
        """Search books by author.

        Args:
            author: Author name
            status: Optional status filter
            limit: Maximum results

        Returns:
            List of books by author
        """
        filters = SearchFilters(
            author=author,
            status=status,
            limit=limit,
            sort_by=SortOrder.TITLE_ASC,
        )
        result = self.search(filters)
        return result.books

    def search_by_series(self, series: str, limit: int = 50) -> list[Book]:
        """Search books in a series.

        Args:
            series: Series name
            limit: Maximum results

        Returns:
            List of books in series, sorted by series index
        """
        with self.db.get_session() as session:
            stmt = select(Book).where(
                func.lower(Book.series).like(f"%{series.lower()}%")
            ).order_by(
                Book.series_index.asc().nullslast()
            ).limit(limit)

            books = list(session.execute(stmt).scalars().all())
            for book in books:
                session.expunge(book)
            return books

    def search_by_tags(
        self,
        tags: list[str],
        match_all: bool = False,
        limit: int = 50,
    ) -> list[Book]:
        """Search books by tags.

        Args:
            tags: Tags to search for
            match_all: If True, book must have all tags
            limit: Maximum results

        Returns:
            List of matching books
        """
        filters = SearchFilters(
            tags=tags,
            any_tag=not match_all,
            limit=limit,
        )
        result = self.search(filters)
        return result.books

    def get_unread_books(
        self,
        sort_by: SortOrder = SortOrder.DATE_ADDED_DESC,
        limit: int = 50,
    ) -> list[Book]:
        """Get books that haven't been read yet.

        Args:
            sort_by: Sort order
            limit: Maximum results

        Returns:
            List of unread books
        """
        filters = SearchFilters(
            statuses=[BookStatus.WISHLIST, BookStatus.ON_HOLD],
            sort_by=sort_by,
            limit=limit,
        )
        result = self.search(filters)
        return result.books

    def get_highly_rated(
        self,
        min_rating: int = 4,
        limit: int = 50,
    ) -> list[Book]:
        """Get highly rated books.

        Args:
            min_rating: Minimum rating (1-5)
            limit: Maximum results

        Returns:
            List of highly rated books
        """
        filters = SearchFilters(
            min_rating=min_rating,
            status=BookStatus.COMPLETED,
            sort_by=SortOrder.RATING_DESC,
            limit=limit,
        )
        result = self.search(filters)
        return result.books

    def get_long_books(
        self,
        min_pages: int = 400,
        limit: int = 50,
    ) -> list[Book]:
        """Get long books.

        Args:
            min_pages: Minimum page count
            limit: Maximum results

        Returns:
            List of long books
        """
        filters = SearchFilters(
            min_pages=min_pages,
            sort_by=SortOrder.PAGE_COUNT_DESC,
            limit=limit,
        )
        result = self.search(filters)
        return result.books

    def get_short_books(
        self,
        max_pages: int = 200,
        limit: int = 50,
    ) -> list[Book]:
        """Get short books.

        Args:
            max_pages: Maximum page count
            limit: Maximum results

        Returns:
            List of short books
        """
        filters = SearchFilters(
            max_pages=max_pages,
            min_pages=1,  # Exclude books with no page count
            sort_by=SortOrder.PAGE_COUNT_ASC,
            limit=limit,
        )
        result = self.search(filters)
        return result.books

    def _apply_sort(self, stmt, sort_by: SortOrder):
        """Apply sorting to query."""
        sort_map = {
            SortOrder.TITLE_ASC: Book.title.asc(),
            SortOrder.TITLE_DESC: Book.title.desc(),
            SortOrder.AUTHOR_ASC: Book.author.asc(),
            SortOrder.AUTHOR_DESC: Book.author.desc(),
            SortOrder.DATE_ADDED_ASC: Book.date_added.asc().nullslast(),
            SortOrder.DATE_ADDED_DESC: Book.date_added.desc().nullsfirst(),
            SortOrder.DATE_FINISHED_ASC: Book.date_finished.asc().nullslast(),
            SortOrder.DATE_FINISHED_DESC: Book.date_finished.desc().nullsfirst(),
            SortOrder.RATING_ASC: Book.rating.asc().nullslast(),
            SortOrder.RATING_DESC: Book.rating.desc().nullsfirst(),
            SortOrder.PAGE_COUNT_ASC: Book.page_count.asc().nullslast(),
            SortOrder.PAGE_COUNT_DESC: Book.page_count.desc().nullsfirst(),
        }
        return stmt.order_by(sort_map.get(sort_by, Book.date_added.desc()))
