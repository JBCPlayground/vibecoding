"""Tests for CollectionManager."""

from uuid import UUID
import pytest

from vibecoding.booktracker.collections import (
    CollectionManager,
    CollectionType,
    SmartCollectionCriteria,
)
from vibecoding.booktracker.collections.schemas import (
    CollectionCreate,
    CollectionUpdate,
    CollectionBookAdd,
    CollectionBookUpdate,
    SmartCriteria,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus


class TestCollectionManager:
    """Tests for CollectionManager class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def manager(self, db):
        """Create manager instance."""
        return CollectionManager(db)

    @pytest.fixture
    def sample_books(self, db):
        """Create sample books for testing."""
        books = []
        book_data = [
            {
                "title": "The Great Gatsby",
                "author": "F. Scott Fitzgerald",
                "status": BookStatus.COMPLETED,
                "rating": 5,
                "tags": ["classics", "fiction"],
                "publication_year": 1925,
            },
            {
                "title": "1984",
                "author": "George Orwell",
                "status": BookStatus.READING,
                "rating": 4,
                "tags": ["dystopian", "classics"],
                "publication_year": 1949,
            },
            {
                "title": "Dune",
                "author": "Frank Herbert",
                "status": BookStatus.WISHLIST,
                "rating": None,
                "tags": ["sci-fi", "fantasy"],
                "publication_year": 1965,
            },
            {
                "title": "The Hobbit",
                "author": "J.R.R. Tolkien",
                "status": BookStatus.COMPLETED,
                "rating": 5,
                "tags": ["fantasy", "classics"],
                "publication_year": 1937,
            },
            {
                "title": "Foundation",
                "author": "Isaac Asimov",
                "status": BookStatus.COMPLETED,
                "rating": 4,
                "tags": ["sci-fi", "classics"],
                "publication_year": 1951,
            },
        ]

        for data in book_data:
            book = db.create_book(BookCreate(**data))
            books.append(book)

        return books

    def test_create_manual_collection(self, manager):
        """Test creating a manual collection."""
        data = CollectionCreate(
            name="My Favorites",
            description="Books I love",
            collection_type=CollectionType.MANUAL,
        )

        collection = manager.create_collection(data)

        assert collection.id is not None
        assert collection.name == "My Favorites"
        assert collection.description == "Books I love"
        assert collection.collection_type == "manual"
        assert not collection.is_smart

    def test_create_smart_collection(self, manager):
        """Test creating a smart collection."""
        criteria = SmartCollectionCriteria().rating_gte(4).to_dict()

        data = CollectionCreate(
            name="Highly Rated",
            description="4+ star books",
            collection_type=CollectionType.SMART,
            smart_criteria=criteria,
        )

        collection = manager.create_collection(data)

        assert collection.is_smart
        assert collection.get_smart_criteria() is not None

    def test_get_collection_by_id(self, manager):
        """Test getting collection by ID."""
        data = CollectionCreate(name="Test Collection")
        created = manager.create_collection(data)

        fetched = manager.get_collection(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "Test Collection"

    def test_get_collection_by_name(self, manager):
        """Test getting collection by name."""
        data = CollectionCreate(name="My Collection")
        manager.create_collection(data)

        fetched = manager.get_collection_by_name("My Collection")
        assert fetched is not None
        assert fetched.name == "My Collection"

        # Case insensitive
        fetched_lower = manager.get_collection_by_name("my collection")
        assert fetched_lower is not None

    def test_get_nonexistent_collection(self, manager):
        """Test getting a collection that doesn't exist."""
        fetched = manager.get_collection("nonexistent-id")
        assert fetched is None

        fetched_name = manager.get_collection_by_name("Nonexistent")
        assert fetched_name is None

    def test_list_collections(self, manager):
        """Test listing all collections."""
        manager.create_collection(CollectionCreate(name="Collection 1"))
        manager.create_collection(CollectionCreate(name="Collection 2"))
        manager.create_collection(
            CollectionCreate(name="Smart One", collection_type=CollectionType.SMART)
        )

        all_collections = manager.list_collections()
        assert len(all_collections) == 3

        # Filter by type
        manual = manager.list_collections(collection_type=CollectionType.MANUAL)
        assert len(manual) == 2

        smart = manager.list_collections(collection_type=CollectionType.SMART)
        assert len(smart) == 1

    def test_list_pinned_collections(self, manager):
        """Test listing only pinned collections."""
        manager.create_collection(CollectionCreate(name="Not Pinned"))
        manager.create_collection(CollectionCreate(name="Pinned", is_pinned=True))

        pinned = manager.list_collections(pinned_only=True)
        assert len(pinned) == 1
        assert pinned[0].name == "Pinned"

    def test_update_collection(self, manager):
        """Test updating a collection."""
        data = CollectionCreate(name="Original Name")
        collection = manager.create_collection(data)

        update_data = CollectionUpdate(
            name="Updated Name",
            description="New description",
            is_pinned=True,
        )

        updated = manager.update_collection(collection.id, update_data)

        assert updated.name == "Updated Name"
        assert updated.description == "New description"
        assert updated.is_pinned is True

    def test_delete_collection(self, manager):
        """Test deleting a collection."""
        data = CollectionCreate(name="To Delete")
        collection = manager.create_collection(data)

        result = manager.delete_collection(collection.id)
        assert result is True

        # Verify it's gone
        fetched = manager.get_collection(collection.id)
        assert fetched is None

    def test_delete_nonexistent_collection(self, manager):
        """Test deleting a collection that doesn't exist."""
        result = manager.delete_collection("nonexistent-id")
        assert result is False

    def test_add_book_to_collection(self, manager, sample_books):
        """Test adding a book to a collection."""
        data = CollectionCreate(name="Reading List")
        collection = manager.create_collection(data)

        book = sample_books[0]
        add_data = CollectionBookAdd(book_id=UUID(book.id))

        cb = manager.add_book_to_collection(collection.id, add_data)

        assert cb is not None
        assert cb.book_id == book.id
        assert cb.collection_id == collection.id

    def test_add_book_with_notes(self, manager, sample_books):
        """Test adding a book with notes."""
        data = CollectionCreate(name="Annotated")
        collection = manager.create_collection(data)

        book = sample_books[0]
        add_data = CollectionBookAdd(
            book_id=UUID(book.id),
            notes="Must read this summer!",
        )

        cb = manager.add_book_to_collection(collection.id, add_data)

        assert cb.notes == "Must read this summer!"

    def test_add_duplicate_book_fails(self, manager, sample_books):
        """Test that adding a book twice fails."""
        data = CollectionCreate(name="No Dupes")
        collection = manager.create_collection(data)

        book = sample_books[0]
        add_data = CollectionBookAdd(book_id=UUID(book.id))

        manager.add_book_to_collection(collection.id, add_data)

        # Adding again should fail
        with pytest.raises(ValueError, match="already in this collection"):
            manager.add_book_to_collection(collection.id, add_data)

    def test_cannot_add_to_smart_collection(self, manager, sample_books):
        """Test that manual adds to smart collections fail."""
        data = CollectionCreate(
            name="Smart",
            collection_type=CollectionType.SMART,
        )
        collection = manager.create_collection(data)

        book = sample_books[0]
        add_data = CollectionBookAdd(book_id=UUID(book.id))

        with pytest.raises(ValueError, match="smart collections"):
            manager.add_book_to_collection(collection.id, add_data)

    def test_remove_book_from_collection(self, manager, sample_books):
        """Test removing a book from a collection."""
        data = CollectionCreate(name="Remove Test")
        collection = manager.create_collection(data)

        book = sample_books[0]
        add_data = CollectionBookAdd(book_id=UUID(book.id))
        manager.add_book_to_collection(collection.id, add_data)

        result = manager.remove_book_from_collection(collection.id, book.id)
        assert result is True

        # Verify book count is 0
        count = manager.get_book_count(collection.id)
        assert count == 0

    def test_remove_nonexistent_book(self, manager):
        """Test removing a book that isn't in the collection."""
        data = CollectionCreate(name="Empty")
        collection = manager.create_collection(data)

        result = manager.remove_book_from_collection(collection.id, "nonexistent")
        assert result is False

    def test_update_book_in_collection(self, manager, sample_books):
        """Test updating a book's position/notes in a collection."""
        data = CollectionCreate(name="Update Test")
        collection = manager.create_collection(data)

        book = sample_books[0]
        add_data = CollectionBookAdd(book_id=UUID(book.id))
        manager.add_book_to_collection(collection.id, add_data)

        update_data = CollectionBookUpdate(position=10, notes="Updated notes")
        updated = manager.update_book_in_collection(collection.id, book.id, update_data)

        assert updated.position == 10
        assert updated.notes == "Updated notes"

    def test_get_manual_collection_books(self, manager, sample_books):
        """Test getting books from a manual collection."""
        data = CollectionCreate(name="My List")
        collection = manager.create_collection(data)

        # Add three books
        for book in sample_books[:3]:
            add_data = CollectionBookAdd(book_id=UUID(book.id))
            manager.add_book_to_collection(collection.id, add_data)

        books = manager.get_collection_books(collection.id)

        assert len(books) == 3

    def test_get_smart_collection_books_by_status(self, manager, sample_books):
        """Test smart collection filtering by status."""
        data = CollectionCreate(
            name="Completed Books",
            collection_type=CollectionType.SMART,
            smart_criteria=SmartCriteria(
                filters=[{"field": "status", "operator": "eq", "value": "completed", "negate": False}],
                match_mode="all",
            ),
        )
        collection = manager.create_collection(data)

        books = manager.get_collection_books(collection.id)

        # Should have 3 completed books
        assert len(books) == 3
        for book in books:
            assert book.status == "completed"

    def test_get_smart_collection_books_by_rating(self, manager, sample_books):
        """Test smart collection filtering by rating."""
        data = CollectionCreate(
            name="Top Rated",
            collection_type=CollectionType.SMART,
            smart_criteria=SmartCriteria(
                filters=[{"field": "rating", "operator": "gte", "value": 5, "negate": False}],
            ),
        )
        collection = manager.create_collection(data)

        books = manager.get_collection_books(collection.id)

        # Should have 2 five-star books
        assert len(books) == 2
        for book in books:
            assert book.rating >= 5

    def test_get_book_count(self, manager, sample_books):
        """Test getting book count for a collection."""
        data = CollectionCreate(name="Count Test")
        collection = manager.create_collection(data)

        assert manager.get_book_count(collection.id) == 0

        # Add books
        for book in sample_books[:2]:
            add_data = CollectionBookAdd(book_id=UUID(book.id))
            manager.add_book_to_collection(collection.id, add_data)

        assert manager.get_book_count(collection.id) == 2

    def test_reorder_books(self, manager, sample_books):
        """Test reordering books in a collection."""
        data = CollectionCreate(name="Reorder Test")
        collection = manager.create_collection(data)

        # Add books
        for book in sample_books[:3]:
            add_data = CollectionBookAdd(book_id=UUID(book.id))
            manager.add_book_to_collection(collection.id, add_data)

        # Reorder: put last book first
        new_order = [sample_books[2].id, sample_books[0].id, sample_books[1].id]
        result = manager.reorder_books(collection.id, new_order)

        assert result is True

        # Verify order
        books = manager.get_collection_books(collection.id)
        assert books[0].id == sample_books[2].id
        assert books[1].id == sample_books[0].id
        assert books[2].id == sample_books[1].id

    def test_get_collections_for_book(self, manager, sample_books):
        """Test getting all collections containing a book."""
        # Create collections and add the same book
        coll1 = manager.create_collection(CollectionCreate(name="Collection 1"))
        coll2 = manager.create_collection(CollectionCreate(name="Collection 2"))
        manager.create_collection(CollectionCreate(name="Collection 3"))  # No book added

        book = sample_books[0]
        add_data = CollectionBookAdd(book_id=UUID(book.id))
        manager.add_book_to_collection(coll1.id, add_data)
        manager.add_book_to_collection(coll2.id, add_data)

        collections = manager.get_collections_for_book(book.id)

        assert len(collections) == 2
        names = {c.name for c in collections}
        assert "Collection 1" in names
        assert "Collection 2" in names

    def test_create_default_collections(self, manager):
        """Test creating default smart collections."""
        created = manager.create_default_collections()

        assert len(created) >= 3

        names = {c.name for c in created}
        assert "Favorites" in names
        assert "Currently Reading" in names
        assert "To Read" in names

        # All should be smart and pinned
        for coll in created:
            assert coll.is_smart
            assert coll.is_pinned

    def test_create_default_collections_idempotent(self, manager):
        """Test that creating defaults twice doesn't duplicate."""
        created1 = manager.create_default_collections()
        created2 = manager.create_default_collections()

        # Second call should create nothing
        assert len(created2) == 0

        # Total should match first call
        all_collections = manager.list_collections()
        assert len(all_collections) == len(created1)

    def test_pagination(self, manager, sample_books):
        """Test pagination of collection books."""
        data = CollectionCreate(name="Pagination Test")
        collection = manager.create_collection(data)

        # Add all books
        for book in sample_books:
            add_data = CollectionBookAdd(book_id=UUID(book.id))
            manager.add_book_to_collection(collection.id, add_data)

        # Get first page
        page1 = manager.get_collection_books(collection.id, limit=2, offset=0)
        assert len(page1) == 2

        # Get second page
        page2 = manager.get_collection_books(collection.id, limit=2, offset=2)
        assert len(page2) == 2

        # Get remaining
        page3 = manager.get_collection_books(collection.id, limit=2, offset=4)
        assert len(page3) == 1

        # Verify no overlap
        all_ids = {b.id for b in page1} | {b.id for b in page2} | {b.id for b in page3}
        assert len(all_ids) == 5


class TestSmartCollectionCriteria:
    """Tests for SmartCollectionCriteria helper."""

    def test_basic_filter(self):
        """Test adding basic filters."""
        criteria = SmartCollectionCriteria()
        criteria.add_filter("status", "eq", "completed")

        result = criteria.to_dict()
        assert len(result["filters"]) == 1
        assert result["filters"][0]["field"] == "status"
        assert result["filters"][0]["operator"] == "eq"
        assert result["filters"][0]["value"] == "completed"

    def test_chaining(self):
        """Test method chaining."""
        criteria = (
            SmartCollectionCriteria()
            .status_is("completed")
            .rating_gte(4)
            .set_sort("date_finished", "desc")
            .set_limit(10)
        )

        result = criteria.to_dict()
        assert len(result["filters"]) == 2
        assert result["sort_by"] == "date_finished"
        assert result["sort_order"] == "desc"
        assert result["limit"] == 10

    def test_match_mode(self):
        """Test match mode setting."""
        criteria = (
            SmartCollectionCriteria()
            .status_is("reading")
            .author_contains("Tolkien")
            .set_match_mode("any")
        )

        result = criteria.to_dict()
        assert result["match_mode"] == "any"

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "filters": [
                {"field": "rating", "operator": "gte", "value": 4, "negate": False}
            ],
            "match_mode": "all",
            "sort_by": "title",
            "sort_order": "asc",
            "limit": 20,
        }

        criteria = SmartCollectionCriteria.from_dict(data)

        assert len(criteria.filters) == 1
        assert criteria.match_mode == "all"
        assert criteria.sort_by == "title"
        assert criteria.limit == 20

    def test_year_between(self):
        """Test year range filter."""
        criteria = SmartCollectionCriteria().year_between(1950, 1970)

        result = criteria.to_dict()
        assert result["filters"][0]["operator"] == "between"
        assert result["filters"][0]["value"] == [1950, 1970]

    def test_tag_filter(self):
        """Test tag filter."""
        criteria = SmartCollectionCriteria().tag_has("sci-fi")

        result = criteria.to_dict()
        assert result["filters"][0]["field"] == "tags"
        assert result["filters"][0]["operator"] == "contains"
        assert result["filters"][0]["value"] == "sci-fi"
