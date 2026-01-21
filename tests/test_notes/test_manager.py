"""Tests for NotesManager."""

import pytest
from uuid import UUID

from vibecoding.booktracker.db.sqlite import Database
from vibecoding.booktracker.db.models import Book
from vibecoding.booktracker.notes.manager import NotesManager
from vibecoding.booktracker.notes.schemas import (
    NoteCreate,
    NoteUpdate,
    NoteType,
    QuoteCreate,
    QuoteUpdate,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    database.create_tables()
    return database


@pytest.fixture
def manager(db):
    """Create a NotesManager with test database."""
    return NotesManager(db)


@pytest.fixture
def sample_book(db):
    """Create a sample book for testing."""
    with db.get_session() as session:
        book = Book(
            title="Test Book",
            author="Test Author",
            status="read",
        )
        session.add(book)
        session.commit()
        session.refresh(book)
        book_id = book.id
    return book_id


@pytest.fixture
def sample_books(db):
    """Create multiple sample books for testing."""
    book_ids = []
    with db.get_session() as session:
        for i in range(5):
            book = Book(
                title=f"Test Book {i+1}",
                author=f"Author {i+1}",
                status="read",
            )
            session.add(book)
            session.commit()
            session.refresh(book)
            book_ids.append(book.id)
    return book_ids


@pytest.fixture
def sample_note(manager, sample_book):
    """Create a sample note for testing."""
    data = NoteCreate(
        book_id=UUID(sample_book),
        note_type=NoteType.INSIGHT,
        title="Key Insight",
        content="This is a key insight from the book.",
        chapter="Chapter 5",
        page_number=42,
        tags=["important", "theme"],
        is_favorite=True,
    )
    return manager.create_note(data)


@pytest.fixture
def sample_quote(manager, sample_book):
    """Create a sample quote for testing."""
    data = QuoteCreate(
        book_id=UUID(sample_book),
        text="To be or not to be, that is the question.",
        speaker="Hamlet",
        context="Famous soliloquy",
        chapter="Act 3",
        page_number=100,
        tags=["famous", "philosophy"],
        is_favorite=True,
    )
    return manager.create_quote(data)


class TestNoteCRUD:
    """Tests for note CRUD operations."""

    def test_create_note(self, manager, sample_book):
        """Test creating a note."""
        data = NoteCreate(
            book_id=UUID(sample_book),
            note_type=NoteType.THOUGHT,
            title="My Thought",
            content="This is my thought about the book.",
            chapter="Chapter 1",
            page_number=10,
            location="loc. 150",
            tags=["reflection", "personal"],
            is_private=True,
            is_favorite=False,
        )
        note = manager.create_note(data)

        assert note.id is not None
        assert note.book_id == sample_book
        assert note.note_type == "thought"
        assert note.title == "My Thought"
        assert note.content == "This is my thought about the book."
        assert note.chapter == "Chapter 1"
        assert note.page_number == 10
        assert note.is_private is True
        assert "reflection" in note.tag_list

    def test_create_note_minimal(self, manager, sample_book):
        """Test creating note with minimal info."""
        data = NoteCreate(
            book_id=UUID(sample_book),
            content="Simple note",
        )
        note = manager.create_note(data)

        assert note.content == "Simple note"
        assert note.note_type == "note"  # Default
        assert note.title is None

    def test_create_note_book_not_found(self, manager):
        """Test creating note for non-existent book."""
        data = NoteCreate(
            book_id=UUID("00000000-0000-0000-0000-000000000000"),
            content="Test note",
        )
        with pytest.raises(ValueError, match="Book not found"):
            manager.create_note(data)

    def test_get_note(self, manager, sample_note):
        """Test getting a note by ID."""
        note = manager.get_note(sample_note.id)

        assert note is not None
        assert note.id == sample_note.id
        assert note.content == sample_note.content

    def test_get_note_not_found(self, manager):
        """Test getting non-existent note."""
        note = manager.get_note("non-existent")
        assert note is None

    def test_list_notes(self, manager, sample_books):
        """Test listing all notes."""
        # Create notes for multiple books
        for book_id in sample_books[:3]:
            manager.create_note(NoteCreate(
                book_id=UUID(book_id),
                content=f"Note for book {book_id}",
            ))

        notes = manager.list_notes()
        assert len(notes) == 3

    def test_list_notes_filter_by_book(self, manager, sample_books):
        """Test filtering notes by book."""
        for book_id in sample_books[:2]:
            manager.create_note(NoteCreate(
                book_id=UUID(book_id),
                content=f"Note for book {book_id}",
            ))

        notes = manager.list_notes(book_id=sample_books[0])
        assert len(notes) == 1
        assert notes[0].book_id == sample_books[0]

    def test_list_notes_filter_by_type(self, manager, sample_book):
        """Test filtering notes by type."""
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Insight",
            note_type=NoteType.INSIGHT,
        ))
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Question",
            note_type=NoteType.QUESTION,
        ))

        insights = manager.list_notes(note_type=NoteType.INSIGHT)
        assert len(insights) == 1
        assert insights[0].note_type == "insight"

    def test_list_notes_favorites_only(self, manager, sample_book):
        """Test filtering for favorites only."""
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Favorite note",
            is_favorite=True,
        ))
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Regular note",
            is_favorite=False,
        ))

        favorites = manager.list_notes(favorites_only=True)
        assert len(favorites) == 1
        assert favorites[0].is_favorite is True

    def test_list_notes_exclude_private(self, manager, sample_book):
        """Test excluding private notes."""
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Public note",
            is_private=False,
        ))
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Private note",
            is_private=True,
        ))

        public = manager.list_notes(include_private=False)
        assert len(public) == 1
        assert public[0].is_private is False

    def test_list_notes_filter_by_tag(self, manager, sample_book):
        """Test filtering notes by tag."""
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Tagged note",
            tags=["important", "review"],
        ))
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Other note",
            tags=["other"],
        ))

        tagged = manager.list_notes(tag="important")
        assert len(tagged) == 1

    def test_update_note(self, manager, sample_note):
        """Test updating a note."""
        data = NoteUpdate(
            title="Updated Title",
            content="Updated content",
            is_favorite=False,
        )
        updated = manager.update_note(sample_note.id, data)

        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.content == "Updated content"
        assert updated.is_favorite is False

    def test_update_note_not_found(self, manager):
        """Test updating non-existent note."""
        data = NoteUpdate(content="Test")
        result = manager.update_note("non-existent", data)
        assert result is None

    def test_delete_note(self, manager, sample_note):
        """Test deleting a note."""
        result = manager.delete_note(sample_note.id)
        assert result is True

        # Verify deletion
        note = manager.get_note(sample_note.id)
        assert note is None

    def test_delete_note_not_found(self, manager):
        """Test deleting non-existent note."""
        result = manager.delete_note("non-existent")
        assert result is False


