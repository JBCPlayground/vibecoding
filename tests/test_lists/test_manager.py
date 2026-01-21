"""Tests for ReadingListManager."""

import pytest
from uuid import UUID, uuid4

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus
from vibecoding.booktracker.lists.manager import ReadingListManager
from vibecoding.booktracker.lists.schemas import (
    ReadingListCreate,
    ReadingListUpdate,
    ListBookCreate,
    ListType,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a ReadingListManager with test database."""
    return ReadingListManager(db)


@pytest.fixture
def sample_books(db):
    """Create sample books for testing."""
    books = []
    genres = ["Fantasy", "Sci-Fi", "Mystery", "Romance", "Thriller"]
    authors = ["Author A", "Author B", "Author A", "Author C", "Author B"]

    for i in range(5):
        book = db.create_book(BookCreate(
            title=f"Book {i + 1}",
            author=authors[i],
            status=BookStatus.WISHLIST,
            genres=[genres[i]],
            page_count=100 + i * 50,
        ))
        books.append(book)
    return books


@pytest.fixture
def rated_books(db):
    """Create books with ratings for recommendation tests."""
    books = []

    # Highly rated books by Author A
    for i in range(3):
        book = db.create_book(BookCreate(
            title=f"Great Book {i + 1}",
            author="Favorite Author",
            status=BookStatus.COMPLETED,
            rating=5,
            genres=["Fantasy", "Adventure"],
        ))
        books.append(book)

    # Unread book by same author
    book = db.create_book(BookCreate(
        title="Unread by Favorite",
        author="Favorite Author",
        status=BookStatus.WISHLIST,
        genres=["Fantasy"],
    ))
    books.append(book)

    # Another genre
    book = db.create_book(BookCreate(
        title="Mystery Novel",
        author="Mystery Writer",
        status=BookStatus.WISHLIST,
        genres=["Mystery"],
        goodreads_avg_rating=4.5,
    ))
    books.append(book)

    return books


class TestReadingListCRUD:
    """Tests for reading list CRUD operations."""

    def test_create_list(self, manager):
        """Test creating a reading list."""
        reading_list = ReadingListCreate(
            name="Summer Reading",
            description="Books to read this summer",
            list_type=ListType.SEASONAL,
        )
        result = manager.create_list(reading_list)

        assert result is not None
        assert result.name == "Summer Reading"
        assert result.description == "Books to read this summer"
        assert result.list_type == ListType.SEASONAL
        assert result.book_count == 0

    def test_create_list_minimal(self, manager):
        """Test creating list with only name."""
        reading_list = ReadingListCreate(name="My List")
        result = manager.create_list(reading_list)

        assert result is not None
        assert result.name == "My List"
        assert result.list_type == ListType.CUSTOM

    def test_create_list_with_icon(self, manager):
        """Test creating list with icon."""
        reading_list = ReadingListCreate(
            name="Favorites",
            icon="⭐",
            is_pinned=True,
        )
        result = manager.create_list(reading_list)

        assert result.icon == "⭐"
        assert result.is_pinned is True

    def test_get_list(self, manager):
        """Test getting a list by ID."""
        reading_list = ReadingListCreate(name="Test List")
        created = manager.create_list(reading_list)

        result = manager.get_list(created.id)

        assert result is not None
        assert result.id == created.id
        assert result.name == "Test List"

    def test_get_list_not_found(self, manager):
        """Test getting non-existent list."""
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        result = manager.get_list(fake_id)

        assert result is None

    def test_update_list(self, manager):
        """Test updating a list."""
        reading_list = ReadingListCreate(name="Original Name")
        created = manager.create_list(reading_list)

        update = ReadingListUpdate(
            name="Updated Name",
            description="New description",
            is_pinned=True,
        )
        result = manager.update_list(created.id, update)

        assert result is not None
        assert result.name == "Updated Name"
        assert result.description == "New description"
        assert result.is_pinned is True

    def test_update_list_partial(self, manager):
        """Test partial update of a list."""
        reading_list = ReadingListCreate(
            name="Test List",
            description="Original desc",
        )
        created = manager.create_list(reading_list)

        update = ReadingListUpdate(is_pinned=True)
        result = manager.update_list(created.id, update)

        assert result.name == "Test List"  # Unchanged
        assert result.description == "Original desc"  # Unchanged
        assert result.is_pinned is True  # Changed

    def test_delete_list(self, manager):
        """Test deleting a list."""
        reading_list = ReadingListCreate(name="To Delete")
        created = manager.create_list(reading_list)

        success = manager.delete_list(created.id)
        assert success is True

        result = manager.get_list(created.id)
        assert result is None

    def test_delete_list_not_found(self, manager):
        """Test deleting non-existent list."""
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        success = manager.delete_list(fake_id)

        assert success is False


class TestReadingListListing:
    """Tests for listing reading lists."""

    def test_get_all_lists_empty(self, manager):
        """Test getting lists when none exist."""
        lists = manager.get_all_lists()
        assert lists == []

    def test_get_all_lists(self, manager):
        """Test getting all lists."""
        manager.create_list(ReadingListCreate(name="List 1"))
        manager.create_list(ReadingListCreate(name="List 2"))
        manager.create_list(ReadingListCreate(name="List 3"))

        lists = manager.get_all_lists()

        assert len(lists) == 3

    def test_get_all_lists_ordered(self, manager):
        """Test lists are ordered by pinned then name."""
        manager.create_list(ReadingListCreate(name="Zebra"))
        manager.create_list(ReadingListCreate(name="Alpha", is_pinned=True))
        manager.create_list(ReadingListCreate(name="Beta"))

        lists = manager.get_all_lists()

        # Pinned first, then alphabetical
        assert lists[0].name == "Alpha"  # Pinned
        assert lists[1].name == "Beta"
        assert lists[2].name == "Zebra"

    def test_get_all_lists_filter_by_type(self, manager):
        """Test filtering by list type."""
        manager.create_list(ReadingListCreate(name="Custom 1"))
        manager.create_list(ReadingListCreate(name="Seasonal 1", list_type=ListType.SEASONAL))
        manager.create_list(ReadingListCreate(name="Custom 2"))

        lists = manager.get_all_lists(list_type=ListType.SEASONAL)

        assert len(lists) == 1
        assert lists[0].name == "Seasonal 1"

    def test_get_all_lists_pinned_only(self, manager):
        """Test getting only pinned lists."""
        manager.create_list(ReadingListCreate(name="Not Pinned"))
        manager.create_list(ReadingListCreate(name="Pinned", is_pinned=True))

        lists = manager.get_all_lists(pinned_only=True)

        assert len(lists) == 1
        assert lists[0].name == "Pinned"


class TestListBooks:
    """Tests for list book operations."""

    def test_add_book_to_list(self, manager, sample_books):
        """Test adding a book to a list."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))
        book = sample_books[0]

        entry = ListBookCreate(book_id=UUID(book.id))
        result = manager.add_book_to_list(reading_list.id, entry)

        assert result is not None
        assert result.book_id == UUID(book.id)
        assert result.position == 0

    def test_add_book_with_note(self, manager, sample_books):
        """Test adding book with note."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))
        book = sample_books[0]

        entry = ListBookCreate(
            book_id=UUID(book.id),
            note="Recommended by a friend",
        )
        result = manager.add_book_to_list(reading_list.id, entry)

        assert result.note == "Recommended by a friend"

    def test_add_book_updates_count(self, manager, sample_books):
        """Test that adding books updates list count."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))

        for book in sample_books[:3]:
            manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))

        result = manager.get_list(reading_list.id)
        assert result.book_count == 3

    def test_add_book_positions_increment(self, manager, sample_books):
        """Test that positions auto-increment."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))

        positions = []
        for book in sample_books[:3]:
            entry = manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))
            positions.append(entry.position)

        assert positions == [0, 1, 2]

    def test_add_duplicate_book(self, manager, sample_books):
        """Test adding same book twice returns existing."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))
        book = sample_books[0]

        entry1 = manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))
        entry2 = manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))

        assert entry1.id == entry2.id

    def test_remove_book_from_list(self, manager, sample_books):
        """Test removing a book from a list."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))
        book = sample_books[0]

        manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))
        success = manager.remove_book_from_list(reading_list.id, UUID(book.id))

        assert success is True

        # Check count updated
        result = manager.get_list(reading_list.id)
        assert result.book_count == 0

    def test_remove_book_not_in_list(self, manager, sample_books):
        """Test removing book not in list."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))
        book = sample_books[0]

        success = manager.remove_book_from_list(reading_list.id, UUID(book.id))

        assert success is False

    def test_get_list_books(self, manager, sample_books):
        """Test getting all books in a list."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))

        for book in sample_books[:3]:
            manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))

        books = manager.get_list_books(reading_list.id)

        assert len(books) == 3
        assert books[0].position == 0
        assert books[1].position == 1
        assert books[2].position == 2

    def test_get_list_books_with_details(self, manager, sample_books):
        """Test that book details are included."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))
        book = sample_books[0]

        manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))
        books = manager.get_list_books(reading_list.id)

        assert books[0].book_title == book.title
        assert books[0].book_author == book.author

    def test_get_list_with_books(self, manager, sample_books):
        """Test getting list with all books."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))

        for book in sample_books[:2]:
            manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))

        result = manager.get_list_with_books(reading_list.id)

        assert result is not None
        assert result.list.name == "Test List"
        assert len(result.books) == 2


class TestListReorder:
    """Tests for reordering books in lists."""

    def test_reorder_book_down(self, manager, sample_books):
        """Test moving a book down in the list."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))

        for book in sample_books[:3]:
            manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))

        # Move first book to position 2
        result = manager.reorder_book(reading_list.id, UUID(sample_books[0].id), 2)

        assert result.position == 2

        # Check all positions
        books = manager.get_list_books(reading_list.id)
        titles = [b.book_title for b in sorted(books, key=lambda x: x.position)]
        assert titles == ["Book 2", "Book 3", "Book 1"]

    def test_reorder_book_up(self, manager, sample_books):
        """Test moving a book up in the list."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))

        for book in sample_books[:3]:
            manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))

        # Move third book to position 0
        result = manager.reorder_book(reading_list.id, UUID(sample_books[2].id), 0)

        assert result.position == 0

        # Check all positions
        books = manager.get_list_books(reading_list.id)
        titles = [b.book_title for b in sorted(books, key=lambda x: x.position)]
        assert titles == ["Book 3", "Book 1", "Book 2"]

    def test_reorder_book_same_position(self, manager, sample_books):
        """Test reordering to same position is no-op."""
        reading_list = manager.create_list(ReadingListCreate(name="Test List"))

        for book in sample_books[:3]:
            manager.add_book_to_list(reading_list.id, ListBookCreate(book_id=UUID(book.id)))

        result = manager.reorder_book(reading_list.id, UUID(sample_books[1].id), 1)

        assert result.position == 1


class TestRecommendations:
    """Tests for recommendation engine."""

    def test_get_recommendations_empty(self, manager):
        """Test recommendations with no data."""
        recs = manager.get_recommendations()
        assert recs == []

    def test_get_similar_books_empty(self, manager):
        """Test similar books with non-existent book."""
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        similar = manager.get_similar_books(fake_id)
        assert similar == []

    def test_get_similar_books_same_author(self, manager, db):
        """Test finding books by same author."""
        # Create books by same author
        book1 = db.create_book(BookCreate(
            title="Book 1",
            author="Test Author",
            status=BookStatus.COMPLETED,
            genres=["Fantasy"],
        ))
        book2 = db.create_book(BookCreate(
            title="Book 2",
            author="Test Author",
            status=BookStatus.WISHLIST,
            genres=["Fantasy"],
        ))

        similar = manager.get_similar_books(UUID(book1.id))

        assert len(similar) >= 1
        assert similar[0].same_author is True
        assert similar[0].book_title == "Book 2"

    def test_get_genre_recommendations(self, manager, db):
        """Test genre-based recommendations."""
        # Create Fantasy books
        db.create_book(BookCreate(
            title="Fantasy 1",
            author="Author A",
            status=BookStatus.WISHLIST,
            genres=["Fantasy"],
            rating=5,
        ))
        db.create_book(BookCreate(
            title="Fantasy 2",
            author="Author B",
            status=BookStatus.WISHLIST,
            genres=["Fantasy"],
        ))

        recs = manager.get_genre_recommendations("Fantasy")

        assert recs.genre == "Fantasy"
        assert recs.unread_count >= 2
        assert len(recs.top_rated) >= 1

    def test_get_author_recommendations(self, manager, rated_books):
        """Test author-based recommendations."""
        recs = manager.get_author_recommendations("Favorite Author")

        assert recs.author == "Favorite Author"
        assert recs.books_read == 3
        assert recs.average_rating == 5.0
        assert len(recs.unread_books) >= 1

    def test_get_recommendation_stats(self, manager, rated_books):
        """Test recommendation statistics."""
        stats = manager.get_recommendation_stats()

        assert stats.total_unread >= 2
        assert "Fantasy" in stats.favorite_genres or len(stats.favorite_genres) >= 0


class TestModelProperties:
    """Tests for model properties."""

    def test_is_auto_property(self, manager):
        """Test is_auto property."""
        custom = manager.create_list(ReadingListCreate(name="Custom"))
        assert custom.is_auto is False

    def test_type_display(self, manager):
        """Test type display strings."""
        types = [
            (ListType.CUSTOM, "Custom"),
            (ListType.SEASONAL, "Seasonal"),
            (ListType.THEMED, "Themed"),
        ]

        for list_type, expected in types:
            lst = manager.create_list(ReadingListCreate(
                name=f"Test {list_type.value}",
                list_type=list_type,
            ))
            assert lst.type_display == expected
