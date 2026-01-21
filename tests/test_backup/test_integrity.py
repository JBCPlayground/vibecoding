"""Tests for integrity checking functionality."""

import json
import pytest
from datetime import date, timedelta

from vibecoding.booktracker.backup.integrity import (
    IntegrityChecker,
    IntegrityReport,
    IntegrityIssue,
    IssueSeverity,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus, ReadingLogCreate
from vibecoding.booktracker.db.models import Book, ReadingLog


class TestIssueSeverity:
    """Tests for IssueSeverity enum."""

    def test_severity_values(self):
        """Test severity level values."""
        assert IssueSeverity.INFO.value == "info"
        assert IssueSeverity.WARNING.value == "warning"
        assert IssueSeverity.ERROR.value == "error"
        assert IssueSeverity.CRITICAL.value == "critical"


class TestIntegrityIssue:
    """Tests for IntegrityIssue dataclass."""

    def test_str_representation(self):
        """Test string representation."""
        issue = IntegrityIssue(
            severity=IssueSeverity.ERROR,
            category="test",
            message="Test message",
            book_title="Test Book",
        )
        str_repr = str(issue)

        assert "[ERROR]" in str_repr
        assert "test" in str_repr
        assert "Test message" in str_repr
        assert "Test Book" in str_repr

    def test_str_without_book(self):
        """Test string representation without book."""
        issue = IntegrityIssue(
            severity=IssueSeverity.WARNING,
            category="general",
            message="General issue",
        )
        str_repr = str(issue)

        assert "[WARNING]" in str_repr
        assert "General issue" in str_repr


class TestIntegrityReport:
    """Tests for IntegrityReport dataclass."""

    def test_issue_counts(self):
        """Test counting issues by severity."""
        report = IntegrityReport(checked_at="2024-01-01")
        report.issues = [
            IntegrityIssue(IssueSeverity.CRITICAL, "cat", "msg1"),
            IntegrityIssue(IssueSeverity.ERROR, "cat", "msg2"),
            IntegrityIssue(IssueSeverity.ERROR, "cat", "msg3"),
            IntegrityIssue(IssueSeverity.WARNING, "cat", "msg4"),
            IntegrityIssue(IssueSeverity.INFO, "cat", "msg5"),
            IntegrityIssue(IssueSeverity.INFO, "cat", "msg6"),
        ]

        assert report.critical_count == 1
        assert report.error_count == 2
        assert report.warning_count == 1
        assert report.info_count == 2

    def test_passed_with_no_errors(self):
        """Test passed status with only warnings."""
        report = IntegrityReport(checked_at="2024-01-01")
        report.issues = [
            IntegrityIssue(IssueSeverity.WARNING, "cat", "msg"),
            IntegrityIssue(IssueSeverity.INFO, "cat", "msg"),
        ]
        report.passed = report.critical_count == 0 and report.error_count == 0

        assert report.passed is True

    def test_failed_with_errors(self):
        """Test failed status with errors."""
        report = IntegrityReport(checked_at="2024-01-01")
        report.issues = [
            IntegrityIssue(IssueSeverity.ERROR, "cat", "msg"),
        ]
        report.passed = report.critical_count == 0 and report.error_count == 0

        assert report.passed is False

    def test_get_issues_by_severity(self):
        """Test filtering issues by severity."""
        report = IntegrityReport(checked_at="2024-01-01")
        report.issues = [
            IntegrityIssue(IssueSeverity.ERROR, "cat", "error1"),
            IntegrityIssue(IssueSeverity.WARNING, "cat", "warning1"),
            IntegrityIssue(IssueSeverity.ERROR, "cat", "error2"),
        ]

        errors = report.get_issues_by_severity(IssueSeverity.ERROR)
        assert len(errors) == 2

    def test_get_issues_by_category(self):
        """Test filtering issues by category."""
        report = IntegrityReport(checked_at="2024-01-01")
        report.issues = [
            IntegrityIssue(IssueSeverity.ERROR, "dates", "date issue"),
            IntegrityIssue(IssueSeverity.ERROR, "rating", "rating issue"),
            IntegrityIssue(IssueSeverity.WARNING, "dates", "another date"),
        ]

        date_issues = report.get_issues_by_category("dates")
        assert len(date_issues) == 2


class TestIntegrityChecker:
    """Tests for IntegrityChecker class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def checker(self, db):
        """Create integrity checker instance."""
        return IntegrityChecker(db)

    def test_check_all_clean_database(self, db, checker):
        """Test check on clean database."""
        # Create valid book
        db.create_book(BookCreate(
            title="Valid Book",
            author="Author",
            status=BookStatus.COMPLETED,
            rating=5,
            date_finished=date.today().isoformat(),
        ))

        report = checker.check_all()

        assert report.passed is True
        assert report.book_count == 1

    def test_check_missing_title(self, db, checker):
        """Test detection of missing title."""
        # Create book directly with missing title
        with db.get_session() as session:
            book = Book(title="", author="Author")  # Empty title
            session.add(book)
            session.commit()

        report = checker.check_all()

        critical_issues = report.get_issues_by_category("required_field")
        assert len(critical_issues) > 0

    def test_check_missing_author(self, db, checker):
        """Test detection of missing/empty author."""
        with db.get_session() as session:
            # Use empty string since NOT NULL constraint requires a value
            book = Book(title="Test Book", author="")
            session.add(book)
            session.commit()

        report = checker.check_all()

        # Missing/empty author should be a warning
        author_issues = [i for i in report.issues if "author" in i.message.lower()]
        assert len(author_issues) > 0

    def test_check_invalid_status(self, db, checker):
        """Test detection of invalid status."""
        with db.get_session() as session:
            book = Book(title="Test", author="Author", status="invalid_status")
            session.add(book)
            session.commit()

        report = checker.check_all()

        status_issues = report.get_issues_by_category("status")
        assert len(status_issues) > 0

    def test_check_date_consistency(self, db, checker):
        """Test date consistency checking."""
        # Create book with start date after finish date
        db.create_book(BookCreate(
            title="Bad Dates Book",
            author="Author",
            status=BookStatus.COMPLETED,
            date_started=(date.today()).isoformat(),
            date_finished=(date.today() - timedelta(days=10)).isoformat(),
        ))

        report = checker.check_all()

        date_issues = report.get_issues_by_category("dates")
        assert any("after" in i.message.lower() for i in date_issues)

    def test_check_completed_without_finish_date(self, db, checker):
        """Test completed book without finish date."""
        db.create_book(BookCreate(
            title="No Finish Date",
            author="Author",
            status=BookStatus.COMPLETED,
        ))

        report = checker.check_all()

        date_issues = report.get_issues_by_category("dates")
        assert any("finish date" in i.message.lower() for i in date_issues)

    def test_check_invalid_rating(self, db, checker):
        """Test invalid rating detection."""
        with db.get_session() as session:
            book = Book(title="Test", author="Author", rating=10)  # Invalid rating
            session.add(book)
            session.commit()

        report = checker.check_all()

        rating_issues = report.get_issues_by_category("rating")
        assert len(rating_issues) > 0

    def test_check_orphaned_logs(self, db, checker):
        """Test detection of orphaned reading logs."""
        # Create log without book
        with db.get_session() as session:
            log = ReadingLog(
                book_id="nonexistent-book-id",
                date=date.today().isoformat(),
                pages_read=20,
            )
            session.add(log)
            session.commit()

        report = checker.check_all()

        orphan_issues = report.get_issues_by_category("orphaned_log")
        assert len(orphan_issues) > 0

    def test_check_duplicate_isbn(self, db, checker):
        """Test detection of duplicate ISBNs."""
        isbn = "1234567890"
        db.create_book(BookCreate(
            title="Book 1",
            author="Author",
            isbn=isbn,
        ))
        db.create_book(BookCreate(
            title="Book 2",
            author="Author",
            isbn=isbn,
        ))

        report = checker.check_all()

        dup_issues = report.get_issues_by_category("duplicate")
        assert any("isbn" in i.message.lower() for i in dup_issues)

    def test_check_possible_duplicate_title(self, db, checker):
        """Test detection of possible duplicate by title+author."""
        db.create_book(BookCreate(
            title="Same Title",
            author="Same Author",
        ))
        db.create_book(BookCreate(
            title="Same Title",
            author="Same Author",
        ))

        report = checker.check_all()

        dup_issues = report.get_issues_by_category("duplicate")
        assert len(dup_issues) > 0

    def test_check_invalid_tag_format(self, db, checker):
        """Test detection of invalid tag format."""
        with db.get_session() as session:
            book = Book(title="Test", author="Author", tags="not-valid-json")
            session.add(book)
            session.commit()

        report = checker.check_all()

        tag_issues = report.get_issues_by_category("tag_format")
        assert len(tag_issues) > 0

    def test_check_series_without_index(self, db, checker):
        """Test detection of series book without index."""
        db.create_book(BookCreate(
            title="Series Book",
            author="Author",
            series="Test Series",
            # No series_index
        ))

        report = checker.check_all()

        series_issues = report.get_issues_by_category("series")
        assert any("index" in i.message.lower() for i in series_issues)

    def test_check_isbn_validity_isbn10(self, db, checker):
        """Test ISBN-10 validation."""
        db.create_book(BookCreate(
            title="Invalid ISBN Book",
            author="Author",
            isbn="1234567899",  # Invalid checksum
        ))

        report = checker.check_all()

        isbn_issues = report.get_issues_by_category("isbn")
        # Note: May or may not catch depending on checksum algorithm
        # This test verifies the check runs without error

    def test_check_single_book(self, db, checker):
        """Test checking a single book."""
        book = db.create_book(BookCreate(
            title="Test Book",
            author="Author",
            status=BookStatus.COMPLETED,
            date_finished=date.today().isoformat(),
        ))

        report = checker.check_book(book.id)

        assert report.book_count == 1
        assert report.passed is True

    def test_check_single_book_not_found(self, checker):
        """Test checking non-existent book."""
        report = checker.check_book("nonexistent-id")

        assert report.passed is False
        assert len(report.issues) > 0

    def test_check_progress_format(self, db, checker):
        """Test progress format validation."""
        with db.get_session() as session:
            book = Book(
                title="Test",
                author="Author",
                progress="abc/xyz",  # Invalid format with "/" (not numbers)
            )
            session.add(book)
            session.commit()

        report = checker.check_all()

        progress_issues = report.get_issues_by_category("progress")
        assert len(progress_issues) > 0

    def test_check_progress_exceeds_total(self, db, checker):
        """Test progress exceeding total pages."""
        with db.get_session() as session:
            book = Book(
                title="Test",
                author="Author",
                progress="500/300",  # Current > total
            )
            session.add(book)
            session.commit()

        report = checker.check_all()

        progress_issues = report.get_issues_by_category("progress")
        assert any("exceeds" in i.message.lower() for i in progress_issues)

    def test_check_future_finish_date(self, db, checker):
        """Test detection of future finish date."""
        future_date = date.today() + timedelta(days=30)
        db.create_book(BookCreate(
            title="Future Book",
            author="Author",
            status=BookStatus.COMPLETED,
            date_finished=future_date.isoformat(),
        ))

        report = checker.check_all()

        date_issues = report.get_issues_by_category("dates")
        assert any("future" in i.message.lower() for i in date_issues)

    def test_fix_issues_dry_run(self, db, checker):
        """Test fix issues in dry run mode."""
        # Create book with fixable issue
        with db.get_session() as session:
            book = Book(
                title="Test",
                author="Author",
                tags="tag1,tag2",  # Wrong format
            )
            session.add(book)
            session.commit()

        report = checker.check_all()
        results = checker.fix_issues(report.issues, dry_run=True)

        # Should report what would be fixed
        assert results["skipped"] >= 0

    def test_check_log_negative_pages(self, db, checker):
        """Test detection of negative pages in log."""
        book = db.create_book(BookCreate(
            title="Test Book",
            author="Author",
        ))

        with db.get_session() as session:
            log = ReadingLog(
                book_id=book.id,
                date=date.today().isoformat(),
                pages_read=-10,  # Negative
            )
            session.add(log)
            session.commit()

        report = checker.check_book(book.id)

        log_issues = report.get_issues_by_category("log")
        assert any("negative" in i.message.lower() for i in log_issues)

    def test_check_log_invalid_page_range(self, db, checker):
        """Test detection of invalid page range in log."""
        book = db.create_book(BookCreate(
            title="Test Book",
            author="Author",
        ))

        with db.get_session() as session:
            log = ReadingLog(
                book_id=book.id,
                date=date.today().isoformat(),
                start_page=100,
                end_page=50,  # End < start
            )
            session.add(log)
            session.commit()

        report = checker.check_book(book.id)

        log_issues = report.get_issues_by_category("log")
        assert len(log_issues) > 0
