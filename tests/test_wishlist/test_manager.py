"""Tests for WishlistManager."""

import pytest
from datetime import date, timedelta
from uuid import UUID

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.wishlist.manager import WishlistManager
from vibecoding.booktracker.wishlist.schemas import (
    WishlistItemCreate,
    WishlistItemUpdate,
    Priority,
    WishlistSource,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a WishlistManager with test database."""
    return WishlistManager(db)


class TestWishlistCRUD:
    """Tests for basic CRUD operations."""

    def test_add_item(self, manager):
        """Test adding an item to wishlist."""
        item = WishlistItemCreate(
            title="The Great Gatsby",
            author="F. Scott Fitzgerald",
            priority=Priority.HIGH,
        )
        result = manager.add_item(item)

        assert result is not None
        assert result.title == "The Great Gatsby"
        assert result.author == "F. Scott Fitzgerald"
        assert result.priority == Priority.HIGH
        assert result.position == 0

    def test_add_item_minimal(self, manager):
        """Test adding item with only title."""
        item = WishlistItemCreate(title="Mystery Book")
        result = manager.add_item(item)

        assert result is not None
        assert result.title == "Mystery Book"
        assert result.priority == Priority.MEDIUM  # Default

    def test_add_item_with_all_fields(self, manager):
        """Test adding item with all fields populated."""
        item = WishlistItemCreate(
            title="Clean Code",
            author="Robert Martin",
            isbn="978-0132350884",
            priority=Priority.MUST_READ,
            source=WishlistSource.FRIEND,
            recommended_by="John Doe",
            recommendation_url="https://example.com/review",
            reason="Want to improve my coding skills",
            estimated_pages=464,
            estimated_hours=15.5,
            genre="Programming",
            target_date=date.today() + timedelta(days=30),
            is_available=True,
            tags=["programming", "best-practices"],
            notes="Need to buy this soon",
        )
        result = manager.add_item(item)

        assert result.title == "Clean Code"
        assert result.isbn == "978-0132350884"
        assert result.source == WishlistSource.FRIEND
        assert result.recommended_by == "John Doe"
        assert result.is_available is True
        assert "programming" in result.tags

    def test_get_item(self, manager):
        """Test getting an item by ID."""
        item = WishlistItemCreate(title="Test Book")
        created = manager.add_item(item)

        result = manager.get_item(created.id)

        assert result is not None
        assert result.id == created.id
        assert result.title == "Test Book"

    def test_get_item_not_found(self, manager):
        """Test getting non-existent item."""
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        result = manager.get_item(fake_id)

        assert result is None

    def test_update_item(self, manager):
        """Test updating an item."""
        item = WishlistItemCreate(title="Original Title", author="Unknown")
        created = manager.add_item(item)

        update = WishlistItemUpdate(
            title="Updated Title",
            author="Known Author",
            priority=Priority.HIGH,
        )
        result = manager.update_item(created.id, update)

        assert result is not None
        assert result.title == "Updated Title"
        assert result.author == "Known Author"
        assert result.priority == Priority.HIGH

    def test_update_item_partial(self, manager):
        """Test partial update of an item."""
        item = WishlistItemCreate(
            title="Test Book",
            author="Test Author",
            priority=Priority.LOW,
        )
        created = manager.add_item(item)

        update = WishlistItemUpdate(priority=Priority.HIGH)
        result = manager.update_item(created.id, update)

        assert result.title == "Test Book"  # Unchanged
        assert result.author == "Test Author"  # Unchanged
        assert result.priority == Priority.HIGH  # Changed

    def test_delete_item(self, manager):
        """Test deleting an item."""
        item = WishlistItemCreate(title="To Delete")
        created = manager.add_item(item)

        success = manager.delete_item(created.id)
        assert success is True

        result = manager.get_item(created.id)
        assert result is None

    def test_delete_item_not_found(self, manager):
        """Test deleting non-existent item."""
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        success = manager.delete_item(fake_id)

        assert success is False


class TestWishlistListing:
    """Tests for listing and filtering items."""

    def test_list_items_empty(self, manager):
        """Test listing empty wishlist."""
        items = manager.list_items()
        assert items == []

    def test_list_items_ordered_by_priority(self, manager):
        """Test items are ordered by priority then position."""
        manager.add_item(WishlistItemCreate(title="Low Priority", priority=Priority.LOW))
        manager.add_item(WishlistItemCreate(title="High Priority", priority=Priority.HIGH))
        manager.add_item(WishlistItemCreate(title="Must Read", priority=Priority.MUST_READ))

        items = manager.list_items()

        assert len(items) == 3
        assert items[0].title == "Must Read"
        assert items[1].title == "High Priority"
        assert items[2].title == "Low Priority"

    def test_list_items_filter_by_priority(self, manager):
        """Test filtering by priority."""
        manager.add_item(WishlistItemCreate(title="Book 1", priority=Priority.HIGH))
        manager.add_item(WishlistItemCreate(title="Book 2", priority=Priority.LOW))
        manager.add_item(WishlistItemCreate(title="Book 3", priority=Priority.HIGH))

        items = manager.list_items(priority=Priority.HIGH)

        assert len(items) == 2
        assert all(item.priority == Priority.HIGH for item in items)

    def test_list_items_filter_by_source(self, manager):
        """Test filtering by source."""
        manager.add_item(WishlistItemCreate(
            title="Book 1", source=WishlistSource.FRIEND
        ))
        manager.add_item(WishlistItemCreate(
            title="Book 2", source=WishlistSource.PODCAST
        ))
        manager.add_item(WishlistItemCreate(
            title="Book 3", source=WishlistSource.FRIEND
        ))

        items = manager.list_items(source=WishlistSource.FRIEND)

        assert len(items) == 2

    def test_list_items_filter_by_available(self, manager):
        """Test filtering by availability."""
        manager.add_item(WishlistItemCreate(title="Available", is_available=True))
        manager.add_item(WishlistItemCreate(title="Not Available", is_available=False))

        items = manager.list_items(is_available=True)

        assert len(items) == 1
        assert items[0].title == "Available"

    def test_list_items_search(self, manager):
        """Test search functionality."""
        manager.add_item(WishlistItemCreate(title="The Great Gatsby", author="Fitzgerald"))
        manager.add_item(WishlistItemCreate(title="Great Expectations", author="Dickens"))
        manager.add_item(WishlistItemCreate(title="1984", author="Orwell"))

        items = manager.list_items(search="Great")

        assert len(items) == 2

    def test_list_items_search_by_author(self, manager):
        """Test search includes author."""
        manager.add_item(WishlistItemCreate(title="Book 1", author="Stephen King"))
        manager.add_item(WishlistItemCreate(title="Book 2", author="J.K. Rowling"))

        items = manager.list_items(search="King")

        assert len(items) == 1
        assert items[0].author == "Stephen King"

    def test_list_items_filter_by_tag(self, manager):
        """Test filtering by tag."""
        manager.add_item(WishlistItemCreate(title="Sci-Fi 1", tags=["sci-fi", "space"]))
        manager.add_item(WishlistItemCreate(title="Fantasy 1", tags=["fantasy"]))
        manager.add_item(WishlistItemCreate(title="Sci-Fi 2", tags=["sci-fi"]))

        items = manager.list_items(tag="sci-fi")

        assert len(items) == 2

    def test_list_items_with_limit(self, manager):
        """Test limit parameter."""
        for i in range(10):
            manager.add_item(WishlistItemCreate(title=f"Book {i}"))

        items = manager.list_items(limit=5)

        assert len(items) == 5


class TestWishlistPriority:
    """Tests for priority management."""

    def test_change_priority(self, manager):
        """Test changing item priority."""
        item = WishlistItemCreate(title="Test Book", priority=Priority.LOW)
        created = manager.add_item(item)

        result = manager.change_priority(created.id, Priority.MUST_READ)

        assert result is not None
        assert result.priority == Priority.MUST_READ

    def test_change_priority_updates_position(self, manager):
        """Test that changing priority moves to end of new priority group."""
        # Add some items in different priorities
        manager.add_item(WishlistItemCreate(title="High 1", priority=Priority.HIGH))
        manager.add_item(WishlistItemCreate(title="High 2", priority=Priority.HIGH))
        low_item = manager.add_item(WishlistItemCreate(title="Low 1", priority=Priority.LOW))

        # Move low item to high priority
        result = manager.change_priority(low_item.id, Priority.HIGH)

        # Should be at position 2 (after High 1 and High 2)
        assert result.position == 2

    def test_change_priority_not_found(self, manager):
        """Test changing priority of non-existent item."""
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        result = manager.change_priority(fake_id, Priority.HIGH)

        assert result is None

    def test_get_by_priority(self, manager):
        """Test getting items grouped by priority."""
        manager.add_item(WishlistItemCreate(title="Must 1", priority=Priority.MUST_READ))
        manager.add_item(WishlistItemCreate(title="High 1", priority=Priority.HIGH))
        manager.add_item(WishlistItemCreate(title="High 2", priority=Priority.HIGH))
        manager.add_item(WishlistItemCreate(title="Low 1", priority=Priority.LOW))

        groups = manager.get_by_priority()

        assert len(groups) == 3
        assert groups[0].priority == Priority.MUST_READ
        assert groups[0].count == 1
        assert groups[1].priority == Priority.HIGH
        assert groups[1].count == 2


class TestWishlistPosition:
    """Tests for position management."""

    def test_position_auto_assigned(self, manager):
        """Test positions are automatically assigned."""
        item1 = manager.add_item(WishlistItemCreate(title="First", priority=Priority.HIGH))
        item2 = manager.add_item(WishlistItemCreate(title="Second", priority=Priority.HIGH))
        item3 = manager.add_item(WishlistItemCreate(title="Third", priority=Priority.HIGH))

        assert item1.position == 0
        assert item2.position == 1
        assert item3.position == 2

    def test_position_per_priority(self, manager):
        """Test positions are per-priority."""
        high1 = manager.add_item(WishlistItemCreate(title="High 1", priority=Priority.HIGH))
        low1 = manager.add_item(WishlistItemCreate(title="Low 1", priority=Priority.LOW))
        high2 = manager.add_item(WishlistItemCreate(title="High 2", priority=Priority.HIGH))

        assert high1.position == 0
        assert low1.position == 0  # Different priority group
        assert high2.position == 1

    def test_reorder_item_down(self, manager):
        """Test moving item to lower position (down in list)."""
        item1 = manager.add_item(WishlistItemCreate(title="First", priority=Priority.HIGH))
        item2 = manager.add_item(WishlistItemCreate(title="Second", priority=Priority.HIGH))
        item3 = manager.add_item(WishlistItemCreate(title="Third", priority=Priority.HIGH))

        # Move first item to position 2
        result = manager.reorder_item(item1.id, 2)

        assert result.position == 2

        # Check other items shifted
        items = manager.list_items(priority=Priority.HIGH)
        assert items[0].title == "Second"
        assert items[1].title == "Third"
        assert items[2].title == "First"

    def test_reorder_item_up(self, manager):
        """Test moving item to higher position (up in list)."""
        item1 = manager.add_item(WishlistItemCreate(title="First", priority=Priority.HIGH))
        item2 = manager.add_item(WishlistItemCreate(title="Second", priority=Priority.HIGH))
        item3 = manager.add_item(WishlistItemCreate(title="Third", priority=Priority.HIGH))

        # Move third item to position 0
        result = manager.reorder_item(item3.id, 0)

        assert result.position == 0

        # Check other items shifted
        items = manager.list_items(priority=Priority.HIGH)
        assert items[0].title == "Third"
        assert items[1].title == "First"
        assert items[2].title == "Second"


class TestWishlistStatus:
    """Tests for status management."""

    def test_mark_available(self, manager):
        """Test marking item as available."""
        item = WishlistItemCreate(title="Test Book", is_available=False)
        created = manager.add_item(item)

        result = manager.mark_available(created.id, True)

        assert result.is_available is True

    def test_mark_not_available(self, manager):
        """Test marking item as not available."""
        item = WishlistItemCreate(title="Test Book", is_available=True)
        created = manager.add_item(item)

        result = manager.mark_available(created.id, False)

        assert result.is_available is False

    def test_mark_on_hold(self, manager):
        """Test marking item as on hold."""
        item = WishlistItemCreate(title="Test Book", is_on_hold=False)
        created = manager.add_item(item)

        result = manager.mark_on_hold(created.id, True)

        assert result.is_on_hold is True

    def test_link_to_book(self, manager):
        """Test linking wishlist item to library book."""
        item = WishlistItemCreate(title="Test Book")
        created = manager.add_item(item)

        book_id = UUID("12345678-1234-1234-1234-123456789abc")
        result = manager.link_to_book(created.id, book_id)

        assert result.book_id == book_id
        assert result.is_in_library is True


class TestWishlistStats:
    """Tests for statistics."""

    def test_stats_empty(self, manager):
        """Test stats with empty wishlist."""
        stats = manager.get_stats()

        assert stats.total_items == 0
        assert stats.by_priority == {}
        assert stats.by_source == {}

    def test_stats_with_items(self, manager):
        """Test stats with items."""
        manager.add_item(WishlistItemCreate(
            title="Book 1",
            priority=Priority.HIGH,
            source=WishlistSource.FRIEND,
            estimated_pages=300,
            is_available=True,
        ))
        manager.add_item(WishlistItemCreate(
            title="Book 2",
            priority=Priority.HIGH,
            source=WishlistSource.PODCAST,
            estimated_pages=200,
        ))
        manager.add_item(WishlistItemCreate(
            title="Book 3",
            priority=Priority.LOW,
            source=WishlistSource.FRIEND,
            estimated_pages=400,
            is_on_hold=True,
        ))

        stats = manager.get_stats()

        assert stats.total_items == 3
        assert stats.by_priority["High"] == 2
        assert stats.by_priority["Low"] == 1
        assert stats.by_source["friend"] == 2
        assert stats.by_source["podcast"] == 1
        assert stats.available_count == 1
        assert stats.on_hold_count == 1
        assert stats.total_estimated_pages == 900

    def test_stats_overdue_targets(self, manager):
        """Test overdue target tracking."""
        yesterday = date.today() - timedelta(days=1)
        tomorrow = date.today() + timedelta(days=1)

        manager.add_item(WishlistItemCreate(
            title="Overdue",
            target_date=yesterday,
        ))
        manager.add_item(WishlistItemCreate(
            title="Upcoming",
            target_date=tomorrow,
        ))
        manager.add_item(WishlistItemCreate(
            title="No Target",
        ))

        stats = manager.get_stats()

        assert stats.items_with_target_date == 2
        assert stats.overdue_targets == 1


class TestNextUpRecommendations:
    """Tests for next up recommendations."""

    def test_next_up_empty(self, manager):
        """Test recommendations with empty wishlist."""
        recs = manager.get_next_up()
        assert recs == []

    def test_next_up_prioritizes_available_high_priority(self, manager):
        """Test available high-priority items are recommended first."""
        manager.add_item(WishlistItemCreate(
            title="Low Priority Available",
            priority=Priority.LOW,
            is_available=True,
        ))
        manager.add_item(WishlistItemCreate(
            title="High Priority Not Available",
            priority=Priority.HIGH,
            is_available=False,
        ))
        manager.add_item(WishlistItemCreate(
            title="High Priority Available",
            priority=Priority.HIGH,
            is_available=True,
        ))

        recs = manager.get_next_up(count=1)

        assert len(recs) == 1
        assert recs[0].item.title == "High Priority Available"
        assert "high priority" in recs[0].reason.lower()

    def test_next_up_includes_target_dates(self, manager):
        """Test items with target dates are recommended."""
        tomorrow = date.today() + timedelta(days=1)

        manager.add_item(WishlistItemCreate(
            title="No Target",
            priority=Priority.LOW,
        ))
        manager.add_item(WishlistItemCreate(
            title="Has Target",
            priority=Priority.LOW,
            target_date=tomorrow,
        ))

        recs = manager.get_next_up(count=5)

        # Should include the item with target date
        target_rec = next((r for r in recs if r.item.title == "Has Target"), None)
        assert target_rec is not None
        assert "1 day" in target_rec.reason.lower()

    def test_next_up_overdue_items(self, manager):
        """Test overdue items show as overdue."""
        yesterday = date.today() - timedelta(days=1)

        manager.add_item(WishlistItemCreate(
            title="Overdue Book",
            priority=Priority.LOW,
            target_date=yesterday,
        ))

        recs = manager.get_next_up()

        assert len(recs) >= 1
        overdue_rec = next((r for r in recs if r.item.title == "Overdue Book"), None)
        assert overdue_rec is not None
        assert "overdue" in overdue_rec.reason.lower()

    def test_next_up_respects_count(self, manager):
        """Test count parameter limits results."""
        # Add items across different priorities to get multiple recommendations
        for i in range(3):
            manager.add_item(WishlistItemCreate(
                title=f"Must Read {i}",
                priority=Priority.MUST_READ,
                is_available=True,
            ))
        for i in range(3):
            manager.add_item(WishlistItemCreate(
                title=f"High {i}",
                priority=Priority.HIGH,
                is_available=True,
            ))

        recs = manager.get_next_up(count=3)

        assert len(recs) == 3


class TestModelProperties:
    """Tests for model properties via response objects."""

    def test_display_title_with_author(self, manager):
        """Test display title includes author."""
        item = WishlistItemCreate(title="1984", author="George Orwell")
        created = manager.add_item(item)

        result = manager.get_item(created.id)

        assert result.display_title == "1984 by George Orwell"

    def test_display_title_without_author(self, manager):
        """Test display title without author."""
        item = WishlistItemCreate(title="Unknown Book")
        created = manager.add_item(item)

        result = manager.get_item(created.id)

        assert result.display_title == "Unknown Book"

    def test_priority_display(self, manager):
        """Test priority display strings."""
        priorities = [
            (Priority.MUST_READ, "Must Read"),
            (Priority.HIGH, "High"),
            (Priority.MEDIUM, "Medium"),
            (Priority.LOW, "Low"),
            (Priority.SOMEDAY, "Someday"),
        ]

        for priority, expected_display in priorities:
            item = WishlistItemCreate(title="Test", priority=priority)
            created = manager.add_item(item)
            assert created.priority_display == expected_display

    def test_is_in_library(self, manager):
        """Test is_in_library property."""
        item = WishlistItemCreate(title="Test Book")
        created = manager.add_item(item)

        assert created.is_in_library is False

        book_id = UUID("12345678-1234-1234-1234-123456789abc")
        linked = manager.link_to_book(created.id, book_id)

        assert linked.is_in_library is True

    def test_tag_list(self, manager):
        """Test tags are properly stored and retrieved."""
        item = WishlistItemCreate(
            title="Test Book",
            tags=["fiction", "dystopian", "classic"],
        )
        created = manager.add_item(item)

        result = manager.get_item(created.id)

        assert result.tags == ["fiction", "dystopian", "classic"]
