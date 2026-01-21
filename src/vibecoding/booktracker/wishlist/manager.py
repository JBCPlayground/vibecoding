"""Manager for wishlist operations."""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func, desc, asc
from sqlalchemy.orm import Session

from ..db.sqlite import Database
from .models import WishlistItem
from .schemas import (
    WishlistItemCreate,
    WishlistItemUpdate,
    WishlistItemResponse,
    WishlistSummary,
    WishlistStats,
    NextUpRecommendation,
    WishlistByPriority,
    Priority,
    WishlistSource,
)


class WishlistManager:
    """Manager for wishlist (TBR) operations."""

    def __init__(self, db: Database):
        """Initialize the wishlist manager.

        Args:
            db: Database instance
        """
        self.db = db

    def add_item(self, item: WishlistItemCreate) -> WishlistItemResponse:
        """Add a new item to the wishlist.

        Args:
            item: Item data to create

        Returns:
            Created item response
        """
        with self.db.get_session() as session:
            # Get the next position for this priority
            max_pos_result = session.query(func.max(WishlistItem.position)).filter(
                WishlistItem.priority == item.priority.value
            ).scalar()
            max_pos = max_pos_result if max_pos_result is not None else -1

            wishlist_item = WishlistItem(
                title=item.title,
                author=item.author,
                isbn=item.isbn,
                book_id=str(item.book_id) if item.book_id else None,
                priority=item.priority.value,
                position=max_pos + 1,
                source=item.source.value if item.source else None,
                recommended_by=item.recommended_by,
                recommendation_url=item.recommendation_url,
                reason=item.reason,
                estimated_pages=item.estimated_pages,
                estimated_hours=item.estimated_hours,
                genre=item.genre,
                target_date=item.target_date.isoformat() if item.target_date else None,
                is_available=item.is_available,
                is_on_hold=item.is_on_hold,
                tags=",".join(item.tags) if item.tags else None,
                notes=item.notes,
            )

            session.add(wishlist_item)
            session.flush()

            return self._to_response(wishlist_item)

    def get_item(self, item_id: UUID) -> Optional[WishlistItemResponse]:
        """Get a wishlist item by ID.

        Args:
            item_id: Item UUID

        Returns:
            Item response or None if not found
        """
        with self.db.get_session() as session:
            item = session.query(WishlistItem).filter(
                WishlistItem.id == str(item_id)
            ).first()

            if not item:
                return None

            return self._to_response(item)

    def update_item(
        self, item_id: UUID, updates: WishlistItemUpdate
    ) -> Optional[WishlistItemResponse]:
        """Update a wishlist item.

        Args:
            item_id: Item UUID
            updates: Fields to update

        Returns:
            Updated item response or None if not found
        """
        with self.db.get_session() as session:
            item = session.query(WishlistItem).filter(
                WishlistItem.id == str(item_id)
            ).first()

            if not item:
                return None

            # Apply updates
            update_data = updates.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if field == "priority" and value is not None:
                    setattr(item, field, value.value if hasattr(value, 'value') else value)
                elif field == "source" and value is not None:
                    setattr(item, field, value.value if hasattr(value, 'value') else value)
                elif field == "target_date" and value is not None:
                    setattr(item, field, value.isoformat() if hasattr(value, 'isoformat') else value)
                elif field == "tags" and value is not None:
                    setattr(item, field, ",".join(value) if isinstance(value, list) else value)
                elif field == "book_id" and value is not None:
                    setattr(item, field, str(value))
                else:
                    setattr(item, field, value)

            session.flush()

            return self._to_response(item)

    def delete_item(self, item_id: UUID) -> bool:
        """Delete a wishlist item.

        Args:
            item_id: Item UUID

        Returns:
            True if deleted, False if not found
        """
        with self.db.get_session() as session:
            item = session.query(WishlistItem).filter(
                WishlistItem.id == str(item_id)
            ).first()

            if not item:
                return False

            session.delete(item)
            return True

    def list_items(
        self,
        priority: Optional[Priority] = None,
        source: Optional[WishlistSource] = None,
        is_available: Optional[bool] = None,
        is_on_hold: Optional[bool] = None,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WishlistSummary]:
        """List wishlist items with optional filters.

        Args:
            priority: Filter by priority
            source: Filter by source
            is_available: Filter by availability
            is_on_hold: Filter by hold status
            search: Search in title/author
            tag: Filter by tag
            limit: Max items to return
            offset: Number of items to skip

        Returns:
            List of item summaries
        """
        with self.db.get_session() as session:
            query = session.query(WishlistItem)

            if priority is not None:
                query = query.filter(WishlistItem.priority == priority.value)

            if source is not None:
                query = query.filter(WishlistItem.source == source.value)

            if is_available is not None:
                query = query.filter(WishlistItem.is_available == is_available)

            if is_on_hold is not None:
                query = query.filter(WishlistItem.is_on_hold == is_on_hold)

            if search:
                search_pattern = f"%{search}%"
                query = query.filter(
                    (WishlistItem.title.ilike(search_pattern)) |
                    (WishlistItem.author.ilike(search_pattern))
                )

            if tag:
                query = query.filter(WishlistItem.tags.ilike(f"%{tag}%"))

            # Order by priority (ascending - 1 is highest) then position
            query = query.order_by(
                asc(WishlistItem.priority),
                asc(WishlistItem.position),
            )

            items = query.offset(offset).limit(limit).all()

            return [self._to_summary(item) for item in items]

    def get_by_priority(self) -> list[WishlistByPriority]:
        """Get items grouped by priority.

        Returns:
            List of items grouped by priority
        """
        with self.db.get_session() as session:
            result = []

            for priority in Priority:
                items = session.query(WishlistItem).filter(
                    WishlistItem.priority == priority.value
                ).order_by(asc(WishlistItem.position)).all()

                if items:
                    result.append(WishlistByPriority(
                        priority=priority,
                        priority_display=self._priority_display(priority.value),
                        items=[self._to_summary(item) for item in items],
                        count=len(items),
                    ))

            return result

    def reorder_item(self, item_id: UUID, new_position: int) -> Optional[WishlistItemResponse]:
        """Move an item to a new position within its priority.

        Args:
            item_id: Item UUID
            new_position: New position (0-indexed)

        Returns:
            Updated item or None if not found
        """
        with self.db.get_session() as session:
            item = session.query(WishlistItem).filter(
                WishlistItem.id == str(item_id)
            ).first()

            if not item:
                return None

            old_position = item.position
            priority = item.priority

            if new_position == old_position:
                return self._to_response(item)

            # Get all items in this priority
            items = session.query(WishlistItem).filter(
                WishlistItem.priority == priority,
                WishlistItem.id != str(item_id),
            ).order_by(asc(WishlistItem.position)).all()

            # Reposition items
            if new_position > old_position:
                # Moving down - shift items up
                for other in items:
                    if old_position < other.position <= new_position:
                        other.position -= 1
            else:
                # Moving up - shift items down
                for other in items:
                    if new_position <= other.position < old_position:
                        other.position += 1

            item.position = new_position
            session.flush()

            return self._to_response(item)

    def change_priority(
        self, item_id: UUID, new_priority: Priority
    ) -> Optional[WishlistItemResponse]:
        """Change an item's priority.

        Args:
            item_id: Item UUID
            new_priority: New priority level

        Returns:
            Updated item or None if not found
        """
        with self.db.get_session() as session:
            item = session.query(WishlistItem).filter(
                WishlistItem.id == str(item_id)
            ).first()

            if not item:
                return None

            if item.priority == new_priority.value:
                return self._to_response(item)

            old_priority = item.priority

            # Remove from old priority - shift items up
            items_in_old = session.query(WishlistItem).filter(
                WishlistItem.priority == old_priority,
                WishlistItem.position > item.position,
            ).all()
            for other in items_in_old:
                other.position -= 1

            # Get max position in new priority
            max_pos_result = session.query(func.max(WishlistItem.position)).filter(
                WishlistItem.priority == new_priority.value
            ).scalar()
            max_pos = max_pos_result if max_pos_result is not None else -1

            # Update item
            item.priority = new_priority.value
            item.position = max_pos + 1

            session.flush()

            return self._to_response(item)

    def mark_available(self, item_id: UUID, available: bool = True) -> Optional[WishlistItemResponse]:
        """Mark an item as available (owned/accessible).

        Args:
            item_id: Item UUID
            available: Availability status

        Returns:
            Updated item or None if not found
        """
        with self.db.get_session() as session:
            item = session.query(WishlistItem).filter(
                WishlistItem.id == str(item_id)
            ).first()

            if not item:
                return None

            item.is_available = available
            session.flush()

            return self._to_response(item)

    def mark_on_hold(self, item_id: UUID, on_hold: bool = True) -> Optional[WishlistItemResponse]:
        """Mark an item as on hold at library.

        Args:
            item_id: Item UUID
            on_hold: Hold status

        Returns:
            Updated item or None if not found
        """
        with self.db.get_session() as session:
            item = session.query(WishlistItem).filter(
                WishlistItem.id == str(item_id)
            ).first()

            if not item:
                return None

            item.is_on_hold = on_hold
            session.flush()

            return self._to_response(item)

    def link_to_book(self, item_id: UUID, book_id: UUID) -> Optional[WishlistItemResponse]:
        """Link a wishlist item to a book in the library.

        Args:
            item_id: Wishlist item UUID
            book_id: Book UUID in library

        Returns:
            Updated item or None if not found
        """
        with self.db.get_session() as session:
            item = session.query(WishlistItem).filter(
                WishlistItem.id == str(item_id)
            ).first()

            if not item:
                return None

            item.book_id = str(book_id)
            session.flush()

            return self._to_response(item)

    def get_stats(self) -> WishlistStats:
        """Get wishlist statistics.

        Returns:
            Statistics about the wishlist
        """
        with self.db.get_session() as session:
            items = session.query(WishlistItem).all()

            if not items:
                return WishlistStats(
                    total_items=0,
                    by_priority={},
                    by_source={},
                    available_count=0,
                    on_hold_count=0,
                    in_library_count=0,
                    total_estimated_pages=0,
                    total_estimated_hours=0.0,
                    oldest_item_date=None,
                    items_with_target_date=0,
                    overdue_targets=0,
                )

            # Count by priority
            by_priority = {}
            for p in Priority:
                count = sum(1 for i in items if i.priority == p.value)
                if count > 0:
                    by_priority[self._priority_display(p.value)] = count

            # Count by source
            by_source = {}
            for item in items:
                if item.source:
                    by_source[item.source] = by_source.get(item.source, 0) + 1

            # Other stats
            available_count = sum(1 for i in items if i.is_available)
            on_hold_count = sum(1 for i in items if i.is_on_hold)
            in_library_count = sum(1 for i in items if i.book_id is not None)

            total_pages = sum(i.estimated_pages or 0 for i in items)
            total_hours = sum(i.estimated_hours or 0.0 for i in items)

            # Date stats
            dates = [i.date_added for i in items]
            oldest_date = date.fromisoformat(min(dates)) if dates else None

            items_with_target = sum(1 for i in items if i.target_date)
            today = date.today()
            overdue = sum(
                1 for i in items
                if i.target_date and date.fromisoformat(i.target_date) < today
            )

            return WishlistStats(
                total_items=len(items),
                by_priority=by_priority,
                by_source=by_source,
                available_count=available_count,
                on_hold_count=on_hold_count,
                in_library_count=in_library_count,
                total_estimated_pages=total_pages,
                total_estimated_hours=total_hours,
                oldest_item_date=oldest_date,
                items_with_target_date=items_with_target,
                overdue_targets=overdue,
            )

    def get_next_up(self, count: int = 5) -> list[NextUpRecommendation]:
        """Get recommendations for what to read next.

        Prioritizes: available items, high priority, target dates.

        Args:
            count: Number of recommendations

        Returns:
            List of recommended items with reasons
        """
        with self.db.get_session() as session:
            recommendations = []

            # First: Available high-priority items
            available_high = session.query(WishlistItem).filter(
                WishlistItem.is_available == True,  # noqa: E712
                WishlistItem.priority <= 2,  # Must Read or High
            ).order_by(
                asc(WishlistItem.priority),
                asc(WishlistItem.position),
            ).limit(count).all()

            for item in available_high:
                recommendations.append(NextUpRecommendation(
                    item=self._to_summary(item),
                    reason="Available and high priority",
                ))

            if len(recommendations) >= count:
                return recommendations[:count]

            # Second: Items with upcoming target dates
            today = date.today()
            target_soon = session.query(WishlistItem).filter(
                WishlistItem.target_date != None,  # noqa: E711
                WishlistItem.id.notin_([r.item.id for r in recommendations]),
            ).order_by(asc(WishlistItem.target_date)).limit(count).all()

            for item in target_soon:
                target = date.fromisoformat(item.target_date)
                days_until = (target - today).days
                if days_until < 0:
                    reason = f"Overdue by {abs(days_until)} days"
                elif days_until == 0:
                    reason = "Target date is today"
                else:
                    reason = f"Target date in {days_until} days"

                recommendations.append(NextUpRecommendation(
                    item=self._to_summary(item),
                    reason=reason,
                ))

            if len(recommendations) >= count:
                return recommendations[:count]

            # Third: Top of each priority
            seen_ids = {str(r.item.id) for r in recommendations}
            for priority in Priority:
                if len(recommendations) >= count:
                    break

                top_item = session.query(WishlistItem).filter(
                    WishlistItem.priority == priority.value,
                    WishlistItem.id.notin_(seen_ids),
                ).order_by(asc(WishlistItem.position)).first()

                if top_item:
                    recommendations.append(NextUpRecommendation(
                        item=self._to_summary(top_item),
                        reason=f"Top of {self._priority_display(priority.value)} priority",
                    ))
                    seen_ids.add(top_item.id)

            return recommendations[:count]

    def _to_response(self, item: WishlistItem) -> WishlistItemResponse:
        """Convert model to response schema."""
        return WishlistItemResponse(
            id=UUID(item.id),
            title=item.title,
            author=item.author,
            isbn=item.isbn,
            book_id=UUID(item.book_id) if item.book_id else None,
            priority=Priority(item.priority),
            priority_display=item.priority_display,
            position=item.position,
            source=WishlistSource(item.source) if item.source else None,
            recommended_by=item.recommended_by,
            recommendation_url=item.recommendation_url,
            reason=item.reason,
            estimated_pages=item.estimated_pages,
            estimated_hours=item.estimated_hours,
            genre=item.genre,
            date_added=date.fromisoformat(item.date_added),
            target_date=date.fromisoformat(item.target_date) if item.target_date else None,
            is_available=item.is_available,
            is_on_hold=item.is_on_hold,
            is_in_library=item.is_in_library,
            tags=item.tag_list,
            notes=item.notes,
            display_title=item.display_title,
            created_at=datetime.fromisoformat(item.created_at),
            updated_at=datetime.fromisoformat(item.updated_at),
        )

    def _to_summary(self, item: WishlistItem) -> WishlistSummary:
        """Convert model to summary schema."""
        return WishlistSummary(
            id=UUID(item.id),
            title=item.title,
            author=item.author,
            priority=Priority(item.priority),
            priority_display=item.priority_display,
            position=item.position,
            source=WishlistSource(item.source) if item.source else None,
            date_added=date.fromisoformat(item.date_added),
            is_available=item.is_available,
            is_in_library=item.is_in_library,
        )

    def _priority_display(self, priority: int) -> str:
        """Get display string for priority value."""
        priorities = {
            1: "Must Read",
            2: "High",
            3: "Medium",
            4: "Low",
            5: "Someday",
        }
        return priorities.get(priority, "Unknown")
