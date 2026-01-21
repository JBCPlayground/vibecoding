"""Manager for tags and custom metadata."""

import json
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func

from ..db.sqlite import Database
from ..db.models import Book
from ..db.schemas import BookStatus
from .models import Tag, BookTag, CustomField, CustomFieldValue
from .schemas import (
    TagColor,
    FieldType,
    TagCreate,
    TagUpdate,
    TagResponse,
    TagWithHierarchy,
    BookTagCreate,
    BookTagResponse,
    TaggedBookResponse,
    CustomFieldCreate,
    CustomFieldUpdate,
    CustomFieldResponse,
    SelectOption,
    FieldValueCreate,
    FieldValueUpdate,
    FieldValueResponse,
    BookFieldsResponse,
    TagStats,
    TagCloud,
    FieldStats,
    BulkTagOperation,
    BulkTagResult,
    TagSuggestion,
)


class TagManager:
    """Manager for tags and custom metadata operations."""

    def __init__(self, db: Database):
        """Initialize the tag manager.

        Args:
            db: Database instance
        """
        self.db = db

    # ========================================================================
    # Tag CRUD
    # ========================================================================

    def create_tag(self, tag_data: TagCreate) -> TagResponse:
        """Create a new tag.

        Args:
            tag_data: Tag creation data

        Returns:
            Created tag response
        """
        with self.db.get_session() as session:
            # Check for duplicate name
            existing = session.query(Tag).filter(
                func.lower(Tag.name) == tag_data.name.lower()
            ).first()
            if existing:
                return self._tag_to_response(existing)

            tag = Tag(
                name=tag_data.name,
                color=tag_data.color.value,
                icon=tag_data.icon,
                description=tag_data.description,
                parent_id=str(tag_data.parent_id) if tag_data.parent_id else None,
            )
            session.add(tag)
            session.commit()
            session.refresh(tag)

            return self._tag_to_response(tag)

    def get_tag(self, tag_id: UUID) -> Optional[TagResponse]:
        """Get a tag by ID.

        Args:
            tag_id: Tag UUID

        Returns:
            Tag response or None
        """
        with self.db.get_session() as session:
            tag = session.query(Tag).filter(Tag.id == str(tag_id)).first()
            if not tag:
                return None
            return self._tag_to_response(tag)

    def get_tag_by_name(self, name: str) -> Optional[TagResponse]:
        """Get a tag by name.

        Args:
            name: Tag name

        Returns:
            Tag response or None
        """
        with self.db.get_session() as session:
            tag = session.query(Tag).filter(
                func.lower(Tag.name) == name.lower()
            ).first()
            if not tag:
                return None
            return self._tag_to_response(tag)

    def get_all_tags(
        self,
        parent_id: Optional[UUID] = None,
        include_children: bool = False,
    ) -> list[TagResponse]:
        """Get all tags.

        Args:
            parent_id: Filter by parent tag
            include_children: Include child tags in hierarchy

        Returns:
            List of tag responses
        """
        with self.db.get_session() as session:
            query = session.query(Tag)

            if parent_id is not None:
                query = query.filter(Tag.parent_id == str(parent_id))
            elif not include_children:
                # Only root tags
                query = query.filter(Tag.parent_id.is_(None))

            tags = query.order_by(Tag.name).all()
            return [self._tag_to_response(tag) for tag in tags]

    def get_tags_hierarchy(self) -> list[TagWithHierarchy]:
        """Get all tags in hierarchical structure.

        Returns:
            List of tags with hierarchy
        """
        with self.db.get_session() as session:
            # Get root tags
            root_tags = session.query(Tag).filter(
                Tag.parent_id.is_(None)
            ).order_by(Tag.name).all()

            return [self._build_tag_hierarchy(tag, session) for tag in root_tags]

    def update_tag(
        self, tag_id: UUID, update_data: TagUpdate
    ) -> Optional[TagResponse]:
        """Update a tag.

        Args:
            tag_id: Tag UUID
            update_data: Update data

        Returns:
            Updated tag response or None
        """
        with self.db.get_session() as session:
            tag = session.query(Tag).filter(Tag.id == str(tag_id)).first()
            if not tag:
                return None

            if update_data.name is not None:
                tag.name = update_data.name
            if update_data.color is not None:
                tag.color = update_data.color.value
            if update_data.icon is not None:
                tag.icon = update_data.icon
            if update_data.description is not None:
                tag.description = update_data.description
            if update_data.parent_id is not None:
                tag.parent_id = str(update_data.parent_id)

            session.commit()
            session.refresh(tag)

            return self._tag_to_response(tag)

    def delete_tag(self, tag_id: UUID) -> bool:
        """Delete a tag.

        Args:
            tag_id: Tag UUID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            tag = session.query(Tag).filter(Tag.id == str(tag_id)).first()
            if not tag:
                return False

            session.delete(tag)
            session.commit()
            return True

    def merge_tags(
        self, source_id: UUID, target_id: UUID
    ) -> Optional[TagResponse]:
        """Merge one tag into another.

        Args:
            source_id: Tag to merge from (will be deleted)
            target_id: Tag to merge into

        Returns:
            Target tag response or None
        """
        with self.db.get_session() as session:
            source = session.query(Tag).filter(Tag.id == str(source_id)).first()
            target = session.query(Tag).filter(Tag.id == str(target_id)).first()

            if not source or not target:
                return None

            # Get book IDs from source tag
            source_book_ids = [bt.book_id for bt in source.book_tags]

            # Delete the source tag first (cascades to its book_tags)
            session.delete(source)
            session.flush()

            # Now add target tag to all source books
            for book_id in source_book_ids:
                # Check if book already has target tag
                existing = session.query(BookTag).filter(
                    BookTag.book_id == book_id,
                    BookTag.tag_id == str(target_id),
                ).first()
                if not existing:
                    new_book_tag = BookTag(
                        book_id=book_id,
                        tag_id=str(target_id),
                    )
                    session.add(new_book_tag)

            session.commit()
            session.refresh(target)

            return self._tag_to_response(target)

    def _tag_to_response(self, tag: Tag) -> TagResponse:
        """Convert tag model to response."""
        return TagResponse(
            id=UUID(tag.id),
            name=tag.name,
            color=TagColor(tag.color),
            icon=tag.icon,
            description=tag.description,
            parent_id=UUID(tag.parent_id) if tag.parent_id else None,
            book_count=tag.book_count,
            created_at=tag.created_at,
        )

    def _build_tag_hierarchy(self, tag: Tag, session) -> TagWithHierarchy:
        """Build hierarchical tag response."""
        children = [
            self._build_tag_hierarchy(child, session)
            for child in tag.children
        ]

        # Build full path
        path_parts = [tag.name]
        parent = tag.parent
        while parent:
            path_parts.insert(0, parent.name)
            parent = parent.parent

        return TagWithHierarchy(
            id=UUID(tag.id),
            name=tag.name,
            color=TagColor(tag.color),
            icon=tag.icon,
            description=tag.description,
            parent_id=UUID(tag.parent_id) if tag.parent_id else None,
            book_count=tag.book_count,
            created_at=tag.created_at,
            parent_name=tag.parent.name if tag.parent else None,
            children=children,
            full_path=" > ".join(path_parts),
        )

    # ========================================================================
    # Book Tagging
    # ========================================================================

    def tag_book(self, book_id: UUID, tag_id: UUID) -> Optional[BookTagResponse]:
        """Add a tag to a book.

        Args:
            book_id: Book UUID
            tag_id: Tag UUID

        Returns:
            Book tag response or None
        """
        with self.db.get_session() as session:
            # Verify book and tag exist
            book = session.query(Book).filter(Book.id == str(book_id)).first()
            tag = session.query(Tag).filter(Tag.id == str(tag_id)).first()

            if not book or not tag:
                return None

            # Check if already tagged
            existing = session.query(BookTag).filter(
                BookTag.book_id == str(book_id),
                BookTag.tag_id == str(tag_id),
            ).first()

            if existing:
                return self._book_tag_to_response(existing, tag)

            book_tag = BookTag(
                book_id=str(book_id),
                tag_id=str(tag_id),
            )
            session.add(book_tag)
            session.commit()
            session.refresh(book_tag)

            return self._book_tag_to_response(book_tag, tag)

    def untag_book(self, book_id: UUID, tag_id: UUID) -> bool:
        """Remove a tag from a book.

        Args:
            book_id: Book UUID
            tag_id: Tag UUID

        Returns:
            True if removed
        """
        with self.db.get_session() as session:
            book_tag = session.query(BookTag).filter(
                BookTag.book_id == str(book_id),
                BookTag.tag_id == str(tag_id),
            ).first()

            if not book_tag:
                return False

            session.delete(book_tag)
            session.commit()
            return True

    def get_book_tags(self, book_id: UUID) -> list[BookTagResponse]:
        """Get all tags for a book.

        Args:
            book_id: Book UUID

        Returns:
            List of book tag responses
        """
        with self.db.get_session() as session:
            book_tags = session.query(BookTag).filter(
                BookTag.book_id == str(book_id)
            ).all()

            results = []
            for bt in book_tags:
                tag = session.query(Tag).filter(Tag.id == bt.tag_id).first()
                if tag:
                    results.append(self._book_tag_to_response(bt, tag))

            return results

    def get_books_by_tag(
        self, tag_id: UUID, include_children: bool = False
    ) -> list[TaggedBookResponse]:
        """Get all books with a tag.

        Args:
            tag_id: Tag UUID
            include_children: Include books with child tags

        Returns:
            List of tagged book responses
        """
        with self.db.get_session() as session:
            tag_ids = [str(tag_id)]

            if include_children:
                # Get all descendant tag IDs
                tag_ids.extend(self._get_descendant_tag_ids(str(tag_id), session))

            book_tags = session.query(BookTag).filter(
                BookTag.tag_id.in_(tag_ids)
            ).all()

            # Group by book
            books_dict = {}
            for bt in book_tags:
                if bt.book_id not in books_dict:
                    book = session.query(Book).filter(Book.id == bt.book_id).first()
                    if book:
                        books_dict[bt.book_id] = {
                            "book": book,
                            "tags": []
                        }

                tag = session.query(Tag).filter(Tag.id == bt.tag_id).first()
                if tag and bt.book_id in books_dict:
                    books_dict[bt.book_id]["tags"].append(
                        self._book_tag_to_response(bt, tag)
                    )

            return [
                TaggedBookResponse(
                    book_id=UUID(data["book"].id),
                    book_title=data["book"].title,
                    book_author=data["book"].author,
                    tags=data["tags"],
                )
                for data in books_dict.values()
            ]

    def _get_descendant_tag_ids(self, tag_id: str, session) -> list[str]:
        """Get all descendant tag IDs recursively."""
        children = session.query(Tag).filter(Tag.parent_id == tag_id).all()
        ids = []
        for child in children:
            ids.append(child.id)
            ids.extend(self._get_descendant_tag_ids(child.id, session))
        return ids

    def _book_tag_to_response(self, book_tag: BookTag, tag: Tag) -> BookTagResponse:
        """Convert book tag to response."""
        return BookTagResponse(
            tag_id=UUID(tag.id),
            tag_name=tag.name,
            tag_color=TagColor(tag.color),
            tag_icon=tag.icon,
            added_at=book_tag.added_at,
        )

    # ========================================================================
    # Bulk Tag Operations
    # ========================================================================

    def bulk_tag_books(self, operation: BulkTagOperation) -> BulkTagResult:
        """Perform bulk tag operations.

        Args:
            operation: Bulk operation data

        Returns:
            Result of bulk operation
        """
        books_affected = set()
        tags_applied = 0
        tags_removed = 0
        errors = []

        with self.db.get_session() as session:
            for book_id in operation.book_ids:
                book = session.query(Book).filter(
                    Book.id == str(book_id)
                ).first()
                if not book:
                    errors.append(f"Book not found: {book_id}")
                    continue

                for tag_id in operation.tag_ids:
                    tag = session.query(Tag).filter(
                        Tag.id == str(tag_id)
                    ).first()
                    if not tag:
                        errors.append(f"Tag not found: {tag_id}")
                        continue

                    if operation.operation == "add":
                        existing = session.query(BookTag).filter(
                            BookTag.book_id == str(book_id),
                            BookTag.tag_id == str(tag_id),
                        ).first()
                        if not existing:
                            book_tag = BookTag(
                                book_id=str(book_id),
                                tag_id=str(tag_id),
                            )
                            session.add(book_tag)
                            tags_applied += 1
                            books_affected.add(str(book_id))

                    elif operation.operation == "remove":
                        book_tag = session.query(BookTag).filter(
                            BookTag.book_id == str(book_id),
                            BookTag.tag_id == str(tag_id),
                        ).first()
                        if book_tag:
                            session.delete(book_tag)
                            tags_removed += 1
                            books_affected.add(str(book_id))

            session.commit()

        return BulkTagResult(
            books_affected=len(books_affected),
            tags_applied=tags_applied,
            tags_removed=tags_removed,
            errors=errors,
        )

    # ========================================================================
    # Custom Field CRUD
    # ========================================================================

    def create_field(self, field_data: CustomFieldCreate) -> CustomFieldResponse:
        """Create a custom field.

        Args:
            field_data: Field creation data

        Returns:
            Created field response
        """
        with self.db.get_session() as session:
            # Check for duplicate name
            existing = session.query(CustomField).filter(
                func.lower(CustomField.name) == field_data.name.lower()
            ).first()
            if existing:
                return self._field_to_response(existing, session)

            # Get next position
            max_pos = session.query(func.max(CustomField.position)).scalar() or 0

            field = CustomField(
                name=field_data.name,
                field_type=field_data.field_type.value,
                description=field_data.description,
                is_required=field_data.is_required,
                default_value=field_data.default_value,
                min_value=field_data.min_value,
                max_value=field_data.max_value,
                position=max_pos + 1,
            )

            if field_data.options:
                field.set_options([opt.model_dump() for opt in field_data.options])

            session.add(field)
            session.commit()
            session.refresh(field)

            return self._field_to_response(field, session)

    def get_field(self, field_id: UUID) -> Optional[CustomFieldResponse]:
        """Get a custom field by ID.

        Args:
            field_id: Field UUID

        Returns:
            Field response or None
        """
        with self.db.get_session() as session:
            field = session.query(CustomField).filter(
                CustomField.id == str(field_id)
            ).first()
            if not field:
                return None
            return self._field_to_response(field, session)

    def get_all_fields(self) -> list[CustomFieldResponse]:
        """Get all custom fields.

        Returns:
            List of field responses
        """
        with self.db.get_session() as session:
            fields = session.query(CustomField).order_by(
                CustomField.position
            ).all()
            return [self._field_to_response(f, session) for f in fields]

    def update_field(
        self, field_id: UUID, update_data: CustomFieldUpdate
    ) -> Optional[CustomFieldResponse]:
        """Update a custom field.

        Args:
            field_id: Field UUID
            update_data: Update data

        Returns:
            Updated field response or None
        """
        with self.db.get_session() as session:
            field = session.query(CustomField).filter(
                CustomField.id == str(field_id)
            ).first()
            if not field:
                return None

            if update_data.name is not None:
                field.name = update_data.name
            if update_data.description is not None:
                field.description = update_data.description
            if update_data.is_required is not None:
                field.is_required = update_data.is_required
            if update_data.default_value is not None:
                field.default_value = update_data.default_value
            if update_data.options is not None:
                field.set_options([opt.model_dump() for opt in update_data.options])
            if update_data.min_value is not None:
                field.min_value = update_data.min_value
            if update_data.max_value is not None:
                field.max_value = update_data.max_value

            session.commit()
            session.refresh(field)

            return self._field_to_response(field, session)

    def delete_field(self, field_id: UUID) -> bool:
        """Delete a custom field.

        Args:
            field_id: Field UUID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            field = session.query(CustomField).filter(
                CustomField.id == str(field_id)
            ).first()
            if not field:
                return False

            session.delete(field)
            session.commit()
            return True

    def _field_to_response(
        self, field: CustomField, session
    ) -> CustomFieldResponse:
        """Convert field model to response."""
        usage_count = session.query(CustomFieldValue).filter(
            CustomFieldValue.field_id == field.id
        ).count()

        options = None
        if field.options:
            raw_options = field.get_options()
            options = [
                SelectOption(
                    value=opt.get("value", ""),
                    label=opt.get("label", ""),
                    color=TagColor(opt["color"]) if opt.get("color") else None,
                )
                for opt in raw_options
            ]

        return CustomFieldResponse(
            id=UUID(field.id),
            name=field.name,
            field_type=FieldType(field.field_type),
            description=field.description,
            is_required=field.is_required,
            default_value=field.default_value,
            options=options,
            min_value=field.min_value,
            max_value=field.max_value,
            usage_count=usage_count,
            created_at=field.created_at,
        )

    # ========================================================================
    # Field Values
    # ========================================================================

    def set_field_value(
        self, book_id: UUID, field_id: UUID, value: str
    ) -> Optional[FieldValueResponse]:
        """Set a custom field value for a book.

        Args:
            book_id: Book UUID
            field_id: Field UUID
            value: Value to set

        Returns:
            Field value response or None
        """
        with self.db.get_session() as session:
            book = session.query(Book).filter(Book.id == str(book_id)).first()
            field = session.query(CustomField).filter(
                CustomField.id == str(field_id)
            ).first()

            if not book or not field:
                return None

            # Validate value based on field type
            if not self._validate_field_value(field, value):
                return None

            # Check for existing value
            existing = session.query(CustomFieldValue).filter(
                CustomFieldValue.book_id == str(book_id),
                CustomFieldValue.field_id == str(field_id),
            ).first()

            if existing:
                existing.value = value
                existing.updated_at = datetime.now().isoformat()
            else:
                existing = CustomFieldValue(
                    book_id=str(book_id),
                    field_id=str(field_id),
                    value=value,
                )
                session.add(existing)

            session.commit()
            session.refresh(existing)

            return self._field_value_to_response(existing, field)

    def get_field_value(
        self, book_id: UUID, field_id: UUID
    ) -> Optional[FieldValueResponse]:
        """Get a field value for a book.

        Args:
            book_id: Book UUID
            field_id: Field UUID

        Returns:
            Field value response or None
        """
        with self.db.get_session() as session:
            value = session.query(CustomFieldValue).filter(
                CustomFieldValue.book_id == str(book_id),
                CustomFieldValue.field_id == str(field_id),
            ).first()

            if not value:
                return None

            field = session.query(CustomField).filter(
                CustomField.id == str(field_id)
            ).first()

            return self._field_value_to_response(value, field)

    def get_book_fields(self, book_id: UUID) -> Optional[BookFieldsResponse]:
        """Get all custom field values for a book.

        Args:
            book_id: Book UUID

        Returns:
            Book fields response or None
        """
        with self.db.get_session() as session:
            book = session.query(Book).filter(Book.id == str(book_id)).first()
            if not book:
                return None

            values = session.query(CustomFieldValue).filter(
                CustomFieldValue.book_id == str(book_id)
            ).all()

            field_responses = []
            for value in values:
                field = session.query(CustomField).filter(
                    CustomField.id == value.field_id
                ).first()
                if field:
                    field_responses.append(
                        self._field_value_to_response(value, field)
                    )

            return BookFieldsResponse(
                book_id=UUID(book.id),
                book_title=book.title,
                fields=field_responses,
            )

    def delete_field_value(self, book_id: UUID, field_id: UUID) -> bool:
        """Delete a field value for a book.

        Args:
            book_id: Book UUID
            field_id: Field UUID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            value = session.query(CustomFieldValue).filter(
                CustomFieldValue.book_id == str(book_id),
                CustomFieldValue.field_id == str(field_id),
            ).first()

            if not value:
                return False

            session.delete(value)
            session.commit()
            return True

    def _validate_field_value(self, field: CustomField, value: str) -> bool:
        """Validate a field value based on field type."""
        field_type = FieldType(field.field_type)

        if field_type == FieldType.NUMBER or field_type == FieldType.RATING:
            try:
                num = float(value)
                if field.min_value is not None and num < field.min_value:
                    return False
                if field.max_value is not None and num > field.max_value:
                    return False
            except ValueError:
                return False

        elif field_type == FieldType.BOOLEAN:
            if value.lower() not in ("true", "false", "1", "0", "yes", "no"):
                return False

        elif field_type == FieldType.DATE:
            try:
                date.fromisoformat(value)
            except ValueError:
                return False

        elif field_type == FieldType.SELECT:
            options = field.get_options()
            valid_values = [opt.get("value") for opt in options]
            if value not in valid_values:
                return False

        elif field_type == FieldType.MULTI_SELECT:
            options = field.get_options()
            valid_values = [opt.get("value") for opt in options]
            try:
                selected = json.loads(value)
                if not all(v in valid_values for v in selected):
                    return False
            except json.JSONDecodeError:
                return False

        return True

    def _field_value_to_response(
        self, value: CustomFieldValue, field: CustomField
    ) -> FieldValueResponse:
        """Convert field value to response."""
        display_value = value.value
        field_type = FieldType(field.field_type)

        # Format display value based on type
        if field_type == FieldType.BOOLEAN:
            display_value = "Yes" if value.value.lower() in ("true", "1", "yes") else "No"
        elif field_type == FieldType.RATING:
            try:
                rating = float(value.value)
                display_value = f"{rating:.1f}/5"
            except ValueError:
                pass
        elif field_type == FieldType.SELECT:
            options = field.get_options()
            for opt in options:
                if opt.get("value") == value.value:
                    display_value = opt.get("label", value.value)
                    break
        elif field_type == FieldType.MULTI_SELECT:
            try:
                selected = json.loads(value.value)
                options = field.get_options()
                labels = []
                for opt in options:
                    if opt.get("value") in selected:
                        labels.append(opt.get("label", opt.get("value")))
                display_value = ", ".join(labels)
            except json.JSONDecodeError:
                pass

        return FieldValueResponse(
            field_id=UUID(field.id),
            field_name=field.name,
            field_type=field_type,
            value=value.value,
            display_value=display_value,
        )

    # ========================================================================
    # Tag Analytics
    # ========================================================================

    def get_tag_stats(self, tag_id: UUID) -> Optional[TagStats]:
        """Get statistics for a tag.

        Args:
            tag_id: Tag UUID

        Returns:
            Tag statistics or None
        """
        with self.db.get_session() as session:
            tag = session.query(Tag).filter(Tag.id == str(tag_id)).first()
            if not tag:
                return None

            book_ids = [bt.book_id for bt in tag.book_tags]
            if not book_ids:
                return TagStats(
                    tag_id=UUID(tag.id),
                    tag_name=tag.name,
                    tag_color=TagColor(tag.color),
                    total_books=0,
                    completed_books=0,
                    average_rating=None,
                    total_pages=0,
                )

            books = session.query(Book).filter(Book.id.in_(book_ids)).all()

            completed = [b for b in books if b.status == BookStatus.COMPLETED.value]
            rated = [b for b in books if b.rating]
            avg_rating = sum(b.rating for b in rated) / len(rated) if rated else None
            total_pages = sum(b.page_count or 0 for b in books)

            return TagStats(
                tag_id=UUID(tag.id),
                tag_name=tag.name,
                tag_color=TagColor(tag.color),
                total_books=len(books),
                completed_books=len(completed),
                average_rating=avg_rating,
                total_pages=total_pages,
            )

    def get_tag_cloud(self) -> TagCloud:
        """Get tag cloud data.

        Returns:
            Tag cloud data
        """
        with self.db.get_session() as session:
            tags = session.query(Tag).all()

            tag_stats = []
            most_used = None
            least_used = None
            max_count = 0
            min_count = float("inf")

            for tag in tags:
                stats = self.get_tag_stats(UUID(tag.id))
                if stats:
                    tag_stats.append(stats)
                    if stats.total_books > max_count:
                        max_count = stats.total_books
                        most_used = stats.tag_name
                    if stats.total_books < min_count and stats.total_books > 0:
                        min_count = stats.total_books
                        least_used = stats.tag_name

            return TagCloud(
                tags=tag_stats,
                total_tags=len(tags),
                most_used_tag=most_used,
                least_used_tag=least_used,
            )

    def get_field_stats(self, field_id: UUID) -> Optional[FieldStats]:
        """Get statistics for a custom field.

        Args:
            field_id: Field UUID

        Returns:
            Field statistics or None
        """
        with self.db.get_session() as session:
            field = session.query(CustomField).filter(
                CustomField.id == str(field_id)
            ).first()
            if not field:
                return None

            values = session.query(CustomFieldValue).filter(
                CustomFieldValue.field_id == str(field_id)
            ).all()

            unique_values = set(v.value for v in values)
            value_counts = {}
            for v in values:
                value_counts[v.value] = value_counts.get(v.value, 0) + 1

            most_common = None
            if value_counts:
                most_common = max(value_counts, key=value_counts.get)

            return FieldStats(
                field_id=UUID(field.id),
                field_name=field.name,
                field_type=FieldType(field.field_type),
                books_with_value=len(values),
                unique_values=len(unique_values),
                most_common_value=most_common,
            )

    # ========================================================================
    # Tag Suggestions
    # ========================================================================

    def suggest_tags(self, book_id: UUID) -> list[TagSuggestion]:
        """Suggest tags for a book based on its content.

        Args:
            book_id: Book UUID

        Returns:
            List of tag suggestions
        """
        with self.db.get_session() as session:
            book = session.query(Book).filter(Book.id == str(book_id)).first()
            if not book:
                return []

            suggestions = []
            existing_tag_ids = set(
                bt.tag_id for bt in session.query(BookTag).filter(
                    BookTag.book_id == str(book_id)
                ).all()
            )

            # Suggest based on genres
            if book.genres:
                try:
                    genres = json.loads(book.genres)
                    for genre in genres:
                        tag = session.query(Tag).filter(
                            func.lower(Tag.name) == genre.lower()
                        ).first()
                        if tag and tag.id not in existing_tag_ids:
                            suggestions.append(TagSuggestion(
                                tag_name=tag.name,
                                confidence=0.9,
                                reason=f"Matches book genre: {genre}",
                                existing_tag_id=UUID(tag.id),
                            ))
                        elif not tag:
                            suggestions.append(TagSuggestion(
                                tag_name=genre,
                                confidence=0.8,
                                reason=f"Based on book genre",
                                existing_tag_id=None,
                            ))
                except json.JSONDecodeError:
                    pass

            # Suggest based on author (if author has tagged books)
            if book.author:
                author_books = session.query(Book).filter(
                    Book.author == book.author,
                    Book.id != str(book_id),
                ).all()

                tag_counts = {}
                for ab in author_books:
                    for bt in session.query(BookTag).filter(
                        BookTag.book_id == ab.id
                    ).all():
                        if bt.tag_id not in existing_tag_ids:
                            tag_counts[bt.tag_id] = tag_counts.get(bt.tag_id, 0) + 1

                for tag_id, count in sorted(
                    tag_counts.items(), key=lambda x: x[1], reverse=True
                )[:3]:
                    tag = session.query(Tag).filter(Tag.id == tag_id).first()
                    if tag:
                        suggestions.append(TagSuggestion(
                            tag_name=tag.name,
                            confidence=min(0.7, count * 0.2),
                            reason=f"Common for author {book.author}",
                            existing_tag_id=UUID(tag.id),
                        ))

            # Remove duplicates and sort by confidence
            seen = set()
            unique_suggestions = []
            for s in sorted(suggestions, key=lambda x: x.confidence, reverse=True):
                if s.tag_name.lower() not in seen:
                    seen.add(s.tag_name.lower())
                    unique_suggestions.append(s)

            return unique_suggestions[:5]