class TestQuoteCRUD:
    """Tests for quote CRUD operations."""

    def test_create_quote(self, manager, sample_book):
        """Test creating a quote."""
        data = QuoteCreate(
            book_id=UUID(sample_book),
            text="The only way to do great work is to love what you do.",
            speaker="Steve Jobs",
            context="Commencement speech reference",
            chapter="Chapter 10",
            page_number=200,
            tags=["motivation", "work"],
            is_favorite=True,
        )
        quote = manager.create_quote(data)

        assert quote.id is not None
        assert quote.book_id == sample_book
        assert "only way to do great work" in quote.text
        assert quote.speaker == "Steve Jobs"
        assert quote.is_favorite is True

    def test_create_quote_minimal(self, manager, sample_book):
        """Test creating quote with minimal info."""
        data = QuoteCreate(
            book_id=UUID(sample_book),
            text="Simple quote",
        )
        quote = manager.create_quote(data)

        assert quote.text == "Simple quote"
        assert quote.speaker is None

    def test_create_quote_book_not_found(self, manager):
        """Test creating quote for non-existent book."""
        data = QuoteCreate(
            book_id=UUID("00000000-0000-0000-0000-000000000000"),
            text="Test quote",
        )
        with pytest.raises(ValueError, match="Book not found"):
            manager.create_quote(data)

    def test_get_quote(self, manager, sample_quote):
        """Test getting a quote by ID."""
        quote = manager.get_quote(sample_quote.id)

        assert quote is not None
        assert quote.id == sample_quote.id

    def test_get_quote_not_found(self, manager):
        """Test getting non-existent quote."""
        quote = manager.get_quote("non-existent")
        assert quote is None

    def test_list_quotes(self, manager, sample_books):
        """Test listing all quotes."""
        for book_id in sample_books[:3]:
            manager.create_quote(QuoteCreate(
                book_id=UUID(book_id),
                text=f"Quote from book {book_id}",
            ))

        quotes = manager.list_quotes()
        assert len(quotes) == 3

    def test_list_quotes_filter_by_book(self, manager, sample_books):
        """Test filtering quotes by book."""
        for book_id in sample_books[:2]:
            manager.create_quote(QuoteCreate(
                book_id=UUID(book_id),
                text=f"Quote from book {book_id}",
            ))

        quotes = manager.list_quotes(book_id=sample_books[0])
        assert len(quotes) == 1

    def test_list_quotes_filter_by_speaker(self, manager, sample_book):
        """Test filtering quotes by speaker."""
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Quote 1",
            speaker="Character A",
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Quote 2",
            speaker="Character B",
        ))

        quotes = manager.list_quotes(speaker="Character A")
        assert len(quotes) == 1

    def test_list_quotes_favorites_only(self, manager, sample_book):
        """Test filtering for favorite quotes only."""
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Favorite quote",
            is_favorite=True,
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Regular quote",
            is_favorite=False,
        ))

        favorites = manager.list_quotes(favorites_only=True)
        assert len(favorites) == 1

    def test_update_quote(self, manager, sample_quote):
        """Test updating a quote."""
        data = QuoteUpdate(
            text="Updated quote text",
            speaker="New Speaker",
        )
        updated = manager.update_quote(sample_quote.id, data)

        assert updated is not None
        assert updated.text == "Updated quote text"
        assert updated.speaker == "New Speaker"

    def test_update_quote_not_found(self, manager):
        """Test updating non-existent quote."""
        data = QuoteUpdate(text="Test")
        result = manager.update_quote("non-existent", data)
        assert result is None

    def test_delete_quote(self, manager, sample_quote):
        """Test deleting a quote."""
        result = manager.delete_quote(sample_quote.id)
        assert result is True

        quote = manager.get_quote(sample_quote.id)
        assert quote is None

    def test_delete_quote_not_found(self, manager):
        """Test deleting non-existent quote."""
        result = manager.delete_quote("non-existent")
        assert result is False


