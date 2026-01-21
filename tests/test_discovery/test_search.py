"""Tests for advanced search functionality."""

import pytest
from datetime import date, timedelta

from vibecoding.booktracker.discovery.search import (
    AdvancedSearch,
    SearchFilters,
    SearchResult,
    SortOrder,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus


class TestSearchFilters:
    """Tests for SearchFilters dataclass."""

    def test_default_values(self):
        """Test default filter values."""
        filters = SearchFilters()
        assert filters.query is None
        assert filters.status is None
        assert filters.sort_by == SortOrder.DATE_ADDED_DESC
        assert filters.limit == 50
        assert filters.offset == 0

    def test_custom_values(self):
        """Test custom filter values."""
        filters = SearchFilters(
            query="test",
            author="Author",
            status=BookStatus.COMPLETED,
            min_rating=4,
            limit=10,
        )
        assert filters.query == "test"
        assert filters.author == "Author"
        assert filters.status == BookStatus.COMPLETED
        assert filters.min_rating == 4
        assert filters.limit == 10


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_has_more_true(self):
        """Test has_more when more pages exist."""
        result = SearchResult(
            books=[],
            total_count=100,
            filters_applied=SearchFilters(),
            page=1,
            total_pages=4,
        )
        assert result.has_more is True

    def test_has_more_false(self):
        """Test has_more on last page."""
        result = SearchResult(
            books=[],
            total_count=50,
            filters_applied=SearchFilters(),
            page=2,
            total_pages=2,
        )
        assert result.has_more is False


class TestAdvancedSearch:
    """Tests for AdvancedSearch class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def searcher(self, db):
        """Create searcher instance."""
        return AdvancedSearch(db)

    @pytest.fixture
    def sample_books(self, db):
        """Create sample books for testing."""
        books = []
        today = date.today()

        # Book 1: Fiction, completed
        books.append(db.create_book(BookCreate(
            title="The Great Novel",
            author="Jane Author",
            status=BookStatus.COMPLETED,
            rating=5,
            page_count=350,
            tags=["fiction", "literary"],
            date_added=today - timedelta(days=30),
            date_finished=today - timedelta(days=10),
            publication_year=2020,
        )))

        # Book 2: Fantasy, wishlist
        books.append(db.create_book(BookCreate(
            title="Dragon's Quest",
            author="John Writer",
            status=BookStatus.WISHLIST,
            page_count=500,
            tags=["fantasy", "adventure"],
            date_added=today - timedelta(days=20),
            series="Dragon Chronicles",
            series_index=1,
        )))

        # Book 3: Fantasy, wishlist (same series)
        books.append(db.create_book(BookCreate(
            title="Dragon's Return",
            author="John Writer",
            status=BookStatus.WISHLIST,
            page_count=480,
            tags=["fantasy", "adventure"],
            date_added=today - timedelta(days=15),
            series="Dragon Chronicles",
            series_index=2,
        )))

        # Book 4: Non-fiction, reading
        books.append(db.create_book(BookCreate(
            title="Science of Everything",
            author="Dr. Expert",
            status=BookStatus.READING,
            page_count=200,
            tags=["non-fiction", "science"],
            date_added=today - timedelta(days=5),
        )))

        # Book 5: Fiction, completed, by same author as Book 1
        books.append(db.create_book(BookCreate(
            title="Another Great Novel",
            author="Jane Author",
            status=BookStatus.COMPLETED,
            rating=4,
            page_count=280,
            tags=["fiction"],
            date_added=today - timedelta(days=25),
            date_finished=today - timedelta(days=5),
        )))

        return books

    def test_quick_search_by_title(self, searcher, sample_books):
        """Test quick search by title."""
        results = searcher.quick_search("Dragon")
        assert len(results) == 2
        assert all("Dragon" in book.title for book in results)

    def test_quick_search_by_author(self, searcher, sample_books):
        """Test quick search by author."""
        results = searcher.quick_search("Jane")
        assert len(results) == 2
        assert all("Jane" in book.author for book in results)

    def test_quick_search_case_insensitive(self, searcher, sample_books):
        """Test case-insensitive search."""
        results = searcher.quick_search("dragon")
        assert len(results) == 2

    def test_quick_search_no_results(self, searcher, sample_books):
        """Test search with no results."""
        results = searcher.quick_search("NonexistentBook")
        assert len(results) == 0

    def test_search_by_author(self, searcher, sample_books):
        """Test search by author name."""
        results = searcher.search_by_author("John Writer")
        assert len(results) == 2
        assert all(book.author == "John Writer" for book in results)

    def test_search_by_author_with_status(self, searcher, sample_books):
        """Test search by author with status filter."""
        results = searcher.search_by_author("Jane Author", status=BookStatus.COMPLETED)
        assert len(results) == 2

    def test_search_by_series(self, searcher, sample_books):
        """Test search by series name."""
        results = searcher.search_by_series("Dragon Chronicles")
        assert len(results) == 2
        # Should be sorted by series index
        assert results[0].series_index == 1
        assert results[1].series_index == 2

    def test_search_by_tags_any(self, searcher, sample_books):
        """Test search by tags (any match)."""
        results = searcher.search_by_tags(["fiction", "science"])
        # Should find books with fiction OR science
        assert len(results) >= 3

    def test_search_by_tags_all(self, searcher, sample_books):
        """Test search by tags (all must match)."""
        results = searcher.search_by_tags(["fantasy", "adventure"], match_all=True)
        assert len(results) == 2

    def test_get_unread_books(self, searcher, sample_books):
        """Test getting unread books."""
        results = searcher.get_unread_books()
        assert len(results) == 2
        for book in results:
            assert book.status in [BookStatus.WISHLIST.value, BookStatus.ON_HOLD.value]

    def test_get_highly_rated(self, searcher, sample_books):
        """Test getting highly rated books."""
        results = searcher.get_highly_rated(min_rating=4)
        assert len(results) == 2
        for book in results:
            assert book.rating >= 4

    def test_get_long_books(self, searcher, sample_books):
        """Test getting long books."""
        results = searcher.get_long_books(min_pages=400)
        assert len(results) == 2
        for book in results:
            assert book.page_count >= 400

    def test_get_short_books(self, searcher, sample_books):
        """Test getting short books."""
        results = searcher.get_short_books(max_pages=250)
        assert len(results) == 1
        assert results[0].page_count == 200

    def test_search_with_pagination(self, searcher, sample_books):
        """Test search with pagination."""
        filters = SearchFilters(limit=2, offset=0)
        result = searcher.search(filters)

        assert len(result.books) == 2
        assert result.total_count == 5
        assert result.total_pages == 3

    def test_search_with_rating_filters(self, searcher, sample_books):
        """Test search with rating filters."""
        filters = SearchFilters(min_rating=4, max_rating=5)
        result = searcher.search(filters)

        for book in result.books:
            assert 4 <= book.rating <= 5

    def test_search_with_page_filters(self, searcher, sample_books):
        """Test search with page count filters."""
        filters = SearchFilters(min_pages=250, max_pages=400)
        result = searcher.search(filters)

        for book in result.books:
            assert 250 <= book.page_count <= 400

    def test_search_with_status_filter(self, searcher, sample_books):
        """Test search with status filter."""
        filters = SearchFilters(status=BookStatus.COMPLETED)
        result = searcher.search(filters)

        assert len(result.books) == 2
        for book in result.books:
            assert book.status == BookStatus.COMPLETED.value

    def test_search_with_multiple_statuses(self, searcher, sample_books):
        """Test search with multiple status filters."""
        filters = SearchFilters(statuses=[BookStatus.WISHLIST, BookStatus.READING])
        result = searcher.search(filters)

        assert len(result.books) == 3

    def test_search_sort_by_title(self, searcher, sample_books):
        """Test search sorted by title."""
        filters = SearchFilters(sort_by=SortOrder.TITLE_ASC)
        result = searcher.search(filters)

        titles = [b.title for b in result.books]
        assert titles == sorted(titles)

    def test_search_sort_by_rating(self, searcher, sample_books):
        """Test search sorted by rating."""
        filters = SearchFilters(sort_by=SortOrder.RATING_DESC, status=BookStatus.COMPLETED)
        result = searcher.search(filters)

        # First book should have higher or equal rating
        if len(result.books) >= 2:
            assert result.books[0].rating >= result.books[1].rating

    def test_search_by_publication_year(self, searcher, sample_books):
        """Test search by publication year."""
        filters = SearchFilters(year_published=2020)
        result = searcher.search(filters)

        for book in result.books:
            assert book.publication_year == 2020

    def test_search_empty_database(self, db):
        """Test search with empty database."""
        searcher = AdvancedSearch(db)
        results = searcher.quick_search("anything")
        assert len(results) == 0

    def test_search_result_pagination_info(self, searcher, sample_books):
        """Test pagination info in search result."""
        filters = SearchFilters(limit=2, offset=2)
        result = searcher.search(filters)

        assert result.page == 2
        assert result.total_pages == 3
        assert result.total_count == 5
