"""Tests for ScheduleManager."""

from datetime import date, time, timedelta
import pytest
from uuid import UUID, uuid4

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.db.schemas import BookCreate, BookStatus
from vibecoding.booktracker.schedule.manager import ScheduleManager
from vibecoding.booktracker.schedule.schemas import (
    PlanStatus,
    ScheduleFrequency,
    ReminderType,
    ReadingPlanCreate,
    ReadingPlanUpdate,
    PlannedBookCreate,
    PlannedBookUpdate,
    ScheduleEntryCreate,
    ScheduleEntryUpdate,
    ReminderCreate,
    ReminderUpdate,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a ScheduleManager with test database."""
    return ScheduleManager(db)


@pytest.fixture
def sample_books(db):
    """Create sample books for testing."""
    books = []
    for i in range(5):
        book = db.create_book(BookCreate(
            title=f"Book {i + 1}",
            author=f"Author {i + 1}",
            status=BookStatus.WISHLIST,
            page_count=200 + i * 50,
        ))
        books.append(book)
    return books


@pytest.fixture
def reading_book(db):
    """Create a book that is currently being read."""
    book = db.create_book(BookCreate(
        title="Currently Reading",
        author="Active Author",
        status=BookStatus.READING,
        page_count=300,
        date_started=date.today().isoformat(),
    ))
    return book


@pytest.fixture
def completed_book(db):
    """Create a completed book."""
    book = db.create_book(BookCreate(
        title="Completed Book",
        author="Done Author",
        status=BookStatus.COMPLETED,
        page_count=250,
        date_finished=date.today().isoformat(),
    ))
    return book


class TestReadingPlanCRUD:
    """Tests for reading plan CRUD operations."""

    def test_create_plan_basic(self, manager):
        """Test creating a basic reading plan."""
        plan_data = ReadingPlanCreate(name="Summer Reading")
        plan = manager.create_plan(plan_data)

        assert plan is not None
        assert plan.name == "Summer Reading"
        assert plan.status == PlanStatus.DRAFT

    def test_create_plan_with_dates(self, manager):
        """Test creating a plan with dates."""
        start = date.today()
        end = date.today() + timedelta(days=30)

        plan_data = ReadingPlanCreate(
            name="Monthly Plan",
            start_date=start,
            end_date=end,
        )
        plan = manager.create_plan(plan_data)

        assert plan.start_date == start
        assert plan.end_date == end
        assert plan.days_remaining == 30

    def test_create_plan_with_targets(self, manager):
        """Test creating a plan with targets."""
        plan_data = ReadingPlanCreate(
            name="Goal Plan",
            target_books=12,
            target_pages=3000,
        )
        plan = manager.create_plan(plan_data)

        assert plan.target_books == 12
        assert plan.target_pages == 3000

    def test_get_plan(self, manager):
        """Test getting a plan by ID."""
        plan_data = ReadingPlanCreate(name="Test Plan")
        created = manager.create_plan(plan_data)

        plan = manager.get_plan(created.id)
        assert plan is not None
        assert plan.id == created.id
        assert plan.name == "Test Plan"

    def test_get_plan_not_found(self, manager):
        """Test getting a non-existent plan."""
        plan = manager.get_plan(uuid4())
        assert plan is None

    def test_get_all_plans(self, manager):
        """Test getting all plans."""
        manager.create_plan(ReadingPlanCreate(name="Plan 1"))
        manager.create_plan(ReadingPlanCreate(name="Plan 2"))

        plans = manager.get_all_plans()
        assert len(plans) == 2

    def test_get_all_plans_excludes_completed(self, manager):
        """Test that completed plans are excluded by default."""
        plan1 = manager.create_plan(ReadingPlanCreate(name="Active"))
        plan2 = manager.create_plan(ReadingPlanCreate(name="Completed"))
        manager.complete_plan(plan2.id)

        plans = manager.get_all_plans()
        assert len(plans) == 1
        assert plans[0].name == "Active"

    def test_get_all_plans_include_completed(self, manager):
        """Test including completed plans."""
        manager.create_plan(ReadingPlanCreate(name="Active"))
        plan2 = manager.create_plan(ReadingPlanCreate(name="Completed"))
        manager.complete_plan(plan2.id)

        plans = manager.get_all_plans(include_completed=True)
        assert len(plans) == 2

    def test_update_plan(self, manager):
        """Test updating a plan."""
        plan = manager.create_plan(ReadingPlanCreate(name="Original"))

        updated = manager.update_plan(
            plan.id,
            ReadingPlanUpdate(name="Updated", description="New description")
        )

        assert updated.name == "Updated"
        assert updated.description == "New description"

    def test_delete_plan(self, manager):
        """Test deleting a plan."""
        plan = manager.create_plan(ReadingPlanCreate(name="To Delete"))

        result = manager.delete_plan(plan.id)
        assert result is True

        assert manager.get_plan(plan.id) is None

    def test_activate_plan(self, manager):
        """Test activating a plan."""
        plan = manager.create_plan(ReadingPlanCreate(name="Draft Plan"))
        assert plan.status == PlanStatus.DRAFT

        activated = manager.activate_plan(plan.id)
        assert activated.status == PlanStatus.ACTIVE

    def test_complete_plan(self, manager):
        """Test completing a plan."""
        plan = manager.create_plan(ReadingPlanCreate(name="To Complete"))

        completed = manager.complete_plan(plan.id)
        assert completed.status == PlanStatus.COMPLETED


class TestPlannedBookCRUD:
    """Tests for planned book CRUD operations."""

    def test_add_book_to_plan(self, manager, sample_books):
        """Test adding a book to a plan."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))
        book = sample_books[0]

        planned = manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(book.id),
            plan_id=plan.id,
        ))

        assert planned is not None
        assert planned.book_title == book.title
        assert planned.plan_id == plan.id

    def test_add_book_with_deadline(self, manager, sample_books):
        """Test adding a book with a deadline."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))
        book = sample_books[0]
        deadline = date.today() + timedelta(days=14)

        planned = manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(book.id),
            plan_id=plan.id,
            target_end_date=deadline,
        ))

        assert planned.target_end_date == deadline
        assert planned.days_until_deadline == 14

    def test_add_book_updates_plan_count(self, manager, sample_books):
        """Test that adding books updates plan count."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))

        for i in range(3):
            manager.add_book_to_plan(PlannedBookCreate(
                book_id=UUID(sample_books[i].id),
                plan_id=plan.id,
            ))

        updated_plan = manager.get_plan(plan.id)
        assert updated_plan.books_planned == 3

    def test_get_books_in_plan(self, manager, sample_books):
        """Test getting books in a plan."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))

        for book in sample_books[:3]:
            manager.add_book_to_plan(PlannedBookCreate(
                book_id=UUID(book.id),
                plan_id=plan.id,
            ))

        books = manager.get_books_in_plan(plan.id)
        assert len(books) == 3

    def test_update_planned_book(self, manager, sample_books):
        """Test updating a planned book."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))
        book = sample_books[0]

        planned = manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(book.id),
            plan_id=plan.id,
        ))

        deadline = date.today() + timedelta(days=7)
        updated = manager.update_planned_book(
            planned.id,
            PlannedBookUpdate(
                target_end_date=deadline,
                priority=1,
            )
        )

        assert updated.target_end_date == deadline
        assert updated.priority == 1

    def test_remove_book_from_plan(self, manager, sample_books):
        """Test removing a book from a plan."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))
        book = sample_books[0]

        planned = manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(book.id),
            plan_id=plan.id,
        ))

        result = manager.remove_book_from_plan(planned.id)
        assert result is True

        books = manager.get_books_in_plan(plan.id)
        assert len(books) == 0

    def test_mark_planned_book_started(self, manager, sample_books):
        """Test marking a planned book as started."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))
        book = sample_books[0]

        planned = manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(book.id),
            plan_id=plan.id,
        ))

        started = manager.mark_planned_book_started(planned.id)
        assert started.actual_start_date == date.today()

    def test_mark_planned_book_completed(self, manager, sample_books):
        """Test marking a planned book as completed."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))
        book = sample_books[0]

        planned = manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(book.id),
            plan_id=plan.id,
        ))

        completed = manager.mark_planned_book_completed(planned.id)
        assert completed.actual_end_date == date.today()
        assert completed.is_completed is True

    def test_overdue_detection(self, manager, sample_books):
        """Test overdue detection for planned books."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))
        book = sample_books[0]

        # Past deadline
        past_deadline = date.today() - timedelta(days=5)
        planned = manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(book.id),
            plan_id=plan.id,
            target_end_date=past_deadline,
        ))

        assert planned.is_overdue is True
        assert planned.days_until_deadline == -5


