"""Tags module for flexible book organization and custom metadata."""

from vibecoding.booktracker.tags.manager import TagManager
from vibecoding.booktracker.tags.models import (
    BookTag,
    CustomField,
    CustomFieldValue,
    Tag,
)
from vibecoding.booktracker.tags.schemas import (
    BookFieldsResponse,
    BookTagCreate,
    BookTagResponse,
    BulkTagOperation,
    BulkTagResult,
    CustomFieldCreate,
    CustomFieldResponse,
    CustomFieldUpdate,
    FieldStats,
    FieldType,
    FieldValueCreate,
    FieldValueResponse,
    FieldValueUpdate,
    SelectOption,
    TagCloud,
    TagColor,
    TagCreate,
    TaggedBookResponse,
    TagResponse,
    TagStats,
    TagSuggestion,
    TagUpdate,
    TagWithHierarchy,
)

__all__ = [
    # Manager
    "TagManager",
    # Models
    "Tag",
    "BookTag",
    "CustomField",
    "CustomFieldValue",
    # Enums
    "TagColor",
    "FieldType",
    # Tag schemas
    "TagCreate",
    "TagUpdate",
    "TagResponse",
    "TagWithHierarchy",
    # Book tag schemas
    "BookTagCreate",
    "BookTagResponse",
    "TaggedBookResponse",
    # Custom field schemas
    "SelectOption",
    "CustomFieldCreate",
    "CustomFieldUpdate",
    "CustomFieldResponse",
    # Field value schemas
    "FieldValueCreate",
    "FieldValueUpdate",
    "FieldValueResponse",
    "BookFieldsResponse",
    # Analytics schemas
    "TagStats",
    "TagCloud",
    "FieldStats",
    # Bulk operations
    "BulkTagOperation",
    "BulkTagResult",
    "TagSuggestion",
]