class TestNoteProperties:
    """Tests for note model properties."""

    def test_tag_list(self, manager, sample_book):
        """Test tag_list property."""
        note = manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Test note",
            tags=["tag1", "tag2", "tag3"],
        ))

        assert note.tag_list == ["tag1", "tag2", "tag3"]

    def test_tag_list_empty(self, manager, sample_book):
        """Test tag_list with no tags."""
        note = manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Test note",
        ))

        assert note.tag_list == []

    def test_short_content(self, manager, sample_book):
        """Test short_content property."""
        long_content = "A" * 200
        note = manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content=long_content,
        ))

        assert len(note.short_content) == 100
        assert note.short_content.endswith("...")

    def test_short_content_short(self, manager, sample_book):
        """Test short_content with short content."""
        note = manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Short",
        ))

        assert note.short_content == "Short"

    def test_location_display(self, manager, sample_book):
        """Test location_display property."""
        note = manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Test",
            chapter="Ch. 5",
            page_number=42,
        ))

        assert "Ch. 5" in note.location_display
        assert "p. 42" in note.location_display


class TestQuoteProperties:
    """Tests for quote model properties."""

    def test_short_text(self, manager, sample_book):
        """Test short_text property."""
        long_text = "B" * 200
        quote = manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text=long_text,
        ))

        assert len(quote.short_text) == 100
        assert quote.short_text.endswith("...")

    def test_attribution(self, manager, sample_book):
        """Test attribution property."""
        quote = manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Test",
            speaker="Narrator",
        ))

        assert quote.attribution == "— Narrator"

    def test_attribution_no_speaker(self, manager, sample_book):
        """Test attribution with no speaker."""
        quote = manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Test",
        ))

        assert quote.attribution == ""