class TestScheduleEntryCRUD:
    """Tests for schedule entry CRUD operations."""

    def test_create_schedule_entry(self, manager):
        """Test creating a schedule entry."""
        entry = manager.create_schedule_entry(ScheduleEntryCreate(
            name="Morning Reading",
            duration_minutes=30,
        ))

        assert entry is not None
        assert entry.name == "Morning Reading"
        assert entry.duration_minutes == 30
        assert entry.is_active is True

    def test_create_schedule_with_time(self, manager):
        """Test creating a schedule with preferred time."""
        entry = manager.create_schedule_entry(ScheduleEntryCreate(
            name="Evening Reading",
            preferred_time=time(20, 0),
            duration_minutes=45,
        ))

        assert entry.preferred_time == time(20, 0)

    def test_create_schedule_with_frequency(self, manager):
        """Test creating a schedule with frequency."""
        entry = manager.create_schedule_entry(ScheduleEntryCreate(
            name="Weekend Reading",
            frequency=ScheduleFrequency.WEEKENDS,
            duration_minutes=60,
        ))

        assert entry.frequency == ScheduleFrequency.WEEKENDS

    def test_create_schedule_with_days(self, manager):
        """Test creating a schedule with specific days."""
        entry = manager.create_schedule_entry(ScheduleEntryCreate(
            name="MWF Reading",
            frequency=ScheduleFrequency.CUSTOM,
            days_of_week=[0, 2, 4],  # Mon, Wed, Fri
            duration_minutes=30,
        ))

        assert entry.days_of_week == [0, 2, 4]

    def test_get_schedule_entry(self, manager):
        """Test getting a schedule entry."""
        entry = manager.create_schedule_entry(ScheduleEntryCreate(
            name="Test Schedule",
            duration_minutes=30,
        ))

        retrieved = manager.get_schedule_entry(entry.id)
        assert retrieved is not None
        assert retrieved.id == entry.id

    def test_get_all_schedule_entries(self, manager):
        """Test getting all schedule entries."""
        manager.create_schedule_entry(ScheduleEntryCreate(name="Schedule 1", duration_minutes=30))
        manager.create_schedule_entry(ScheduleEntryCreate(name="Schedule 2", duration_minutes=45))

        entries = manager.get_all_schedule_entries()
        assert len(entries) == 2

    def test_get_active_entries_only(self, manager):
        """Test getting only active entries."""
        entry1 = manager.create_schedule_entry(ScheduleEntryCreate(name="Active", duration_minutes=30))
        entry2 = manager.create_schedule_entry(ScheduleEntryCreate(name="Inactive", duration_minutes=30))
        manager.update_schedule_entry(entry2.id, ScheduleEntryUpdate(is_active=False))

        entries = manager.get_all_schedule_entries(active_only=True)
        assert len(entries) == 1
        assert entries[0].name == "Active"

    def test_update_schedule_entry(self, manager):
        """Test updating a schedule entry."""
        entry = manager.create_schedule_entry(ScheduleEntryCreate(
            name="Original",
            duration_minutes=30,
        ))

        updated = manager.update_schedule_entry(
            entry.id,
            ScheduleEntryUpdate(name="Updated", duration_minutes=60)
        )

        assert updated.name == "Updated"
        assert updated.duration_minutes == 60

    def test_delete_schedule_entry(self, manager):
        """Test deleting a schedule entry."""
        entry = manager.create_schedule_entry(ScheduleEntryCreate(
            name="To Delete",
            duration_minutes=30,
        ))

        result = manager.delete_schedule_entry(entry.id)
        assert result is True

        assert manager.get_schedule_entry(entry.id) is None


