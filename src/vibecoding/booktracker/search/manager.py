"""Manager for advanced search operations."""

import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_, select

from ..db.models import Book
from ..db.sqlite import Database, get_db
from .schemas import (
    AdvancedSearchQuery,
    BookSearchResult,
    NoteSearchResult,
    QuoteSearchResult,
    ResultType,
    ReviewSearchResult,
    SearchQuery,
    SearchResult,
    SearchResults,
    SearchScope,
    SearchSuggestion,
    SearchSuggestions,
    SortBy,
)


class SearchManager:
    """Manages advanced search operations across all entities."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize search manager.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    # -------------------------------------------------------------------------
    # Unified Search
    # -------------------------------------------------------------------------

    def search(self, query: SearchQuery) -> SearchResults:
        """Perform a unified search across all specified scopes.

        Args:
            query: Search query parameters

        Returns:
            SearchResults with all matching items
        """
        start_time = time.time()
        results: list[SearchResult] = []
        facets: dict[str, dict[str, int]] = {
            "type": {},
            "status": {},
            "genre": {},
        }

        search_term = query.query.lower()
        scopes = query.scope

        # Determine which scopes to search
        search_all = SearchScope.ALL in scopes

        # Search books
        if search_all or SearchScope.BOOKS in scopes:
            book_results = self._search_books(search_term, query)
            results.extend(book_results)
            facets["type"]["book"] = len(book_results)

        # Search notes
        if search_all or SearchScope.NOTES in scopes:
            note_results = self._search_notes(search_term, query)
            results.extend(note_results)
            facets["type"]["note"] = len(note_results)

        # Search quotes
        if search_all or SearchScope.QUOTES in scopes:
            quote_results = self._search_quotes(search_term, query)
            results.extend(quote_results)
            facets["type"]["quote"] = len(quote_results)

        # Search reviews
        if search_all or SearchScope.REVIEWS in scopes:
            review_results = self._search_reviews(search_term, query)
            results.extend(review_results)
            facets["type"]["review"] = len(review_results)

        # Search collections
        if search_all or SearchScope.COLLECTIONS in scopes:
            collection_results = self._search_collections(search_term, query)
            results.extend(collection_results)
            facets["type"]["collection"] = len(collection_results)

        # Search lists
        if search_all or SearchScope.LISTS in scopes:
            list_results = self._search_lists(search_term, query)
            results.extend(list_results)
            facets["type"]["list"] = len(list_results)

        # Search tags
        if search_all or SearchScope.TAGS in scopes:
            tag_results = self._search_tags(search_term, query)
            results.extend(tag_results)
            facets["type"]["tag"] = len(tag_results)

        # Search authors
        if search_all or SearchScope.AUTHORS in scopes:
            author_results = self._search_authors(search_term, query)
            results.extend(author_results)
            facets["type"]["author"] = len(author_results)

        # Sort results
        results = self._sort_results(results, query.sort_by, query.sort_order)

        # Calculate total before pagination
        total_count = len(results)

        # Apply pagination
        paginated = results[query.offset : query.offset + query.limit]
        has_more = query.offset + len(paginated) < total_count

        search_time = (time.time() - start_time) * 1000

        return SearchResults(
            query=query.query,
            total_count=total_count,
            results=paginated,
            has_more=has_more,
            facets=facets,
            search_time_ms=search_time,
        )

    def advanced_search(self, query: AdvancedSearchQuery) -> SearchResults:
        """Perform advanced search with field-specific queries.

        Args:
            query: Advanced search query

        Returns:
            SearchResults
        """
        start_time = time.time()
        results: list[SearchResult] = []

        # Build combined search terms
        search_terms = []
        if query.title:
            search_terms.append(("title", query.title.lower()))
        if query.author:
            search_terms.append(("author", query.author.lower()))
        if query.content:
            search_terms.append(("content", query.content.lower()))
        if query.tag:
            search_terms.append(("tag", query.tag.lower()))
        if query.genre:
            search_terms.append(("genre", query.genre.lower()))

        # Add boolean operators
        must_terms = [t.lower() for t in query.must_include]
        should_terms = [t.lower() for t in query.should_include]
        exclude_terms = [t.lower() for t in query.must_exclude]

        scopes = query.scope
        search_all = SearchScope.ALL in scopes

        # Search books with advanced criteria
        if search_all or SearchScope.BOOKS in scopes:
            results.extend(
                self._advanced_search_books(
                    search_terms, must_terms, should_terms, exclude_terms
                )
            )

        # Search notes
        if search_all or SearchScope.NOTES in scopes:
            results.extend(
                self._advanced_search_notes(
                    search_terms, must_terms, should_terms, exclude_terms
                )
            )

        # Search quotes
        if search_all or SearchScope.QUOTES in scopes:
            results.extend(
                self._advanced_search_quotes(
                    search_terms, must_terms, should_terms, exclude_terms
                )
            )

        # Sort and paginate
        results = self._sort_results(results, query.sort_by, query.sort_order)
        total_count = len(results)
        paginated = results[: query.limit]

        search_time = (time.time() - start_time) * 1000

        return SearchResults(
            query=self._build_query_string(query),
            total_count=total_count,
            results=paginated,
            has_more=len(results) > query.limit,
            facets={},
            search_time_ms=search_time,
        )

    # -------------------------------------------------------------------------
    # Entity-Specific Search
    # -------------------------------------------------------------------------

    def search_books(
        self,
        query: str,
        status: Optional[str] = None,
        genre: Optional[str] = None,
        min_rating: Optional[float] = None,
        limit: int = 20,
    ) -> list[BookSearchResult]:
        """Search books specifically.

        Args:
            query: Search query
            status: Filter by status
            genre: Filter by genre
            min_rating: Minimum rating filter
            limit: Maximum results

        Returns:
            List of book search results
        """
        search_term = query.lower()
        results = []

        with self.db.get_session() as session:
            stmt = select(Book).where(
                or_(
                    func.lower(Book.title).like(f"%{search_term}%"),
                    func.lower(Book.author).like(f"%{search_term}%"),
                    func.lower(Book.description).like(f"%{search_term}%"),
                    func.lower(Book.genres).like(f"%{search_term}%"),
                    func.lower(Book.isbn).like(f"%{search_term}%"),
                )
            )

            if status:
                stmt = stmt.where(Book.status == status)
            if genre:
                stmt = stmt.where(func.lower(Book.genres).like(f"%{genre.lower()}%"))
            if min_rating:
                stmt = stmt.where(Book.rating >= min_rating)

            stmt = stmt.limit(limit)
            books = session.execute(stmt).scalars().all()

            for book in books:
                snippet = self._create_snippet(
                    f"{book.title} by {book.author or 'Unknown'}. {book.description or ''}",
                    search_term,
                )
                score = self._calculate_relevance(
                    search_term, book.title, book.author, book.description
                )

                results.append(
                    BookSearchResult(
                        id=book.id,
                        title=book.title,
                        author=book.author,
                        genres=book.genres,
                        status=book.status,
                        rating=book.rating,
                        snippet=snippet,
                        relevance_score=score,
                    )
                )

        return sorted(results, key=lambda x: x.relevance_score, reverse=True)

    def search_notes(
        self,
        query: str,
        book_id: Optional[str] = None,
        note_type: Optional[str] = None,
        limit: int = 20,
    ) -> list[NoteSearchResult]:
        """Search notes specifically.

        Args:
            query: Search query
            book_id: Filter by book
            note_type: Filter by note type
            limit: Maximum results

        Returns:
            List of note search results
        """
        from ..notes.models import Note

        search_term = query.lower()
        results = []

        with self.db.get_session() as session:
            stmt = select(Note).where(
                or_(
                    func.lower(Note.title).like(f"%{search_term}%"),
                    func.lower(Note.content).like(f"%{search_term}%"),
                    func.lower(Note.tags).like(f"%{search_term}%"),
                )
            )

            if book_id:
                stmt = stmt.where(Note.book_id == book_id)
            if note_type:
                stmt = stmt.where(Note.note_type == note_type)

            stmt = stmt.limit(limit)
            notes = session.execute(stmt).scalars().all()

            for note in notes:
                book = session.execute(
                    select(Book).where(Book.id == note.book_id)
                ).scalar_one_or_none()

                snippet = self._create_snippet(
                    f"{note.title or ''} {note.content}", search_term
                )
                score = self._calculate_relevance(
                    search_term, note.title, note.content
                )

                results.append(
                    NoteSearchResult(
                        id=note.id,
                        book_id=note.book_id,
                        book_title=book.title if book else "Unknown",
                        note_type=note.note_type,
                        title=note.title,
                        snippet=snippet,
                        relevance_score=score,
                    )
                )

        return sorted(results, key=lambda x: x.relevance_score, reverse=True)

    def search_quotes(
        self,
        query: str,
        book_id: Optional[str] = None,
        speaker: Optional[str] = None,
        limit: int = 20,
    ) -> list[QuoteSearchResult]:
        """Search quotes specifically.

        Args:
            query: Search query
            book_id: Filter by book
            speaker: Filter by speaker
            limit: Maximum results

        Returns:
            List of quote search results
        """
        from ..notes.models import Quote

        search_term = query.lower()
        results = []

        with self.db.get_session() as session:
            stmt = select(Quote).where(
                or_(
                    func.lower(Quote.text).like(f"%{search_term}%"),
                    func.lower(Quote.speaker).like(f"%{search_term}%"),
                    func.lower(Quote.context).like(f"%{search_term}%"),
                    func.lower(Quote.tags).like(f"%{search_term}%"),
                )
            )

            if book_id:
                stmt = stmt.where(Quote.book_id == book_id)
            if speaker:
                stmt = stmt.where(
                    func.lower(Quote.speaker).like(f"%{speaker.lower()}%")
                )

            stmt = stmt.limit(limit)
            quotes = session.execute(stmt).scalars().all()

            for quote in quotes:
                book = session.execute(
                    select(Book).where(Book.id == quote.book_id)
                ).scalar_one_or_none()

                snippet = self._create_snippet(quote.text, search_term)
                score = self._calculate_relevance(
                    search_term, quote.text, quote.speaker, quote.context
                )

                results.append(
                    QuoteSearchResult(
                        id=quote.id,
                        book_id=quote.book_id,
                        book_title=book.title if book else "Unknown",
                        text_snippet=snippet,
                        speaker=quote.speaker,
                        relevance_score=score,
                    )
                )

        return sorted(results, key=lambda x: x.relevance_score, reverse=True)

    def search_reviews(
        self,
        query: str,
        book_id: Optional[str] = None,
        min_rating: Optional[float] = None,
        limit: int = 20,
    ) -> list[ReviewSearchResult]:
        """Search reviews specifically.

        Args:
            query: Search query
            book_id: Filter by book
            min_rating: Minimum rating filter
            limit: Maximum results

        Returns:
            List of review search results
        """
        from ..reviews.models import Review

        search_term = query.lower()
        results = []

        with self.db.get_session() as session:
            stmt = select(Review).where(
                or_(
                    func.lower(Review.title).like(f"%{search_term}%"),
                    func.lower(Review.content).like(f"%{search_term}%"),
                    func.lower(Review.pros).like(f"%{search_term}%"),
                    func.lower(Review.cons).like(f"%{search_term}%"),
                )
            )

            if book_id:
                stmt = stmt.where(Review.book_id == book_id)
            if min_rating:
                stmt = stmt.where(Review.rating >= min_rating)

            stmt = stmt.limit(limit)
            reviews = session.execute(stmt).scalars().all()

            for review in reviews:
                book = session.execute(
                    select(Book).where(Book.id == review.book_id)
                ).scalar_one_or_none()

                snippet = self._create_snippet(
                    f"{review.title or ''} {review.content}", search_term
                )
                score = self._calculate_relevance(
                    search_term, review.title, review.content
                )

                results.append(
                    ReviewSearchResult(
                        id=review.id,
                        book_id=review.book_id,
                        book_title=book.title if book else "Unknown",
                        rating=review.rating,
                        snippet=snippet,
                        relevance_score=score,
                    )
                )

        return sorted(results, key=lambda x: x.relevance_score, reverse=True)

    # -------------------------------------------------------------------------
    # Suggestions and Autocomplete
    # -------------------------------------------------------------------------

    def get_suggestions(self, query: str, limit: int = 10) -> SearchSuggestions:
        """Get search suggestions for autocomplete.

        Args:
            query: Partial query string
            limit: Maximum suggestions

        Returns:
            SearchSuggestions
        """
        search_term = query.lower()
        suggestions: list[SearchSuggestion] = []

        with self.db.get_session() as session:
            # Book title suggestions
            books = (
                session.execute(
                    select(Book.title)
                    .where(func.lower(Book.title).like(f"%{search_term}%"))
                    .distinct()
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            for title in books:
                suggestions.append(
                    SearchSuggestion(text=title, result_type=ResultType.BOOK, count=1)
                )

            # Author suggestions
            authors = (
                session.execute(
                    select(Book.author, func.count(Book.id))
                    .where(func.lower(Book.author).like(f"%{search_term}%"))
                    .group_by(Book.author)
                    .limit(limit)
                )
                .all()
            )
            for author, count in authors:
                if author:
                    suggestions.append(
                        SearchSuggestion(
                            text=author, result_type=ResultType.AUTHOR, count=count
                        )
                    )

        # Sort by relevance (exact prefix match first)
        suggestions.sort(
            key=lambda x: (
                not x.text.lower().startswith(search_term),
                -x.count,
                len(x.text),
            )
        )

        return SearchSuggestions(query=query, suggestions=suggestions[:limit])

    # -------------------------------------------------------------------------
    # Internal Search Methods
    # -------------------------------------------------------------------------

    def _search_books(
        self, search_term: str, query: SearchQuery
    ) -> list[SearchResult]:
        """Search books and return unified results."""
        results = []

        with self.db.get_session() as session:
            stmt = select(Book).where(
                or_(
                    func.lower(Book.title).like(f"%{search_term}%"),
                    func.lower(Book.author).like(f"%{search_term}%"),
                    func.lower(Book.description).like(f"%{search_term}%"),
                    func.lower(Book.genres).like(f"%{search_term}%"),
                )
            )

            if query.book_status:
                stmt = stmt.where(Book.status == query.book_status)
            if query.genre:
                stmt = stmt.where(
                    func.lower(Book.genres).like(f"%{query.genre.lower()}%")
                )
            if query.author:
                stmt = stmt.where(
                    func.lower(Book.author).like(f"%{query.author.lower()}%")
                )
            if query.min_rating:
                stmt = stmt.where(Book.rating >= query.min_rating)

            books = session.execute(stmt).scalars().all()

            for book in books:
                snippet = self._create_snippet(
                    f"{book.title}. {book.description or ''}", search_term
                )
                score = self._calculate_relevance(
                    search_term, book.title, book.author, book.description
                )

                results.append(
                    SearchResult(
                        id=book.id,
                        result_type=ResultType.BOOK,
                        title=book.title,
                        subtitle=book.author,
                        snippet=snippet,
                        relevance_score=score,
                        created_at=(
                            datetime.fromisoformat(book.created_at)
                            if book.created_at
                            else None
                        ),
                        metadata={
                            "status": book.status,
                            "genres": book.genres,
                            "rating": book.rating,
                        },
                    )
                )

        return results

    def _search_notes(
        self, search_term: str, query: SearchQuery
    ) -> list[SearchResult]:
        """Search notes and return unified results."""
        from ..notes.models import Note

        results = []

        with self.db.get_session() as session:
            stmt = select(Note).where(
                or_(
                    func.lower(Note.title).like(f"%{search_term}%"),
                    func.lower(Note.content).like(f"%{search_term}%"),
                    func.lower(Note.tags).like(f"%{search_term}%"),
                )
            )

            if query.favorites_only:
                stmt = stmt.where(Note.is_favorite == True)  # noqa: E712

            notes = session.execute(stmt).scalars().all()

            for note in notes:
                book = session.execute(
                    select(Book).where(Book.id == note.book_id)
                ).scalar_one_or_none()

                snippet = self._create_snippet(note.content, search_term)
                score = self._calculate_relevance(
                    search_term, note.title, note.content
                )

                results.append(
                    SearchResult(
                        id=note.id,
                        result_type=ResultType.NOTE,
                        title=note.title or "Note",
                        subtitle=book.title if book else None,
                        snippet=snippet,
                        relevance_score=score,
                        created_at=(
                            datetime.fromisoformat(note.created_at)
                            if note.created_at
                            else None
                        ),
                        metadata={"note_type": note.note_type, "book_id": note.book_id},
                    )
                )

        return results

    def _search_quotes(
        self, search_term: str, query: SearchQuery
    ) -> list[SearchResult]:
        """Search quotes and return unified results."""
        from ..notes.models import Quote

        results = []

        with self.db.get_session() as session:
            stmt = select(Quote).where(
                or_(
                    func.lower(Quote.text).like(f"%{search_term}%"),
                    func.lower(Quote.speaker).like(f"%{search_term}%"),
                    func.lower(Quote.context).like(f"%{search_term}%"),
                )
            )

            if query.favorites_only:
                stmt = stmt.where(Quote.is_favorite == True)  # noqa: E712

            quotes = session.execute(stmt).scalars().all()

            for quote in quotes:
                book = session.execute(
                    select(Book).where(Book.id == quote.book_id)
                ).scalar_one_or_none()

                snippet = self._create_snippet(quote.text, search_term)
                score = self._calculate_relevance(
                    search_term, quote.text, quote.speaker
                )

                results.append(
                    SearchResult(
                        id=quote.id,
                        result_type=ResultType.QUOTE,
                        title=f'"{quote.text[:50]}..."' if len(quote.text) > 50 else f'"{quote.text}"',
                        subtitle=book.title if book else None,
                        snippet=snippet,
                        relevance_score=score,
                        created_at=(
                            datetime.fromisoformat(quote.created_at)
                            if quote.created_at
                            else None
                        ),
                        metadata={"speaker": quote.speaker, "book_id": quote.book_id},
                    )
                )

        return results

    def _search_reviews(
        self, search_term: str, query: SearchQuery
    ) -> list[SearchResult]:
        """Search reviews and return unified results."""
        from ..reviews.models import Review

        results = []

        with self.db.get_session() as session:
            stmt = select(Review).where(
                or_(
                    func.lower(Review.title).like(f"%{search_term}%"),
                    func.lower(Review.content).like(f"%{search_term}%"),
                )
            )

            if query.min_rating:
                stmt = stmt.where(Review.rating >= query.min_rating)

            reviews = session.execute(stmt).scalars().all()

            for review in reviews:
                book = session.execute(
                    select(Book).where(Book.id == review.book_id)
                ).scalar_one_or_none()

                snippet = self._create_snippet(review.content, search_term)
                score = self._calculate_relevance(
                    search_term, review.title, review.content
                )

                results.append(
                    SearchResult(
                        id=review.id,
                        result_type=ResultType.REVIEW,
                        title=review.title or "Review",
                        subtitle=book.title if book else None,
                        snippet=snippet,
                        relevance_score=score,
                        created_at=(
                            datetime.fromisoformat(review.created_at)
                            if review.created_at
                            else None
                        ),
                        metadata={"rating": review.rating, "book_id": review.book_id},
                    )
                )

        return results

    def _search_collections(
        self, search_term: str, query: SearchQuery
    ) -> list[SearchResult]:
        """Search collections and return unified results."""
        from ..collections.models import Collection

        results = []

        with self.db.get_session() as session:
            stmt = select(Collection).where(
                or_(
                    func.lower(Collection.name).like(f"%{search_term}%"),
                    func.lower(Collection.description).like(f"%{search_term}%"),
                )
            )

            collections = session.execute(stmt).scalars().all()

            for collection in collections:
                snippet = self._create_snippet(
                    f"{collection.name}. {collection.description or ''}", search_term
                )
                score = self._calculate_relevance(
                    search_term, collection.name, collection.description
                )

                results.append(
                    SearchResult(
                        id=collection.id,
                        result_type=ResultType.COLLECTION,
                        title=collection.name,
                        subtitle=f"{len(collection.books)} books",
                        snippet=snippet,
                        relevance_score=score,
                        created_at=(
                            datetime.fromisoformat(collection.created_at)
                            if collection.created_at
                            else None
                        ),
                        metadata={"book_count": len(collection.books)},
                    )
                )

        return results

    def _search_lists(
        self, search_term: str, query: SearchQuery
    ) -> list[SearchResult]:
        """Search reading lists and return unified results."""
        from ..lists.models import ReadingList

        results = []

        with self.db.get_session() as session:
            stmt = select(ReadingList).where(
                or_(
                    func.lower(ReadingList.name).like(f"%{search_term}%"),
                    func.lower(ReadingList.description).like(f"%{search_term}%"),
                )
            )

            lists = session.execute(stmt).scalars().all()

            for reading_list in lists:
                snippet = self._create_snippet(
                    f"{reading_list.name}. {reading_list.description or ''}",
                    search_term,
                )
                score = self._calculate_relevance(
                    search_term, reading_list.name, reading_list.description
                )

                results.append(
                    SearchResult(
                        id=reading_list.id,
                        result_type=ResultType.LIST,
                        title=reading_list.name,
                        subtitle=f"{len(reading_list.books)} books",
                        snippet=snippet,
                        relevance_score=score,
                        created_at=(
                            datetime.fromisoformat(reading_list.created_at)
                            if reading_list.created_at
                            else None
                        ),
                        metadata={"book_count": len(reading_list.books)},
                    )
                )

        return results

    def _search_tags(
        self, search_term: str, query: SearchQuery
    ) -> list[SearchResult]:
        """Search tags and return unified results."""
        from ..tags.models import Tag

        results = []

        with self.db.get_session() as session:
            stmt = select(Tag).where(
                or_(
                    func.lower(Tag.name).like(f"%{search_term}%"),
                    func.lower(Tag.description).like(f"%{search_term}%"),
                )
            )

            tags = session.execute(stmt).scalars().all()

            for tag in tags:
                snippet = self._create_snippet(
                    f"{tag.name}. {tag.description or ''}", search_term
                )
                score = self._calculate_relevance(search_term, tag.name, tag.description)

                results.append(
                    SearchResult(
                        id=tag.id,
                        result_type=ResultType.TAG,
                        title=tag.name,
                        subtitle=f"{len(tag.book_tags)} books",
                        snippet=snippet,
                        relevance_score=score,
                        created_at=(
                            datetime.fromisoformat(tag.created_at)
                            if tag.created_at
                            else None
                        ),
                        metadata={"color": tag.color, "book_count": len(tag.book_tags)},
                    )
                )

        return results

    def _search_authors(
        self, search_term: str, query: SearchQuery
    ) -> list[SearchResult]:
        """Search authors and return unified results."""
        results = []

        with self.db.get_session() as session:
            # Get distinct authors matching the query
            authors = (
                session.execute(
                    select(Book.author, func.count(Book.id))
                    .where(func.lower(Book.author).like(f"%{search_term}%"))
                    .group_by(Book.author)
                )
                .all()
            )

            for author, book_count in authors:
                if not author:
                    continue

                score = self._calculate_relevance(search_term, author)

                results.append(
                    SearchResult(
                        id=author,  # Use author name as ID
                        result_type=ResultType.AUTHOR,
                        title=author,
                        subtitle=f"{book_count} books",
                        snippet=f"Author of {book_count} books in your library",
                        relevance_score=score,
                        created_at=None,
                        metadata={"book_count": book_count},
                    )
                )

        return results

    def _advanced_search_books(
        self,
        search_terms: list[tuple[str, str]],
        must_terms: list[str],
        should_terms: list[str],
        exclude_terms: list[str],
    ) -> list[SearchResult]:
        """Advanced search for books."""
        results = []

        with self.db.get_session() as session:
            stmt = select(Book)

            # Apply field-specific filters
            for field, term in search_terms:
                if field == "title":
                    stmt = stmt.where(func.lower(Book.title).like(f"%{term}%"))
                elif field == "author":
                    stmt = stmt.where(func.lower(Book.author).like(f"%{term}%"))
                elif field == "genre":
                    stmt = stmt.where(func.lower(Book.genres).like(f"%{term}%"))

            books = session.execute(stmt).scalars().all()

            for book in books:
                text = f"{book.title} {book.author or ''} {book.description or ''}"
                text_lower = text.lower()

                # Apply boolean filters
                if must_terms and not all(t in text_lower for t in must_terms):
                    continue
                if exclude_terms and any(t in text_lower for t in exclude_terms):
                    continue

                # Calculate relevance
                score = 0.5
                if should_terms:
                    matches = sum(1 for t in should_terms if t in text_lower)
                    score = min(0.5 + (matches * 0.1), 1.0)

                results.append(
                    SearchResult(
                        id=book.id,
                        result_type=ResultType.BOOK,
                        title=book.title,
                        subtitle=book.author,
                        snippet=text[:150],
                        relevance_score=score,
                        created_at=None,
                        metadata={"status": book.status},
                    )
                )

        return results

    def _advanced_search_notes(
        self,
        search_terms: list[tuple[str, str]],
        must_terms: list[str],
        should_terms: list[str],
        exclude_terms: list[str],
    ) -> list[SearchResult]:
        """Advanced search for notes."""
        from ..notes.models import Note

        results = []

        with self.db.get_session() as session:
            stmt = select(Note)

            for field, term in search_terms:
                if field == "title":
                    stmt = stmt.where(func.lower(Note.title).like(f"%{term}%"))
                elif field == "content":
                    stmt = stmt.where(func.lower(Note.content).like(f"%{term}%"))
                elif field == "tag":
                    stmt = stmt.where(func.lower(Note.tags).like(f"%{term}%"))

            notes = session.execute(stmt).scalars().all()

            for note in notes:
                text = f"{note.title or ''} {note.content}"
                text_lower = text.lower()

                if must_terms and not all(t in text_lower for t in must_terms):
                    continue
                if exclude_terms and any(t in text_lower for t in exclude_terms):
                    continue

                score = 0.5
                if should_terms:
                    matches = sum(1 for t in should_terms if t in text_lower)
                    score = min(0.5 + (matches * 0.1), 1.0)

                book = session.execute(
                    select(Book).where(Book.id == note.book_id)
                ).scalar_one_or_none()

                results.append(
                    SearchResult(
                        id=note.id,
                        result_type=ResultType.NOTE,
                        title=note.title or "Note",
                        subtitle=book.title if book else None,
                        snippet=text[:150],
                        relevance_score=score,
                        created_at=None,
                        metadata={"note_type": note.note_type},
                    )
                )

        return results

    def _advanced_search_quotes(
        self,
        search_terms: list[tuple[str, str]],
        must_terms: list[str],
        should_terms: list[str],
        exclude_terms: list[str],
    ) -> list[SearchResult]:
        """Advanced search for quotes."""
        from ..notes.models import Quote

        results = []

        with self.db.get_session() as session:
            stmt = select(Quote)

            for field, term in search_terms:
                if field == "content":
                    stmt = stmt.where(func.lower(Quote.text).like(f"%{term}%"))
                elif field == "tag":
                    stmt = stmt.where(func.lower(Quote.tags).like(f"%{term}%"))

            quotes = session.execute(stmt).scalars().all()

            for quote in quotes:
                text = f"{quote.text} {quote.speaker or ''}"
                text_lower = text.lower()

                if must_terms and not all(t in text_lower for t in must_terms):
                    continue
                if exclude_terms and any(t in text_lower for t in exclude_terms):
                    continue

                score = 0.5
                if should_terms:
                    matches = sum(1 for t in should_terms if t in text_lower)
                    score = min(0.5 + (matches * 0.1), 1.0)

                book = session.execute(
                    select(Book).where(Book.id == quote.book_id)
                ).scalar_one_or_none()

                results.append(
                    SearchResult(
                        id=quote.id,
                        result_type=ResultType.QUOTE,
                        title=f'"{quote.text[:50]}..."',
                        subtitle=book.title if book else None,
                        snippet=text[:150],
                        relevance_score=score,
                        created_at=None,
                        metadata={"speaker": quote.speaker},
                    )
                )

        return results

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _calculate_relevance(
        self, query: str, *texts: Optional[str]
    ) -> float:
        """Calculate relevance score for search results.

        Simple TF-based scoring for now.
        """
        query_terms = query.lower().split()
        score = 0.0
        total_weight = 0.0

        for i, text in enumerate(texts):
            if not text:
                continue

            text_lower = text.lower()
            weight = 1.0 / (i + 1)  # First field has highest weight
            total_weight += weight

            for term in query_terms:
                if term in text_lower:
                    # Exact match bonus
                    if text_lower == term:
                        score += weight * 1.0
                    # Starts with bonus
                    elif text_lower.startswith(term):
                        score += weight * 0.8
                    # Contains
                    else:
                        score += weight * 0.5

        if total_weight == 0:
            return 0.0

        return min(score / (total_weight * len(query_terms)), 1.0)

    def _create_snippet(
        self, text: str, query: str, max_length: int = 150
    ) -> str:
        """Create a highlighted snippet around the search term."""
        if not text:
            return ""

        text_lower = text.lower()
        query_lower = query.lower()

        # Find the position of the query
        pos = text_lower.find(query_lower)

        if pos == -1:
            # Query not found, return beginning
            return text[:max_length] + "..." if len(text) > max_length else text

        # Calculate snippet bounds
        start = max(0, pos - 50)
        end = min(len(text), pos + len(query) + 100)

        snippet = text[start:end]

        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet

    def _sort_results(
        self,
        results: list[SearchResult],
        sort_by: SortBy,
        sort_order,
    ) -> list[SearchResult]:
        """Sort search results."""
        reverse = sort_order.value == "desc"

        if sort_by == SortBy.RELEVANCE:
            return sorted(results, key=lambda x: x.relevance_score, reverse=True)
        elif sort_by == SortBy.DATE:
            return sorted(
                results,
                key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=reverse,
            )
        elif sort_by == SortBy.TITLE:
            return sorted(results, key=lambda x: x.title.lower(), reverse=reverse)

        return results

    def _build_query_string(self, query: AdvancedSearchQuery) -> str:
        """Build a human-readable query string from advanced query."""
        parts = []
        if query.title:
            parts.append(f"title:{query.title}")
        if query.author:
            parts.append(f"author:{query.author}")
        if query.content:
            parts.append(f"content:{query.content}")
        if query.tag:
            parts.append(f"tag:{query.tag}")
        if query.must_include:
            parts.append(f"+({' '.join(query.must_include)})")
        if query.should_include:
            parts.append(f"({' '.join(query.should_include)})")
        if query.must_exclude:
            parts.append(f"-({' '.join(query.must_exclude)})")
        return " ".join(parts) or "advanced search"
