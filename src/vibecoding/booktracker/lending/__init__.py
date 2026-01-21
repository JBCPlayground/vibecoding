"""Book lending tracker module.

Provides functionality for:
- Tracking books lent to others
- Tracking books borrowed from others
- Due date management
- Overdue notifications
"""

from .manager import LendingManager
from .models import Loan, Contact
from .schemas import (
    LoanCreate,
    LoanUpdate,
    LoanResponse,
    LoanType,
    LoanStatus,
    ContactCreate,
    ContactUpdate,
    ContactResponse,
)

__all__ = [
    "LendingManager",
    "Loan",
    "Contact",
    "LoanCreate",
    "LoanUpdate",
    "LoanResponse",
    "LoanType",
    "LoanStatus",
    "ContactCreate",
    "ContactUpdate",
    "ContactResponse",
]