class TestReminderCRUD:
    """Tests for reminder CRUD operations."""

    def test_create_reminder(self, manager):
        """Test creating a reminder."""
        reminder = manager.create_reminder(ReminderCreate(
            reminder_type=ReminderType.READING_TIME,
            reminder_time=time(20, 0),
        ))

        assert reminder is not None
        assert reminder.reminder_type == ReminderType.READING_TIME
        assert reminder.reminder_time == time(20, 0)

    def test_create_reminder_with_message(self, manager):
        """Test creating a reminder with message."""
        reminder = manager.create_reminder(ReminderCreate(
            reminder_type=ReminderType.READING_TIME,
            reminder_time=time(21, 0),
            message="Time to read!",
        ))

        assert reminder.message == "Time to read!"

    def test_create_reminder_with_days(self, manager):
        """Test creating a reminder for specific days."""
        reminder = manager.create_reminder(ReminderCreate(
            reminder_type=ReminderType.STREAK,
            reminder_time=time(19, 0),
            days_of_week=[0, 1, 2, 3, 4],  # Weekdays
        ))

        assert reminder.days_of_week == [0, 1, 2, 3, 4]

    def test_get_reminder(self, manager):
        """Test getting a reminder."""
        reminder = manager.create_reminder(ReminderCreate(
            reminder_type=ReminderType.READING_TIME,
            reminder_time=time(20, 0),
        ))

        retrieved = manager.get_reminder(reminder.id)
        assert retrieved is not None
        assert retrieved.id == reminder.id

    def test_get_all_reminders(self, manager):
        """Test getting all reminders."""
        manager.create_reminder(ReminderCreate(
            reminder_type=ReminderType.READING_TIME,
            reminder_time=time(20, 0),
        ))
        manager.create_reminder(ReminderCreate(
            reminder_type=ReminderType.STREAK,
            reminder_time=time(21, 0),
        ))

        reminders = manager.get_all_reminders()
        assert len(reminders) == 2

    def test_update_reminder(self, manager):
        """Test updating a reminder."""
        reminder = manager.create_reminder(ReminderCreate(
            reminder_type=ReminderType.READING_TIME,
            reminder_time=time(20, 0),
        ))

        updated = manager.update_reminder(
            reminder.id,
            ReminderUpdate(message="Updated message", reminder_time=time(21, 30))
        )

        assert updated.message == "Updated message"
        assert updated.reminder_time == time(21, 30)

    def test_delete_reminder(self, manager):
        """Test deleting a reminder."""
        reminder = manager.create_reminder(ReminderCreate(
            reminder_type=ReminderType.READING_TIME,
            reminder_time=time(20, 0),
        ))

        result = manager.delete_reminder(reminder.id)
        assert result is True

        assert manager.get_reminder(reminder.id) is None