class TestSearchAndQuery:
    """Tests for search and query functionality."""

    def test_search_notes_by_content(self, manager, sample_book):
        """Test searching notes by content."""
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="The protagonist shows great courage.",
        ))

        results = manager.search_notes("protagonist")
        assert len(results) == 1

    def test_search_notes_by_title(self, manager, sample_book):
        """Test searching notes by title."""
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            title="Important Character Analysis",
            content="Some analysis.",
        ))

        results = manager.search_notes("character analysis")
        assert len(results) == 1

    def test_search_notes_no_results(self, manager, sample_book):
        """Test search with no results."""
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Test note",
        ))

        results = manager.search_notes("nonexistent")
        assert len(results) == 0

    def test_search_quotes_by_text(self, manager, sample_book):
        """Test searching quotes by text."""
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="All that glitters is not gold.",
        ))

        results = manager.search_quotes("glitters")
        assert len(results) == 1

    def test_search_quotes_by_speaker(self, manager, sample_book):
        """Test searching quotes by speaker."""
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Some quote",
            speaker="Captain Ahab",
        ))

        results = manager.search_quotes("Captain Ahab")
        assert len(results) == 1

    def test_get_book_annotations(self, manager, sample_book):
        """Test getting all annotations for a book."""
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Note 1",
        ))
        manager.create_note(NoteCreate(
            book_id=UUID(sample_book),
            content="Note 2",
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Quote 1",
        ))

        annotations = manager.get_book_annotations(sample_book)

        assert annotations is not None
        assert annotations.total_notes == 2
        assert annotations.total_quotes == 1
        assert len(annotations.notes) == 2
        assert len(annotations.quotes) == 1

    def test_get_book_annotations_not_found(self, manager):
        """Test getting annotations for non-existent book."""
        result = manager.get_book_annotations("non-existent")
        assert result is None

    def test_get_random_quote(self, manager, sample_book):
        """Test getting a random quote."""
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Quote 1",
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Quote 2",
        ))

        quote = manager.get_random_quote()
        assert quote is not None
        assert quote.short_text in ["Quote 1", "Quote 2"]

    def test_get_random_quote_empty(self, manager):
        """Test getting random quote when none exist."""
        quote = manager.get_random_quote()
        assert quote is None


class TestStatistics:
    """Tests for notes statistics."""

    def test_get_stats_empty(self, manager):
        """Test stats with no data."""
        stats = manager.get_stats()

        assert stats.total_notes == 0
        assert stats.total_quotes == 0
        assert stats.favorite_notes == 0
        assert stats.favorite_quotes == 0

    def test_get_stats_with_data(self, manager, sample_books):
        """Test stats with various data."""
        # Create notes
        for i, book_id in enumerate(sample_books[:3]):
            manager.create_note(NoteCreate(
                book_id=UUID(book_id),
                content=f"Note {i}",
                note_type=NoteType.INSIGHT if i < 2 else NoteType.QUESTION,
                is_favorite=(i == 0),
            ))

        # Create quotes
        for i, book_id in enumerate(sample_books[:2]):
            manager.create_quote(QuoteCreate(
                book_id=UUID(book_id),
                text=f"Quote {i}",
                is_favorite=(i == 0),
            ))

        stats = manager.get_stats()

        assert stats.total_notes == 3
        assert stats.total_quotes == 2
        assert stats.favorite_notes == 1
        assert stats.favorite_quotes == 1
        assert stats.books_with_notes == 3
        assert stats.books_with_quotes == 2
        assert "insight" in stats.notes_by_type
        assert stats.notes_by_type["insight"] == 2


