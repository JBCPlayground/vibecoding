"""Notes manager for reading notes and quotes operations."""

import random
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, or_

from ..db.models import Book
from ..db.sqlite import Database, get_db
from .models import CollectionQuote, Note, Quote, QuoteCollection
from .schemas import (
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
    CollectionWithQuotes,
    HighlightColor,
    NoteCreate,
    NoteType,
    NoteUpdate,
    NoteSummary,
    NotesStats,
    QuoteCreate,
    QuoteStats,
    QuoteSummary,
    QuoteType,
    QuoteUpdate,
    BookAnnotations,
)


class NotesManager:
    """Manages reading notes and quotes operations."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize notes manager.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    # -------------------------------------------------------------------------
    # Note CRUD
    # -------------------------------------------------------------------------

    def create_note(self, data: NoteCreate) -> Note:
        """Create a new note.

        Args:
            data: Note creation data

        Returns:
            Created note
        """
        with self.db.get_session() as session:
            # Verify book exists
            book = session.execute(
                select(Book).where(Book.id == str(data.book_id))
            ).scalar_one_or_none()
            if not book:
                raise ValueError("Book not found")

            # Convert tags list to comma-separated string
            tags_str = None
            if data.tags:
                tags_str = ",".join(data.tags)

            note = Note(
                book_id=str(data.book_id),
                note_type=data.note_type.value,
                title=data.title,
                content=data.content,
                chapter=data.chapter,
                page_number=data.page_number,
                location=data.location,
                tags=tags_str,
                is_private=data.is_private,
                is_favorite=data.is_favorite,
            )

            session.add(note)
            session.commit()
            session.refresh(note)
            session.expunge(note)

            return note

    def get_note(self, note_id: str) -> Optional[Note]:
        """Get a note by ID.

        Args:
            note_id: Note ID

        Returns:
            Note or None
        """
        with self.db.get_session() as session:
            stmt = select(Note).where(Note.id == note_id)
            note = session.execute(stmt).scalar_one_or_none()
            if note:
                session.expunge(note)
            return note

    def list_notes(
        self,
        book_id: Optional[str] = None,
        note_type: Optional[NoteType] = None,
        favorites_only: bool = False,
        include_private: bool = True,
        tag: Optional[str] = None,
        order_by: str = "created_at",
        descending: bool = True,
    ) -> list[Note]:
        """List notes with optional filters.

        Args:
            book_id: Filter by book
            note_type: Filter by type
            favorites_only: Only return favorites
            include_private: Include private notes
            tag: Filter by tag
            order_by: Field to order by
            descending: Sort descending

        Returns:
            List of notes
        """
        with self.db.get_session() as session:
            stmt = select(Note)

            if book_id:
                stmt = stmt.where(Note.book_id == book_id)
            if note_type:
                stmt = stmt.where(Note.note_type == note_type.value)
            if favorites_only:
                stmt = stmt.where(Note.is_favorite == True)  # noqa: E712
            if not include_private:
                stmt = stmt.where(Note.is_private == False)  # noqa: E712
            if tag:
                # Exact tag match in comma-separated list
                tag_lower = tag.lower()
                stmt = stmt.where(
                    or_(
                        func.lower(Note.tags) == tag_lower,
                        func.lower(Note.tags).like(f"{tag_lower},%"),
                        func.lower(Note.tags).like(f"%,{tag_lower}"),
                        func.lower(Note.tags).like(f"%,{tag_lower},%"),
                    )
                )

            # Apply ordering
            order_column = {
                "created_at": Note.created_at,
                "updated_at": Note.updated_at,
                "page_number": Note.page_number,
            }.get(order_by, Note.created_at)

            if descending:
                stmt = stmt.order_by(order_column.desc().nullslast())
            else:
                stmt = stmt.order_by(order_column.asc().nullsfirst())

            notes = session.execute(stmt).scalars().all()
            for note in notes:
                session.expunge(note)
            return list(notes)

    def update_note(self, note_id: str, data: NoteUpdate) -> Optional[Note]:
        """Update a note.

        Args:
            note_id: Note ID
            data: Update data

        Returns:
            Updated note or None
        """
        with self.db.get_session() as session:
            stmt = select(Note).where(Note.id == note_id)
            note = session.execute(stmt).scalar_one_or_none()

            if not note:
                return None

            update_data = data.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if field == "tags" and value is not None:
                    note.tags = ",".join(value) if value else None
                elif field == "note_type" and value is not None:
                    note.note_type = value.value
                elif hasattr(note, field):
                    setattr(note, field, value)

            note.updated_at = datetime.now(timezone.utc).isoformat()
            session.commit()
            session.refresh(note)
            session.expunge(note)

            return note

    def delete_note(self, note_id: str) -> bool:
        """Delete a note.

        Args:
            note_id: Note ID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            stmt = select(Note).where(Note.id == note_id)
            note = session.execute(stmt).scalar_one_or_none()

            if not note:
                return False

            session.delete(note)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Quote CRUD
    # -------------------------------------------------------------------------

    def create_quote(self, data: QuoteCreate) -> Quote:
        """Create a new quote.

        Args:
            data: Quote creation data

        Returns:
            Created quote
        """
        with self.db.get_session() as session:
            # Verify book exists
            book = session.execute(
                select(Book).where(Book.id == str(data.book_id))
            ).scalar_one_or_none()
            if not book:
                raise ValueError("Book not found")

            # Convert tags list to comma-separated string
            tags_str = None
            if data.tags:
                tags_str = ",".join(data.tags)

            quote = Quote(
                book_id=str(data.book_id),
                text=data.text,
                quote_type=data.quote_type.value,
                color=data.color.value if data.color else None,
                speaker=data.speaker,
                context=data.context,
                chapter=data.chapter,
                page_number=data.page_number,
                location=data.location,
                tags=tags_str,
                is_favorite=data.is_favorite,
            )

            session.add(quote)
            session.commit()
            session.refresh(quote)
            session.expunge(quote)

            return quote

    def get_quote(self, quote_id: str) -> Optional[Quote]:
        """Get a quote by ID.

        Args:
            quote_id: Quote ID

        Returns:
            Quote or None
        """
        with self.db.get_session() as session:
            stmt = select(Quote).where(Quote.id == quote_id)
            quote = session.execute(stmt).scalar_one_or_none()
            if quote:
                session.expunge(quote)
            return quote

    def list_quotes(
        self,
        book_id: Optional[str] = None,
        favorites_only: bool = False,
        speaker: Optional[str] = None,
        tag: Optional[str] = None,
        quote_type: Optional[QuoteType] = None,
        color: Optional[HighlightColor] = None,
        order_by: str = "created_at",
        descending: bool = True,
    ) -> list[Quote]:
        """List quotes with optional filters.

        Args:
            book_id: Filter by book
            favorites_only: Only return favorites
            speaker: Filter by speaker/character
            tag: Filter by tag
            quote_type: Filter by quote type
            color: Filter by highlight color
            order_by: Field to order by
            descending: Sort descending

        Returns:
            List of quotes
        """
        with self.db.get_session() as session:
            stmt = select(Quote)

            if book_id:
                stmt = stmt.where(Quote.book_id == book_id)
            if favorites_only:
                stmt = stmt.where(Quote.is_favorite == True)  # noqa: E712
            if speaker:
                stmt = stmt.where(func.lower(Quote.speaker).like(f"%{speaker.lower()}%"))
            if quote_type:
                stmt = stmt.where(Quote.quote_type == quote_type.value)
            if color:
                stmt = stmt.where(Quote.color == color.value)
            if tag:
                tag_lower = tag.lower()
                stmt = stmt.where(
                    or_(
                        func.lower(Quote.tags) == tag_lower,
                        func.lower(Quote.tags).like(f"{tag_lower},%"),
                        func.lower(Quote.tags).like(f"%,{tag_lower}"),
                        func.lower(Quote.tags).like(f"%,{tag_lower},%"),
                    )
                )

            # Apply ordering
            order_column = {
                "created_at": Quote.created_at,
                "updated_at": Quote.updated_at,
                "page_number": Quote.page_number,
            }.get(order_by, Quote.created_at)

            if descending:
                stmt = stmt.order_by(order_column.desc().nullslast())
            else:
                stmt = stmt.order_by(order_column.asc().nullsfirst())

            quotes = session.execute(stmt).scalars().all()
            for quote in quotes:
                session.expunge(quote)
            return list(quotes)

    def update_quote(self, quote_id: str, data: QuoteUpdate) -> Optional[Quote]:
        """Update a quote.

        Args:
            quote_id: Quote ID
            data: Update data

        Returns:
            Updated quote or None
        """
        with self.db.get_session() as session:
            stmt = select(Quote).where(Quote.id == quote_id)
            quote = session.execute(stmt).scalar_one_or_none()

            if not quote:
                return None

            update_data = data.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if field == "tags" and value is not None:
                    quote.tags = ",".join(value) if value else None
                elif field == "quote_type" and value is not None:
                    quote.quote_type = value.value
                elif field == "color" and value is not None:
                    quote.color = value.value
                elif hasattr(quote, field):
                    setattr(quote, field, value)

            quote.updated_at = datetime.now(timezone.utc).isoformat()
            session.commit()
            session.refresh(quote)
            session.expunge(quote)

            return quote

    def delete_quote(self, quote_id: str) -> bool:
        """Delete a quote.

        Args:
            quote_id: Quote ID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            stmt = select(Quote).where(Quote.id == quote_id)
            quote = session.execute(stmt).scalar_one_or_none()

            if not quote:
                return False

            session.delete(quote)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Search and Query
    # -------------------------------------------------------------------------

    def search_notes(self, query: str, include_private: bool = True) -> list[NoteSummary]:
        """Search notes by content or title.

        Args:
            query: Search query
            include_private: Include private notes

        Returns:
            List of matching note summaries
        """
        with self.db.get_session() as session:
            query_lower = f"%{query.lower()}%"
            stmt = select(Note).where(
                or_(
                    func.lower(Note.title).like(query_lower),
                    func.lower(Note.content).like(query_lower),
                    func.lower(Note.tags).like(query_lower),
                )
            )

            if not include_private:
                stmt = stmt.where(Note.is_private == False)  # noqa: E712

            stmt = stmt.order_by(Note.updated_at.desc())

            notes = session.execute(stmt).scalars().all()
            for note in notes:
                session.expunge(note)

        return self._notes_to_summaries(list(notes))

    def search_quotes(self, query: str) -> list[QuoteSummary]:
        """Search quotes by text or context.

        Args:
            query: Search query

        Returns:
            List of matching quote summaries
        """
        with self.db.get_session() as session:
            query_lower = f"%{query.lower()}%"
            stmt = select(Quote).where(
                or_(
                    func.lower(Quote.text).like(query_lower),
                    func.lower(Quote.context).like(query_lower),
                    func.lower(Quote.speaker).like(query_lower),
                    func.lower(Quote.tags).like(query_lower),
                )
            ).order_by(Quote.updated_at.desc())

            quotes = session.execute(stmt).scalars().all()
            for quote in quotes:
                session.expunge(quote)

        return self._quotes_to_summaries(list(quotes))

    def get_book_annotations(self, book_id: str) -> Optional[BookAnnotations]:
        """Get all notes and quotes for a book.

        Args:
            book_id: Book ID

        Returns:
            BookAnnotations or None if book not found
        """
        with self.db.get_session() as session:
            book = session.execute(
                select(Book).where(Book.id == book_id)
            ).scalar_one_or_none()

            if not book:
                return None

            book_title = book.title
            book_author = book.author or "Unknown"

        notes = self.list_notes(book_id=book_id, order_by="page_number", descending=False)
        quotes = self.list_quotes(book_id=book_id, order_by="page_number", descending=False)

        return BookAnnotations(
            book_id=UUID(book_id),
            book_title=book_title,
            book_author=book_author,
            notes=self._notes_to_summaries(notes),
            quotes=self._quotes_to_summaries(quotes),
            total_notes=len(notes),
            total_quotes=len(quotes),
        )

    def get_random_quote(self, favorites_only: bool = False) -> Optional[QuoteSummary]:
        """Get a random quote.

        Args:
            favorites_only: Only select from favorites

        Returns:
            Random quote summary or None
        """
        quotes = self.list_quotes(favorites_only=favorites_only)
        if not quotes:
            return None

        quote = random.choice(quotes)
        summaries = self._quotes_to_summaries([quote])
        return summaries[0] if summaries else None

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_stats(self) -> NotesStats:
        """Get notes and quotes statistics.

        Returns:
            NotesStats with counts
        """
        with self.db.get_session() as session:
            # Count notes
            total_notes = session.execute(
                select(func.count()).select_from(Note)
            ).scalar() or 0

            # Count quotes
            total_quotes = session.execute(
                select(func.count()).select_from(Quote)
            ).scalar() or 0

            # Notes by type
            notes_by_type = {}
            for note_type in NoteType:
                count = session.execute(
                    select(func.count()).where(Note.note_type == note_type.value)
                ).scalar() or 0
                if count > 0:
                    notes_by_type[note_type.value] = count

            # Favorite counts
            favorite_notes = session.execute(
                select(func.count()).where(Note.is_favorite == True)  # noqa: E712
            ).scalar() or 0

            favorite_quotes = session.execute(
                select(func.count()).where(Quote.is_favorite == True)  # noqa: E712
            ).scalar() or 0

            # Books with notes/quotes
            books_with_notes = session.execute(
                select(func.count(func.distinct(Note.book_id)))
            ).scalar() or 0

            books_with_quotes = session.execute(
                select(func.count(func.distinct(Quote.book_id)))
            ).scalar() or 0

        # Get all tags
        all_tags = self._get_all_tags()
        total_tags = len(all_tags)
        most_used_tags = all_tags[:10]

        return NotesStats(
            total_notes=total_notes,
            total_quotes=total_quotes,
            notes_by_type=notes_by_type,
            favorite_notes=favorite_notes,
            favorite_quotes=favorite_quotes,
            books_with_notes=books_with_notes,
            books_with_quotes=books_with_quotes,
            total_tags=total_tags,
            most_used_tags=most_used_tags,
        )

    # -------------------------------------------------------------------------
    # Tag Management
    # -------------------------------------------------------------------------

    def get_all_note_tags(self) -> list[tuple[str, int]]:
        """Get all note tags with counts.

        Returns:
            List of (tag, count) tuples
        """
        notes = self.list_notes()
        return self._count_tags([n.tag_list for n in notes])

    def get_all_quote_tags(self) -> list[tuple[str, int]]:
        """Get all quote tags with counts.

        Returns:
            List of (tag, count) tuples
        """
        quotes = self.list_quotes()
        return self._count_tags([q.tag_list for q in quotes])

    def _get_all_tags(self) -> list[tuple[str, int]]:
        """Get all tags (notes and quotes) with counts."""
        notes = self.list_notes()
        quotes = self.list_quotes()

        tag_counts: dict[str, int] = {}
        for note in notes:
            for tag in note.tag_list:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for quote in quotes:
            for tag in quote.tag_list:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

    def _count_tags(self, tag_lists: list[list[str]]) -> list[tuple[str, int]]:
        """Count tags from multiple tag lists."""
        tag_counts: dict[str, int] = {}
        for tags in tag_lists:
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _notes_to_summaries(self, notes: list[Note]) -> list[NoteSummary]:
        """Convert notes to summaries with book info."""
        summaries = []

        for note in notes:
            with self.db.get_session() as session:
                book = session.execute(
                    select(Book).where(Book.id == note.book_id)
                ).scalar_one_or_none()

                if book:
                    summaries.append(NoteSummary(
                        id=UUID(note.id),
                        book_id=UUID(note.book_id),
                        book_title=book.title,
                        note_type=NoteType(note.note_type),
                        title=note.title,
                        short_content=note.short_content,
                        location_display=note.location_display,
                        is_favorite=note.is_favorite,
                        created_at=datetime.fromisoformat(note.created_at),
                    ))

        return summaries

    def _quotes_to_summaries(self, quotes: list[Quote]) -> list[QuoteSummary]:
        """Convert quotes to summaries with book info."""
        summaries = []

        for quote in quotes:
            with self.db.get_session() as session:
                book = session.execute(
                    select(Book).where(Book.id == quote.book_id)
                ).scalar_one_or_none()

                if book:
                    summaries.append(QuoteSummary(
                        id=UUID(quote.id),
                        book_id=UUID(quote.book_id),
                        book_title=book.title,
                        book_author=book.author or "Unknown",
                        short_text=quote.short_text,
                        quote_type=QuoteType(quote.quote_type),
                        color=HighlightColor(quote.color) if quote.color else None,
                        speaker=quote.speaker,
                        location_display=quote.location_display,
                        is_favorite=quote.is_favorite,
                        created_at=datetime.fromisoformat(quote.created_at),
                    ))

        return summaries

    # -------------------------------------------------------------------------
    # Favorite Management
    # -------------------------------------------------------------------------

    def toggle_note_favorite(self, note_id: str) -> Optional[Note]:
        """Toggle favorite status for a note.

        Args:
            note_id: Note ID

        Returns:
            Updated note or None
        """
        note = self.get_note(note_id)
        if not note:
            return None

        return self.update_note(
            note_id,
            NoteUpdate(is_favorite=not note.is_favorite),
        )

    def toggle_quote_favorite(self, quote_id: str) -> Optional[Quote]:
        """Toggle favorite status for a quote.

        Args:
            quote_id: Quote ID

        Returns:
            Updated quote or None
        """
        quote = self.get_quote(quote_id)
        if not quote:
            return None

        return self.update_quote(
            quote_id,
            QuoteUpdate(is_favorite=not quote.is_favorite),
        )

    # -------------------------------------------------------------------------
    # Quote Collections
    # -------------------------------------------------------------------------

    def create_collection(self, data: CollectionCreate) -> CollectionResponse:
        """Create a new quote collection.

        Args:
            data: Collection creation data

        Returns:
            Created collection
        """
        with self.db.get_session() as session:
            collection = QuoteCollection(
                name=data.name,
                description=data.description,
                icon=data.icon,
                is_public=data.is_public,
            )
            session.add(collection)
            session.commit()
            session.refresh(collection)

            return CollectionResponse(
                id=UUID(collection.id),
                name=collection.name,
                description=collection.description,
                icon=collection.icon,
                is_public=collection.is_public,
                quote_count=0,
                created_at=datetime.fromisoformat(collection.created_at),
                updated_at=datetime.fromisoformat(collection.updated_at),
            )

    def get_collection(self, collection_id: str) -> Optional[CollectionWithQuotes]:
        """Get a collection with its quotes.

        Args:
            collection_id: Collection ID

        Returns:
            Collection with quotes or None
        """
        with self.db.get_session() as session:
            collection = session.execute(
                select(QuoteCollection).where(QuoteCollection.id == collection_id)
            ).scalar_one_or_none()

            if not collection:
                return None

            # Get quotes in order
            quote_links = (
                session.execute(
                    select(CollectionQuote)
                    .where(CollectionQuote.collection_id == collection_id)
                    .order_by(CollectionQuote.position)
                )
                .scalars()
                .all()
            )

            quote_summaries = []
            for link in quote_links:
                quote = session.execute(
                    select(Quote).where(Quote.id == link.quote_id)
                ).scalar_one_or_none()
                if quote:
                    book = session.execute(
                        select(Book).where(Book.id == quote.book_id)
                    ).scalar_one_or_none()
                    if book:
                        quote_summaries.append(
                            QuoteSummary(
                                id=UUID(quote.id),
                                book_id=UUID(quote.book_id),
                                book_title=book.title,
                                book_author=book.author or "Unknown",
                                short_text=quote.short_text,
                                quote_type=QuoteType(quote.quote_type),
                                color=(
                                    HighlightColor(quote.color) if quote.color else None
                                ),
                                speaker=quote.speaker,
                                location_display=quote.location_display,
                                is_favorite=quote.is_favorite,
                                created_at=datetime.fromisoformat(quote.created_at),
                            )
                        )

            return CollectionWithQuotes(
                id=UUID(collection.id),
                name=collection.name,
                description=collection.description,
                icon=collection.icon,
                is_public=collection.is_public,
                quotes=quote_summaries,
                created_at=datetime.fromisoformat(collection.created_at),
            )

    def update_collection(
        self, collection_id: str, data: CollectionUpdate
    ) -> Optional[CollectionResponse]:
        """Update a collection.

        Args:
            collection_id: Collection ID
            data: Update data

        Returns:
            Updated collection or None
        """
        with self.db.get_session() as session:
            collection = session.execute(
                select(QuoteCollection).where(QuoteCollection.id == collection_id)
            ).scalar_one_or_none()

            if not collection:
                return None

            update_data = data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if hasattr(collection, field):
                    setattr(collection, field, value)

            collection.updated_at = datetime.now(timezone.utc).isoformat()
            session.commit()
            session.refresh(collection)

            return CollectionResponse(
                id=UUID(collection.id),
                name=collection.name,
                description=collection.description,
                icon=collection.icon,
                is_public=collection.is_public,
                quote_count=collection.quote_count,
                created_at=datetime.fromisoformat(collection.created_at),
                updated_at=datetime.fromisoformat(collection.updated_at),
            )

    def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection.

        Args:
            collection_id: Collection ID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            collection = session.execute(
                select(QuoteCollection).where(QuoteCollection.id == collection_id)
            ).scalar_one_or_none()

            if not collection:
                return False

            session.delete(collection)
            session.commit()
            return True

    def list_collections(self) -> list[CollectionResponse]:
        """List all quote collections.

        Returns:
            List of collections
        """
        with self.db.get_session() as session:
            collections = (
                session.execute(
                    select(QuoteCollection).order_by(QuoteCollection.name)
                )
                .scalars()
                .all()
            )

            return [
                CollectionResponse(
                    id=UUID(c.id),
                    name=c.name,
                    description=c.description,
                    icon=c.icon,
                    is_public=c.is_public,
                    quote_count=c.quote_count,
                    created_at=datetime.fromisoformat(c.created_at),
                    updated_at=datetime.fromisoformat(c.updated_at),
                )
                for c in collections
            ]

    def add_quote_to_collection(
        self, collection_id: str, quote_id: str, position: Optional[int] = None
    ) -> bool:
        """Add a quote to a collection.

        Args:
            collection_id: Collection ID
            quote_id: Quote ID
            position: Position in collection (optional)

        Returns:
            True if added
        """
        with self.db.get_session() as session:
            # Verify both exist
            collection = session.execute(
                select(QuoteCollection).where(QuoteCollection.id == collection_id)
            ).scalar_one_or_none()
            quote = session.execute(
                select(Quote).where(Quote.id == quote_id)
            ).scalar_one_or_none()

            if not collection or not quote:
                return False

            # Check if already in collection
            existing = session.execute(
                select(CollectionQuote).where(
                    CollectionQuote.collection_id == collection_id,
                    CollectionQuote.quote_id == quote_id,
                )
            ).scalar_one_or_none()

            if existing:
                return True  # Already added

            # Get max position if not provided
            if position is None:
                max_pos = session.execute(
                    select(func.max(CollectionQuote.position)).where(
                        CollectionQuote.collection_id == collection_id
                    )
                ).scalar()
                position = (max_pos or 0) + 1

            link = CollectionQuote(
                collection_id=collection_id,
                quote_id=quote_id,
                position=position,
            )
            session.add(link)
            session.commit()
            return True

    def remove_quote_from_collection(
        self, collection_id: str, quote_id: str
    ) -> bool:
        """Remove a quote from a collection.

        Args:
            collection_id: Collection ID
            quote_id: Quote ID

        Returns:
            True if removed
        """
        with self.db.get_session() as session:
            link = session.execute(
                select(CollectionQuote).where(
                    CollectionQuote.collection_id == collection_id,
                    CollectionQuote.quote_id == quote_id,
                )
            ).scalar_one_or_none()

            if not link:
                return False

            session.delete(link)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Quote of the Day / Random
    # -------------------------------------------------------------------------

    def get_quote_of_the_day(self) -> Optional[QuoteSummary]:
        """Get quote of the day (deterministic based on date).

        Returns:
            Quote summary or None
        """
        today = datetime.now(timezone.utc).date()
        seed = int(today.strftime("%Y%m%d"))

        # Prefer favorites
        quotes = self.list_quotes(favorites_only=True)
        if not quotes:
            quotes = self.list_quotes()

        if not quotes:
            return None

        random.seed(seed)
        quote = random.choice(quotes)
        random.seed()  # Reset seed

        summaries = self._quotes_to_summaries([quote])
        return summaries[0] if summaries else None

    # -------------------------------------------------------------------------
    # Extended Quote Stats
    # -------------------------------------------------------------------------

    def get_quote_stats(self) -> QuoteStats:
        """Get detailed quote statistics.

        Returns:
            QuoteStats with counts
        """
        with self.db.get_session() as session:
            # Total quotes
            total = session.execute(
                select(func.count()).select_from(Quote)
            ).scalar() or 0

            # Count by type
            highlights = session.execute(
                select(func.count()).where(Quote.quote_type == "highlight")
            ).scalar() or 0
            excerpts = session.execute(
                select(func.count()).where(Quote.quote_type == "excerpt")
            ).scalar() or 0

            # Favorites
            favorites = session.execute(
                select(func.count()).where(Quote.is_favorite == True)  # noqa: E712
            ).scalar() or 0

            # Quotes by book
            quotes_by_book: dict[str, int] = {}
            book_counts = session.execute(
                select(Quote.book_id, func.count(Quote.id)).group_by(Quote.book_id)
            ).all()
            for book_id, count in book_counts:
                book = session.execute(
                    select(Book).where(Book.id == book_id)
                ).scalar_one_or_none()
                if book:
                    quotes_by_book[book.title] = count

            # Quotes by color
            quotes_by_color: dict[str, int] = {}
            color_counts = session.execute(
                select(Quote.color, func.count(Quote.id))
                .where(Quote.color.isnot(None))
                .group_by(Quote.color)
            ).all()
            for color, count in color_counts:
                quotes_by_color[color] = count

            # Quotes by type
            quotes_by_type: dict[str, int] = {}
            type_counts = session.execute(
                select(Quote.quote_type, func.count(Quote.id)).group_by(Quote.quote_type)
            ).all()
            for qtype, count in type_counts:
                quotes_by_type[qtype] = count

            # Most quoted book
            most_quoted = None
            if book_counts:
                max_book_id = max(book_counts, key=lambda x: x[1])[0]
                book = session.execute(
                    select(Book).where(Book.id == max_book_id)
                ).scalar_one_or_none()
                if book:
                    most_quoted = book.title

            # Collections count
            collections = session.execute(
                select(func.count()).select_from(QuoteCollection)
            ).scalar() or 0

        return QuoteStats(
            total_quotes=total,
            total_highlights=highlights,
            total_excerpts=excerpts,
            favorites_count=favorites,
            quotes_by_book=quotes_by_book,
            quotes_by_color=quotes_by_color,
            quotes_by_type=quotes_by_type,
            most_quoted_book=most_quoted,
            most_used_tags=self.get_all_quote_tags()[:10],
            collections_count=collections,
        )

    # -------------------------------------------------------------------------
    # Export Quotes
    # -------------------------------------------------------------------------

    def export_quotes(
        self,
        book_id: Optional[str] = None,
        format: str = "text",
    ) -> str:
        """Export quotes to text or markdown format.

        Args:
            book_id: Filter by book (optional)
            format: Output format ('text' or 'markdown')

        Returns:
            Formatted string of quotes
        """
        if book_id:
            quotes = self.list_quotes(book_id=book_id, order_by="page_number", descending=False)
        else:
            quotes = self.list_quotes(order_by="page_number", descending=False)

        if format == "markdown":
            return self._export_quotes_markdown(quotes)
        return self._export_quotes_text(quotes)

    def _export_quotes_text(self, quotes: list[Quote]) -> str:
        """Export quotes as plain text."""
        lines = []
        current_book = None

        for quote in quotes:
            with self.db.get_session() as session:
                book = session.execute(
                    select(Book).where(Book.id == quote.book_id)
                ).scalar_one_or_none()

                if book and book.title != current_book:
                    if lines:
                        lines.append("")
                    lines.append(f"=== {book.title} by {book.author or 'Unknown'} ===")
                    current_book = book.title

            lines.append("")
            lines.append(f'"{quote.text}"')
            if quote.speaker:
                lines.append(f"  - {quote.speaker}")
            if quote.page_number:
                lines.append(f"  - Page {quote.page_number}")
            if quote.context:
                lines.append(f"  Note: {quote.context}")

        return "\n".join(lines)

    def _export_quotes_markdown(self, quotes: list[Quote]) -> str:
        """Export quotes as markdown."""
        lines = []
        current_book = None

        for quote in quotes:
            with self.db.get_session() as session:
                book = session.execute(
                    select(Book).where(Book.id == quote.book_id)
                ).scalar_one_or_none()

                if book and book.title != current_book:
                    if lines:
                        lines.append("")
                    lines.append(f"## {book.title}")
                    if book.author:
                        lines.append(f"*by {book.author}*")
                    lines.append("")
                    current_book = book.title

            lines.append(f"> {quote.text}")
            location_parts = []
            if quote.speaker:
                location_parts.append(quote.speaker)
            if quote.page_number:
                location_parts.append(f"p. {quote.page_number}")
            if quote.chapter:
                location_parts.append(quote.chapter)
            if location_parts:
                lines.append(f"*— {', '.join(location_parts)}*")
            if quote.context:
                lines.append(f"\n**Note:** {quote.context}")
            if quote.tag_list:
                lines.append(f"\nTags: {', '.join(quote.tag_list)}")
            lines.append("")

        return "\n".join(lines)
