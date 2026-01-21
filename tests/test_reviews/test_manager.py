"""Tests for ReviewManager."""

import pytest
from datetime import date
from uuid import UUID

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.db.models import Book
from vibecoding.booktracker.reviews.manager import ReviewManager
from vibecoding.booktracker.reviews.schemas import (
    ReviewCreate,
    ReviewUpdate,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a ReviewManager with test database."""
    return ReviewManager(db)


@pytest.fixture
def sample_book(db):
    """Create a sample book for testing."""
    with db.get_session() as session:
        book = Book(
            title="Test Book",
            author="Test Author",
            status="read",
        )
        session.add(book)
        session.commit()
        session.refresh(book)
        book_id = book.id
    return book_id


@pytest.fixture
def sample_books(db):
    """Create multiple sample books for testing."""
    book_ids = []
    with db.get_session() as session:
        for i in range(10):
            book = Book(
                title=f"Test Book {i+1}",
                author=f"Author {i+1}",
                status="read",
            )
            session.add(book)
            session.commit()
            session.refresh(book)
            book_ids.append(book.id)
    return book_ids


@pytest.fixture
def sample_review(manager, sample_book):
    """Create a sample review for testing."""
    data = ReviewCreate(
        book_id=UUID(sample_book),
        rating=4.5,
        title="Great Book!",
        content="This was a fantastic read.",
        is_favorite=True,
        contains_spoilers=False,
        would_recommend=True,
        would_reread=True,
        tags=["fiction", "must-read"],
        review_date=date.today(),
    )
    return manager.create_review(data)


class TestReviewCRUD:
    """Tests for review CRUD operations."""

    def test_create_review(self, manager, sample_book):
        """Test creating a review."""
        data = ReviewCreate(
            book_id=UUID(sample_book),
            rating=4.0,
            title="Good Read",
            content="Enjoyed this book a lot.",
            is_favorite=False,
            contains_spoilers=True,
            would_recommend=True,
            tags=["mystery", "thriller"],
            review_date=date.today(),
        )
        review = manager.create_review(data)

        assert review.id is not None
        assert review.book_id == sample_book
        assert review.rating == 4.0
        assert review.title == "Good Read"
        assert review.content == "Enjoyed this book a lot."
        assert review.is_favorite is False
        assert review.contains_spoilers is True
        assert review.would_recommend is True
        assert "mystery" in review.tag_list
        assert "thriller" in review.tag_list

    def test_create_review_minimal(self, manager, sample_book):
        """Test creating a review with minimal info."""
        data = ReviewCreate(
            book_id=UUID(sample_book),
            rating=3.5,
        )
        review = manager.create_review(data)

        assert review.rating == 3.5
        assert review.title is None
        assert review.content is None

    def test_create_review_book_not_found(self, manager):
        """Test creating review for non-existent book."""
        data = ReviewCreate(
            book_id=UUID("00000000-0000-0000-0000-000000000000"),
            rating=4.0,
        )
        with pytest.raises(ValueError, match="Book not found"):
            manager.create_review(data)

    def test_create_review_already_exists(self, manager, sample_book, sample_review):
        """Test cannot create duplicate review for same book."""
        data = ReviewCreate(
            book_id=UUID(sample_book),
            rating=3.0,
        )
        with pytest.raises(ValueError, match="Review already exists"):
            manager.create_review(data)

    def test_get_review(self, manager, sample_review):
        """Test getting a review by ID."""
        review = manager.get_review(sample_review.id)

        assert review is not None
        assert review.id == sample_review.id
        assert review.rating == sample_review.rating

    def test_get_review_not_found(self, manager):
        """Test getting a non-existent review."""
        review = manager.get_review("non-existent-id")
        assert review is None

    def test_get_review_by_book(self, manager, sample_book, sample_review):
        """Test getting review by book ID."""
        review = manager.get_review_by_book(sample_book)

        assert review is not None
        assert review.id == sample_review.id

    def test_get_review_by_book_not_found(self, manager, sample_book):
        """Test getting review for book with no review."""
        review = manager.get_review_by_book(sample_book)
        assert review is None

    def test_list_reviews(self, manager, sample_books):
        """Test listing all reviews."""
        # Create reviews for multiple books
        for i, book_id in enumerate(sample_books[:5]):
            manager.create_review(ReviewCreate(
                book_id=UUID(book_id),
                rating=float(i + 1),
                review_date=date.today(),
            ))

        reviews = manager.list_reviews()
        assert len(reviews) == 5

    def test_list_reviews_filter_by_rating(self, manager, sample_books):
        """Test filtering reviews by rating."""
        for i, book_id in enumerate(sample_books[:5]):
            manager.create_review(ReviewCreate(
                book_id=UUID(book_id),
                rating=float(i + 1),
            ))

        # Filter by min rating
        high_rated = manager.list_reviews(min_rating=4.0)
        assert len(high_rated) == 2  # 4 and 5

        # Filter by max rating
        low_rated = manager.list_reviews(max_rating=2.0)
        assert len(low_rated) == 2  # 1 and 2

        # Filter by range
        mid_rated = manager.list_reviews(min_rating=2.0, max_rating=4.0)
        assert len(mid_rated) == 3  # 2, 3, 4

    def test_list_reviews_favorites_only(self, manager, sample_books):
        """Test filtering for favorites only."""
        # Create some favorites and non-favorites
        for i, book_id in enumerate(sample_books[:5]):
            manager.create_review(ReviewCreate(
                book_id=UUID(book_id),
                rating=4.0,
                is_favorite=(i % 2 == 0),
            ))

        favorites = manager.list_reviews(favorites_only=True)
        assert len(favorites) == 3  # 0, 2, 4 are favorites

    def test_list_reviews_filter_by_tag(self, manager, sample_books):
        """Test filtering reviews by tag."""
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_books[0]),
            rating=4.0,
            tags=["fiction", "favorite"],
        ))
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_books[1]),
            rating=3.5,
            tags=["non-fiction"],
        ))

        fiction_reviews = manager.list_reviews(tag="fiction")
        assert len(fiction_reviews) == 1

    def test_update_review(self, manager, sample_review):
        """Test updating a review."""
        data = ReviewUpdate(
            rating=5.0,
            title="Updated Title",
            is_favorite=False,
        )
        updated = manager.update_review(sample_review.id, data)

        assert updated is not None
        assert updated.rating == 5.0
        assert updated.title == "Updated Title"
        assert updated.is_favorite is False
        # Unchanged fields
        assert updated.content == sample_review.content

    def test_update_review_tags(self, manager, sample_review):
        """Test updating review tags."""
        data = ReviewUpdate(tags=["new-tag", "another-tag"])
        updated = manager.update_review(sample_review.id, data)

        assert "new-tag" in updated.tag_list
        assert "another-tag" in updated.tag_list

    def test_update_review_not_found(self, manager):
        """Test updating non-existent review."""
        data = ReviewUpdate(rating=5.0)
        result = manager.update_review("non-existent", data)
        assert result is None

    def test_delete_review(self, manager, sample_review):
        """Test deleting a review."""
        result = manager.delete_review(sample_review.id)
        assert result is True

        # Verify deletion
        review = manager.get_review(sample_review.id)
        assert review is None

    def test_delete_review_not_found(self, manager):
        """Test deleting non-existent review."""
        result = manager.delete_review("non-existent")
        assert result is False


class TestQuickRating:
    """Tests for quick rating functionality."""

    def test_quick_rate_new(self, manager, sample_book):
        """Test quick rating a new book."""
        review = manager.quick_rate(sample_book, 4.5)

        assert review is not None
        assert review.rating == 4.5
        assert review.book_id == sample_book

    def test_quick_rate_existing(self, manager, sample_book, sample_review):
        """Test quick rating updates existing review."""
        review = manager.quick_rate(sample_book, 3.0)

        assert review.id == sample_review.id
        assert review.rating == 3.0

    def test_quick_rate_with_favorite(self, manager, sample_book):
        """Test quick rating with favorite flag."""
        review = manager.quick_rate(sample_book, 5.0, is_favorite=True)

        assert review.rating == 5.0
        assert review.is_favorite is True

    def test_toggle_favorite(self, manager, sample_book, sample_review):
        """Test toggling favorite status."""
        # Initial state is favorite
        assert sample_review.is_favorite is True

        # Toggle off
        updated = manager.toggle_favorite(sample_book)
        assert updated.is_favorite is False

        # Toggle on
        updated = manager.toggle_favorite(sample_book)
        assert updated.is_favorite is True

    def test_toggle_favorite_no_review(self, manager, sample_book):
        """Test toggle favorite with no review."""
        result = manager.toggle_favorite(sample_book)
        assert result is None


class TestReviewProperties:
    """Tests for review model properties."""

    def test_tag_list(self, manager, sample_book):
        """Test tag_list property."""
        review = manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=4.0,
            tags=["one", "two", "three"],
        ))

        assert review.tag_list == ["one", "two", "three"]

    def test_tag_list_empty(self, manager, sample_book):
        """Test tag_list with no tags."""
        review = manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=4.0,
        ))

        assert review.tag_list == []

    def test_star_display(self, manager, sample_book):
        """Test star_display property."""
        review = manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=3.5,
        ))

        assert "★★★" in review.star_display
        assert "½" in review.star_display

    def test_star_display_full(self, manager, sample_book):
        """Test star_display with full rating."""
        review = manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=5.0,
        ))

        assert review.star_display == "★★★★★"

    def test_star_display_no_rating(self, manager, sample_book):
        """Test star_display with no rating."""
        review = manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
        ))

        assert review.star_display == "No rating"

    def test_has_detailed_ratings(self, manager, sample_book):
        """Test has_detailed_ratings property."""
        review = manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=4.0,
            plot_rating=4.5,
            characters_rating=4.0,
        ))

        assert review.has_detailed_ratings is True

    def test_has_detailed_ratings_none(self, manager, sample_book):
        """Test has_detailed_ratings with no detailed ratings."""
        review = manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=4.0,
        ))

        assert review.has_detailed_ratings is False

    def test_average_detailed_rating(self, manager, sample_book):
        """Test average_detailed_rating property."""
        review = manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=4.0,
            plot_rating=4.0,
            characters_rating=5.0,
            writing_rating=3.0,
        ))

        assert review.average_detailed_rating == 4.0  # (4+5+3)/3


class TestStatistics:
    """Tests for review statistics."""

    def test_get_stats_empty(self, manager):
        """Test stats with no reviews."""
        stats = manager.get_stats()

        assert stats.total_reviews == 0
        assert stats.total_rated == 0
        assert stats.average_rating is None
        assert stats.total_favorites == 0

    def test_get_stats_with_reviews(self, manager, sample_books):
        """Test stats with various reviews."""
        # Create reviews with different ratings
        ratings = [1.0, 2.0, 3.0, 4.0, 5.0]
        for i, book_id in enumerate(sample_books[:5]):
            manager.create_review(ReviewCreate(
                book_id=UUID(book_id),
                rating=ratings[i],
                is_favorite=(i >= 3),  # 4 and 5 star are favorites
                would_recommend=(i >= 2),  # 3+ star recommend
            ))

        stats = manager.get_stats()

        assert stats.total_reviews == 5
        assert stats.total_rated == 5
        assert stats.average_rating == 3.0
        assert stats.total_favorites == 2
        assert stats.would_recommend_count == 3

    def test_rating_distribution(self, manager, sample_books):
        """Test rating distribution calculation."""
        # Create reviews with known ratings
        # Distribution ranges: 1-star (0.5-1.49), 2-star (1.5-2.49), 3-star (2.5-3.49), 4-star (3.5-4.49), 5-star (4.5+)
        ratings = [1.0, 2.0, 2.5, 3.0, 4.0, 4.5, 5.0]
        for i, rating in enumerate(ratings):
            manager.create_review(ReviewCreate(
                book_id=UUID(sample_books[i]),
                rating=rating,
            ))

        stats = manager.get_stats()

        assert stats.distribution.one_star == 1  # 1.0
        assert stats.distribution.two_star == 1  # 2.0
        assert stats.distribution.three_star == 2  # 2.5, 3.0
        assert stats.distribution.four_star == 1  # 4.0
        assert stats.distribution.five_star == 2  # 4.5, 5.0

    def test_get_top_rated(self, manager, sample_books):
        """Test getting top rated books."""
        # Create reviews with varying ratings
        for i, book_id in enumerate(sample_books[:5]):
            manager.create_review(ReviewCreate(
                book_id=UUID(book_id),
                rating=float(i + 1),
            ))

        top = manager.get_top_rated(3)

        assert len(top) == 3
        assert top[0].rating == 5.0
        assert top[1].rating == 4.0
        assert top[2].rating == 3.0

    def test_get_favorites(self, manager, sample_books):
        """Test getting favorite books."""
        # Create some favorites
        for i, book_id in enumerate(sample_books[:4]):
            manager.create_review(ReviewCreate(
                book_id=UUID(book_id),
                rating=4.0,
                is_favorite=(i < 2),
            ))

        favorites = manager.get_favorites()
        assert len(favorites) == 2

    def test_get_recent_reviews(self, manager, sample_books):
        """Test getting recent reviews."""
        for book_id in sample_books[:5]:
            manager.create_review(ReviewCreate(
                book_id=UUID(book_id),
                rating=4.0,
            ))

        recent = manager.get_recent_reviews(3)
        assert len(recent) == 3


class TestSearchAndQuery:
    """Tests for search and query functionality."""

    def test_search_reviews_by_title(self, manager, sample_book):
        """Test searching reviews by title."""
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=4.0,
            title="Amazing Science Fiction",
        ))

        results = manager.search_reviews("science fiction")
        assert len(results) == 1

    def test_search_reviews_by_content(self, manager, sample_book):
        """Test searching reviews by content."""
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=4.0,
            content="The protagonist's journey was incredible.",
        ))

        results = manager.search_reviews("protagonist")
        assert len(results) == 1

    def test_search_reviews_by_tag(self, manager, sample_book):
        """Test searching reviews by tag."""
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=4.0,
            tags=["dystopian", "adventure"],
        ))

        results = manager.search_reviews("dystopian")
        assert len(results) == 1

    def test_search_reviews_no_results(self, manager, sample_book):
        """Test search with no matching results."""
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=4.0,
            title="A Mystery Novel",
        ))

        results = manager.search_reviews("romance")
        assert len(results) == 0

    def test_get_reviews_with_tag(self, manager, sample_books):
        """Test getting reviews with specific tag."""
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_books[0]),
            rating=4.0,
            tags=["horror", "supernatural"],
        ))
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_books[1]),
            rating=3.5,
            tags=["horror", "classic"],
        ))
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_books[2]),
            rating=4.5,
            tags=["romance"],
        ))

        horror_reviews = manager.get_reviews_with_tag("horror")
        assert len(horror_reviews) == 2

    def test_get_all_tags(self, manager, sample_books):
        """Test getting all tags with counts."""
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_books[0]),
            rating=4.0,
            tags=["fiction", "favorite"],
        ))
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_books[1]),
            rating=3.5,
            tags=["fiction", "classic"],
        ))

        tags = manager.get_all_tags()

        # Convert to dict for easier testing
        tag_dict = dict(tags)
        assert tag_dict["fiction"] == 2
        assert tag_dict["favorite"] == 1
        assert tag_dict["classic"] == 1

    def test_get_reviews_by_rating(self, manager, sample_books):
        """Test getting reviews by specific rating."""
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_books[0]),
            rating=4.0,
        ))
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_books[1]),
            rating=4.5,
        ))
        manager.create_review(ReviewCreate(
            book_id=UUID(sample_books[2]),
            rating=3.0,
        ))

        four_star = manager.get_reviews_by_rating(4.0)
        assert len(four_star) == 1


class TestRatingValidation:
    """Tests for rating validation."""

    def test_rating_rounded_to_half(self, manager, sample_book):
        """Test ratings are rounded to nearest 0.5."""
        review = manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=3.7,  # Should round to 3.5
        ))

        assert review.rating == 3.5

    def test_rating_minimum_rejects_below(self, manager, sample_book):
        """Test rating below minimum is rejected."""
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            ReviewCreate(
                book_id=UUID(sample_book),
                rating=0.3,  # Below 0.5 minimum
            )

    def test_rating_maximum_rejects_above(self, manager, sample_book):
        """Test rating above maximum is rejected."""
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            ReviewCreate(
                book_id=UUID(sample_book),
                rating=5.5,  # Above 5.0 maximum
            )

    def test_rating_at_boundaries(self, manager, sample_book):
        """Test ratings at boundary values."""
        # Test minimum
        review_min = manager.create_review(ReviewCreate(
            book_id=UUID(sample_book),
            rating=0.5,
        ))
        assert review_min.rating == 0.5