class TestPlanProgress:
    """Tests for plan progress tracking."""

    def test_get_plan_progress(self, manager, sample_books):
        """Test getting plan progress."""
        plan = manager.create_plan(ReadingPlanCreate(
            name="Progress Plan",
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
        ))

        for book in sample_books[:3]:
            manager.add_book_to_plan(PlannedBookCreate(
                book_id=UUID(book.id),
                plan_id=plan.id,
            ))

        progress = manager.get_plan_progress(plan.id)

        assert progress is not None
        assert progress.total_books == 3
        assert progress.completed_books == 0
        assert progress.days_elapsed == 10
        assert progress.days_remaining == 20

    def test_progress_with_completed_books(self, manager, sample_books):
        """Test progress with completed books."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))

        planned1 = manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(sample_books[0].id),
            plan_id=plan.id,
        ))
        manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(sample_books[1].id),
            plan_id=plan.id,
        ))

        manager.mark_planned_book_completed(planned1.id)

        progress = manager.get_plan_progress(plan.id)
        assert progress.completed_books == 1
        assert progress.not_started_books == 1


class TestDeadlines:
    """Tests for deadline tracking."""

    def test_get_upcoming_deadlines(self, manager, sample_books):
        """Test getting upcoming deadlines."""
        plan = manager.create_plan(ReadingPlanCreate(name="Deadline Plan"))

        manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(sample_books[0].id),
            plan_id=plan.id,
            target_end_date=date.today() + timedelta(days=7),
        ))
        manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(sample_books[1].id),
            plan_id=plan.id,
            target_end_date=date.today() + timedelta(days=14),
        ))

        deadlines = manager.get_upcoming_deadlines(days=30)
        assert len(deadlines) == 2

    def test_deadlines_sorted_by_date(self, manager, sample_books):
        """Test that deadlines are sorted by date."""
        plan = manager.create_plan(ReadingPlanCreate(name="Deadline Plan"))

        # Add in reverse order
        manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(sample_books[0].id),
            plan_id=plan.id,
            target_end_date=date.today() + timedelta(days=14),
        ))
        manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(sample_books[1].id),
            plan_id=plan.id,
            target_end_date=date.today() + timedelta(days=7),
        ))

        deadlines = manager.get_upcoming_deadlines()
        assert deadlines[0].days_remaining < deadlines[1].days_remaining

    def test_overdue_deadlines_included(self, manager, sample_books):
        """Test that overdue deadlines are included."""
        plan = manager.create_plan(ReadingPlanCreate(name="Deadline Plan"))

        manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(sample_books[0].id),
            plan_id=plan.id,
            target_end_date=date.today() - timedelta(days=5),
        ))

        deadlines = manager.get_upcoming_deadlines()
        assert len(deadlines) == 1
        assert deadlines[0].days_remaining < 0


class TestScheduleSummary:
    """Tests for schedule summary."""

    def test_get_schedule_summary(self, manager):
        """Test getting schedule summary."""
        manager.create_plan(ReadingPlanCreate(name="Active Plan"))
        plan = manager.get_all_plans()[0]
        manager.activate_plan(plan.id)

        summary = manager.get_schedule_summary()

        assert summary is not None
        assert summary.active_plans == 1

    def test_summary_with_schedules(self, manager):
        """Test summary includes schedule info."""
        manager.create_schedule_entry(ScheduleEntryCreate(
            name="Daily Reading",
            duration_minutes=30,
        ))

        summary = manager.get_schedule_summary()
        assert len(summary.this_week_schedule.entries) == 1


class TestEdgeCases:
    """Tests for edge cases."""

    def test_plan_with_no_books(self, manager):
        """Test plan progress with no books."""
        plan = manager.create_plan(ReadingPlanCreate(name="Empty Plan"))
        progress = manager.get_plan_progress(plan.id)

        assert progress.total_books == 0
        assert progress.on_track is True

    def test_duplicate_book_in_plan(self, manager, sample_books):
        """Test adding same book twice returns existing."""
        plan = manager.create_plan(ReadingPlanCreate(name="Test Plan"))
        book = sample_books[0]

        planned1 = manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(book.id),
            plan_id=plan.id,
        ))
        planned2 = manager.add_book_to_plan(PlannedBookCreate(
            book_id=UUID(book.id),
            plan_id=plan.id,
        ))

        assert planned1.id == planned2.id

    def test_plan_progress_calculation(self, manager, sample_books):
        """Test plan progress percentage calculation."""
        plan = manager.create_plan(ReadingPlanCreate(
            name="Test Plan",
            target_books=4,
        ))

        for book in sample_books[:4]:
            manager.add_book_to_plan(PlannedBookCreate(
                book_id=UUID(book.id),
                plan_id=plan.id,
            ))

        books = manager.get_books_in_plan(plan.id)
        manager.mark_planned_book_completed(books[0].id)
        manager.mark_planned_book_completed(books[1].id)

        plan_response = manager.get_plan(plan.id)
        assert plan_response.progress_percentage == 50.0

    def test_schedule_next_occurrence_daily(self, manager):
        """Test next occurrence for daily schedule."""
        entry = manager.create_schedule_entry(ScheduleEntryCreate(
            name="Daily",
            frequency=ScheduleFrequency.DAILY,
            duration_minutes=30,
        ))

        assert entry.next_occurrence == date.today()

    def test_reminder_default_all_days(self, manager):
        """Test reminder without days_of_week covers all days."""
        reminder = manager.create_reminder(ReminderCreate(
            reminder_type=ReminderType.READING_TIME,
            reminder_time=time(20, 0),
        ))

        # No specific days means all days, returned as None
        assert reminder.days_of_week is None
