"""Pydantic schemas for book lending."""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class LoanType(str, Enum):
    """Type of loan."""

    LENT = "lent"  # You lent the book to someone
    BORROWED = "borrowed"  # You borrowed from someone


class LoanStatus(str, Enum):
    """Status of a loan."""

    ACTIVE = "active"
    RETURNED = "returned"
    LOST = "lost"
    DAMAGED = "damaged"


class BookCondition(str, Enum):
    """Condition of a book."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class ContactBase(BaseModel):
    """Base contact fields."""

    name: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class ContactCreate(ContactBase):
    """Schema for creating a contact."""

    pass


class ContactUpdate(BaseModel):
    """Schema for updating a contact."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    email: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class ContactResponse(ContactBase):
    """Schema for contact responses."""

    id: UUID
    total_lent: int
    total_borrowed: int
    total_returned: int
    total_unreturned: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactSummary(BaseModel):
    """Summary of a contact for listing."""

    id: UUID
    name: str
    email: Optional[str]
    active_loans: int
    total_loans: int


class LoanBase(BaseModel):
    """Base loan fields."""

    book_id: UUID
    contact_id: UUID
    loan_type: LoanType
    loan_date: date
    due_date: Optional[date] = None
    condition_out: Optional[BookCondition] = None
    notes: Optional[str] = None

    @field_validator("due_date")
    @classmethod
    def due_after_loan(cls, v, info):
        """Validate due date is after loan date."""
        if v and "loan_date" in info.data and v < info.data["loan_date"]:
            raise ValueError("due_date must be after loan_date")
        return v


class LoanCreate(LoanBase):
    """Schema for creating a loan."""

    pass


class LoanUpdate(BaseModel):
    """Schema for updating a loan."""

    due_date: Optional[date] = None
    status: Optional[LoanStatus] = None
    return_date: Optional[date] = None
    condition_in: Optional[BookCondition] = None
    notes: Optional[str] = None
    reminder_date: Optional[date] = None


class LoanResponse(BaseModel):
    """Schema for loan responses."""

    id: UUID
    book_id: UUID
    contact_id: UUID
    loan_type: LoanType
    status: LoanStatus
    loan_date: date
    due_date: Optional[date]
    return_date: Optional[date]
    condition_out: Optional[BookCondition]
    condition_in: Optional[BookCondition]
    notes: Optional[str]
    is_overdue: bool
    days_until_due: Optional[int]
    days_overdue: int
    created_at: datetime
    updated_at: datetime

    # Related data (populated by manager)
    book_title: Optional[str] = None
    contact_name: Optional[str] = None

    model_config = {"from_attributes": True}


class LoanSummary(BaseModel):
    """Summary of a loan for listing."""

    id: UUID
    book_title: str
    contact_name: str
    loan_type: LoanType
    status: LoanStatus
    loan_date: date
    due_date: Optional[date]
    is_overdue: bool
    days_until_due: Optional[int]


class LendingStats(BaseModel):
    """Overall lending statistics."""

    total_lent: int
    total_borrowed: int
    currently_lent: int
    currently_borrowed: int
    overdue_lent: int
    overdue_borrowed: int
    total_contacts: int


class OverdueReport(BaseModel):
    """Report of overdue loans."""

    loans: list[LoanSummary]
    total_overdue: int
    oldest_overdue_days: int
