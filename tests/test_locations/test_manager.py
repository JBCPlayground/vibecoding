"""Tests for LocationManager."""

import pytest
from datetime import datetime, timezone

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.db.models import Book
from vibecoding.booktracker.locations.manager import LocationManager
from vibecoding.booktracker.locations.schemas import (
    LocationCreate,
    LocationUpdate,
    LocationSessionCreate,
    LocationType,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a LocationManager with test database."""
    return LocationManager(db)


@pytest.fixture
def sample_book(db):
    """Create a sample book for testing."""
    with db.get_session() as session:
        book = Book(
            title="Test Book",
            author="Test Author",
            status="reading",
        )
        session.add(book)
        session.commit()
        session.refresh(book)
        book_id = book.id
    return book_id


@pytest.fixture
def sample_location(manager):
    """Create a sample location for testing."""
    data = LocationCreate(
        name="Home Office",
        location_type=LocationType.HOME,
        description="My reading nook",
        icon="🏠",
        is_favorite=True,
    )
    return manager.create_location(data)


class TestLocationCRUD:
    """Tests for location CRUD operations."""

    def test_create_location(self, manager):
        """Test creating a location."""
        data = LocationCreate(
            name="Coffee Shop",
            location_type=LocationType.CAFE,
            description="Local cafe with good lighting",
            address="123 Main St",
            icon="☕",
        )
        location = manager.create_location(data)

        assert location is not None
        assert location.name == "Coffee Shop"
        assert location.location_type == "cafe"
        assert location.description == "Local cafe with good lighting"
        assert location.address == "123 Main St"
        assert location.icon == "☕"

    def test_create_location_minimal(self, manager):
        """Test creating a location with minimal data."""
        data = LocationCreate(name="Library")
        location = manager.create_location(data)

        assert location.name == "Library"
        assert location.location_type == "other"
        assert location.is_favorite is False

    def test_get_location(self, manager, sample_location):
        """Test getting a location by ID."""
        location = manager.get_location(sample_location.id)

        assert location is not None
        assert location.id == sample_location.id
        assert location.name == "Home Office"

    def test_get_location_not_found(self, manager):
        """Test getting non-existent location."""
        location = manager.get_location("nonexistent")
        assert location is None

    def test_get_location_by_name(self, manager, sample_location):
        """Test getting a location by name."""
        location = manager.get_location_by_name("Home Office")
        assert location is not None
        assert location.id == sample_location.id

    def test_get_location_by_name_case_insensitive(self, manager, sample_location):
        """Test getting location by name is case insensitive."""
        location = manager.get_location_by_name("home office")
        assert location is not None
        assert location.id == sample_location.id

    def test_list_locations(self, manager):
        """Test listing all locations."""
        manager.create_location(LocationCreate(name="Home", location_type=LocationType.HOME))
        manager.create_location(LocationCreate(name="Cafe", location_type=LocationType.CAFE))
        manager.create_location(LocationCreate(name="Library", location_type=LocationType.LIBRARY))

        locations = manager.list_locations()
        assert len(locations) == 3

    def test_list_locations_filter_by_type(self, manager):
        """Test filtering locations by type."""
        manager.create_location(LocationCreate(name="Home", location_type=LocationType.HOME))
        manager.create_location(LocationCreate(name="Cafe 1", location_type=LocationType.CAFE))
        manager.create_location(LocationCreate(name="Cafe 2", location_type=LocationType.CAFE))

        cafes = manager.list_locations(location_type=LocationType.CAFE)
        assert len(cafes) == 2

    def test_list_locations_favorites_only(self, manager):
        """Test filtering for favorite locations only."""
        manager.create_location(LocationCreate(name="Home", is_favorite=True))
        manager.create_location(LocationCreate(name="Office", is_favorite=False))

        favorites = manager.list_locations(favorites_only=True)
        assert len(favorites) == 1
        assert favorites[0].name == "Home"

    def test_update_location(self, manager, sample_location):
        """Test updating a location."""
        data = LocationUpdate(
            name="Updated Office",
            description="New description",
        )
        updated = manager.update_location(sample_location.id, data)

        assert updated is not None
        assert updated.name == "Updated Office"
        assert updated.description == "New description"

    def test_update_location_type(self, manager, sample_location):
        """Test updating location type."""
        data = LocationUpdate(location_type=LocationType.OFFICE)
        updated = manager.update_location(sample_location.id, data)

        assert updated.location_type == "office"

    def test_update_location_not_found(self, manager):
        """Test updating non-existent location."""
        data = LocationUpdate(name="Test")
        result = manager.update_location("nonexistent", data)
        assert result is None

    def test_delete_location(self, manager, sample_location):
        """Test deleting a location."""
        result = manager.delete_location(sample_location.id)
        assert result is True

        location = manager.get_location(sample_location.id)
        assert location is None

    def test_delete_location_not_found(self, manager):
        """Test deleting non-existent location."""
        result = manager.delete_location("nonexistent")
        assert result is False


class TestLocationSessions:
    """Tests for location session operations."""

    def test_log_session(self, manager, sample_location, sample_book):
        """Test logging a reading session."""
        data = LocationSessionCreate(
            location_id=sample_location.id,
            book_id=sample_book,
            minutes_read=30,
            pages_read=25,
            notes="Good reading session",
        )
        session = manager.log_session(data)

        assert session is not None
        assert session.location_id == sample_location.id
        assert session.book_id == sample_book
        assert session.minutes_read == 30
        assert session.pages_read == 25
        assert session.notes == "Good reading session"

    def test_log_session_without_book(self, manager, sample_location):
        """Test logging a session without a book."""
        data = LocationSessionCreate(
            location_id=sample_location.id,
            minutes_read=60,
        )
        session = manager.log_session(data)

        assert session is not None
        assert session.book_id is None

    def test_log_session_location_not_found(self, manager, sample_book):
        """Test logging session to non-existent location."""
        data = LocationSessionCreate(
            location_id="nonexistent",
            minutes_read=30,
        )
        with pytest.raises(ValueError, match="Location not found"):
            manager.log_session(data)

    def test_log_session_book_not_found(self, manager, sample_location):
        """Test logging session with non-existent book."""
        data = LocationSessionCreate(
            location_id=sample_location.id,
            book_id="nonexistent",
            minutes_read=30,
        )
        with pytest.raises(ValueError, match="Book not found"):
            manager.log_session(data)

    def test_list_sessions(self, manager, sample_location, sample_book):
        """Test listing sessions."""
        for i in range(3):
            manager.log_session(LocationSessionCreate(
                location_id=sample_location.id,
                book_id=sample_book,
                minutes_read=30 + i * 10,
            ))

        sessions = manager.list_sessions()
        assert len(sessions) == 3

    def test_list_sessions_filter_by_location(self, manager, sample_book):
        """Test filtering sessions by location."""
        loc1 = manager.create_location(LocationCreate(name="Location 1"))
        loc2 = manager.create_location(LocationCreate(name="Location 2"))

        manager.log_session(LocationSessionCreate(
            location_id=loc1.id,
            minutes_read=30,
        ))
        manager.log_session(LocationSessionCreate(
            location_id=loc2.id,
            minutes_read=30,
        ))

        sessions = manager.list_sessions(location_id=loc1.id)
        assert len(sessions) == 1
        assert sessions[0].location_id == loc1.id

    def test_list_sessions_filter_by_book(self, manager, sample_location, db):
        """Test filtering sessions by book."""
        with db.get_session() as session:
            book1 = Book(title="Book 1", author="Author 1", status="reading")
            book2 = Book(title="Book 2", author="Author 2", status="reading")
            session.add(book1)
            session.add(book2)
            session.commit()
            session.refresh(book1)
            session.refresh(book2)
            book1_id = book1.id
            book2_id = book2.id

        manager.log_session(LocationSessionCreate(
            location_id=sample_location.id,
            book_id=book1_id,
            minutes_read=30,
        ))
        manager.log_session(LocationSessionCreate(
            location_id=sample_location.id,
            book_id=book2_id,
            minutes_read=45,
        ))

        sessions = manager.list_sessions(book_id=book1_id)
        assert len(sessions) == 1
        assert sessions[0].book_id == book1_id

    def test_delete_session(self, manager, sample_location):
        """Test deleting a session."""
        session_obj = manager.log_session(LocationSessionCreate(
            location_id=sample_location.id,
            minutes_read=30,
        ))

        result = manager.delete_session(session_obj.id)
        assert result is True

        sessions = manager.list_sessions()
        assert len(sessions) == 0

    def test_delete_session_not_found(self, manager):
        """Test deleting non-existent session."""
        result = manager.delete_session("nonexistent")
        assert result is False


class TestLocationTotals:
    """Tests for location totals and aggregations."""

    def test_location_total_sessions(self, manager, sample_location):
        """Test total sessions count."""
        for _ in range(5):
            manager.log_session(LocationSessionCreate(
                location_id=sample_location.id,
                minutes_read=30,
            ))

        location = manager.get_location(sample_location.id)
        assert location.total_sessions == 5

    def test_location_total_minutes(self, manager, sample_location):
        """Test total minutes calculation."""
        manager.log_session(LocationSessionCreate(
            location_id=sample_location.id,
            minutes_read=30,
        ))
        manager.log_session(LocationSessionCreate(
            location_id=sample_location.id,
            minutes_read=45,
        ))

        location = manager.get_location(sample_location.id)
        assert location.total_minutes == 75

    def test_location_total_pages(self, manager, sample_location):
        """Test total pages calculation."""
        manager.log_session(LocationSessionCreate(
            location_id=sample_location.id,
            minutes_read=30,
            pages_read=20,
        ))
        manager.log_session(LocationSessionCreate(
            location_id=sample_location.id,
            minutes_read=45,
            pages_read=35,
        ))

        location = manager.get_location(sample_location.id)
        assert location.total_pages == 55


class TestLocationStats:
    """Tests for location statistics."""

    def test_get_stats_empty(self, manager):
        """Test getting stats with no data."""
        stats = manager.get_stats()

        assert stats.total_locations == 0
        assert stats.total_sessions == 0
        assert stats.total_minutes == 0

    def test_get_stats_with_data(self, manager, sample_book):
        """Test getting stats with data."""
        # Create locations
        home = manager.create_location(LocationCreate(
            name="Home",
            location_type=LocationType.HOME,
            is_favorite=True,
        ))
        cafe = manager.create_location(LocationCreate(
            name="Cafe",
            location_type=LocationType.CAFE,
        ))

        # Log sessions
        manager.log_session(LocationSessionCreate(
            location_id=home.id,
            book_id=sample_book,
            minutes_read=60,
            pages_read=30,
        ))
        manager.log_session(LocationSessionCreate(
            location_id=home.id,
            minutes_read=30,
            pages_read=15,
        ))
        manager.log_session(LocationSessionCreate(
            location_id=cafe.id,
            minutes_read=45,
            pages_read=20,
        ))

        stats = manager.get_stats()

        assert stats.total_locations == 2
        assert stats.total_sessions == 3
        assert stats.total_minutes == 135
        assert stats.total_pages == 65
        assert stats.favorite_location == "Home"
        assert stats.most_used_location == "Home"
        assert "home" in stats.minutes_by_type
        assert "cafe" in stats.minutes_by_type

    def test_get_location_breakdown(self, manager, sample_location, sample_book):
        """Test getting breakdown for a location."""
        manager.log_session(LocationSessionCreate(
            location_id=sample_location.id,
            book_id=sample_book,
            minutes_read=60,
            pages_read=30,
        ))
        manager.log_session(LocationSessionCreate(
            location_id=sample_location.id,
            minutes_read=30,
            pages_read=15,
        ))

        breakdown = manager.get_location_breakdown(sample_location.id)

        assert breakdown is not None
        assert breakdown.location_id == sample_location.id
        assert breakdown.location_name == "Home Office"
        assert breakdown.total_sessions == 2
        assert breakdown.total_minutes == 90
        assert breakdown.total_pages == 45
        assert breakdown.average_session_minutes == 45.0
        assert len(breakdown.books_read_here) == 1

    def test_get_location_breakdown_not_found(self, manager):
        """Test getting breakdown for non-existent location."""
        breakdown = manager.get_location_breakdown("nonexistent")
        assert breakdown is None


class TestLocationResponse:
    """Tests for location response conversion."""

    def test_to_response(self, manager, sample_location):
        """Test converting location to response."""
        manager.log_session(LocationSessionCreate(
            location_id=sample_location.id,
            minutes_read=60,
            pages_read=30,
        ))

        location = manager.get_location(sample_location.id)
        response = manager.to_response(location)

        assert response.id == sample_location.id
        assert response.name == "Home Office"
        assert response.location_type == LocationType.HOME
        assert response.total_sessions == 1
        assert response.total_minutes == 60
        assert response.total_pages == 30


class TestLocationTypes:
    """Tests for location type functionality."""

    def test_all_location_types(self, manager):
        """Test creating locations with all types."""
        for loc_type in LocationType:
            location = manager.create_location(LocationCreate(
                name=f"Test {loc_type.value}",
                location_type=loc_type,
            ))
            assert location.location_type == loc_type.value

    def test_filter_each_type(self, manager):
        """Test filtering by each location type."""
        for loc_type in LocationType:
            manager.create_location(LocationCreate(
                name=f"Test {loc_type.value}",
                location_type=loc_type,
            ))

        for loc_type in LocationType:
            locations = manager.list_locations(location_type=loc_type)
            assert len(locations) == 1
            assert locations[0].location_type == loc_type.value