class TestTagManagement:
    """Tests for tag management."""

    def test_get_all_note_tags(self, manager, sample_books):
        """Test getting all note tags."""
        manager.create_note(NoteCreate(
            book_id=UUID(sample_books[0]),
            content="Note 1",
            tags=["fiction", "favorite"],
        ))
        manager.create_note(NoteCreate(
            book_id=UUID(sample_books[1]),
            content="Note 2",
            tags=["fiction", "classic"],
        ))

        tags = manager.get_all_note_tags()
        tag_dict = dict(tags)

        assert tag_dict["fiction"] == 2
        assert tag_dict["favorite"] == 1

    def test_get_all_quote_tags(self, manager, sample_books):
        """Test getting all quote tags."""
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_books[0]),
            text="Quote 1",
            tags=["wisdom", "life"],
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_books[1]),
            text="Quote 2",
            tags=["wisdom"],
        ))

        tags = manager.get_all_quote_tags()
        tag_dict = dict(tags)

        assert tag_dict["wisdom"] == 2
        assert tag_dict["life"] == 1


class TestFavoriteManagement:
    """Tests for favorite management."""

    def test_toggle_note_favorite(self, manager, sample_note):
        """Test toggling note favorite status."""
        # Sample note starts as favorite
        assert sample_note.is_favorite is True

        # Toggle off
        updated = manager.toggle_note_favorite(sample_note.id)
        assert updated.is_favorite is False

        # Toggle on
        updated = manager.toggle_note_favorite(sample_note.id)
        assert updated.is_favorite is True

    def test_toggle_note_favorite_not_found(self, manager):
        """Test toggling non-existent note."""
        result = manager.toggle_note_favorite("non-existent")
        assert result is None

    def test_toggle_quote_favorite(self, manager, sample_quote):
        """Test toggling quote favorite status."""
        assert sample_quote.is_favorite is True

        updated = manager.toggle_quote_favorite(sample_quote.id)
        assert updated.is_favorite is False

    def test_toggle_quote_favorite_not_found(self, manager):
        """Test toggling non-existent quote."""
        result = manager.toggle_quote_favorite("non-existent")
        assert result is None


class TestQuoteTypeAndColor:
    """Tests for quote type and highlight color features."""

    def test_create_quote_with_type(self, manager, sample_book):
        """Test creating a quote with specific type."""
        from vibecoding.booktracker.notes.schemas import QuoteType

        data = QuoteCreate(
            book_id=UUID(sample_book),
            text="This is a highlighted passage.",
            quote_type=QuoteType.HIGHLIGHT,
        )
        quote = manager.create_quote(data)

        assert quote.quote_type == "highlight"

    def test_create_quote_with_color(self, manager, sample_book):
        """Test creating a quote with highlight color."""
        from vibecoding.booktracker.notes.schemas import QuoteType, HighlightColor

        data = QuoteCreate(
            book_id=UUID(sample_book),
            text="Important passage",
            quote_type=QuoteType.HIGHLIGHT,
            color=HighlightColor.YELLOW,
        )
        quote = manager.create_quote(data)

        assert quote.color == "yellow"

    def test_filter_quotes_by_type(self, manager, sample_book):
        """Test filtering quotes by type."""
        from vibecoding.booktracker.notes.schemas import QuoteType

        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="A direct quote",
            quote_type=QuoteType.QUOTE,
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="A highlighted passage",
            quote_type=QuoteType.HIGHLIGHT,
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="An excerpt",
            quote_type=QuoteType.EXCERPT,
        ))

        highlights = manager.list_quotes(quote_type=QuoteType.HIGHLIGHT)
        assert len(highlights) == 1
        assert highlights[0].quote_type == "highlight"

    def test_filter_quotes_by_color(self, manager, sample_book):
        """Test filtering quotes by color."""
        from vibecoding.booktracker.notes.schemas import QuoteType, HighlightColor

        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Yellow highlight",
            quote_type=QuoteType.HIGHLIGHT,
            color=HighlightColor.YELLOW,
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Blue highlight",
            quote_type=QuoteType.HIGHLIGHT,
            color=HighlightColor.BLUE,
        ))

        yellow = manager.list_quotes(color=HighlightColor.YELLOW)
        assert len(yellow) == 1

    def test_update_quote_type_and_color(self, manager, sample_book):
        """Test updating quote type and color."""
        from vibecoding.booktracker.notes.schemas import QuoteType, HighlightColor

        data = QuoteCreate(
            book_id=UUID(sample_book),
            text="Original text",
        )
        quote = manager.create_quote(data)
        assert quote.quote_type == "quote"
        assert quote.color is None

        updated = manager.update_quote(
            quote.id,
            QuoteUpdate(
                quote_type=QuoteType.HIGHLIGHT,
                color=HighlightColor.GREEN,
            )
        )

        assert updated.quote_type == "highlight"
        assert updated.color == "green"


