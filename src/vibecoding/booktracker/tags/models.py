"""SQLAlchemy models for tags and custom metadata."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.models import Base


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid4())


class Tag(Base):
    """A reusable tag for organizing books."""

    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    color: Mapped[str] = mapped_column(String(20), default="gray")
    icon: Mapped[Optional[str]] = mapped_column(String(10))
    description: Mapped[Optional[str]] = mapped_column(String(200))
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tags.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now().isoformat()
    )

    # Relationships
    parent: Mapped[Optional["Tag"]] = relationship(
        "Tag", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Tag"]] = relationship(
        "Tag", back_populates="parent", cascade="all, delete-orphan"
    )
    book_tags: Mapped[list["BookTag"]] = relationship(
        "BookTag", back_populates="tag", cascade="all, delete-orphan"
    )

    @property
    def book_count(self) -> int:
        """Get count of books with this tag."""
        return len(self.book_tags) if self.book_tags else 0


class BookTag(Base):
    """Association between a book and a tag."""

    __tablename__ = "book_tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now().isoformat()
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="book_tags")


# Import Book for relationship
from ..db.models import Book  # noqa: E402


class CustomField(Base):
    """A user-defined custom metadata field."""

    __tablename__ = "custom_fields"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(200))
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[Optional[str]] = mapped_column(Text)
    options: Mapped[Optional[str]] = mapped_column(Text)  # JSON array for select types
    min_value: Mapped[Optional[float]] = mapped_column(Float)
    max_value: Mapped[Optional[float]] = mapped_column(Float)
    position: Mapped[int] = mapped_column(Integer, default=0)  # Display order
    created_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now().isoformat()
    )

    # Relationships
    values: Mapped[list["CustomFieldValue"]] = relationship(
        "CustomFieldValue", back_populates="field", cascade="all, delete-orphan"
    )

    def get_options(self) -> list[dict]:
        """Get options as list of dicts."""
        if not self.options:
            return []
        import json
        try:
            return json.loads(self.options)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_options(self, options: list[dict]) -> None:
        """Set options from list of dicts."""
        import json
        self.options = json.dumps(options) if options else None


class CustomFieldValue(Base):
    """Value of a custom field for a specific book."""

    __tablename__ = "custom_field_values"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("custom_fields.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now().isoformat()
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book")
    field: Mapped["CustomField"] = relationship("CustomField", back_populates="values")
