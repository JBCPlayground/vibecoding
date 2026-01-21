"""Tests for similar books finder."""

import pytest
from datetime import date, timedelta

from vibecoding.booktracker.discovery.similar import (
    SimilarBooksFinder,
    SimilarityScore,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus


class TestSimilarityScore:
    """Tests for SimilarityScore dataclass."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def sample_book(self, db):
        """Create a sample book."""
        return db.create_book(BookCreate(
            title="Test Book",
            author="Test Author",
            status=BookStatus.WISHLIST,
        ))

    def test_score_calculation(self, sample_book):
        """Test automatic score calculation."""
        score = SimilarityScore(
            book=sample_book,
            author_score=1.0,
            genre_score=0.5,
            series_score=0.0,
            length_score=0.8,
            era_score=0.9,
            rating_score=0.7,
        )

        # Total score should be weighted average
        assert score.total_score > 0
        assert score.total_score <= 1.0

    def test_score_with_match_reasons(self, sample_book):
        """Test score with match reasons."""
        score = SimilarityScore(
            book=sample_book,
            author_score=1.0,
            match_reasons=["Same author: Test Author"],
        )

        assert len(score.match_reasons) == 1
        assert "Same author" in score.match_reasons[0]


class TestSimilarBooksFinder:
    """Tests for SimilarBooksFinder class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def finder(self, db):
        """Create finder instance."""
        return SimilarBooksFinder(db)

    @pytest.fixture
    def sample_books(self, db):
        """Create sample books for testing."""
        books = {}

        # Source book - completed, highly rated
        books["source"] = db.create_book(BookCreate(
            title="The Fantasy Epic",
            author="Famous Author",
            status=BookStatus.COMPLETED,
            rating=5,
            page_count=400,
            tags=["fantasy", "epic", "adventure"],
            series="Great Series",
            series_index=1,
            publication_year=2020,
        ))

        # Similar by author (unread)
        books["same_author"] = db.create_book(BookCreate(
            title="Another by Famous",
            author="Famous Author",
            status=BookStatus.WISHLIST,
            tags=["fantasy"],
            page_count=350,
        ))

        # Similar by series (unread)
        books["same_series"] = db.create_book(BookCreate(
            title="Great Series Book 2",
            author="Famous Author",
            status=BookStatus.WISHLIST,
            series="Great Series",
            series_index=2,
            tags=["fantasy", "epic"],
        ))

        # Similar by genre (unread)
        books["same_genre"] = db.create_book(BookCreate(
            title="Another Fantasy Book",
            author="Different Author",
            status=BookStatus.WISHLIST,
            tags=["fantasy", "adventure"],
            page_count=380,
            publication_year=2021,
        ))

        # Not similar (different genre)
        books["different"] = db.create_book(BookCreate(
            title="Romance Novel",
            author="Romance Author",
            status=BookStatus.WISHLIST,
            tags=["romance", "contemporary"],
            page_count=250,
        ))

        # Already read book
        books["read"] = db.create_book(BookCreate(
            title="Read Fantasy",
            author="Famous Author",
            status=BookStatus.COMPLETED,
            tags=["fantasy"],
        ))

        return books

    def test_find_similar(self, finder, sample_books):
        """Test finding similar books."""
        source_id = sample_books["source"].id
        similar = finder.find_similar(source_id, limit=10)

        assert len(similar) > 0
        # Source book should not be in results
        assert all(s.book.id != source_id for s in similar)

    def test_find_similar_excludes_read(self, finder, sample_books):
        """Test that similar excludes read books by default."""
        source_id = sample_books["source"].id
        similar = finder.find_similar(source_id, include_read=False)

        for s in similar:
            assert s.book.status in [
                BookStatus.WISHLIST.value,
                BookStatus.ON_HOLD.value,
            ]

    def test_find_similar_includes_read(self, finder, sample_books):
        """Test including read books in similar."""
        source_id = sample_books["source"].id
        similar = finder.find_similar(source_id, include_read=True)

        # Should have more results when including read
        similar_unread = finder.find_similar(source_id, include_read=False)
        assert len(similar) >= len(similar_unread)

    def test_find_similar_sorted_by_score(self, finder, sample_books):
        """Test that results are sorted by score."""
        source_id = sample_books["source"].id
        similar = finder.find_similar(source_id)

        scores = [s.total_score for s in similar]
        assert scores == sorted(scores, reverse=True)

    def test_find_similar_book_not_found(self, finder):
        """Test with non-existent book."""
        similar = finder.find_similar("nonexistent-id")
        assert len(similar) == 0

    def test_find_similar_to_favorites(self, db, sample_books):
        """Test finding similar to favorite books."""
        finder = SimilarBooksFinder(db)
        similar = finder.find_similar_to_favorites(min_rating=4)

        # Should find books similar to the 5-star book
        assert len(similar) > 0

    def test_find_similar_to_favorites_empty(self, db):
        """Test similar to favorites with no rated books."""
        finder = SimilarBooksFinder(db)
        similar = finder.find_similar_to_favorites()

        assert len(similar) == 0

    def test_find_by_author(self, finder, sample_books):
        """Test finding books by author."""
        books = finder.find_by_author("Famous Author")

        assert len(books) >= 3
        for book in books:
            assert "famous" in book.author.lower()

    def test_find_by_author_exclude(self, finder, sample_books):
        """Test finding books by author excluding a book."""
        source_id = sample_books["source"].id
        books = finder.find_by_author("Famous Author", exclude_book_id=source_id)

        assert all(b.id != source_id for b in books)

    def test_find_in_same_series(self, finder, sample_books):
        """Test finding books in same series."""
        books = finder.find_in_same_series("Great Series")

        assert len(books) == 2
        # Should be sorted by series index
        assert books[0].series_index < books[1].series_index

    def test_find_in_same_series_exclude(self, finder, sample_books):
        """Test finding series books excluding one."""
        source_id = sample_books["source"].id
        books = finder.find_in_same_series("Great Series", exclude_book_id=source_id)

        assert len(books) == 1
        assert books[0].series_index == 2

    def test_find_in_same_series_empty(self, finder):
        """Test finding series with no series name."""
        books = finder.find_in_same_series("")
        assert len(books) == 0

    def test_find_by_tags_any(self, finder, sample_books):
        """Test finding books by tags (any match)."""
        books = finder.find_by_tags(["fantasy", "romance"])

        # Should find books with fantasy OR romance
        assert len(books) >= 4

    def test_find_by_tags_all(self, finder, sample_books):
        """Test finding books by tags (all must match)."""
        books = finder.find_by_tags(["fantasy", "adventure"], match_all=True)

        # Fewer books should match all tags
        assert len(books) >= 1

    def test_find_by_tags_empty(self, finder):
        """Test finding books with empty tag list."""
        books = finder.find_by_tags([])
        assert len(books) == 0

    def test_similarity_score_author(self, finder, sample_books):
        """Test author similarity scoring."""
        source_id = sample_books["source"].id
        similar = finder.find_similar(source_id)

        # Same author book should score highly
        same_author = next((s for s in similar if s.book.id == sample_books["same_author"].id), None)
        if same_author:
            assert same_author.author_score == 1.0

    def test_similarity_score_series(self, finder, sample_books):
        """Test series similarity scoring."""
        source_id = sample_books["source"].id
        similar = finder.find_similar(source_id)

        # Same series book should score highly on series
        same_series = next((s for s in similar if s.book.id == sample_books["same_series"].id), None)
        if same_series:
            assert same_series.series_score == 1.0

    def test_similarity_score_genre(self, finder, sample_books):
        """Test genre similarity scoring."""
        source_id = sample_books["source"].id
        similar = finder.find_similar(source_id)

        # Same genre book should have genre score > 0
        same_genre = next((s for s in similar if s.book.id == sample_books["same_genre"].id), None)
        if same_genre:
            assert same_genre.genre_score > 0

    def test_match_reasons_populated(self, finder, sample_books):
        """Test that match reasons are populated."""
        source_id = sample_books["source"].id
        similar = finder.find_similar(source_id)

        # Books with high scores should have reasons
        for s in similar:
            if s.total_score > 0.3:
                assert len(s.match_reasons) > 0

    def test_minimum_threshold(self, finder, sample_books):
        """Test minimum similarity threshold."""
        source_id = sample_books["source"].id
        similar = finder.find_similar(source_id)

        # All results should be above minimum threshold
        for s in similar:
            assert s.total_score > 0.1

    def test_limit_respected(self, finder, sample_books):
        """Test that limit is respected."""
        source_id = sample_books["source"].id
        similar = finder.find_similar(source_id, limit=2)

        assert len(similar) <= 2