class TestQuoteCollections:
    """Tests for quote collections."""

    def test_create_collection(self, manager):
        """Test creating a quote collection."""
        from vibecoding.booktracker.notes.schemas import CollectionCreate

        data = CollectionCreate(
            name="Inspirational Quotes",
            description="Quotes that inspire me",
            icon="💡",
        )
        collection = manager.create_collection(data)

        assert collection.name == "Inspirational Quotes"
        assert collection.description == "Quotes that inspire me"
        assert collection.icon == "💡"
        assert collection.quote_count == 0

    def test_list_collections(self, manager):
        """Test listing collections."""
        from vibecoding.booktracker.notes.schemas import CollectionCreate

        manager.create_collection(CollectionCreate(name="Collection A"))
        manager.create_collection(CollectionCreate(name="Collection B"))

        collections = manager.list_collections()
        assert len(collections) == 2

    def test_get_collection(self, manager, sample_book):
        """Test getting a collection with quotes."""
        from vibecoding.booktracker.notes.schemas import CollectionCreate

        collection = manager.create_collection(CollectionCreate(name="Test Collection"))

        # Add a quote
        quote = manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Test quote",
        ))

        manager.add_quote_to_collection(str(collection.id), quote.id)

        fetched = manager.get_collection(str(collection.id))
        assert fetched is not None
        assert len(fetched.quotes) == 1

    def test_update_collection(self, manager):
        """Test updating a collection."""
        from vibecoding.booktracker.notes.schemas import CollectionCreate, CollectionUpdate

        collection = manager.create_collection(CollectionCreate(name="Original Name"))

        updated = manager.update_collection(
            str(collection.id),
            CollectionUpdate(name="Updated Name", description="New description")
        )

        assert updated.name == "Updated Name"
        assert updated.description == "New description"

    def test_delete_collection(self, manager):
        """Test deleting a collection."""
        from vibecoding.booktracker.notes.schemas import CollectionCreate

        collection = manager.create_collection(CollectionCreate(name="To Delete"))

        result = manager.delete_collection(str(collection.id))
        assert result is True

        fetched = manager.get_collection(str(collection.id))
        assert fetched is None

    def test_add_quote_to_collection(self, manager, sample_book):
        """Test adding a quote to a collection."""
        from vibecoding.booktracker.notes.schemas import CollectionCreate

        collection = manager.create_collection(CollectionCreate(name="My Quotes"))
        quote = manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="A memorable quote",
        ))

        result = manager.add_quote_to_collection(str(collection.id), quote.id)
        assert result is True

        fetched = manager.get_collection(str(collection.id))
        assert len(fetched.quotes) == 1

    def test_add_quote_already_in_collection(self, manager, sample_book):
        """Test adding same quote twice."""
        from vibecoding.booktracker.notes.schemas import CollectionCreate

        collection = manager.create_collection(CollectionCreate(name="My Quotes"))
        quote = manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="A quote",
        ))

        manager.add_quote_to_collection(str(collection.id), quote.id)
        result = manager.add_quote_to_collection(str(collection.id), quote.id)

        assert result is True  # Should return True but not duplicate
        fetched = manager.get_collection(str(collection.id))
        assert len(fetched.quotes) == 1

    def test_remove_quote_from_collection(self, manager, sample_book):
        """Test removing a quote from a collection."""
        from vibecoding.booktracker.notes.schemas import CollectionCreate

        collection = manager.create_collection(CollectionCreate(name="My Quotes"))
        quote = manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="A quote",
        ))

        manager.add_quote_to_collection(str(collection.id), quote.id)
        result = manager.remove_quote_from_collection(str(collection.id), quote.id)

        assert result is True
        fetched = manager.get_collection(str(collection.id))
        assert len(fetched.quotes) == 0

    def test_add_quote_to_nonexistent_collection(self, manager, sample_book):
        """Test adding quote to non-existent collection."""
        quote = manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="A quote",
        ))

        result = manager.add_quote_to_collection("nonexistent", quote.id)
        assert result is False


