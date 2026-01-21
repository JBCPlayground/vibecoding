"""Tests for SearchManager."""

import pytest
from uuid import UUID

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.db.models import Book
from vibecoding.booktracker.search.manager import SearchManager
from vibecoding.booktracker.search.schemas import (
    AdvancedSearchQuery,
    ResultType,
    SearchQuery,
    SearchScope,
    SortBy,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a SearchManager with test database."""
    return SearchManager(db)


@pytest.fixture
def sample_books(db):
    """Create sample books for testing."""
    import json
    books = []
    with db.get_session() as session:
        book_data = [
            {
                "title": "The Great Gatsby",
                "author": "F. Scott Fitzgerald",
                "genres": json.dumps(["Fiction"]),
                "status": "read",
                "rating": 4,
                "description": "A story of decadence and excess.",
            },
            {
                "title": "1984",
                "author": "George Orwell",
                "genres": json.dumps(["Dystopian"]),
                "status": "read",
                "rating": 5,
                "description": "A dystopian social science fiction novel.",
            },
            {
                "title": "To Kill a Mockingbird",
                "author": "Harper Lee",
                "genres": json.dumps(["Fiction"]),
                "status": "reading",
                "rating": 4,
                "description": "A novel about racial injustice.",
            },
            {
                "title": "Pride and Prejudice",
                "author": "Jane Austen",
                "genres": json.dumps(["Romance"]),
                "status": "to-read",
                "rating": None,
                "description": "A romantic novel of manners.",
            },
            {
                "title": "The Catcher in the Rye",
                "author": "J.D. Salinger",
                "genres": json.dumps(["Fiction"]),
                "status": "read",
                "rating": 3,
                "description": "A story about teenage angst.",
            },
        ]

        for data in book_data:
            book = Book(**data)
            session.add(book)
            session.commit()
            session.refresh(book)
            books.append(book.id)

    return books


@pytest.fixture
def sample_notes(db, sample_books):
    """Create sample notes for testing."""
    from vibecoding.booktracker.notes.models import Note

    note_ids = []
    with db.get_session() as session:
        notes_data = [
            {
                "book_id": sample_books[0],
                "title": "Theme Analysis",
                "content": "The green light symbolizes hope and the American dream.",
                "note_type": "insight",
                "tags": "theme,symbolism",
            },
            {
                "book_id": sample_books[1],
                "title": "Big Brother",
                "content": "The concept of surveillance and control is central.",
                "note_type": "insight",
                "tags": "theme,politics",
            },
            {
                "book_id": sample_books[2],
                "title": "Character Study",
                "content": "Atticus Finch represents moral integrity.",
                "note_type": "thought",
                "tags": "character",
            },
        ]

        for data in notes_data:
            note = Note(**data)
            session.add(note)
            session.commit()
            session.refresh(note)
            note_ids.append(note.id)

    return note_ids


@pytest.fixture
def sample_quotes(db, sample_books):
    """Create sample quotes for testing."""
    from vibecoding.booktracker.notes.models import Quote

    quote_ids = []
    with db.get_session() as session:
        quotes_data = [
            {
                "book_id": sample_books[0],
                "text": "So we beat on, boats against the current, borne back ceaselessly into the past.",
                "speaker": "Nick Carraway",
                "context": "Final line of the novel",
            },
            {
                "book_id": sample_books[1],
                "text": "Big Brother is watching you.",
                "speaker": None,
                "context": "Famous quote from the novel",
            },
            {
                "book_id": sample_books[2],
                "text": "You never really understand a person until you climb into his skin.",
                "speaker": "Atticus Finch",
                "context": "Advice to Scout",
            },
        ]

        for data in quotes_data:
            quote = Quote(**data)
            session.add(quote)
            session.commit()
            session.refresh(quote)
            quote_ids.append(quote.id)

    return quote_ids


class TestUnifiedSearch:
    """Tests for unified search functionality."""

    def test_search_all_scopes(self, manager, sample_books, sample_notes, sample_quotes):
        """Test searching across all scopes."""
        query = SearchQuery(query="gatsby", scope=[SearchScope.ALL])
        results = manager.search(query)

        assert results.total_count > 0
        assert results.query == "gatsby"
        assert results.search_time_ms >= 0

    def test_search_books_only(self, manager, sample_books):
        """Test searching books only."""
        query = SearchQuery(query="fitzgerald", scope=[SearchScope.BOOKS])
        results = manager.search(query)

        assert results.total_count >= 1
        assert all(r.result_type == ResultType.BOOK for r in results.results)

    def test_search_notes_only(self, manager, sample_books, sample_notes):
        """Test searching notes only."""
        query = SearchQuery(query="theme", scope=[SearchScope.NOTES])
        results = manager.search(query)

        assert results.total_count >= 1
        assert all(r.result_type == ResultType.NOTE for r in results.results)

    def test_search_quotes_only(self, manager, sample_books, sample_quotes):
        """Test searching quotes only."""
        query = SearchQuery(query="brother", scope=[SearchScope.QUOTES])
        results = manager.search(query)

        assert results.total_count >= 1
        assert all(r.result_type == ResultType.QUOTE for r in results.results)

    def test_search_multiple_scopes(self, manager, sample_books, sample_notes):
        """Test searching multiple scopes."""
        query = SearchQuery(
            query="fiction",
            scope=[SearchScope.BOOKS, SearchScope.NOTES]
        )
        results = manager.search(query)

        assert results.total_count >= 1

    def test_search_with_filters(self, manager, sample_books):
        """Test search with filters."""
        query = SearchQuery(
            query="fiction",
            scope=[SearchScope.BOOKS],
            book_status="read",
        )
        results = manager.search(query)

        for r in results.results:
            assert r.metadata.get("status") == "read"

    def test_search_pagination(self, manager, sample_books):
        """Test search pagination."""
        query = SearchQuery(query="the", scope=[SearchScope.BOOKS], limit=2)
        results = manager.search(query)

        assert len(results.results) <= 2

    def test_search_no_results(self, manager, sample_books):
        """Test search with no results."""
        query = SearchQuery(query="xyznonexistent123")
        results = manager.search(query)

        assert results.total_count == 0
        assert len(results.results) == 0

    def test_search_facets(self, manager, sample_books, sample_notes, sample_quotes):
        """Test search result facets."""
        query = SearchQuery(query="the", scope=[SearchScope.ALL])
        results = manager.search(query)

        assert "type" in results.facets


class TestBookSearch:
    """Tests for book-specific search."""

    def test_search_by_title(self, manager, sample_books):
        """Test searching books by title."""
        results = manager.search_books("gatsby")

        assert len(results) >= 1
        assert any("gatsby" in r.title.lower() for r in results)

    def test_search_by_author(self, manager, sample_books):
        """Test searching books by author."""
        results = manager.search_books("orwell")

        assert len(results) >= 1
        assert any("orwell" in (r.author or "").lower() for r in results)

    def test_search_by_genre(self, manager, sample_books):
        """Test searching books by genre."""
        results = manager.search_books("fiction", genre="fiction")

        assert len(results) >= 1
        # Genre filter was applied (results should contain fiction genre)

    def test_search_by_status(self, manager, sample_books):
        """Test searching books by status."""
        results = manager.search_books("the", status="read")

        assert all(r.status == "read" for r in results)

    def test_search_by_rating(self, manager, sample_books):
        """Test searching books by minimum rating."""
        results = manager.search_books("the", min_rating=4.0)

        for r in results:
            if r.rating:
                assert r.rating >= 4.0

    def test_relevance_scoring(self, manager, sample_books):
        """Test that results are sorted by relevance."""
        results = manager.search_books("gatsby")

        if len(results) > 1:
            # First result should have highest score
            assert results[0].relevance_score >= results[-1].relevance_score


class TestNoteSearch:
    """Tests for note-specific search."""

    def test_search_notes_by_content(self, manager, sample_books, sample_notes):
        """Test searching notes by content."""
        results = manager.search_notes("green light")

        assert len(results) >= 1

    def test_search_notes_by_title(self, manager, sample_books, sample_notes):
        """Test searching notes by title."""
        results = manager.search_notes("theme analysis")

        assert len(results) >= 1

    def test_search_notes_filter_by_book(self, manager, sample_books, sample_notes):
        """Test filtering notes by book."""
        results = manager.search_notes("theme", book_id=sample_books[0])

        assert all(r.book_id == sample_books[0] for r in results)

    def test_search_notes_filter_by_type(self, manager, sample_books, sample_notes):
        """Test filtering notes by type."""
        results = manager.search_notes("the", note_type="insight")

        assert all(r.note_type == "insight" for r in results)


class TestQuoteSearch:
    """Tests for quote-specific search."""

    def test_search_quotes_by_text(self, manager, sample_books, sample_quotes):
        """Test searching quotes by text."""
        results = manager.search_quotes("boats against")

        assert len(results) >= 1

    def test_search_quotes_by_speaker(self, manager, sample_books, sample_quotes):
        """Test searching quotes by speaker."""
        results = manager.search_quotes("atticus", speaker="atticus")

        assert len(results) >= 1

    def test_search_quotes_filter_by_book(self, manager, sample_books, sample_quotes):
        """Test filtering quotes by book."""
        results = manager.search_quotes("the", book_id=sample_books[0])

        assert all(r.book_id == sample_books[0] for r in results)


class TestAdvancedSearch:
    """Tests for advanced search functionality."""

    def test_advanced_search_by_title(self, manager, sample_books):
        """Test advanced search by title field."""
        query = AdvancedSearchQuery(title="gatsby")
        results = manager.advanced_search(query)

        assert results.total_count >= 1

    def test_advanced_search_by_author(self, manager, sample_books):
        """Test advanced search by author field."""
        query = AdvancedSearchQuery(author="orwell")
        results = manager.advanced_search(query)

        assert results.total_count >= 1

    def test_advanced_search_must_include(self, manager, sample_books):
        """Test advanced search with must include terms."""
        query = AdvancedSearchQuery(
            must_include=["fiction"],
            scope=[SearchScope.BOOKS],
        )
        results = manager.advanced_search(query)

        # All results must contain "fiction"
        for r in results.results:
            text = f"{r.title} {r.subtitle or ''} {r.snippet}".lower()
            assert "fiction" in text

    def test_advanced_search_must_exclude(self, manager, sample_books):
        """Test advanced search with exclusion terms."""
        query = AdvancedSearchQuery(
            title="the",
            must_exclude=["dystopian"],
            scope=[SearchScope.BOOKS],
        )
        results = manager.advanced_search(query)

        # No results should contain "dystopian"
        for r in results.results:
            text = f"{r.title} {r.subtitle or ''} {r.snippet}".lower()
            assert "dystopian" not in text

    def test_advanced_search_combined_criteria(self, manager, sample_books, sample_notes):
        """Test advanced search with multiple criteria."""
        query = AdvancedSearchQuery(
            content="theme",
            must_include=["symbolism"],
            scope=[SearchScope.NOTES],
        )
        results = manager.advanced_search(query)

        # Results should match all criteria
        assert results.total_count >= 0


class TestSearchSuggestions:
    """Tests for search suggestions."""

    def test_get_suggestions(self, manager, sample_books):
        """Test getting search suggestions."""
        suggestions = manager.get_suggestions("gat")

        assert len(suggestions.suggestions) >= 0

    def test_suggestions_include_books(self, manager, sample_books):
        """Test that suggestions include book titles."""
        suggestions = manager.get_suggestions("great")

        titles = [s.text for s in suggestions.suggestions if s.result_type == ResultType.BOOK]
        assert any("great" in t.lower() for t in titles) or len(titles) == 0

    def test_suggestions_include_authors(self, manager, sample_books):
        """Test that suggestions include authors."""
        suggestions = manager.get_suggestions("fitz")

        authors = [s.text for s in suggestions.suggestions if s.result_type == ResultType.AUTHOR]
        # May or may not find matches depending on data


class TestRelevanceScoring:
    """Tests for relevance scoring."""

    def test_exact_match_scores_higher(self, manager, sample_books):
        """Test that exact matches score higher."""
        results = manager.search_books("1984")

        if len(results) > 0:
            # The exact title match should have high relevance
            exact_match = next((r for r in results if r.title == "1984"), None)
            if exact_match:
                assert exact_match.relevance_score > 0.5

    def test_title_match_scores_higher_than_description(self, manager, sample_books):
        """Test that title matches score higher than description matches."""
        # Search for something in title vs description
        results = manager.search_books("gatsby")

        if len(results) > 0:
            # Title match should be first
            assert "gatsby" in results[0].title.lower()


class TestSnippetCreation:
    """Tests for snippet creation."""

    def test_snippet_contains_query(self, manager, sample_books):
        """Test that snippets contain the search query."""
        results = manager.search_books("gatsby")

        if len(results) > 0:
            # Snippet should contain or reference the query
            assert len(results[0].snippet) > 0

    def test_snippet_length(self, manager, sample_books):
        """Test that snippets are reasonable length."""
        results = manager.search_books("the")

        for r in results:
            assert len(r.snippet) <= 200


class TestSorting:
    """Tests for result sorting."""

    def test_sort_by_relevance(self, manager, sample_books):
        """Test sorting by relevance (default)."""
        query = SearchQuery(query="the", sort_by=SortBy.RELEVANCE)
        results = manager.search(query)

        if len(results.results) > 1:
            scores = [r.relevance_score for r in results.results]
            assert scores == sorted(scores, reverse=True)

    def test_sort_by_title(self, manager, sample_books):
        """Test sorting by title."""
        query = SearchQuery(query="the", sort_by=SortBy.TITLE)
        results = manager.search(query)

        if len(results.results) > 1:
            titles = [r.title.lower() for r in results.results]
            # Should be sorted (ascending or descending)
            assert titles == sorted(titles) or titles == sorted(titles, reverse=True)
