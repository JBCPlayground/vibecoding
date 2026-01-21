"""Collections module for organizing books into custom lists.

Provides functionality for:
- Manual collections (curated book lists)
- Smart collections (dynamic filtering)
- Collection management operations
"""

from .manager import CollectionManager
from .models import Collection, CollectionBook, SmartCollectionCriteria
from .schemas import (
    CollectionCreate,
    CollectionUpdate,
    CollectionResponse,
    CollectionType,
    FilterOperator,
    SmartFilter,
)

__all__ = [
    "CollectionManager",
    "Collection",
    "CollectionBook",
    "SmartCollectionCriteria",
    "CollectionCreate",
    "CollectionUpdate",
    "CollectionResponse",
    "CollectionType",
    "FilterOperator",
    "SmartFilter",
]
