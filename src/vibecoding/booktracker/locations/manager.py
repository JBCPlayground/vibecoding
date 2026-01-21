"""Manager for reading locations operations."""

from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select

from ..db.models import Book
from ..db.sqlite import Database, get_db
from .models import LocationSession, ReadingLocation
from .schemas import (
    LocationBreakdown,
    LocationCreate,
    LocationResponse,
    LocationSessionCreate,
    LocationSessionResponse,
    LocationStats,
    LocationSummary,
    LocationType,
    LocationUpdate,
)


class LocationManager:
    """Manages reading location operations."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize location manager.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    # -------------------------------------------------------------------------
    # Location CRUD
    # -------------------------------------------------------------------------

    def create_location(self, data: LocationCreate) -> ReadingLocation:
        """Create a new reading location.

        Args:
            data: Location creation data

        Returns:
            Created location
        """
        with self.db.get_session() as session:
            location = ReadingLocation(
                name=data.name,
                location_type=data.location_type.value,
                description=data.description,
                address=data.address,
                icon=data.icon,
                is_favorite=data.is_favorite,
            )
            session.add(location)
            session.commit()
            session.refresh(location)
            session.expunge(location)
            return location

    def get_location(self, location_id: str) -> Optional[ReadingLocation]:
        """Get a location by ID.

        Args:
            location_id: Location ID

        Returns:
            Location or None
        """
        with self.db.get_session() as session:
            location = session.execute(
                select(ReadingLocation).where(ReadingLocation.id == location_id)
            ).scalar_one_or_none()
            if location:
                # Eagerly load sessions
                _ = location.sessions
                session.expunge(location)
            return location

    def get_location_by_name(self, name: str) -> Optional[ReadingLocation]:
        """Get a location by name.

        Args:
            name: Location name

        Returns:
            Location or None
        """
        with self.db.get_session() as session:
            location = session.execute(
                select(ReadingLocation).where(
                    func.lower(ReadingLocation.name) == name.lower()
                )
            ).scalar_one_or_none()
            if location:
                _ = location.sessions
                session.expunge(location)
            return location

    def list_locations(
        self,
        location_type: Optional[LocationType] = None,
        favorites_only: bool = False,
        order_by: str = "name",
    ) -> list[ReadingLocation]:
        """List all locations.

        Args:
            location_type: Filter by type
            favorites_only: Only return favorites
            order_by: Field to order by

        Returns:
            List of locations
        """
        with self.db.get_session() as session:
            stmt = select(ReadingLocation)

            if location_type:
                stmt = stmt.where(ReadingLocation.location_type == location_type.value)
            if favorites_only:
                stmt = stmt.where(ReadingLocation.is_favorite == True)  # noqa: E712

            # Apply ordering
            if order_by == "name":
                stmt = stmt.order_by(ReadingLocation.name.asc())
            elif order_by == "created_at":
                stmt = stmt.order_by(ReadingLocation.created_at.desc())
            elif order_by == "updated_at":
                stmt = stmt.order_by(ReadingLocation.updated_at.desc())

            locations = session.execute(stmt).scalars().all()
            for loc in locations:
                _ = loc.sessions
                session.expunge(loc)
            return list(locations)

    def update_location(
        self, location_id: str, data: LocationUpdate
    ) -> Optional[ReadingLocation]:
        """Update a location.

        Args:
            location_id: Location ID
            data: Update data

        Returns:
            Updated location or None
        """
        with self.db.get_session() as session:
            location = session.execute(
                select(ReadingLocation).where(ReadingLocation.id == location_id)
            ).scalar_one_or_none()

            if not location:
                return None

            update_data = data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if field == "location_type" and value is not None:
                    location.location_type = value.value
                elif hasattr(location, field):
                    setattr(location, field, value)

            location.updated_at = datetime.now(timezone.utc).isoformat()
            session.commit()
            session.refresh(location)
            _ = location.sessions
            session.expunge(location)
            return location

    def delete_location(self, location_id: str) -> bool:
        """Delete a location.

        Args:
            location_id: Location ID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            location = session.execute(
                select(ReadingLocation).where(ReadingLocation.id == location_id)
            ).scalar_one_or_none()

            if not location:
                return False

            session.delete(location)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Session Logging
    # -------------------------------------------------------------------------

    def log_session(self, data: LocationSessionCreate) -> LocationSession:
        """Log a reading session at a location.

        Args:
            data: Session data

        Returns:
            Created session
        """
        with self.db.get_session() as session:
            # Verify location exists
            location = session.execute(
                select(ReadingLocation).where(ReadingLocation.id == data.location_id)
            ).scalar_one_or_none()
            if not location:
                raise ValueError("Location not found")

            # Verify book if provided
            if data.book_id:
                book = session.execute(
                    select(Book).where(Book.id == data.book_id)
                ).scalar_one_or_none()
                if not book:
                    raise ValueError("Book not found")

            loc_session = LocationSession(
                location_id=data.location_id,
                book_id=data.book_id,
                minutes_read=data.minutes_read,
                pages_read=data.pages_read,
                notes=data.notes,
            )

            if data.session_date:
                loc_session.session_date = data.session_date.isoformat()

            session.add(loc_session)
            session.commit()
            session.refresh(loc_session)
            session.expunge(loc_session)
            return loc_session

    def get_session(self, session_id: str) -> Optional[LocationSession]:
        """Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session or None
        """
        with self.db.get_session() as session:
            loc_session = session.execute(
                select(LocationSession).where(LocationSession.id == session_id)
            ).scalar_one_or_none()
            if loc_session:
                session.expunge(loc_session)
            return loc_session

    def list_sessions(
        self,
        location_id: Optional[str] = None,
        book_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[LocationSessionResponse]:
        """List location sessions.

        Args:
            location_id: Filter by location
            book_id: Filter by book
            limit: Maximum sessions to return

        Returns:
            List of session responses
        """
        with self.db.get_session() as session:
            stmt = select(LocationSession)

            if location_id:
                stmt = stmt.where(LocationSession.location_id == location_id)
            if book_id:
                stmt = stmt.where(LocationSession.book_id == book_id)

            stmt = stmt.order_by(LocationSession.session_date.desc()).limit(limit)

            sessions_list = session.execute(stmt).scalars().all()
            results = []

            for loc_session in sessions_list:
                location = session.execute(
                    select(ReadingLocation).where(
                        ReadingLocation.id == loc_session.location_id
                    )
                ).scalar_one_or_none()

                book = None
                if loc_session.book_id:
                    book = session.execute(
                        select(Book).where(Book.id == loc_session.book_id)
                    ).scalar_one_or_none()

                results.append(
                    LocationSessionResponse(
                        id=loc_session.id,
                        location_id=loc_session.location_id,
                        location_name=location.name if location else "Unknown",
                        book_id=loc_session.book_id,
                        book_title=book.title if book else None,
                        minutes_read=loc_session.minutes_read,
                        pages_read=loc_session.pages_read,
                        notes=loc_session.notes,
                        session_date=datetime.fromisoformat(loc_session.session_date),
                        created_at=datetime.fromisoformat(loc_session.created_at),
                    )
                )

            return results

    def delete_session(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            loc_session = session.execute(
                select(LocationSession).where(LocationSession.id == session_id)
            ).scalar_one_or_none()

            if not loc_session:
                return False

            session.delete(loc_session)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_stats(self) -> LocationStats:
        """Get location statistics.

        Returns:
            LocationStats with counts and breakdown
        """
        with self.db.get_session() as session:
            # Count locations
            total_locations = session.execute(
                select(func.count()).select_from(ReadingLocation)
            ).scalar() or 0

            # Count sessions
            total_sessions = session.execute(
                select(func.count()).select_from(LocationSession)
            ).scalar() or 0

            # Total reading
            total_minutes = session.execute(
                select(func.sum(LocationSession.minutes_read))
            ).scalar() or 0

            total_pages = session.execute(
                select(func.sum(LocationSession.pages_read))
            ).scalar() or 0

            # Get all locations for breakdown
            locations = session.execute(select(ReadingLocation)).scalars().all()

            # Calculate favorites and most used
            favorite_location = None
            most_used_location = None
            max_minutes = 0

            minutes_by_type: dict[str, int] = {}
            sessions_by_type: dict[str, int] = {}

            for loc in locations:
                # Load sessions
                _ = loc.sessions

                if loc.is_favorite and favorite_location is None:
                    favorite_location = loc.name

                loc_minutes = loc.total_minutes
                if loc_minutes > max_minutes:
                    max_minutes = loc_minutes
                    most_used_location = loc.name

                # Aggregate by type
                loc_type = loc.location_type
                minutes_by_type[loc_type] = minutes_by_type.get(loc_type, 0) + loc_minutes
                sessions_by_type[loc_type] = (
                    sessions_by_type.get(loc_type, 0) + loc.total_sessions
                )

            # Build top locations data before leaving session
            top_locs_data = []
            for loc in sorted(locations, key=lambda x: x.total_minutes, reverse=True)[:5]:
                top_locs_data.append({
                    "id": loc.id,
                    "name": loc.name,
                    "location_type": loc.location_type,
                    "icon": loc.icon,
                    "total_sessions": loc.total_sessions,
                    "total_minutes": loc.total_minutes,
                })

            # Reading by hour
            reading_by_hour: dict[int, int] = {h: 0 for h in range(24)}
            all_sessions = session.execute(select(LocationSession)).scalars().all()
            for s in all_sessions:
                hour = s.session_hour
                reading_by_hour[hour] += s.minutes_read

        return LocationStats(
            total_locations=total_locations,
            total_sessions=total_sessions,
            total_minutes=total_minutes,
            total_pages=total_pages,
            favorite_location=favorite_location,
            most_used_location=most_used_location,
            minutes_by_type=minutes_by_type,
            sessions_by_type=sessions_by_type,
            top_locations=[
                LocationSummary(
                    id=loc_data["id"],
                    name=loc_data["name"],
                    location_type=LocationType(loc_data["location_type"]),
                    icon=loc_data["icon"],
                    total_sessions=loc_data["total_sessions"],
                    total_minutes=loc_data["total_minutes"],
                )
                for loc_data in top_locs_data
            ],
            reading_by_hour=reading_by_hour,
        )

    def get_location_breakdown(self, location_id: str) -> Optional[LocationBreakdown]:
        """Get detailed breakdown for a location.

        Args:
            location_id: Location ID

        Returns:
            LocationBreakdown or None
        """
        location = self.get_location(location_id)
        if not location:
            return None

        with self.db.get_session() as session:
            # Get sessions for this location
            sessions_list = (
                session.execute(
                    select(LocationSession)
                    .where(LocationSession.location_id == location_id)
                    .order_by(LocationSession.session_date.desc())
                )
                .scalars()
                .all()
            )

            # Calculate statistics
            total_sessions = len(sessions_list)
            total_minutes = sum(s.minutes_read for s in sessions_list)
            total_pages = sum(s.pages_read for s in sessions_list)
            avg_minutes = total_minutes / total_sessions if total_sessions > 0 else 0.0

            # Books read here
            book_ids = set(s.book_id for s in sessions_list if s.book_id)
            books_read = []
            for book_id in book_ids:
                book = session.execute(
                    select(Book).where(Book.id == book_id)
                ).scalar_one_or_none()
                if book:
                    books_read.append(book.title)

            # Most recent session
            most_recent = None
            if sessions_list:
                most_recent = datetime.fromisoformat(sessions_list[0].session_date)

            # Favorite time of day
            hour_counts: Counter = Counter()
            for s in sessions_list:
                hour = s.session_hour
                hour_counts[hour] += s.minutes_read

            favorite_time = None
            if hour_counts:
                peak_hour = hour_counts.most_common(1)[0][0]
                if 5 <= peak_hour < 12:
                    favorite_time = "morning"
                elif 12 <= peak_hour < 17:
                    favorite_time = "afternoon"
                elif 17 <= peak_hour < 21:
                    favorite_time = "evening"
                else:
                    favorite_time = "night"

        return LocationBreakdown(
            location_id=location.id,
            location_name=location.name,
            total_sessions=total_sessions,
            total_minutes=total_minutes,
            total_pages=total_pages,
            average_session_minutes=avg_minutes,
            books_read_here=books_read,
            most_recent_session=most_recent,
            favorite_time_of_day=favorite_time,
        )

    # -------------------------------------------------------------------------
    # Response Helpers
    # -------------------------------------------------------------------------

    def to_response(self, location: ReadingLocation) -> LocationResponse:
        """Convert location to response schema.

        Args:
            location: Location model

        Returns:
            LocationResponse
        """
        return LocationResponse(
            id=location.id,
            name=location.name,
            location_type=LocationType(location.location_type),
            description=location.description,
            address=location.address,
            icon=location.icon,
            is_favorite=location.is_favorite,
            total_sessions=location.total_sessions,
            total_minutes=location.total_minutes,
            total_pages=location.total_pages,
            created_at=datetime.fromisoformat(location.created_at),
            updated_at=datetime.fromisoformat(location.updated_at),
        )
