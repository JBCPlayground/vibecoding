"""Reading session management.

Handles starting, stopping, and tracking active reading sessions.
Sessions can be timed (start/stop) or manually logged.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from ..db.schemas import BookStatus, ReadingLogCreate
from ..db.sqlite import Database, get_db


@dataclass
class ReadingSession:
    """An active reading session."""

    book_id: str
    book_title: str
    start_time: datetime
    start_page: Optional[int] = None
    current_page: Optional[int] = None
    notes: list[str] = field(default_factory=list)
    location: Optional[str] = None

    def duration_minutes(self) -> int:
        """Get duration of session in minutes."""
        elapsed = datetime.now(timezone.utc) - self.start_time
        return int(elapsed.total_seconds() / 60)

    def pages_read(self) -> Optional[int]:
        """Get number of pages read in session."""
        if self.start_page is not None and self.current_page is not None:
            return max(0, self.current_page - self.start_page)
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary for persistence."""
        return {
            "book_id": self.book_id,
            "book_title": self.book_title,
            "start_time": self.start_time.isoformat(),
            "start_page": self.start_page,
            "current_page": self.current_page,
            "notes": self.notes,
            "location": self.location,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReadingSession":
        """Create from dictionary."""
        return cls(
            book_id=data["book_id"],
            book_title=data["book_title"],
            start_time=datetime.fromisoformat(data["start_time"]),
            start_page=data.get("start_page"),
            current_page=data.get("current_page"),
            notes=data.get("notes", []),
            location=data.get("location"),
        )


class SessionManager:
    """Manages active reading sessions."""

    def __init__(self, db: Optional[Database] = None, session_file: Optional[Path] = None):
        """Initialize session manager.

        Args:
            db: Database instance
            session_file: Path to persist active session (default: ~/.booktracker_session.json)
        """
        self.db = db or get_db()
        self.session_file = session_file or Path.home() / ".booktracker_session.json"
        self._active_session: Optional[ReadingSession] = None
        self._load_session()

    def _load_session(self) -> None:
        """Load active session from file if exists."""
        if self.session_file.exists():
            try:
                with open(self.session_file, "r") as f:
                    data = json.load(f)
                    self._active_session = ReadingSession.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                self._active_session = None

    def _save_session(self) -> None:
        """Save active session to file."""
        if self._active_session:
            with open(self.session_file, "w") as f:
                json.dump(self._active_session.to_dict(), f)
        elif self.session_file.exists():
            self.session_file.unlink()

    @property
    def active_session(self) -> Optional[ReadingSession]:
        """Get active reading session."""
        return self._active_session

    def has_active_session(self) -> bool:
        """Check if there's an active reading session."""
        return self._active_session is not None

    def start_session(
        self,
        book_id: str,
        start_page: Optional[int] = None,
        location: Optional[str] = None,
    ) -> ReadingSession:
        """Start a new reading session.

        Args:
            book_id: ID of the book being read
            start_page: Page number starting from
            location: Where reading (home, commute, etc.)

        Returns:
            New ReadingSession

        Raises:
            ValueError: If there's already an active session
        """
        if self._active_session:
            raise ValueError(
                f"Already reading '{self._active_session.book_title}'. "
                "Stop the current session first."
            )

        # Get book info
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError(f"Book not found: {book_id}")

        # Update book status to reading if it's not already
        if book.status not in (BookStatus.READING.value, BookStatus.COMPLETED.value):
            from ..db.schemas import BookUpdate
            self.db.update_book(book_id, BookUpdate(status=BookStatus.READING))

        self._active_session = ReadingSession(
            book_id=book_id,
            book_title=book.title,
            start_time=datetime.now(timezone.utc),
            start_page=start_page,
            location=location,
        )
        self._save_session()

        return self._active_session

    def update_progress(
        self,
        current_page: Optional[int] = None,
        note: Optional[str] = None,
    ) -> Optional[ReadingSession]:
        """Update progress in the active session.

        Args:
            current_page: Current page number
            note: Note to add to session

        Returns:
            Updated session or None if no active session
        """
        if not self._active_session:
            return None

        if current_page is not None:
            self._active_session.current_page = current_page

        if note:
            self._active_session.notes.append(note)

        self._save_session()
        return self._active_session

    def stop_session(
        self,
        end_page: Optional[int] = None,
        final_note: Optional[str] = None,
    ) -> Optional[ReadingLogCreate]:
        """Stop the active reading session and create a log entry.

        Args:
            end_page: Final page number
            final_note: Note to add before stopping

        Returns:
            ReadingLogCreate if session was stopped, None if no active session
        """
        if not self._active_session:
            return None

        session = self._active_session

        # Update final page if provided
        if end_page is not None:
            session.current_page = end_page

        # Add final note if provided
        if final_note:
            session.notes.append(final_note)

        # Calculate duration
        duration = session.duration_minutes()

        # Calculate pages read
        pages_read = session.pages_read()

        # Combine notes
        notes = "\n".join(session.notes) if session.notes else None

        # Create reading log
        log_create = ReadingLogCreate(
            book_id=UUID(session.book_id),
            date=date.today(),
            pages_read=pages_read,
            start_page=session.start_page,
            end_page=session.current_page,
            duration_minutes=duration if duration > 0 else None,
            location=session.location,
            notes=notes,
        )

        # Save to database
        self.db.create_reading_log(log_create)

        # Update book progress if we have page info
        if session.current_page is not None:
            book = self.db.get_book(session.book_id)
            if book and book.page_count:
                progress_pct = min(100, int((session.current_page / book.page_count) * 100))
                from ..db.schemas import BookUpdate
                self.db.update_book(
                    session.book_id,
                    BookUpdate(progress=f"{progress_pct}%"),
                )

        # Clear active session
        self._active_session = None
        self._save_session()

        return log_create

    def cancel_session(self) -> bool:
        """Cancel the active session without logging.

        Returns:
            True if session was cancelled, False if no active session
        """
        if not self._active_session:
            return False

        self._active_session = None
        self._save_session()
        return True

    def log_session(
        self,
        book_id: str,
        pages_read: Optional[int] = None,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
        duration_minutes: Optional[int] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        session_date: Optional[date] = None,
    ) -> ReadingLogCreate:
        """Manually log a reading session without start/stop.

        Args:
            book_id: ID of the book read
            pages_read: Number of pages read
            start_page: Starting page number
            end_page: Ending page number
            duration_minutes: Time spent reading
            location: Where reading took place
            notes: Reading notes
            session_date: Date of session (defaults to today)

        Returns:
            Created ReadingLogCreate
        """
        # Verify book exists
        book = self.db.get_book(book_id)
        if not book:
            raise ValueError(f"Book not found: {book_id}")

        # Calculate pages_read from start/end if not provided
        if pages_read is None and start_page is not None and end_page is not None:
            pages_read = max(0, end_page - start_page)

        log_create = ReadingLogCreate(
            book_id=UUID(book_id),
            date=session_date or date.today(),
            pages_read=pages_read,
            start_page=start_page,
            end_page=end_page,
            duration_minutes=duration_minutes,
            location=location,
            notes=notes,
        )

        # Save to database
        self.db.create_reading_log(log_create)

        # Update book progress if we have end_page info
        if end_page is not None and book.page_count:
            progress_pct = min(100, int((end_page / book.page_count) * 100))
            from ..db.schemas import BookUpdate
            self.db.update_book(book_id, BookUpdate(progress=f"{progress_pct}%"))

        return log_create


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager(db: Optional[Database] = None) -> SessionManager:
    """Get or create the global session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(db)
    return _session_manager


def reset_session_manager() -> None:
    """Reset the global session manager. Used for testing."""
    global _session_manager
    _session_manager = None
