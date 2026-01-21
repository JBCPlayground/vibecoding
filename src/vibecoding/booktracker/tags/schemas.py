"""Pydantic schemas for tags and custom metadata."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TagColor(str, Enum):
    """Predefined tag colors."""

    RED = "red"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    PURPLE = "purple"
    PINK = "pink"
    GRAY = "gray"
    TEAL = "teal"
    INDIGO = "indigo"


class FieldType(str, Enum):
    """Types of custom fields."""

    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    URL = "url"
    RATING = "rating"


# ============================================================================
# Tag Schemas
# ============================================================================


class TagCreate(BaseModel):
    """Schema for creating a tag."""

    name: str = Field(..., min_length=1, max_length=50)
    color: TagColor = TagColor.GRAY
    icon: Optional[str] = Field(None, max_length=10)  # Emoji or icon name
    description: Optional[str] = Field(None, max_length=200)
    parent_id: Optional[UUID] = None  # For hierarchical tags


class TagUpdate(BaseModel):
    """Schema for updating a tag."""

    name: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[TagColor] = None
    icon: Optional[str] = Field(None, max_length=10)
    description: Optional[str] = Field(None, max_length=200)
    parent_id: Optional[UUID] = None


class TagResponse(BaseModel):
    """Response schema for a tag."""

    id: UUID
    name: str
    color: TagColor
    icon: Optional[str]
    description: Optional[str]
    parent_id: Optional[UUID]
    book_count: int
    created_at: str

    model_config = {"from_attributes": True}


class TagWithHierarchy(TagResponse):
    """Tag with parent/child information."""

    parent_name: Optional[str] = None
    children: list["TagWithHierarchy"] = []
    full_path: str  # "Parent > Child > Grandchild"


# ============================================================================
# Book Tag Schemas
# ============================================================================


class BookTagCreate(BaseModel):
    """Schema for tagging a book."""

    book_id: UUID
    tag_id: UUID


class BookTagResponse(BaseModel):
    """Response for a book's tag."""

    tag_id: UUID
    tag_name: str
    tag_color: TagColor
    tag_icon: Optional[str]
    added_at: str

    model_config = {"from_attributes": True}


class TaggedBookResponse(BaseModel):
    """Response for a tagged book."""

    book_id: UUID
    book_title: str
    book_author: Optional[str]
    tags: list[BookTagResponse]

    model_config = {"from_attributes": True}


# ============================================================================
# Custom Field Schemas
# ============================================================================


class SelectOption(BaseModel):
    """Option for select/multi-select fields."""

    value: str
    label: str
    color: Optional[TagColor] = None


class CustomFieldCreate(BaseModel):
    """Schema for creating a custom field."""

    name: str = Field(..., min_length=1, max_length=50)
    field_type: FieldType
    description: Optional[str] = Field(None, max_length=200)
    is_required: bool = False
    default_value: Optional[str] = None
    options: Optional[list[SelectOption]] = None  # For select types
    min_value: Optional[float] = None  # For number/rating
    max_value: Optional[float] = None


class CustomFieldUpdate(BaseModel):
    """Schema for updating a custom field."""

    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=200)
    is_required: Optional[bool] = None
    default_value: Optional[str] = None
    options: Optional[list[SelectOption]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class CustomFieldResponse(BaseModel):
    """Response schema for a custom field."""

    id: UUID
    name: str
    field_type: FieldType
    description: Optional[str]
    is_required: bool
    default_value: Optional[str]
    options: Optional[list[SelectOption]]
    min_value: Optional[float]
    max_value: Optional[float]
    usage_count: int  # How many books have this field set
    created_at: str

    model_config = {"from_attributes": True}


# ============================================================================
# Custom Field Value Schemas
# ============================================================================


class FieldValueCreate(BaseModel):
    """Schema for setting a custom field value on a book."""

    book_id: UUID
    field_id: UUID
    value: str  # Stored as string, interpreted based on field type


class FieldValueUpdate(BaseModel):
    """Schema for updating a field value."""

    value: str


class FieldValueResponse(BaseModel):
    """Response for a custom field value."""

    field_id: UUID
    field_name: str
    field_type: FieldType
    value: str
    display_value: str  # Formatted for display

    model_config = {"from_attributes": True}


class BookFieldsResponse(BaseModel):
    """All custom field values for a book."""

    book_id: UUID
    book_title: str
    fields: list[FieldValueResponse]

    model_config = {"from_attributes": True}


# ============================================================================
# Tag Analytics
# ============================================================================


class TagStats(BaseModel):
    """Statistics for a tag."""

    tag_id: UUID
    tag_name: str
    tag_color: TagColor
    total_books: int
    completed_books: int
    average_rating: Optional[float]
    total_pages: int


class TagCloud(BaseModel):
    """Tag cloud data for visualization."""

    tags: list[TagStats]
    total_tags: int
    most_used_tag: Optional[str]
    least_used_tag: Optional[str]


class FieldStats(BaseModel):
    """Statistics for a custom field."""

    field_id: UUID
    field_name: str
    field_type: FieldType
    books_with_value: int
    unique_values: int
    most_common_value: Optional[str]


# ============================================================================
# Bulk Operations
# ============================================================================


class BulkTagOperation(BaseModel):
    """Schema for bulk tag operations."""

    book_ids: list[UUID]
    tag_ids: list[UUID]
    operation: str  # "add" or "remove"


class BulkTagResult(BaseModel):
    """Result of bulk tag operation."""

    books_affected: int
    tags_applied: int
    tags_removed: int
    errors: list[str]


class TagSuggestion(BaseModel):
    """Suggested tag based on book content."""

    tag_name: str
    confidence: float  # 0.0 to 1.0
    reason: str  # Why this tag is suggested
    existing_tag_id: Optional[UUID] = None  # If matches existing tag
