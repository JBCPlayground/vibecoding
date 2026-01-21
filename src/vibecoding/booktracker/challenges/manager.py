"""Challenge manager for reading challenge operations."""

from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from ..db.models import Book
from ..db.sqlite import Database, get_db
from .models import Challenge, ChallengeBook
from .schemas import (
    ChallengeCreate,
    ChallengeUpdate,
    ChallengeType,
    ChallengeStatus,
    ChallengeProgress,
    ChallengeCriteria,
    ChallengeBookAdd,
    YearlyChallenge,
)


class ChallengeManager:
    """Manages reading challenge operations."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize challenge manager.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def create_challenge(self, data: ChallengeCreate) -> Challenge:
        """Create a new challenge.

        Args:
            data: Challenge creation data

        Returns:
            Created challenge
        """
        with self.db.get_session() as session:
            challenge = Challenge(
                name=data.name,
                description=data.description,
                challenge_type=data.challenge_type.value,
                target=data.target,
                start_date=data.start_date.isoformat(),
                end_date=data.end_date.isoformat(),
                auto_count=data.auto_count,
                icon=data.icon,
                color=data.color,
            )

            if data.criteria:
                challenge.set_criteria(data.criteria.model_dump())

            session.add(challenge)
            session.commit()

            # If auto_count, calculate initial progress
            if data.auto_count:
                self._update_auto_count(session, challenge)
                session.commit()

            session.refresh(challenge)
            session.expunge(challenge)

            return challenge

    def create_yearly_challenge(self, data: YearlyChallenge) -> Challenge:
        """Create a yearly reading challenge.

        Args:
            data: Yearly challenge configuration

        Returns:
            Created challenge
        """
        name = data.name or f"{data.year} Reading Challenge"
        start = date(data.year, 1, 1)
        end = date(data.year, 12, 31)

        # Default criteria: books completed this year
        criteria = ChallengeCriteria(
            status="completed",
            require_finish_in_period=True,
        )

        create_data = ChallengeCreate(
            name=name,
            description=f"Read {data.target} books in {data.year}",
            challenge_type=data.challenge_type,
            target=data.target,
            start_date=start,
            end_date=end,
            auto_count=True,
            criteria=criteria,
            icon="calendar",
            color="blue",
        )

        return self.create_challenge(create_data)

    def get_challenge(self, challenge_id: str) -> Optional[Challenge]:
        """Get a challenge by ID.

        Args:
            challenge_id: Challenge ID

        Returns:
            Challenge or None
        """
        with self.db.get_session() as session:
            stmt = select(Challenge).where(Challenge.id == challenge_id)
            challenge = session.execute(stmt).scalar_one_or_none()
            if challenge:
                session.expunge(challenge)
            return challenge

    def get_challenge_by_name(self, name: str) -> Optional[Challenge]:
        """Get a challenge by name.

        Args:
            name: Challenge name

        Returns:
            Challenge or None
        """
        with self.db.get_session() as session:
            stmt = select(Challenge).where(func.lower(Challenge.name) == name.lower())
            challenge = session.execute(stmt).scalar_one_or_none()
            if challenge:
                session.expunge(challenge)
            return challenge

    def list_challenges(
        self,
        status: Optional[ChallengeStatus] = None,
        active_only: bool = False,
        year: Optional[int] = None,
    ) -> list[Challenge]:
        """List challenges.

        Args:
            status: Filter by status
            active_only: Only return currently active challenges
            year: Filter by year

        Returns:
            List of challenges
        """
        with self.db.get_session() as session:
            stmt = select(Challenge)

            if status:
                stmt = stmt.where(Challenge.status == status.value)

            if active_only:
                today = date.today().isoformat()
                stmt = stmt.where(
                    Challenge.status == "active",
                    Challenge.start_date <= today,
                    Challenge.end_date >= today,
                )

            if year:
                year_start = f"{year}-01-01"
                year_end = f"{year}-12-31"
                stmt = stmt.where(
                    Challenge.start_date >= year_start,
                    Challenge.end_date <= year_end,
                )

            stmt = stmt.order_by(Challenge.start_date.desc())

            challenges = session.execute(stmt).scalars().all()
            for c in challenges:
                session.expunge(c)
            return list(challenges)

    def update_challenge(
        self,
        challenge_id: str,
        data: ChallengeUpdate,
    ) -> Optional[Challenge]:
        """Update a challenge.

        Args:
            challenge_id: Challenge ID
            data: Update data

        Returns:
            Updated challenge or None
        """
        with self.db.get_session() as session:
            stmt = select(Challenge).where(Challenge.id == challenge_id)
            challenge = session.execute(stmt).scalar_one_or_none()

            if not challenge:
                return None

            update_data = data.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if field == "criteria" and value is not None:
                    challenge.set_criteria(value)
                elif field == "status" and value is not None:
                    challenge.status = value.value
                elif field == "end_date" and value is not None:
                    challenge.end_date = value.isoformat()
                elif hasattr(challenge, field):
                    setattr(challenge, field, value)

            challenge.updated_at = datetime.now(timezone.utc).isoformat()

            # Check if completed
            if challenge.current >= challenge.target and challenge.status == "active":
                challenge.status = "completed"
                challenge.completed_at = datetime.now(timezone.utc).isoformat()

            session.commit()
            session.refresh(challenge)
            session.expunge(challenge)

            return challenge

    def delete_challenge(self, challenge_id: str) -> bool:
        """Delete a challenge.

        Args:
            challenge_id: Challenge ID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            stmt = select(Challenge).where(Challenge.id == challenge_id)
            challenge = session.execute(stmt).scalar_one_or_none()

            if not challenge:
                return False

            session.delete(challenge)
            session.commit()
            return True

    def add_book_to_challenge(
        self,
        challenge_id: str,
        data: ChallengeBookAdd,
    ) -> Optional[ChallengeBook]:
        """Manually add a book to a challenge.

        Args:
            challenge_id: Challenge ID
            data: Book addition data

        Returns:
            ChallengeBook or None
        """
        with self.db.get_session() as session:
            # Verify challenge exists
            stmt = select(Challenge).where(Challenge.id == challenge_id)
            challenge = session.execute(stmt).scalar_one_or_none()

            if not challenge:
                return None

            # Check if book already counted
            existing = session.execute(
                select(ChallengeBook).where(
                    ChallengeBook.challenge_id == challenge_id,
                    ChallengeBook.book_id == str(data.book_id),
                )
            ).scalar_one_or_none()

            if existing:
                raise ValueError("Book already counted in this challenge")

            # Get book for value calculation
            book = session.execute(
                select(Book).where(Book.id == str(data.book_id))
            ).scalar_one_or_none()

            if not book:
                raise ValueError("Book not found")

            # Calculate value based on challenge type
            if data.value is not None:
                value = data.value
            elif challenge.challenge_type == "pages":
                value = book.page_count or 0
            else:
                value = 1

            cb = ChallengeBook(
                challenge_id=challenge_id,
                book_id=str(data.book_id),
                value=value,
                notes=data.notes,
            )

            session.add(cb)

            # Update challenge current count
            challenge.current += value
            if challenge.current >= challenge.target and challenge.status == "active":
                challenge.status = "completed"
                challenge.completed_at = datetime.now(timezone.utc).isoformat()

            session.commit()
            session.refresh(cb)
            session.expunge(cb)

            return cb

    def remove_book_from_challenge(
        self,
        challenge_id: str,
        book_id: str,
    ) -> bool:
        """Remove a book from a challenge.

        Args:
            challenge_id: Challenge ID
            book_id: Book ID

        Returns:
            True if removed
        """
        with self.db.get_session() as session:
            stmt = select(ChallengeBook).where(
                ChallengeBook.challenge_id == challenge_id,
                ChallengeBook.book_id == book_id,
            )
            cb = session.execute(stmt).scalar_one_or_none()

            if not cb:
                return False

            # Update challenge count
            challenge = session.execute(
                select(Challenge).where(Challenge.id == challenge_id)
            ).scalar_one_or_none()

            if challenge:
                challenge.current = max(0, challenge.current - cb.value)
                # Revert completion if needed
                if challenge.current < challenge.target and challenge.status == "completed":
                    challenge.status = "active"
                    challenge.completed_at = None

            session.delete(cb)
            session.commit()
            return True

    def get_challenge_books(self, challenge_id: str) -> list[Book]:
        """Get books counted toward a challenge.

        Args:
            challenge_id: Challenge ID

        Returns:
            List of books
        """
        with self.db.get_session() as session:
            stmt = (
                select(Book)
                .join(ChallengeBook, Book.id == ChallengeBook.book_id)
                .where(ChallengeBook.challenge_id == challenge_id)
                .order_by(ChallengeBook.counted_at.desc())
            )

            books = session.execute(stmt).scalars().all()
            for book in books:
                session.expunge(book)
            return list(books)

    def get_progress(self, challenge_id: str) -> Optional[ChallengeProgress]:
        """Get detailed progress for a challenge.

        Args:
            challenge_id: Challenge ID

        Returns:
            ChallengeProgress or None
        """
        with self.db.get_session() as session:
            stmt = select(Challenge).where(Challenge.id == challenge_id)
            challenge = session.execute(stmt).scalar_one_or_none()

            if not challenge:
                return None

            # Count books
            book_count = session.execute(
                select(func.count()).where(
                    ChallengeBook.challenge_id == challenge_id
                )
            ).scalar() or 0

            # Calculate pace
            start = date.fromisoformat(challenge.start_date)
            end = date.fromisoformat(challenge.end_date)
            today = date.today()

            days_elapsed = max(1, (today - start).days)
            days_total = max(1, (end - start).days)
            days_remaining = max(0, (end - today).days)

            current_pace = challenge.current / days_elapsed if days_elapsed > 0 else 0
            pace_needed = (
                challenge.remaining / days_remaining if days_remaining > 0 else float("inf")
            )

            # On track if current pace meets needed pace
            on_track = challenge.current >= challenge.target or current_pace >= pace_needed

            return ChallengeProgress(
                current=challenge.current,
                target=challenge.target,
                percent=challenge.progress_percent,
                remaining=challenge.remaining,
                days_remaining=days_remaining,
                books_counted=book_count,
                on_track=on_track,
                pace_needed=round(pace_needed, 2),
                current_pace=round(current_pace, 2),
            )

    def refresh_challenge(self, challenge_id: str) -> Optional[Challenge]:
        """Refresh auto-count for a challenge.

        Args:
            challenge_id: Challenge ID

        Returns:
            Updated challenge or None
        """
        with self.db.get_session() as session:
            stmt = select(Challenge).where(Challenge.id == challenge_id)
            challenge = session.execute(stmt).scalar_one_or_none()

            if not challenge or not challenge.auto_count:
                return challenge

            self._update_auto_count(session, challenge)
            session.commit()
            session.refresh(challenge)
            session.expunge(challenge)

            return challenge

    def refresh_all_challenges(self) -> int:
        """Refresh all auto-count challenges.

        Returns:
            Number of challenges refreshed
        """
        with self.db.get_session() as session:
            stmt = select(Challenge).where(
                Challenge.auto_count == True,
                Challenge.status == "active",
            )
            challenges = session.execute(stmt).scalars().all()

            for challenge in challenges:
                self._update_auto_count(session, challenge)

            session.commit()
            return len(challenges)

    def _update_auto_count(self, session: Session, challenge: Challenge) -> None:
        """Update auto-count for a challenge.

        Args:
            session: Database session
            challenge: Challenge to update
        """
        criteria = challenge.get_criteria() or {}

        # Build query for matching books
        stmt = select(Book)
        conditions = []

        # Filter by status
        if criteria.get("status"):
            conditions.append(Book.status == criteria["status"])

        # Filter by finish date in period
        if criteria.get("require_finish_in_period", True):
            conditions.append(Book.date_finished >= challenge.start_date)
            conditions.append(Book.date_finished <= challenge.end_date)

        # Filter by tags
        if criteria.get("tags"):
            for tag in criteria["tags"]:
                conditions.append(Book.tags.contains(tag))

        # Filter by author
        if criteria.get("author"):
            conditions.append(
                func.lower(Book.author).contains(criteria["author"].lower())
            )

        # Filter by series
        if criteria.get("series"):
            conditions.append(
                func.lower(Book.series) == criteria["series"].lower()
            )

        # Filter by publication year
        if criteria.get("min_year"):
            conditions.append(Book.publication_year >= criteria["min_year"])
        if criteria.get("max_year"):
            conditions.append(Book.publication_year <= criteria["max_year"])

        # Filter by minimum pages
        if criteria.get("min_pages"):
            conditions.append(Book.page_count >= criteria["min_pages"])

        if conditions:
            stmt = stmt.where(and_(*conditions))

        books = session.execute(stmt).scalars().all()

        # Clear existing challenge books
        session.execute(
            ChallengeBook.__table__.delete().where(
                ChallengeBook.challenge_id == challenge.id
            )
        )

        # Add matching books
        total_value = 0
        for book in books:
            if challenge.challenge_type == "pages":
                value = book.page_count or 0
            else:
                value = 1

            cb = ChallengeBook(
                challenge_id=challenge.id,
                book_id=book.id,
                value=value,
            )
            session.add(cb)
            total_value += value

        challenge.current = total_value

        # Update status
        if challenge.current >= challenge.target and challenge.status == "active":
            challenge.status = "completed"
            challenge.completed_at = datetime.now(timezone.utc).isoformat()

    def check_expired_challenges(self) -> list[Challenge]:
        """Check for expired challenges and mark them as failed.

        Returns:
            List of expired challenges
        """
        with self.db.get_session() as session:
            today = date.today().isoformat()

            stmt = select(Challenge).where(
                Challenge.status == "active",
                Challenge.end_date < today,
            )
            expired = session.execute(stmt).scalars().all()

            expired_ids = []
            for challenge in expired:
                if challenge.current >= challenge.target:
                    challenge.status = "completed"
                    challenge.completed_at = datetime.now(timezone.utc).isoformat()
                else:
                    challenge.status = "failed"
                expired_ids.append(challenge.id)

            session.commit()

        # Fetch fresh copies outside the session
        result = []
        for cid in expired_ids:
            challenge = self.get_challenge(cid)
            if challenge:
                result.append(challenge)

        return result

    def get_challenges_for_book(self, book_id: str) -> list[Challenge]:
        """Get all challenges that include a book.

        Args:
            book_id: Book ID

        Returns:
            List of challenges
        """
        with self.db.get_session() as session:
            stmt = (
                select(Challenge)
                .join(ChallengeBook, Challenge.id == ChallengeBook.challenge_id)
                .where(ChallengeBook.book_id == book_id)
            )
            challenges = session.execute(stmt).scalars().all()
            for c in challenges:
                session.expunge(c)
            return list(challenges)
