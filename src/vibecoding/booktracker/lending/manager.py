"""Lending manager for book loan operations."""

from datetime import date, datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_

from ..db.models import Book
from ..db.sqlite import Database, get_db
from .models import Loan, Contact
from .schemas import (
    LoanCreate,
    LoanUpdate,
    LoanType,
    LoanStatus,
    ContactCreate,
    ContactUpdate,
    LendingStats,
    LoanSummary,
    OverdueReport,
)


class LendingManager:
    """Manages book lending operations."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize lending manager.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    # -------------------------------------------------------------------------
    # Contact Management
    # -------------------------------------------------------------------------

    def create_contact(self, data: ContactCreate) -> Contact:
        """Create a new contact.

        Args:
            data: Contact creation data

        Returns:
            Created contact
        """
        with self.db.get_session() as session:
            contact = Contact(
                name=data.name,
                email=data.email,
                phone=data.phone,
                notes=data.notes,
            )
            session.add(contact)
            session.commit()
            session.refresh(contact)
            session.expunge(contact)
            return contact

    def get_contact(self, contact_id: str) -> Optional[Contact]:
        """Get a contact by ID.

        Args:
            contact_id: Contact ID

        Returns:
            Contact or None
        """
        with self.db.get_session() as session:
            stmt = select(Contact).where(Contact.id == contact_id)
            contact = session.execute(stmt).scalar_one_or_none()
            if contact:
                session.expunge(contact)
            return contact

    def get_contact_by_name(self, name: str) -> Optional[Contact]:
        """Get a contact by name.

        Args:
            name: Contact name

        Returns:
            Contact or None
        """
        with self.db.get_session() as session:
            stmt = select(Contact).where(func.lower(Contact.name) == name.lower())
            contact = session.execute(stmt).scalar_one_or_none()
            if contact:
                session.expunge(contact)
            return contact

    def list_contacts(
        self,
        with_active_loans: bool = False,
    ) -> list[Contact]:
        """List all contacts.

        Args:
            with_active_loans: Only return contacts with active loans

        Returns:
            List of contacts
        """
        with self.db.get_session() as session:
            stmt = select(Contact).order_by(Contact.name)

            if with_active_loans:
                stmt = stmt.where(Contact.total_unreturned > 0)

            contacts = session.execute(stmt).scalars().all()
            for c in contacts:
                session.expunge(c)
            return list(contacts)

    def update_contact(
        self,
        contact_id: str,
        data: ContactUpdate,
    ) -> Optional[Contact]:
        """Update a contact.

        Args:
            contact_id: Contact ID
            data: Update data

        Returns:
            Updated contact or None
        """
        with self.db.get_session() as session:
            stmt = select(Contact).where(Contact.id == contact_id)
            contact = session.execute(stmt).scalar_one_or_none()

            if not contact:
                return None

            update_data = data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if hasattr(contact, field):
                    setattr(contact, field, value)

            contact.updated_at = datetime.now(timezone.utc).isoformat()
            session.commit()
            session.refresh(contact)
            session.expunge(contact)

            return contact

    def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact.

        Args:
            contact_id: Contact ID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            stmt = select(Contact).where(Contact.id == contact_id)
            contact = session.execute(stmt).scalar_one_or_none()

            if not contact:
                return False

            # Check for active loans
            if contact.total_unreturned > 0:
                raise ValueError("Cannot delete contact with active loans")

            session.delete(contact)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Loan Management
    # -------------------------------------------------------------------------

    def create_loan(self, data: LoanCreate) -> Loan:
        """Create a new loan record.

        Args:
            data: Loan creation data

        Returns:
            Created loan
        """
        with self.db.get_session() as session:
            # Verify book exists
            book = session.execute(
                select(Book).where(Book.id == str(data.book_id))
            ).scalar_one_or_none()
            if not book:
                raise ValueError("Book not found")

            # Verify contact exists
            contact = session.execute(
                select(Contact).where(Contact.id == str(data.contact_id))
            ).scalar_one_or_none()
            if not contact:
                raise ValueError("Contact not found")

            # Check if book is already on loan
            existing_active = session.execute(
                select(Loan).where(
                    Loan.book_id == str(data.book_id),
                    Loan.status == "active",
                )
            ).scalar_one_or_none()
            if existing_active:
                raise ValueError("Book is already on loan")

            loan = Loan(
                book_id=str(data.book_id),
                contact_id=str(data.contact_id),
                loan_type=data.loan_type.value,
                loan_date=data.loan_date.isoformat(),
                due_date=data.due_date.isoformat() if data.due_date else None,
                condition_out=data.condition_out.value if data.condition_out else None,
                notes=data.notes,
            )

            session.add(loan)

            # Update contact statistics
            if data.loan_type == LoanType.LENT:
                contact.total_lent += 1
            else:
                contact.total_borrowed += 1
            contact.total_unreturned += 1

            session.commit()
            session.refresh(loan)
            session.expunge(loan)

            return loan

    def get_loan(self, loan_id: str) -> Optional[Loan]:
        """Get a loan by ID.

        Args:
            loan_id: Loan ID

        Returns:
            Loan or None
        """
        with self.db.get_session() as session:
            stmt = select(Loan).where(Loan.id == loan_id)
            loan = session.execute(stmt).scalar_one_or_none()
            if loan:
                session.expunge(loan)
            return loan

    def list_loans(
        self,
        loan_type: Optional[LoanType] = None,
        status: Optional[LoanStatus] = None,
        contact_id: Optional[str] = None,
        book_id: Optional[str] = None,
        overdue_only: bool = False,
    ) -> list[Loan]:
        """List loans with optional filters.

        Args:
            loan_type: Filter by type (lent/borrowed)
            status: Filter by status
            contact_id: Filter by contact
            book_id: Filter by book
            overdue_only: Only return overdue loans

        Returns:
            List of loans
        """
        with self.db.get_session() as session:
            stmt = select(Loan)

            if loan_type:
                stmt = stmt.where(Loan.loan_type == loan_type.value)
            if status:
                stmt = stmt.where(Loan.status == status.value)
            if contact_id:
                stmt = stmt.where(Loan.contact_id == contact_id)
            if book_id:
                stmt = stmt.where(Loan.book_id == book_id)
            if overdue_only:
                today = date.today().isoformat()
                stmt = stmt.where(
                    Loan.status == "active",
                    Loan.due_date.isnot(None),
                    Loan.due_date < today,
                )

            stmt = stmt.order_by(Loan.loan_date.desc())

            loans = session.execute(stmt).scalars().all()
            for loan in loans:
                session.expunge(loan)
            return list(loans)

    def update_loan(
        self,
        loan_id: str,
        data: LoanUpdate,
    ) -> Optional[Loan]:
        """Update a loan.

        Args:
            loan_id: Loan ID
            data: Update data

        Returns:
            Updated loan or None
        """
        with self.db.get_session() as session:
            stmt = select(Loan).where(Loan.id == loan_id)
            loan = session.execute(stmt).scalar_one_or_none()

            if not loan:
                return None

            update_data = data.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if field == "status" and value:
                    loan.status = value.value
                elif field == "due_date" and value:
                    loan.due_date = value.isoformat()
                elif field == "return_date" and value:
                    loan.return_date = value.isoformat()
                elif field == "reminder_date" and value:
                    loan.reminder_date = value.isoformat()
                elif field == "condition_in" and value:
                    loan.condition_in = value.value
                elif hasattr(loan, field):
                    setattr(loan, field, value)

            loan.updated_at = datetime.now(timezone.utc).isoformat()
            session.commit()
            session.refresh(loan)
            session.expunge(loan)

            return loan

    def return_loan(
        self,
        loan_id: str,
        return_date: Optional[date] = None,
        condition: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[Loan]:
        """Mark a loan as returned.

        Args:
            loan_id: Loan ID
            return_date: Date of return (default: today)
            condition: Condition when returned
            notes: Additional notes

        Returns:
            Updated loan or None
        """
        with self.db.get_session() as session:
            stmt = select(Loan).where(Loan.id == loan_id)
            loan = session.execute(stmt).scalar_one_or_none()

            if not loan:
                return None

            if loan.status != "active":
                raise ValueError("Loan is not active")

            loan.status = "returned"
            loan.return_date = (return_date or date.today()).isoformat()
            if condition:
                loan.condition_in = condition
            if notes:
                loan.notes = (loan.notes or "") + f"\n\nReturn notes: {notes}"

            # Update contact statistics
            contact = session.execute(
                select(Contact).where(Contact.id == loan.contact_id)
            ).scalar_one_or_none()
            if contact:
                contact.total_returned += 1
                contact.total_unreturned = max(0, contact.total_unreturned - 1)

            session.commit()
            session.refresh(loan)
            session.expunge(loan)

            return loan

    def mark_lost(
        self,
        loan_id: str,
        notes: Optional[str] = None,
    ) -> Optional[Loan]:
        """Mark a loan as lost.

        Args:
            loan_id: Loan ID
            notes: Additional notes

        Returns:
            Updated loan or None
        """
        with self.db.get_session() as session:
            stmt = select(Loan).where(Loan.id == loan_id)
            loan = session.execute(stmt).scalar_one_or_none()

            if not loan:
                return None

            loan.status = "lost"
            if notes:
                loan.notes = (loan.notes or "") + f"\n\nLost: {notes}"

            # Update contact statistics
            contact = session.execute(
                select(Contact).where(Contact.id == loan.contact_id)
            ).scalar_one_or_none()
            if contact:
                contact.total_unreturned = max(0, contact.total_unreturned - 1)

            session.commit()
            session.refresh(loan)
            session.expunge(loan)

            return loan

    def delete_loan(self, loan_id: str) -> bool:
        """Delete a loan record.

        Args:
            loan_id: Loan ID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            stmt = select(Loan).where(Loan.id == loan_id)
            loan = session.execute(stmt).scalar_one_or_none()

            if not loan:
                return False

            # Update contact statistics if loan was active
            if loan.status == "active":
                contact = session.execute(
                    select(Contact).where(Contact.id == loan.contact_id)
                ).scalar_one_or_none()
                if contact:
                    contact.total_unreturned = max(0, contact.total_unreturned - 1)

            session.delete(loan)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Statistics and Reports
    # -------------------------------------------------------------------------

    def get_stats(self) -> LendingStats:
        """Get overall lending statistics.

        Returns:
            LendingStats with counts
        """
        with self.db.get_session() as session:
            today = date.today().isoformat()

            # Count lent books
            total_lent = session.execute(
                select(func.count()).where(Loan.loan_type == "lent")
            ).scalar() or 0

            currently_lent = session.execute(
                select(func.count()).where(
                    Loan.loan_type == "lent",
                    Loan.status == "active",
                )
            ).scalar() or 0

            overdue_lent = session.execute(
                select(func.count()).where(
                    Loan.loan_type == "lent",
                    Loan.status == "active",
                    Loan.due_date.isnot(None),
                    Loan.due_date < today,
                )
            ).scalar() or 0

            # Count borrowed books
            total_borrowed = session.execute(
                select(func.count()).where(Loan.loan_type == "borrowed")
            ).scalar() or 0

            currently_borrowed = session.execute(
                select(func.count()).where(
                    Loan.loan_type == "borrowed",
                    Loan.status == "active",
                )
            ).scalar() or 0

            overdue_borrowed = session.execute(
                select(func.count()).where(
                    Loan.loan_type == "borrowed",
                    Loan.status == "active",
                    Loan.due_date.isnot(None),
                    Loan.due_date < today,
                )
            ).scalar() or 0

            # Count contacts
            total_contacts = session.execute(
                select(func.count()).select_from(Contact)
            ).scalar() or 0

            return LendingStats(
                total_lent=total_lent,
                total_borrowed=total_borrowed,
                currently_lent=currently_lent,
                currently_borrowed=currently_borrowed,
                overdue_lent=overdue_lent,
                overdue_borrowed=overdue_borrowed,
                total_contacts=total_contacts,
            )

    def get_overdue_loans(self) -> OverdueReport:
        """Get report of overdue loans.

        Returns:
            OverdueReport with overdue loans
        """
        loans = self.list_loans(overdue_only=True)
        summaries = []
        oldest_days = 0

        for loan in loans:
            # Get book and contact info within session
            book_title = None
            contact_name = None
            with self.db.get_session() as session:
                book = session.execute(
                    select(Book).where(Book.id == loan.book_id)
                ).scalar_one_or_none()
                contact = session.execute(
                    select(Contact).where(Contact.id == loan.contact_id)
                ).scalar_one_or_none()
                if book:
                    book_title = book.title
                if contact:
                    contact_name = contact.name

            if book_title and contact_name:
                summary = LoanSummary(
                    id=UUID(loan.id),
                    book_title=book_title,
                    contact_name=contact_name,
                    loan_type=LoanType(loan.loan_type),
                    status=LoanStatus(loan.status),
                    loan_date=date.fromisoformat(loan.loan_date),
                    due_date=date.fromisoformat(loan.due_date) if loan.due_date else None,
                    is_overdue=loan.is_overdue,
                    days_until_due=loan.days_until_due,
                )
                summaries.append(summary)

                if loan.days_overdue > oldest_days:
                    oldest_days = loan.days_overdue

        return OverdueReport(
            loans=summaries,
            total_overdue=len(summaries),
            oldest_overdue_days=oldest_days,
        )

    def get_loans_due_soon(self, days: int = 7) -> list[Loan]:
        """Get loans due within specified days.

        Args:
            days: Number of days to look ahead

        Returns:
            List of loans due soon
        """
        with self.db.get_session() as session:
            today = date.today()
            future = today + timedelta(days=days)

            stmt = select(Loan).where(
                Loan.status == "active",
                Loan.due_date.isnot(None),
                Loan.due_date >= today.isoformat(),
                Loan.due_date <= future.isoformat(),
            ).order_by(Loan.due_date)

            loans = session.execute(stmt).scalars().all()
            for loan in loans:
                session.expunge(loan)
            return list(loans)

    def get_loan_history_for_book(self, book_id: str) -> list[Loan]:
        """Get loan history for a specific book.

        Args:
            book_id: Book ID

        Returns:
            List of loans for the book
        """
        return self.list_loans(book_id=book_id)

    def get_loan_history_for_contact(self, contact_id: str) -> list[Loan]:
        """Get loan history for a specific contact.

        Args:
            contact_id: Contact ID

        Returns:
            List of loans with the contact
        """
        return self.list_loans(contact_id=contact_id)
