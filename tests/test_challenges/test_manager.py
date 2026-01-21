"""Tests for ChallengeManager."""

from datetime import date, timedelta
from uuid import UUID
import pytest

from vibecoding.booktracker.challenges import (
    ChallengeManager,
    ChallengeType,
    ChallengeStatus,
)
from vibecoding.booktracker.challenges.schemas import (
    ChallengeCreate,
    ChallengeUpdate,
    ChallengeBookAdd,
    ChallengeCriteria,
    YearlyChallenge,
)
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus


class TestChallengeManager:
    """Tests for ChallengeManager class."""

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
        """Create manager instance."""
        return ChallengeManager(db)

    @pytest.fixture
    def sample_books(self, db):
        """Create sample books for testing."""
        today = date.today()
        books = []
        book_data = [
            {
                "title": "Book 1",
                "author": "Author A",
                "status": BookStatus.COMPLETED,
                "rating": 5,
                "page_count": 300,
                "date_finished": (today - timedelta(days=10)).isoformat(),
            },
            {
                "title": "Book 2",
                "author": "Author A",
                "status": BookStatus.COMPLETED,
                "rating": 4,
                "page_count": 250,
                "date_finished": (today - timedelta(days=5)).isoformat(),
            },
            {
                "title": "Book 3",
                "author": "Author B",
                "status": BookStatus.COMPLETED,
                "rating": 3,
                "page_count": 400,
                "date_finished": today.isoformat(),
            },
            {
                "title": "Book 4",
                "author": "Author B",
                "status": BookStatus.READING,
                "page_count": 350,
            },
            {
                "title": "Book 5",
                "author": "Author C",
                "status": BookStatus.WISHLIST,
                "page_count": 200,
            },
        ]

        for data in book_data:
            book = db.create_book(BookCreate(**data))
            books.append(book)

        return books

    def test_create_challenge(self, manager):
        """Test creating a basic challenge."""
        today = date.today()
        data = ChallengeCreate(
            name="Read 10 Books",
            description="My reading goal",
            challenge_type=ChallengeType.BOOKS,
            target=10,
            start_date=today,
            end_date=today + timedelta(days=30),
        )

        challenge = manager.create_challenge(data)

        assert challenge.id is not None
        assert challenge.name == "Read 10 Books"
        assert challenge.target == 10
        assert challenge.current == 0
        assert challenge.challenge_type == "books"
        assert challenge.status == "active"

    def test_create_pages_challenge(self, manager):
        """Test creating a pages-based challenge."""
        today = date.today()
        data = ChallengeCreate(
            name="Read 5000 Pages",
            challenge_type=ChallengeType.PAGES,
            target=5000,
            start_date=today,
            end_date=today + timedelta(days=365),
        )

        challenge = manager.create_challenge(data)

        assert challenge.challenge_type == "pages"
        assert challenge.target == 5000

    def test_create_yearly_challenge(self, manager):
        """Test creating a yearly reading challenge."""
        year = date.today().year

        data = YearlyChallenge(year=year, target=52)
        challenge = manager.create_yearly_challenge(data)

        assert challenge.name == f"{year} Reading Challenge"
        assert challenge.target == 52
        assert challenge.start_date == f"{year}-01-01"
        assert challenge.end_date == f"{year}-12-31"

    def test_create_challenge_with_criteria(self, manager):
        """Test creating a challenge with filtering criteria."""
        today = date.today()
        criteria = ChallengeCriteria(
            status="completed",
            require_finish_in_period=True,
        )

        data = ChallengeCreate(
            name="Completion Challenge",
            target=5,
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=30),
            criteria=criteria,
        )

        challenge = manager.create_challenge(data)

        assert challenge.get_criteria() is not None
        assert challenge.get_criteria()["status"] == "completed"

    def test_get_challenge_by_id(self, manager):
        """Test getting challenge by ID."""
        data = ChallengeCreate(
            name="Test Challenge",
            target=10,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        created = manager.create_challenge(data)

        fetched = manager.get_challenge(created.id)

        assert fetched is not None
        assert fetched.id == created.id

    def test_get_challenge_by_name(self, manager):
        """Test getting challenge by name."""
        data = ChallengeCreate(
            name="My Challenge",
            target=10,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        manager.create_challenge(data)

        fetched = manager.get_challenge_by_name("My Challenge")
        assert fetched is not None

        # Case insensitive
        fetched_lower = manager.get_challenge_by_name("my challenge")
        assert fetched_lower is not None

    def test_get_nonexistent_challenge(self, manager):
        """Test getting a challenge that doesn't exist."""
        fetched = manager.get_challenge("nonexistent-id")
        assert fetched is None

    def test_list_challenges(self, manager):
        """Test listing all challenges."""
        today = date.today()
        for i in range(3):
            data = ChallengeCreate(
                name=f"Challenge {i}",
                target=10,
                start_date=today,
                end_date=today + timedelta(days=30),
            )
            manager.create_challenge(data)

        challenges = manager.list_challenges()
        assert len(challenges) == 3

    def test_list_active_challenges(self, manager):
        """Test listing only active challenges."""
        today = date.today()

        # Active challenge
        active_data = ChallengeCreate(
            name="Active",
            target=10,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=30),
        )
        manager.create_challenge(active_data)

        # Future challenge
        future_data = ChallengeCreate(
            name="Future",
            target=10,
            start_date=today + timedelta(days=10),
            end_date=today + timedelta(days=40),
        )
        manager.create_challenge(future_data)

        active = manager.list_challenges(active_only=True)
        assert len(active) == 1
        assert active[0].name == "Active"

    def test_update_challenge(self, manager):
        """Test updating a challenge."""
        today = date.today()
        data = ChallengeCreate(
            name="Original",
            target=10,
            start_date=today,
            end_date=today + timedelta(days=30),
        )
        challenge = manager.create_challenge(data)

        update_data = ChallengeUpdate(
            name="Updated",
            target=20,
        )
        updated = manager.update_challenge(challenge.id, update_data)

        assert updated.name == "Updated"
        assert updated.target == 20

    def test_delete_challenge(self, manager):
        """Test deleting a challenge."""
        today = date.today()
        data = ChallengeCreate(
            name="To Delete",
            target=10,
            start_date=today,
            end_date=today + timedelta(days=30),
        )
        challenge = manager.create_challenge(data)

        result = manager.delete_challenge(challenge.id)
        assert result is True

        fetched = manager.get_challenge(challenge.id)
        assert fetched is None

    def test_add_book_to_challenge(self, manager, sample_books):
        """Test manually adding a book to a challenge."""
        today = date.today()
        data = ChallengeCreate(
            name="Manual Challenge",
            target=5,
            start_date=today,
            end_date=today + timedelta(days=30),
            auto_count=False,
        )
        challenge = manager.create_challenge(data)

        book = sample_books[0]
        add_data = ChallengeBookAdd(book_id=UUID(book.id))

        cb = manager.add_book_to_challenge(challenge.id, add_data)

        assert cb is not None
        assert cb.book_id == book.id

        # Verify count updated
        updated = manager.get_challenge(challenge.id)
        assert updated.current == 1

    def test_add_book_pages_challenge(self, manager, sample_books):
        """Test adding a book to a pages challenge counts pages."""
        today = date.today()
        data = ChallengeCreate(
            name="Pages Challenge",
            challenge_type=ChallengeType.PAGES,
            target=1000,
            start_date=today,
            end_date=today + timedelta(days=30),
            auto_count=False,
        )
        challenge = manager.create_challenge(data)

        book = sample_books[0]  # 300 pages
        add_data = ChallengeBookAdd(book_id=UUID(book.id))

        cb = manager.add_book_to_challenge(challenge.id, add_data)

        assert cb.value == 300

        updated = manager.get_challenge(challenge.id)
        assert updated.current == 300

    def test_add_duplicate_book_fails(self, manager, sample_books):
        """Test adding the same book twice fails."""
        today = date.today()
        data = ChallengeCreate(
            name="No Dupes",
            target=5,
            start_date=today,
            end_date=today + timedelta(days=30),
            auto_count=False,
        )
        challenge = manager.create_challenge(data)

        book = sample_books[0]
        add_data = ChallengeBookAdd(book_id=UUID(book.id))

        manager.add_book_to_challenge(challenge.id, add_data)

        with pytest.raises(ValueError, match="already counted"):
            manager.add_book_to_challenge(challenge.id, add_data)

    def test_remove_book_from_challenge(self, manager, sample_books):
        """Test removing a book from a challenge."""
        today = date.today()
        data = ChallengeCreate(
            name="Remove Test",
            target=5,
            start_date=today,
            end_date=today + timedelta(days=30),
            auto_count=False,
        )
        challenge = manager.create_challenge(data)

        book = sample_books[0]
        add_data = ChallengeBookAdd(book_id=UUID(book.id))
        manager.add_book_to_challenge(challenge.id, add_data)

        result = manager.remove_book_from_challenge(challenge.id, book.id)
        assert result is True

        updated = manager.get_challenge(challenge.id)
        assert updated.current == 0

    def test_get_challenge_books(self, manager, sample_books):
        """Test getting books counted in a challenge."""
        today = date.today()
        data = ChallengeCreate(
            name="Books Test",
            target=5,
            start_date=today,
            end_date=today + timedelta(days=30),
            auto_count=False,
        )
        challenge = manager.create_challenge(data)

        for book in sample_books[:3]:
            add_data = ChallengeBookAdd(book_id=UUID(book.id))
            manager.add_book_to_challenge(challenge.id, add_data)

        books = manager.get_challenge_books(challenge.id)
        assert len(books) == 3

    def test_get_progress(self, manager, sample_books):
        """Test getting detailed progress."""
        today = date.today()
        data = ChallengeCreate(
            name="Progress Test",
            target=10,
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=20),
            auto_count=False,
        )
        challenge = manager.create_challenge(data)

        # Add 3 books
        for book in sample_books[:3]:
            add_data = ChallengeBookAdd(book_id=UUID(book.id))
            manager.add_book_to_challenge(challenge.id, add_data)

        progress = manager.get_progress(challenge.id)

        assert progress is not None
        assert progress.current == 3
        assert progress.target == 10
        assert progress.remaining == 7
        assert progress.books_counted == 3
        assert progress.percent == 30.0
        assert progress.days_remaining == 20

    def test_auto_count_completed_books(self, manager, sample_books):
        """Test auto-count for completed books in date range."""
        today = date.today()

        criteria = ChallengeCriteria(
            status="completed",
            require_finish_in_period=True,
        )

        data = ChallengeCreate(
            name="Auto Count",
            target=10,
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=30),
            auto_count=True,
            criteria=criteria,
        )

        challenge = manager.create_challenge(data)

        # Should have counted the 3 completed books
        assert challenge.current == 3

    def test_refresh_challenge(self, manager, sample_books, db):
        """Test refreshing auto-count."""
        today = date.today()

        criteria = ChallengeCriteria(
            status="completed",
            require_finish_in_period=True,
        )

        data = ChallengeCreate(
            name="Refresh Test",
            target=10,
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=30),
            auto_count=True,
            criteria=criteria,
        )

        challenge = manager.create_challenge(data)
        initial_count = challenge.current

        # Add another completed book
        new_book = db.create_book(BookCreate(
            title="New Completed",
            author="Author",
            status=BookStatus.COMPLETED,
            date_finished=today.isoformat(),
        ))

        refreshed = manager.refresh_challenge(challenge.id)
        assert refreshed.current == initial_count + 1

    def test_challenge_completion(self, manager, sample_books):
        """Test challenge auto-completes when target reached."""
        today = date.today()
        data = ChallengeCreate(
            name="Complete Test",
            target=2,
            start_date=today,
            end_date=today + timedelta(days=30),
            auto_count=False,
        )
        challenge = manager.create_challenge(data)

        # Add books to reach target
        for book in sample_books[:2]:
            add_data = ChallengeBookAdd(book_id=UUID(book.id))
            manager.add_book_to_challenge(challenge.id, add_data)

        completed = manager.get_challenge(challenge.id)
        assert completed.status == "completed"
        assert completed.is_complete

    def test_check_expired_challenges(self, manager):
        """Test checking for expired challenges."""
        today = date.today()

        # Create an expired incomplete challenge
        data = ChallengeCreate(
            name="Expired",
            target=10,
            start_date=today - timedelta(days=60),
            end_date=today - timedelta(days=1),
            auto_count=False,
        )
        manager.create_challenge(data)

        expired = manager.check_expired_challenges()

        assert len(expired) == 1
        assert expired[0].status == "failed"

    def test_get_challenges_for_book(self, manager, sample_books):
        """Test getting all challenges containing a book."""
        today = date.today()

        # Create two challenges and add the same book
        for i in range(2):
            data = ChallengeCreate(
                name=f"Challenge {i}",
                target=5,
                start_date=today,
                end_date=today + timedelta(days=30),
                auto_count=False,
            )
            challenge = manager.create_challenge(data)
            add_data = ChallengeBookAdd(book_id=UUID(sample_books[0].id))
            manager.add_book_to_challenge(challenge.id, add_data)

        challenges = manager.get_challenges_for_book(sample_books[0].id)
        assert len(challenges) == 2

    def test_progress_percent_calculation(self, manager):
        """Test progress percentage calculation."""
        today = date.today()
        data = ChallengeCreate(
            name="Percent Test",
            target=10,
            start_date=today,
            end_date=today + timedelta(days=30),
            auto_count=False,
        )
        challenge = manager.create_challenge(data)

        assert challenge.progress_percent == 0.0

        # Update to 5 out of 10
        manager.update_challenge(challenge.id, ChallengeUpdate(target=10))

        # Manually set current by adding placeholder
        with manager.db.get_session() as session:
            from vibecoding.booktracker.challenges.models import Challenge as ChallengeModel
            ch = session.get(ChallengeModel, challenge.id)
            ch.current = 5
            session.commit()

        updated = manager.get_challenge(challenge.id)
        assert updated.progress_percent == 50.0

    def test_days_remaining(self, manager):
        """Test days remaining calculation."""
        today = date.today()
        data = ChallengeCreate(
            name="Days Test",
            target=10,
            start_date=today,
            end_date=today + timedelta(days=15),
        )
        challenge = manager.create_challenge(data)

        assert challenge.days_remaining == 15

    def test_challenge_properties(self, manager):
        """Test challenge property methods."""
        today = date.today()
        data = ChallengeCreate(
            name="Properties Test",
            target=5,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=25),
        )
        challenge = manager.create_challenge(data)

        assert challenge.is_active is True
        assert challenge.is_complete is False
        assert challenge.remaining == 5
