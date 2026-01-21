"""Tests for LendingManager."""

import pytest
from datetime import date, timedelta
from uuid import UUID

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.db.models import Book
from vibecoding.booktracker.lending.manager import LendingManager
from vibecoding.booktracker.lending.schemas import (
    ContactCreate,
    ContactUpdate,
    LoanCreate,
    LoanUpdate,
    LoanType,
    LoanStatus,
    BookCondition,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a LendingManager with test database."""
    return LendingManager(db)


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
        for i in range(5):
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
def sample_contact(manager):
    """Create a sample contact for testing."""
    data = ContactCreate(
        name="John Doe",
        email="john@example.com",
        phone="123-456-7890",
        notes="Test contact",
    )
    return manager.create_contact(data)


class TestContactManagement:
    """Tests for contact management."""

    def test_create_contact(self, manager):
        """Test creating a contact."""
        data = ContactCreate(
            name="Alice Smith",
            email="alice@example.com",
            phone="555-1234",
            notes="Friend from book club",
        )
        contact = manager.create_contact(data)

        assert contact.id is not None
        assert contact.name == "Alice Smith"
        assert contact.email == "alice@example.com"
        assert contact.phone == "555-1234"
        assert contact.notes == "Friend from book club"
        assert contact.total_lent == 0
        assert contact.total_borrowed == 0
        assert contact.total_returned == 0
        assert contact.total_unreturned == 0

    def test_create_contact_minimal(self, manager):
        """Test creating contact with minimal info."""
        data = ContactCreate(name="Bob")
        contact = manager.create_contact(data)

        assert contact.name == "Bob"
        assert contact.email is None
        assert contact.phone is None

    def test_get_contact(self, manager, sample_contact):
        """Test getting a contact by ID."""
        contact = manager.get_contact(sample_contact.id)

        assert contact is not None
        assert contact.id == sample_contact.id
        assert contact.name == sample_contact.name

    def test_get_contact_not_found(self, manager):
        """Test getting a non-existent contact."""
        contact = manager.get_contact("non-existent-id")
        assert contact is None

    def test_get_contact_by_name(self, manager, sample_contact):
        """Test getting contact by name."""
        contact = manager.get_contact_by_name("John Doe")
        assert contact is not None
        assert contact.id == sample_contact.id

    def test_get_contact_by_name_case_insensitive(self, manager, sample_contact):
        """Test name lookup is case insensitive."""
        contact = manager.get_contact_by_name("JOHN DOE")
        assert contact is not None
        assert contact.id == sample_contact.id

    def test_get_contact_by_name_not_found(self, manager):
        """Test getting non-existent contact by name."""
        contact = manager.get_contact_by_name("Nobody")
        assert contact is None

    def test_list_contacts(self, manager):
        """Test listing all contacts."""
        # Create multiple contacts
        for name in ["Alice", "Bob", "Charlie"]:
            manager.create_contact(ContactCreate(name=name))

        contacts = manager.list_contacts()
        assert len(contacts) == 3
        # Should be sorted by name
        names = [c.name for c in contacts]
        assert names == ["Alice", "Bob", "Charlie"]

    def test_list_contacts_with_active_loans(self, manager, sample_book, sample_contact):
        """Test filtering contacts with active loans."""
        # Create another contact without loans
        manager.create_contact(ContactCreate(name="No Loans"))

        # Create a loan for sample_contact
        loan_data = LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        )
        manager.create_loan(loan_data)

        # Only sample_contact should be returned
        contacts = manager.list_contacts(with_active_loans=True)
        assert len(contacts) == 1
        assert contacts[0].id == sample_contact.id

    def test_update_contact(self, manager, sample_contact):
        """Test updating a contact."""
        data = ContactUpdate(
            name="John Updated",
            email="john.updated@example.com",
        )
        updated = manager.update_contact(sample_contact.id, data)

        assert updated is not None
        assert updated.name == "John Updated"
        assert updated.email == "john.updated@example.com"
        # Unchanged field
        assert updated.phone == sample_contact.phone

    def test_update_contact_not_found(self, manager):
        """Test updating non-existent contact."""
        data = ContactUpdate(name="Nobody")
        result = manager.update_contact("non-existent", data)
        assert result is None

    def test_delete_contact(self, manager, sample_contact):
        """Test deleting a contact."""
        result = manager.delete_contact(sample_contact.id)
        assert result is True

        # Verify deletion
        contact = manager.get_contact(sample_contact.id)
        assert contact is None

    def test_delete_contact_with_active_loans(self, manager, sample_book, sample_contact):
        """Test cannot delete contact with active loans."""
        # Create an active loan
        loan_data = LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        )
        manager.create_loan(loan_data)

        with pytest.raises(ValueError, match="Cannot delete contact with active loans"):
            manager.delete_contact(sample_contact.id)

    def test_delete_contact_not_found(self, manager):
        """Test deleting non-existent contact."""
        result = manager.delete_contact("non-existent")
        assert result is False


class TestLoanManagement:
    """Tests for loan management."""

    def test_create_loan_lent(self, manager, sample_book, sample_contact):
        """Test creating a lent loan."""
        loan_data = LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
            due_date=date.today() + timedelta(days=14),
            condition_out=BookCondition.GOOD,
            notes="Lent for vacation reading",
        )
        loan = manager.create_loan(loan_data)

        assert loan.id is not None
        assert loan.book_id == sample_book
        assert loan.contact_id == sample_contact.id
        assert loan.loan_type == "lent"
        assert loan.status == "active"
        assert loan.condition_out == "good"
        assert loan.notes == "Lent for vacation reading"

        # Verify contact stats updated
        contact = manager.get_contact(sample_contact.id)
        assert contact.total_lent == 1
        assert contact.total_unreturned == 1

    def test_create_loan_borrowed(self, manager, sample_book, sample_contact):
        """Test creating a borrowed loan."""
        loan_data = LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.BORROWED,
            loan_date=date.today(),
        )
        loan = manager.create_loan(loan_data)

        assert loan.loan_type == "borrowed"

        # Verify contact stats updated
        contact = manager.get_contact(sample_contact.id)
        assert contact.total_borrowed == 1
        assert contact.total_unreturned == 1

    def test_create_loan_book_not_found(self, manager, sample_contact):
        """Test creating loan with non-existent book."""
        loan_data = LoanCreate(
            book_id=UUID("00000000-0000-0000-0000-000000000000"),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        )
        with pytest.raises(ValueError, match="Book not found"):
            manager.create_loan(loan_data)

    def test_create_loan_contact_not_found(self, manager, sample_book):
        """Test creating loan with non-existent contact."""
        loan_data = LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID("00000000-0000-0000-0000-000000000000"),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        )
        with pytest.raises(ValueError, match="Contact not found"):
            manager.create_loan(loan_data)

    def test_create_loan_book_already_on_loan(self, manager, sample_book, sample_contact):
        """Test cannot create loan for book already on loan."""
        # Create first loan
        loan_data = LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        )
        manager.create_loan(loan_data)

        # Try to create another loan for same book
        with pytest.raises(ValueError, match="Book is already on loan"):
            manager.create_loan(loan_data)

    def test_get_loan(self, manager, sample_book, sample_contact):
        """Test getting a loan by ID."""
        loan_data = LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        )
        created = manager.create_loan(loan_data)

        loan = manager.get_loan(created.id)
        assert loan is not None
        assert loan.id == created.id

    def test_get_loan_not_found(self, manager):
        """Test getting non-existent loan."""
        loan = manager.get_loan("non-existent")
        assert loan is None

    def test_list_loans(self, manager, sample_books, sample_contact):
        """Test listing all loans."""
        # Create multiple loans
        for i, book_id in enumerate(sample_books[:3]):
            loan_data = LoanCreate(
                book_id=UUID(book_id),
                contact_id=UUID(sample_contact.id),
                loan_type=LoanType.LENT if i % 2 == 0 else LoanType.BORROWED,
                loan_date=date.today() - timedelta(days=i),
            )
            manager.create_loan(loan_data)

        loans = manager.list_loans()
        assert len(loans) == 3

    def test_list_loans_filter_by_type(self, manager, sample_books, sample_contact):
        """Test filtering loans by type."""
        # Create lent and borrowed loans
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[0]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[1]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.BORROWED,
            loan_date=date.today(),
        ))

        lent_loans = manager.list_loans(loan_type=LoanType.LENT)
        assert len(lent_loans) == 1
        assert lent_loans[0].loan_type == "lent"

        borrowed_loans = manager.list_loans(loan_type=LoanType.BORROWED)
        assert len(borrowed_loans) == 1

    def test_list_loans_filter_by_status(self, manager, sample_books, sample_contact):
        """Test filtering loans by status."""
        # Create and return a loan
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[0]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))
        manager.return_loan(loan.id)

        # Create an active loan
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[1]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        active_loans = manager.list_loans(status=LoanStatus.ACTIVE)
        assert len(active_loans) == 1

        returned_loans = manager.list_loans(status=LoanStatus.RETURNED)
        assert len(returned_loans) == 1

    def test_list_loans_filter_by_contact(self, manager, sample_books):
        """Test filtering loans by contact."""
        # Create two contacts
        contact1 = manager.create_contact(ContactCreate(name="Contact 1"))
        contact2 = manager.create_contact(ContactCreate(name="Contact 2"))

        # Create loans for each
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[0]),
            contact_id=UUID(contact1.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[1]),
            contact_id=UUID(contact2.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        contact1_loans = manager.list_loans(contact_id=contact1.id)
        assert len(contact1_loans) == 1
        assert contact1_loans[0].contact_id == contact1.id

    def test_list_loans_filter_by_book(self, manager, sample_books, sample_contact):
        """Test filtering loans by book."""
        # Create loan for specific book
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[0]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        loans = manager.list_loans(book_id=sample_books[0])
        assert len(loans) == 1
        assert loans[0].book_id == sample_books[0]

    def test_update_loan(self, manager, sample_book, sample_contact):
        """Test updating a loan."""
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        new_due = date.today() + timedelta(days=30)
        update = LoanUpdate(
            due_date=new_due,
            notes="Extended due date",
        )
        updated = manager.update_loan(loan.id, update)

        assert updated is not None
        assert updated.due_date == new_due.isoformat()
        assert updated.notes == "Extended due date"

    def test_update_loan_not_found(self, manager):
        """Test updating non-existent loan."""
        update = LoanUpdate(notes="Test")
        result = manager.update_loan("non-existent", update)
        assert result is None

    def test_return_loan(self, manager, sample_book, sample_contact):
        """Test returning a loan."""
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        returned = manager.return_loan(
            loan.id,
            return_date=date.today(),
            condition="good",
            notes="Returned in good condition",
        )

        assert returned is not None
        assert returned.status == "returned"
        assert returned.return_date == date.today().isoformat()
        assert returned.condition_in == "good"
        assert "Return notes:" in returned.notes

        # Verify contact stats updated
        contact = manager.get_contact(sample_contact.id)
        assert contact.total_returned == 1
        assert contact.total_unreturned == 0

    def test_return_loan_default_date(self, manager, sample_book, sample_contact):
        """Test returning loan with default date."""
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        returned = manager.return_loan(loan.id)
        assert returned.return_date == date.today().isoformat()

    def test_return_loan_not_active(self, manager, sample_book, sample_contact):
        """Test cannot return already returned loan."""
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))
        manager.return_loan(loan.id)

        with pytest.raises(ValueError, match="Loan is not active"):
            manager.return_loan(loan.id)

    def test_return_loan_not_found(self, manager):
        """Test returning non-existent loan."""
        result = manager.return_loan("non-existent")
        assert result is None

    def test_mark_lost(self, manager, sample_book, sample_contact):
        """Test marking a loan as lost."""
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        lost = manager.mark_lost(loan.id, notes="Never returned")

        assert lost is not None
        assert lost.status == "lost"
        assert "Lost:" in lost.notes

        # Verify contact stats updated
        contact = manager.get_contact(sample_contact.id)
        assert contact.total_unreturned == 0

    def test_mark_lost_not_found(self, manager):
        """Test marking non-existent loan as lost."""
        result = manager.mark_lost("non-existent")
        assert result is None

    def test_delete_loan(self, manager, sample_book, sample_contact):
        """Test deleting a loan."""
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        result = manager.delete_loan(loan.id)
        assert result is True

        # Verify deletion
        deleted = manager.get_loan(loan.id)
        assert deleted is None

        # Verify contact stats updated
        contact = manager.get_contact(sample_contact.id)
        assert contact.total_unreturned == 0

    def test_delete_loan_not_found(self, manager):
        """Test deleting non-existent loan."""
        result = manager.delete_loan("non-existent")
        assert result is False


class TestOverdueDetection:
    """Tests for overdue loan detection."""

    def test_list_overdue_loans(self, manager, sample_books, sample_contact):
        """Test listing overdue loans."""
        # Create overdue loan
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[0]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=7),  # Overdue
        ))

        # Create non-overdue loan
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[1]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
            due_date=date.today() + timedelta(days=14),  # Not overdue
        ))

        # Create loan without due date
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[2]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        overdue = manager.list_loans(overdue_only=True)
        assert len(overdue) == 1
        assert overdue[0].book_id == sample_books[0]

    def test_loan_is_overdue_property(self, manager, sample_book, sample_contact):
        """Test loan is_overdue property."""
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=7),
        ))

        assert loan.is_overdue is True
        assert loan.days_overdue == 7

    def test_loan_not_overdue(self, manager, sample_book, sample_contact):
        """Test non-overdue loan."""
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
            due_date=date.today() + timedelta(days=14),
        ))

        assert loan.is_overdue is False
        assert loan.days_until_due == 14

    def test_loan_no_due_date(self, manager, sample_book, sample_contact):
        """Test loan without due date."""
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        assert loan.is_overdue is False
        assert loan.days_until_due is None
        assert loan.days_overdue == 0

    def test_get_loans_due_soon(self, manager, sample_books, sample_contact):
        """Test getting loans due within specified days."""
        # Create loan due in 3 days
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[0]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
            due_date=date.today() + timedelta(days=3),
        ))

        # Create loan due in 10 days
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[1]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
            due_date=date.today() + timedelta(days=10),
        ))

        # Create overdue loan (should not be included)
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[2]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today() - timedelta(days=20),
            due_date=date.today() - timedelta(days=5),
        ))

        due_soon = manager.get_loans_due_soon(days=7)
        assert len(due_soon) == 1
        assert due_soon[0].book_id == sample_books[0]

    def test_get_overdue_report(self, manager, sample_books, sample_contact):
        """Test getting overdue report."""
        # Create overdue loan
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[0]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=10),
        ))

        report = manager.get_overdue_loans()

        assert report.total_overdue == 1
        assert report.oldest_overdue_days == 10
        assert len(report.loans) == 1
        assert report.loans[0].book_title == "Test Book 1"
        assert report.loans[0].contact_name == "John Doe"


class TestLendingStatistics:
    """Tests for lending statistics."""

    def test_get_stats_empty(self, manager):
        """Test stats with no loans."""
        stats = manager.get_stats()

        assert stats.total_lent == 0
        assert stats.total_borrowed == 0
        assert stats.currently_lent == 0
        assert stats.currently_borrowed == 0
        assert stats.overdue_lent == 0
        assert stats.overdue_borrowed == 0
        assert stats.total_contacts == 0

    def test_get_stats_with_loans(self, manager, sample_books, sample_contact):
        """Test stats with various loans."""
        # Create active lent loan (overdue)
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[0]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=5),
        ))

        # Create active lent loan (not overdue)
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[1]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
            due_date=date.today() + timedelta(days=14),
        ))

        # Create and return a loan
        loan = manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[2]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.LENT,
            loan_date=date.today() - timedelta(days=10),
        ))
        manager.return_loan(loan.id)

        # Create borrowed loan (overdue)
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_books[3]),
            contact_id=UUID(sample_contact.id),
            loan_type=LoanType.BORROWED,
            loan_date=date.today() - timedelta(days=20),
            due_date=date.today() - timedelta(days=3),
        ))

        stats = manager.get_stats()

        assert stats.total_lent == 3  # Including returned
        assert stats.total_borrowed == 1
        assert stats.currently_lent == 2  # Active only
        assert stats.currently_borrowed == 1
        assert stats.overdue_lent == 1
        assert stats.overdue_borrowed == 1
        assert stats.total_contacts == 1


class TestLoanHistory:
    """Tests for loan history queries."""

    def test_get_loan_history_for_book(self, manager, sample_book):
        """Test getting loan history for a book."""
        # Create two contacts
        contact1 = manager.create_contact(ContactCreate(name="Contact 1"))
        contact2 = manager.create_contact(ContactCreate(name="Contact 2"))

        # Create first loan and return it
        loan1 = manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(contact1.id),
            loan_type=LoanType.LENT,
            loan_date=date.today() - timedelta(days=60),
        ))
        manager.return_loan(loan1.id)

        # Create second loan
        manager.create_loan(LoanCreate(
            book_id=UUID(sample_book),
            contact_id=UUID(contact2.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
        ))

        history = manager.get_loan_history_for_book(sample_book)
        assert len(history) == 2

    def test_get_loan_history_for_contact(self, manager, sample_books, sample_contact):
        """Test getting loan history for a contact."""
        # Create multiple loans for same contact
        for i in range(3):
            loan = manager.create_loan(LoanCreate(
                book_id=UUID(sample_books[i]),
                contact_id=UUID(sample_contact.id),
                loan_type=LoanType.LENT,
                loan_date=date.today() - timedelta(days=30-i*10),
            ))
            if i < 2:
                manager.return_loan(loan.id)

        history = manager.get_loan_history_for_contact(sample_contact.id)
        assert len(history) == 3
