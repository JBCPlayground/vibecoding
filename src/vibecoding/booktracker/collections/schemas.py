"""Pydantic schemas for collections."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CollectionType(str, Enum):
    """Type of collection."""

    MANUAL = "manual"
    SMART = "smart"


class FilterOperator(str, Enum):
    """Operators for smart collection filters."""

    EQ = "eq"  # equals
    NE = "ne"  # not equals
    GT = "gt"  # greater than
    LT = "lt"  # less than
    GTE = "gte"  # greater than or equal
    LTE = "lte"  # less than or equal
    CONTAINS = "contains"  # string contains / array contains
    IN = "in"  # value in list
    BETWEEN = "between"  # value between two values
    IS_NULL = "is_null"  # field is null
    IS_NOT_NULL = "is_not_null"  # field is not null


class SmartFilter(BaseModel):
    """A single filter condition for smart collections."""

    field: str = Field(..., description="Field to filter on")
    operator: FilterOperator = Field(..., description="Comparison operator")
    value: Optional[str | int | float | list | bool] = Field(
        None, description="Value to compare against"
    )
    negate: bool = Field(default=False, description="Negate the condition")


class SmartCriteria(BaseModel):
    """Criteria for smart collections."""

    filters: list[SmartFilter] = Field(default_factory=list)
    match_mode: str = Field(default="all", description="'all' or 'any'")
    sort_by: Optional[str] = None
    sort_order: str = Field(default="asc", description="'asc' or 'desc'")
    limit: Optional[int] = Field(None, ge=1)


class CollectionBase(BaseModel):
    """Base collection fields."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=20)
    is_pinned: bool = False


class CollectionCreate(CollectionBase):
    """Schema for creating a collection."""

    collection_type: CollectionType = CollectionType.MANUAL
    smart_criteria: Optional[SmartCriteria] = None


class CollectionUpdate(BaseModel):
    """Schema for updating a collection."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=20)
    is_pinned: Optional[bool] = None
    sort_order: Optional[int] = None
    smart_criteria: Optional[SmartCriteria] = None


class CollectionResponse(CollectionBase):
    """Schema for collection responses."""

    id: UUID
    collection_type: CollectionType
    smart_criteria: Optional[SmartCriteria] = None
    sort_order: int
    is_default: bool
    book_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionBookAdd(BaseModel):
    """Schema for adding a book to a collection."""

    book_id: UUID
    position: Optional[int] = None
    notes: Optional[str] = None


class CollectionBookUpdate(BaseModel):
    """Schema for updating a book in a collection."""

    position: Optional[int] = None
    notes: Optional[str] = None


class CollectionBookResponse(BaseModel):
    """Schema for collection book responses."""

    id: UUID
    collection_id: UUID
    book_id: UUID
    position: int
    added_at: datetime
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class CollectionSummary(BaseModel):
    """Summary of a collection for listing."""

    id: UUID
    name: str
    description: Optional[str]
    collection_type: CollectionType
    book_count: int
    icon: Optional[str]
    color: Optional[str]
    is_pinned: bool
    is_default: bool


class CollectionWithBooks(CollectionResponse):
    """Collection response including books."""

    books: list[dict] = Field(default_factory=list)
