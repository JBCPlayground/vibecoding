"""Manager for reading schedules and planning."""

import json
from datetime import date, datetime, time, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import and_

from ..db.sqlite import Database
from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from .models import ReadingPlan, PlannedBook, ScheduleEntry, Reminder
from .schemas import (
    PlanStatus,
    ScheduleFrequency,
    ReminderType,
    ReadingPlanCreate,
    ReadingPlanUpdate,
    ReadingPlanResponse,
    PlannedBookCreate,
    PlannedBookUpdate,
    PlannedBookResponse,
    ScheduleEntryCreate,
    ScheduleEntryUpdate,
    ScheduleEntryResponse,
    ReminderCreate,
    ReminderUpdate,
    ReminderResponse,
    PlanProgress,
    WeeklySchedule,
    UpcomingDeadline,
    ScheduleSummary,
)


class ScheduleManager:
    """Manager for reading schedules and planning."""

    def __init__(self, db: Database):
        """Initialize the schedule manager.

        Args:
            db: Database instance
        """
        self.db = db

    # ========================================================================
    # Reading Plan CRUD
    # ========================================================================

    def create_plan(self, plan_data: ReadingPlanCreate) -> ReadingPlanResponse:
        """Create a new reading plan.

        Args:
            plan_data: Plan creation data

        Returns:
            Created plan response
        """
        with self.db.get_session() as session:
            plan = ReadingPlan(
                name=plan_data.name,
                description=plan_data.description,
                start_date=plan_data.start_date.isoformat() if plan_data.start_date else None,
                end_date=plan_data.end_date.isoformat() if plan_data.end_date else None,
                target_books=plan_data.target_books,
                target_pages=plan_data.target_pages,
                status=PlanStatus.DRAFT.value,
            )
            session.add(plan)
            session.commit()
            session.refresh(plan)

            return self._plan_to_response(plan, session)

    def get_plan(self, plan_id: UUID) -> Optional[ReadingPlanResponse]:
        """Get a reading plan by ID.

        Args:
            plan_id: Plan UUID

        Returns:
            Plan response or None
        """
        with self.db.get_session() as session:
            plan = session.query(ReadingPlan).filter(
                ReadingPlan.id == str(plan_id)
            ).first()

            if not plan:
                return None

            return self._plan_to_response(plan, session)

    def get_all_plans(
        self,
        status: Optional[PlanStatus] = None,
        include_completed: bool = False,
    ) -> list[ReadingPlanResponse]:
        """Get all reading plans.

        Args:
            status: Filter by status
            include_completed: Include completed plans

        Returns:
            List of plan responses
        """
        with self.db.get_session() as session:
            query = session.query(ReadingPlan)

            if status:
                query = query.filter(ReadingPlan.status == status.value)
            elif not include_completed:
                query = query.filter(
                    ReadingPlan.status.notin_([
                        PlanStatus.COMPLETED.value,
                        PlanStatus.CANCELLED.value,
                    ])
                )

            plans = query.order_by(ReadingPlan.created_at.desc()).all()

            return [self._plan_to_response(plan, session) for plan in plans]

    def update_plan(
        self, plan_id: UUID, update_data: ReadingPlanUpdate
    ) -> Optional[ReadingPlanResponse]:
        """Update a reading plan.

        Args:
            plan_id: Plan UUID
            update_data: Update data

        Returns:
            Updated plan response or None
        """
        with self.db.get_session() as session:
            plan = session.query(ReadingPlan).filter(
                ReadingPlan.id == str(plan_id)
            ).first()

            if not plan:
                return None

            if update_data.name is not None:
                plan.name = update_data.name
            if update_data.description is not None:
                plan.description = update_data.description
            if update_data.start_date is not None:
                plan.start_date = update_data.start_date.isoformat()
            if update_data.end_date is not None:
                plan.end_date = update_data.end_date.isoformat()
            if update_data.target_books is not None:
                plan.target_books = update_data.target_books
            if update_data.target_pages is not None:
                plan.target_pages = update_data.target_pages
            if update_data.status is not None:
                plan.status = update_data.status.value

            plan.updated_at = datetime.now().isoformat()
            session.commit()
            session.refresh(plan)

            return self._plan_to_response(plan, session)

    def delete_plan(self, plan_id: UUID) -> bool:
        """Delete a reading plan.

        Args:
            plan_id: Plan UUID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            plan = session.query(ReadingPlan).filter(
                ReadingPlan.id == str(plan_id)
            ).first()

            if not plan:
                return False

            session.delete(plan)
            session.commit()
            return True

    def activate_plan(self, plan_id: UUID) -> Optional[ReadingPlanResponse]:
        """Activate a reading plan.

        Args:
            plan_id: Plan UUID

        Returns:
            Updated plan response
        """
        return self.update_plan(
            plan_id, ReadingPlanUpdate(status=PlanStatus.ACTIVE)
        )

    def complete_plan(self, plan_id: UUID) -> Optional[ReadingPlanResponse]:
        """Mark a plan as completed.

        Args:
            plan_id: Plan UUID

        Returns:
            Updated plan response
        """
        return self.update_plan(
            plan_id, ReadingPlanUpdate(status=PlanStatus.COMPLETED)
        )

    def _plan_to_response(self, plan: ReadingPlan, session) -> ReadingPlanResponse:
        """Convert plan model to response."""
        # Get planned books stats
        planned_books = session.query(PlannedBook).filter(
            PlannedBook.plan_id == plan.id
        ).all()

        books_planned = len(planned_books)
        books_completed = sum(
            1 for pb in planned_books if pb.actual_end_date is not None
        )

        # Calculate pages
        pages_planned = 0
        pages_read = 0
        for pb in planned_books:
            book = session.query(Book).filter(Book.id == pb.book_id).first()
            if book and book.page_count:
                pages_planned += book.page_count
                if pb.actual_end_date:
                    pages_read += book.page_count

        # Calculate progress
        if plan.target_books:
            progress = (books_completed / plan.target_books) * 100
        elif plan.target_pages:
            progress = (pages_read / plan.target_pages) * 100
        elif books_planned > 0:
            progress = (books_completed / books_planned) * 100
        else:
            progress = 0

        # Days remaining
        days_remaining = None
        if plan.end_date:
            end = date.fromisoformat(plan.end_date)
            days_remaining = (end - date.today()).days

        # On track calculation
        on_track = True
        if plan.end_date and plan.start_date:
            start = date.fromisoformat(plan.start_date)
            end = date.fromisoformat(plan.end_date)
            total_days = (end - start).days or 1
            elapsed_days = (date.today() - start).days
            expected_progress = (elapsed_days / total_days) * 100
            on_track = progress >= expected_progress * 0.9  # 90% tolerance

        return ReadingPlanResponse(
            id=UUID(plan.id),
            name=plan.name,
            description=plan.description,
            start_date=date.fromisoformat(plan.start_date) if plan.start_date else None,
            end_date=date.fromisoformat(plan.end_date) if plan.end_date else None,
            target_books=plan.target_books,
            target_pages=plan.target_pages,
            status=PlanStatus(plan.status),
            books_planned=books_planned,
            books_completed=books_completed,
            pages_planned=pages_planned,
            pages_read=pages_read,
            progress_percentage=min(progress, 100),
            days_remaining=days_remaining,
            on_track=on_track,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    # ========================================================================
    # Planned Book CRUD
    # ========================================================================

    def add_book_to_plan(
        self, book_data: PlannedBookCreate
    ) -> Optional[PlannedBookResponse]:
        """Add a book to a reading plan.

        Args:
            book_data: Planned book data

        Returns:
            Planned book response or None
        """
        with self.db.get_session() as session:
            # Verify plan and book exist
            plan = session.query(ReadingPlan).filter(
                ReadingPlan.id == str(book_data.plan_id)
            ).first()
            book = session.query(Book).filter(
                Book.id == str(book_data.book_id)
            ).first()

            if not plan or not book:
                return None

            # Check if already in plan
            existing = session.query(PlannedBook).filter(
                PlannedBook.plan_id == str(book_data.plan_id),
                PlannedBook.book_id == str(book_data.book_id),
            ).first()

            if existing:
                return self._planned_book_to_response(existing, session)

            # Get next position if not specified
            position = book_data.position
            if position == 1:
                max_pos = session.query(PlannedBook).filter(
                    PlannedBook.plan_id == str(book_data.plan_id)
                ).count()
                position = max_pos + 1

            planned = PlannedBook(
                book_id=str(book_data.book_id),
                plan_id=str(book_data.plan_id),
                position=position,
                target_start_date=book_data.target_start_date.isoformat() if book_data.target_start_date else None,
                target_end_date=book_data.target_end_date.isoformat() if book_data.target_end_date else None,
                priority=book_data.priority,
                notes=book_data.notes,
            )

            # Set actual start if book is being read
            if book.status == BookStatus.READING.value and book.date_started:
                planned.actual_start_date = book.date_started

            # Set actual end if book is completed
            if book.status == BookStatus.COMPLETED.value and book.date_finished:
                planned.actual_end_date = book.date_finished

            session.add(planned)
            session.commit()
            session.refresh(planned)

            return self._planned_book_to_response(planned, session)

    def get_planned_book(
        self, planned_book_id: UUID
    ) -> Optional[PlannedBookResponse]:
        """Get a planned book by ID.

        Args:
            planned_book_id: Planned book UUID

        Returns:
            Planned book response or None
        """
        with self.db.get_session() as session:
            planned = session.query(PlannedBook).filter(
                PlannedBook.id == str(planned_book_id)
            ).first()

            if not planned:
                return None

            return self._planned_book_to_response(planned, session)

    def get_books_in_plan(
        self, plan_id: UUID, completed_only: bool = False
    ) -> list[PlannedBookResponse]:
        """Get all books in a plan.

        Args:
            plan_id: Plan UUID
            completed_only: Only return completed books

        Returns:
            List of planned book responses
        """
        with self.db.get_session() as session:
            query = session.query(PlannedBook).filter(
                PlannedBook.plan_id == str(plan_id)
            )

            if completed_only:
                query = query.filter(PlannedBook.actual_end_date.isnot(None))

            planned_books = query.order_by(PlannedBook.position).all()

            return [
                self._planned_book_to_response(pb, session)
                for pb in planned_books
            ]

    def update_planned_book(
        self, planned_book_id: UUID, update_data: PlannedBookUpdate
    ) -> Optional[PlannedBookResponse]:
        """Update a planned book.

        Args:
            planned_book_id: Planned book UUID
            update_data: Update data

        Returns:
            Updated planned book response or None
        """
        with self.db.get_session() as session:
            planned = session.query(PlannedBook).filter(
                PlannedBook.id == str(planned_book_id)
            ).first()

            if not planned:
                return None

            if update_data.position is not None:
                planned.position = update_data.position
            if update_data.target_start_date is not None:
                planned.target_start_date = update_data.target_start_date.isoformat()
            if update_data.target_end_date is not None:
                planned.target_end_date = update_data.target_end_date.isoformat()
            if update_data.priority is not None:
                planned.priority = update_data.priority
            if update_data.notes is not None:
                planned.notes = update_data.notes

            session.commit()
            session.refresh(planned)

            return self._planned_book_to_response(planned, session)

    def remove_book_from_plan(self, planned_book_id: UUID) -> bool:
        """Remove a book from a plan.

        Args:
            planned_book_id: Planned book UUID

        Returns:
            True if removed
        """
        with self.db.get_session() as session:
            planned = session.query(PlannedBook).filter(
                PlannedBook.id == str(planned_book_id)
            ).first()

            if not planned:
                return False

            session.delete(planned)
            session.commit()
            return True

    def mark_planned_book_started(
        self, planned_book_id: UUID, start_date: Optional[date] = None
    ) -> Optional[PlannedBookResponse]:
        """Mark a planned book as started.

        Args:
            planned_book_id: Planned book UUID
            start_date: Start date (defaults to today)

        Returns:
            Updated planned book response
        """
        with self.db.get_session() as session:
            planned = session.query(PlannedBook).filter(
                PlannedBook.id == str(planned_book_id)
            ).first()

            if not planned:
                return None

            planned.actual_start_date = (start_date or date.today()).isoformat()
            session.commit()
            session.refresh(planned)

            return self._planned_book_to_response(planned, session)

    def mark_planned_book_completed(
        self, planned_book_id: UUID, end_date: Optional[date] = None
    ) -> Optional[PlannedBookResponse]:
        """Mark a planned book as completed.

        Args:
            planned_book_id: Planned book UUID
            end_date: End date (defaults to today)

        Returns:
            Updated planned book response
        """
        with self.db.get_session() as session:
            planned = session.query(PlannedBook).filter(
                PlannedBook.id == str(planned_book_id)
            ).first()

            if not planned:
                return None

            planned.actual_end_date = (end_date or date.today()).isoformat()
            if not planned.actual_start_date:
                planned.actual_start_date = planned.actual_end_date

            session.commit()
            session.refresh(planned)

            return self._planned_book_to_response(planned, session)

    def _planned_book_to_response(
        self, planned: PlannedBook, session
    ) -> PlannedBookResponse:
        """Convert planned book model to response."""
        book = session.query(Book).filter(Book.id == planned.book_id).first()

        is_overdue = False
        days_until_deadline = None
        if planned.target_end_date and not planned.actual_end_date:
            deadline = date.fromisoformat(planned.target_end_date)
            days_until_deadline = (deadline - date.today()).days
            is_overdue = days_until_deadline < 0

        return PlannedBookResponse(
            id=UUID(planned.id),
            book_id=UUID(planned.book_id),
            plan_id=UUID(planned.plan_id),
            book_title=book.title if book else "Unknown",
            book_author=book.author if book else None,
            position=planned.position,
            target_start_date=date.fromisoformat(planned.target_start_date) if planned.target_start_date else None,
            target_end_date=date.fromisoformat(planned.target_end_date) if planned.target_end_date else None,
            actual_start_date=date.fromisoformat(planned.actual_start_date) if planned.actual_start_date else None,
            actual_end_date=date.fromisoformat(planned.actual_end_date) if planned.actual_end_date else None,
            priority=planned.priority,
            notes=planned.notes,
            is_completed=planned.actual_end_date is not None,
            is_overdue=is_overdue,
            days_until_deadline=days_until_deadline,
            page_count=book.page_count if book else None,
        )

    # ========================================================================
    # Schedule Entry CRUD
    # ========================================================================

    def create_schedule_entry(
        self, entry_data: ScheduleEntryCreate
    ) -> ScheduleEntryResponse:
        """Create a schedule entry.

        Args:
            entry_data: Schedule entry data

        Returns:
            Schedule entry response
        """
        with self.db.get_session() as session:
            entry = ScheduleEntry(
                name=entry_data.name,
                frequency=entry_data.frequency.value,
                days_of_week=json.dumps(entry_data.days_of_week) if entry_data.days_of_week else None,
                preferred_time=entry_data.preferred_time.isoformat() if entry_data.preferred_time else None,
                duration_minutes=entry_data.duration_minutes,
                book_id=str(entry_data.book_id) if entry_data.book_id else None,
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)

            return self._schedule_entry_to_response(entry, session)

    def get_schedule_entry(
        self, entry_id: UUID
    ) -> Optional[ScheduleEntryResponse]:
        """Get a schedule entry by ID.

        Args:
            entry_id: Entry UUID

        Returns:
            Schedule entry response or None
        """
        with self.db.get_session() as session:
            entry = session.query(ScheduleEntry).filter(
                ScheduleEntry.id == str(entry_id)
            ).first()

            if not entry:
                return None

            return self._schedule_entry_to_response(entry, session)

    def get_all_schedule_entries(
        self, active_only: bool = True
    ) -> list[ScheduleEntryResponse]:
        """Get all schedule entries.

        Args:
            active_only: Only return active entries

        Returns:
            List of schedule entry responses
        """
        with self.db.get_session() as session:
            query = session.query(ScheduleEntry)

            if active_only:
                query = query.filter(ScheduleEntry.is_active == True)

            entries = query.order_by(ScheduleEntry.preferred_time).all()

            return [
                self._schedule_entry_to_response(entry, session)
                for entry in entries
            ]

    def update_schedule_entry(
        self, entry_id: UUID, update_data: ScheduleEntryUpdate
    ) -> Optional[ScheduleEntryResponse]:
        """Update a schedule entry.

        Args:
            entry_id: Entry UUID
            update_data: Update data

        Returns:
            Updated schedule entry response or None
        """
        with self.db.get_session() as session:
            entry = session.query(ScheduleEntry).filter(
                ScheduleEntry.id == str(entry_id)
            ).first()

            if not entry:
                return None

            if update_data.name is not None:
                entry.name = update_data.name
            if update_data.frequency is not None:
                entry.frequency = update_data.frequency.value
            if update_data.days_of_week is not None:
                entry.days_of_week = json.dumps(update_data.days_of_week)
            if update_data.preferred_time is not None:
                entry.preferred_time = update_data.preferred_time.isoformat()
            if update_data.duration_minutes is not None:
                entry.duration_minutes = update_data.duration_minutes
            if update_data.book_id is not None:
                entry.book_id = str(update_data.book_id)
            if update_data.is_active is not None:
                entry.is_active = update_data.is_active

            session.commit()
            session.refresh(entry)

            return self._schedule_entry_to_response(entry, session)

    def delete_schedule_entry(self, entry_id: UUID) -> bool:
        """Delete a schedule entry.

        Args:
            entry_id: Entry UUID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            entry = session.query(ScheduleEntry).filter(
                ScheduleEntry.id == str(entry_id)
            ).first()

            if not entry:
                return False

            session.delete(entry)
            session.commit()
            return True

    def _schedule_entry_to_response(
        self, entry: ScheduleEntry, session
    ) -> ScheduleEntryResponse:
        """Convert schedule entry model to response."""
        book_title = None
        if entry.book_id:
            book = session.query(Book).filter(Book.id == entry.book_id).first()
            book_title = book.title if book else None

        days = entry.get_days_of_week()
        next_occurrence = self._calculate_next_occurrence(entry)

        return ScheduleEntryResponse(
            id=UUID(entry.id),
            name=entry.name,
            frequency=ScheduleFrequency(entry.frequency),
            days_of_week=days if days else None,
            preferred_time=time.fromisoformat(entry.preferred_time) if entry.preferred_time else None,
            duration_minutes=entry.duration_minutes,
            book_id=UUID(entry.book_id) if entry.book_id else None,
            book_title=book_title,
            is_active=entry.is_active,
            next_occurrence=next_occurrence,
            created_at=entry.created_at,
        )

    def _calculate_next_occurrence(self, entry: ScheduleEntry) -> Optional[date]:
        """Calculate next occurrence of a schedule entry."""
        if not entry.is_active:
            return None

        today = date.today()
        today_weekday = today.weekday()

        if entry.frequency == ScheduleFrequency.DAILY.value:
            return today

        if entry.frequency == ScheduleFrequency.WEEKDAYS.value:
            if today_weekday < 5:  # Mon-Fri
                return today
            # Next Monday
            days_until_monday = 7 - today_weekday
            return today + timedelta(days=days_until_monday)

        if entry.frequency == ScheduleFrequency.WEEKENDS.value:
            if today_weekday >= 5:  # Sat-Sun
                return today
            # Next Saturday
            days_until_saturday = 5 - today_weekday
            return today + timedelta(days=days_until_saturday)

        if entry.frequency == ScheduleFrequency.WEEKLY.value:
            days = entry.get_days_of_week()
            if not days:
                return today

            # Find next day in the list
            for i in range(7):
                check_day = (today_weekday + i) % 7
                if check_day in days:
                    return today + timedelta(days=i)

        if entry.frequency == ScheduleFrequency.CUSTOM.value:
            days = entry.get_days_of_week()
            if not days:
                return None

            for i in range(7):
                check_day = (today_weekday + i) % 7
                if check_day in days:
                    return today + timedelta(days=i)

        return None

    # ========================================================================
    # Reminder CRUD
    # ========================================================================

    def create_reminder(self, reminder_data: ReminderCreate) -> ReminderResponse:
        """Create a reminder.

        Args:
            reminder_data: Reminder data

        Returns:
            Reminder response
        """
        with self.db.get_session() as session:
            reminder = Reminder(
                reminder_type=reminder_data.reminder_type.value,
                message=reminder_data.message,
                reminder_time=reminder_data.reminder_time.isoformat(),
                days_of_week=json.dumps(reminder_data.days_of_week) if reminder_data.days_of_week else None,
                book_id=str(reminder_data.book_id) if reminder_data.book_id else None,
                plan_id=str(reminder_data.plan_id) if reminder_data.plan_id else None,
            )
            session.add(reminder)
            session.commit()
            session.refresh(reminder)

            return self._reminder_to_response(reminder)

    def get_reminder(self, reminder_id: UUID) -> Optional[ReminderResponse]:
        """Get a reminder by ID.

        Args:
            reminder_id: Reminder UUID

        Returns:
            Reminder response or None
        """
        with self.db.get_session() as session:
            reminder = session.query(Reminder).filter(
                Reminder.id == str(reminder_id)
            ).first()

            if not reminder:
                return None

            return self._reminder_to_response(reminder)

    def get_all_reminders(
        self, active_only: bool = True
    ) -> list[ReminderResponse]:
        """Get all reminders.

        Args:
            active_only: Only return active reminders

        Returns:
            List of reminder responses
        """
        with self.db.get_session() as session:
            query = session.query(Reminder)

            if active_only:
                query = query.filter(Reminder.is_active == True)

            reminders = query.order_by(Reminder.reminder_time).all()

            return [self._reminder_to_response(r) for r in reminders]

    def update_reminder(
        self, reminder_id: UUID, update_data: ReminderUpdate
    ) -> Optional[ReminderResponse]:
        """Update a reminder.

        Args:
            reminder_id: Reminder UUID
            update_data: Update data

        Returns:
            Updated reminder response or None
        """
        with self.db.get_session() as session:
            reminder = session.query(Reminder).filter(
                Reminder.id == str(reminder_id)
            ).first()

            if not reminder:
                return None

            if update_data.message is not None:
                reminder.message = update_data.message
            if update_data.reminder_time is not None:
                reminder.reminder_time = update_data.reminder_time.isoformat()
            if update_data.days_of_week is not None:
                reminder.days_of_week = json.dumps(update_data.days_of_week)
            if update_data.is_active is not None:
                reminder.is_active = update_data.is_active

            session.commit()
            session.refresh(reminder)

            return self._reminder_to_response(reminder)

    def delete_reminder(self, reminder_id: UUID) -> bool:
        """Delete a reminder.

        Args:
            reminder_id: Reminder UUID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            reminder = session.query(Reminder).filter(
                Reminder.id == str(reminder_id)
            ).first()

            if not reminder:
                return False

            session.delete(reminder)
            session.commit()
            return True

    def _reminder_to_response(self, reminder: Reminder) -> ReminderResponse:
        """Convert reminder model to response."""
        days = reminder.get_days_of_week()

        return ReminderResponse(
            id=UUID(reminder.id),
            reminder_type=ReminderType(reminder.reminder_type),
            message=reminder.message,
            reminder_time=time.fromisoformat(reminder.reminder_time),
            days_of_week=days if days != list(range(7)) else None,
            book_id=UUID(reminder.book_id) if reminder.book_id else None,
            plan_id=UUID(reminder.plan_id) if reminder.plan_id else None,
            is_active=reminder.is_active,
            created_at=reminder.created_at,
        )

    # ========================================================================
    # Planning Analytics
    # ========================================================================

    def get_plan_progress(self, plan_id: UUID) -> Optional[PlanProgress]:
        """Get detailed progress for a plan.

        Args:
            plan_id: Plan UUID

        Returns:
            Plan progress or None
        """
        with self.db.get_session() as session:
            plan = session.query(ReadingPlan).filter(
                ReadingPlan.id == str(plan_id)
            ).first()

            if not plan:
                return None

            planned_books = session.query(PlannedBook).filter(
                PlannedBook.plan_id == plan.id
            ).all()

            total_books = len(planned_books)
            completed_books = sum(
                1 for pb in planned_books if pb.actual_end_date
            )
            in_progress_books = sum(
                1 for pb in planned_books
                if pb.actual_start_date and not pb.actual_end_date
            )
            not_started_books = total_books - completed_books - in_progress_books

            # Calculate pages
            total_pages = 0
            pages_read = 0
            for pb in planned_books:
                book = session.query(Book).filter(Book.id == pb.book_id).first()
                if book and book.page_count:
                    total_pages += book.page_count
                    if pb.actual_end_date:
                        pages_read += book.page_count

            # Time calculations
            days_elapsed = 0
            days_remaining = 0
            if plan.start_date:
                start = date.fromisoformat(plan.start_date)
                days_elapsed = max(0, (date.today() - start).days)
            if plan.end_date:
                end = date.fromisoformat(plan.end_date)
                days_remaining = max(0, (end - date.today()).days)

            # Pace calculations
            books_per_day_needed = 0
            pages_per_day_needed = 0
            if days_remaining > 0:
                books_remaining = total_books - completed_books
                pages_remaining = total_pages - pages_read
                books_per_day_needed = books_remaining / days_remaining
                pages_per_day_needed = pages_remaining / days_remaining

            current_pace_books = 0
            current_pace_pages = 0
            if days_elapsed > 0:
                current_pace_books = completed_books / days_elapsed
                current_pace_pages = pages_read / days_elapsed

            # Projected completion
            projected_completion = None
            if current_pace_books > 0:
                books_remaining = total_books - completed_books
                days_to_complete = int(books_remaining / current_pace_books)
                projected_completion = date.today() + timedelta(days=days_to_complete)

            on_track = current_pace_books >= books_per_day_needed * 0.9 if books_per_day_needed > 0 else True

            return PlanProgress(
                plan_id=UUID(plan.id),
                plan_name=plan.name,
                total_books=total_books,
                completed_books=completed_books,
                in_progress_books=in_progress_books,
                not_started_books=not_started_books,
                total_pages=total_pages,
                pages_read=pages_read,
                days_elapsed=days_elapsed,
                days_remaining=days_remaining,
                books_per_day_needed=books_per_day_needed,
                pages_per_day_needed=pages_per_day_needed,
                current_pace_books=current_pace_books,
                current_pace_pages=current_pace_pages,
                projected_completion=projected_completion,
                on_track=on_track,
            )

    def get_upcoming_deadlines(self, days: int = 30) -> list[UpcomingDeadline]:
        """Get upcoming book deadlines.

        Args:
            days: Number of days to look ahead

        Returns:
            List of upcoming deadlines
        """
        with self.db.get_session() as session:
            cutoff = (date.today() + timedelta(days=days)).isoformat()

            planned_books = session.query(PlannedBook).filter(
                PlannedBook.target_end_date.isnot(None),
                PlannedBook.target_end_date <= cutoff,
                PlannedBook.actual_end_date.is_(None),
            ).order_by(PlannedBook.target_end_date).all()

            deadlines = []
            for pb in planned_books:
                book = session.query(Book).filter(Book.id == pb.book_id).first()
                if not book:
                    continue

                deadline = date.fromisoformat(pb.target_end_date)
                days_remaining = (deadline - date.today()).days

                # Calculate if at risk
                pages_remaining = None
                is_at_risk = False
                if book.page_count:
                    pages_remaining = book.page_count  # Full book if not tracking progress
                    if days_remaining > 0 and pages_remaining > 0:
                        pages_per_day_needed = pages_remaining / days_remaining
                        is_at_risk = pages_per_day_needed > 100  # More than 100 pages/day

                deadlines.append(UpcomingDeadline(
                    book_id=UUID(book.id),
                    book_title=book.title,
                    book_author=book.author,
                    deadline=deadline,
                    days_remaining=days_remaining,
                    pages_remaining=pages_remaining,
                    is_at_risk=is_at_risk or days_remaining < 0,
                ))

            return deadlines

    def get_schedule_summary(self) -> ScheduleSummary:
        """Get a summary of schedules and plans.

        Returns:
            Schedule summary
        """
        with self.db.get_session() as session:
            # Active plans
            active_plans = session.query(ReadingPlan).filter(
                ReadingPlan.status == PlanStatus.ACTIVE.value
            ).count()

            # Books in plans
            books_in_plans = session.query(PlannedBook).filter(
                PlannedBook.actual_end_date.is_(None)
            ).count()

            # Upcoming deadlines
            deadlines = self.get_upcoming_deadlines(14)

            # This week's schedule
            entries = self.get_all_schedule_entries(active_only=True)
            today = date.today()
            week_start = today - timedelta(days=today.weekday())

            total_minutes = sum(e.duration_minutes for e in entries)

            # Get completed minutes from reading logs this week
            week_logs = session.query(ReadingLog).filter(
                ReadingLog.date >= week_start.isoformat()
            ).all()
            completed_minutes = sum(log.duration_minutes or 0 for log in week_logs)

            weekly_schedule = WeeklySchedule(
                week_start=week_start,
                entries=entries,
                total_planned_minutes=total_minutes * 7,  # Approximate
                completed_minutes=completed_minutes,
                books_scheduled=len(set(e.book_id for e in entries if e.book_id)),
                completion_rate=(completed_minutes / (total_minutes * 7) * 100) if total_minutes > 0 else 0,
            )

            # Reading time today
            reading_time = None
            for entry in entries:
                if entry.preferred_time and entry.next_occurrence == today:
                    reading_time = entry.preferred_time
                    break

            # Current book
            current_book = session.query(Book).filter(
                Book.status == BookStatus.READING.value
            ).first()

            return ScheduleSummary(
                active_plans=active_plans,
                books_in_plans=books_in_plans,
                upcoming_deadlines=deadlines,
                this_week_schedule=weekly_schedule,
                reading_time_today=reading_time,
                current_book=current_book.title if current_book else None,
            )
