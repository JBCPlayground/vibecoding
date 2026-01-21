"""Library hold and checkout tracking.

Manages library holds, checkouts, due dates, renewals, and reminders.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from ..db.models import Book
from ..db.schemas import BookStatus, BookUpdate
from ..db.sqlite import Database, get_db


class HoldStatus(str, Enum):
    """Status of a library hold."""

    PENDING = "pending"  # Hold placed, waiting
    READY = "ready"  # Ready for pickup
    CHECKED_OUT = "checked_out"  # Currently borrowed
    RETURNED = "returned"  # Returned to library
    EXPIRED = "expired"  # Hold expired


class ReminderType(str, Enum):
    """Type of library reminder."""

    DUE_SOON = "due_soon"  # Book due within reminder window
    OVERDUE = "overdue"  # Book is past due date
    HOLD_READY = "hold_ready"  # Hold is ready for pickup
    HOLD_EXPIRING = "hold_expiring"  # Hold pickup window ending


@dataclass
class LibraryItem:
    """A library book with tracking info."""

    book_id: str
    title: str
    author: str
    status: HoldStatus
    library_source: Optional[str] = None
    hold_date: Optional[date] = None
    due_date: Optional[date] = None
    pickup_location: Optional[str] = None
    renewals: int = 0
    days_until_due: Optional[int] = None
    is_overdue: bool = False

    @classmethod
    def from_book(cls, book: Book) -> "LibraryItem":
        """Create from Book model."""
        # Determine hold status from book status and dates
        if book.status == BookStatus.ON_HOLD.value:
            if book.library_due_date:
                status = HoldStatus.CHECKED_OUT
            else:
                status = HoldStatus.PENDING
        elif book.status == BookStatus.READING.value and book.library_due_date:
            status = HoldStatus.CHECKED_OUT
        else:
            status = HoldStatus.RETURNED

        # Calculate days until due
        days_until_due = None
        is_overdue = False
        if book.library_due_date:
            due = date.fromisoformat(book.library_due_date)
            days_until_due = (due - date.today()).days
            is_overdue = days_until_due < 0

        return cls(
            book_id=book.id,
            title=book.title,
            author=book.author,
            status=status,
            library_source=book.library_source,
            hold_date=date.fromisoformat(book.library_hold_date) if book.library_hold_date else None,
            due_date=date.fromisoformat(book.library_due_date) if book.library_due_date else None,
            pickup_location=book.pickup_location,
            renewals=book.renewals or 0,
            days_until_due=days_until_due,
            is_overdue=is_overdue,
        )


@dataclass
class Reminder:
    """A library reminder."""

    book_id: str
    title: str
    author: str
    reminder_type: ReminderType
    due_date: Optional[date] = None
    days_until_due: Optional[int] = None
    message: str = ""

    def __post_init__(self):
        """Generate message based on type."""
        if not self.message:
            if self.reminder_type == ReminderType.OVERDUE:
                days = abs(self.days_until_due or 0)
                self.message = f"OVERDUE by {days} day{'s' if days != 1 else ''}"
            elif self.reminder_type == ReminderType.DUE_SOON:
                days = self.days_until_due or 0
                if days == 0:
                    self.message = "Due TODAY"
                elif days == 1:
                    self.message = "Due tomorrow"
                else:
                    self.message = f"Due in {days} days"
            elif self.reminder_type == ReminderType.HOLD_READY:
                self.message = "Ready for pickup"
            elif self.reminder_type == ReminderType.HOLD_EXPIRING:
                self.message = "Pickup window ending soon"


class LibraryTracker:
    """Manages library holds and checkouts."""

    # Default settings
    DEFAULT_LOAN_DAYS = 21
    DEFAULT_RENEWAL_DAYS = 14
    MAX_RENEWALS = 2
    REMINDER_DAYS = 3  # Days before due to send reminder

    def __init__(self, db: Optional[Database] = None):
        """Initialize library tracker.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    # ========================================================================
    # Hold Management
    # ========================================================================

    def place_hold(
        self,
        book_id: str,
        pickup_location: Optional[str] = None,
        library_source: Optional[str] = None,
    ) -> LibraryItem:
        """Place a hold on a library book.

        Args:
            book_id: Book ID
            pickup_location: Where to pick up
            library_source: Library name (e.g., "Seattle Public Library")

        Returns:
            LibraryItem with updated info
        """
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError(f"Book not found: {book_id}")

        update = BookUpdate(
            status=BookStatus.ON_HOLD,
            library_hold_date=date.today(),
            pickup_location=pickup_location,
            library_source=library_source,
        )

        updated_book = self.db.update_book(book_id, update)
        return LibraryItem.from_book(updated_book)

    def mark_ready(
        self,
        book_id: str,
        pickup_location: Optional[str] = None,
    ) -> LibraryItem:
        """Mark a hold as ready for pickup.

        Args:
            book_id: Book ID
            pickup_location: Pickup location (updates if provided)

        Returns:
            LibraryItem with updated info
        """
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError(f"Book not found: {book_id}")

        update_data = {}
        if pickup_location:
            update_data["pickup_location"] = pickup_location

        # Status stays ON_HOLD but we track it's ready
        # (In a real system, you might add a separate field)
        update = BookUpdate(**update_data) if update_data else None
        if update:
            self.db.update_book(book_id, update)

        book = self.db.get_book(book_id)
        return LibraryItem.from_book(book)

    def checkout(
        self,
        book_id: str,
        due_date: Optional[date] = None,
        loan_days: Optional[int] = None,
    ) -> LibraryItem:
        """Check out a library book.

        Args:
            book_id: Book ID
            due_date: Specific due date (optional)
            loan_days: Days until due (default: DEFAULT_LOAN_DAYS)

        Returns:
            LibraryItem with updated info
        """
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError(f"Book not found: {book_id}")

        if due_date is None:
            days = loan_days or self.DEFAULT_LOAN_DAYS
            due_date = date.today() + timedelta(days=days)

        update = BookUpdate(
            status=BookStatus.READING,
            library_due_date=due_date,
            date_started=date.today(),
            renewals=0,
        )

        # Set hold date if not already set
        if not book.library_hold_date:
            update.library_hold_date = date.today()

        updated_book = self.db.update_book(book_id, update)
        return LibraryItem.from_book(updated_book)

    def renew(
        self,
        book_id: str,
        new_due_date: Optional[date] = None,
        extension_days: Optional[int] = None,
    ) -> LibraryItem:
        """Renew a library book.

        Args:
            book_id: Book ID
            new_due_date: Specific new due date (optional)
            extension_days: Days to extend (default: DEFAULT_RENEWAL_DAYS)

        Returns:
            LibraryItem with updated info

        Raises:
            ValueError: If max renewals exceeded or book not checked out
        """
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError(f"Book not found: {book_id}")

        if not book.library_due_date:
            raise ValueError("Book is not checked out from library")

        current_renewals = book.renewals or 0
        if current_renewals >= self.MAX_RENEWALS:
            raise ValueError(f"Maximum renewals ({self.MAX_RENEWALS}) reached")

        if new_due_date is None:
            days = extension_days or self.DEFAULT_RENEWAL_DAYS
            current_due = date.fromisoformat(book.library_due_date)
            # Extend from current due date or today, whichever is later
            base_date = max(current_due, date.today())
            new_due_date = base_date + timedelta(days=days)

        update = BookUpdate(
            library_due_date=new_due_date,
            renewals=current_renewals + 1,
        )

        updated_book = self.db.update_book(book_id, update)
        return LibraryItem.from_book(updated_book)

    def return_book(self, book_id: str, mark_finished: bool = False) -> LibraryItem:
        """Return a library book.

        Args:
            book_id: Book ID
            mark_finished: Whether to mark the book as completed

        Returns:
            LibraryItem with updated info
        """
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError(f"Book not found: {book_id}")

        update = BookUpdate(
            library_due_date=None,
            library_hold_date=None,
            renewals=None,
        )

        if mark_finished:
            update.status = BookStatus.COMPLETED
            update.date_finished = date.today()
        else:
            # Reset to wishlist if not finished
            update.status = BookStatus.WISHLIST

        updated_book = self.db.update_book(book_id, update)
        return LibraryItem.from_book(updated_book)

    def cancel_hold(self, book_id: str) -> LibraryItem:
        """Cancel a library hold.

        Args:
            book_id: Book ID

        Returns:
            LibraryItem with updated info
        """
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError(f"Book not found: {book_id}")

        update = BookUpdate(
            status=BookStatus.WISHLIST,
            library_hold_date=None,
            pickup_location=None,
        )

        updated_book = self.db.update_book(book_id, update)
        return LibraryItem.from_book(updated_book)

    # ========================================================================
    # Query Methods
    # ========================================================================

    def get_holds(self) -> list[LibraryItem]:
        """Get all books on hold (waiting for pickup).

        Returns:
            List of LibraryItems with hold status
        """
        books = self.db.get_books_by_status(BookStatus.ON_HOLD.value)
        items = []
        for book in books:
            # Only include books without due date (not yet checked out)
            if not book.library_due_date:
                items.append(LibraryItem.from_book(book))
        return items

    def get_checkouts(self) -> list[LibraryItem]:
        """Get all checked out library books.

        Returns:
            List of LibraryItems that are checked out
        """
        # Get books with due dates (reading or on_hold status)
        with self.db.get_session() as session:
            from sqlalchemy import select
            from ..db.models import Book as BookModel

            stmt = select(BookModel).where(
                BookModel.library_due_date.isnot(None)
            ).order_by(BookModel.library_due_date)

            books = list(session.execute(stmt).scalars().all())

            items = []
            for book in books:
                session.expunge(book)
                items.append(LibraryItem.from_book(book))

            return items

    def get_due_soon(self, days: Optional[int] = None) -> list[LibraryItem]:
        """Get books due within the specified days.

        Args:
            days: Number of days to look ahead (default: REMINDER_DAYS)

        Returns:
            List of LibraryItems due soon
        """
        if days is None:
            days = self.REMINDER_DAYS

        cutoff = date.today() + timedelta(days=days)

        checkouts = self.get_checkouts()
        return [
            item for item in checkouts
            if item.due_date and item.due_date <= cutoff and not item.is_overdue
        ]

    def get_overdue(self) -> list[LibraryItem]:
        """Get all overdue library books.

        Returns:
            List of overdue LibraryItems
        """
        checkouts = self.get_checkouts()
        return [item for item in checkouts if item.is_overdue]

    def get_all_library_items(self) -> list[LibraryItem]:
        """Get all library-related books (holds and checkouts).

        Returns:
            List of all LibraryItems
        """
        holds = self.get_holds()
        checkouts = self.get_checkouts()
        return holds + checkouts

    # ========================================================================
    # Reminders
    # ========================================================================

    def get_reminders(
        self,
        include_due_soon: bool = True,
        include_overdue: bool = True,
        due_soon_days: Optional[int] = None,
    ) -> list[Reminder]:
        """Get all active library reminders.

        Args:
            include_due_soon: Include books due soon
            include_overdue: Include overdue books
            due_soon_days: Days to look ahead for due soon

        Returns:
            List of Reminder objects, sorted by urgency
        """
        reminders = []

        if include_overdue:
            overdue = self.get_overdue()
            for item in overdue:
                reminders.append(Reminder(
                    book_id=item.book_id,
                    title=item.title,
                    author=item.author,
                    reminder_type=ReminderType.OVERDUE,
                    due_date=item.due_date,
                    days_until_due=item.days_until_due,
                ))

        if include_due_soon:
            due_soon = self.get_due_soon(days=due_soon_days)
            for item in due_soon:
                reminders.append(Reminder(
                    book_id=item.book_id,
                    title=item.title,
                    author=item.author,
                    reminder_type=ReminderType.DUE_SOON,
                    due_date=item.due_date,
                    days_until_due=item.days_until_due,
                ))

        # Sort by urgency (overdue first, then by days until due)
        def sort_key(r: Reminder) -> tuple:
            # Overdue items first (negative days), then by days ascending
            is_overdue = r.reminder_type == ReminderType.OVERDUE
            days = r.days_until_due or 0
            return (not is_overdue, days)

        reminders.sort(key=sort_key)
        return reminders

    def get_summary(self) -> dict:
        """Get a summary of library status.

        Returns:
            Dictionary with counts and lists
        """
        holds = self.get_holds()
        checkouts = self.get_checkouts()
        overdue = self.get_overdue()
        due_soon = self.get_due_soon()

        return {
            "holds_count": len(holds),
            "checkouts_count": len(checkouts),
            "overdue_count": len(overdue),
            "due_soon_count": len(due_soon),
            "holds": holds,
            "checkouts": checkouts,
            "overdue": overdue,
            "due_soon": due_soon,
        }
