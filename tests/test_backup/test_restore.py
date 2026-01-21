"""Tests for restore functionality."""

import json
import pytest
from datetime import date, timedelta
from pathlib import Path

from vibecoding.booktracker.backup.backup import BackupManager
from vibecoding.booktracker.backup.restore import (
    RestoreManager,
    RestoreResult,
    RestoreMode,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus, ReadingLogCreate
from vibecoding.booktracker.db.models import Book


class TestRestoreMode:
    """Tests for RestoreMode enum."""

    def test_mode_values(self):
        """Test restore mode values."""
        assert RestoreMode.REPLACE.value == "replace"
        assert RestoreMode.MERGE.value == "merge"
        assert RestoreMode.UPDATE.value == "update"
        assert RestoreMode.INCREMENTAL.value == "incremental"


class TestRestoreResult:
    """Tests for RestoreResult dataclass."""

    def test_total_restored(self):
        """Test total restored calculation."""
        result = RestoreResult(
            success=True,
            books_restored=10,
            logs_restored=50,
        )
        assert result.total_restored == 60

    def test_default_values(self):
        """Test default values."""
        result = RestoreResult(success=True)
        assert result.books_skipped == 0
        assert result.books_updated == 0
        assert len(result.warnings) == 0


class TestRestoreManager:
    """Tests for RestoreManager class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def restore_manager(self, db):
        """Create restore manager instance."""
        return RestoreManager(db)

    @pytest.fixture
    def backup_manager(self, db):
        """Create backup manager instance."""
        return BackupManager(db)

    @pytest.fixture
    def sample_data(self, db):
        """Create sample data."""
        books = []
        today = date.today()

        for i in range(5):
            book = db.create_book(BookCreate(
                title=f"Test Book {i+1}",
                author="Test Author",
                status=BookStatus.COMPLETED,
                rating=4,
                tags=["fiction"],
            ))
            books.append(book)

            # Add logs
            for j in range(2):
                log_data = ReadingLogCreate(
                    book_id=book.id,
                    date=(today - timedelta(days=j)).isoformat(),
                    pages_read=20,
                )
                with db.get_session() as session:
                    db.create_reading_log(log_data, session)

        return books

    @pytest.fixture
    def backup_file(self, backup_manager, sample_data, tmp_path):
        """Create a backup file."""
        output = tmp_path / "backup"
        result = backup_manager.create_backup(output, compress=False)
        return result.backup_path

    def test_restore_replace(self, db, restore_manager, backup_file):
        """Test restore with replace mode."""
        # Clear database first
        from sqlalchemy import delete
        from vibecoding.booktracker.db.models import ReadingLog

        with db.get_session() as session:
            session.execute(delete(ReadingLog))
            session.execute(delete(Book))
            session.commit()

        result = restore_manager.restore(backup_file, mode=RestoreMode.REPLACE)

        assert result.success is True
        assert result.books_restored == 5
        assert result.logs_restored == 10

    def test_restore_merge_new_books(self, tmp_path):
        """Test restore merge with new books."""
        from vibecoding.booktracker.db.sqlite import Database

        # Create empty target database
        db_path = tmp_path / "target.db"
        target_db = Database(str(db_path))
        target_db.create_tables()

        # Create source database with data
        source_path = tmp_path / "source.db"
        source_db = Database(str(source_path))
        source_db.create_tables()

        source_db.create_book(BookCreate(
            title="New Book",
            author="Author",
            status=BookStatus.WISHLIST,
        ))

        # Create backup from source
        backup_mgr = BackupManager(source_db)
        backup_result = backup_mgr.create_backup(tmp_path / "backup", compress=False)

        # Restore to target
        restore_mgr = RestoreManager(target_db)
        result = restore_mgr.restore(backup_result.backup_path, mode=RestoreMode.MERGE)

        assert result.success is True
        assert result.books_restored == 1
        assert result.books_skipped == 0

    def test_restore_merge_skip_existing(self, db, restore_manager, backup_file):
        """Test restore merge skips existing books."""
        # Database already has books from sample_data fixture
        result = restore_manager.restore(backup_file, mode=RestoreMode.MERGE)

        assert result.success is True
        assert result.books_skipped == 5
        assert result.books_restored == 0

    def test_restore_update(self, db, restore_manager, backup_manager, tmp_path):
        """Test restore update mode."""
        # Create initial book
        book = db.create_book(BookCreate(
            title="Original Title",
            author="Author",
            status=BookStatus.WISHLIST,
        ))
        book_id = book.id

        # Create backup with modified data
        backup_data = {
            "books": [{
                "id": book_id,
                "title": "Updated Title",
                "author": "Author",
                "status": BookStatus.COMPLETED.value,
                "tags": [],
            }],
            "reading_logs": [],
            "_metadata": {
                "version": "1.0",
                "book_count": 1,
                "reading_log_count": 0,
            },
        }

        backup_path = tmp_path / "update_backup.booktracker-backup"
        with open(backup_path, "w") as f:
            json.dump(backup_data, f)

        result = restore_manager.restore(backup_path, mode=RestoreMode.UPDATE)

        assert result.success is True
        assert result.books_updated == 1

        # Verify update
        with db.get_session() as session:
            updated_book = session.get(Book, book_id)
            assert updated_book.title == "Updated Title"
            assert updated_book.status == BookStatus.COMPLETED.value

    def test_restore_dry_run(self, db, restore_manager, backup_file):
        """Test restore dry run."""
        # Clear database
        from sqlalchemy import delete
        from vibecoding.booktracker.db.models import ReadingLog

        with db.get_session() as session:
            session.execute(delete(ReadingLog))
            session.execute(delete(Book))
            session.commit()

        result = restore_manager.restore(backup_file, mode=RestoreMode.REPLACE, dry_run=True)

        assert result.success is True
        assert result.books_restored == 5

        # Verify database is still empty
        with db.get_session() as session:
            from sqlalchemy import select, func
            count = session.execute(select(func.count()).select_from(Book)).scalar()
            assert count == 0

    def test_preview_restore(self, db, restore_manager, backup_file, sample_data):
        """Test restore preview."""
        preview = restore_manager.preview_restore(backup_file)

        assert "error" not in preview
        assert preview["backup_books"] == 5
        assert preview["backup_logs"] == 10
        assert preview["current_books"] == 5

    def test_restore_invalid_file(self, restore_manager, tmp_path):
        """Test restore with invalid file."""
        invalid_path = tmp_path / "invalid.booktracker-backup"
        with open(invalid_path, "w") as f:
            f.write("not valid json")

        result = restore_manager.restore(invalid_path)

        assert result.success is False
        assert result.error is not None

    def test_restore_missing_books(self, restore_manager, tmp_path):
        """Test restore with missing books key."""
        invalid_path = tmp_path / "incomplete.booktracker-backup"
        with open(invalid_path, "w") as f:
            json.dump({"reading_logs": []}, f)

        result = restore_manager.restore(invalid_path)

        assert result.success is False
        assert "missing books" in result.error.lower()

    def test_restore_sqlite(self, db, backup_manager, sample_data, tmp_path):
        """Test SQLite restore."""
        # Create SQLite backup
        backup_result = backup_manager.create_sqlite_backup(tmp_path / "backup")

        # Create new target database
        from vibecoding.booktracker.db.sqlite import Database
        target_path = tmp_path / "target.db"
        target_db = Database(str(target_path))
        target_db.create_tables()

        restore_mgr = RestoreManager(target_db)
        result = restore_mgr.restore_sqlite(backup_result.backup_path, target_path)

        assert result.success is True
        assert result.books_restored == 5

    def test_restore_preserves_all_fields(self, tmp_path):
        """Test that restore preserves all book fields."""
        from vibecoding.booktracker.db.sqlite import Database

        # Create source with full data
        source_path = tmp_path / "source.db"
        source_db = Database(str(source_path))
        source_db.create_tables()

        book = source_db.create_book(BookCreate(
            title="Full Book",
            author="Full Author",
            isbn="1234567890",
            status=BookStatus.COMPLETED,
            rating=5,
            page_count=500,
            tags=["tag1", "tag2"],
            comments="Test notes",
            publisher="Test Publisher",
            publication_year=2023,
            series="Test Series",
            series_index=1,
        ))

        # Create backup
        backup_mgr = BackupManager(source_db)
        backup_result = backup_mgr.create_backup(tmp_path / "backup", compress=False)

        # Restore to new database
        target_path = tmp_path / "target.db"
        target_db = Database(str(target_path))
        target_db.create_tables()

        restore_mgr = RestoreManager(target_db)
        restore_mgr.restore(backup_result.backup_path, mode=RestoreMode.REPLACE)

        # Verify all fields
        with target_db.get_session() as session:
            restored = session.get(Book, book.id)
            assert restored.title == "Full Book"
            assert restored.author == "Full Author"
            assert restored.isbn == "1234567890"
            assert restored.rating == 5
            assert restored.page_count == 500
            assert restored.comments == "Test notes"
            assert restored.series == "Test Series"
            assert restored.series_index == 1
