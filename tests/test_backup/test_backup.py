"""Tests for backup functionality."""

import gzip
import json
import pytest
from datetime import date, timedelta
from pathlib import Path

from vibecoding.booktracker.backup.backup import (
    BackupManager,
    BackupResult,
    BackupMetadata,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus, ReadingLogCreate


class TestBackupMetadata:
    """Tests for BackupMetadata dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metadata = BackupMetadata(
            version="1.0",
            created_at="2024-01-01T00:00:00",
            book_count=10,
            reading_log_count=50,
        )
        data = metadata.to_dict()

        assert data["version"] == "1.0"
        assert data["book_count"] == 10
        assert data["reading_log_count"] == 50

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "version": "1.0",
            "created_at": "2024-01-01T00:00:00",
            "book_count": 5,
            "reading_log_count": 20,
            "checksum": "abc123",
        }
        metadata = BackupMetadata.from_dict(data)

        assert metadata.version == "1.0"
        assert metadata.book_count == 5
        assert metadata.checksum == "abc123"


class TestBackupResult:
    """Tests for BackupResult dataclass."""

    def test_size_human_bytes(self):
        """Test human-readable size for bytes."""
        result = BackupResult(success=True, size_bytes=500)
        assert result.size_human == "500 B"

    def test_size_human_kb(self):
        """Test human-readable size for KB."""
        result = BackupResult(success=True, size_bytes=2048)
        assert "KB" in result.size_human

    def test_size_human_mb(self):
        """Test human-readable size for MB."""
        result = BackupResult(success=True, size_bytes=2 * 1024 * 1024)
        assert "MB" in result.size_human


class TestBackupManager:
    """Tests for BackupManager class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a test database."""
        from vibecoding.booktracker.db.sqlite import Database

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.create_tables()
        return db

    @pytest.fixture
    def manager(self, db):
        """Create backup manager instance."""
        return BackupManager(db)

    @pytest.fixture
    def sample_data(self, db):
        """Create sample books and logs."""
        today = date.today()
        books = []

        for i in range(5):
            book = db.create_book(BookCreate(
                title=f"Test Book {i+1}",
                author="Test Author",
                status=BookStatus.COMPLETED,
                rating=4,
                page_count=250,
                tags=["fiction", "test"],
                date_finished=(today - timedelta(days=i)).isoformat(),
            ))
            books.append(book)

        # Add some reading logs
        for i in range(10):
            log_data = ReadingLogCreate(
                book_id=books[0].id,
                date=(today - timedelta(days=i)).isoformat(),
                pages_read=25,
                duration_minutes=30,
            )
            with db.get_session() as session:
                db.create_reading_log(log_data, session)

        return books

    def test_create_backup(self, manager, sample_data, tmp_path):
        """Test creating a backup."""
        output = tmp_path / "backup"
        result = manager.create_backup(output, compress=False)

        assert result.success is True
        assert result.backup_path is not None
        assert result.backup_path.exists()
        assert result.metadata is not None
        assert result.metadata.book_count == 5
        assert result.metadata.reading_log_count == 10

    def test_create_compressed_backup(self, manager, sample_data, tmp_path):
        """Test creating a compressed backup."""
        output = tmp_path / "backup"
        result = manager.create_backup(output, compress=True)

        assert result.success is True
        assert result.backup_path.suffix == ".gz"

        # Verify it's valid gzip
        with gzip.open(result.backup_path, "rt") as f:
            data = json.load(f)
        assert "books" in data

    def test_create_backup_with_metadata_file(self, manager, sample_data, tmp_path):
        """Test that metadata file is created."""
        output = tmp_path / "backup"
        result = manager.create_backup(output, include_metadata=True)

        assert result.success is True
        meta_path = result.backup_path.with_suffix(result.backup_path.suffix + ".meta")
        assert meta_path.exists()

        with open(meta_path, "r") as f:
            meta = json.load(f)
        assert meta["book_count"] == 5

    def test_create_sqlite_backup(self, manager, sample_data, tmp_path):
        """Test creating SQLite backup."""
        output = tmp_path / "backup"
        result = manager.create_sqlite_backup(output)

        assert result.success is True
        assert result.backup_path.suffix == ".db"
        assert result.backup_path.exists()

    def test_create_backup_empty_db(self, manager, tmp_path):
        """Test backup with empty database."""
        output = tmp_path / "backup"
        result = manager.create_backup(output)

        assert result.success is True
        assert result.metadata.book_count == 0
        assert result.metadata.reading_log_count == 0

    def test_verify_backup_valid(self, manager, sample_data, tmp_path):
        """Test verifying a valid backup."""
        output = tmp_path / "backup"
        create_result = manager.create_backup(output, compress=False)

        is_valid, error = manager.verify_backup(create_result.backup_path)

        assert is_valid is True
        assert error is None

    def test_verify_backup_invalid(self, manager, tmp_path):
        """Test verifying an invalid backup."""
        # Create invalid backup file
        invalid_path = tmp_path / "invalid.booktracker-backup"
        with open(invalid_path, "w") as f:
            json.dump({"invalid": True}, f)

        is_valid, error = manager.verify_backup(invalid_path)

        assert is_valid is False
        assert error is not None

    def test_list_backups(self, manager, sample_data, tmp_path):
        """Test listing backups."""
        # Create multiple backups
        for i in range(3):
            manager.create_backup(tmp_path / f"backup{i}")

        backups = manager.list_backups(tmp_path)

        assert len(backups) == 3

    def test_list_backups_empty_dir(self, manager, tmp_path):
        """Test listing backups in empty directory."""
        backups = manager.list_backups(tmp_path)
        assert len(backups) == 0

    def test_backup_preserves_data(self, manager, sample_data, tmp_path):
        """Test that backup preserves all data."""
        output = tmp_path / "backup"
        result = manager.create_backup(output, compress=False)

        # Load and check content
        with open(result.backup_path, "r") as f:
            data = json.load(f)

        assert len(data["books"]) == 5
        assert len(data["reading_logs"]) == 10

        # Check book data
        book = data["books"][0]
        assert "title" in book
        assert "author" in book
        assert "tags" in book
        assert isinstance(book["tags"], list)

    def test_incremental_backup(self, db, tmp_path):
        """Test incremental backup."""
        from datetime import datetime

        today = date.today()

        # Create some old data
        old_date = today - timedelta(days=30)
        db.create_book(BookCreate(
            title="Old Book",
            author="Author",
            status=BookStatus.COMPLETED,
            date_added=old_date.isoformat(),
        ))

        # Create new data with explicit recent date
        db.create_book(BookCreate(
            title="New Book",
            author="Author",
            status=BookStatus.WISHLIST,
            date_added=today.isoformat(),
        ))

        manager = BackupManager(db)
        # Use yesterday as the cutoff so today's book is included
        since = datetime.combine(today - timedelta(days=1), datetime.min.time())
        result = manager.create_incremental_backup(tmp_path / "incremental", since)

        assert result.success is True
        # Should only include recent book (added today)
        assert result.metadata.book_count == 1
