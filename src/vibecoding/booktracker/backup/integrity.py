"""Data integrity checking.

Validates database consistency and identifies issues.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import select, func

from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


class IssueSeverity(str, Enum):
    """Severity level for integrity issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class IntegrityIssue:
    """An integrity issue found during checking."""

    severity: IssueSeverity
    category: str
    message: str
    book_id: Optional[str] = None
    book_title: Optional[str] = None
    suggestion: Optional[str] = None

    def __str__(self) -> str:
        """String representation."""
        prefix = f"[{self.severity.value.upper()}]"
        book_info = f" (Book: {self.book_title})" if self.book_title else ""
        return f"{prefix} {self.category}: {self.message}{book_info}"


@dataclass
class IntegrityReport:
    """Report from integrity check."""

    checked_at: str
    book_count: int = 0
    log_count: int = 0
    issues: list[IntegrityIssue] = field(default_factory=list)
    passed: bool = True

    @property
    def critical_count(self) -> int:
        """Count of critical issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.CRITICAL)

    @property
    def error_count(self) -> int:
        """Count of error issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of warning issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @property
    def info_count(self) -> int:
        """Count of info issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.INFO)

    def get_issues_by_severity(self, severity: IssueSeverity) -> list[IntegrityIssue]:
        """Get issues of a specific severity."""
        return [i for i in self.issues if i.severity == severity]

    def get_issues_by_category(self, category: str) -> list[IntegrityIssue]:
        """Get issues of a specific category."""
        return [i for i in self.issues if i.category == category]


class IntegrityChecker:
    """Checks database integrity and data consistency."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize integrity checker.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def check_all(self) -> IntegrityReport:
        """Run all integrity checks.

        Returns:
            IntegrityReport with all issues found
        """
        report = IntegrityReport(checked_at=datetime.now().isoformat())

        with self.db.get_session() as session:
            # Get counts
            report.book_count = session.execute(
                select(func.count()).select_from(Book)
            ).scalar() or 0
            report.log_count = session.execute(
                select(func.count()).select_from(ReadingLog)
            ).scalar() or 0

            # Run all checks
            report.issues.extend(self._check_required_fields(session))
            report.issues.extend(self._check_status_consistency(session))
            report.issues.extend(self._check_date_consistency(session))
            report.issues.extend(self._check_rating_validity(session))
            report.issues.extend(self._check_progress_consistency(session))
            report.issues.extend(self._check_orphaned_logs(session))
            report.issues.extend(self._check_duplicate_books(session))
            report.issues.extend(self._check_tag_format(session))
            report.issues.extend(self._check_series_consistency(session))
            report.issues.extend(self._check_isbn_validity(session))

        # Determine if check passed
        report.passed = report.critical_count == 0 and report.error_count == 0

        return report

    def check_book(self, book_id: str) -> IntegrityReport:
        """Check integrity of a single book.

        Args:
            book_id: ID of book to check

        Returns:
            IntegrityReport for the book
        """
        report = IntegrityReport(checked_at=datetime.now().isoformat())

        with self.db.get_session() as session:
            book = session.get(Book, book_id)
            if not book:
                report.issues.append(IntegrityIssue(
                    severity=IssueSeverity.ERROR,
                    category="existence",
                    message=f"Book not found: {book_id}",
                ))
                report.passed = False
                return report

            report.book_count = 1

            # Check this specific book
            report.issues.extend(self._check_book_required_fields(book))
            report.issues.extend(self._check_book_status(book))
            report.issues.extend(self._check_book_dates(book))
            report.issues.extend(self._check_book_rating(book))
            report.issues.extend(self._check_book_progress(book))
            report.issues.extend(self._check_book_tags(book))
            report.issues.extend(self._check_book_series(book))
            report.issues.extend(self._check_book_isbn(book))

            # Check logs for this book
            stmt = select(ReadingLog).where(ReadingLog.book_id == book_id)
            logs = list(session.execute(stmt).scalars().all())
            report.log_count = len(logs)

            for log in logs:
                report.issues.extend(self._check_log_consistency(log, book))

        report.passed = report.critical_count == 0 and report.error_count == 0
        return report

    def fix_issues(self, issues: list[IntegrityIssue], dry_run: bool = True) -> dict:
        """Attempt to fix identified issues.

        Args:
            issues: Issues to fix
            dry_run: If True, don't actually fix

        Returns:
            Dictionary with fix results
        """
        results = {
            "fixed": 0,
            "skipped": 0,
            "failed": 0,
            "details": [],
        }

        fixable_categories = [
            "tag_format",
            "progress",
            "dates",
        ]

        with self.db.get_session() as session:
            for issue in issues:
                if issue.category not in fixable_categories:
                    results["skipped"] += 1
                    results["details"].append(f"Skipped: {issue.message} (not auto-fixable)")
                    continue

                if not issue.book_id:
                    results["skipped"] += 1
                    continue

                try:
                    if not dry_run:
                        fixed = self._fix_issue(session, issue)
                        if fixed:
                            results["fixed"] += 1
                            results["details"].append(f"Fixed: {issue.message}")
                        else:
                            results["failed"] += 1
                    else:
                        results["fixed"] += 1
                        results["details"].append(f"Would fix: {issue.message}")

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(f"Failed: {issue.message} - {e}")

            if not dry_run:
                session.commit()

        return results

    def _check_required_fields(self, session) -> list[IntegrityIssue]:
        """Check for missing required fields."""
        issues = []

        stmt = select(Book)
        books = list(session.execute(stmt).scalars().all())

        for book in books:
            issues.extend(self._check_book_required_fields(book))

        return issues

    def _check_book_required_fields(self, book: Book) -> list[IntegrityIssue]:
        """Check required fields for a book."""
        issues = []

        if not book.title:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.CRITICAL,
                category="required_field",
                message="Missing title",
                book_id=book.id,
                suggestion="Add a title to the book",
            ))

        if not book.author or not book.author.strip():
            issues.append(IntegrityIssue(
                severity=IssueSeverity.WARNING,
                category="required_field",
                message="Missing author",
                book_id=book.id,
                book_title=book.title,
                suggestion="Add an author to the book",
            ))

        return issues

    def _check_status_consistency(self, session) -> list[IntegrityIssue]:
        """Check status field consistency."""
        issues = []

        stmt = select(Book)
        books = list(session.execute(stmt).scalars().all())

        for book in books:
            issues.extend(self._check_book_status(book))

        return issues

    def _check_book_status(self, book: Book) -> list[IntegrityIssue]:
        """Check status consistency for a book."""
        issues = []

        valid_statuses = [s.value for s in BookStatus]
        if book.status and book.status not in valid_statuses:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.ERROR,
                category="status",
                message=f"Invalid status: {book.status}",
                book_id=book.id,
                book_title=book.title,
                suggestion=f"Valid statuses: {', '.join(valid_statuses)}",
            ))

        return issues

    def _check_date_consistency(self, session) -> list[IntegrityIssue]:
        """Check date field consistency."""
        issues = []

        stmt = select(Book)
        books = list(session.execute(stmt).scalars().all())

        for book in books:
            issues.extend(self._check_book_dates(book))

        return issues

    def _check_book_dates(self, book: Book) -> list[IntegrityIssue]:
        """Check date consistency for a book."""
        issues = []

        # Parse dates
        try:
            date_added = date.fromisoformat(book.date_added) if book.date_added else None
            date_started = date.fromisoformat(book.date_started) if book.date_started else None
            date_finished = date.fromisoformat(book.date_finished) if book.date_finished else None
        except ValueError as e:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.ERROR,
                category="dates",
                message=f"Invalid date format: {e}",
                book_id=book.id,
                book_title=book.title,
            ))
            return issues

        # Check date order
        if date_started and date_finished and date_started > date_finished:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.ERROR,
                category="dates",
                message="Start date is after finish date",
                book_id=book.id,
                book_title=book.title,
                suggestion="Swap the dates or correct one of them",
            ))

        if date_added and date_started and date_added > date_started:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.WARNING,
                category="dates",
                message="Added date is after start date",
                book_id=book.id,
                book_title=book.title,
            ))

        # Check status consistency with dates
        if book.status == BookStatus.COMPLETED.value and not date_finished:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.WARNING,
                category="dates",
                message="Completed book missing finish date",
                book_id=book.id,
                book_title=book.title,
                suggestion="Add a finish date",
            ))

        if book.status == BookStatus.READING.value and not date_started:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.INFO,
                category="dates",
                message="Currently reading book missing start date",
                book_id=book.id,
                book_title=book.title,
            ))

        # Check for future dates
        today = date.today()
        if date_finished and date_finished > today:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.WARNING,
                category="dates",
                message="Finish date is in the future",
                book_id=book.id,
                book_title=book.title,
            ))

        return issues

    def _check_rating_validity(self, session) -> list[IntegrityIssue]:
        """Check rating field validity."""
        issues = []

        stmt = select(Book).where(Book.rating.isnot(None))
        books = list(session.execute(stmt).scalars().all())

        for book in books:
            issues.extend(self._check_book_rating(book))

        return issues

    def _check_book_rating(self, book: Book) -> list[IntegrityIssue]:
        """Check rating for a book."""
        issues = []

        if book.rating is not None:
            if book.rating < 1 or book.rating > 5:
                issues.append(IntegrityIssue(
                    severity=IssueSeverity.ERROR,
                    category="rating",
                    message=f"Invalid rating: {book.rating} (must be 1-5)",
                    book_id=book.id,
                    book_title=book.title,
                ))

            if book.status != BookStatus.COMPLETED.value:
                issues.append(IntegrityIssue(
                    severity=IssueSeverity.INFO,
                    category="rating",
                    message="Book has rating but status is not 'completed'",
                    book_id=book.id,
                    book_title=book.title,
                ))

        return issues

    def _check_progress_consistency(self, session) -> list[IntegrityIssue]:
        """Check progress field consistency."""
        issues = []

        stmt = select(Book)
        books = list(session.execute(stmt).scalars().all())

        for book in books:
            issues.extend(self._check_book_progress(book))

        return issues

    def _check_book_progress(self, book: Book) -> list[IntegrityIssue]:
        """Check progress for a book."""
        issues = []

        if book.progress:
            # Check progress format (should be like "150/300" or "50%")
            if "/" in book.progress:
                try:
                    current, total = book.progress.split("/")
                    current_pages = int(current.strip())
                    total_pages = int(total.strip())

                    if current_pages > total_pages:
                        issues.append(IntegrityIssue(
                            severity=IssueSeverity.WARNING,
                            category="progress",
                            message=f"Current progress ({current_pages}) exceeds total ({total_pages})",
                            book_id=book.id,
                            book_title=book.title,
                        ))

                    if book.page_count and total_pages != book.page_count:
                        issues.append(IntegrityIssue(
                            severity=IssueSeverity.INFO,
                            category="progress",
                            message=f"Progress total ({total_pages}) differs from page count ({book.page_count})",
                            book_id=book.id,
                            book_title=book.title,
                        ))

                except ValueError:
                    issues.append(IntegrityIssue(
                        severity=IssueSeverity.WARNING,
                        category="progress",
                        message=f"Invalid progress format: {book.progress}",
                        book_id=book.id,
                        book_title=book.title,
                    ))

        return issues

    def _check_orphaned_logs(self, session) -> list[IntegrityIssue]:
        """Check for reading logs without associated books."""
        issues = []

        # Find logs with no matching book
        stmt = select(ReadingLog).where(
            ~ReadingLog.book_id.in_(select(Book.id))
        )
        orphaned = list(session.execute(stmt).scalars().all())

        for log in orphaned:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.ERROR,
                category="orphaned_log",
                message=f"Reading log {log.id} references non-existent book {log.book_id}",
                suggestion="Delete the orphaned log or restore the book",
            ))

        return issues

    def _check_duplicate_books(self, session) -> list[IntegrityIssue]:
        """Check for duplicate books."""
        issues = []

        # Check by ISBN
        stmt = select(Book.isbn, func.count(Book.id)).where(
            Book.isbn.isnot(None),
            Book.isbn != "",
        ).group_by(Book.isbn).having(func.count(Book.id) > 1)

        duplicates = list(session.execute(stmt).all())

        for isbn, count in duplicates:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.WARNING,
                category="duplicate",
                message=f"Duplicate ISBN found: {isbn} ({count} books)",
                suggestion="Review and merge duplicate entries",
            ))

        # Check by title + author
        stmt = select(Book.title, Book.author, func.count(Book.id)).group_by(
            func.lower(Book.title), func.lower(Book.author)
        ).having(func.count(Book.id) > 1)

        duplicates = list(session.execute(stmt).all())

        for title, author, count in duplicates:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.INFO,
                category="duplicate",
                message=f"Possible duplicate: '{title}' by {author} ({count} entries)",
                suggestion="Review if these are the same book",
            ))

        return issues

    def _check_tag_format(self, session) -> list[IntegrityIssue]:
        """Check tag format consistency."""
        issues = []

        stmt = select(Book).where(Book.tags.isnot(None), Book.tags != "")
        books = list(session.execute(stmt).scalars().all())

        for book in books:
            issues.extend(self._check_book_tags(book))

        return issues

    def _check_book_tags(self, book: Book) -> list[IntegrityIssue]:
        """Check tags for a book."""
        issues = []

        if book.tags:
            try:
                tags = json.loads(book.tags)
                if not isinstance(tags, list):
                    issues.append(IntegrityIssue(
                        severity=IssueSeverity.ERROR,
                        category="tag_format",
                        message="Tags are not stored as list",
                        book_id=book.id,
                        book_title=book.title,
                    ))
            except json.JSONDecodeError:
                issues.append(IntegrityIssue(
                    severity=IssueSeverity.ERROR,
                    category="tag_format",
                    message="Invalid JSON in tags field",
                    book_id=book.id,
                    book_title=book.title,
                ))

        return issues

    def _check_series_consistency(self, session) -> list[IntegrityIssue]:
        """Check series field consistency."""
        issues = []

        stmt = select(Book).where(Book.series.isnot(None), Book.series != "")
        books = list(session.execute(stmt).scalars().all())

        for book in books:
            issues.extend(self._check_book_series(book))

        return issues

    def _check_book_series(self, book: Book) -> list[IntegrityIssue]:
        """Check series info for a book."""
        issues = []

        if book.series and book.series_index is None:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.INFO,
                category="series",
                message=f"Book in series '{book.series}' missing series index",
                book_id=book.id,
                book_title=book.title,
            ))

        if book.series_index is not None and not book.series:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.WARNING,
                category="series",
                message="Book has series index but no series name",
                book_id=book.id,
                book_title=book.title,
            ))

        return issues

    def _check_isbn_validity(self, session) -> list[IntegrityIssue]:
        """Check ISBN validity."""
        issues = []

        stmt = select(Book).where(Book.isbn.isnot(None))
        books = list(session.execute(stmt).scalars().all())

        for book in books:
            issues.extend(self._check_book_isbn(book))

        return issues

    def _check_book_isbn(self, book: Book) -> list[IntegrityIssue]:
        """Check ISBN for a book."""
        issues = []

        if book.isbn:
            # Remove hyphens for validation
            isbn = book.isbn.replace("-", "").replace(" ", "")

            if len(isbn) == 10:
                if not self._validate_isbn10(isbn):
                    issues.append(IntegrityIssue(
                        severity=IssueSeverity.WARNING,
                        category="isbn",
                        message=f"Invalid ISBN-10 checksum: {book.isbn}",
                        book_id=book.id,
                        book_title=book.title,
                    ))
            elif len(isbn) == 13:
                if not self._validate_isbn13(isbn):
                    issues.append(IntegrityIssue(
                        severity=IssueSeverity.WARNING,
                        category="isbn",
                        message=f"Invalid ISBN-13 checksum: {book.isbn}",
                        book_id=book.id,
                        book_title=book.title,
                    ))
            elif isbn:  # Has content but wrong length
                issues.append(IntegrityIssue(
                    severity=IssueSeverity.WARNING,
                    category="isbn",
                    message=f"ISBN has invalid length ({len(isbn)}): {book.isbn}",
                    book_id=book.id,
                    book_title=book.title,
                ))

        return issues

    def _validate_isbn10(self, isbn: str) -> bool:
        """Validate ISBN-10 checksum."""
        if len(isbn) != 10:
            return False

        try:
            total = 0
            for i, char in enumerate(isbn[:-1]):
                total += int(char) * (10 - i)

            check = isbn[-1]
            if check == "X":
                total += 10
            else:
                total += int(check)

            return total % 11 == 0
        except ValueError:
            return False

    def _validate_isbn13(self, isbn: str) -> bool:
        """Validate ISBN-13 checksum."""
        if len(isbn) != 13:
            return False

        try:
            total = 0
            for i, char in enumerate(isbn):
                if i % 2 == 0:
                    total += int(char)
                else:
                    total += int(char) * 3

            return total % 10 == 0
        except ValueError:
            return False

    def _check_log_consistency(self, log: ReadingLog, book: Book) -> list[IntegrityIssue]:
        """Check consistency of a reading log."""
        issues = []

        if log.pages_read and log.pages_read < 0:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.ERROR,
                category="log",
                message=f"Negative pages read: {log.pages_read}",
                book_id=book.id,
                book_title=book.title,
            ))

        if log.start_page and log.end_page and log.start_page > log.end_page:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.ERROR,
                category="log",
                message=f"Start page ({log.start_page}) > end page ({log.end_page})",
                book_id=book.id,
                book_title=book.title,
            ))

        if log.duration_minutes and log.duration_minutes < 0:
            issues.append(IntegrityIssue(
                severity=IssueSeverity.ERROR,
                category="log",
                message=f"Negative duration: {log.duration_minutes}",
                book_id=book.id,
                book_title=book.title,
            ))

        return issues

    def _fix_issue(self, session, issue: IntegrityIssue) -> bool:
        """Attempt to fix a single issue."""
        if not issue.book_id:
            return False

        book = session.get(Book, issue.book_id)
        if not book:
            return False

        if issue.category == "tag_format":
            # Try to fix tag format
            if book.tags and not book.tags.startswith("["):
                # Assume comma-separated
                tags = [t.strip() for t in book.tags.split(",")]
                book.tags = json.dumps(tags)
                return True

        return False
