"""Tests for recommendation engine."""

import pytest
from datetime import date, timedelta

from vibecoding.booktracker.discovery.recommendations import (
    RecommendationEngine,
    Recommendation,
    RecommendationType,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus


class TestRecommendationType:
    """Tests for RecommendationType enum."""

    def test_type_values(self):
        """Test recommendation type values."""
        assert RecommendationType.BY_AUTHOR.value == "by_author"
        assert RecommendationType.BY_GENRE.value == "by_genre"
        assert RecommendationType.BY_SERIES.value == "by_series"
        assert RecommendationType.QUICK_READ.value == "quick_read"
        assert RecommendationType.READ_NEXT.value == "read_next"


class TestRecommendation:
    """Tests for Recommendation dataclass."""

    @pytest.fixture
    def sample_book(self, db):
        """Create a sample book."""
        return db.create_book(BookCreate(
            title="Test Book",
            author="Test Author",
            status=BookStatus.WISHLIST,
        ))

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    def test_recommendation_creation(self, sample_book):
        """Test creating a recommendation."""
        rec = Recommendation(
            book=sample_book,
            recommendation_type=RecommendationType.BY_AUTHOR,
            reason="You've enjoyed this author",
            score=0.8,
        )
        assert rec.book.title == "Test Book"
        assert rec.recommendation_type == RecommendationType.BY_AUTHOR
        assert rec.score == 0.8

    def test_recommendation_default_score(self, sample_book):
        """Test default score value."""
        rec = Recommendation(
            book=sample_book,
            recommendation_type=RecommendationType.BY_GENRE,
            reason="Based on your genres",
        )
        assert rec.score == 0.0


class TestRecommendationEngine:
    """Tests for RecommendationEngine class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def engine(self, db):
        """Create recommendation engine instance."""
        return RecommendationEngine(db)

    @pytest.fixture
    def populated_db(self, db):
        """Populate database with sample books."""
        today = date.today()

        # Completed books by favorite author
        for i in range(3):
            db.create_book(BookCreate(
                title=f"Completed Book {i+1}",
                author="Favorite Author",
                status=BookStatus.COMPLETED,
                rating=5,
                tags=["fantasy", "adventure"],
                date_finished=(today - timedelta(days=i*10)).isoformat(),
            ))

        # Unread books by favorite author
        db.create_book(BookCreate(
            title="Unread by Favorite",
            author="Favorite Author",
            status=BookStatus.WISHLIST,
            tags=["fantasy"],
        ))

        # Series books - some completed, some unread
        db.create_book(BookCreate(
            title="Series Book 1",
            author="Series Author",
            status=BookStatus.COMPLETED,
            series="Epic Series",
            series_index=1,
        ))
        db.create_book(BookCreate(
            title="Series Book 2",
            author="Series Author",
            status=BookStatus.WISHLIST,
            series="Epic Series",
            series_index=2,
        ))

        # Book marked as read next
        db.create_book(BookCreate(
            title="Read Next Book",
            author="Another Author",
            status=BookStatus.WISHLIST,
            read_next=True,
        ))

        # Short book for quick reads
        db.create_book(BookCreate(
            title="Short Story Collection",
            author="Short Author",
            status=BookStatus.WISHLIST,
            page_count=150,
        ))

        # Highly rated book
        db.create_book(BookCreate(
            title="Popular Book",
            author="Popular Author",
            status=BookStatus.WISHLIST,
            goodreads_avg_rating=4.5,
        ))

        # Old wishlist book
        db.create_book(BookCreate(
            title="Old Wishlist Book",
            author="Old Author",
            status=BookStatus.WISHLIST,
            date_added=(today - timedelta(days=365)).isoformat(),
        ))

        return db

    def test_get_recommendations(self, populated_db):
        """Test getting recommendations."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations(limit=10)

        assert len(recs) > 0
        # Read next should be highest priority
        assert recs[0].recommendation_type == RecommendationType.READ_NEXT

    def test_get_recommendations_empty_db(self, engine):
        """Test recommendations with empty database."""
        recs = engine.get_recommendations()
        assert len(recs) == 0

    def test_get_what_to_read_next(self, populated_db):
        """Test getting single best recommendation."""
        engine = RecommendationEngine(populated_db)
        rec = engine.get_what_to_read_next()

        assert rec is not None
        assert rec.book.title == "Read Next Book"

    def test_get_what_to_read_next_empty(self, engine):
        """Test what to read next with empty db."""
        rec = engine.get_what_to_read_next()
        assert rec is None

    def test_recommend_by_author(self, populated_db):
        """Test author-based recommendations."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations_by_type(RecommendationType.BY_AUTHOR)

        assert len(recs) > 0
        # Should recommend unread books by favorite author
        assert any(r.book.author == "Favorite Author" for r in recs)

    def test_recommend_by_series(self, populated_db):
        """Test series-based recommendations."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations_by_type(RecommendationType.BY_SERIES)

        assert len(recs) > 0
        # Should recommend next book in series
        series_rec = next((r for r in recs if r.book.series == "Epic Series"), None)
        assert series_rec is not None
        assert series_rec.book.series_index == 2

    def test_recommend_by_genre(self, populated_db):
        """Test genre-based recommendations."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations_by_type(RecommendationType.BY_GENRE)

        # May or may not have results depending on tag matching
        for rec in recs:
            assert rec.recommendation_type == RecommendationType.BY_GENRE

    def test_recommend_quick_reads(self, populated_db):
        """Test quick read recommendations."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations_by_type(RecommendationType.QUICK_READ)

        assert len(recs) > 0
        for rec in recs:
            assert rec.book.page_count <= 200

    def test_recommend_highly_rated(self, populated_db):
        """Test highly rated recommendations."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations_by_type(RecommendationType.HIGHLY_RATED)

        assert len(recs) > 0
        for rec in recs:
            assert rec.book.goodreads_avg_rating >= 4.0

    def test_recommend_long_awaited(self, populated_db):
        """Test long-awaited recommendations."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations_by_type(RecommendationType.LONG_AWAITED)

        assert len(recs) > 0
        # First should be oldest
        if len(recs) >= 2:
            first_added = recs[0].book.date_added
            second_added = recs[1].book.date_added
            if first_added and second_added:
                assert first_added <= second_added

    def test_recommend_read_next(self, populated_db):
        """Test read-next recommendations."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations_by_type(RecommendationType.READ_NEXT)

        assert len(recs) > 0
        for rec in recs:
            assert rec.book.read_next is True

    def test_recommendations_no_duplicates(self, populated_db):
        """Test that recommendations don't include duplicates."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations(limit=20)

        book_ids = [r.book.id for r in recs]
        assert len(book_ids) == len(set(book_ids))

    def test_recommendations_sorted_by_score(self, populated_db):
        """Test that recommendations are sorted by score."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations(limit=10)

        scores = [r.score for r in recs]
        assert scores == sorted(scores, reverse=True)

    def test_recommendations_limit(self, populated_db):
        """Test recommendation limit."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations(limit=3)

        assert len(recs) <= 3

    def test_recommendation_has_reason(self, populated_db):
        """Test that recommendations have reasons."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations()

        for rec in recs:
            assert rec.reason
            assert len(rec.reason) > 0

    def test_recommendations_only_unread(self, populated_db):
        """Test that recommendations only include unread books."""
        engine = RecommendationEngine(populated_db)
        recs = engine.get_recommendations()

        for rec in recs:
            assert rec.book.status in [
                BookStatus.WISHLIST.value,
                BookStatus.ON_HOLD.value,
            ]