class TestQuoteOfTheDay:
    """Tests for quote of the day feature."""

    def test_get_quote_of_the_day(self, manager, sample_book):
        """Test getting quote of the day."""
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Daily inspiration",
            is_favorite=True,
        ))

        quote = manager.get_quote_of_the_day()
        assert quote is not None

    def test_quote_of_day_deterministic(self, manager, sample_book):
        """Test that quote of the day is consistent within a day."""
        for i in range(3):
            manager.create_quote(QuoteCreate(
                book_id=UUID(sample_book),
                text=f"Quote {i}",
                is_favorite=True,
            ))

        # Get quote twice - should be the same
        quote1 = manager.get_quote_of_the_day()
        quote2 = manager.get_quote_of_the_day()

        assert quote1.id == quote2.id

    def test_quote_of_day_empty(self, manager):
        """Test quote of the day with no quotes."""
        quote = manager.get_quote_of_the_day()
        assert quote is None


class TestQuoteStats:
    """Tests for extended quote statistics."""

    def test_get_quote_stats(self, manager, sample_book):
        """Test getting quote statistics."""
        from vibecoding.booktracker.notes.schemas import QuoteType, HighlightColor

        # Create various quotes
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Quote 1",
            quote_type=QuoteType.QUOTE,
            is_favorite=True,
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Highlight 1",
            quote_type=QuoteType.HIGHLIGHT,
            color=HighlightColor.YELLOW,
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="Excerpt 1",
            quote_type=QuoteType.EXCERPT,
        ))

        stats = manager.get_quote_stats()

        assert stats.total_quotes == 3
        assert stats.total_highlights == 1
        assert stats.total_excerpts == 1
        assert stats.favorites_count == 1
        assert "quote" in stats.quotes_by_type
        assert "highlight" in stats.quotes_by_type
        assert "excerpt" in stats.quotes_by_type


class TestExportQuotes:
    """Tests for quote export functionality."""

    def test_export_quotes_text(self, manager, sample_book):
        """Test exporting quotes as text."""
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="A memorable quote from the book.",
            speaker="Character",
            page_number=42,
        ))

        result = manager.export_quotes(format="text")

        assert "A memorable quote from the book." in result
        assert "Character" in result
        assert "Page 42" in result

    def test_export_quotes_markdown(self, manager, sample_book):
        """Test exporting quotes as markdown."""
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_book),
            text="A quote for markdown export.",
            page_number=10,
            tags=["wisdom"],
        ))

        result = manager.export_quotes(format="markdown")

        assert ">" in result  # Markdown blockquote
        assert "A quote for markdown export." in result
        assert "Tags:" in result

    def test_export_quotes_by_book(self, manager, sample_books):
        """Test exporting quotes filtered by book."""
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_books[0]),
            text="Quote from book 1",
        ))
        manager.create_quote(QuoteCreate(
            book_id=UUID(sample_books[1]),
            text="Quote from book 2",
        ))

        result = manager.export_quotes(book_id=sample_books[0], format="text")

        assert "Quote from book 1" in result
        assert "Quote from book 2" not in result
