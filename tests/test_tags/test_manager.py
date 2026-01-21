"""Tests for TagManager."""

import json
import pytest
from uuid import UUID, uuid4

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus
from vibecoding.booktracker.tags.manager import TagManager
from vibecoding.booktracker.tags.schemas import (
    TagColor,
    FieldType,
    TagCreate,
    TagUpdate,
    CustomFieldCreate,
    CustomFieldUpdate,
    SelectOption,
    BulkTagOperation,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a TagManager with test database."""
    return TagManager(db)


@pytest.fixture
def sample_books(db):
    """Create sample books for testing."""
    books = []
    genres_list = [
        ["Fantasy", "Adventure"],
        ["Mystery", "Thriller"],
        ["Sci-Fi"],
        ["Romance"],
        ["Fantasy", "Romance"],
    ]
    for i in range(5):
        book = db.create_book(BookCreate(
            title=f"Book {i + 1}",
            author=f"Author {chr(65 + i % 3)}",  # A, B, C
            status=BookStatus.COMPLETED if i < 3 else BookStatus.WISHLIST,
            rating=3 + (i % 3) if i < 3 else None,
            genres=genres_list[i],
            page_count=200 + i * 50,
        ))
        books.append(book)
    return books


@pytest.fixture
def sample_tags(manager):
    """Create sample tags for testing."""
    tags = []
    colors = [TagColor.RED, TagColor.BLUE, TagColor.GREEN, TagColor.PURPLE, TagColor.ORANGE]

    for i in range(5):
        tag = manager.create_tag(TagCreate(
            name=f"Tag {i + 1}",
            color=colors[i],
            description=f"Description for tag {i + 1}",
        ))
        tags.append(tag)

    return tags


class TestTagCRUD:
    """Tests for tag CRUD operations."""

    def test_create_tag_basic(self, manager):
        """Test creating a basic tag."""
        tag = manager.create_tag(TagCreate(name="Fiction"))

        assert tag is not None
        assert tag.name == "Fiction"
        assert tag.color == TagColor.GRAY

    def test_create_tag_with_color(self, manager):
        """Test creating a tag with color."""
        tag = manager.create_tag(TagCreate(
            name="Fantasy",
            color=TagColor.PURPLE,
        ))

        assert tag.color == TagColor.PURPLE

    def test_create_tag_with_icon(self, manager):
        """Test creating a tag with icon."""
        tag = manager.create_tag(TagCreate(
            name="Favorites",
            icon="⭐",
        ))

        assert tag.icon == "⭐"

    def test_create_duplicate_tag_returns_existing(self, manager):
        """Test that creating duplicate tag returns existing."""
        tag1 = manager.create_tag(TagCreate(name="Fiction"))
        tag2 = manager.create_tag(TagCreate(name="Fiction"))

        assert tag1.id == tag2.id

    def test_create_tag_case_insensitive_duplicate(self, manager):
        """Test duplicate detection is case insensitive."""
        tag1 = manager.create_tag(TagCreate(name="Fiction"))
        tag2 = manager.create_tag(TagCreate(name="FICTION"))

        assert tag1.id == tag2.id

    def test_get_tag(self, manager, sample_tags):
        """Test getting a tag by ID."""
        tag = manager.get_tag(sample_tags[0].id)

        assert tag is not None
        assert tag.id == sample_tags[0].id

    def test_get_tag_not_found(self, manager):
        """Test getting non-existent tag."""
        tag = manager.get_tag(uuid4())
        assert tag is None

    def test_get_tag_by_name(self, manager, sample_tags):
        """Test getting a tag by name."""
        tag = manager.get_tag_by_name("Tag 1")
        assert tag is not None
        assert tag.name == "Tag 1"

    def test_get_tag_by_name_case_insensitive(self, manager, sample_tags):
        """Test getting tag by name is case insensitive."""
        tag = manager.get_tag_by_name("TAG 1")
        assert tag is not None
        assert tag.name == "Tag 1"

    def test_get_all_tags(self, manager, sample_tags):
        """Test getting all tags."""
        tags = manager.get_all_tags(include_children=True)
        assert len(tags) == 5

    def test_update_tag(self, manager, sample_tags):
        """Test updating a tag."""
        tag = sample_tags[0]
        updated = manager.update_tag(
            tag.id,
            TagUpdate(name="Updated Name", color=TagColor.TEAL)
        )

        assert updated.name == "Updated Name"
        assert updated.color == TagColor.TEAL

    def test_delete_tag(self, manager, sample_tags):
        """Test deleting a tag."""
        tag = sample_tags[0]
        result = manager.delete_tag(tag.id)

        assert result is True
        assert manager.get_tag(tag.id) is None


class TestTagHierarchy:
    """Tests for tag hierarchy."""

    def test_create_child_tag(self, manager):
        """Test creating a child tag."""
        parent = manager.create_tag(TagCreate(name="Fiction"))
        child = manager.create_tag(TagCreate(
            name="Fantasy",
            parent_id=parent.id,
        ))

        assert child.parent_id == parent.id

    def test_get_tags_hierarchy(self, manager):
        """Test getting tags in hierarchy."""
        parent = manager.create_tag(TagCreate(name="Fiction"))
        manager.create_tag(TagCreate(name="Fantasy", parent_id=parent.id))
        manager.create_tag(TagCreate(name="Sci-Fi", parent_id=parent.id))

        hierarchy = manager.get_tags_hierarchy()

        assert len(hierarchy) == 1  # Only root
        assert hierarchy[0].name == "Fiction"
        assert len(hierarchy[0].children) == 2

    def test_hierarchy_full_path(self, manager):
        """Test full path in hierarchy."""
        parent = manager.create_tag(TagCreate(name="Fiction"))
        child = manager.create_tag(TagCreate(name="Fantasy", parent_id=parent.id))
        grandchild = manager.create_tag(TagCreate(name="Epic Fantasy", parent_id=child.id))

        hierarchy = manager.get_tags_hierarchy()
        epic = hierarchy[0].children[0].children[0]

        assert epic.full_path == "Fiction > Fantasy > Epic Fantasy"


class TestBookTagging:
    """Tests for book tagging operations."""

    def test_tag_book(self, manager, sample_books, sample_tags):
        """Test tagging a book."""
        book = sample_books[0]
        tag = sample_tags[0]

        result = manager.tag_book(UUID(book.id), tag.id)

        assert result is not None
        assert result.tag_name == tag.name

    def test_tag_book_duplicate(self, manager, sample_books, sample_tags):
        """Test tagging same book twice returns existing."""
        book = sample_books[0]
        tag = sample_tags[0]

        result1 = manager.tag_book(UUID(book.id), tag.id)
        result2 = manager.tag_book(UUID(book.id), tag.id)

        assert result1.tag_id == result2.tag_id

    def test_untag_book(self, manager, sample_books, sample_tags):
        """Test removing a tag from a book."""
        book = sample_books[0]
        tag = sample_tags[0]

        manager.tag_book(UUID(book.id), tag.id)
        result = manager.untag_book(UUID(book.id), tag.id)

        assert result is True

        book_tags = manager.get_book_tags(UUID(book.id))
        assert len(book_tags) == 0

    def test_get_book_tags(self, manager, sample_books, sample_tags):
        """Test getting all tags for a book."""
        book = sample_books[0]

        for tag in sample_tags[:3]:
            manager.tag_book(UUID(book.id), tag.id)

        book_tags = manager.get_book_tags(UUID(book.id))
        assert len(book_tags) == 3

    def test_get_books_by_tag(self, manager, sample_books, sample_tags):
        """Test getting all books with a tag."""
        tag = sample_tags[0]

        for book in sample_books[:3]:
            manager.tag_book(UUID(book.id), tag.id)

        books = manager.get_books_by_tag(tag.id)
        assert len(books) == 3

    def test_get_books_by_tag_include_children(self, manager, sample_books):
        """Test getting books with tag including child tags."""
        parent = manager.create_tag(TagCreate(name="Fiction"))
        child = manager.create_tag(TagCreate(name="Fantasy", parent_id=parent.id))

        manager.tag_book(UUID(sample_books[0].id), parent.id)
        manager.tag_book(UUID(sample_books[1].id), child.id)

        books = manager.get_books_by_tag(parent.id, include_children=True)
        assert len(books) == 2


class TestBulkOperations:
    """Tests for bulk tag operations."""

    def test_bulk_add_tags(self, manager, sample_books, sample_tags):
        """Test bulk adding tags."""
        book_ids = [UUID(b.id) for b in sample_books[:3]]
        tag_ids = [sample_tags[0].id, sample_tags[1].id]

        result = manager.bulk_tag_books(BulkTagOperation(
            book_ids=book_ids,
            tag_ids=tag_ids,
            operation="add",
        ))

        assert result.books_affected == 3
        assert result.tags_applied == 6  # 3 books * 2 tags

    def test_bulk_remove_tags(self, manager, sample_books, sample_tags):
        """Test bulk removing tags."""
        book_ids = [UUID(b.id) for b in sample_books[:3]]
        tag_ids = [sample_tags[0].id]

        # First add tags
        for book_id in book_ids:
            manager.tag_book(book_id, sample_tags[0].id)

        # Then remove
        result = manager.bulk_tag_books(BulkTagOperation(
            book_ids=book_ids,
            tag_ids=tag_ids,
            operation="remove",
        ))

        assert result.books_affected == 3
        assert result.tags_removed == 3


class TestCustomFieldCRUD:
    """Tests for custom field CRUD operations."""

    def test_create_text_field(self, manager):
        """Test creating a text field."""
        field = manager.create_field(CustomFieldCreate(
            name="Reading Location",
            field_type=FieldType.TEXT,
        ))

        assert field is not None
        assert field.name == "Reading Location"
        assert field.field_type == FieldType.TEXT

    def test_create_number_field(self, manager):
        """Test creating a number field."""
        field = manager.create_field(CustomFieldCreate(
            name="Re-read Count",
            field_type=FieldType.NUMBER,
            min_value=0,
            max_value=100,
        ))

        assert field.field_type == FieldType.NUMBER
        assert field.min_value == 0
        assert field.max_value == 100

    def test_create_select_field(self, manager):
        """Test creating a select field."""
        field = manager.create_field(CustomFieldCreate(
            name="Format",
            field_type=FieldType.SELECT,
            options=[
                SelectOption(value="hardcover", label="Hardcover"),
                SelectOption(value="paperback", label="Paperback"),
                SelectOption(value="ebook", label="E-book"),
            ],
        ))

        assert field.field_type == FieldType.SELECT
        assert len(field.options) == 3

    def test_create_rating_field(self, manager):
        """Test creating a rating field."""
        field = manager.create_field(CustomFieldCreate(
            name="Writing Quality",
            field_type=FieldType.RATING,
            min_value=1,
            max_value=5,
        ))

        assert field.field_type == FieldType.RATING

    def test_get_field(self, manager):
        """Test getting a field."""
        created = manager.create_field(CustomFieldCreate(
            name="Test Field",
            field_type=FieldType.TEXT,
        ))

        field = manager.get_field(created.id)
        assert field is not None
        assert field.id == created.id

    def test_get_all_fields(self, manager):
        """Test getting all fields."""
        manager.create_field(CustomFieldCreate(name="Field 1", field_type=FieldType.TEXT))
        manager.create_field(CustomFieldCreate(name="Field 2", field_type=FieldType.NUMBER))

        fields = manager.get_all_fields()
        assert len(fields) == 2

    def test_update_field(self, manager):
        """Test updating a field."""
        field = manager.create_field(CustomFieldCreate(
            name="Original",
            field_type=FieldType.TEXT,
        ))

        updated = manager.update_field(
            field.id,
            CustomFieldUpdate(name="Updated", description="New description")
        )

        assert updated.name == "Updated"
        assert updated.description == "New description"

    def test_delete_field(self, manager):
        """Test deleting a field."""
        field = manager.create_field(CustomFieldCreate(
            name="To Delete",
            field_type=FieldType.TEXT,
        ))

        result = manager.delete_field(field.id)
        assert result is True
        assert manager.get_field(field.id) is None


class TestFieldValues:
    """Tests for custom field values."""

    def test_set_text_field_value(self, manager, sample_books):
        """Test setting a text field value."""
        field = manager.create_field(CustomFieldCreate(
            name="Notes",
            field_type=FieldType.TEXT,
        ))

        result = manager.set_field_value(
            UUID(sample_books[0].id),
            field.id,
            "Great book!"
        )

        assert result is not None
        assert result.value == "Great book!"

    def test_set_number_field_value(self, manager, sample_books):
        """Test setting a number field value."""
        field = manager.create_field(CustomFieldCreate(
            name="Re-read Count",
            field_type=FieldType.NUMBER,
            min_value=0,
        ))

        result = manager.set_field_value(
            UUID(sample_books[0].id),
            field.id,
            "3"
        )

        assert result is not None
        assert result.value == "3"

    def test_set_boolean_field_value(self, manager, sample_books):
        """Test setting a boolean field value."""
        field = manager.create_field(CustomFieldCreate(
            name="Favorite",
            field_type=FieldType.BOOLEAN,
        ))

        result = manager.set_field_value(
            UUID(sample_books[0].id),
            field.id,
            "true"
        )

        assert result is not None
        assert result.display_value == "Yes"

    def test_set_date_field_value(self, manager, sample_books):
        """Test setting a date field value."""
        field = manager.create_field(CustomFieldCreate(
            name="Purchase Date",
            field_type=FieldType.DATE,
        ))

        result = manager.set_field_value(
            UUID(sample_books[0].id),
            field.id,
            "2024-06-15"
        )

        assert result is not None
        assert result.value == "2024-06-15"

    def test_set_select_field_value(self, manager, sample_books):
        """Test setting a select field value."""
        field = manager.create_field(CustomFieldCreate(
            name="Format",
            field_type=FieldType.SELECT,
            options=[
                SelectOption(value="hardcover", label="Hardcover"),
                SelectOption(value="paperback", label="Paperback"),
            ],
        ))

        result = manager.set_field_value(
            UUID(sample_books[0].id),
            field.id,
            "hardcover"
        )

        assert result is not None
        assert result.display_value == "Hardcover"

    def test_set_invalid_select_value_fails(self, manager, sample_books):
        """Test that invalid select value fails."""
        field = manager.create_field(CustomFieldCreate(
            name="Format",
            field_type=FieldType.SELECT,
            options=[
                SelectOption(value="hardcover", label="Hardcover"),
            ],
        ))

        result = manager.set_field_value(
            UUID(sample_books[0].id),
            field.id,
            "invalid"
        )

        assert result is None

    def test_get_book_fields(self, manager, sample_books):
        """Test getting all field values for a book."""
        field1 = manager.create_field(CustomFieldCreate(name="Field 1", field_type=FieldType.TEXT))
        field2 = manager.create_field(CustomFieldCreate(name="Field 2", field_type=FieldType.NUMBER))

        manager.set_field_value(UUID(sample_books[0].id), field1.id, "Value 1")
        manager.set_field_value(UUID(sample_books[0].id), field2.id, "42")

        result = manager.get_book_fields(UUID(sample_books[0].id))

        assert result is not None
        assert len(result.fields) == 2

    def test_update_field_value(self, manager, sample_books):
        """Test updating a field value."""
        field = manager.create_field(CustomFieldCreate(
            name="Notes",
            field_type=FieldType.TEXT,
        ))

        manager.set_field_value(UUID(sample_books[0].id), field.id, "Original")
        result = manager.set_field_value(UUID(sample_books[0].id), field.id, "Updated")

        assert result.value == "Updated"

    def test_delete_field_value(self, manager, sample_books):
        """Test deleting a field value."""
        field = manager.create_field(CustomFieldCreate(
            name="Notes",
            field_type=FieldType.TEXT,
        ))

        manager.set_field_value(UUID(sample_books[0].id), field.id, "Value")
        result = manager.delete_field_value(UUID(sample_books[0].id), field.id)

        assert result is True
        assert manager.get_field_value(UUID(sample_books[0].id), field.id) is None


class TestTagAnalytics:
    """Tests for tag analytics."""

    def test_get_tag_stats(self, manager, sample_books, sample_tags):
        """Test getting tag statistics."""
        tag = sample_tags[0]

        # Tag some books
        for book in sample_books[:3]:
            manager.tag_book(UUID(book.id), tag.id)

        stats = manager.get_tag_stats(tag.id)

        assert stats is not None
        assert stats.total_books == 3
        assert stats.completed_books > 0

    def test_get_tag_cloud(self, manager, sample_books, sample_tags):
        """Test getting tag cloud."""
        # Tag books with different tags
        manager.tag_book(UUID(sample_books[0].id), sample_tags[0].id)
        manager.tag_book(UUID(sample_books[1].id), sample_tags[0].id)
        manager.tag_book(UUID(sample_books[2].id), sample_tags[1].id)

        cloud = manager.get_tag_cloud()

        assert cloud is not None
        assert cloud.total_tags == 5
        assert cloud.most_used_tag == "Tag 1"

    def test_get_field_stats(self, manager, sample_books):
        """Test getting field statistics."""
        field = manager.create_field(CustomFieldCreate(
            name="Format",
            field_type=FieldType.TEXT,
        ))

        manager.set_field_value(UUID(sample_books[0].id), field.id, "Hardcover")
        manager.set_field_value(UUID(sample_books[1].id), field.id, "Hardcover")
        manager.set_field_value(UUID(sample_books[2].id), field.id, "Paperback")

        stats = manager.get_field_stats(field.id)

        assert stats is not None
        assert stats.books_with_value == 3
        assert stats.unique_values == 2
        assert stats.most_common_value == "Hardcover"


class TestTagSuggestions:
    """Tests for tag suggestions."""

    def test_suggest_tags_from_genres(self, manager, sample_books):
        """Test suggesting tags based on book genres."""
        # Create tag matching a genre
        manager.create_tag(TagCreate(name="Fantasy"))

        suggestions = manager.suggest_tags(UUID(sample_books[0].id))

        # Book 0 has Fantasy genre
        fantasy_suggestion = next(
            (s for s in suggestions if s.tag_name.lower() == "fantasy"),
            None
        )
        assert fantasy_suggestion is not None
        assert fantasy_suggestion.existing_tag_id is not None

    def test_suggest_tags_returns_new_tags(self, manager, sample_books):
        """Test that suggestions include new tags from genres."""
        suggestions = manager.suggest_tags(UUID(sample_books[0].id))

        # Should suggest based on genres even if tag doesn't exist
        assert len(suggestions) > 0


class TestMergeTags:
    """Tests for tag merging."""

    def test_merge_tags(self, manager, sample_books, sample_tags):
        """Test merging one tag into another."""
        source = sample_tags[0]
        target = sample_tags[1]

        # Tag books with source
        manager.tag_book(UUID(sample_books[0].id), source.id)
        manager.tag_book(UUID(sample_books[1].id), source.id)

        # Merge
        result = manager.merge_tags(source.id, target.id)

        assert result is not None
        assert manager.get_tag(source.id) is None

        # Books should now have target tag
        target_books = manager.get_books_by_tag(target.id)
        assert len(target_books) == 2


class TestEdgeCases:
    """Tests for edge cases."""

    def test_tag_nonexistent_book(self, manager, sample_tags):
        """Test tagging a non-existent book."""
        result = manager.tag_book(uuid4(), sample_tags[0].id)
        assert result is None

    def test_tag_with_nonexistent_tag(self, manager, sample_books):
        """Test tagging with non-existent tag."""
        result = manager.tag_book(UUID(sample_books[0].id), uuid4())
        assert result is None

    def test_field_validation_number_range(self, manager, sample_books):
        """Test number field validation with range."""
        field = manager.create_field(CustomFieldCreate(
            name="Rating",
            field_type=FieldType.NUMBER,
            min_value=1,
            max_value=5,
        ))

        # Valid value
        result = manager.set_field_value(UUID(sample_books[0].id), field.id, "3")
        assert result is not None

        # Out of range
        result = manager.set_field_value(UUID(sample_books[0].id), field.id, "10")
        assert result is None

    def test_field_validation_invalid_date(self, manager, sample_books):
        """Test date field validation."""
        field = manager.create_field(CustomFieldCreate(
            name="Date",
            field_type=FieldType.DATE,
        ))

        result = manager.set_field_value(UUID(sample_books[0].id), field.id, "invalid-date")
        assert result is None

    def test_empty_tag_cloud(self, manager):
        """Test tag cloud with no tags."""
        cloud = manager.get_tag_cloud()
        assert cloud.total_tags == 0
        assert cloud.most_used_tag is None
