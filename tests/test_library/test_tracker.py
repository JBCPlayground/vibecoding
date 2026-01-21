"""Tests for library tracker."""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from src.vibecoding.booktracker.db.schemas import BookStatus
from src.vibecoding.booktracker.library.tracker import (
    HoldStatus,
    LibraryItem,
    LibraryTracker,
    Reminder,
    ReminderType,
)


class TestLibraryItem:
    """Tests for LibraryItem dataclass."""

    def test_create_basic_item(self):
        """Test creating a basic LibraryItem."""
        item = LibraryItem(
            book_id="test-id",
            title="Test Book",
            author="Test Author",
            status=HoldStatus.PENDING,
        )

        assert item.book_id == "test-id"
        assert item.title == "Test Book"
        assert item.status == HoldStatus.PENDING
        assert item.renewals == 0
        assert not item.is_overdue

    def test_from_book_on_hold(self):
        """Test creating from book on hold."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.ON_HOLD.value
        mock_book.library_source = "Public Library"
        mock_book.library_hold_date = date.today().isoformat()
        mock_book.library_due_date = None
        mock_book.pickup_location = "Main Branch"
        mock_book.renewals = 0

        item = LibraryItem.from_book(mock_book)

        assert item.status == HoldStatus.PENDING
        assert item.pickup_location == "Main Branch"
        assert item.is_overdue is False

    def test_from_book_checked_out(self):
        """Test creating from checked out book."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.READING.value
        mock_book.library_source = "Public Library"
        mock_book.library_hold_date = (date.today() - timedelta(days=7)).isoformat()
        mock_book.library_due_date = (date.today() + timedelta(days=14)).isoformat()
        mock_book.pickup_location = "Main Branch"
        mock_book.renewals = 1

        item = LibraryItem.from_book(mock_book)

        assert item.status == HoldStatus.CHECKED_OUT
        assert item.days_until_due == 14
        assert item.renewals == 1
        assert not item.is_overdue

    def test_from_book_overdue(self):
        """Test creating from overdue book."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.READING.value
        mock_book.library_source = None
        mock_book.library_hold_date = None
        mock_book.library_due_date = (date.today() - timedelta(days=3)).isoformat()
        mock_book.pickup_location = None
        mock_book.renewals = 2

        item = LibraryItem.from_book(mock_book)

        assert item.status == HoldStatus.CHECKED_OUT
        assert item.days_until_due == -3
        assert item.is_overdue is True


class TestReminder:
    """Tests for Reminder dataclass."""

    def test_overdue_reminder_message(self):
        """Test overdue reminder generates correct message."""
        reminder = Reminder(
            book_id="book-123",
            title="Test Book",
            author="Test Author",
            reminder_type=ReminderType.OVERDUE,
            due_date=date.today() - timedelta(days=5),
            days_until_due=-5,
        )

        assert "OVERDUE" in reminder.message
        assert "5 days" in reminder.message

    def test_due_today_reminder_message(self):
        """Test due today reminder."""
        reminder = Reminder(
            book_id="book-123",
            title="Test Book",
            author="Test Author",
            reminder_type=ReminderType.DUE_SOON,
            due_date=date.today(),
            days_until_due=0,
        )

        assert "TODAY" in reminder.message

    def test_due_tomorrow_reminder_message(self):
        """Test due tomorrow reminder."""
        reminder = Reminder(
            book_id="book-123",
            title="Test Book",
            author="Test Author",
            reminder_type=ReminderType.DUE_SOON,
            due_date=date.today() + timedelta(days=1),
            days_until_due=1,
        )

        assert "tomorrow" in reminder.message

    def test_due_soon_reminder_message(self):
        """Test due soon reminder."""
        reminder = Reminder(
            book_id="book-123",
            title="Test Book",
            author="Test Author",
            reminder_type=ReminderType.DUE_SOON,
            due_date=date.today() + timedelta(days=3),
            days_until_due=3,
        )

        assert "3 days" in reminder.message


class TestLibraryTracker:
    """Tests for LibraryTracker."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        return MagicMock()

    @pytest.fixture
    def tracker(self, mock_db):
        """Create a tracker with mocked database."""
        return LibraryTracker(db=mock_db)

    def test_place_hold(self, tracker, mock_db):
        """Test placing a hold."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.ON_HOLD.value
        mock_book.library_hold_date = date.today().isoformat()
        mock_book.library_due_date = None
        mock_book.pickup_location = "Main Branch"
        mock_book.library_source = "Public Library"
        mock_book.renewals = 0

        mock_db.get_book.return_value = mock_book
        mock_db.update_book.return_value = mock_book

        item = tracker.place_hold(
            book_id="book-123",
            pickup_location="Main Branch",
            library_source="Public Library",
        )

        assert item.title == "Test Book"
        mock_db.update_book.assert_called_once()
        call_args = mock_db.update_book.call_args
        assert call_args[0][0] == "book-123"

    def test_place_hold_book_not_found(self, tracker, mock_db):
        """Test placing hold on nonexistent book."""
        mock_db.get_book.return_value = None

        with pytest.raises(ValueError, match="Book not found"):
            tracker.place_hold(book_id="invalid-id")

    def test_checkout(self, tracker, mock_db):
        """Test checking out a book."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.READING.value
        mock_book.library_hold_date = date.today().isoformat()
        mock_book.library_due_date = (date.today() + timedelta(days=21)).isoformat()
        mock_book.pickup_location = None
        mock_book.library_source = None
        mock_book.renewals = 0

        mock_db.get_book.return_value = mock_book
        mock_db.update_book.return_value = mock_book

        item = tracker.checkout(book_id="book-123")

        assert item.status == HoldStatus.CHECKED_OUT
        mock_db.update_book.assert_called_once()

    def test_checkout_with_custom_due_date(self, tracker, mock_db):
        """Test checkout with specific due date."""
        due_date = date.today() + timedelta(days=14)

        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.READING.value
        mock_book.library_hold_date = date.today().isoformat()
        mock_book.library_due_date = due_date.isoformat()
        mock_book.pickup_location = None
        mock_book.library_source = None
        mock_book.renewals = 0

        mock_db.get_book.return_value = mock_book
        mock_db.update_book.return_value = mock_book

        item = tracker.checkout(book_id="book-123", due_date=due_date)

        assert item.due_date == due_date

    def test_renew(self, tracker, mock_db):
        """Test renewing a book."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.READING.value
        mock_book.library_hold_date = date.today().isoformat()
        mock_book.library_due_date = (date.today() + timedelta(days=3)).isoformat()
        mock_book.pickup_location = None
        mock_book.library_source = None
        mock_book.renewals = 0

        # After renewal
        renewed_book = MagicMock()
        renewed_book.id = "book-123"
        renewed_book.title = "Test Book"
        renewed_book.author = "Test Author"
        renewed_book.status = BookStatus.READING.value
        renewed_book.library_hold_date = date.today().isoformat()
        renewed_book.library_due_date = (date.today() + timedelta(days=17)).isoformat()
        renewed_book.pickup_location = None
        renewed_book.library_source = None
        renewed_book.renewals = 1

        mock_db.get_book.return_value = mock_book
        mock_db.update_book.return_value = renewed_book

        item = tracker.renew(book_id="book-123")

        assert item.renewals == 1
        mock_db.update_book.assert_called_once()

    def test_renew_max_renewals(self, tracker, mock_db):
        """Test renewing when max renewals reached."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.library_due_date = (date.today() + timedelta(days=3)).isoformat()
        mock_book.renewals = 2  # Max is 2

        mock_db.get_book.return_value = mock_book

        with pytest.raises(ValueError, match="Maximum renewals"):
            tracker.renew(book_id="book-123")

    def test_renew_not_checked_out(self, tracker, mock_db):
        """Test renewing a book that's not checked out."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.library_due_date = None  # Not checked out

        mock_db.get_book.return_value = mock_book

        with pytest.raises(ValueError, match="not checked out"):
            tracker.renew(book_id="book-123")

    def test_return_book(self, tracker, mock_db):
        """Test returning a book."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.WISHLIST.value
        mock_book.library_hold_date = None
        mock_book.library_due_date = None
        mock_book.pickup_location = None
        mock_book.library_source = None
        mock_book.renewals = None

        mock_db.get_book.return_value = mock_book
        mock_db.update_book.return_value = mock_book

        item = tracker.return_book(book_id="book-123")

        mock_db.update_book.assert_called_once()

    def test_return_book_mark_finished(self, tracker, mock_db):
        """Test returning a book and marking as finished."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.COMPLETED.value
        mock_book.library_hold_date = None
        mock_book.library_due_date = None
        mock_book.pickup_location = None
        mock_book.library_source = None
        mock_book.renewals = None

        mock_db.get_book.return_value = mock_book
        mock_db.update_book.return_value = mock_book

        tracker.return_book(book_id="book-123", mark_finished=True)

        call_args = mock_db.update_book.call_args
        update_data = call_args[0][1]
        assert update_data.status == BookStatus.COMPLETED

    def test_cancel_hold(self, tracker, mock_db):
        """Test cancelling a hold."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.WISHLIST.value
        mock_book.library_hold_date = None
        mock_book.library_due_date = None
        mock_book.pickup_location = None
        mock_book.library_source = None
        mock_book.renewals = None

        mock_db.get_book.return_value = mock_book
        mock_db.update_book.return_value = mock_book

        tracker.cancel_hold(book_id="book-123")

        mock_db.update_book.assert_called_once()

    def test_get_holds(self, tracker, mock_db):
        """Test getting holds."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Test Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.ON_HOLD.value
        mock_book.library_hold_date = date.today().isoformat()
        mock_book.library_due_date = None
        mock_book.pickup_location = "Main Branch"
        mock_book.library_source = None
        mock_book.renewals = 0

        mock_db.get_books_by_status.return_value = [mock_book]

        holds = tracker.get_holds()

        assert len(holds) == 1
        assert holds[0].status == HoldStatus.PENDING

    def test_get_overdue(self, tracker, mock_db):
        """Test getting overdue books."""
        mock_book = MagicMock()
        mock_book.id = "book-123"
        mock_book.title = "Overdue Book"
        mock_book.author = "Test Author"
        mock_book.status = BookStatus.READING.value
        mock_book.library_hold_date = None
        mock_book.library_due_date = (date.today() - timedelta(days=3)).isoformat()
        mock_book.pickup_location = None
        mock_book.library_source = None
        mock_book.renewals = 0

        # Mock the session context
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_book]

        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        overdue = tracker.get_overdue()

        assert len(overdue) == 1
        assert overdue[0].is_overdue is True

    def test_get_reminders(self, tracker, mock_db):
        """Test getting reminders."""
        # Mock an overdue book
        overdue_book = MagicMock()
        overdue_book.id = "book-1"
        overdue_book.title = "Overdue Book"
        overdue_book.author = "Author 1"
        overdue_book.status = BookStatus.READING.value
        overdue_book.library_hold_date = None
        overdue_book.library_due_date = (date.today() - timedelta(days=2)).isoformat()
        overdue_book.pickup_location = None
        overdue_book.library_source = None
        overdue_book.renewals = 0

        # Mock a book due soon
        due_soon_book = MagicMock()
        due_soon_book.id = "book-2"
        due_soon_book.title = "Due Soon Book"
        due_soon_book.author = "Author 2"
        due_soon_book.status = BookStatus.READING.value
        due_soon_book.library_hold_date = None
        due_soon_book.library_due_date = (date.today() + timedelta(days=1)).isoformat()
        due_soon_book.pickup_location = None
        due_soon_book.library_source = None
        due_soon_book.renewals = 0

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            overdue_book, due_soon_book
        ]

        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        reminders = tracker.get_reminders()

        assert len(reminders) == 2
        # Overdue should be first
        assert reminders[0].reminder_type == ReminderType.OVERDUE
        assert reminders[1].reminder_type == ReminderType.DUE_SOON

    def test_get_summary(self, tracker, mock_db):
        """Test getting library summary."""
        # Setup mocks
        mock_db.get_books_by_status.return_value = []

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        summary = tracker.get_summary()

        assert "holds_count" in summary
        assert "checkouts_count" in summary
        assert "overdue_count" in summary
        assert "due_soon_count" in summary


class TestHoldStatus:
    """Tests for HoldStatus enum."""

    def test_enum_values(self):
        """Test enum values."""
        assert HoldStatus.PENDING.value == "pending"
        assert HoldStatus.READY.value == "ready"
        assert HoldStatus.CHECKED_OUT.value == "checked_out"
        assert HoldStatus.RETURNED.value == "returned"


class TestReminderType:
    """Tests for ReminderType enum."""

    def test_enum_values(self):
        """Test enum values."""
        assert ReminderType.DUE_SOON.value == "due_soon"
        assert ReminderType.OVERDUE.value == "overdue"
        assert ReminderType.HOLD_READY.value == "hold_ready"
