"""Command-line interface for booktracker.

Built with Typer for commands and Rich for beautiful output.
"""

from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import get_config
from .db import get_db
from .db.schemas import BookCreate, BookStatus, BookUpdate, ReadingLogCreate

# Create the main app
app = typer.Typer(
    name="booktracker",
    help="Track your reading with Notion integration.",
    no_args_is_help=True,
)

# Create sub-apps for command groups
import_app = typer.Typer(help="Import books from CSV files.")
app.add_typer(import_app, name="import")

# Rich console for pretty output
console = Console()


# ============================================================================
# Helper Functions
# ============================================================================


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]Error:[/bold red] {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]Success:[/bold green] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]Warning:[/bold yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[dim]{message}[/dim]")


def format_book_table(books: list, title: str = "Books") -> Table:
    """Create a rich table for displaying books."""
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Title", style="cyan", no_wrap=False, max_width=40)
    table.add_column("Author", style="green", max_width=25)
    table.add_column("Status", style="yellow")
    table.add_column("Rating", justify="center")
    table.add_column("Progress", justify="center")

    for book in books:
        rating = "★" * (book.rating or 0) + "☆" * (5 - (book.rating or 0)) if book.rating else "-"
        table.add_row(
            book.title,
            book.author,
            book.status,
            rating,
            book.progress or "-",
        )

    return table


# ============================================================================
# Book Management Commands
# ============================================================================


@app.command()
def add(
    query: str = typer.Argument(..., help="Book title to search for"),
    isbn: Optional[str] = typer.Option(None, "--isbn", "-i", help="Add by ISBN instead"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Filter by author"),
    status: BookStatus = typer.Option(BookStatus.WISHLIST, "--status", "-s", help="Initial status"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max search results"),
) -> None:
    """Add a new book by searching Open Library.

    Search for a book by title (or ISBN with --isbn flag), review the results,
    and add the selected book to your library.
    """
    from .api import OpenLibraryClient, OpenLibraryError

    db = get_db()
    client = OpenLibraryClient()

    if isbn:
        # Check if book already exists
        existing = db.get_book_by_isbn(isbn)
        if existing:
            print_warning(f"Book with ISBN {isbn} already exists: {existing.title}")
            raise typer.Exit(1)

        console.print(f"[dim]Looking up ISBN: {isbn}...[/dim]")
        try:
            result = client.get_by_isbn(isbn)
        except OpenLibraryError as e:
            print_error(f"Open Library error: {e}")
            raise typer.Exit(1)

        if not result:
            print_error(f"No book found with ISBN: {isbn}")
            console.print("[dim]Try 'booktracker add-manual' to add manually.[/dim]")
            raise typer.Exit(1)

        # Show book details and confirm
        _show_book_preview(result)
        if not typer.confirm("\nAdd this book?", default=True):
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

        book_data = result.to_book_create(status=status)
        book = db.create_book(book_data)
        print_success(f"Added: {book.title} by {book.author}")
        return

    # Search by title/author
    console.print(f"[dim]Searching Open Library for: {query}...[/dim]")
    try:
        if author:
            results = client.search(query, author=author, limit=limit)
        else:
            results = client.search(query, limit=limit)
    except OpenLibraryError as e:
        print_error(f"Open Library error: {e}")
        raise typer.Exit(1)

    if not results:
        print_error(f"No books found matching: {query}")
        console.print("[dim]Try 'booktracker add-manual' to add manually.[/dim]")
        raise typer.Exit(1)

    # Display results
    console.print(f"\n[bold]Found {len(results)} results:[/bold]\n")
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="cyan", width=3)
    table.add_column("Title", width=35)
    table.add_column("Author", width=20)
    table.add_column("Year", width=6)
    table.add_column("ISBN", width=14)

    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r.title[:35],
            r.author[:20],
            str(r.first_publish_year or "-"),
            r.isbn13 or r.isbn or "-",
        )

    console.print(table)

    # Let user select
    choice = typer.prompt("\nSelect book number (0 to cancel)", type=int, default=1)
    if choice == 0 or choice > len(results):
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    selected = results[choice - 1]

    # Check for duplicates
    if selected.isbn:
        existing = db.get_book_by_isbn(selected.isbn)
        if existing:
            print_warning(f"This book already exists: {existing.title}")
            raise typer.Exit(1)
    if selected.isbn13:
        existing = db.get_book_by_isbn(selected.isbn13)
        if existing:
            print_warning(f"This book already exists: {existing.title}")
            raise typer.Exit(1)

    # Show preview and confirm
    _show_book_preview(selected)
    if not typer.confirm("\nAdd this book?", default=True):
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    book_data = selected.to_book_create(status=status)
    book = db.create_book(book_data)
    print_success(f"Added: {book.title} by {book.author}")

    pending = db.count_pending_sync_items()
    console.print(f"[dim]({pending} items pending sync to Notion)[/dim]")


def _show_book_preview(result) -> None:
    """Display a book preview panel."""
    from .api import BookResult

    if not isinstance(result, BookResult):
        return

    lines = [
        f"[bold]{result.title}[/bold]",
        f"by {result.author}",
    ]

    if result.first_publish_year:
        lines.append(f"Published: {result.first_publish_year}")
    if result.publisher:
        lines.append(f"Publisher: {result.publisher}")
    if result.page_count:
        lines.append(f"Pages: {result.page_count}")
    if result.isbn13 or result.isbn:
        lines.append(f"ISBN: {result.isbn13 or result.isbn}")
    if result.subjects:
        lines.append(f"Subjects: {', '.join(result.subjects[:5])}")
    if result.cover_url:
        lines.append(f"Cover: {result.cover_url}")

    console.print(Panel("\n".join(lines), title="Book Details"))


@app.command("add-manual")
def add_manual(
    title: str = typer.Option(..., "--title", "-t", prompt="Book title"),
    author: str = typer.Option(..., "--author", "-a", prompt="Author"),
    isbn: Optional[str] = typer.Option(None, "--isbn", "-i", help="ISBN"),
    status: BookStatus = typer.Option(
        BookStatus.WISHLIST, "--status", "-s", help="Reading status"
    ),
    pages: Optional[int] = typer.Option(None, "--pages", "-p", help="Page count"),
) -> None:
    """Add a book manually (without Open Library search)."""
    db = get_db()

    # Check for duplicates
    if isbn:
        existing = db.get_book_by_isbn(isbn)
        if existing:
            print_warning(f"Book with ISBN {isbn} already exists: {existing.title}")
            raise typer.Exit(1)

    book_data = BookCreate(
        title=title,
        author=author,
        isbn=isbn,
        status=status,
        page_count=pages,
        date_added=date.today(),
    )

    book = db.create_book(book_data)
    print_success(f"Added: {book.title} by {book.author}")

    # Show sync status
    pending = db.count_pending_sync_items()
    console.print(f"[dim]({pending} items pending sync to Notion)[/dim]")


@app.command()
def update(
    query: str = typer.Argument(..., help="Book title or ID to update"),
    status: Optional[BookStatus] = typer.Option(None, "--status", "-s", help="New status"),
    rating: Optional[int] = typer.Option(None, "--rating", "-r", min=1, max=5, help="Rating 1-5"),
    progress: Optional[str] = typer.Option(None, "--progress", "-p", help="Progress (e.g., '50%')"),
    finished: bool = typer.Option(False, "--finished", "-f", help="Mark as finished today"),
) -> None:
    """Update a book's status, rating, or progress."""
    db = get_db()

    # Search for the book
    books = db.search_books(query, limit=5)
    if not books:
        print_error(f"No book found matching: {query}")
        raise typer.Exit(1)

    if len(books) == 1:
        book = books[0]
    else:
        # Show options and let user choose
        console.print("\n[bold]Multiple books found:[/bold]")
        for i, b in enumerate(books, 1):
            console.print(f"  {i}. {b.title} by {b.author}")

        choice = typer.prompt("Select book number", type=int, default=1)
        if choice < 1 or choice > len(books):
            print_error("Invalid selection")
            raise typer.Exit(1)
        book = books[choice - 1]

    # Build update
    update_data = BookUpdate()
    if status:
        update_data.status = status
    if rating:
        update_data.rating = rating
    if progress:
        update_data.progress = progress
    if finished:
        update_data.status = BookStatus.COMPLETED
        update_data.date_finished = date.today()

    db.update_book(book.id, update_data)
    print_success(f"Updated: {book.title}")


@app.command("list")
def list_books(
    status: Optional[BookStatus] = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max books to show"),
) -> None:
    """List books, optionally filtered by status."""
    db = get_db()

    if status:
        books = db.get_books_by_status(status.value)
        title = f"Books - {status.value.title()}"
    else:
        books = db.get_all_books()
        title = "All Books"

    if not books:
        console.print("[dim]No books found.[/dim]")
        return

    books = books[:limit]
    table = format_book_table(books, title=title)
    console.print(table)

    total = len(db.get_all_books())
    if len(books) < total:
        console.print(f"[dim]Showing {len(books)} of {total} books[/dim]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
) -> None:
    """Search for books by title or author."""
    db = get_db()
    books = db.search_books(query, limit=limit)

    if not books:
        console.print(f"[dim]No books found matching: {query}[/dim]")
        return

    table = format_book_table(books, title=f"Search: {query}")
    console.print(table)


# ============================================================================
# Reading Log Commands
# ============================================================================


@app.command()
def read(
    query: Optional[str] = typer.Argument(None, help="Book title to start/stop reading"),
    start: bool = typer.Option(False, "--start", "-s", help="Start a reading session"),
    stop: bool = typer.Option(False, "--stop", "-x", help="Stop the current session"),
    cancel: bool = typer.Option(False, "--cancel", "-c", help="Cancel session without logging"),
    page: Optional[int] = typer.Option(None, "--page", "-p", help="Current page number"),
    note: Optional[str] = typer.Option(None, "--note", "-n", help="Add a note"),
    location: Optional[str] = typer.Option(None, "--location", "-l", help="Where you're reading"),
) -> None:
    """Manage reading sessions (start, stop, update progress).

    Examples:
      booktracker read "1984" --start --page 1      # Start reading from page 1
      booktracker read --page 50                     # Update progress to page 50
      booktracker read --note "Great chapter!"       # Add a note to current session
      booktracker read --stop --page 75              # Stop session at page 75
      booktracker read                               # Show current session status
    """
    from .reading import get_session_manager

    db = get_db()
    manager = get_session_manager(db)

    # Show current session status if no action specified
    if not any([start, stop, cancel, page, note]) and not query:
        session = manager.active_session
        if not session:
            console.print("[dim]No active reading session.[/dim]")
            console.print("[dim]Use 'booktracker read \"Book Title\" --start' to begin.[/dim]")
            return

        duration = session.duration_minutes()
        pages = session.pages_read()

        table = Table(title="Active Reading Session", show_header=False)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Book", session.book_title)
        table.add_row("Started", session.start_time.strftime("%H:%M"))
        table.add_row("Duration", f"{duration} minutes")
        if session.start_page:
            table.add_row("Start Page", str(session.start_page))
        if session.current_page:
            table.add_row("Current Page", str(session.current_page))
        if pages:
            table.add_row("Pages Read", str(pages))
        if session.location:
            table.add_row("Location", session.location)
        if session.notes:
            table.add_row("Notes", f"{len(session.notes)} note(s)")

        console.print(table)
        console.print("\n[dim]Use --stop to end, --page to update progress, --note to add notes[/dim]")
        return

    # Cancel current session
    if cancel:
        if manager.cancel_session():
            print_success("Reading session cancelled.")
        else:
            print_warning("No active session to cancel.")
        return

    # Stop current session
    if stop:
        log_entry = manager.stop_session(end_page=page, final_note=note)
        if log_entry:
            console.print("[green]Reading session logged![/green]")
            if log_entry.pages_read:
                console.print(f"  Pages read: {log_entry.pages_read}")
            if log_entry.duration_minutes:
                console.print(f"  Duration: {log_entry.duration_minutes} minutes")
        else:
            print_warning("No active session to stop.")
        return

    # Update current session progress
    if (page or note) and not start:
        session = manager.update_progress(current_page=page, note=note)
        if session:
            if page:
                console.print(f"[green]Progress updated to page {page}[/green]")
            if note:
                console.print("[green]Note added.[/green]")
        else:
            print_warning("No active session to update.")
        return

    # Start a new session
    if start and query:
        # Find the book
        books = db.search_books(query, limit=5)
        if not books:
            print_error(f"No book found matching: {query}")
            raise typer.Exit(1)

        if len(books) == 1:
            book = books[0]
        else:
            console.print("\n[bold]Multiple books found:[/bold]")
            for i, b in enumerate(books, 1):
                console.print(f"  {i}. {b.title} by {b.author}")
            choice = typer.prompt("Select book number", type=int, default=1)
            if choice < 1 or choice > len(books):
                print_error("Invalid selection")
                raise typer.Exit(1)
            book = books[choice - 1]

        try:
            session = manager.start_session(
                book_id=book.id,
                start_page=page,
                location=location,
            )
            console.print(f"[green]Started reading:[/green] {session.book_title}")
            if page:
                console.print(f"  Starting from page {page}")
            console.print("[dim]Use 'booktracker read --stop' when done.[/dim]")
        except ValueError as e:
            print_error(str(e))
            raise typer.Exit(1)
        return

    if start and not query:
        print_error("Specify a book title to start reading.")
        raise typer.Exit(1)


@app.command()
def log(
    query: str = typer.Argument(..., help="Book title to log reading for"),
    pages: Optional[int] = typer.Option(None, "--pages", "-p", help="Pages read"),
    start_page: Optional[int] = typer.Option(None, "--from", help="Starting page"),
    end_page: Optional[int] = typer.Option(None, "--to", help="Ending page"),
    duration: Optional[int] = typer.Option(None, "--duration", "-d", help="Minutes spent"),
    location: Optional[str] = typer.Option(None, "--location", "-l", help="Where you read"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Reading notes"),
    session_date: Optional[str] = typer.Option(None, "--date", help="Date (YYYY-MM-DD, default: today)"),
) -> None:
    """Log a reading session manually (without start/stop timer)."""
    from .reading import get_session_manager

    db = get_db()
    manager = get_session_manager(db)

    # Find the book
    books = db.search_books(query, limit=5)
    if not books:
        print_error(f"No book found matching: {query}")
        raise typer.Exit(1)

    book = books[0]
    if len(books) > 1:
        console.print("\n[bold]Multiple books found:[/bold]")
        for i, b in enumerate(books, 1):
            console.print(f"  {i}. {b.title} by {b.author}")
        choice = typer.prompt("Select book number", type=int, default=1)
        if choice < 1 or choice > len(books):
            print_error("Invalid selection")
            raise typer.Exit(1)
        book = books[choice - 1]

    log_date = date.fromisoformat(session_date) if session_date else None

    try:
        manager.log_session(
            book_id=book.id,
            pages_read=pages,
            start_page=start_page,
            end_page=end_page,
            duration_minutes=duration,
            location=location,
            notes=notes,
            session_date=log_date,
        )
        print_success(f"Logged reading session for: {book.title}")
        if pages:
            console.print(f"  Pages: {pages}")
        if duration:
            console.print(f"  Duration: {duration} minutes")
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command()
def reading(
    book_query: Optional[str] = typer.Argument(None, help="Show progress for specific book"),
) -> None:
    """Show currently reading books with progress."""
    from .reading import ProgressTracker

    db = get_db()
    tracker = ProgressTracker(db)

    if book_query:
        # Show detailed progress for a specific book
        books = db.search_books(book_query, limit=1)
        if not books:
            print_error(f"No book found matching: {book_query}")
            raise typer.Exit(1)

        book = books[0]
        try:
            progress = tracker.get_book_progress(book.id)
        except ValueError as e:
            print_error(str(e))
            raise typer.Exit(1)

        # Show detailed progress panel
        lines = [
            f"[bold]{progress['book_title']}[/bold]",
            "",
        ]

        if progress['total_pages']:
            bar_width = 30
            filled = int((progress['progress_percent'] / 100) * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            lines.append(f"Progress: [{bar}] {progress['progress_percent']}%")
            lines.append(f"Page {progress['current_page']} of {progress['total_pages']}")
        else:
            lines.append(f"Pages read: {progress['pages_read']}")

        lines.append("")
        lines.append(f"Reading sessions: {progress['sessions_count']}")
        if progress['time_spent_minutes']:
            hours = progress['time_spent_minutes'] // 60
            mins = progress['time_spent_minutes'] % 60
            if hours:
                lines.append(f"Time spent: {hours}h {mins}m")
            else:
                lines.append(f"Time spent: {mins} minutes")

        if progress['estimated_time_remaining']:
            est_hours = progress['estimated_time_remaining'] // 60
            est_mins = progress['estimated_time_remaining'] % 60
            if est_hours:
                lines.append(f"Est. remaining: {est_hours}h {est_mins}m")
            else:
                lines.append(f"Est. remaining: {est_mins} minutes")

        console.print(Panel("\n".join(lines), title="Reading Progress"))
        return

    # Show all currently reading books
    currently_reading = tracker.get_currently_reading()

    if not currently_reading:
        console.print("[dim]No books currently being read.[/dim]")
        console.print("[dim]Use 'booktracker read \"Book Title\" --start' to begin reading.[/dim]")
        return

    table = Table(title="Currently Reading", show_header=True, header_style="bold magenta")
    table.add_column("Title", style="cyan", max_width=35)
    table.add_column("Author", style="green", max_width=20)
    table.add_column("Progress", justify="center")
    table.add_column("Page", justify="right")
    table.add_column("Last Read")

    for book in currently_reading:
        # Create progress bar
        pct = book['progress_percent']
        bar_width = 10
        filled = int((pct / 100) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)

        page_info = ""
        if book['current_page'] and book['total_pages']:
            page_info = f"{book['current_page']}/{book['total_pages']}"
        elif book['current_page']:
            page_info = f"p.{book['current_page']}"

        table.add_row(
            book['title'][:35],
            book['author'][:20],
            f"[{bar}] {pct}%",
            page_info,
            book['last_read_date'] or "-",
        )

    console.print(table)


@app.command()
def history(
    book_query: Optional[str] = typer.Argument(None, help="Filter by book title"),
    days: int = typer.Option(30, "--days", "-d", help="Number of days to show"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max entries to show"),
) -> None:
    """Show reading history."""
    from datetime import timedelta
    from .reading import ProgressTracker

    db = get_db()
    tracker = ProgressTracker(db)

    start_date = date.today() - timedelta(days=days)
    end_date = date.today()

    # Find book ID if query provided
    book_id = None
    if book_query:
        books = db.search_books(book_query, limit=1)
        if not books:
            print_error(f"No book found matching: {book_query}")
            raise typer.Exit(1)
        book_id = books[0].id

    history_entries = tracker.get_reading_history(
        book_id=book_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    if not history_entries:
        console.print(f"[dim]No reading history in the last {days} days.[/dim]")
        return

    title = f"Reading History (Last {days} Days)"
    if book_query:
        title = f"Reading History: {history_entries[0]['book_title']}"

    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Date", style="cyan")
    table.add_column("Book", max_width=30)
    table.add_column("Pages", justify="right")
    table.add_column("Time", justify="right")
    table.add_column("Location")

    for entry in history_entries:
        time_str = ""
        if entry['duration_minutes']:
            if entry['duration_minutes'] >= 60:
                time_str = f"{entry['duration_minutes'] // 60}h {entry['duration_minutes'] % 60}m"
            else:
                time_str = f"{entry['duration_minutes']}m"

        pages_str = ""
        if entry['pages_read']:
            pages_str = str(entry['pages_read'])
        elif entry['start_page'] and entry['end_page']:
            pages_str = f"{entry['start_page']}-{entry['end_page']}"

        table.add_row(
            entry['date'],
            entry['book_title'][:30] if not book_query else "-",
            pages_str,
            time_str,
            entry['location'] or "-",
        )

    console.print(table)

    # Show summary
    total_pages = sum(e['pages_read'] or 0 for e in history_entries)
    total_minutes = sum(e['duration_minutes'] or 0 for e in history_entries)
    console.print(f"\n[dim]Total: {total_pages} pages, ", end="")
    if total_minutes >= 60:
        console.print(f"{total_minutes // 60}h {total_minutes % 60}m[/dim]")
    else:
        console.print(f"{total_minutes} minutes[/dim]")


# ============================================================================
# Sync Commands
# ============================================================================


@app.command()
def sync(
    status_only: bool = typer.Option(False, "--status", "-s", help="Show sync status only"),
    force_pull: bool = typer.Option(False, "--force-pull", help="Force full refresh from Notion"),
    push_only: bool = typer.Option(False, "--push", help="Only push local changes"),
    pull_only: bool = typer.Option(False, "--pull", help="Only pull from Notion"),
    non_interactive: bool = typer.Option(False, "--yes", "-y", help="Auto-resolve conflicts (Notion wins)"),
) -> None:
    """Sync local database with Notion."""
    config = get_config()
    db = get_db()

    if not config.has_notion_config():
        print_error("Notion not configured. Set NOTION_API_KEY and NOTION_DATABASE_ID.")
        raise typer.Exit(1)

    pending = db.count_pending_sync_items()

    if status_only:
        console.print(Panel(f"[bold]{pending}[/bold] items pending sync", title="Sync Status"))
        all_books = db.get_all_books()
        synced = sum(1 for b in all_books if b.notion_page_id)
        console.print(f"[dim]Local books: {len(all_books)} ({synced} synced to Notion)[/dim]")
        return

    from .sync import SyncProcessor, NotionConfigError

    try:
        processor = SyncProcessor(db=db)
    except NotionConfigError as e:
        print_error(str(e))
        raise typer.Exit(1)

    interactive = not non_interactive

    if force_pull or pull_only:
        console.print("[bold]Pulling from Notion...[/bold]")
        result = processor.pull_changes(interactive=interactive)
        console.print(f"\n[green]Pulled: {result.pulled} books[/green]")
        if result.conflicts:
            console.print(f"[yellow]Conflicts resolved: {result.conflicts}[/yellow]")
        if result.errors:
            print_error(f"{len(result.errors)} errors occurred")
            for title, error in result.errors[:5]:
                console.print(f"  [red]- {title}: {error}[/red]")
            raise typer.Exit(1)
        return

    if push_only:
        if pending == 0:
            console.print("[green]✓[/green] No pending changes to push.")
            return
        console.print(f"[bold]Pushing {pending} items to Notion...[/bold]")
        result = processor.push_pending(interactive=interactive)
        console.print(f"\n[green]Pushed: {result.pushed} items[/green]")
        if result.errors:
            print_error(f"{len(result.errors)} errors occurred")
            raise typer.Exit(1)
        return

    # Full sync (push + pull)
    if pending == 0:
        console.print("[dim]No pending local changes.[/dim]")

    result = processor.sync(interactive=interactive)

    console.print("\n" + "=" * 40)
    console.print("[bold]Sync Complete[/bold]")
    console.print("=" * 40)
    console.print(f"  Pushed to Notion: {result.pushed}")
    console.print(f"  Pulled from Notion: {result.pulled}")
    if result.conflicts:
        console.print(f"  Conflicts resolved: {result.conflicts}")
    if result.skipped:
        console.print(f"  Skipped: {result.skipped}")
    if result.errors:
        print_error(f"{len(result.errors)} errors occurred")
        raise typer.Exit(1)
    else:
        console.print("\n[green]✓ Sync successful![/green]")


# ============================================================================
# Import Commands
# ============================================================================


@import_app.command("notion")
def import_notion_cmd(
    file: Path = typer.Argument(..., help="Path to Notion CSV export"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without importing"),
    backup_first: bool = typer.Option(False, "--backup", "-b", help="Backup database first"),
    non_interactive: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
) -> None:
    """Import books from Notion CSV export."""
    if not file.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(1)

    if backup_first:
        from datetime import datetime
        import shutil

        config = get_config()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config.db_path.parent / f"books_backup_{timestamp}.db"
        if config.db_path.exists():
            shutil.copy2(config.db_path, backup_path)
            console.print(f"[dim]Database backed up to: {backup_path}[/dim]")

    from .etl import import_notion

    result = import_notion(
        file_path=file,
        dry_run=dry_run,
        interactive=not non_interactive,
    )

    if dry_run:
        return

    if result.errors:
        raise typer.Exit(1)


@import_app.command("calibre")
def import_calibre_cmd(
    file: Path = typer.Argument(..., help="Path to Calibre CSV export"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without importing"),
    backup_first: bool = typer.Option(False, "--backup", "-b", help="Backup database first"),
    non_interactive: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
) -> None:
    """Import books from Calibre CSV export."""
    if not file.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(1)

    if backup_first:
        from datetime import datetime
        import shutil

        config = get_config()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config.db_path.parent / f"books_backup_{timestamp}.db"
        if config.db_path.exists():
            shutil.copy2(config.db_path, backup_path)
            console.print(f"[dim]Database backed up to: {backup_path}[/dim]")

    from .etl import import_calibre

    result = import_calibre(
        file_path=file,
        dry_run=dry_run,
        interactive=not non_interactive,
    )

    if dry_run:
        return

    if result.errors:
        raise typer.Exit(1)


@import_app.command("goodreads")
def import_goodreads_cmd(
    file: Path = typer.Argument(..., help="Path to Goodreads CSV export"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without importing"),
    backup_first: bool = typer.Option(False, "--backup", "-b", help="Backup database first"),
    non_interactive: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
) -> None:
    """Import books from Goodreads CSV export."""
    if not file.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(1)

    if backup_first:
        from datetime import datetime
        import shutil

        config = get_config()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config.db_path.parent / f"books_backup_{timestamp}.db"
        if config.db_path.exists():
            shutil.copy2(config.db_path, backup_path)
            console.print(f"[dim]Database backed up to: {backup_path}[/dim]")

    from .etl import import_goodreads

    result = import_goodreads(
        file_path=file,
        dry_run=dry_run,
        interactive=not non_interactive,
    )

    if dry_run:
        return

    if result.errors:
        raise typer.Exit(1)


@import_app.command("all")
def import_all_cmd(
    notion: Optional[Path] = typer.Option(None, "--notion", help="Notion CSV file"),
    calibre: Optional[Path] = typer.Option(None, "--calibre", help="Calibre CSV file"),
    goodreads: Optional[Path] = typer.Option(None, "--goodreads", help="Goodreads CSV file"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without importing"),
    backup_first: bool = typer.Option(False, "--backup", "-b", help="Backup database first"),
    non_interactive: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
) -> None:
    """Import books from all sources at once."""
    if not any([notion, calibre, goodreads]):
        print_error("At least one source file is required.")
        raise typer.Exit(1)

    # Validate all files exist
    for path, name in [(notion, "Notion"), (calibre, "Calibre"), (goodreads, "Goodreads")]:
        if path and not path.exists():
            print_error(f"{name} file not found: {path}")
            raise typer.Exit(1)

    if backup_first:
        from datetime import datetime
        import shutil

        config = get_config()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config.db_path.parent / f"books_backup_{timestamp}.db"
        if config.db_path.exists():
            shutil.copy2(config.db_path, backup_path)
            console.print(f"[dim]Database backed up to: {backup_path}[/dim]")

    from .etl import import_from_csv

    result = import_from_csv(
        notion_path=notion,
        calibre_path=calibre,
        goodreads_path=goodreads,
        dry_run=dry_run,
        interactive=not non_interactive,
    )

    if dry_run:
        return

    if result.errors:
        raise typer.Exit(1)


@import_app.command("csv")
def import_csv_generic(
    file: Path = typer.Argument(..., help="Path to CSV file"),
    title_col: Optional[str] = typer.Option(None, "--title", help="Title column name"),
    author_col: Optional[str] = typer.Option(None, "--author", help="Author column name"),
    duplicates: str = typer.Option("skip", "--duplicates", "-d", help="Handle duplicates: skip, update, replace"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without importing"),
) -> None:
    """Import books from any CSV file with auto-detection."""
    from .imports import GenericCSVImporter, FieldMapping, DuplicateHandling

    if not file.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(1)

    db = get_db()

    # Create field mapping if columns specified
    mapping = None
    if title_col or author_col:
        mapping = FieldMapping(
            title=title_col or "title",
            author=author_col or "author",
        )

    importer = GenericCSVImporter(db, mapping)

    # Get duplicate handling mode
    dup_map = {
        "skip": DuplicateHandling.SKIP,
        "update": DuplicateHandling.UPDATE,
        "replace": DuplicateHandling.REPLACE,
    }
    dup_mode = dup_map.get(duplicates, DuplicateHandling.SKIP)

    # Preview first
    preview = importer.preview_import(file)
    if not preview.get("valid"):
        print_error(f"Invalid file: {preview.get('error')}")
        raise typer.Exit(1)

    console.print(Panel("[bold]Import Preview[/bold]", style="magenta"))
    console.print(f"Total records: {preview['total_records']}")
    console.print(f"New books: {preview['new_books']}")
    console.print(f"Already in library: {preview['existing_books']}")

    if preview.get("top_authors"):
        console.print("\n[bold]Top Authors:[/bold]")
        for author, count in preview["top_authors"]:
            console.print(f"  {author}: {count} books")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made.[/dim]")
        return

    # Perform import
    result = importer.import_file(file, duplicate_handling=dup_mode)

    if result.success:
        print_success(f"Import complete! {result.summary}")
    else:
        print_error("Import failed")
        for error in result.error_messages[:5]:
            console.print(f"  [red]{error}[/red]")


@import_app.command("preview")
def import_preview(
    file: Path = typer.Argument(..., help="Path to file to preview"),
    source: str = typer.Option("auto", "--source", "-s", help="Source type: auto, goodreads, calibre, csv"),
) -> None:
    """Preview what would be imported from a file."""
    if not file.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(1)

    db = get_db()

    # Determine importer
    if source == "auto":
        # Auto-detect based on file content
        source = _detect_import_source(file)

    importer = _get_importer(source, db)
    if not importer:
        print_error(f"Unknown source type: {source}")
        raise typer.Exit(1)

    preview = importer.preview_import(file)

    if not preview.get("valid"):
        print_error(f"Invalid file: {preview.get('error')}")
        raise typer.Exit(1)

    console.print(Panel(f"[bold]Import Preview: {source.title()}[/bold]", style="magenta"))

    table = Table(show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Records", str(preview["total_records"]))
    table.add_row("New Books", str(preview["new_books"]))
    table.add_row("Already Exists", str(preview["existing_books"]))

    console.print(table)

    if preview.get("statuses"):
        console.print("\n[bold]By Status:[/bold]")
        for status, count in preview["statuses"].items():
            console.print(f"  {status}: {count}")

    if preview.get("top_authors"):
        console.print("\n[bold]Top Authors:[/bold]")
        for author, count in preview["top_authors"][:10]:
            console.print(f"  {author}: {count} books")


@import_app.command("goodreads-enhanced")
def import_goodreads_enhanced(
    file: Path = typer.Argument(..., help="Path to Goodreads CSV export"),
    duplicates: str = typer.Option("skip", "--duplicates", "-d", help="Handle duplicates: skip, update, replace"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without importing"),
) -> None:
    """Import books from Goodreads using enhanced parser."""
    from .imports import GoodreadsImporter, DuplicateHandling

    if not file.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(1)

    db = get_db()
    importer = GoodreadsImporter(db)

    # Get duplicate handling mode
    dup_map = {
        "skip": DuplicateHandling.SKIP,
        "update": DuplicateHandling.UPDATE,
        "replace": DuplicateHandling.REPLACE,
    }
    dup_mode = dup_map.get(duplicates, DuplicateHandling.SKIP)

    # Validate and preview
    is_valid, error = importer.validate_file(file)
    if not is_valid:
        print_error(f"Invalid Goodreads file: {error}")
        raise typer.Exit(1)

    preview = importer.preview_import(file)
    console.print(Panel("[bold]Goodreads Import Preview[/bold]", style="green"))
    console.print(f"Total records: {preview['total_records']}")
    console.print(f"New books: {preview['new_books']}")
    console.print(f"Already in library: {preview['existing_books']}")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made.[/dim]")
        return

    result = importer.import_file(file, duplicate_handling=dup_mode)

    if result.success:
        print_success(f"Goodreads import complete! {result.summary}")
    else:
        print_error("Import failed")
        for error in result.error_messages[:5]:
            console.print(f"  [red]{error}[/red]")


@import_app.command("calibre-enhanced")
def import_calibre_enhanced(
    file: Path = typer.Argument(..., help="Path to Calibre CSV export or library folder"),
    duplicates: str = typer.Option("skip", "--duplicates", "-d", help="Handle duplicates: skip, update, replace"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without importing"),
) -> None:
    """Import books from Calibre using enhanced parser."""
    from .imports import CalibreImporter, DuplicateHandling
    from .imports.calibre import CalibreLibraryImporter

    if not file.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(1)

    db = get_db()

    # Determine if this is a CSV or library folder
    if file.is_dir():
        importer = CalibreLibraryImporter(db)
    else:
        importer = CalibreImporter(db)

    # Get duplicate handling mode
    dup_map = {
        "skip": DuplicateHandling.SKIP,
        "update": DuplicateHandling.UPDATE,
        "replace": DuplicateHandling.REPLACE,
    }
    dup_mode = dup_map.get(duplicates, DuplicateHandling.SKIP)

    # Validate
    is_valid, error = importer.validate_file(file)
    if not is_valid:
        print_error(f"Invalid Calibre source: {error}")
        raise typer.Exit(1)

    preview = importer.preview_import(file)
    console.print(Panel("[bold]Calibre Import Preview[/bold]", style="blue"))
    console.print(f"Total records: {preview['total_records']}")
    console.print(f"New books: {preview['new_books']}")
    console.print(f"Already in library: {preview['existing_books']}")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made.[/dim]")
        return

    result = importer.import_file(file, duplicate_handling=dup_mode)

    if result.success:
        print_success(f"Calibre import complete! {result.summary}")
    else:
        print_error("Import failed")
        for error in result.error_messages[:5]:
            console.print(f"  [red]{error}[/red]")


def _detect_import_source(file: Path) -> str:
    """Detect import source type from file."""
    import csv

    try:
        with open(file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            columns = set(c.lower() for c in (reader.fieldnames or []))

            # Goodreads markers
            if "exclusive shelf" in columns or "bookshelves" in columns:
                return "goodreads"

            # Calibre markers
            if "uuid" in columns or "identifiers" in columns:
                return "calibre"

            return "csv"
    except Exception:
        return "csv"


def _get_importer(source: str, db):
    """Get importer for source type."""
    from .imports import GoodreadsImporter, CalibreImporter, GenericCSVImporter

    importers = {
        "goodreads": GoodreadsImporter,
        "calibre": CalibreImporter,
        "csv": GenericCSVImporter,
    }

    importer_class = importers.get(source)
    if importer_class:
        return importer_class(db)
    return None


# ============================================================================
# Export & Backup Commands
# ============================================================================


# Create export sub-app
export_app = typer.Typer(help="Export data to CSV, JSON, or generate reports.")
app.add_typer(export_app, name="export")


@export_app.command("csv")
def export_csv(
    output: Path = typer.Option(
        Path("./books_export.csv"), "--output", "-o", help="Output file path"
    ),
    format: str = typer.Option(
        "standard", "--format", "-f",
        help="Format: standard, goodreads, notion, calibre"
    ),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
) -> None:
    """Export books to CSV file."""
    from .export import CSVExporter, ExportFormat

    db = get_db()
    exporter = CSVExporter(db)

    # Parse format
    try:
        export_format = ExportFormat(format.lower())
    except ValueError:
        print_error(f"Invalid format: {format}. Use: standard, goodreads, notion, calibre")
        raise typer.Exit(1)

    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = BookStatus(status.lower())
        except ValueError:
            print_error(f"Invalid status: {status}")
            raise typer.Exit(1)

    console.print(f"[dim]Exporting to {output}...[/dim]")
    result = exporter.export_books(output, format=export_format, status_filter=status_filter)

    if result.success:
        print_success(f"Exported {result.records_exported} books to {result.file_path}")
    else:
        print_error(f"Export failed: {result.error}")
        raise typer.Exit(1)


@export_app.command("json")
def export_json(
    output: Path = typer.Option(
        Path("./books_export.json"), "--output", "-o", help="Output file path"
    ),
    include_logs: bool = typer.Option(True, "--logs/--no-logs", help="Include reading logs"),
    compact: bool = typer.Option(False, "--compact", "-c", help="Compact JSON output"),
) -> None:
    """Export all data to JSON file."""
    from .export import JSONExporter

    db = get_db()
    exporter = JSONExporter(db)

    console.print(f"[dim]Exporting to {output}...[/dim]")
    result = exporter.export_all(output, include_reading_logs=include_logs, pretty=not compact)

    if result.success:
        print_success(f"Exported {result.books_exported} books, {result.logs_exported} reading logs")
        console.print(f"  Output: {result.file_path}")
    else:
        print_error(f"Export failed: {result.error}")
        raise typer.Exit(1)


@export_app.command("logs")
def export_logs(
    output: Path = typer.Option(
        Path("./reading_logs.csv"), "--output", "-o", help="Output file path"
    ),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Filter by book title"),
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Last N days only"),
    json_format: bool = typer.Option(False, "--json", "-j", help="Export as JSON"),
) -> None:
    """Export reading logs to CSV or JSON."""
    from datetime import timedelta

    db = get_db()

    # Get book ID if filtering by book
    book_id = None
    if book:
        books = db.search_books(book, limit=1)
        if not books:
            print_error(f"No book found matching: {book}")
            raise typer.Exit(1)
        book_id = books[0].id

    # Calculate date range
    start_date = None
    if days:
        start_date = date.today() - timedelta(days=days)

    if json_format:
        from .export import JSONExporter
        exporter = JSONExporter(db)
        result = exporter.export_reading_logs(
            output,
            book_id=book_id,
            start_date=start_date,
        )
        count = result.logs_exported
    else:
        from .export import CSVExporter
        exporter = CSVExporter(db)
        result = exporter.export_reading_logs(
            output,
            book_id=book_id,
            start_date=start_date,
        )
        count = result.records_exported

    if result.success:
        print_success(f"Exported {count} reading logs to {result.file_path}")
    else:
        print_error(f"Export failed: {result.error}")
        raise typer.Exit(1)


# ============================================================================
# Report Commands
# ============================================================================

# Create report sub-app
report_app = typer.Typer(help="Generate reading reports.")
app.add_typer(report_app, name="report")


@report_app.command("year")
def report_year(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year (default: current)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save to file"),
) -> None:
    """Generate a Year in Review report."""
    from .export import ReportGenerator

    db = get_db()
    generator = ReportGenerator(db)

    if year is None:
        year = date.today().year

    console.print(f"[dim]Generating {year} Year in Review...[/dim]\n")

    review = generator.generate_year_in_review(year)

    if review.books_finished == 0:
        console.print(f"[dim]No books finished in {year}.[/dim]")
        return

    # Display the report
    console.print(Panel(f"[bold]📚 Year in Review: {year}[/bold]", style="magenta"))

    # Overview
    table = Table(title="Overview", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Books Finished", str(review.books_finished))
    table.add_row("Books Started", str(review.books_started))
    table.add_row("Total Pages", f"{review.total_pages:,}")
    if review.total_reading_time_minutes:
        hours = review.total_reading_time_minutes // 60
        table.add_row("Reading Time", f"{hours} hours")
    table.add_row("Reading Sessions", str(review.total_reading_sessions))
    table.add_row("Active Reading Days", str(review.active_reading_days))

    console.print(table)

    # Averages
    avg_table = Table(title="Averages", show_header=False)
    avg_table.add_column("Metric", style="cyan")
    avg_table.add_column("Value", style="green", justify="right")

    if review.avg_rating > 0:
        avg_table.add_row("Average Rating", f"{review.avg_rating}/5")
    avg_table.add_row("Average Book Length", f"{review.avg_book_length:.0f} pages")
    if review.avg_days_to_finish > 0:
        avg_table.add_row("Days to Finish Book", f"{review.avg_days_to_finish:.1f}")
    avg_table.add_row("Pages per Day", f"{review.avg_pages_per_day:.1f}")

    console.print(avg_table)

    # Records
    if review.longest_book or review.highest_rated_book:
        console.print("\n[bold]🏆 Records[/bold]")
        if review.longest_book:
            console.print(f"  Longest: {review.longest_book.title} ({review.longest_book.page_count} pages)")
        if review.shortest_book and review.shortest_book != review.longest_book:
            console.print(f"  Shortest: {review.shortest_book.title} ({review.shortest_book.page_count} pages)")
        if review.highest_rated_book:
            console.print(f"  Highest Rated: {review.highest_rated_book.title}")

    # Top Authors
    if review.top_authors:
        console.print("\n[bold]✍️ Top Authors[/bold]")
        for author, count in review.top_authors[:5]:
            console.print(f"  {author}: {count} book(s)")

    # Top Genres
    if review.top_genres:
        console.print("\n[bold]🏷️ Top Genres[/bold]")
        for genre, count in review.top_genres[:5]:
            console.print(f"  {genre}: {count} book(s)")

    # Five-Star Books
    if review.five_star_books:
        console.print("\n[bold]⭐ Five-Star Books[/bold]")
        for book in review.five_star_books[:5]:
            console.print(f"  • {book.title} by {book.author}")

    # Books by Month Chart
    if review.books_by_month:
        console.print("\n[bold]📅 Books by Month[/bold]")
        import calendar
        for month in range(1, 13):
            count = review.books_by_month.get(month, 0)
            bar = "█" * count if count else "░"
            console.print(f"  {calendar.month_abbr[month]}: {bar} {count}")

    # Highlights
    console.print("\n[bold]🎯 Highlights[/bold]")
    if review.most_productive_month:
        console.print(f"  Most Productive: {review.most_productive_month}")
    if review.favorite_reading_location:
        console.print(f"  Favorite Spot: {review.favorite_reading_location}")
    if review.reading_streak_days > 1:
        console.print(f"  Longest Streak: {review.reading_streak_days} days")

    # Year-over-year
    if review.books_vs_last_year is not None:
        console.print("\n[bold]📊 vs Last Year[/bold]")
        if review.books_vs_last_year >= 0:
            console.print(f"  Books: [green]+{review.books_vs_last_year}[/green]")
        else:
            console.print(f"  Books: [red]{review.books_vs_last_year}[/red]")
        if review.pages_vs_last_year is not None:
            if review.pages_vs_last_year >= 0:
                console.print(f"  Pages: [green]+{review.pages_vs_last_year:,}[/green]")
            else:
                console.print(f"  Pages: [red]{review.pages_vs_last_year:,}[/red]")

    # Save to file if requested
    if output:
        text_report = generator.generate_reading_stats_text(year)
        with open(output, "w", encoding="utf-8") as f:
            f.write(text_report)
        console.print(f"\n[dim]Report saved to: {output}[/dim]")


@report_app.command("month")
def report_month(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year"),
    month: Optional[int] = typer.Option(None, "--month", "-m", help="Month (1-12)"),
) -> None:
    """Generate a monthly reading report."""
    from .export import ReportGenerator
    import calendar

    db = get_db()
    generator = ReportGenerator(db)

    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month

    report = generator.generate_monthly_report(year, month)

    console.print(Panel(f"[bold]📚 {report.month_name} {report.year}[/bold]", style="magenta"))

    if report.books_finished == 0 and report.reading_sessions == 0:
        console.print("[dim]No reading activity this month.[/dim]")
        return

    table = Table(show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Books Finished", str(report.books_finished))
    table.add_row("Pages Read", f"{report.pages_read:,}")
    table.add_row("Reading Sessions", str(report.reading_sessions))
    table.add_row("Active Days", str(report.active_days))

    if report.reading_time_minutes:
        hours = report.reading_time_minutes // 60
        mins = report.reading_time_minutes % 60
        table.add_row("Reading Time", f"{hours}h {mins}m")

    if report.avg_rating > 0:
        table.add_row("Average Rating", f"{report.avg_rating}/5")

    console.print(table)

    if report.books:
        console.print("\n[bold]Books Finished:[/bold]")
        for book in report.books:
            rating = "★" * (book.rating or 0) if book.rating else ""
            console.print(f"  • {book.title} by {book.author} {rating}")


@report_app.command("summary")
def report_summary() -> None:
    """Show a quick reading summary."""
    from .export import ReportGenerator

    db = get_db()
    generator = ReportGenerator(db)

    today = date.today()
    current_year = generator.generate_year_in_review(today.year)
    current_month = generator.generate_monthly_report(today.year, today.month)

    console.print(Panel("[bold]📚 Reading Summary[/bold]", style="magenta"))

    # This month
    console.print(f"\n[bold]{current_month.month_name} {current_month.year}:[/bold]")
    console.print(f"  Books: {current_month.books_finished} | Pages: {current_month.pages_read:,} | Sessions: {current_month.reading_sessions}")

    # This year
    console.print(f"\n[bold]{current_year.year} Year-to-Date:[/bold]")
    console.print(f"  Books: {current_year.books_finished} | Pages: {current_year.total_pages:,}")
    if current_year.avg_rating > 0:
        console.print(f"  Avg Rating: {current_year.avg_rating}/5")

    # Comparison
    if current_year.books_vs_last_year is not None:
        console.print(f"\n[bold]vs Last Year:[/bold]")
        if current_year.books_vs_last_year >= 0:
            console.print(f"  [green]+{current_year.books_vs_last_year} books[/green]")
        else:
            console.print(f"  [red]{current_year.books_vs_last_year} books[/red]")


@report_app.command("heatmap")
def report_heatmap(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year (default: current)"),
    month: Optional[int] = typer.Option(None, "--month", "-m", help="Show specific month only"),
) -> None:
    """Display a reading activity heatmap."""
    from .reports import ReportManager

    db = get_db()
    manager = ReportManager(db)

    if year is None:
        year = date.today().year

    if month:
        # Show single month heatmap
        heatmap = manager.get_month_heatmap(year, month)
        console.print(Panel(f"[bold]Reading Heatmap: {heatmap.month_name} {heatmap.year}[/bold]", style="magenta"))

        # Display weeks
        console.print("\n[dim]Mon Tue Wed Thu Fri Sat Sun[/dim]")
        intensity_chars = ["  ", "░░", "▒▒", "▓▓", "██"]

        for week in heatmap.weeks:
            row = ""
            for day in week.days:
                char = intensity_chars[day.intensity]
                row += f"{char}  "
            console.print(row)

        # Stats
        console.print(f"\n[cyan]Reading Days:[/cyan] {heatmap.total_reading_days}")
        console.print(f"[cyan]Total Pages:[/cyan] {heatmap.total_pages:,}")
        console.print(f"[cyan]Books Completed:[/cyan] {heatmap.books_completed}")
    else:
        # Show full year heatmap
        heatmap = manager.get_year_heatmap(year)
        console.print(Panel(f"[bold]Reading Heatmap: {heatmap.year}[/bold]", style="magenta"))

        import calendar
        intensity_chars = [" ", "░", "▒", "▓", "█"]

        for heatmap_month in heatmap.months:
            console.print(f"\n[bold]{heatmap_month.month_name}[/bold]")
            month_str = ""
            for week in heatmap_month.weeks:
                for day in week.days:
                    month_str += intensity_chars[day.intensity]
                month_str += " "
            console.print(f"  {month_str}")

        # Legend
        console.print("\n[dim]Legend: ░ light  ▒ medium  ▓ high  █ very high[/dim]")

        # Year stats
        console.print(f"\n[cyan]Total Reading Days:[/cyan] {heatmap.total_reading_days}")
        console.print(f"[cyan]Total Pages:[/cyan] {heatmap.total_pages:,}")
        console.print(f"[cyan]Books Completed:[/cyan] {heatmap.books_completed}")
        console.print(f"[cyan]Current Streak:[/cyan] {heatmap.current_streak} days")
        console.print(f"[cyan]Longest Streak:[/cyan] {heatmap.longest_streak} days")


@report_app.command("dashboard")
def report_dashboard(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year (default: current)"),
) -> None:
    """Show a reading dashboard with key stats."""
    from .reports import ReportManager

    db = get_db()
    manager = ReportManager(db)

    if year is None:
        year = date.today().year

    dashboard = manager.get_dashboard(year)

    console.print(Panel("[bold]Reading Dashboard[/bold]", style="magenta"))

    # Current status
    status_table = Table(title="Current Status", show_header=False)
    status_table.add_column("Metric", style="cyan")
    status_table.add_column("Value", style="green", justify="right")

    status_table.add_row("Currently Reading", str(dashboard.currently_reading))
    status_table.add_row("Books This Year", str(dashboard.books_this_year))
    status_table.add_row("Pages This Year", f"{dashboard.pages_this_year:,}")
    status_table.add_row("Current Streak", f"{dashboard.current_streak} days")

    console.print(status_table)

    # Quick stats
    if dashboard.average_rating or dashboard.favorite_genre or dashboard.favorite_author:
        console.print("\n[bold]Quick Stats[/bold]")
        if dashboard.average_rating:
            console.print(f"  Average Rating: {dashboard.average_rating:.1f}/5")
        console.print(f"  Books per Month: {dashboard.books_per_month:.1f}")
        if dashboard.favorite_genre:
            console.print(f"  Top Genre: {dashboard.favorite_genre}")
        if dashboard.favorite_author:
            console.print(f"  Top Author: {dashboard.favorite_author}")

    # Goals progress
    if dashboard.goals:
        console.print("\n[bold]Goals Progress[/bold]")
        for goal in dashboard.goals:
            pct = goal.percentage
            filled = int(pct / 5)  # 20 chars total
            bar = "█" * filled + "░" * (20 - filled)
            status = "[green]On track[/green]" if goal.on_track else "[yellow]Behind[/yellow]"
            console.print(f"  {goal.goal_type.capitalize()}: [{bar}] {goal.current}/{goal.target} ({pct:.0f}%) {status}")

    # Recent activity
    if dashboard.recent_activity:
        console.print("\n[bold]Recent Activity[/bold]")
        for activity in dashboard.recent_activity[:5]:
            icon = "✓" if activity.activity_type == "completed" else "▶" if activity.activity_type == "started" else "📖"
            console.print(f"  {icon} {activity.date}: {activity.book_title}")
            if activity.details:
                console.print(f"      [dim]{activity.details}[/dim]")

    # Books by month chart
    console.print("\n[bold]Books by Month[/bold]")
    for point in dashboard.books_by_month_chart.data:
        bar = "█" * int(point.value) if point.value else "░"
        console.print(f"  {point.label:>3}: {bar} {int(point.value)}")


@report_app.command("recap")
def report_recap(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year (default: current)"),
    export_format: Optional[str] = typer.Option(None, "--export", "-e", help="Export format: json, markdown, csv"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Generate a detailed yearly recap with fun facts."""
    from .reports import ReportManager, ExportFormat

    db = get_db()
    manager = ReportManager(db)

    if year is None:
        year = date.today().year

    recap = manager.get_yearly_recap(year)

    # Check for export
    if export_format:
        try:
            fmt = ExportFormat(export_format.lower())
        except ValueError:
            print_error(f"Invalid format: {export_format}. Use: json, markdown, csv")
            raise typer.Exit(1)

        export_data = manager.export_recap(year, fmt)
        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(export_data.content)
            print_success(f"Recap exported to: {output}")
        else:
            console.print(export_data.content)
        return

    # Display recap
    console.print(Panel(f"[bold]📚 {year} Year in Review[/bold]", style="magenta"))

    if recap.books_completed == 0:
        console.print(f"[dim]No books completed in {year}.[/dim]")
        return

    # Overview stats
    overview = Table(title="Overview", show_header=False)
    overview.add_column("Metric", style="cyan")
    overview.add_column("Value", style="green", justify="right")

    overview.add_row("Books Completed", str(recap.books_completed))
    overview.add_row("Total Pages", f"{recap.total_pages:,}")
    if recap.total_reading_minutes > 0:
        hours = recap.total_reading_minutes // 60
        overview.add_row("Reading Time", f"{hours} hours")
    overview.add_row("Reading Days", str(recap.reading_days))

    console.print(overview)

    # Averages
    avgs = Table(title="Averages", show_header=False)
    avgs.add_column("Metric", style="cyan")
    avgs.add_column("Value", style="green", justify="right")

    if recap.average_rating:
        avgs.add_row("Average Rating", f"{recap.average_rating:.1f}/5")
    avgs.add_row("Pages per Book", f"{recap.average_pages_per_book:.0f}")
    avgs.add_row("Books per Month", f"{recap.average_books_per_month:.1f}")
    avgs.add_row("Pages per Day", f"{recap.pages_per_day:.1f}")

    console.print(avgs)

    # Highlights
    if recap.highest_rated_books:
        console.print("\n[bold]⭐ Highest Rated[/bold]")
        for book in recap.highest_rated_books[:3]:
            rating = "★" * (book.rating or 0)
            console.print(f"  {book.title} by {book.author or 'Unknown'} {rating}")

    if recap.longest_book:
        console.print(f"\n[bold]📖 Longest Book:[/bold] {recap.longest_book.title} ({recap.longest_book.pages} pages)")

    if recap.shortest_book:
        console.print(f"[bold]📗 Shortest Book:[/bold] {recap.shortest_book.title} ({recap.shortest_book.pages} pages)")

    # Books by month
    console.print("\n[bold]📅 Books by Month[/bold]")
    for month_data in recap.books_by_month:
        bar = "█" * month_data.books_completed if month_data.books_completed else "░"
        console.print(f"  {month_data.month_name[:3]:>3}: {bar} {month_data.books_completed}")

    # Top genres
    if recap.top_genres:
        console.print("\n[bold]🏷️ Top Genres[/bold]")
        for genre in recap.top_genres[:5]:
            console.print(f"  {genre.genre}: {genre.count} books ({genre.percentage:.0f}%)")

    # Top authors
    if recap.top_authors:
        console.print("\n[bold]✍️ Top Authors[/bold]")
        for author in recap.top_authors[:5]:
            rating = f" ({author.average_rating:.1f}★)" if author.average_rating else ""
            console.print(f"  {author.author}: {author.books_read} books{rating}")

    # Streaks
    console.print("\n[bold]🔥 Streaks[/bold]")
    console.print(f"  Current: {recap.current_streak} days")
    console.print(f"  Longest: {recap.longest_streak} days")

    # Year-over-year
    if recap.books_vs_last_year is not None:
        console.print("\n[bold]📊 vs Last Year[/bold]")
        diff = recap.books_vs_last_year
        color = "green" if diff >= 0 else "red"
        sign = "+" if diff > 0 else ""
        console.print(f"  Books: [{color}]{sign}{diff}[/{color}]")
        if recap.pages_vs_last_year is not None:
            page_diff = recap.pages_vs_last_year
            page_color = "green" if page_diff >= 0 else "red"
            page_sign = "+" if page_diff > 0 else ""
            console.print(f"  Pages: [{page_color}]{page_sign}{page_diff:,}[/{page_color}]")

    # Fun facts
    if recap.fun_facts:
        console.print("\n[bold]🎉 Fun Facts[/bold]")
        for fact in recap.fun_facts:
            console.print(f"  • {fact}")


@report_app.command("genres")
def report_genres(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year (default: all time)"),
) -> None:
    """Show genre distribution chart."""
    from .reports import ReportManager

    db = get_db()
    manager = ReportManager(db)

    chart = manager.get_genre_chart(year)

    title = f"Genre Distribution ({year})" if year else "Genre Distribution (All Time)"
    console.print(Panel(f"[bold]{title}[/bold]", style="magenta"))

    if not chart.data:
        console.print("[dim]No genre data available.[/dim]")
        return

    # Find max for scaling
    max_val = max(p.value for p in chart.data) if chart.data else 1

    for point in chart.data:
        pct = (point.value / chart.total * 100) if chart.total > 0 else 0
        bar_len = int((point.value / max_val) * 30) if max_val > 0 else 0
        bar = "█" * bar_len
        console.print(f"  {point.label:>20}: {bar} {int(point.value)} ({pct:.1f}%)")


@report_app.command("ratings")
def report_ratings(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year (default: all time)"),
) -> None:
    """Show rating distribution chart."""
    from .reports import ReportManager

    db = get_db()
    manager = ReportManager(db)

    chart = manager.get_rating_chart(year)

    title = f"Rating Distribution ({year})" if year else "Rating Distribution (All Time)"
    console.print(Panel(f"[bold]{title}[/bold]", style="magenta"))

    if not chart.data:
        console.print("[dim]No rating data available.[/dim]")
        return

    # Find max for scaling
    max_val = max(p.value for p in chart.data) if chart.data else 1

    for point in chart.data:
        bar_len = int((point.value / max_val) * 30) if max_val > 0 else 0
        bar = "█" * bar_len
        console.print(f"  {point.label}: {bar} {int(point.value)}")


@report_app.command("progress")
def report_progress(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year (default: current)"),
) -> None:
    """Show monthly reading progress chart."""
    from .reports import ReportManager

    db = get_db()
    manager = ReportManager(db)

    if year is None:
        year = date.today().year

    chart = manager.get_monthly_progress_chart(year)

    console.print(Panel(f"[bold]{chart.title}[/bold]", style="magenta"))

    if not chart.series:
        console.print("[dim]No progress data available.[/dim]")
        return

    # Find max for scaling
    max_val = max(p.y for p in chart.series) if chart.series else 1

    for point in chart.series:
        bar_len = int((point.y / max_val) * 30) if max_val > 0 else 0
        bar = "█" * bar_len if bar_len else "░"
        console.print(f"  {point.x:>3}: {bar} {int(point.y)}")


@app.command()
def backup(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Backup file path"),
) -> None:
    """Backup the SQLite database to a timestamped file."""
    import shutil
    from datetime import datetime

    config = get_config()
    db_path = config.db_path

    if not db_path.exists():
        print_error(f"Database not found: {db_path}")
        raise typer.Exit(1)

    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = db_path.parent / f"books_backup_{timestamp}.db"

    shutil.copy2(db_path, output)
    print_success(f"Database backed up to: {output}")


# ============================================================================
# Statistics Commands
# ============================================================================


@app.command()
def stats(
    days: int = typer.Option(30, "--days", "-d", help="Number of days for reading stats"),
    all_time: bool = typer.Option(False, "--all", "-a", help="Show all-time stats"),
) -> None:
    """Show reading statistics."""
    from datetime import timedelta
    from .reading import ProgressTracker

    db = get_db()
    books = db.get_all_books()

    if not books:
        console.print("[dim]No books in library.[/dim]")
        return

    # Library stats
    total = len(books)
    completed = len([b for b in books if b.status == BookStatus.COMPLETED.value])
    reading = len([b for b in books if b.status == BookStatus.READING.value])
    wishlist = len([b for b in books if b.status == BookStatus.WISHLIST.value])
    on_hold = len([b for b in books if b.status == BookStatus.ON_HOLD.value])

    table = Table(title="Library Overview", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Total books", str(total))
    table.add_row("Completed", str(completed))
    table.add_row("Currently reading", str(reading))
    table.add_row("Wishlist", str(wishlist))
    table.add_row("Library holds", str(on_hold))

    # Average rating
    rated_books = [b for b in books if b.rating]
    if rated_books:
        avg_rating = sum(b.rating for b in rated_books) / len(rated_books)
        table.add_row("Average rating", f"{avg_rating:.1f} / 5")

    console.print(table)

    # Reading activity stats
    tracker = ProgressTracker(db)

    if all_time:
        start_date = date(2000, 1, 1)  # Far in past
        period_label = "All Time"
    else:
        start_date = date.today() - timedelta(days=days)
        period_label = f"Last {days} Days"

    reading_stats = tracker.get_stats(start_date=start_date, end_date=date.today())

    if reading_stats.total_sessions > 0:
        console.print()  # Blank line

        stats_table = Table(title=f"Reading Activity ({period_label})", show_header=False)
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", style="green", justify="right")

        stats_table.add_row("Reading sessions", str(reading_stats.total_sessions))
        stats_table.add_row("Pages read", str(reading_stats.total_pages))

        if reading_stats.total_minutes:
            hours = reading_stats.total_minutes // 60
            mins = reading_stats.total_minutes % 60
            if hours:
                stats_table.add_row("Time reading", f"{hours}h {mins}m")
            else:
                stats_table.add_row("Time reading", f"{mins}m")

        stats_table.add_row("Books touched", str(reading_stats.total_books))
        stats_table.add_row("Books finished", str(reading_stats.books_finished))

        if reading_stats.avg_pages_per_session > 0:
            stats_table.add_row("Avg pages/session", f"{reading_stats.avg_pages_per_session:.0f}")

        if reading_stats.avg_reading_speed > 0:
            stats_table.add_row("Reading speed", f"{reading_stats.avg_reading_speed:.0f} pages/hr")

        if reading_stats.current_streak_days > 0:
            stats_table.add_row("Current streak", f"{reading_stats.current_streak_days} days")

        if reading_stats.longest_streak_days > 0:
            stats_table.add_row("Longest streak", f"{reading_stats.longest_streak_days} days")

        console.print(stats_table)

        # Show reading by location if available
        if reading_stats.pages_by_location and len(reading_stats.pages_by_location) > 1:
            console.print()
            loc_table = Table(title="Pages by Location", show_header=True, header_style="bold")
            loc_table.add_column("Location", style="cyan")
            loc_table.add_column("Pages", style="green", justify="right")

            for loc, pages in sorted(
                reading_stats.pages_by_location.items(),
                key=lambda x: x[1],
                reverse=True,
            ):
                loc_table.add_row(loc, str(pages))

            console.print(loc_table)
    else:
        console.print(f"\n[dim]No reading sessions logged in the last {days} days.[/dim]")
        console.print("[dim]Use 'booktracker read' or 'booktracker log' to track reading.[/dim]")


# ============================================================================
# Library Commands
# ============================================================================

# Create library sub-app
library_app = typer.Typer(help="Manage library holds, checkouts, and due dates.")
app.add_typer(library_app, name="library")


@library_app.command("hold")
def library_hold(
    query: str = typer.Argument(..., help="Book title to place hold on"),
    location: Optional[str] = typer.Option(None, "--location", "-l", help="Pickup location"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Library name"),
) -> None:
    """Place a hold on a library book."""
    from .library import LibraryTracker

    db = get_db()
    tracker = LibraryTracker(db)

    # Find the book
    books = db.search_books(query, limit=5)
    if not books:
        print_error(f"No book found matching: {query}")
        raise typer.Exit(1)

    if len(books) == 1:
        book = books[0]
    else:
        console.print("\n[bold]Multiple books found:[/bold]")
        for i, b in enumerate(books, 1):
            console.print(f"  {i}. {b.title} by {b.author}")
        choice = typer.prompt("Select book number", type=int, default=1)
        if choice < 1 or choice > len(books):
            print_error("Invalid selection")
            raise typer.Exit(1)
        book = books[choice - 1]

    try:
        item = tracker.place_hold(
            book_id=book.id,
            pickup_location=location,
            library_source=source,
        )
        print_success(f"Hold placed: {item.title}")
        if location:
            console.print(f"  Pickup: {location}")
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)


@library_app.command("checkout")
def library_checkout(
    query: str = typer.Argument(..., help="Book title to check out"),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="Due date (YYYY-MM-DD)"),
    days: int = typer.Option(21, "--days", help="Loan period in days"),
) -> None:
    """Check out a library book (set due date)."""
    from .library import LibraryTracker

    db = get_db()
    tracker = LibraryTracker(db)

    # Find the book
    books = db.search_books(query, limit=5)
    if not books:
        print_error(f"No book found matching: {query}")
        raise typer.Exit(1)

    if len(books) == 1:
        book = books[0]
    else:
        console.print("\n[bold]Multiple books found:[/bold]")
        for i, b in enumerate(books, 1):
            console.print(f"  {i}. {b.title} by {b.author}")
        choice = typer.prompt("Select book number", type=int, default=1)
        if choice < 1 or choice > len(books):
            print_error("Invalid selection")
            raise typer.Exit(1)
        book = books[choice - 1]

    due_date = date.fromisoformat(due) if due else None

    try:
        item = tracker.checkout(
            book_id=book.id,
            due_date=due_date,
            loan_days=days if not due_date else None,
        )
        print_success(f"Checked out: {item.title}")
        console.print(f"  Due: {item.due_date}")
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)


@library_app.command("renew")
def library_renew(
    query: str = typer.Argument(..., help="Book title to renew"),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="New due date (YYYY-MM-DD)"),
    days: int = typer.Option(14, "--days", help="Extension in days"),
) -> None:
    """Renew a library book (extend due date)."""
    from .library import LibraryTracker

    db = get_db()
    tracker = LibraryTracker(db)

    # Find the book
    books = db.search_books(query, limit=5)
    if not books:
        print_error(f"No book found matching: {query}")
        raise typer.Exit(1)

    if len(books) == 1:
        book = books[0]
    else:
        console.print("\n[bold]Multiple books found:[/bold]")
        for i, b in enumerate(books, 1):
            console.print(f"  {i}. {b.title} by {b.author}")
        choice = typer.prompt("Select book number", type=int, default=1)
        if choice < 1 or choice > len(books):
            print_error("Invalid selection")
            raise typer.Exit(1)
        book = books[choice - 1]

    new_due_date = date.fromisoformat(due) if due else None

    try:
        item = tracker.renew(
            book_id=book.id,
            new_due_date=new_due_date,
            extension_days=days if not new_due_date else None,
        )
        print_success(f"Renewed: {item.title}")
        console.print(f"  New due date: {item.due_date}")
        console.print(f"  Renewals used: {item.renewals}")
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)


@library_app.command("return")
def library_return(
    query: str = typer.Argument(..., help="Book title to return"),
    finished: bool = typer.Option(False, "--finished", "-f", help="Mark as finished"),
) -> None:
    """Return a library book."""
    from .library import LibraryTracker

    db = get_db()
    tracker = LibraryTracker(db)

    # Find the book
    books = db.search_books(query, limit=5)
    if not books:
        print_error(f"No book found matching: {query}")
        raise typer.Exit(1)

    if len(books) == 1:
        book = books[0]
    else:
        console.print("\n[bold]Multiple books found:[/bold]")
        for i, b in enumerate(books, 1):
            console.print(f"  {i}. {b.title} by {b.author}")
        choice = typer.prompt("Select book number", type=int, default=1)
        if choice < 1 or choice > len(books):
            print_error("Invalid selection")
            raise typer.Exit(1)
        book = books[choice - 1]

    try:
        item = tracker.return_book(book_id=book.id, mark_finished=finished)
        print_success(f"Returned: {item.title}")
        if finished:
            console.print("  Marked as finished")
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)


@library_app.command("cancel")
def library_cancel(
    query: str = typer.Argument(..., help="Book title to cancel hold"),
) -> None:
    """Cancel a library hold."""
    from .library import LibraryTracker

    db = get_db()
    tracker = LibraryTracker(db)

    # Find the book
    books = db.search_books(query, limit=5)
    if not books:
        print_error(f"No book found matching: {query}")
        raise typer.Exit(1)

    if len(books) == 1:
        book = books[0]
    else:
        console.print("\n[bold]Multiple books found:[/bold]")
        for i, b in enumerate(books, 1):
            console.print(f"  {i}. {b.title} by {b.author}")
        choice = typer.prompt("Select book number", type=int, default=1)
        if choice < 1 or choice > len(books):
            print_error("Invalid selection")
            raise typer.Exit(1)
        book = books[choice - 1]

    try:
        tracker.cancel_hold(book_id=book.id)
        print_success(f"Hold cancelled: {book.title}")
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)


@library_app.command("list")
def library_list(
    all_items: bool = typer.Option(False, "--all", "-a", help="Show all library items"),
    holds_only: bool = typer.Option(False, "--holds", help="Show only holds"),
    checkouts_only: bool = typer.Option(False, "--checkouts", help="Show only checkouts"),
) -> None:
    """List library holds and checkouts."""
    from .library import LibraryTracker

    db = get_db()
    tracker = LibraryTracker(db)

    if holds_only:
        items = tracker.get_holds()
        title = "Library Holds"
    elif checkouts_only:
        items = tracker.get_checkouts()
        title = "Checked Out Books"
    else:
        items = tracker.get_all_library_items()
        title = "Library Items"

    if not items:
        console.print("[dim]No library items found.[/dim]")
        return

    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Title", style="cyan", max_width=35)
    table.add_column("Author", style="green", max_width=20)
    table.add_column("Status")
    table.add_column("Due Date")
    table.add_column("Days Left", justify="right")
    table.add_column("Location")

    for item in items:
        # Status styling
        if item.is_overdue:
            status_str = "[bold red]OVERDUE[/bold red]"
            days_str = f"[red]{item.days_until_due}[/red]"
        elif item.status.value == "checked_out":
            if item.days_until_due is not None and item.days_until_due <= 3:
                status_str = "[yellow]Due Soon[/yellow]"
                days_str = f"[yellow]{item.days_until_due}[/yellow]"
            else:
                status_str = "Checked Out"
                days_str = str(item.days_until_due) if item.days_until_due is not None else "-"
        elif item.status.value == "pending":
            status_str = "[blue]On Hold[/blue]"
            days_str = "-"
        else:
            status_str = item.status.value.title()
            days_str = "-"

        table.add_row(
            item.title[:35],
            item.author[:20],
            status_str,
            str(item.due_date) if item.due_date else "-",
            days_str,
            item.pickup_location or "-",
        )

    console.print(table)


@library_app.command("due")
def library_due(
    days: int = typer.Option(7, "--days", "-d", help="Days to look ahead"),
    overdue_only: bool = typer.Option(False, "--overdue", "-o", help="Show only overdue"),
) -> None:
    """Show books due soon or overdue."""
    from .library import LibraryTracker

    db = get_db()
    tracker = LibraryTracker(db)

    if overdue_only:
        items = tracker.get_overdue()
        title = "Overdue Books"
    else:
        overdue = tracker.get_overdue()
        due_soon = tracker.get_due_soon(days=days)
        items = overdue + due_soon
        title = f"Due Soon (Next {days} Days)"

    if not items:
        if overdue_only:
            console.print("[green]No overdue books![/green]")
        else:
            console.print(f"[green]No books due in the next {days} days.[/green]")
        return

    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Title", style="cyan", max_width=35)
    table.add_column("Author", style="green", max_width=20)
    table.add_column("Due Date")
    table.add_column("Status")
    table.add_column("Renewals", justify="center")

    for item in items:
        if item.is_overdue:
            days_str = f"[bold red]OVERDUE ({abs(item.days_until_due)}d)[/bold red]"
        elif item.days_until_due == 0:
            days_str = "[bold yellow]TODAY[/bold yellow]"
        elif item.days_until_due == 1:
            days_str = "[yellow]Tomorrow[/yellow]"
        else:
            days_str = f"{item.days_until_due} days"

        table.add_row(
            item.title[:35],
            item.author[:20],
            str(item.due_date) if item.due_date else "-",
            days_str,
            f"{item.renewals}/2",
        )

    console.print(table)

    # Summary
    overdue_count = len([i for i in items if i.is_overdue])
    if overdue_count > 0:
        console.print(f"\n[bold red]Warning: {overdue_count} book(s) overdue![/bold red]")


@library_app.command("reminders")
def library_reminders(
    days: int = typer.Option(3, "--days", "-d", help="Days ahead for due soon alerts"),
) -> None:
    """Show library reminders (due soon and overdue)."""
    from .library import LibraryTracker

    db = get_db()
    tracker = LibraryTracker(db)

    reminders = tracker.get_reminders(due_soon_days=days)

    if not reminders:
        console.print("[green]No library reminders - you're all caught up![/green]")
        return

    console.print(Panel("[bold]Library Reminders[/bold]", style="magenta"))

    for reminder in reminders:
        if reminder.reminder_type.value == "overdue":
            icon = "[bold red]![/bold red]"
            style = "red"
        else:
            icon = "[yellow]*[/yellow]"
            style = "yellow"

        console.print(f"  {icon} [{style}]{reminder.message}[/{style}]: {reminder.title}")
        console.print(f"      by {reminder.author}")
        if reminder.due_date:
            console.print(f"      Due: {reminder.due_date}")
        console.print()


@library_app.command("summary")
def library_summary() -> None:
    """Show library summary."""
    from .library import LibraryTracker

    db = get_db()
    tracker = LibraryTracker(db)

    summary = tracker.get_summary()

    table = Table(title="Library Summary", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green", justify="right")

    table.add_row("Holds (waiting)", str(summary["holds_count"]))
    table.add_row("Checked out", str(summary["checkouts_count"]))
    table.add_row("Due soon", str(summary["due_soon_count"]))

    if summary["overdue_count"] > 0:
        table.add_row("[red]Overdue[/red]", f"[bold red]{summary['overdue_count']}[/bold red]")
    else:
        table.add_row("Overdue", "0")

    console.print(table)

    # Show overdue warning
    if summary["overdue_count"] > 0:
        console.print("\n[bold red]You have overdue books! Use 'library due --overdue' for details.[/bold red]")


# ============================================================================
# Goals Commands
# ============================================================================

# Create goals sub-app
goals_app = typer.Typer(help="Manage reading goals.")
app.add_typer(goals_app, name="goals")


@goals_app.command("set")
def goals_set(
    goal_type: str = typer.Argument(..., help="Goal type: books, pages, or minutes"),
    target: int = typer.Argument(..., help="Target number"),
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year (default: current)"),
    month: Optional[int] = typer.Option(None, "--month", "-m", help="Month 1-12 (None = yearly)"),
) -> None:
    """Set a reading goal."""
    from .stats import GoalTracker, GoalType

    # Validate goal type
    try:
        gt = GoalType(goal_type.lower())
    except ValueError:
        print_error(f"Invalid goal type: {goal_type}. Use: books, pages, or minutes")
        raise typer.Exit(1)

    db = get_db()
    tracker = GoalTracker(db)

    goal = tracker.set_goal(
        goal_type=gt,
        target=target,
        year=year,
        month=month,
    )

    period = goal.period_label
    print_success(f"Goal set: {target} {goal_type} for {period}")


@goals_app.command("show")
def goals_show(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year to show"),
    all_goals: bool = typer.Option(False, "--all", "-a", help="Show all goals"),
) -> None:
    """Show reading goals and progress."""
    from .stats import GoalTracker

    db = get_db()
    tracker = GoalTracker(db)

    if all_goals:
        goals = tracker.get_all_goals()
        title = "All Reading Goals"
    else:
        goals = tracker.get_current_goals()
        title = "Current Reading Goals"

    if not goals:
        console.print("[dim]No reading goals set.[/dim]")
        console.print("[dim]Use 'booktracker goals set <type> <target>' to set a goal.[/dim]")
        return

    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Period", style="cyan")
    table.add_column("Type")
    table.add_column("Progress", justify="center")
    table.add_column("Target", justify="right")
    table.add_column("Remaining", justify="right")
    table.add_column("Status")

    for goal in goals:
        # Progress bar
        bar_width = 15
        filled = int((goal.progress_percent / 100) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)

        # Status with color
        if goal.is_complete:
            status = "[bold green]Complete![/bold green]"
        elif goal.progress_percent >= 75:
            status = "[green]On Track[/green]"
        elif goal.progress_percent >= 50:
            status = "[yellow]Making Progress[/yellow]"
        else:
            status = "[dim]In Progress[/dim]"

        table.add_row(
            goal.period_label,
            goal.goal_type.value.title(),
            f"[{bar}] {goal.progress_percent}%",
            str(goal.target),
            str(goal.remaining),
            status,
        )

    console.print(table)


@goals_app.command("progress")
def goals_progress() -> None:
    """Show detailed progress summary for current goals."""
    from .stats import GoalTracker

    db = get_db()
    tracker = GoalTracker(db)

    summary = tracker.get_progress_summary()

    if not summary["goals"]:
        console.print("[dim]No current goals to track.[/dim]")
        return

    console.print(Panel("[bold]Goal Progress Summary[/bold]", style="magenta"))

    for item in summary["goals"]:
        goal = item["goal"]
        expected = item["expected_percent"]
        actual = item["actual_percent"]
        status = item["status"]

        # Status icon
        if status == "complete":
            icon = "[bold green]✓[/bold green]"
            status_text = "[green]Complete![/green]"
        elif status == "on_track":
            icon = "[green]●[/green]"
            status_text = "[green]On Track[/green]"
        else:
            icon = "[yellow]○[/yellow]"
            status_text = "[yellow]Behind[/yellow]"

        console.print(f"\n{icon} [bold]{goal.period_label}[/bold] - {goal.goal_type.value.title()}")
        console.print(f"   Progress: {goal.current}/{goal.target} ({actual}%)")
        console.print(f"   Expected: {expected}% | Status: {status_text}")

        # Calculate required pace
        pace = tracker.calculate_required_pace(goal)
        if pace["remaining"] > 0 and pace["remaining_days"] > 0:
            console.print(f"   Need: {pace['per_day']} {pace['unit']}/day to finish on time")

    # Overall summary
    console.print("\n" + "─" * 40)
    console.print(f"[green]Complete: {summary['complete_count']}[/green] | "
                  f"[green]On Track: {summary['on_track_count']}[/green] | "
                  f"[yellow]Behind: {summary['behind_count']}[/yellow]")


@goals_app.command("delete")
def goals_delete(
    goal_type: str = typer.Argument(..., help="Goal type: books, pages, or minutes"),
    year: int = typer.Argument(..., help="Year of goal to delete"),
    month: Optional[int] = typer.Option(None, "--month", "-m", help="Month (None = yearly)"),
) -> None:
    """Delete a reading goal."""
    from .stats import GoalTracker, GoalType

    # Validate goal type
    try:
        gt = GoalType(goal_type.lower())
    except ValueError:
        print_error(f"Invalid goal type: {goal_type}. Use: books, pages, or minutes")
        raise typer.Exit(1)

    db = get_db()
    tracker = GoalTracker(db)

    if tracker.delete_goal(gt, year, month):
        period = f"{year}" if not month else f"{month}/{year}"
        print_success(f"Goal deleted: {goal_type} for {period}")
    else:
        print_error("Goal not found")
        raise typer.Exit(1)


# ============================================================================
# Insights Commands
# ============================================================================


@app.command()
def insights(
    limit: int = typer.Option(5, "--limit", "-l", help="Number of insights to show"),
    insight_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
) -> None:
    """Show personalized reading insights."""
    from .stats import InsightGenerator, InsightType

    db = get_db()
    generator = InsightGenerator(db)

    if insight_type:
        try:
            it = InsightType(insight_type.lower())
            all_insights = generator.get_insights_by_type(it)
        except ValueError:
            valid_types = ", ".join(t.value for t in InsightType)
            print_error(f"Invalid type: {insight_type}. Valid types: {valid_types}")
            raise typer.Exit(1)
    else:
        all_insights = generator.get_dashboard_insights(limit=limit)

    if not all_insights:
        console.print("[dim]No insights available yet.[/dim]")
        console.print("[dim]Keep reading and tracking to get personalized insights![/dim]")
        return

    console.print(Panel("[bold]Reading Insights[/bold]", style="magenta"))

    for insight in all_insights[:limit]:
        # Icon based on type
        icons = {
            "achievement": "[bold green]🏆[/bold green]",
            "trend": "[blue]📈[/blue]",
            "recommendation": "[yellow]💡[/yellow]",
            "streak": "[orange]🔥[/orange]",
            "comparison": "[cyan]📊[/cyan]",
            "milestone": "[magenta]🎯[/magenta]",
        }
        icon = icons.get(insight.insight_type.value, "•")

        console.print(f"\n{icon} [bold]{insight.title}[/bold]")
        console.print(f"   {insight.message}")


# ============================================================================
# Analytics Commands
# ============================================================================

# Create analytics sub-app
analytics_app = typer.Typer(help="Detailed reading analytics.")
app.add_typer(analytics_app, name="analytics")


@analytics_app.command("year")
def analytics_year(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year to analyze"),
) -> None:
    """Show yearly reading statistics."""
    from .stats import ReadingAnalytics

    db = get_db()
    analytics = ReadingAnalytics(db)

    stats = analytics.get_yearly_stats(year)

    if stats.books_finished == 0 and stats.books_started == 0:
        console.print(f"[dim]No reading activity for {stats.year}.[/dim]")
        return

    console.print(Panel(f"[bold]Reading Stats: {stats.year}[/bold]", style="magenta"))

    # Main stats table
    table = Table(show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Books Finished", str(stats.books_finished))
    table.add_row("Books Started", str(stats.books_started))
    table.add_row("Total Pages", f"{stats.total_pages:,}")

    if stats.total_reading_time:
        hours = stats.total_reading_time // 60
        table.add_row("Reading Time", f"{hours}h")

    if stats.avg_rating > 0:
        table.add_row("Avg Rating", f"{stats.avg_rating}/5")

    if stats.avg_pages_per_book > 0:
        table.add_row("Avg Book Length", f"{stats.avg_pages_per_book:.0f} pages")

    if stats.avg_days_to_finish > 0:
        table.add_row("Avg Days to Finish", f"{stats.avg_days_to_finish:.0f}")

    console.print(table)

    # Books by month
    if stats.books_by_month:
        console.print("\n[bold]Books by Month:[/bold]")
        import calendar
        month_str = ""
        for m in range(1, 13):
            count = stats.books_by_month.get(m, 0)
            bar = "█" * count if count else "░"
            month_str += f"  {calendar.month_abbr[m]}: {bar} {count}\n"
        console.print(month_str)

    # Top authors
    if stats.top_authors:
        console.print("[bold]Top Authors:[/bold]")
        for author, count in stats.top_authors[:5]:
            console.print(f"  {author}: {count} book(s)")

    # Rating distribution
    if stats.rating_distribution:
        console.print("\n[bold]Rating Distribution:[/bold]")
        for rating in range(5, 0, -1):
            count = stats.rating_distribution.get(rating, 0)
            stars = "★" * rating
            bar = "█" * count
            console.print(f"  {stars}: {bar} {count}")


@analytics_app.command("month")
def analytics_month(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year"),
    month: Optional[int] = typer.Option(None, "--month", "-m", help="Month (1-12)"),
) -> None:
    """Show monthly reading statistics."""
    from .stats import ReadingAnalytics

    db = get_db()
    analytics = ReadingAnalytics(db)

    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month

    stats = analytics.get_monthly_stats(year, month)

    import calendar
    month_name = calendar.month_name[month]

    if stats.books_finished == 0 and stats.reading_sessions == 0:
        console.print(f"[dim]No reading activity for {month_name} {year}.[/dim]")
        return

    console.print(Panel(f"[bold]Reading Stats: {month_name} {year}[/bold]", style="magenta"))

    table = Table(show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Books Finished", str(stats.books_finished))
    table.add_row("Pages Read", f"{stats.pages_read:,}")
    table.add_row("Reading Sessions", str(stats.reading_sessions))

    if stats.reading_time:
        hours = stats.reading_time // 60
        mins = stats.reading_time % 60
        table.add_row("Time Reading", f"{hours}h {mins}m")

    table.add_row("Avg Pages/Day", f"{stats.avg_pages_per_day:.1f}")

    console.print(table)

    # Books finished
    if stats.books:
        console.print("\n[bold]Books Finished:[/bold]")
        for book in stats.books:
            rating = "★" * (book["rating"] or 0) if book["rating"] else ""
            console.print(f"  • {book['title']} by {book['author']} {rating}")


@analytics_app.command("authors")
def analytics_authors(
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Search for author"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
) -> None:
    """Show statistics by author."""
    from .stats import ReadingAnalytics

    db = get_db()
    analytics = ReadingAnalytics(db)

    stats = analytics.get_author_stats(author)

    if not stats:
        console.print("[dim]No author data available.[/dim]")
        return

    title = f"Author Stats: {author}" if author else "Author Statistics"
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Author", style="cyan", max_width=30)
    table.add_column("Books", justify="right")
    table.add_column("Pages", justify="right")
    table.add_column("Avg Rating", justify="center")

    for stat in stats[:limit]:
        rating_str = f"{stat.avg_rating}/5" if stat.avg_rating else "-"
        table.add_row(
            stat.author[:30],
            str(stat.books_read),
            f"{stat.total_pages:,}",
            rating_str,
        )

    console.print(table)


@analytics_app.command("genres")
def analytics_genres(
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
) -> None:
    """Show statistics by genre/tag."""
    from .stats import ReadingAnalytics

    db = get_db()
    analytics = ReadingAnalytics(db)

    stats = analytics.get_genre_stats()

    if not stats:
        console.print("[dim]No genre data available.[/dim]")
        console.print("[dim]Add tags to books to see genre statistics.[/dim]")
        return

    table = Table(title="Genre Statistics", show_header=True, header_style="bold magenta")
    table.add_column("Genre", style="cyan", max_width=25)
    table.add_column("Books", justify="right")
    table.add_column("Pages", justify="right")
    table.add_column("Avg Rating", justify="center")

    for stat in stats[:limit]:
        rating_str = f"{stat.avg_rating}/5" if stat.avg_rating else "-"
        table.add_row(
            stat.genre[:25],
            str(stat.books_count),
            f"{stat.total_pages:,}",
            rating_str,
        )

    console.print(table)


@analytics_app.command("pace")
def analytics_pace(
    days: int = typer.Option(30, "--days", "-d", help="Days to analyze"),
) -> None:
    """Show recent reading pace."""
    from .stats import ReadingAnalytics

    db = get_db()
    analytics = ReadingAnalytics(db)

    pace = analytics.get_reading_pace(days)

    if pace["reading_sessions"] == 0:
        console.print(f"[dim]No reading activity in the last {days} days.[/dim]")
        return

    console.print(Panel(f"[bold]Reading Pace: Last {days} Days[/bold]", style="magenta"))

    table = Table(show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Books Finished", str(pace["books_finished"]))
    table.add_row("Total Pages", f"{pace['total_pages']:,}")
    table.add_row("Reading Sessions", str(pace["reading_sessions"]))
    table.add_row("Active Days", str(pace["active_days"]))

    if pace["total_time_minutes"]:
        hours = pace["total_time_minutes"] // 60
        table.add_row("Time Reading", f"{hours}h")

    table.add_row("Pages/Day", f"{pace['pages_per_day']:.1f}")
    table.add_row("Pages/Session", f"{pace['pages_per_session']:.1f}")

    if pace["avg_session_length"] > 0:
        table.add_row("Avg Session", f"{pace['avg_session_length']:.0f} min")

    table.add_row("Reading Frequency", f"{pace['reading_frequency']:.0f}%")

    console.print(table)


@analytics_app.command("ratings")
def analytics_ratings() -> None:
    """Show rating analysis."""
    from .stats import ReadingAnalytics

    db = get_db()
    analytics = ReadingAnalytics(db)

    analysis = analytics.get_rating_analysis()

    if analysis["total_rated"] == 0:
        console.print("[dim]No rated books yet.[/dim]")
        return

    console.print(Panel("[bold]Rating Analysis[/bold]", style="magenta"))

    console.print(f"Total Rated: {analysis['total_rated']} books")
    console.print(f"Average Rating: {analysis['avg_rating']}/5")
    console.print(f"Most Common: {analysis['mode_rating']} stars")

    console.print("\n[bold]Distribution:[/bold]")
    for rating in range(5, 0, -1):
        count = analysis["distribution"].get(rating, 0)
        pct = analysis["distribution_percent"].get(rating, 0)
        stars = "★" * rating + "☆" * (5 - rating)
        bar = "█" * int(pct / 5) if pct else ""
        console.print(f"  {stars}: {bar} {count} ({pct}%)")


@analytics_app.command("all-time")
def analytics_all_time() -> None:
    """Show all-time reading statistics."""
    from .stats import ReadingAnalytics

    db = get_db()
    analytics = ReadingAnalytics(db)

    stats = analytics.get_all_time_stats()

    if stats["books_completed"] == 0:
        console.print("[dim]No completed books yet.[/dim]")
        return

    console.print(Panel("[bold]All-Time Reading Stats[/bold]", style="magenta"))

    table = Table(show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Total Books", str(stats["total_books"]))
    table.add_row("Books Completed", str(stats["books_completed"]))
    table.add_row("Total Pages", f"{stats['total_pages']:,}")
    table.add_row("Reading Hours", f"{stats['total_reading_hours']:,}")
    table.add_row("Days Spent Reading", f"{stats['days_spent_reading']}")
    table.add_row("Years Active", str(stats["years_active"]))

    if stats["avg_rating"] > 0:
        table.add_row("Avg Rating", f"{stats['avg_rating']}/5")

    table.add_row("Books Rated", str(stats["books_rated"]))
    table.add_row("5-Star Books", str(stats["five_star_books"]))
    table.add_row("Avg Book Length", f"{stats['avg_book_length']:.0f} pages")

    console.print(table)

    if stats["longest_book"]:
        console.print(f"\n[bold]Longest Book:[/bold] {stats['longest_book']['title']} "
                      f"({stats['longest_book']['pages']} pages)")

    if stats["first_book_date"]:
        console.print(f"[dim]First book finished: {stats['first_book_date']}[/dim]")


# ============================================================================
# Search Commands
# ============================================================================

search_app = typer.Typer(help="Search your book library.")
app.add_typer(search_app, name="search")


@search_app.command("query")
def search_query(
    query: str = typer.Argument(..., help="Search text"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
) -> None:
    """Quick search by title, author, or description."""
    from .discovery import AdvancedSearch

    db = get_db()
    searcher = AdvancedSearch(db)

    books = searcher.quick_search(query, limit=limit)

    if not books:
        console.print(f"[dim]No books found matching '{query}'[/dim]")
        return

    table = format_book_table(books, f"Search Results: '{query}'")
    console.print(table)
    console.print(f"[dim]Found {len(books)} book(s)[/dim]")


@search_app.command("author")
def search_author(
    author: str = typer.Argument(..., help="Author name"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
) -> None:
    """Search books by author."""
    from .discovery import AdvancedSearch

    db = get_db()
    searcher = AdvancedSearch(db)

    status_filter = BookStatus(status) if status else None
    books = searcher.search_by_author(author, status=status_filter, limit=limit)

    if not books:
        console.print(f"[dim]No books found by '{author}'[/dim]")
        return

    table = format_book_table(books, f"Books by '{author}'")
    console.print(table)


@search_app.command("series")
def search_series(
    series: str = typer.Argument(..., help="Series name"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
) -> None:
    """Search books in a series."""
    from .discovery import AdvancedSearch

    db = get_db()
    searcher = AdvancedSearch(db)

    books = searcher.search_by_series(series, limit=limit)

    if not books:
        console.print(f"[dim]No books found in series '{series}'[/dim]")
        return

    table = Table(title=f"Series: {series}", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Author", style="green")
    table.add_column("Status", style="yellow")

    for book in books:
        idx = str(book.series_index) if book.series_index else "-"
        table.add_row(idx, book.title, book.author, book.status)

    console.print(table)


@search_app.command("tags")
def search_tags(
    tags: str = typer.Argument(..., help="Tags (comma-separated)"),
    match_all: bool = typer.Option(False, "--all", "-a", help="Match all tags"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
) -> None:
    """Search books by tags."""
    from .discovery import AdvancedSearch

    db = get_db()
    searcher = AdvancedSearch(db)

    tag_list = [t.strip() for t in tags.split(",")]
    books = searcher.search_by_tags(tag_list, match_all=match_all, limit=limit)

    if not books:
        console.print(f"[dim]No books found with tags: {tags}[/dim]")
        return

    mode = "all of" if match_all else "any of"
    table = format_book_table(books, f"Books with {mode}: {tags}")
    console.print(table)


@search_app.command("unread")
def search_unread(
    sort: str = typer.Option("added", "--sort", "-s", help="Sort by: added, title, author, pages"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
) -> None:
    """List unread books (wishlist and on-hold)."""
    from .discovery import AdvancedSearch, SortOrder

    sort_map = {
        "added": SortOrder.DATE_ADDED_DESC,
        "title": SortOrder.TITLE_ASC,
        "author": SortOrder.AUTHOR_ASC,
        "pages": SortOrder.PAGE_COUNT_ASC,
    }

    db = get_db()
    searcher = AdvancedSearch(db)

    sort_order = sort_map.get(sort, SortOrder.DATE_ADDED_DESC)
    books = searcher.get_unread_books(sort_by=sort_order, limit=limit)

    if not books:
        console.print("[dim]No unread books in your library.[/dim]")
        return

    table = format_book_table(books, "Unread Books")
    console.print(table)
    console.print(f"[dim]{len(books)} unread book(s)[/dim]")


@search_app.command("rated")
def search_rated(
    min_rating: int = typer.Option(4, "--min", "-m", help="Minimum rating (1-5)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
) -> None:
    """Show highly rated books."""
    from .discovery import AdvancedSearch

    db = get_db()
    searcher = AdvancedSearch(db)

    books = searcher.get_highly_rated(min_rating=min_rating, limit=limit)

    if not books:
        console.print(f"[dim]No books rated {min_rating}+ stars.[/dim]")
        return

    stars = "★" * min_rating + "+"
    table = format_book_table(books, f"Books Rated {stars}")
    console.print(table)


@search_app.command("advanced")
def search_advanced(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Search text"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Author name"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Book status"),
    min_rating: Optional[int] = typer.Option(None, "--min-rating", help="Minimum rating"),
    max_rating: Optional[int] = typer.Option(None, "--max-rating", help="Maximum rating"),
    min_pages: Optional[int] = typer.Option(None, "--min-pages", help="Minimum pages"),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", help="Maximum pages"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Tags (comma-separated)"),
    series: Optional[str] = typer.Option(None, "--series", help="Series name"),
    sort: str = typer.Option("added", "--sort", help="Sort by: added, title, author, rating, pages"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
) -> None:
    """Advanced search with multiple filters."""
    from .discovery import AdvancedSearch, SearchFilters, SortOrder

    sort_map = {
        "added": SortOrder.DATE_ADDED_DESC,
        "title": SortOrder.TITLE_ASC,
        "author": SortOrder.AUTHOR_ASC,
        "rating": SortOrder.RATING_DESC,
        "pages": SortOrder.PAGE_COUNT_DESC,
    }

    filters = SearchFilters(
        query=query,
        author=author,
        status=BookStatus(status) if status else None,
        min_rating=min_rating,
        max_rating=max_rating,
        min_pages=min_pages,
        max_pages=max_pages,
        tags=[t.strip() for t in tags.split(",")] if tags else None,
        series=series,
        sort_by=sort_map.get(sort, SortOrder.DATE_ADDED_DESC),
        limit=limit,
    )

    db = get_db()
    searcher = AdvancedSearch(db)
    result = searcher.search(filters)

    if not result.books:
        console.print("[dim]No books match your filters.[/dim]")
        return

    table = format_book_table(result.books, "Search Results")
    console.print(table)
    console.print(f"[dim]Showing {len(result.books)} of {result.total_count} results[/dim]")


# ============================================================================
# Discovery Commands
# ============================================================================

discover_app = typer.Typer(help="Discover what to read next.")
app.add_typer(discover_app, name="discover")


@discover_app.command("recommendations")
def discover_recommendations(
    limit: int = typer.Option(10, "--limit", "-l", help="Max recommendations"),
) -> None:
    """Get personalized book recommendations."""
    from .discovery import RecommendationEngine

    db = get_db()
    engine = RecommendationEngine(db)

    recs = engine.get_recommendations(limit=limit)

    if not recs:
        console.print("[dim]No recommendations available. Add more books to your library![/dim]")
        return

    console.print(Panel("[bold]Personalized Recommendations[/bold]", style="magenta"))

    for i, rec in enumerate(recs, 1):
        book = rec.book
        rating = f" ({book.goodreads_avg_rating:.1f}★)" if book.goodreads_avg_rating else ""
        console.print(f"\n[bold cyan]{i}. {book.title}[/bold cyan]{rating}")
        console.print(f"   [green]{book.author}[/green]")
        console.print(f"   [dim]{rec.reason}[/dim]")
        if book.page_count:
            console.print(f"   [dim]{book.page_count} pages[/dim]")


@discover_app.command("next")
def discover_next() -> None:
    """Get the top recommendation for what to read next."""
    from .discovery import RecommendationEngine

    db = get_db()
    engine = RecommendationEngine(db)

    rec = engine.get_what_to_read_next()

    if not rec:
        console.print("[dim]No recommendation available.[/dim]")
        return

    book = rec.book
    console.print(Panel("[bold]What to Read Next[/bold]", style="green"))
    console.print(f"\n[bold cyan]{book.title}[/bold cyan]")
    console.print(f"by [green]{book.author}[/green]")
    console.print(f"\n[yellow]{rec.reason}[/yellow]")

    if book.page_count:
        console.print(f"\n[dim]{book.page_count} pages[/dim]")
    if book.goodreads_avg_rating:
        console.print(f"[dim]Goodreads: {book.goodreads_avg_rating:.1f}★[/dim]")


@discover_app.command("by-type")
def discover_by_type(
    rec_type: str = typer.Argument(
        ...,
        help="Type: author, genre, series, length, rated, quick, long-awaited, recent, read-next"
    ),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
) -> None:
    """Get recommendations of a specific type."""
    from .discovery import RecommendationEngine, RecommendationType

    type_map = {
        "author": RecommendationType.BY_AUTHOR,
        "genre": RecommendationType.BY_GENRE,
        "series": RecommendationType.BY_SERIES,
        "length": RecommendationType.BY_LENGTH,
        "rated": RecommendationType.HIGHLY_RATED,
        "quick": RecommendationType.QUICK_READ,
        "long-awaited": RecommendationType.LONG_AWAITED,
        "recent": RecommendationType.RECENTLY_ADDED,
        "read-next": RecommendationType.READ_NEXT,
    }

    if rec_type not in type_map:
        print_error(f"Unknown type: {rec_type}")
        console.print(f"[dim]Available: {', '.join(type_map.keys())}[/dim]")
        return

    db = get_db()
    engine = RecommendationEngine(db)

    recs = engine.get_recommendations_by_type(type_map[rec_type], limit=limit)

    if not recs:
        console.print(f"[dim]No {rec_type} recommendations available.[/dim]")
        return

    console.print(Panel(f"[bold]{rec_type.title()} Recommendations[/bold]", style="magenta"))

    for i, rec in enumerate(recs, 1):
        book = rec.book
        console.print(f"\n[bold cyan]{i}. {book.title}[/bold cyan]")
        console.print(f"   [green]{book.author}[/green]")
        console.print(f"   [dim]{rec.reason}[/dim]")


@discover_app.command("similar")
def discover_similar(
    book_title: str = typer.Argument(..., help="Book title to find similar books for"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
    include_read: bool = typer.Option(False, "--include-read", "-r", help="Include already-read books"),
) -> None:
    """Find books similar to a given book."""
    from .discovery import AdvancedSearch, SimilarBooksFinder

    db = get_db()

    # First find the source book
    searcher = AdvancedSearch(db)
    matches = searcher.quick_search(book_title, limit=5)

    if not matches:
        print_error(f"Book not found: {book_title}")
        return

    source_book = matches[0]
    finder = SimilarBooksFinder(db)

    similar = finder.find_similar(source_book.id, limit=limit, include_read=include_read)

    if not similar:
        console.print(f"[dim]No similar books found for '{source_book.title}'[/dim]")
        return

    console.print(Panel(f"[bold]Books Similar to: {source_book.title}[/bold]", style="magenta"))

    for i, score in enumerate(similar, 1):
        book = score.book
        pct = int(score.total_score * 100)
        console.print(f"\n[bold cyan]{i}. {book.title}[/bold cyan] [dim]({pct}% match)[/dim]")
        console.print(f"   [green]{book.author}[/green]")
        if score.match_reasons:
            console.print(f"   [dim]{', '.join(score.match_reasons[:2])}[/dim]")


@discover_app.command("like-favorites")
def discover_like_favorites(
    min_rating: int = typer.Option(4, "--min-rating", "-r", help="Minimum rating for favorites"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
) -> None:
    """Find books similar to your highly-rated books."""
    from .discovery import SimilarBooksFinder

    db = get_db()
    finder = SimilarBooksFinder(db)

    similar = finder.find_similar_to_favorites(min_rating=min_rating, limit=limit)

    if not similar:
        console.print("[dim]No similar books found. Rate more books![/dim]")
        return

    stars = "★" * min_rating + "+"
    console.print(Panel(f"[bold]Books Like Your {stars} Reads[/bold]", style="magenta"))

    for i, score in enumerate(similar, 1):
        book = score.book
        pct = int(score.total_score * 100)
        console.print(f"\n[bold cyan]{i}. {book.title}[/bold cyan] [dim]({pct}% match)[/dim]")
        console.print(f"   [green]{book.author}[/green]")
        if score.match_reasons:
            console.print(f"   [dim]{', '.join(score.match_reasons[:2])}[/dim]")


@discover_app.command("quick-reads")
def discover_quick_reads(
    max_pages: int = typer.Option(200, "--max-pages", "-p", help="Maximum pages"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
) -> None:
    """Find short books for quick reads."""
    from .discovery import AdvancedSearch

    db = get_db()
    searcher = AdvancedSearch(db)

    books = searcher.get_short_books(max_pages=max_pages, limit=limit)

    if not books:
        console.print(f"[dim]No books under {max_pages} pages found.[/dim]")
        return

    table = Table(title=f"Quick Reads (Under {max_pages} Pages)", show_header=True, header_style="bold magenta")
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Author", style="green")
    table.add_column("Pages", justify="right", style="yellow")
    table.add_column("Status")

    for book in books:
        table.add_row(
            book.title,
            book.author,
            str(book.page_count) if book.page_count else "-",
            book.status,
        )

    console.print(table)


# ============================================================================
# Backup & Restore Commands
# ============================================================================

backup_app = typer.Typer(help="Backup, restore, and verify your library data.")
app.add_typer(backup_app, name="backup")


@backup_app.command("create")
def backup_create(
    output: Path = typer.Argument(..., help="Output file path"),
    compress: bool = typer.Option(True, "--compress/--no-compress", help="Compress backup"),
    sqlite: bool = typer.Option(False, "--sqlite", help="Create SQLite file backup instead"),
) -> None:
    """Create a backup of your library."""
    from .backup import BackupManager

    db = get_db()
    manager = BackupManager(db)

    if sqlite:
        result = manager.create_sqlite_backup(output)
    else:
        result = manager.create_backup(output, compress=compress)

    if result.success:
        print_success(f"Backup created: {result.backup_path}")
        console.print(f"[dim]Size: {result.size_human}[/dim]")
        if result.metadata:
            console.print(f"[dim]Books: {result.metadata.book_count}, Logs: {result.metadata.reading_log_count}[/dim]")
    else:
        print_error(f"Backup failed: {result.error}")


@backup_app.command("restore")
def backup_restore(
    backup_path: Path = typer.Argument(..., help="Path to backup file"),
    mode: str = typer.Option("replace", "--mode", "-m", help="Mode: replace, merge, update"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without restoring"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Restore your library from a backup."""
    from .backup import RestoreManager, RestoreMode

    if not backup_path.exists():
        print_error(f"Backup file not found: {backup_path}")
        return

    mode_map = {
        "replace": RestoreMode.REPLACE,
        "merge": RestoreMode.MERGE,
        "update": RestoreMode.UPDATE,
    }

    if mode not in mode_map:
        print_error(f"Invalid mode: {mode}")
        console.print(f"[dim]Valid modes: {', '.join(mode_map.keys())}[/dim]")
        return

    db = get_db()
    manager = RestoreManager(db)

    # Preview first
    preview = manager.preview_restore(backup_path)
    if "error" in preview:
        print_error(f"Failed to read backup: {preview['error']}")
        return

    console.print(Panel("[bold]Restore Preview[/bold]", style="yellow"))
    console.print(f"Backup created: {preview.get('backup_created', 'Unknown')}")
    console.print(f"Books in backup: {preview['backup_books']}")
    console.print(f"Logs in backup: {preview['backup_logs']}")
    console.print(f"Current books: {preview['current_books']}")

    if mode == "replace":
        console.print("[bold red]WARNING: This will DELETE all current data![/bold red]")

    if dry_run:
        result = manager.restore(backup_path, mode=mode_map[mode], dry_run=True)
        console.print(f"\n[bold]Dry run results:[/bold]")
        console.print(f"  Would restore: {result.books_restored} books, {result.logs_restored} logs")
        if result.books_skipped:
            console.print(f"  Would skip: {result.books_skipped} existing books")
        if result.books_updated:
            console.print(f"  Would update: {result.books_updated} books")
        return

    if not force:
        confirm = typer.confirm("Proceed with restore?")
        if not confirm:
            console.print("[dim]Restore cancelled.[/dim]")
            return

    result = manager.restore(backup_path, mode=mode_map[mode])

    if result.success:
        print_success("Restore completed!")
        console.print(f"  Books restored: {result.books_restored}")
        console.print(f"  Logs restored: {result.logs_restored}")
        if result.books_skipped:
            console.print(f"  Books skipped: {result.books_skipped}")
        if result.books_updated:
            console.print(f"  Books updated: {result.books_updated}")
        if result.warnings:
            console.print(f"\n[yellow]Warnings ({len(result.warnings)}):[/yellow]")
            for warning in result.warnings[:5]:
                console.print(f"  - {warning}")
    else:
        print_error(f"Restore failed: {result.error}")


@backup_app.command("verify")
def backup_verify(
    backup_path: Path = typer.Argument(..., help="Path to backup file"),
) -> None:
    """Verify a backup file's integrity."""
    from .backup import BackupManager

    if not backup_path.exists():
        print_error(f"Backup file not found: {backup_path}")
        return

    db = get_db()
    manager = BackupManager(db)

    is_valid, error = manager.verify_backup(backup_path)

    if is_valid:
        print_success("Backup is valid!")
    else:
        print_error(f"Backup verification failed: {error}")


@backup_app.command("list")
def backup_list(
    directory: Path = typer.Argument(".", help="Directory to search for backups"),
) -> None:
    """List available backups in a directory."""
    from .backup import BackupManager

    db = get_db()
    manager = BackupManager(db)

    backups = manager.list_backups(directory)

    if not backups:
        console.print(f"[dim]No backups found in {directory}[/dim]")
        return

    table = Table(title="Available Backups", show_header=True, header_style="bold magenta")
    table.add_column("File", style="cyan")
    table.add_column("Created", style="green")
    table.add_column("Books")
    table.add_column("Logs")
    table.add_column("Size")

    for path, metadata in backups:
        size = path.stat().st_size
        size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024*1024):.1f} MB"
        table.add_row(
            path.name,
            metadata.created_at[:19] if metadata.created_at else "-",
            str(metadata.book_count),
            str(metadata.reading_log_count),
            size_str,
        )

    console.print(table)


@backup_app.command("check")
def backup_check(
    book_id: Optional[str] = typer.Option(None, "--book", "-b", help="Check specific book only"),
    fix: bool = typer.Option(False, "--fix", "-f", help="Attempt to fix issues"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview fixes only"),
) -> None:
    """Check database integrity."""
    from .backup import IntegrityChecker, IssueSeverity

    db = get_db()
    checker = IntegrityChecker(db)

    if book_id:
        report = checker.check_book(book_id)
    else:
        report = checker.check_all()

    # Display results
    status = "[bold green]PASSED[/bold green]" if report.passed else "[bold red]FAILED[/bold red]"
    console.print(Panel(f"[bold]Integrity Check: {status}[/bold]", style="magenta"))

    console.print(f"Books checked: {report.book_count}")
    console.print(f"Logs checked: {report.log_count}")

    if report.issues:
        console.print(f"\n[bold]Issues Found: {len(report.issues)}[/bold]")
        console.print(f"  Critical: {report.critical_count}")
        console.print(f"  Errors: {report.error_count}")
        console.print(f"  Warnings: {report.warning_count}")
        console.print(f"  Info: {report.info_count}")

        # Show critical and error issues
        for issue in report.get_issues_by_severity(IssueSeverity.CRITICAL):
            console.print(f"\n[bold red][CRITICAL][/bold red] {issue.category}: {issue.message}")
            if issue.book_title:
                console.print(f"  Book: {issue.book_title}")
            if issue.suggestion:
                console.print(f"  [dim]Suggestion: {issue.suggestion}[/dim]")

        for issue in report.get_issues_by_severity(IssueSeverity.ERROR):
            console.print(f"\n[bold red][ERROR][/bold red] {issue.category}: {issue.message}")
            if issue.book_title:
                console.print(f"  Book: {issue.book_title}")

        # Summarize warnings
        warnings = report.get_issues_by_severity(IssueSeverity.WARNING)
        if warnings:
            console.print(f"\n[yellow]Warnings ({len(warnings)}):[/yellow]")
            for issue in warnings[:10]:
                console.print(f"  - {issue.message}")
            if len(warnings) > 10:
                console.print(f"  ... and {len(warnings) - 10} more")

        if fix:
            console.print("\n[bold]Attempting fixes...[/bold]")
            results = checker.fix_issues(report.issues, dry_run=dry_run)
            console.print(f"  Fixed: {results['fixed']}")
            console.print(f"  Skipped: {results['skipped']}")
            console.print(f"  Failed: {results['failed']}")
    else:
        console.print("\n[green]No issues found![/green]")


# ============================================================================
# Collection Commands
# ============================================================================

collection_app = typer.Typer(help="Manage book collections and reading lists.")
app.add_typer(collection_app, name="collection")


@collection_app.command("create")
def collection_create(
    name: str = typer.Argument(..., help="Collection name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Description"),
    smart: bool = typer.Option(False, "--smart", "-s", help="Create smart collection"),
    icon: Optional[str] = typer.Option(None, "--icon", help="Icon name"),
    color: Optional[str] = typer.Option(None, "--color", help="Color name"),
    pinned: bool = typer.Option(False, "--pinned", "-p", help="Pin to top"),
) -> None:
    """Create a new collection."""
    from .collections import CollectionManager, CollectionCreate, CollectionType

    db = get_db()
    manager = CollectionManager(db)

    # Check if already exists
    existing = manager.get_collection_by_name(name)
    if existing:
        print_error(f"Collection '{name}' already exists")
        return

    data = CollectionCreate(
        name=name,
        description=description,
        collection_type=CollectionType.SMART if smart else CollectionType.MANUAL,
        icon=icon,
        color=color,
        is_pinned=pinned,
    )

    collection = manager.create_collection(data)
    print_success(f"Collection created: {collection.name}")
    console.print(f"[dim]ID: {collection.id}[/dim]")

    if smart:
        console.print(
            "[dim]Use 'collection edit --criteria' to set smart collection filters[/dim]"
        )


@collection_app.command("list")
def collection_list(
    smart_only: bool = typer.Option(False, "--smart", "-s", help="Show only smart collections"),
    pinned_only: bool = typer.Option(False, "--pinned", "-p", help="Show only pinned"),
) -> None:
    """List all collections."""
    from .collections import CollectionManager, CollectionType

    db = get_db()
    manager = CollectionManager(db)

    coll_type = CollectionType.SMART if smart_only else None
    collections = manager.list_collections(
        collection_type=coll_type,
        pinned_only=pinned_only,
    )

    if not collections:
        console.print("[dim]No collections found. Create one with 'collection create'[/dim]")
        return

    table = Table(title="Collections", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Books", justify="right")
    table.add_column("Pinned")
    table.add_column("Description", max_width=40)

    for coll in collections:
        book_count = manager.get_book_count(coll.id)
        type_badge = "[blue]smart[/blue]" if coll.is_smart else "[green]manual[/green]"
        pinned_badge = "[yellow]*[/yellow]" if coll.is_pinned else ""

        table.add_row(
            f"{coll.icon or ''} {coll.name}",
            type_badge,
            str(book_count),
            pinned_badge,
            (coll.description or "")[:40],
        )

    console.print(table)


@collection_app.command("show")
def collection_show(
    name: str = typer.Argument(..., help="Collection name"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max books to show"),
) -> None:
    """Show books in a collection."""
    from .collections import CollectionManager

    db = get_db()
    manager = CollectionManager(db)

    collection = manager.get_collection_by_name(name)
    if not collection:
        print_error(f"Collection not found: {name}")
        return

    books = manager.get_collection_books(collection.id, limit=limit)

    # Header
    console.print(
        Panel(
            f"[bold]{collection.name}[/bold]\n{collection.description or ''}",
            style="cyan",
        )
    )

    if collection.is_smart:
        console.print("[dim]Smart collection - books match filter criteria[/dim]")

    if not books:
        console.print("[dim]No books in this collection[/dim]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", style="cyan", max_width=50)
    table.add_column("Author")
    table.add_column("Status")
    table.add_column("Rating")

    for i, book in enumerate(books, 1):
        rating_str = "*" * book.rating if book.rating else "-"
        table.add_row(
            str(i),
            book.title,
            book.author,
            book.status or "-",
            rating_str,
        )

    console.print(table)

    total = manager.get_book_count(collection.id)
    if total > limit:
        console.print(f"[dim]Showing {limit} of {total} books[/dim]")


@collection_app.command("add")
def collection_add(
    collection_name: str = typer.Argument(..., help="Collection name"),
    book_id: str = typer.Argument(..., help="Book ID to add"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notes for this book"),
) -> None:
    """Add a book to a collection."""
    from uuid import UUID
    from .collections import CollectionManager, CollectionBookAdd

    db = get_db()
    manager = CollectionManager(db)

    collection = manager.get_collection_by_name(collection_name)
    if not collection:
        print_error(f"Collection not found: {collection_name}")
        return

    if collection.is_smart:
        print_error("Cannot manually add books to smart collections")
        return

    try:
        data = CollectionBookAdd(book_id=UUID(book_id), notes=notes)
        cb = manager.add_book_to_collection(collection.id, data)

        if cb:
            print_success(f"Book added to '{collection_name}'")
        else:
            print_error("Failed to add book")
    except ValueError as e:
        print_error(str(e))


@collection_app.command("remove")
def collection_remove(
    collection_name: str = typer.Argument(..., help="Collection name"),
    book_id: str = typer.Argument(..., help="Book ID to remove"),
) -> None:
    """Remove a book from a collection."""
    from .collections import CollectionManager

    db = get_db()
    manager = CollectionManager(db)

    collection = manager.get_collection_by_name(collection_name)
    if not collection:
        print_error(f"Collection not found: {collection_name}")
        return

    if collection.is_smart:
        print_error("Cannot manually remove books from smart collections")
        return

    if manager.remove_book_from_collection(collection.id, book_id):
        print_success(f"Book removed from '{collection_name}'")
    else:
        print_error("Book not found in collection")


@collection_app.command("delete")
def collection_delete(
    name: str = typer.Argument(..., help="Collection name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a collection."""
    from .collections import CollectionManager

    db = get_db()
    manager = CollectionManager(db)

    collection = manager.get_collection_by_name(name)
    if not collection:
        print_error(f"Collection not found: {name}")
        return

    book_count = manager.get_book_count(collection.id)

    if not force:
        msg = f"Delete collection '{name}'"
        if book_count > 0 and not collection.is_smart:
            msg += f" (contains {book_count} books)"
        msg += "?"
        if not typer.confirm(msg):
            console.print("[dim]Cancelled.[/dim]")
            return

    try:
        if manager.delete_collection(collection.id):
            print_success(f"Collection '{name}' deleted")
        else:
            print_error("Failed to delete collection")
    except ValueError as e:
        print_error(str(e))


@collection_app.command("edit")
def collection_edit(
    name: str = typer.Argument(..., help="Collection name"),
    new_name: Optional[str] = typer.Option(None, "--name", help="New name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    pinned: Optional[bool] = typer.Option(None, "--pinned/--not-pinned", help="Pin/unpin"),
) -> None:
    """Edit a collection's settings."""
    from .collections import CollectionManager, CollectionUpdate

    db = get_db()
    manager = CollectionManager(db)

    collection = manager.get_collection_by_name(name)
    if not collection:
        print_error(f"Collection not found: {name}")
        return

    update_data = {}
    if new_name is not None:
        update_data["name"] = new_name
    if description is not None:
        update_data["description"] = description
    if pinned is not None:
        update_data["is_pinned"] = pinned

    if not update_data:
        console.print("[dim]No changes specified[/dim]")
        return

    data = CollectionUpdate(**update_data)
    updated = manager.update_collection(collection.id, data)

    if updated:
        print_success(f"Collection updated: {updated.name}")
    else:
        print_error("Failed to update collection")


@collection_app.command("reorder")
def collection_reorder(
    name: str = typer.Argument(..., help="Collection name"),
    book_ids: str = typer.Argument(..., help="Comma-separated book IDs in desired order"),
) -> None:
    """Reorder books in a collection."""
    from .collections import CollectionManager

    db = get_db()
    manager = CollectionManager(db)

    collection = manager.get_collection_by_name(name)
    if not collection:
        print_error(f"Collection not found: {name}")
        return

    if collection.is_smart:
        print_error("Cannot manually reorder smart collections")
        return

    ids = [bid.strip() for bid in book_ids.split(",")]

    if manager.reorder_books(collection.id, ids):
        print_success(f"Books reordered in '{name}'")
    else:
        print_error("Failed to reorder books")


@collection_app.command("init-defaults")
def collection_init_defaults() -> None:
    """Create default smart collections (Favorites, Currently Reading, etc.)."""
    from .collections import CollectionManager

    db = get_db()
    manager = CollectionManager(db)

    created = manager.create_default_collections()

    if created:
        print_success(f"Created {len(created)} default collections:")
        for coll in created:
            console.print(f"  - {coll.name}")
    else:
        console.print("[dim]Default collections already exist[/dim]")


@collection_app.command("for-book")
def collection_for_book(
    book_id: str = typer.Argument(..., help="Book ID"),
) -> None:
    """List collections containing a specific book."""
    from .collections import CollectionManager

    db = get_db()
    manager = CollectionManager(db)

    collections = manager.get_collections_for_book(book_id)

    if not collections:
        console.print("[dim]This book is not in any collections[/dim]")
        return

    console.print(f"[bold]Collections containing this book:[/bold]")
    for coll in collections:
        type_badge = "[blue]smart[/blue]" if coll.is_smart else "[green]manual[/green]"
        console.print(f"  - {coll.name} ({type_badge})")


# ============================================================================
# Challenge Commands
# ============================================================================

challenge_app = typer.Typer(help="Manage reading challenges and track progress.")
app.add_typer(challenge_app, name="challenge")


@challenge_app.command("create")
def challenge_create(
    name: str = typer.Argument(..., help="Challenge name"),
    target: int = typer.Argument(..., help="Target number to reach"),
    start: str = typer.Option(None, "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
    challenge_type: str = typer.Option("books", "--type", "-t", help="Type: books, pages"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Description"),
) -> None:
    """Create a new reading challenge."""
    from datetime import date
    from .challenges import ChallengeManager, ChallengeType
    from .challenges.schemas import ChallengeCreate

    db = get_db()
    manager = ChallengeManager(db)

    # Default dates: today to end of year
    today = date.today()
    if start:
        start_date = date.fromisoformat(start)
    else:
        start_date = today

    if end:
        end_date = date.fromisoformat(end)
    else:
        end_date = date(today.year, 12, 31)

    try:
        ctype = ChallengeType(challenge_type)
    except ValueError:
        print_error(f"Invalid challenge type: {challenge_type}")
        console.print(f"[dim]Valid types: {', '.join(t.value for t in ChallengeType)}[/dim]")
        return

    data = ChallengeCreate(
        name=name,
        description=description,
        challenge_type=ctype,
        target=target,
        start_date=start_date,
        end_date=end_date,
    )

    challenge = manager.create_challenge(data)
    print_success(f"Challenge created: {challenge.name}")
    console.print(f"[dim]Target: {target} {challenge_type}[/dim]")
    console.print(f"[dim]Period: {start_date} to {end_date}[/dim]")


@challenge_app.command("yearly")
def challenge_yearly(
    target: int = typer.Argument(..., help="Number of books to read"),
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year (default: current)"),
) -> None:
    """Create a yearly reading challenge (like Goodreads)."""
    from datetime import date
    from .challenges import ChallengeManager
    from .challenges.schemas import YearlyChallenge

    db = get_db()
    manager = ChallengeManager(db)

    if year is None:
        year = date.today().year

    # Check if challenge already exists
    existing = manager.get_challenge_by_name(f"{year} Reading Challenge")
    if existing:
        print_error(f"A {year} reading challenge already exists")
        console.print(f"[dim]Use 'challenge show' to view it or 'challenge delete' to remove it[/dim]")
        return

    data = YearlyChallenge(year=year, target=target)
    challenge = manager.create_yearly_challenge(data)

    print_success(f"Created: {challenge.name}")
    console.print(f"[bold]Goal: Read {target} books in {year}[/bold]")


@challenge_app.command("list")
def challenge_list(
    active_only: bool = typer.Option(False, "--active", "-a", help="Show only active"),
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Filter by year"),
) -> None:
    """List all challenges."""
    from .challenges import ChallengeManager

    db = get_db()
    manager = ChallengeManager(db)

    challenges = manager.list_challenges(active_only=active_only, year=year)

    if not challenges:
        console.print("[dim]No challenges found. Create one with 'challenge create' or 'challenge yearly'[/dim]")
        return

    table = Table(title="Reading Challenges", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Progress", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("%", justify="right")
    table.add_column("Days Left", justify="right")
    table.add_column("Status")

    for ch in challenges:
        # Progress bar
        percent = ch.progress_percent
        filled = int(percent / 10)
        bar = "[green]" + "*" * filled + "[/green]" + "-" * (10 - filled)

        # Status badge
        if ch.status == "completed":
            status = "[bold green]DONE[/bold green]"
        elif ch.status == "failed":
            status = "[bold red]FAILED[/bold red]"
        elif ch.status == "abandoned":
            status = "[dim]abandoned[/dim]"
        elif ch.is_active:
            status = "[yellow]active[/yellow]"
        else:
            status = "[dim]pending[/dim]"

        table.add_row(
            ch.name,
            f"{ch.current}",
            f"{ch.target}",
            f"{percent:.0f}%",
            str(ch.days_remaining) if ch.is_active else "-",
            status,
        )

    console.print(table)


@challenge_app.command("show")
def challenge_show(
    name: str = typer.Argument(..., help="Challenge name"),
) -> None:
    """Show detailed challenge progress."""
    from .challenges import ChallengeManager

    db = get_db()
    manager = ChallengeManager(db)

    challenge = manager.get_challenge_by_name(name)
    if not challenge:
        print_error(f"Challenge not found: {name}")
        return

    progress = manager.get_progress(challenge.id)
    if not progress:
        print_error("Could not calculate progress")
        return

    # Header
    status_color = "green" if challenge.status == "completed" else "yellow" if challenge.is_active else "red"
    console.print(Panel(
        f"[bold]{challenge.name}[/bold]\n"
        f"{challenge.description or ''}\n"
        f"[{status_color}]{challenge.status.upper()}[/{status_color}]",
        style="cyan",
    ))

    # Progress bar
    percent = progress.percent
    bar_width = 30
    filled = int((percent / 100) * bar_width)
    bar = "[green]" + "#" * filled + "[/green]" + "-" * (bar_width - filled)
    console.print(f"\n  Progress: [{bar}] {percent:.1f}%")
    console.print(f"  Current: {progress.current} / {progress.target} ({progress.remaining} remaining)")

    # Pace info
    if challenge.is_active:
        console.print(f"\n  [bold]Pace Information:[/bold]")
        console.print(f"    Days remaining: {progress.days_remaining}")
        console.print(f"    Current pace: {progress.current_pace:.2f} per day")
        console.print(f"    Needed pace: {progress.pace_needed:.2f} per day")

        if progress.on_track:
            console.print(f"    Status: [green]On track![/green]")
        else:
            console.print(f"    Status: [yellow]Behind pace[/yellow]")

    # Books counted
    books = manager.get_challenge_books(challenge.id)
    if books:
        console.print(f"\n  [bold]Books counted ({len(books)}):[/bold]")
        for i, book in enumerate(books[:10], 1):
            console.print(f"    {i}. {book.title} - {book.author}")
        if len(books) > 10:
            console.print(f"    ... and {len(books) - 10} more")


@challenge_app.command("add")
def challenge_add(
    name: str = typer.Argument(..., help="Challenge name"),
    book_id: str = typer.Argument(..., help="Book ID to add"),
) -> None:
    """Manually add a book to a challenge."""
    from uuid import UUID
    from .challenges import ChallengeManager
    from .challenges.schemas import ChallengeBookAdd

    db = get_db()
    manager = ChallengeManager(db)

    challenge = manager.get_challenge_by_name(name)
    if not challenge:
        print_error(f"Challenge not found: {name}")
        return

    try:
        data = ChallengeBookAdd(book_id=UUID(book_id))
        cb = manager.add_book_to_challenge(challenge.id, data)

        if cb:
            print_success(f"Book added to '{name}'")
            console.print(f"[dim]Progress: {challenge.current + cb.value}/{challenge.target}[/dim]")
        else:
            print_error("Failed to add book")
    except ValueError as e:
        print_error(str(e))


@challenge_app.command("remove")
def challenge_remove(
    name: str = typer.Argument(..., help="Challenge name"),
    book_id: str = typer.Argument(..., help="Book ID to remove"),
) -> None:
    """Remove a book from a challenge."""
    from .challenges import ChallengeManager

    db = get_db()
    manager = ChallengeManager(db)

    challenge = manager.get_challenge_by_name(name)
    if not challenge:
        print_error(f"Challenge not found: {name}")
        return

    if manager.remove_book_from_challenge(challenge.id, book_id):
        print_success(f"Book removed from '{name}'")
    else:
        print_error("Book not found in challenge")


@challenge_app.command("refresh")
def challenge_refresh(
    name: Optional[str] = typer.Argument(None, help="Challenge name (or all if omitted)"),
) -> None:
    """Refresh auto-count challenges."""
    from .challenges import ChallengeManager

    db = get_db()
    manager = ChallengeManager(db)

    if name:
        challenge = manager.get_challenge_by_name(name)
        if not challenge:
            print_error(f"Challenge not found: {name}")
            return

        updated = manager.refresh_challenge(challenge.id)
        if updated:
            print_success(f"Refreshed: {updated.name}")
            console.print(f"[dim]Progress: {updated.current}/{updated.target}[/dim]")
    else:
        count = manager.refresh_all_challenges()
        print_success(f"Refreshed {count} challenges")


@challenge_app.command("delete")
def challenge_delete(
    name: str = typer.Argument(..., help="Challenge name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a challenge."""
    from .challenges import ChallengeManager

    db = get_db()
    manager = ChallengeManager(db)

    challenge = manager.get_challenge_by_name(name)
    if not challenge:
        print_error(f"Challenge not found: {name}")
        return

    if not force:
        if not typer.confirm(f"Delete challenge '{name}'?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    if manager.delete_challenge(challenge.id):
        print_success(f"Challenge '{name}' deleted")
    else:
        print_error("Failed to delete challenge")


@challenge_app.command("update")
def challenge_update(
    name: str = typer.Argument(..., help="Challenge name"),
    target: Optional[int] = typer.Option(None, "--target", "-t", help="New target"),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="New end date"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="New status"),
) -> None:
    """Update a challenge."""
    from datetime import date
    from .challenges import ChallengeManager, ChallengeStatus
    from .challenges.schemas import ChallengeUpdate

    db = get_db()
    manager = ChallengeManager(db)

    challenge = manager.get_challenge_by_name(name)
    if not challenge:
        print_error(f"Challenge not found: {name}")
        return

    update_data = {}
    if target is not None:
        update_data["target"] = target
    if end is not None:
        update_data["end_date"] = date.fromisoformat(end)
    if status is not None:
        try:
            update_data["status"] = ChallengeStatus(status)
        except ValueError:
            print_error(f"Invalid status: {status}")
            return

    if not update_data:
        console.print("[dim]No changes specified[/dim]")
        return

    data = ChallengeUpdate(**update_data)
    updated = manager.update_challenge(challenge.id, data)

    if updated:
        print_success(f"Challenge updated: {updated.name}")
    else:
        print_error("Failed to update challenge")


# ============================================================================
# Lending Commands
# ============================================================================

lending_app = typer.Typer(help="Track books lent to or borrowed from others.")
app.add_typer(lending_app, name="lending")


@lending_app.command("lend")
def lending_lend(
    book_id: str = typer.Argument(..., help="Book ID to lend"),
    contact: str = typer.Argument(..., help="Contact name"),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="Due date (YYYY-MM-DD)"),
    condition: Optional[str] = typer.Option(None, "--condition", "-c", help="Book condition"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notes"),
) -> None:
    """Lend a book to someone."""
    from datetime import date
    from uuid import UUID
    from .lending import LendingManager, LoanType
    from .lending.schemas import LoanCreate, BookCondition

    db = get_db()
    manager = LendingManager(db)

    # Get or create contact
    contact_obj = manager.get_contact_by_name(contact)
    if not contact_obj:
        from .lending.schemas import ContactCreate
        contact_obj = manager.create_contact(ContactCreate(name=contact))
        console.print(f"[dim]Created new contact: {contact}[/dim]")

    # Parse condition
    condition_enum = None
    if condition:
        try:
            condition_enum = BookCondition(condition.lower())
        except ValueError:
            print_error(f"Invalid condition: {condition}")
            console.print(f"[dim]Valid: {', '.join(c.value for c in BookCondition)}[/dim]")
            return

    # Parse due date
    due_date = None
    if due:
        due_date = date.fromisoformat(due)

    try:
        data = LoanCreate(
            book_id=UUID(book_id),
            contact_id=UUID(contact_obj.id),
            loan_type=LoanType.LENT,
            loan_date=date.today(),
            due_date=due_date,
            condition_out=condition_enum,
            notes=notes,
        )
        loan = manager.create_loan(data)
        print_success(f"Book lent to {contact}")
        if due_date:
            console.print(f"[dim]Due: {due_date}[/dim]")
    except ValueError as e:
        print_error(str(e))


@lending_app.command("borrow")
def lending_borrow(
    book_id: str = typer.Argument(..., help="Book ID borrowed"),
    contact: str = typer.Argument(..., help="Contact name"),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="Due date (YYYY-MM-DD)"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notes"),
) -> None:
    """Record borrowing a book from someone."""
    from datetime import date
    from uuid import UUID
    from .lending import LendingManager, LoanType
    from .lending.schemas import LoanCreate

    db = get_db()
    manager = LendingManager(db)

    # Get or create contact
    contact_obj = manager.get_contact_by_name(contact)
    if not contact_obj:
        from .lending.schemas import ContactCreate
        contact_obj = manager.create_contact(ContactCreate(name=contact))
        console.print(f"[dim]Created new contact: {contact}[/dim]")

    # Parse due date
    due_date = None
    if due:
        due_date = date.fromisoformat(due)

    try:
        data = LoanCreate(
            book_id=UUID(book_id),
            contact_id=UUID(contact_obj.id),
            loan_type=LoanType.BORROWED,
            loan_date=date.today(),
            due_date=due_date,
            notes=notes,
        )
        loan = manager.create_loan(data)
        print_success(f"Recorded borrowing from {contact}")
        if due_date:
            console.print(f"[dim]Due: {due_date}[/dim]")
    except ValueError as e:
        print_error(str(e))


@lending_app.command("return")
def lending_return(
    loan_id: str = typer.Argument(..., help="Loan ID to return"),
    condition: Optional[str] = typer.Option(None, "--condition", "-c", help="Return condition"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notes"),
) -> None:
    """Mark a loan as returned."""
    from .lending import LendingManager

    db = get_db()
    manager = LendingManager(db)

    try:
        loan = manager.return_loan(loan_id, condition=condition, notes=notes)
        if loan:
            print_success("Loan marked as returned")
        else:
            print_error("Loan not found")
    except ValueError as e:
        print_error(str(e))


@lending_app.command("list")
def lending_list(
    lent: bool = typer.Option(False, "--lent", "-l", help="Show only lent books"),
    borrowed: bool = typer.Option(False, "--borrowed", "-b", help="Show only borrowed books"),
    active: bool = typer.Option(False, "--active", "-a", help="Show only active loans"),
    overdue: bool = typer.Option(False, "--overdue", "-o", help="Show only overdue loans"),
) -> None:
    """List loan records."""
    from .lending import LendingManager, LoanType, LoanStatus

    db = get_db()
    manager = LendingManager(db)

    loan_type = None
    if lent:
        loan_type = LoanType.LENT
    elif borrowed:
        loan_type = LoanType.BORROWED

    status = LoanStatus.ACTIVE if active else None

    loans = manager.list_loans(
        loan_type=loan_type,
        status=status,
        overdue_only=overdue,
    )

    if not loans:
        console.print("[dim]No loans found[/dim]")
        return

    table = Table(title="Loans", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Type")
    table.add_column("Book", style="cyan", max_width=30)
    table.add_column("Contact")
    table.add_column("Date")
    table.add_column("Due")
    table.add_column("Status")

    for loan in loans:
        # Get book and contact names
        book = db.get_book(loan.book_id)
        contact = manager.get_contact(loan.contact_id)

        type_badge = "[yellow]LENT[/yellow]" if loan.is_lent else "[blue]BORROWED[/blue]"

        if loan.status == "active":
            if loan.is_overdue:
                status_str = f"[bold red]OVERDUE ({loan.days_overdue}d)[/bold red]"
            elif loan.due_date:
                status_str = f"[green]active ({loan.days_until_due}d)[/green]"
            else:
                status_str = "[green]active[/green]"
        elif loan.status == "returned":
            status_str = "[dim]returned[/dim]"
        else:
            status_str = f"[red]{loan.status}[/red]"

        table.add_row(
            loan.id[:8],
            type_badge,
            book.title if book else "Unknown",
            contact.name if contact else "Unknown",
            loan.loan_date,
            loan.due_date or "-",
            status_str,
        )

    console.print(table)


@lending_app.command("overdue")
def lending_overdue() -> None:
    """Show overdue loans."""
    from .lending import LendingManager

    db = get_db()
    manager = LendingManager(db)

    report = manager.get_overdue_loans()

    if not report.loans:
        print_success("No overdue loans!")
        return

    console.print(Panel(
        f"[bold red]Overdue Loans: {report.total_overdue}[/bold red]\n"
        f"Oldest: {report.oldest_overdue_days} days overdue",
        style="red",
    ))

    table = Table(show_header=True, header_style="bold red")
    table.add_column("Type")
    table.add_column("Book", style="cyan")
    table.add_column("Contact")
    table.add_column("Due Date")
    table.add_column("Days Overdue", justify="right")

    for loan in report.loans:
        type_badge = "[yellow]LENT[/yellow]" if loan.loan_type.value == "lent" else "[blue]BORROWED[/blue]"
        days = abs(loan.days_until_due) if loan.days_until_due else 0

        table.add_row(
            type_badge,
            loan.book_title,
            loan.contact_name,
            loan.due_date.isoformat() if loan.due_date else "-",
            f"[bold red]{days}[/bold red]",
        )

    console.print(table)


@lending_app.command("due-soon")
def lending_due_soon(
    days: int = typer.Option(7, "--days", "-d", help="Days to look ahead"),
) -> None:
    """Show loans due soon."""
    from .lending import LendingManager

    db = get_db()
    manager = LendingManager(db)

    loans = manager.get_loans_due_soon(days=days)

    if not loans:
        console.print(f"[dim]No loans due in the next {days} days[/dim]")
        return

    console.print(f"[bold]Loans due in the next {days} days:[/bold]")

    for loan in loans:
        book = db.get_book(loan.book_id)
        contact = manager.get_contact(loan.contact_id)

        days_left = loan.days_until_due or 0
        if days_left <= 2:
            urgency = "[bold red]"
        elif days_left <= 5:
            urgency = "[yellow]"
        else:
            urgency = "[green]"

        type_str = "lent to" if loan.is_lent else "borrowed from"
        console.print(
            f"  {urgency}{loan.due_date}[/]: "
            f"{book.title if book else 'Unknown'} "
            f"({type_str} {contact.name if contact else 'Unknown'})"
        )


@lending_app.command("stats")
def lending_stats() -> None:
    """Show lending statistics."""
    from .lending import LendingManager

    db = get_db()
    manager = LendingManager(db)

    stats = manager.get_stats()

    console.print(Panel("[bold]Lending Statistics[/bold]", style="cyan"))

    console.print(f"\n[bold]Lent Books:[/bold]")
    console.print(f"  Total lent: {stats.total_lent}")
    console.print(f"  Currently out: {stats.currently_lent}")
    if stats.overdue_lent > 0:
        console.print(f"  [red]Overdue: {stats.overdue_lent}[/red]")

    console.print(f"\n[bold]Borrowed Books:[/bold]")
    console.print(f"  Total borrowed: {stats.total_borrowed}")
    console.print(f"  Currently have: {stats.currently_borrowed}")
    if stats.overdue_borrowed > 0:
        console.print(f"  [red]Overdue: {stats.overdue_borrowed}[/red]")

    console.print(f"\n[bold]Contacts:[/bold] {stats.total_contacts}")


@lending_app.command("contacts")
def lending_contacts(
    active: bool = typer.Option(False, "--active", "-a", help="Only show contacts with active loans"),
) -> None:
    """List lending contacts."""
    from .lending import LendingManager

    db = get_db()
    manager = LendingManager(db)

    contacts = manager.list_contacts(with_active_loans=active)

    if not contacts:
        console.print("[dim]No contacts found[/dim]")
        return

    table = Table(title="Contacts", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Email")
    table.add_column("Lent", justify="right")
    table.add_column("Borrowed", justify="right")
    table.add_column("Active", justify="right")

    for contact in contacts:
        table.add_row(
            contact.name,
            contact.email or "-",
            str(contact.total_lent),
            str(contact.total_borrowed),
            str(contact.total_unreturned) if contact.total_unreturned > 0 else "-",
        )

    console.print(table)


@lending_app.command("contact-add")
def lending_contact_add(
    name: str = typer.Argument(..., help="Contact name"),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address"),
    phone: Optional[str] = typer.Option(None, "--phone", "-p", help="Phone number"),
) -> None:
    """Add a new contact."""
    from .lending import LendingManager
    from .lending.schemas import ContactCreate

    db = get_db()
    manager = LendingManager(db)

    existing = manager.get_contact_by_name(name)
    if existing:
        print_error(f"Contact '{name}' already exists")
        return

    data = ContactCreate(name=name, email=email, phone=phone)
    contact = manager.create_contact(data)
    print_success(f"Contact created: {contact.name}")


@lending_app.command("contact-delete")
def lending_contact_delete(
    name: str = typer.Argument(..., help="Contact name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a contact."""
    from .lending import LendingManager

    db = get_db()
    manager = LendingManager(db)

    contact = manager.get_contact_by_name(name)
    if not contact:
        print_error(f"Contact not found: {name}")
        return

    if not force:
        if not typer.confirm(f"Delete contact '{name}'?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    try:
        if manager.delete_contact(contact.id):
            print_success(f"Contact '{name}' deleted")
        else:
            print_error("Failed to delete contact")
    except ValueError as e:
        print_error(str(e))


@lending_app.command("lost")
def lending_lost(
    loan_id: str = typer.Argument(..., help="Loan ID to mark as lost"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notes"),
) -> None:
    """Mark a loan as lost."""
    from .lending import LendingManager

    db = get_db()
    manager = LendingManager(db)

    loan = manager.mark_lost(loan_id, notes=notes)
    if loan:
        print_success("Loan marked as lost")
    else:
        print_error("Loan not found")


# ============================================================================
# Review Commands
# ============================================================================

review_app = typer.Typer(help="Manage book reviews and ratings.")
app.add_typer(review_app, name="review")


@review_app.command("add")
def review_add(
    book: str = typer.Argument(..., help="Book title or ID"),
    rating: Optional[float] = typer.Option(None, "--rating", "-r", help="Rating (0.5-5)"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Review title"),
    content: Optional[str] = typer.Option(None, "--content", "-c", help="Review content"),
    favorite: bool = typer.Option(False, "--favorite", "-f", help="Mark as favorite"),
    spoilers: bool = typer.Option(False, "--spoilers", help="Contains spoilers"),
    recommend: Optional[bool] = typer.Option(None, "--recommend", help="Would recommend"),
    reread: Optional[bool] = typer.Option(None, "--reread", help="Would reread"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
) -> None:
    """Add a review for a book."""
    from uuid import UUID
    from datetime import date
    from .reviews import ReviewManager, ReviewCreate
    from .library import BookTracker

    db = get_db()
    tracker = BookTracker(db)
    manager = ReviewManager(db)

    # Find book
    book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
    if isinstance(book_obj, list):
        book_obj = book_obj[0] if book_obj else None

    if not book_obj:
        print_error(f"Book not found: {book}")
        return

    # Check if review exists
    existing = manager.get_review_by_book(book_obj.id)
    if existing:
        print_error("Review already exists for this book. Use 'review update' instead.")
        return

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    try:
        data = ReviewCreate(
            book_id=UUID(book_obj.id),
            rating=rating,
            title=title,
            content=content,
            is_favorite=favorite,
            contains_spoilers=spoilers,
            would_recommend=recommend,
            would_reread=reread,
            tags=tag_list,
            review_date=date.today(),
        )
        review = manager.create_review(data)

        console.print(Panel(
            f"[bold]{book_obj.title}[/bold]\n"
            f"Rating: {review.star_display}\n"
            f"Favorite: {'Yes' if review.is_favorite else 'No'}",
            title="[green]Review Added[/green]",
        ))
    except ValueError as e:
        print_error(str(e))


@review_app.command("rate")
def review_rate(
    book: str = typer.Argument(..., help="Book title or ID"),
    rating: float = typer.Argument(..., help="Rating (0.5-5)"),
    favorite: bool = typer.Option(False, "--favorite", "-f", help="Mark as favorite"),
) -> None:
    """Quick rate a book."""
    from .reviews import ReviewManager
    from .library import BookTracker

    db = get_db()
    tracker = BookTracker(db)
    manager = ReviewManager(db)

    # Find book
    book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
    if isinstance(book_obj, list):
        book_obj = book_obj[0] if book_obj else None

    if not book_obj:
        print_error(f"Book not found: {book}")
        return

    try:
        review = manager.quick_rate(book_obj.id, rating, favorite)
        console.print(f"[green]Rated[/green] {book_obj.title}: {review.star_display}")
    except ValueError as e:
        print_error(str(e))


@review_app.command("update")
def review_update(
    book: str = typer.Argument(..., help="Book title or ID"),
    rating: Optional[float] = typer.Option(None, "--rating", "-r", help="Rating (0.5-5)"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Review title"),
    content: Optional[str] = typer.Option(None, "--content", "-c", help="Review content"),
    favorite: Optional[bool] = typer.Option(None, "--favorite", "-f", help="Mark as favorite"),
    spoilers: Optional[bool] = typer.Option(None, "--spoilers", help="Contains spoilers"),
    recommend: Optional[bool] = typer.Option(None, "--recommend", help="Would recommend"),
    reread: Optional[bool] = typer.Option(None, "--reread", help="Would reread"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
) -> None:
    """Update a book review."""
    from .reviews import ReviewManager, ReviewUpdate
    from .library import BookTracker

    db = get_db()
    tracker = BookTracker(db)
    manager = ReviewManager(db)

    # Find book
    book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
    if isinstance(book_obj, list):
        book_obj = book_obj[0] if book_obj else None

    if not book_obj:
        print_error(f"Book not found: {book}")
        return

    review = manager.get_review_by_book(book_obj.id)
    if not review:
        print_error("No review found for this book. Use 'review add' instead.")
        return

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    data = ReviewUpdate(
        rating=rating,
        title=title,
        content=content,
        is_favorite=favorite,
        contains_spoilers=spoilers,
        would_recommend=recommend,
        would_reread=reread,
        tags=tag_list,
    )
    updated = manager.update_review(review.id, data)

    if updated:
        print_success(f"Review updated for: {book_obj.title}")
    else:
        print_error("Failed to update review")


@review_app.command("show")
def review_show(
    book: str = typer.Argument(..., help="Book title or ID"),
) -> None:
    """Show review for a book."""
    from .reviews import ReviewManager
    from .library import BookTracker

    db = get_db()
    tracker = BookTracker(db)
    manager = ReviewManager(db)

    # Find book
    book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
    if isinstance(book_obj, list):
        book_obj = book_obj[0] if book_obj else None

    if not book_obj:
        print_error(f"Book not found: {book}")
        return

    review = manager.get_review_by_book(book_obj.id)
    if not review:
        print_error("No review found for this book")
        return

    # Build review display
    content_parts = [
        f"[bold]{book_obj.title}[/bold] by {book_obj.author or 'Unknown'}",
        f"\nRating: {review.star_display}",
    ]

    if review.title:
        content_parts.append(f"\n[italic]\"{review.title}\"[/italic]")

    if review.content:
        if review.contains_spoilers:
            content_parts.append("\n\n[yellow]⚠ Contains Spoilers[/yellow]")
        content_parts.append(f"\n\n{review.content}")

    # Flags
    flags = []
    if review.is_favorite:
        flags.append("❤ Favorite")
    if review.would_recommend:
        flags.append("👍 Recommended")
    if review.would_reread:
        flags.append("🔄 Would Reread")

    if flags:
        content_parts.append(f"\n\n{' | '.join(flags)}")

    # Detailed ratings
    if review.has_detailed_ratings:
        content_parts.append("\n\n[dim]Detailed Ratings:[/dim]")
        if review.plot_rating:
            content_parts.append(f"\n  Plot: {review.plot_rating}/5")
        if review.characters_rating:
            content_parts.append(f"\n  Characters: {review.characters_rating}/5")
        if review.writing_rating:
            content_parts.append(f"\n  Writing: {review.writing_rating}/5")
        if review.pacing_rating:
            content_parts.append(f"\n  Pacing: {review.pacing_rating}/5")
        if review.enjoyment_rating:
            content_parts.append(f"\n  Enjoyment: {review.enjoyment_rating}/5")

    # Tags
    if review.tag_list:
        content_parts.append(f"\n\nTags: {', '.join(review.tag_list)}")

    console.print(Panel("".join(content_parts), title="[blue]Review[/blue]"))


@review_app.command("delete")
def review_delete(
    book: str = typer.Argument(..., help="Book title or ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a book review."""
    from .reviews import ReviewManager
    from .library import BookTracker

    db = get_db()
    tracker = BookTracker(db)
    manager = ReviewManager(db)

    # Find book
    book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
    if isinstance(book_obj, list):
        book_obj = book_obj[0] if book_obj else None

    if not book_obj:
        print_error(f"Book not found: {book}")
        return

    review = manager.get_review_by_book(book_obj.id)
    if not review:
        print_error("No review found for this book")
        return

    if not force:
        if not typer.confirm(f"Delete review for '{book_obj.title}'?"):
            print_info("Cancelled")
            return

    if manager.delete_review(review.id):
        print_success("Review deleted")
    else:
        print_error("Failed to delete review")


@review_app.command("list")
def review_list(
    min_rating: Optional[float] = typer.Option(None, "--min", help="Minimum rating"),
    max_rating: Optional[float] = typer.Option(None, "--max", help="Maximum rating"),
    favorites: bool = typer.Option(False, "--favorites", "-f", help="Only favorites"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by tag"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """List reviews."""
    from .reviews import ReviewManager

    db = get_db()
    manager = ReviewManager(db)

    reviews = manager.list_reviews(
        min_rating=min_rating,
        max_rating=max_rating,
        favorites_only=favorites,
        tag=tag,
    )[:limit]

    if not reviews:
        print_info("No reviews found")
        return

    summaries = manager._to_summaries(reviews)

    table = Table(title="Reviews")
    table.add_column("Title", style="cyan")
    table.add_column("Author")
    table.add_column("Rating", justify="center")
    table.add_column("Fav", justify="center")

    for summary in summaries:
        table.add_row(
            summary.book_title[:40],
            summary.book_author[:25],
            summary.star_display,
            "❤" if summary.is_favorite else "",
        )

    console.print(table)


@review_app.command("favorites")
def review_favorites() -> None:
    """List all favorite books."""
    from .reviews import ReviewManager

    db = get_db()
    manager = ReviewManager(db)

    favorites = manager.get_favorites()

    if not favorites:
        print_info("No favorites yet")
        return

    table = Table(title="❤ Favorite Books")
    table.add_column("Title", style="cyan")
    table.add_column("Author")
    table.add_column("Rating", justify="center")

    for fav in favorites:
        table.add_row(
            fav.book_title[:40],
            fav.book_author[:25],
            fav.star_display,
        )

    console.print(table)


@review_app.command("top")
def review_top(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of books"),
) -> None:
    """Show top rated books."""
    from .reviews import ReviewManager

    db = get_db()
    manager = ReviewManager(db)

    top = manager.get_top_rated(limit)

    if not top:
        print_info("No rated books yet")
        return

    table = Table(title="Top Rated Books")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Title", style="cyan")
    table.add_column("Author")
    table.add_column("Rating", justify="center")
    table.add_column("Fav", justify="center")

    for i, book in enumerate(top, 1):
        stars = "★" * int(book.rating) + ("½" if book.rating % 1 >= 0.5 else "") + "☆" * (5 - int(book.rating) - (1 if book.rating % 1 >= 0.5 else 0))
        table.add_row(
            str(i),
            book.book_title[:35],
            book.book_author[:20],
            stars,
            "❤" if book.is_favorite else "",
        )

    console.print(table)


@review_app.command("stats")
def review_stats() -> None:
    """Show review statistics."""
    from .reviews import ReviewManager

    db = get_db()
    manager = ReviewManager(db)

    stats = manager.get_stats()

    # Build stats display
    content = f"""[bold]Overview[/bold]
Total Reviews: {stats.total_reviews}
Books Rated: {stats.total_rated}
Average Rating: {stats.average_rating or 'N/A'}
Total Favorites: {stats.total_favorites}

[bold]Rating Distribution[/bold]
★★★★★ ({stats.distribution.five_star}): {'█' * min(stats.distribution.five_star, 20)}
★★★★☆ ({stats.distribution.four_star}): {'█' * min(stats.distribution.four_star, 20)}
★★★☆☆ ({stats.distribution.three_star}): {'█' * min(stats.distribution.three_star, 20)}
★★☆☆☆ ({stats.distribution.two_star}): {'█' * min(stats.distribution.two_star, 20)}
★☆☆☆☆ ({stats.distribution.one_star}): {'█' * min(stats.distribution.one_star, 20)}

[bold]Recommendations[/bold]
Would Recommend: {stats.would_recommend_count}
Would Reread: {stats.would_reread_count}"""

    if stats.avg_plot_rating or stats.avg_characters_rating or stats.avg_writing_rating:
        content += "\n\n[bold]Detailed Rating Averages[/bold]"
        if stats.avg_plot_rating:
            content += f"\nPlot: {stats.avg_plot_rating}/5"
        if stats.avg_characters_rating:
            content += f"\nCharacters: {stats.avg_characters_rating}/5"
        if stats.avg_writing_rating:
            content += f"\nWriting: {stats.avg_writing_rating}/5"
        if stats.avg_pacing_rating:
            content += f"\nPacing: {stats.avg_pacing_rating}/5"
        if stats.avg_enjoyment_rating:
            content += f"\nEnjoyment: {stats.avg_enjoyment_rating}/5"

    console.print(Panel(content, title="[blue]Review Statistics[/blue]"))


@review_app.command("tags")
def review_tags() -> None:
    """List all review tags."""
    from .reviews import ReviewManager

    db = get_db()
    manager = ReviewManager(db)

    tags = manager.get_all_tags()

    if not tags:
        print_info("No tags found")
        return

    table = Table(title="Review Tags")
    table.add_column("Tag", style="cyan")
    table.add_column("Count", justify="right")

    for tag, count in tags:
        table.add_row(tag, str(count))

    console.print(table)


@review_app.command("search")
def review_search(
    query: str = typer.Argument(..., help="Search query"),
) -> None:
    """Search reviews by content."""
    from .reviews import ReviewManager

    db = get_db()
    manager = ReviewManager(db)

    results = manager.search_reviews(query)

    if not results:
        print_info(f"No reviews found matching '{query}'")
        return

    table = Table(title=f"Reviews matching '{query}'")
    table.add_column("Title", style="cyan")
    table.add_column("Author")
    table.add_column("Rating", justify="center")

    for review in results:
        table.add_row(
            review.book_title[:40],
            review.book_author[:25],
            review.star_display,
        )

    console.print(table)


@review_app.command("toggle-favorite")
def review_toggle_favorite(
    book: str = typer.Argument(..., help="Book title or ID"),
) -> None:
    """Toggle favorite status for a book."""
    from .reviews import ReviewManager
    from .library import BookTracker

    db = get_db()
    tracker = BookTracker(db)
    manager = ReviewManager(db)

    # Find book
    book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
    if isinstance(book_obj, list):
        book_obj = book_obj[0] if book_obj else None

    if not book_obj:
        print_error(f"Book not found: {book}")
        return

    review = manager.toggle_favorite(book_obj.id)
    if review:
        status = "added to" if review.is_favorite else "removed from"
        console.print(f"[green]{book_obj.title}[/green] {status} favorites")
    else:
        print_error("No review found for this book. Rate or review it first.")


# ============================================================================
# Notes Commands
# ============================================================================

notes_app = typer.Typer(help="Manage reading notes and annotations.")
app.add_typer(notes_app, name="notes")


@notes_app.command("add")
def notes_add(
    book: str = typer.Argument(..., help="Book title or ID"),
    content: str = typer.Argument(..., help="Note content"),
    note_type: str = typer.Option("note", "--type", "-t", help="Note type"),
    title: Optional[str] = typer.Option(None, "--title", help="Note title"),
    chapter: Optional[str] = typer.Option(None, "--chapter", "-c", help="Chapter"),
    page: Optional[int] = typer.Option(None, "--page", "-p", help="Page number"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
    favorite: bool = typer.Option(False, "--favorite", "-f", help="Mark as favorite"),
    private: bool = typer.Option(False, "--private", help="Mark as private"),
) -> None:
    """Add a note for a book."""
    from uuid import UUID
    from .notes import NotesManager, NoteCreate, NoteType
    from .library import BookTracker

    db = get_db()
    tracker = BookTracker(db)
    manager = NotesManager(db)

    # Find book
    book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
    if isinstance(book_obj, list):
        book_obj = book_obj[0] if book_obj else None

    if not book_obj:
        print_error(f"Book not found: {book}")
        return

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    try:
        note_type_enum = NoteType(note_type)
    except ValueError:
        print_error(f"Invalid note type: {note_type}")
        return

    try:
        data = NoteCreate(
            book_id=UUID(book_obj.id),
            note_type=note_type_enum,
            title=title,
            content=content,
            chapter=chapter,
            page_number=page,
            tags=tag_list,
            is_favorite=favorite,
            is_private=private,
        )
        note = manager.create_note(data)

        console.print(Panel(
            f"[bold]{book_obj.title}[/bold]\n"
            f"Type: {note.note_type}\n"
            f"{note.short_content}",
            title="[green]Note Added[/green]",
        ))
    except ValueError as e:
        print_error(str(e))


@notes_app.command("list")
def notes_list(
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Filter by book"),
    note_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    favorites: bool = typer.Option(False, "--favorites", "-f", help="Only favorites"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """List notes."""
    from .notes import NotesManager, NoteType
    from .library import BookTracker

    db = get_db()
    manager = NotesManager(db)

    book_id = None
    if book:
        tracker = BookTracker(db)
        book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
        if isinstance(book_obj, list):
            book_obj = book_obj[0] if book_obj else None
        if book_obj:
            book_id = book_obj.id

    note_type_enum = None
    if note_type:
        try:
            note_type_enum = NoteType(note_type)
        except ValueError:
            print_error(f"Invalid note type: {note_type}")
            return

    notes = manager.list_notes(
        book_id=book_id,
        note_type=note_type_enum,
        favorites_only=favorites,
        tag=tag,
    )[:limit]

    if not notes:
        print_info("No notes found")
        return

    summaries = manager._notes_to_summaries(notes)

    table = Table(title="Notes")
    table.add_column("Book", style="cyan")
    table.add_column("Type")
    table.add_column("Content")
    table.add_column("Loc")
    table.add_column("Fav", justify="center")

    for summary in summaries:
        table.add_row(
            summary.book_title[:25],
            summary.note_type.value,
            summary.short_content[:40],
            summary.location_display,
            "★" if summary.is_favorite else "",
        )

    console.print(table)


@notes_app.command("show")
def notes_show(
    note_id: str = typer.Argument(..., help="Note ID"),
) -> None:
    """Show a note."""
    from .notes import NotesManager
    from .library import BookTracker

    db = get_db()
    manager = NotesManager(db)

    note = manager.get_note(note_id)
    if not note:
        print_error("Note not found")
        return

    tracker = BookTracker(db)
    book = tracker.get_book(note.book_id)

    content_parts = [
        f"[bold]{book.title if book else 'Unknown'}[/bold]",
        f"\nType: {note.note_type}",
    ]

    if note.location_display:
        content_parts.append(f"\nLocation: {note.location_display}")

    if note.title:
        content_parts.append(f"\n\n[italic]{note.title}[/italic]")

    content_parts.append(f"\n\n{note.content}")

    if note.tag_list:
        content_parts.append(f"\n\nTags: {', '.join(note.tag_list)}")

    flags = []
    if note.is_favorite:
        flags.append("★ Favorite")
    if note.is_private:
        flags.append("🔒 Private")
    if flags:
        content_parts.append(f"\n\n{' | '.join(flags)}")

    console.print(Panel("".join(content_parts), title="[blue]Note[/blue]"))


@notes_app.command("delete")
def notes_delete(
    note_id: str = typer.Argument(..., help="Note ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a note."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    note = manager.get_note(note_id)
    if not note:
        print_error("Note not found")
        return

    if not force:
        if not typer.confirm("Delete this note?"):
            print_info("Cancelled")
            return

    if manager.delete_note(note_id):
        print_success("Note deleted")
    else:
        print_error("Failed to delete note")


@notes_app.command("search")
def notes_search(
    query: str = typer.Argument(..., help="Search query"),
) -> None:
    """Search notes."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    results = manager.search_notes(query)

    if not results:
        print_info(f"No notes found matching '{query}'")
        return

    table = Table(title=f"Notes matching '{query}'")
    table.add_column("Book", style="cyan")
    table.add_column("Type")
    table.add_column("Content")

    for note in results:
        table.add_row(
            note.book_title[:25],
            note.note_type.value,
            note.short_content[:50],
        )

    console.print(table)


@notes_app.command("book")
def notes_book(
    book: str = typer.Argument(..., help="Book title or ID"),
) -> None:
    """Show all notes for a book."""
    from .notes import NotesManager
    from .library import BookTracker

    db = get_db()
    tracker = BookTracker(db)
    manager = NotesManager(db)

    book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
    if isinstance(book_obj, list):
        book_obj = book_obj[0] if book_obj else None

    if not book_obj:
        print_error(f"Book not found: {book}")
        return

    annotations = manager.get_book_annotations(book_obj.id)
    if not annotations:
        print_info("No annotations found")
        return

    console.print(f"\n[bold]{annotations.book_title}[/bold] by {annotations.book_author}")
    console.print(f"Notes: {annotations.total_notes} | Quotes: {annotations.total_quotes}\n")

    if annotations.notes:
        table = Table(title="Notes")
        table.add_column("Type")
        table.add_column("Content")
        table.add_column("Location")

        for note in annotations.notes:
            table.add_row(
                note.note_type.value,
                note.short_content[:50],
                note.location_display,
            )
        console.print(table)

    if annotations.quotes:
        console.print()
        table = Table(title="Quotes")
        table.add_column("Quote")
        table.add_column("Speaker")
        table.add_column("Location")

        for quote in annotations.quotes:
            table.add_row(
                quote.short_text[:50],
                quote.speaker or "",
                quote.location_display,
            )
        console.print(table)


@notes_app.command("stats")
def notes_stats() -> None:
    """Show notes statistics."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    stats = manager.get_stats()

    content = f"""[bold]Overview[/bold]
Total Notes: {stats.total_notes}
Total Quotes: {stats.total_quotes}
Books with Notes: {stats.books_with_notes}
Books with Quotes: {stats.books_with_quotes}

[bold]Favorites[/bold]
Favorite Notes: {stats.favorite_notes}
Favorite Quotes: {stats.favorite_quotes}"""

    if stats.notes_by_type:
        content += "\n\n[bold]Notes by Type[/bold]"
        for note_type, count in stats.notes_by_type.items():
            content += f"\n  {note_type}: {count}"

    if stats.most_used_tags:
        content += "\n\n[bold]Top Tags[/bold]"
        for tag, count in stats.most_used_tags[:5]:
            content += f"\n  {tag}: {count}"

    console.print(Panel(content, title="[blue]Notes Statistics[/blue]"))


# ============================================================================
# Quotes Commands
# ============================================================================

quotes_app = typer.Typer(help="Manage book quotes and passages.")
app.add_typer(quotes_app, name="quotes")


@quotes_app.command("add")
def quotes_add(
    book: str = typer.Argument(..., help="Book title or ID"),
    text: str = typer.Argument(..., help="Quote text"),
    speaker: Optional[str] = typer.Option(None, "--speaker", "-s", help="Speaker/character"),
    context: Optional[str] = typer.Option(None, "--context", "-c", help="Context or note"),
    chapter: Optional[str] = typer.Option(None, "--chapter", help="Chapter"),
    page: Optional[int] = typer.Option(None, "--page", "-p", help="Page number"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
    favorite: bool = typer.Option(False, "--favorite", "-f", help="Mark as favorite"),
    quote_type: str = typer.Option("quote", "--type", "-t", help="Type: quote, highlight, excerpt, paraphrase"),
    color: Optional[str] = typer.Option(None, "--color", help="Highlight color: yellow, green, blue, pink, purple, orange"),
) -> None:
    """Add a quote from a book."""
    from uuid import UUID
    from .notes import NotesManager, QuoteCreate, QuoteType, HighlightColor
    from .library import BookTracker

    db = get_db()
    tracker = BookTracker(db)
    manager = NotesManager(db)

    # Find book
    book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
    if isinstance(book_obj, list):
        book_obj = book_obj[0] if book_obj else None

    if not book_obj:
        print_error(f"Book not found: {book}")
        return

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    # Parse quote type
    try:
        qtype = QuoteType(quote_type)
    except ValueError:
        print_error(f"Invalid quote type: {quote_type}. Use: quote, highlight, excerpt, paraphrase")
        return

    # Parse color
    qcolor = None
    if color:
        try:
            qcolor = HighlightColor(color)
        except ValueError:
            print_error(f"Invalid color: {color}. Use: yellow, green, blue, pink, purple, orange")
            return

    try:
        data = QuoteCreate(
            book_id=UUID(book_obj.id),
            text=text,
            quote_type=qtype,
            color=qcolor,
            speaker=speaker,
            context=context,
            chapter=chapter,
            page_number=page,
            tags=tag_list,
            is_favorite=favorite,
        )
        quote = manager.create_quote(data)

        console.print(Panel(
            f"[italic]\"{quote.short_text}\"[/italic]\n"
            f"{quote.attribution}\n"
            f"— [bold]{book_obj.title}[/bold]",
            title="[green]Quote Added[/green]",
        ))
    except ValueError as e:
        print_error(str(e))


@quotes_app.command("list")
def quotes_list(
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Filter by book"),
    favorites: bool = typer.Option(False, "--favorites", "-f", help="Only favorites"),
    speaker: Optional[str] = typer.Option(None, "--speaker", "-s", help="Filter by speaker"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """List quotes."""
    from .notes import NotesManager
    from .library import BookTracker

    db = get_db()
    manager = NotesManager(db)

    book_id = None
    if book:
        tracker = BookTracker(db)
        book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
        if isinstance(book_obj, list):
            book_obj = book_obj[0] if book_obj else None
        if book_obj:
            book_id = book_obj.id

    quotes = manager.list_quotes(
        book_id=book_id,
        favorites_only=favorites,
        speaker=speaker,
        tag=tag,
    )[:limit]

    if not quotes:
        print_info("No quotes found")
        return

    summaries = manager._quotes_to_summaries(quotes)

    table = Table(title="Quotes")
    table.add_column("Quote")
    table.add_column("Book", style="cyan")
    table.add_column("Speaker")
    table.add_column("Fav", justify="center")

    for summary in summaries:
        table.add_row(
            summary.short_text[:40],
            summary.book_title[:20],
            summary.speaker or "",
            "★" if summary.is_favorite else "",
        )

    console.print(table)


@quotes_app.command("show")
def quotes_show(
    quote_id: str = typer.Argument(..., help="Quote ID"),
) -> None:
    """Show a quote."""
    from .notes import NotesManager
    from .library import BookTracker

    db = get_db()
    manager = NotesManager(db)

    quote = manager.get_quote(quote_id)
    if not quote:
        print_error("Quote not found")
        return

    tracker = BookTracker(db)
    book = tracker.get_book(quote.book_id)

    content_parts = [
        f"[italic]\"{quote.text}\"[/italic]",
    ]

    if quote.speaker:
        content_parts.append(f"\n\n— {quote.speaker}")

    content_parts.append(f"\n\n[bold]{book.title if book else 'Unknown'}[/bold]")
    content_parts.append(f" by {book.author if book else 'Unknown'}")

    if quote.location_display:
        content_parts.append(f"\n{quote.location_display}")

    if quote.context:
        content_parts.append(f"\n\n[dim]Context: {quote.context}[/dim]")

    if quote.tag_list:
        content_parts.append(f"\n\nTags: {', '.join(quote.tag_list)}")

    if quote.is_favorite:
        content_parts.append("\n\n★ Favorite")

    console.print(Panel("".join(content_parts), title="[blue]Quote[/blue]"))


@quotes_app.command("delete")
def quotes_delete(
    quote_id: str = typer.Argument(..., help="Quote ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a quote."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    quote = manager.get_quote(quote_id)
    if not quote:
        print_error("Quote not found")
        return

    if not force:
        if not typer.confirm("Delete this quote?"):
            print_info("Cancelled")
            return

    if manager.delete_quote(quote_id):
        print_success("Quote deleted")
    else:
        print_error("Failed to delete quote")


@quotes_app.command("search")
def quotes_search(
    query: str = typer.Argument(..., help="Search query"),
) -> None:
    """Search quotes."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    results = manager.search_quotes(query)

    if not results:
        print_info(f"No quotes found matching '{query}'")
        return

    table = Table(title=f"Quotes matching '{query}'")
    table.add_column("Quote")
    table.add_column("Book", style="cyan")
    table.add_column("Speaker")

    for quote in results:
        table.add_row(
            quote.short_text[:40],
            quote.book_title[:20],
            quote.speaker or "",
        )

    console.print(table)


@quotes_app.command("random")
def quotes_random(
    favorites: bool = typer.Option(False, "--favorites", "-f", help="Only from favorites"),
) -> None:
    """Show a random quote."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    quote = manager.get_random_quote(favorites_only=favorites)
    if not quote:
        print_info("No quotes found")
        return

    console.print(Panel(
        f"[italic]\"{quote.short_text}\"[/italic]\n\n"
        f"— [bold]{quote.book_title}[/bold] by {quote.book_author}",
        title="[blue]Random Quote[/blue]",
    ))


@quotes_app.command("favorites")
def quotes_favorites() -> None:
    """List favorite quotes."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    quotes = manager.list_quotes(favorites_only=True)
    if not quotes:
        print_info("No favorite quotes")
        return

    summaries = manager._quotes_to_summaries(quotes)

    table = Table(title="★ Favorite Quotes")
    table.add_column("Quote")
    table.add_column("Book", style="cyan")
    table.add_column("Speaker")

    for summary in summaries:
        table.add_row(
            summary.short_text[:45],
            summary.book_title[:20],
            summary.speaker or "",
        )

    console.print(table)


@quotes_app.command("daily")
def quotes_daily() -> None:
    """Show quote of the day."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    quote = manager.get_quote_of_the_day()
    if not quote:
        print_info("No quotes found")
        return

    console.print(Panel(
        f"[italic]\"{quote.short_text}\"[/italic]\n\n"
        f"— [bold]{quote.book_title}[/bold] by {quote.book_author}",
        title="[blue]Quote of the Day[/blue]",
    ))


@quotes_app.command("stats")
def quotes_stats() -> None:
    """Show quote statistics."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    stats = manager.get_quote_stats()

    content = f"""Total Quotes: {stats.total_quotes}
Highlights: {stats.total_highlights}
Excerpts: {stats.total_excerpts}
Favorites: {stats.favorites_count}
Collections: {stats.collections_count}

Most Quoted Book: {stats.most_quoted_book or 'N/A'}"""

    if stats.quotes_by_type:
        content += "\n\nBy Type:"
        for qtype, count in stats.quotes_by_type.items():
            content += f"\n  {qtype}: {count}"

    if stats.quotes_by_color:
        content += "\n\nBy Color:"
        for color, count in stats.quotes_by_color.items():
            content += f"\n  {color}: {count}"

    if stats.most_used_tags:
        content += "\n\nTop Tags:"
        for tag, count in stats.most_used_tags[:5]:
            content += f"\n  {tag}: {count}"

    console.print(Panel(content, title="[cyan]Quote Statistics[/cyan]"))


@quotes_app.command("export")
def quotes_export(
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Export only quotes from this book"),
    format: str = typer.Option("text", "--format", "-f", help="Format: text or markdown"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Export quotes to text or markdown."""
    from .notes import NotesManager
    from .library import BookTracker

    db = get_db()
    manager = NotesManager(db)
    tracker = BookTracker(db)

    book_id = None
    if book:
        book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
        if isinstance(book_obj, list):
            book_obj = book_obj[0] if book_obj else None
        if book_obj:
            book_id = book_obj.id

    result = manager.export_quotes(book_id=book_id, format=format)

    if output:
        with open(output, "w") as f:
            f.write(result)
        print_success(f"Quotes exported to {output}")
    else:
        console.print(result)


# ============================================================================
# Quote Collection Commands
# ============================================================================

collection_app = typer.Typer(help="Manage quote collections.")
app.add_typer(collection_app, name="collection")


@collection_app.command("create")
def collection_create(
    name: str = typer.Argument(..., help="Collection name"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
    icon: Optional[str] = typer.Option(None, "--icon", help="Icon emoji"),
    public: bool = typer.Option(False, "--public", help="Make collection public"),
) -> None:
    """Create a quote collection."""
    from .notes import NotesManager, CollectionCreate

    db = get_db()
    manager = NotesManager(db)

    data = CollectionCreate(
        name=name,
        description=description,
        icon=icon,
        is_public=public,
    )
    collection = manager.create_collection(data)

    print_success(f"Collection '{collection.name}' created (ID: {collection.id})")


@collection_app.command("list")
def collection_list() -> None:
    """List quote collections."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    collections = manager.list_collections()
    if not collections:
        print_info("No collections found")
        return

    table = Table(title="Quote Collections")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Quotes", justify="right")
    table.add_column("Public")

    for c in collections:
        table.add_row(
            f"{c.icon or ''} {c.name}".strip(),
            (c.description or "")[:30],
            str(c.quote_count),
            "Yes" if c.is_public else "No",
        )

    console.print(table)


@collection_app.command("show")
def collection_show(
    collection_id: str = typer.Argument(..., help="Collection ID or name"),
) -> None:
    """Show a collection with its quotes."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    # Try by ID first, then search by name
    collection = manager.get_collection(collection_id)
    if not collection:
        collections = manager.list_collections()
        for c in collections:
            if c.name.lower() == collection_id.lower():
                collection = manager.get_collection(str(c.id))
                break

    if not collection:
        print_error("Collection not found")
        return

    content = f"[bold]{collection.icon or ''} {collection.name}[/bold]"
    if collection.description:
        content += f"\n{collection.description}"
    content += f"\n\n{len(collection.quotes)} quotes"

    console.print(Panel(content, title="[cyan]Collection[/cyan]"))

    if collection.quotes:
        table = Table()
        table.add_column("Quote")
        table.add_column("Book", style="cyan")

        for quote in collection.quotes:
            table.add_row(
                quote.short_text[:50],
                quote.book_title[:25],
            )

        console.print(table)


@collection_app.command("add")
def collection_add_quote(
    collection_id: str = typer.Argument(..., help="Collection ID"),
    quote_id: str = typer.Argument(..., help="Quote ID to add"),
) -> None:
    """Add a quote to a collection."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    if manager.add_quote_to_collection(collection_id, quote_id):
        print_success("Quote added to collection")
    else:
        print_error("Failed to add quote - collection or quote not found")


@collection_app.command("remove")
def collection_remove_quote(
    collection_id: str = typer.Argument(..., help="Collection ID"),
    quote_id: str = typer.Argument(..., help="Quote ID to remove"),
) -> None:
    """Remove a quote from a collection."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    if manager.remove_quote_from_collection(collection_id, quote_id):
        print_success("Quote removed from collection")
    else:
        print_error("Quote not found in collection")


@collection_app.command("delete")
def collection_delete(
    collection_id: str = typer.Argument(..., help="Collection ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a collection."""
    from .notes import NotesManager

    db = get_db()
    manager = NotesManager(db)

    collection = manager.get_collection(collection_id)
    if not collection:
        print_error("Collection not found")
        return

    if not force:
        if not typer.confirm(f"Delete collection '{collection.name}'?"):
            return

    if manager.delete_collection(collection_id):
        print_success("Collection deleted")
    else:
        print_error("Failed to delete collection")


# ============================================================================
# Streak Commands
# ============================================================================

streak_app = typer.Typer(help="Track reading streaks and habits.")
app.add_typer(streak_app, name="streak")


@streak_app.command("log")
def streak_log(
    minutes: int = typer.Option(0, "--minutes", "-m", help="Minutes read"),
    pages: int = typer.Option(0, "--pages", "-p", help="Pages read"),
    date_str: Optional[str] = typer.Option(None, "--date", "-d", help="Date (YYYY-MM-DD)"),
    hour: Optional[int] = typer.Option(None, "--hour", help="Primary reading hour (0-23)"),
) -> None:
    """Log reading activity."""
    from datetime import date
    from .streaks import StreakManager

    db = get_db()
    manager = StreakManager(db)

    reading_date = None
    if date_str:
        try:
            reading_date = date.fromisoformat(date_str)
        except ValueError:
            print_error("Invalid date format. Use YYYY-MM-DD")
            return

    if minutes == 0 and pages == 0:
        print_error("Specify at least minutes or pages read")
        return

    daily = manager.log_reading(
        reading_date=reading_date,
        minutes=minutes,
        pages=pages,
        primary_hour=hour,
    )

    # Check streak status
    status = manager.get_streak_status()
    current = manager.get_current_streak()

    content = f"Logged: {daily.minutes_read} min, {daily.pages_read} pages"
    if current:
        content += f"\n\nCurrent Streak: {current.length} days"
        if status.value == "active":
            content += " (Active)"
        elif status.value == "at_risk":
            content += " (Keep it going!)"

    console.print(Panel(content, title="[green]Reading Logged[/green]"))


@streak_app.command("status")
def streak_status() -> None:
    """Show current streak status."""
    from .streaks import StreakManager

    db = get_db()
    manager = StreakManager(db)

    current = manager.get_current_streak()
    status = manager.get_streak_status()
    longest = manager.get_longest_streak()

    if not current and not longest:
        print_info("No reading activity yet. Start your streak!")
        return

    content_parts = []

    # Current streak
    if current:
        status_emoji = {
            "active": "[green]Active[/green]",
            "at_risk": "[yellow]At Risk[/yellow]",
            "ended": "[red]Ended[/red]",
        }.get(status.value, status.value)

        content_parts.append(f"[bold]Current Streak:[/bold] {current.length} days {status_emoji}")
        content_parts.append(f"Started: {current.start_date}")
        content_parts.append(f"Total: {current.total_minutes} min, {current.total_pages} pages")
    else:
        content_parts.append("[bold]Current Streak:[/bold] 0 days")
        content_parts.append("[dim]Start reading today to begin a new streak![/dim]")

    # Longest streak
    if longest:
        content_parts.append(f"\n[bold]Longest Streak:[/bold] {longest.length} days")
        content_parts.append(f"Period: {longest.start_date} to {longest.end_date or 'ongoing'}")

    console.print(Panel("\n".join(content_parts), title="[blue]Streak Status[/blue]"))


@streak_app.command("history")
def streak_history(
    limit: int = typer.Option(14, "--limit", "-n", help="Days to show"),
) -> None:
    """Show reading history."""
    from .streaks import StreakManager

    db = get_db()
    manager = StreakManager(db)

    readings = manager.get_reading_history(limit=limit)

    if not readings:
        print_info("No reading history")
        return

    table = Table(title=f"Reading History (Last {limit} days)")
    table.add_column("Date")
    table.add_column("Minutes", justify="right")
    table.add_column("Pages", justify="right")
    table.add_column("Goal", justify="center")

    for reading in readings:
        goal_status = ""
        if reading.goal_met:
            goal_status = "[green]Met[/green]"
        elif reading.goal_minutes or reading.goal_pages:
            progress = reading.goal_progress
            if progress:
                goal_status = f"{int(progress * 100)}%"

        table.add_row(
            reading.reading_date,
            str(reading.minutes_read),
            str(reading.pages_read),
            goal_status,
        )

    console.print(table)


@streak_app.command("stats")
def streak_stats() -> None:
    """Show streak statistics."""
    from .streaks import StreakManager

    db = get_db()
    manager = StreakManager(db)

    stats = manager.get_stats()

    status_display = {
        "active": "[green]Active[/green]",
        "at_risk": "[yellow]At Risk[/yellow]",
        "ended": "[red]No Active Streak[/red]",
    }.get(stats.streak_status.value, stats.streak_status.value)

    content = f"""[bold]Streak Status:[/bold] {status_display}

[bold]Current Streak[/bold]
Length: {stats.current_streak} days
Minutes: {stats.current_streak_minutes}
Pages: {stats.current_streak_pages}
Books Completed: {stats.current_streak_books}

[bold]Records[/bold]
Longest Streak: {stats.longest_streak} days
Total Streaks: {stats.total_streaks}
Total Reading Days: {stats.total_reading_days}

[bold]Averages[/bold]
Avg Streak Length: {stats.average_streak_length} days
Avg Daily Minutes: {stats.average_daily_minutes}
Avg Daily Pages: {stats.average_daily_pages}

[bold]Best Day[/bold]
Date: {stats.best_day_date or 'N/A'}
Minutes: {stats.best_day_minutes}
Pages: {stats.best_day_pages}"""

    console.print(Panel(content, title="[blue]Streak Statistics[/blue]"))


@streak_app.command("habits")
def streak_habits() -> None:
    """Analyze reading habits."""
    from .streaks import StreakManager

    db = get_db()
    manager = StreakManager(db)

    habits = manager.get_reading_habits()

    content_parts = [
        f"[bold]Consistency Score:[/bold] {habits.consistency_score}%",
        f"Reading days this week: {habits.reading_days_this_week}/7",
        f"Reading days this month: {habits.reading_days_this_month}/30",
    ]

    if habits.most_productive_weekday:
        content_parts.append(f"\n[bold]Best Day:[/bold] {habits.most_productive_weekday}")
    if habits.most_productive_hour is not None:
        hour_display = f"{habits.most_productive_hour}:00"
        content_parts.append(f"[bold]Best Hour:[/bold] {hour_display}")

    content_parts.append(f"\n[bold]Trends[/bold]")
    content_parts.append(f"Minutes: {habits.minutes_trend}")
    content_parts.append(f"Pages: {habits.pages_trend}")

    console.print(Panel("\n".join(content_parts), title="[blue]Reading Habits[/blue]"))

    # Weekday breakdown
    if habits.weekday_stats:
        table = Table(title="Weekday Breakdown")
        table.add_column("Day")
        table.add_column("Avg Min", justify="right")
        table.add_column("Avg Pages", justify="right")
        table.add_column("Frequency", justify="right")

        for ws in habits.weekday_stats:
            table.add_row(
                ws.weekday_name[:3],
                str(int(ws.average_minutes)),
                str(int(ws.average_pages)),
                f"{ws.reading_frequency:.0f}%",
            )

        console.print(table)


@streak_app.command("milestones")
def streak_milestones() -> None:
    """Show milestone achievements."""
    from .streaks import StreakManager

    db = get_db()
    manager = StreakManager(db)

    milestones = manager.get_milestones()

    table = Table(title="Streak Milestones")
    table.add_column("Status", justify="center")
    table.add_column("Milestone")
    table.add_column("Days", justify="right")
    table.add_column("Achieved")

    for m in milestones:
        status = "[green]Achieved[/green]" if m.achieved else "[dim]Locked[/dim]"
        achieved_str = str(m.achieved_date) if m.achieved_date else "-"

        table.add_row(
            status,
            f"{m.name}\n[dim]{m.description}[/dim]",
            str(m.days_required),
            achieved_str,
        )

    console.print(table)


@streak_app.command("calendar")
def streak_calendar(
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year"),
    month: Optional[int] = typer.Option(None, "--month", "-m", help="Month (1-12)"),
) -> None:
    """Show reading calendar."""
    from datetime import date
    from calendar import month_name
    from .streaks import StreakManager

    db = get_db()
    manager = StreakManager(db)

    today = date.today()
    year = year or today.year
    month = month or today.month

    cal = manager.get_calendar(year, month)

    console.print(f"\n[bold]{month_name[month]} {year}[/bold]")
    console.print(f"Reading days: {cal.total_reading_days} | "
                  f"Minutes: {cal.total_minutes} | Pages: {cal.total_pages}\n")

    # Simple calendar display
    console.print("Mon Tue Wed Thu Fri Sat Sun")

    # Find first day of month
    first_day = date(year, month, 1)
    start_weekday = first_day.weekday()

    # Print leading spaces
    line = "    " * start_weekday

    from calendar import monthrange
    _, days_in_month = monthrange(year, month)

    for day in range(1, days_in_month + 1):
        if cal.days.get(day, False):
            # Reading day
            streak_len = cal.streak_days.get(day, 0)
            if streak_len >= 7:
                line += f"[green]{day:3}[/green] "
            else:
                line += f"[cyan]{day:3}[/cyan] "
        else:
            line += f"[dim]{day:3}[/dim] "

        # Check if end of week
        current_date = date(year, month, day)
        if current_date.weekday() == 6:
            console.print(line)
            line = ""

    if line:
        console.print(line)

    console.print("\n[cyan]Cyan[/cyan] = Reading day | [green]Green[/green] = 7+ day streak")


@streak_app.command("goal")
def streak_goal(
    minutes: Optional[int] = typer.Option(None, "--minutes", "-m", help="Daily minutes goal"),
    pages: Optional[int] = typer.Option(None, "--pages", "-p", help="Daily pages goal"),
) -> None:
    """Set daily reading goal."""
    from .streaks import StreakManager

    db = get_db()
    manager = StreakManager(db)

    if minutes is None and pages is None:
        # Show current goal
        daily = manager.get_daily_reading(date.today())
        if daily and (daily.goal_minutes or daily.goal_pages):
            console.print(f"Today's goal: {daily.goal_minutes or 0} min / {daily.goal_pages or 0} pages")
            if daily.goal_met:
                console.print("[green]Goal met![/green]")
            else:
                progress = daily.goal_progress
                if progress:
                    console.print(f"Progress: {int(progress * 100)}%")
        else:
            print_info("No goal set for today. Use --minutes or --pages to set one.")
        return

    from datetime import date as date_type
    daily = manager.set_daily_goal(
        goal_minutes=minutes,
        goal_pages=pages,
        reading_date=date_type.today(),
    )

    console.print(f"[green]Goal set:[/green] {minutes or 0} minutes / {pages or 0} pages")
    if daily.goal_met:
        console.print("[green]Already achieved![/green]")


@streak_app.command("top")
def streak_top(
    limit: int = typer.Option(5, "--limit", "-n", help="Number of streaks"),
) -> None:
    """Show top streaks."""
    from .streaks import StreakManager

    db = get_db()
    manager = StreakManager(db)

    streaks = manager.get_all_streaks(limit=limit)

    if not streaks:
        print_info("No streaks recorded yet")
        return

    table = Table(title="Top Streaks")
    table.add_column("#", justify="right")
    table.add_column("Length", justify="right")
    table.add_column("Period")
    table.add_column("Minutes", justify="right")
    table.add_column("Pages", justify="right")
    table.add_column("Status")

    for i, streak in enumerate(streaks, 1):
        status = "[green]Current[/green]" if streak.is_current else "[dim]Ended[/dim]"
        period = f"{streak.start_date}"
        if streak.end_date:
            period += f" to {streak.end_date}"
        else:
            period += " to now"

        table.add_row(
            str(i),
            f"{streak.length} days",
            period,
            str(streak.total_minutes),
            str(streak.total_pages),
            status,
        )

    console.print(table)


# ============================================================================
# Wishlist Commands
# ============================================================================

wishlist_app = typer.Typer(help="Manage your TBR (To Be Read) wishlist.")
app.add_typer(wishlist_app, name="wishlist")


@wishlist_app.command("add")
def wishlist_add(
    title: str = typer.Argument(..., help="Book title"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Author name"),
    priority: int = typer.Option(3, "--priority", "-p", help="Priority 1-5 (1=must read)"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Recommendation source"),
    recommended_by: Optional[str] = typer.Option(None, "--from", help="Who recommended it"),
    reason: Optional[str] = typer.Option(None, "--reason", "-r", help="Why you want to read it"),
    genre: Optional[str] = typer.Option(None, "--genre", "-g", help="Genre"),
    pages: Optional[int] = typer.Option(None, "--pages", help="Estimated pages"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
) -> None:
    """Add a book to your wishlist."""
    from .wishlist import WishlistManager, WishlistItemCreate, Priority, WishlistSource

    db = get_db()
    manager = WishlistManager(db)

    # Parse priority
    try:
        priority_enum = Priority(priority)
    except ValueError:
        print_error("Priority must be 1-5")
        return

    # Parse source
    source_enum = None
    if source:
        try:
            source_enum = WishlistSource(source.lower())
        except ValueError:
            # Show valid sources
            valid = ", ".join([s.value for s in WishlistSource])
            print_error(f"Invalid source. Valid sources: {valid}")
            return

    # Parse tags
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    item = WishlistItemCreate(
        title=title,
        author=author,
        priority=priority_enum,
        source=source_enum,
        recommended_by=recommended_by,
        reason=reason,
        genre=genre,
        estimated_pages=pages,
        tags=tag_list,
    )

    result = manager.add_item(item)
    console.print(Panel(
        f"[bold]{result.title}[/bold]\n"
        f"Author: {result.author or 'Unknown'}\n"
        f"Priority: {result.priority_display}\n"
        f"Position: #{result.position + 1}",
        title="[green]Added to Wishlist[/green]"
    ))


@wishlist_app.command("list")
def wishlist_list(
    priority: Optional[int] = typer.Option(None, "--priority", "-p", help="Filter by priority"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Filter by source"),
    available: Optional[bool] = typer.Option(None, "--available", help="Filter by availability"),
    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search title/author"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by tag"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max items to show"),
) -> None:
    """List wishlist items."""
    from .wishlist import WishlistManager, Priority, WishlistSource

    db = get_db()
    manager = WishlistManager(db)

    # Parse filters
    priority_enum = None
    if priority is not None:
        try:
            priority_enum = Priority(priority)
        except ValueError:
            print_error("Priority must be 1-5")
            return

    source_enum = None
    if source:
        try:
            source_enum = WishlistSource(source.lower())
        except ValueError:
            pass  # Ignore invalid source

    items = manager.list_items(
        priority=priority_enum,
        source=source_enum,
        is_available=available,
        search=search,
        tag=tag,
        limit=limit,
    )

    if not items:
        print_info("No items in wishlist")
        return

    table = Table(title=f"Wishlist ({len(items)} items)")
    table.add_column("#", justify="right")
    table.add_column("Title")
    table.add_column("Author")
    table.add_column("Priority")
    table.add_column("Source")
    table.add_column("Status")

    for i, item in enumerate(items, 1):
        status_parts = []
        if item.is_available:
            status_parts.append("[green]Available[/green]")
        if item.is_in_library:
            status_parts.append("[blue]In Library[/blue]")
        status = " ".join(status_parts) or "[dim]-[/dim]"

        table.add_row(
            str(i),
            item.title[:40] + "..." if len(item.title) > 40 else item.title,
            item.author or "[dim]Unknown[/dim]",
            item.priority_display,
            item.source.value if item.source else "[dim]-[/dim]",
            status,
        )

    console.print(table)


@wishlist_app.command("show")
def wishlist_show(
    item_id: str = typer.Argument(..., help="Item ID or search term"),
) -> None:
    """Show details of a wishlist item."""
    from uuid import UUID
    from .wishlist import WishlistManager

    db = get_db()
    manager = WishlistManager(db)

    # Try as UUID first
    try:
        uuid = UUID(item_id)
        item = manager.get_item(uuid)
    except ValueError:
        # Search by title
        items = manager.list_items(search=item_id, limit=1)
        item = manager.get_item(items[0].id) if items else None

    if not item:
        print_error("Item not found")
        return

    content = f"""[bold]{item.title}[/bold]
Author: {item.author or 'Unknown'}
Priority: {item.priority_display} (#{item.position + 1})

Source: {item.source.value if item.source else 'N/A'}
Recommended by: {item.recommended_by or 'N/A'}
Genre: {item.genre or 'N/A'}

Estimated: {item.estimated_pages or '?'} pages / {item.estimated_hours or '?'} hours
Target date: {item.target_date or 'Not set'}
Date added: {item.date_added}

Status:
  Available: {'Yes' if item.is_available else 'No'}
  On Hold: {'Yes' if item.is_on_hold else 'No'}
  In Library: {'Yes' if item.is_in_library else 'No'}

Tags: {', '.join(item.tags) if item.tags else 'None'}

Reason: {item.reason or 'Not specified'}
Notes: {item.notes or 'None'}"""

    console.print(Panel(content, title="[blue]Wishlist Item[/blue]"))
    console.print(f"\n[dim]ID: {item.id}[/dim]")


@wishlist_app.command("priority")
def wishlist_priority(
    item_id: str = typer.Argument(..., help="Item ID or search term"),
    priority: int = typer.Argument(..., help="New priority (1-5)"),
) -> None:
    """Change an item's priority."""
    from uuid import UUID
    from .wishlist import WishlistManager, Priority

    db = get_db()
    manager = WishlistManager(db)

    # Parse priority
    try:
        priority_enum = Priority(priority)
    except ValueError:
        print_error("Priority must be 1-5")
        return

    # Find item
    try:
        uuid = UUID(item_id)
    except ValueError:
        items = manager.list_items(search=item_id, limit=1)
        if not items:
            print_error("Item not found")
            return
        uuid = items[0].id

    result = manager.change_priority(uuid, priority_enum)
    if result:
        console.print(f"[green]Priority changed to {result.priority_display}[/green]")
    else:
        print_error("Item not found")


@wishlist_app.command("available")
def wishlist_available(
    item_id: str = typer.Argument(..., help="Item ID or search term"),
    available: bool = typer.Option(True, "--yes/--no", help="Mark as available"),
) -> None:
    """Mark an item as available (owned/accessible)."""
    from uuid import UUID
    from .wishlist import WishlistManager

    db = get_db()
    manager = WishlistManager(db)

    # Find item
    try:
        uuid = UUID(item_id)
    except ValueError:
        items = manager.list_items(search=item_id, limit=1)
        if not items:
            print_error("Item not found")
            return
        uuid = items[0].id

    result = manager.mark_available(uuid, available)
    if result:
        status = "available" if available else "not available"
        console.print(f"[green]Marked '{result.title}' as {status}[/green]")
    else:
        print_error("Item not found")


@wishlist_app.command("hold")
def wishlist_hold(
    item_id: str = typer.Argument(..., help="Item ID or search term"),
    on_hold: bool = typer.Option(True, "--yes/--no", help="Mark as on hold"),
) -> None:
    """Mark an item as on hold at library."""
    from uuid import UUID
    from .wishlist import WishlistManager

    db = get_db()
    manager = WishlistManager(db)

    # Find item
    try:
        uuid = UUID(item_id)
    except ValueError:
        items = manager.list_items(search=item_id, limit=1)
        if not items:
            print_error("Item not found")
            return
        uuid = items[0].id

    result = manager.mark_on_hold(uuid, on_hold)
    if result:
        status = "on hold" if on_hold else "not on hold"
        console.print(f"[green]Marked '{result.title}' as {status}[/green]")
    else:
        print_error("Item not found")


@wishlist_app.command("remove")
def wishlist_remove(
    item_id: str = typer.Argument(..., help="Item ID or search term"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove an item from wishlist."""
    from uuid import UUID
    from .wishlist import WishlistManager

    db = get_db()
    manager = WishlistManager(db)

    # Find item
    try:
        uuid = UUID(item_id)
        item = manager.get_item(uuid)
    except ValueError:
        items = manager.list_items(search=item_id, limit=1)
        if not items:
            print_error("Item not found")
            return
        uuid = items[0].id
        item = manager.get_item(uuid)

    if not item:
        print_error("Item not found")
        return

    if not confirm:
        console.print(f"Remove '[bold]{item.title}[/bold]' from wishlist?")
        if not typer.confirm("Confirm?"):
            print_info("Cancelled")
            return

    if manager.delete_item(uuid):
        console.print(f"[green]Removed '{item.title}' from wishlist[/green]")
    else:
        print_error("Failed to remove item")


@wishlist_app.command("stats")
def wishlist_stats() -> None:
    """Show wishlist statistics."""
    from .wishlist import WishlistManager

    db = get_db()
    manager = WishlistManager(db)

    stats = manager.get_stats()

    if stats.total_items == 0:
        print_info("Your wishlist is empty")
        return

    # Priority breakdown
    priority_lines = []
    for priority, count in stats.by_priority.items():
        priority_lines.append(f"  {priority}: {count}")

    # Source breakdown
    source_lines = []
    for source, count in stats.by_source.items():
        source_lines.append(f"  {source}: {count}")

    content = f"""[bold]Total Items:[/bold] {stats.total_items}

[bold]By Priority:[/bold]
{chr(10).join(priority_lines) if priority_lines else '  None'}

[bold]By Source:[/bold]
{chr(10).join(source_lines) if source_lines else '  None'}

[bold]Status:[/bold]
  Available: {stats.available_count}
  On Hold: {stats.on_hold_count}
  In Library: {stats.in_library_count}

[bold]Estimates:[/bold]
  Total Pages: {stats.total_estimated_pages:,}
  Total Hours: {stats.total_estimated_hours:.1f}

[bold]Dates:[/bold]
  Oldest Item: {stats.oldest_item_date or 'N/A'}
  With Target Date: {stats.items_with_target_date}
  Overdue Targets: {stats.overdue_targets}"""

    console.print(Panel(content, title="[blue]Wishlist Statistics[/blue]"))


@wishlist_app.command("next")
def wishlist_next(
    count: int = typer.Option(5, "--count", "-n", help="Number of recommendations"),
) -> None:
    """Get recommendations for what to read next."""
    from .wishlist import WishlistManager

    db = get_db()
    manager = WishlistManager(db)

    recommendations = manager.get_next_up(count=count)

    if not recommendations:
        print_info("No recommendations available. Add some books to your wishlist!")
        return

    table = Table(title="What to Read Next")
    table.add_column("#", justify="right")
    table.add_column("Book")
    table.add_column("Author")
    table.add_column("Priority")
    table.add_column("Reason")

    for i, rec in enumerate(recommendations, 1):
        table.add_row(
            str(i),
            rec.item.title[:35] + "..." if len(rec.item.title) > 35 else rec.item.title,
            rec.item.author or "[dim]Unknown[/dim]",
            rec.item.priority_display,
            rec.reason,
        )

    console.print(table)


@wishlist_app.command("by-priority")
def wishlist_by_priority() -> None:
    """Show wishlist grouped by priority."""
    from .wishlist import WishlistManager

    db = get_db()
    manager = WishlistManager(db)

    groups = manager.get_by_priority()

    if not groups:
        print_info("Your wishlist is empty")
        return

    for group in groups:
        table = Table(title=f"{group.priority_display} Priority ({group.count} items)")
        table.add_column("#", justify="right")
        table.add_column("Title")
        table.add_column("Author")
        table.add_column("Added")
        table.add_column("Status")

        for i, item in enumerate(group.items, 1):
            status = ""
            if item.is_available:
                status = "[green]Available[/green]"
            elif item.is_in_library:
                status = "[blue]In Library[/blue]"

            table.add_row(
                str(i),
                item.title[:40] + "..." if len(item.title) > 40 else item.title,
                item.author or "[dim]Unknown[/dim]",
                str(item.date_added),
                status or "[dim]-[/dim]",
            )

        console.print(table)
        console.print()


# ============================================================================
# Series Commands
# ============================================================================

series_app = typer.Typer(help="Manage book series and reading order.")
app.add_typer(series_app, name="series")


@series_app.command("create")
def series_create(
    name: str = typer.Argument(..., help="Series name"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Author name"),
    total_books: Optional[int] = typer.Option(None, "--total", "-t", help="Total books in series"),
    complete: bool = typer.Option(False, "--complete", "-c", help="Series is complete (finished by author)"),
    genre: Optional[str] = typer.Option(None, "--genre", "-g", help="Genre"),
) -> None:
    """Create a new book series."""
    from .series import SeriesManager, SeriesCreate

    db = get_db()
    manager = SeriesManager(db)

    series = SeriesCreate(
        name=name,
        author=author,
        total_books=total_books,
        is_complete=complete,
        genre=genre,
    )

    result = manager.create_series(series)
    console.print(Panel(
        f"[bold]{result.name}[/bold]\n"
        f"Author: {result.author or 'Unknown'}\n"
        f"Total Books: {result.total_books or 'Unknown'}\n"
        f"Complete: {'Yes' if result.is_complete else 'No'}",
        title="[green]Series Created[/green]"
    ))
    console.print(f"\n[dim]ID: {result.id}[/dim]")


@series_app.command("list")
def series_list(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Filter by author"),
    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search by name"),
    complete: Optional[bool] = typer.Option(None, "--complete", help="Filter by completion"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max items to show"),
) -> None:
    """List all series."""
    from .series import SeriesManager, SeriesStatus

    db = get_db()
    manager = SeriesManager(db)

    # Parse status
    status_enum = None
    if status:
        try:
            status_enum = SeriesStatus(status.lower())
        except ValueError:
            valid = ", ".join([s.value for s in SeriesStatus])
            print_error(f"Invalid status. Valid: {valid}")
            return

    series_list = manager.list_series(
        status=status_enum,
        author=author,
        search=search,
        is_complete=complete,
        limit=limit,
    )

    if not series_list:
        print_info("No series found")
        return

    table = Table(title=f"Series ({len(series_list)} found)")
    table.add_column("Name")
    table.add_column("Author")
    table.add_column("Progress")
    table.add_column("Status")
    table.add_column("Complete")

    for series in series_list:
        progress = f"{series.books_read}"
        if series.total_books:
            progress += f"/{series.total_books}"
        progress += f" ({series.completion_percentage:.0f}%)"

        table.add_row(
            series.name[:35] + "..." if len(series.name) > 35 else series.name,
            series.author or "[dim]Unknown[/dim]",
            progress,
            series.status_display,
            "[green]Yes[/green]" if series.is_complete else "[dim]No[/dim]",
        )

    console.print(table)


@series_app.command("show")
def series_show(
    series_id: str = typer.Argument(..., help="Series ID or search term"),
) -> None:
    """Show details of a series with all its books."""
    from uuid import UUID
    from .series import SeriesManager

    db = get_db()
    manager = SeriesManager(db)

    # Try as UUID first
    try:
        uuid = UUID(series_id)
        result = manager.get_series_with_books(uuid)
    except ValueError:
        # Search by name
        series_list = manager.list_series(search=series_id, limit=1)
        if not series_list:
            print_error("Series not found")
            return
        result = manager.get_series_with_books(series_list[0].id)

    if not result:
        print_error("Series not found")
        return

    series = result.series
    content = f"""[bold]{series.name}[/bold]
Author: {series.author or 'Unknown'}
Genre: {series.genre or 'N/A'}

Status: {series.status_display}
Complete: {'Yes (author finished series)' if series.is_complete else 'No / Ongoing'}

Progress: {series.books_read} read / {series.total_books or '?'} total ({series.completion_percentage:.0f}%)
Books Owned: {series.books_owned}
Books Remaining: {series.books_remaining or 'Unknown'}

Average Rating: {f'{series.average_rating:.1f}/5' if series.average_rating else 'N/A'}

Notes: {series.notes or 'None'}"""

    console.print(Panel(content, title="[blue]Series Details[/blue]"))

    # Show books table
    if result.books:
        table = Table(title="Books in Series")
        table.add_column("#", justify="right")
        table.add_column("Title")
        table.add_column("Status")
        table.add_column("Rating")
        table.add_column("Owned")

        for book in result.books:
            position = book.position_display
            if book.is_optional:
                position += " [dim](optional)[/dim]"

            read_status = "[green]Read[/green]" if book.is_read else "[dim]Unread[/dim]"
            owned = "[green]Yes[/green]" if book.is_owned else "[dim]No[/dim]"
            rating = f"{book.book_rating}/5" if book.book_rating else "[dim]-[/dim]"

            table.add_row(
                position,
                book.book_title or f"[dim]Book ID: {book.book_id}[/dim]",
                read_status,
                rating,
                owned,
            )

        console.print(table)

        if result.next_to_read:
            console.print(f"\n[yellow]Next to read:[/yellow] {result.next_to_read.book_title or 'Unknown'} ({result.next_to_read.position_display})")

    console.print(f"\n[dim]ID: {series.id}[/dim]")


@series_app.command("add-book")
def series_add_book(
    series_id: str = typer.Argument(..., help="Series ID or name"),
    book_id: str = typer.Argument(..., help="Book ID to add"),
    position: float = typer.Argument(..., help="Position in series (e.g., 1, 2, 1.5)"),
    label: Optional[str] = typer.Option(None, "--label", "-l", help="Position label (e.g., 'Prequel')"),
    optional: bool = typer.Option(False, "--optional", help="Mark as optional/skippable"),
    read: bool = typer.Option(False, "--read", "-r", help="Mark as already read"),
    owned: bool = typer.Option(False, "--owned", "-o", help="Mark as owned"),
) -> None:
    """Add a book to a series."""
    from uuid import UUID
    from .series import SeriesManager, SeriesBookCreate

    db = get_db()
    manager = SeriesManager(db)

    # Find series
    try:
        series_uuid = UUID(series_id)
    except ValueError:
        series_list = manager.list_series(search=series_id, limit=1)
        if not series_list:
            print_error("Series not found")
            return
        series_uuid = series_list[0].id

    # Validate book ID
    try:
        book_uuid = UUID(book_id)
    except ValueError:
        print_error("Invalid book ID format")
        return

    entry = SeriesBookCreate(
        book_id=book_uuid,
        position=position,
        position_label=label,
        is_optional=optional,
        is_read=read,
        is_owned=owned,
    )

    result = manager.add_book_to_series(series_uuid, entry)
    if result:
        console.print(f"[green]Added book at position {result.position_display}[/green]")
    else:
        print_error("Failed to add book - series not found")


@series_app.command("mark-read")
def series_mark_read(
    series_id: str = typer.Argument(..., help="Series ID or name"),
    book_id: str = typer.Argument(..., help="Book ID"),
    unread: bool = typer.Option(False, "--unread", help="Mark as unread instead"),
) -> None:
    """Mark a book in a series as read."""
    from uuid import UUID
    from .series import SeriesManager

    db = get_db()
    manager = SeriesManager(db)

    # Find series
    try:
        series_uuid = UUID(series_id)
    except ValueError:
        series_list = manager.list_series(search=series_id, limit=1)
        if not series_list:
            print_error("Series not found")
            return
        series_uuid = series_list[0].id

    # Validate book ID
    try:
        book_uuid = UUID(book_id)
    except ValueError:
        print_error("Invalid book ID format")
        return

    result = manager.mark_book_read(series_uuid, book_uuid, is_read=not unread)
    if result:
        status = "read" if not unread else "unread"
        console.print(f"[green]Marked {result.position_display} as {status}[/green]")
    else:
        print_error("Book not found in series")


@series_app.command("status")
def series_status(
    series_id: str = typer.Argument(..., help="Series ID or name"),
    status: str = typer.Argument(..., help="New status (not_started, in_progress, completed, on_hold, abandoned)"),
) -> None:
    """Update series reading status."""
    from uuid import UUID
    from .series import SeriesManager, SeriesUpdate, SeriesStatus

    db = get_db()
    manager = SeriesManager(db)

    # Parse status
    try:
        status_enum = SeriesStatus(status.lower())
    except ValueError:
        valid = ", ".join([s.value for s in SeriesStatus])
        print_error(f"Invalid status. Valid: {valid}")
        return

    # Find series
    try:
        series_uuid = UUID(series_id)
    except ValueError:
        series_list = manager.list_series(search=series_id, limit=1)
        if not series_list:
            print_error("Series not found")
            return
        series_uuid = series_list[0].id

    result = manager.update_series(series_uuid, SeriesUpdate(status=status_enum))
    if result:
        console.print(f"[green]Status updated to: {result.status_display}[/green]")
    else:
        print_error("Series not found")


@series_app.command("next")
def series_next(
    limit: int = typer.Option(5, "--limit", "-n", help="Number of recommendations"),
) -> None:
    """Show next books to read in your series."""
    from .series import SeriesManager

    db = get_db()
    manager = SeriesManager(db)

    recommendations = manager.get_next_in_series(limit=limit)

    if not recommendations:
        print_info("No in-progress series with unread books")
        return

    table = Table(title="Next in Series")
    table.add_column("Series")
    table.add_column("Next Book")
    table.add_column("Position")
    table.add_column("Progress")

    for rec in recommendations:
        progress = f"{rec.books_read_in_series}"
        if rec.total_in_series:
            progress += f"/{rec.total_in_series}"

        table.add_row(
            rec.series_name[:30] + "..." if len(rec.series_name) > 30 else rec.series_name,
            rec.book_entry.book_title or "[dim]Unknown[/dim]",
            rec.book_entry.position_display,
            progress,
        )

    console.print(table)


@series_app.command("stats")
def series_stats() -> None:
    """Show series statistics."""
    from .series import SeriesManager

    db = get_db()
    manager = SeriesManager(db)

    stats = manager.get_stats()

    if stats.total_series == 0:
        print_info("No series tracked yet")
        return

    # Status breakdown
    status_lines = []
    for status, count in stats.by_status.items():
        status_lines.append(f"  {status}: {count}")

    content = f"""[bold]Total Series:[/bold] {stats.total_series}

[bold]By Status:[/bold]
{chr(10).join(status_lines) if status_lines else '  None'}

[bold]Progress:[/bold]
  Completed: {stats.completed_series}
  In Progress: {stats.in_progress_series}

[bold]Books:[/bold]
  Total Series Books: {stats.total_series_books}
  Books Read: {stats.series_books_read}
  Overall Completion: {stats.overall_completion:.1f}%

[bold]Insights:[/bold]
  Avg Series Length: {stats.average_series_length:.1f} books
  Longest Series: {stats.longest_series or 'N/A'}
  Most Read: {stats.most_read_series or 'N/A'}"""

    console.print(Panel(content, title="[blue]Series Statistics[/blue]"))


@series_app.command("delete")
def series_delete(
    series_id: str = typer.Argument(..., help="Series ID or name"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a series (keeps the books)."""
    from uuid import UUID
    from .series import SeriesManager

    db = get_db()
    manager = SeriesManager(db)

    # Find series
    try:
        series_uuid = UUID(series_id)
        series = manager.get_series(series_uuid)
    except ValueError:
        series_list = manager.list_series(search=series_id, limit=1)
        if not series_list:
            print_error("Series not found")
            return
        series_uuid = series_list[0].id
        series = manager.get_series(series_uuid)

    if not series:
        print_error("Series not found")
        return

    if not confirm:
        console.print(f"Delete series '[bold]{series.name}[/bold]'?")
        console.print("[dim]Note: This removes the series but keeps all books in your library.[/dim]")
        if not typer.confirm("Confirm?"):
            print_info("Cancelled")
            return

    if manager.delete_series(series_uuid):
        console.print(f"[green]Deleted series '{series.name}'[/green]")
    else:
        print_error("Failed to delete series")


# ============================================================================
# Reading Lists Commands
# ============================================================================

lists_app = typer.Typer(help="Manage reading lists and get recommendations.")
app.add_typer(lists_app, name="lists")


@lists_app.command("create")
def lists_create(
    name: str = typer.Argument(..., help="List name"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
    list_type: str = typer.Option("custom", "--type", "-t", help="Type: custom, seasonal, themed"),
    pinned: bool = typer.Option(False, "--pinned", "-p", help="Pin this list"),
    icon: Optional[str] = typer.Option(None, "--icon", "-i", help="Icon emoji"),
) -> None:
    """Create a new reading list."""
    from .lists import ReadingListManager, ReadingListCreate, ListType

    db = get_db()
    manager = ReadingListManager(db)

    # Parse list type
    try:
        type_enum = ListType(list_type.lower())
    except ValueError:
        valid = ", ".join([t.value for t in ListType if t != ListType.AUTO])
        print_error(f"Invalid type. Valid: {valid}")
        return

    reading_list = ReadingListCreate(
        name=name,
        description=description,
        list_type=type_enum,
        is_pinned=pinned,
        icon=icon,
    )

    result = manager.create_list(reading_list)
    console.print(Panel(
        f"[bold]{result.name}[/bold]\n"
        f"Type: {result.type_display}\n"
        f"Pinned: {'Yes' if result.is_pinned else 'No'}",
        title="[green]List Created[/green]"
    ))
    console.print(f"\n[dim]ID: {result.id}[/dim]")


@lists_app.command("list")
def lists_list(
    list_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    pinned: bool = typer.Option(False, "--pinned", "-p", help="Show pinned only"),
) -> None:
    """Show all reading lists."""
    from .lists import ReadingListManager, ListType

    db = get_db()
    manager = ReadingListManager(db)

    # Parse type filter
    type_enum = None
    if list_type:
        try:
            type_enum = ListType(list_type.lower())
        except ValueError:
            pass

    lists = manager.get_all_lists(list_type=type_enum, pinned_only=pinned)

    if not lists:
        print_info("No reading lists found")
        return

    table = Table(title=f"Reading Lists ({len(lists)})")
    table.add_column("", justify="center", width=3)
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Books", justify="right")
    table.add_column("Pinned")

    for lst in lists:
        icon = lst.icon or ""
        pinned_str = "[yellow]*[/yellow]" if lst.is_pinned else ""

        table.add_row(
            icon,
            lst.name,
            lst.type_display,
            str(lst.book_count),
            pinned_str,
        )

    console.print(table)


@lists_app.command("show")
def lists_show(
    list_id: str = typer.Argument(..., help="List ID or name"),
) -> None:
    """Show a reading list with its books."""
    from uuid import UUID
    from .lists import ReadingListManager

    db = get_db()
    manager = ReadingListManager(db)

    # Find list
    try:
        uuid = UUID(list_id)
        result = manager.get_list_with_books(uuid)
    except ValueError:
        all_lists = manager.get_all_lists()
        matching = [lst for lst in all_lists if list_id.lower() in lst.name.lower()]
        if not matching:
            print_error("List not found")
            return
        result = manager.get_list_with_books(matching[0].id)

    if not result:
        print_error("List not found")
        return

    lst = result.list
    content = f"""[bold]{lst.icon or ''} {lst.name}[/bold]
Type: {lst.type_display}
Books: {lst.book_count}
Pinned: {'Yes' if lst.is_pinned else 'No'}

{lst.description or '[dim]No description[/dim]'}"""

    console.print(Panel(content, title="[blue]Reading List[/blue]"))

    if result.books:
        table = Table(title="Books")
        table.add_column("#", justify="right")
        table.add_column("Title")
        table.add_column("Author")
        table.add_column("Status")
        table.add_column("Rating")

        for i, book in enumerate(result.books, 1):
            rating = f"{book.book_rating}/5" if book.book_rating else "[dim]-[/dim]"

            table.add_row(
                str(i),
                book.book_title or f"[dim]{book.book_id}[/dim]",
                book.book_author or "[dim]Unknown[/dim]",
                book.book_status or "[dim]-[/dim]",
                rating,
            )

        console.print(table)
    else:
        print_info("No books in this list yet")

    console.print(f"\n[dim]ID: {lst.id}[/dim]")


@lists_app.command("add")
def lists_add(
    list_id: str = typer.Argument(..., help="List ID or name"),
    book_id: str = typer.Argument(..., help="Book ID to add"),
    note: Optional[str] = typer.Option(None, "--note", "-n", help="Note about why this book is in the list"),
) -> None:
    """Add a book to a reading list."""
    from uuid import UUID
    from .lists import ReadingListManager, ListBookCreate

    db = get_db()
    manager = ReadingListManager(db)

    # Find list
    try:
        list_uuid = UUID(list_id)
    except ValueError:
        all_lists = manager.get_all_lists()
        matching = [lst for lst in all_lists if list_id.lower() in lst.name.lower()]
        if not matching:
            print_error("List not found")
            return
        list_uuid = matching[0].id

    # Validate book ID
    try:
        book_uuid = UUID(book_id)
    except ValueError:
        print_error("Invalid book ID format")
        return

    entry = ListBookCreate(book_id=book_uuid, note=note)
    result = manager.add_book_to_list(list_uuid, entry)

    if result:
        console.print(f"[green]Added book to list at position {result.position + 1}[/green]")
    else:
        print_error("Failed to add book - list not found")


@lists_app.command("remove")
def lists_remove(
    list_id: str = typer.Argument(..., help="List ID or name"),
    book_id: str = typer.Argument(..., help="Book ID to remove"),
) -> None:
    """Remove a book from a reading list."""
    from uuid import UUID
    from .lists import ReadingListManager

    db = get_db()
    manager = ReadingListManager(db)

    # Find list
    try:
        list_uuid = UUID(list_id)
    except ValueError:
        all_lists = manager.get_all_lists()
        matching = [lst for lst in all_lists if list_id.lower() in lst.name.lower()]
        if not matching:
            print_error("List not found")
            return
        list_uuid = matching[0].id

    # Validate book ID
    try:
        book_uuid = UUID(book_id)
    except ValueError:
        print_error("Invalid book ID format")
        return

    if manager.remove_book_from_list(list_uuid, book_uuid):
        console.print("[green]Book removed from list[/green]")
    else:
        print_error("Book not found in list")


@lists_app.command("delete")
def lists_delete(
    list_id: str = typer.Argument(..., help="List ID or name"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a reading list."""
    from uuid import UUID
    from .lists import ReadingListManager

    db = get_db()
    manager = ReadingListManager(db)

    # Find list
    try:
        list_uuid = UUID(list_id)
        lst = manager.get_list(list_uuid)
    except ValueError:
        all_lists = manager.get_all_lists()
        matching = [l for l in all_lists if list_id.lower() in l.name.lower()]
        if not matching:
            print_error("List not found")
            return
        list_uuid = matching[0].id
        lst = manager.get_list(list_uuid)

    if not lst:
        print_error("List not found")
        return

    if not confirm:
        console.print(f"Delete list '[bold]{lst.name}[/bold]'?")
        if not typer.confirm("Confirm?"):
            print_info("Cancelled")
            return

    if manager.delete_list(list_uuid):
        console.print(f"[green]Deleted list '{lst.name}'[/green]")
    else:
        print_error("Failed to delete list")


@lists_app.command("pin")
def lists_pin(
    list_id: str = typer.Argument(..., help="List ID or name"),
    unpin: bool = typer.Option(False, "--unpin", help="Unpin instead of pin"),
) -> None:
    """Pin or unpin a reading list."""
    from uuid import UUID
    from .lists import ReadingListManager, ReadingListUpdate

    db = get_db()
    manager = ReadingListManager(db)

    # Find list
    try:
        list_uuid = UUID(list_id)
    except ValueError:
        all_lists = manager.get_all_lists()
        matching = [lst for lst in all_lists if list_id.lower() in lst.name.lower()]
        if not matching:
            print_error("List not found")
            return
        list_uuid = matching[0].id

    result = manager.update_list(list_uuid, ReadingListUpdate(is_pinned=not unpin))
    if result:
        status = "unpinned" if unpin else "pinned"
        console.print(f"[green]List {status}[/green]")
    else:
        print_error("List not found")


# ============================================================================
# Recommendations Commands
# ============================================================================

recommend_app = typer.Typer(help="Get personalized book recommendations.")
app.add_typer(recommend_app, name="recommend")


@recommend_app.command("all")
def recommend_all(
    limit: int = typer.Option(5, "--limit", "-n", help="Recommendations per category"),
) -> None:
    """Get personalized recommendations across all categories."""
    from .lists import ReadingListManager

    db = get_db()
    manager = ReadingListManager(db)

    rec_sets = manager.get_recommendations(limit=limit)

    if not rec_sets:
        print_info("Not enough data for recommendations. Read and rate more books!")
        return

    for rec_set in rec_sets:
        console.print(f"\n[bold cyan]{rec_set.title}[/bold cyan]")
        if rec_set.description:
            console.print(f"[dim]{rec_set.description}[/dim]\n")

        table = Table(show_header=True)
        table.add_column("Title")
        table.add_column("Author")
        table.add_column("Why")

        for rec in rec_set.recommendations:
            table.add_row(
                rec.book_title[:40] + "..." if len(rec.book_title) > 40 else rec.book_title,
                rec.book_author or "[dim]Unknown[/dim]",
                rec.reason_display,
            )

        console.print(table)


@recommend_app.command("similar")
def recommend_similar(
    book_id: str = typer.Argument(..., help="Book ID to find similar books for"),
    limit: int = typer.Option(5, "--limit", "-n", help="Number of similar books"),
) -> None:
    """Find books similar to a given book."""
    from uuid import UUID
    from .lists import ReadingListManager

    db = get_db()
    manager = ReadingListManager(db)

    try:
        uuid = UUID(book_id)
    except ValueError:
        print_error("Invalid book ID format")
        return

    similar = manager.get_similar_books(uuid, limit=limit)

    if not similar:
        print_info("No similar books found")
        return

    table = Table(title="Similar Books")
    table.add_column("Title")
    table.add_column("Author")
    table.add_column("Match")
    table.add_column("Same Author")

    for book in similar:
        match_pct = f"{book.similarity_score * 100:.0f}%"
        same = "[green]Yes[/green]" if book.same_author else "[dim]No[/dim]"

        table.add_row(
            book.book_title[:40] + "..." if len(book.book_title) > 40 else book.book_title,
            book.book_author or "[dim]Unknown[/dim]",
            match_pct,
            same,
        )

    console.print(table)


@recommend_app.command("genre")
def recommend_genre(
    genre: str = typer.Argument(..., help="Genre to get recommendations for"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of recommendations"),
) -> None:
    """Get recommendations for a specific genre."""
    from .lists import ReadingListManager

    db = get_db()
    manager = ReadingListManager(db)

    recs = manager.get_genre_recommendations(genre, limit=limit)

    content = f"""[bold]Genre:[/bold] {recs.genre}
[bold]Unread:[/bold] {recs.unread_count} books
[bold]Avg Rating (read):[/bold] {f'{recs.average_rating:.1f}/5' if recs.average_rating else 'N/A'}"""

    console.print(Panel(content, title=f"[blue]{genre} Recommendations[/blue]"))

    if recs.top_rated:
        table = Table(title="Top Rated Unread")
        table.add_column("Title")
        table.add_column("Author")

        for rec in recs.top_rated:
            table.add_row(
                rec.book_title[:40] + "..." if len(rec.book_title) > 40 else rec.book_title,
                rec.book_author or "[dim]Unknown[/dim]",
            )

        console.print(table)
    else:
        print_info(f"No unread {genre} books found")


@recommend_app.command("author")
def recommend_author(
    author: str = typer.Argument(..., help="Author to get recommendations for"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of recommendations"),
) -> None:
    """Get recommendations for books by an author."""
    from .lists import ReadingListManager

    db = get_db()
    manager = ReadingListManager(db)

    recs = manager.get_author_recommendations(author, limit=limit)

    content = f"""[bold]Author:[/bold] {recs.author}
[bold]Books Read:[/bold] {recs.books_read}
[bold]Avg Rating:[/bold] {f'{recs.average_rating:.1f}/5' if recs.average_rating else 'N/A'}"""

    console.print(Panel(content, title=f"[blue]{author} Recommendations[/blue]"))

    if recs.unread_books:
        table = Table(title="Unread Books")
        table.add_column("Title")
        table.add_column("Context")

        for rec in recs.unread_books:
            table.add_row(
                rec.book_title[:40] + "..." if len(rec.book_title) > 40 else rec.book_title,
                rec.context or "",
            )

        console.print(table)
    else:
        print_info(f"No unread books by {author} found")


@recommend_app.command("stats")
def recommend_stats() -> None:
    """Show recommendation statistics."""
    from .lists import ReadingListManager

    db = get_db()
    manager = ReadingListManager(db)

    stats = manager.get_recommendation_stats()

    content = f"""[bold]Overview[/bold]
Total Unread: {stats.total_unread}
Highly Rated Unread: {stats.highly_rated_unread}
Quick Reads Available: {stats.quick_reads_available}

[bold]Favorite Genres[/bold]
{chr(10).join(f'  - {g}' for g in stats.favorite_genres) if stats.favorite_genres else '  [dim]Not enough data[/dim]'}

[bold]Favorite Authors[/bold]
{chr(10).join(f'  - {a}' for a in stats.favorite_authors) if stats.favorite_authors else '  [dim]Not enough data[/dim]'}"""

    console.print(Panel(content, title="[blue]Recommendation Stats[/blue]"))


# ============================================================================
# Schedule & Planning Commands
# ============================================================================

plan_app = typer.Typer(help="Manage reading plans and schedules.")
app.add_typer(plan_app, name="plan")


@plan_app.command("create")
def plan_create(
    name: str = typer.Argument(..., help="Plan name"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
    start: Optional[str] = typer.Option(None, "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
    target_books: Optional[int] = typer.Option(None, "--books", "-b", help="Target number of books"),
    target_pages: Optional[int] = typer.Option(None, "--pages", "-p", help="Target number of pages"),
) -> None:
    """Create a new reading plan."""
    from .schedule import ScheduleManager, ReadingPlanCreate

    db = get_db()
    manager = ScheduleManager(db)

    start_date = None
    end_date = None
    if start:
        try:
            start_date = date.fromisoformat(start)
        except ValueError:
            print_error("Invalid start date format. Use YYYY-MM-DD")
            raise typer.Exit(1)
    if end:
        try:
            end_date = date.fromisoformat(end)
        except ValueError:
            print_error("Invalid end date format. Use YYYY-MM-DD")
            raise typer.Exit(1)

    plan_data = ReadingPlanCreate(
        name=name,
        description=description,
        start_date=start_date,
        end_date=end_date,
        target_books=target_books,
        target_pages=target_pages,
    )

    plan = manager.create_plan(plan_data)
    print_success(f"Created plan: {plan.name}")
    console.print(f"  ID: [cyan]{plan.id}[/cyan]")
    console.print(f"  Status: [yellow]{plan.status.value}[/yellow]")
    if plan.end_date:
        console.print(f"  Deadline: {plan.end_date}")


@plan_app.command("list")
def plan_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include completed/cancelled plans"),
) -> None:
    """List all reading plans."""
    from .schedule import ScheduleManager

    db = get_db()
    manager = ScheduleManager(db)

    plans = manager.get_all_plans(include_completed=all)

    if not plans:
        console.print("[dim]No reading plans found.[/dim]")
        return

    table = Table(title="Reading Plans")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Books")
    table.add_column("Progress")
    table.add_column("Deadline")

    for plan in plans:
        status_color = {
            "draft": "dim",
            "active": "green",
            "completed": "cyan",
            "paused": "yellow",
            "cancelled": "red",
        }.get(plan.status.value, "white")

        progress_bar = ""
        if plan.progress_percentage > 0:
            filled = int(plan.progress_percentage / 10)
            progress_bar = f"[green]{'█' * filled}[/green]{'░' * (10 - filled)} {plan.progress_percentage:.0f}%"
        else:
            progress_bar = "░░░░░░░░░░ 0%"

        table.add_row(
            plan.name,
            f"[{status_color}]{plan.status.value}[/{status_color}]",
            f"{plan.books_completed}/{plan.books_planned}",
            progress_bar,
            str(plan.end_date) if plan.end_date else "-",
        )

    console.print(table)


@plan_app.command("show")
def plan_show(
    plan_id: str = typer.Argument(..., help="Plan ID"),
) -> None:
    """Show details of a reading plan."""
    from uuid import UUID
    from .schedule import ScheduleManager

    db = get_db()
    manager = ScheduleManager(db)

    try:
        uuid = UUID(plan_id)
    except ValueError:
        print_error("Invalid plan ID format")
        raise typer.Exit(1)

    plan = manager.get_plan(uuid)
    if not plan:
        print_error("Plan not found")
        raise typer.Exit(1)

    # Progress info
    progress = manager.get_plan_progress(uuid)

    console.print(Panel(f"[bold]{plan.name}[/bold]", style="magenta"))

    if plan.description:
        console.print(f"[dim]{plan.description}[/dim]\n")

    # Status table
    table = Table(show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Status", plan.status.value)
    table.add_row("Books", f"{plan.books_completed}/{plan.books_planned}")
    table.add_row("Pages", f"{plan.pages_read:,}/{plan.pages_planned:,}")
    table.add_row("Progress", f"{plan.progress_percentage:.1f}%")

    if plan.start_date:
        table.add_row("Start Date", str(plan.start_date))
    if plan.end_date:
        table.add_row("End Date", str(plan.end_date))
    if plan.days_remaining is not None:
        table.add_row("Days Remaining", str(plan.days_remaining))

    table.add_row("On Track", "[green]Yes[/green]" if plan.on_track else "[red]No[/red]")

    console.print(table)

    # Show books in plan
    books = manager.get_books_in_plan(uuid)
    if books:
        console.print("\n[bold]Books in Plan:[/bold]")
        for book in books[:10]:
            status = "[green]✓[/green]" if book.is_completed else "[yellow]▶[/yellow]" if book.actual_start_date else "[dim]○[/dim]"
            deadline = f" (due {book.target_end_date})" if book.target_end_date and not book.is_completed else ""
            overdue = " [red]OVERDUE[/red]" if book.is_overdue else ""
            console.print(f"  {status} {book.book_title}{deadline}{overdue}")


@plan_app.command("activate")
def plan_activate(
    plan_id: str = typer.Argument(..., help="Plan ID"),
) -> None:
    """Activate a reading plan."""
    from uuid import UUID
    from .schedule import ScheduleManager

    db = get_db()
    manager = ScheduleManager(db)

    try:
        uuid = UUID(plan_id)
    except ValueError:
        print_error("Invalid plan ID format")
        raise typer.Exit(1)

    plan = manager.activate_plan(uuid)
    if not plan:
        print_error("Plan not found")
        raise typer.Exit(1)

    print_success(f"Plan '{plan.name}' is now active")


@plan_app.command("complete")
def plan_complete(
    plan_id: str = typer.Argument(..., help="Plan ID"),
) -> None:
    """Mark a reading plan as completed."""
    from uuid import UUID
    from .schedule import ScheduleManager

    db = get_db()
    manager = ScheduleManager(db)

    try:
        uuid = UUID(plan_id)
    except ValueError:
        print_error("Invalid plan ID format")
        raise typer.Exit(1)

    plan = manager.complete_plan(uuid)
    if not plan:
        print_error("Plan not found")
        raise typer.Exit(1)

    print_success(f"Plan '{plan.name}' marked as completed")
    console.print(f"  Books completed: {plan.books_completed}/{plan.books_planned}")


@plan_app.command("add-book")
def plan_add_book(
    plan_id: str = typer.Argument(..., help="Plan ID"),
    book_query: str = typer.Argument(..., help="Book title or ID"),
    deadline: Optional[str] = typer.Option(None, "--deadline", "-d", help="Target end date (YYYY-MM-DD)"),
    priority: int = typer.Option(2, "--priority", "-p", help="Priority 1-5 (1=highest)"),
) -> None:
    """Add a book to a reading plan."""
    from uuid import UUID
    from .schedule import ScheduleManager, PlannedBookCreate

    db = get_db()
    manager = ScheduleManager(db)

    # Parse plan ID
    try:
        plan_uuid = UUID(plan_id)
    except ValueError:
        print_error("Invalid plan ID format")
        raise typer.Exit(1)

    # Find book
    try:
        book_uuid = UUID(book_query)
        books = [db.get_book(book_uuid)]
    except ValueError:
        books = db.search_books(book_query, limit=1)

    if not books or not books[0]:
        print_error(f"Book not found: {book_query}")
        raise typer.Exit(1)

    book = books[0]

    # Parse deadline
    target_end = None
    if deadline:
        try:
            target_end = date.fromisoformat(deadline)
        except ValueError:
            print_error("Invalid deadline format. Use YYYY-MM-DD")
            raise typer.Exit(1)

    planned_data = PlannedBookCreate(
        book_id=UUID(book.id),
        plan_id=plan_uuid,
        target_end_date=target_end,
        priority=priority,
    )

    result = manager.add_book_to_plan(planned_data)
    if not result:
        print_error("Could not add book to plan")
        raise typer.Exit(1)

    print_success(f"Added '{book.title}' to plan")
    if target_end:
        console.print(f"  Deadline: {target_end}")


@plan_app.command("deadlines")
def plan_deadlines(
    days: int = typer.Option(30, "--days", "-d", help="Days to look ahead"),
) -> None:
    """Show upcoming book deadlines."""
    from .schedule import ScheduleManager

    db = get_db()
    manager = ScheduleManager(db)

    deadlines = manager.get_upcoming_deadlines(days)

    if not deadlines:
        console.print(f"[dim]No upcoming deadlines in the next {days} days.[/dim]")
        return

    table = Table(title=f"Upcoming Deadlines (next {days} days)")
    table.add_column("Book")
    table.add_column("Author")
    table.add_column("Deadline")
    table.add_column("Days Left")
    table.add_column("Status")

    for d in deadlines:
        days_color = "green" if d.days_remaining > 7 else "yellow" if d.days_remaining > 0 else "red"
        status = "[red]OVERDUE[/red]" if d.days_remaining < 0 else "[yellow]AT RISK[/yellow]" if d.is_at_risk else "[green]OK[/green]"

        table.add_row(
            d.book_title[:30] + "..." if len(d.book_title) > 30 else d.book_title,
            d.book_author or "-",
            str(d.deadline),
            f"[{days_color}]{d.days_remaining}[/{days_color}]",
            status,
        )

    console.print(table)


@plan_app.command("summary")
def plan_summary() -> None:
    """Show schedule and planning summary."""
    from .schedule import ScheduleManager

    db = get_db()
    manager = ScheduleManager(db)

    summary = manager.get_schedule_summary()

    console.print(Panel("[bold]Schedule Summary[/bold]", style="magenta"))

    # Overview
    console.print(f"[cyan]Active Plans:[/cyan] {summary.active_plans}")
    console.print(f"[cyan]Books in Plans:[/cyan] {summary.books_in_plans}")
    if summary.current_book:
        console.print(f"[cyan]Currently Reading:[/cyan] {summary.current_book}")
    if summary.reading_time_today:
        console.print(f"[cyan]Scheduled Reading Today:[/cyan] {summary.reading_time_today}")

    # Upcoming deadlines
    if summary.upcoming_deadlines:
        console.print("\n[bold]Upcoming Deadlines:[/bold]")
        for d in summary.upcoming_deadlines[:5]:
            status = "[red]OVERDUE[/red]" if d.days_remaining < 0 else f"{d.days_remaining} days"
            console.print(f"  • {d.book_title}: {d.deadline} ({status})")

    # Weekly schedule
    if summary.this_week_schedule.entries:
        console.print(f"\n[bold]This Week:[/bold]")
        console.print(f"  Planned: {summary.this_week_schedule.total_planned_minutes} min")
        console.print(f"  Completed: {summary.this_week_schedule.completed_minutes} min")
        console.print(f"  Completion: {summary.this_week_schedule.completion_rate:.0f}%")


schedule_app = typer.Typer(help="Manage recurring reading schedules.")
app.add_typer(schedule_app, name="schedule")


@schedule_app.command("create")
def schedule_create(
    name: str = typer.Argument(..., help="Schedule name"),
    duration: int = typer.Option(30, "--duration", "-d", help="Duration in minutes"),
    time_str: Optional[str] = typer.Option(None, "--time", "-t", help="Preferred time (HH:MM)"),
    frequency: str = typer.Option("daily", "--frequency", "-f", help="Frequency: daily, weekdays, weekends, weekly"),
    days: Optional[str] = typer.Option(None, "--days", help="Days of week (0=Mon, comma-separated)"),
) -> None:
    """Create a recurring reading schedule."""
    from .schedule import ScheduleManager, ScheduleEntryCreate, ScheduleFrequency

    db = get_db()
    manager = ScheduleManager(db)

    # Parse time
    preferred_time = None
    if time_str:
        try:
            parts = time_str.split(":")
            preferred_time = time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            print_error("Invalid time format. Use HH:MM")
            raise typer.Exit(1)

    # Parse frequency
    try:
        freq = ScheduleFrequency(frequency.lower())
    except ValueError:
        print_error(f"Invalid frequency: {frequency}. Use: daily, weekdays, weekends, weekly")
        raise typer.Exit(1)

    # Parse days
    days_list = None
    if days:
        try:
            days_list = [int(d.strip()) for d in days.split(",")]
        except ValueError:
            print_error("Invalid days format. Use comma-separated numbers (0=Mon)")
            raise typer.Exit(1)

    entry_data = ScheduleEntryCreate(
        name=name,
        frequency=freq,
        days_of_week=days_list,
        preferred_time=preferred_time,
        duration_minutes=duration,
    )

    entry = manager.create_schedule_entry(entry_data)
    print_success(f"Created schedule: {entry.name}")
    console.print(f"  Frequency: {entry.frequency.value}")
    console.print(f"  Duration: {entry.duration_minutes} minutes")
    if entry.preferred_time:
        console.print(f"  Time: {entry.preferred_time}")


@schedule_app.command("list")
def schedule_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include inactive schedules"),
) -> None:
    """List reading schedules."""
    from .schedule import ScheduleManager

    db = get_db()
    manager = ScheduleManager(db)

    entries = manager.get_all_schedule_entries(active_only=not all)

    if not entries:
        console.print("[dim]No schedules found.[/dim]")
        return

    table = Table(title="Reading Schedules")
    table.add_column("Name")
    table.add_column("Frequency")
    table.add_column("Time")
    table.add_column("Duration")
    table.add_column("Next")
    table.add_column("Active")

    for entry in entries:
        table.add_row(
            entry.name,
            entry.frequency.value,
            str(entry.preferred_time) if entry.preferred_time else "-",
            f"{entry.duration_minutes} min",
            str(entry.next_occurrence) if entry.next_occurrence else "-",
            "[green]Yes[/green]" if entry.is_active else "[dim]No[/dim]",
        )

    console.print(table)


@schedule_app.command("delete")
def schedule_delete(
    entry_id: str = typer.Argument(..., help="Schedule entry ID"),
) -> None:
    """Delete a schedule entry."""
    from uuid import UUID
    from .schedule import ScheduleManager

    db = get_db()
    manager = ScheduleManager(db)

    try:
        uuid = UUID(entry_id)
    except ValueError:
        print_error("Invalid entry ID format")
        raise typer.Exit(1)

    if manager.delete_schedule_entry(uuid):
        print_success("Schedule deleted")
    else:
        print_error("Schedule not found")
        raise typer.Exit(1)


reminder_app = typer.Typer(help="Manage reading reminders.")
app.add_typer(reminder_app, name="reminder")


@reminder_app.command("create")
def reminder_create(
    time_str: str = typer.Argument(..., help="Reminder time (HH:MM)"),
    reminder_type: str = typer.Option("reading_time", "--type", "-t", help="Type: reading_time, deadline, goal_check, streak"),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Custom message"),
    days: Optional[str] = typer.Option(None, "--days", help="Days of week (0=Mon, comma-separated)"),
) -> None:
    """Create a reading reminder."""
    from .schedule import ScheduleManager, ReminderCreate, ReminderType

    db = get_db()
    manager = ScheduleManager(db)

    # Parse time
    try:
        parts = time_str.split(":")
        reminder_time = time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        print_error("Invalid time format. Use HH:MM")
        raise typer.Exit(1)

    # Parse type
    try:
        rtype = ReminderType(reminder_type.lower())
    except ValueError:
        print_error(f"Invalid type: {reminder_type}")
        raise typer.Exit(1)

    # Parse days
    days_list = None
    if days:
        try:
            days_list = [int(d.strip()) for d in days.split(",")]
        except ValueError:
            print_error("Invalid days format")
            raise typer.Exit(1)

    reminder_data = ReminderCreate(
        reminder_type=rtype,
        message=message,
        reminder_time=reminder_time,
        days_of_week=days_list,
    )

    reminder = manager.create_reminder(reminder_data)
    print_success(f"Created reminder at {reminder.reminder_time}")
    console.print(f"  Type: {reminder.reminder_type.value}")


@reminder_app.command("list")
def reminder_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include inactive reminders"),
) -> None:
    """List reading reminders."""
    from .schedule import ScheduleManager

    db = get_db()
    manager = ScheduleManager(db)

    reminders = manager.get_all_reminders(active_only=not all)

    if not reminders:
        console.print("[dim]No reminders found.[/dim]")
        return

    table = Table(title="Reading Reminders")
    table.add_column("Time")
    table.add_column("Type")
    table.add_column("Message")
    table.add_column("Active")

    for r in reminders:
        table.add_row(
            str(r.reminder_time),
            r.reminder_type.value,
            r.message or "-",
            "[green]Yes[/green]" if r.is_active else "[dim]No[/dim]",
        )

    console.print(table)


@reminder_app.command("delete")
def reminder_delete(
    reminder_id: str = typer.Argument(..., help="Reminder ID"),
) -> None:
    """Delete a reminder."""
    from uuid import UUID
    from .schedule import ScheduleManager

    db = get_db()
    manager = ScheduleManager(db)

    try:
        uuid = UUID(reminder_id)
    except ValueError:
        print_error("Invalid reminder ID format")
        raise typer.Exit(1)

    if manager.delete_reminder(uuid):
        print_success("Reminder deleted")
    else:
        print_error("Reminder not found")
        raise typer.Exit(1)


# ============================================================================
# Tags & Custom Metadata Commands
# ============================================================================

tag_app = typer.Typer(help="Manage tags for book organization.")
app.add_typer(tag_app, name="tag")


@tag_app.command("create")
def tag_create(
    name: str = typer.Argument(..., help="Tag name"),
    color: str = typer.Option("gray", "--color", "-c", help="Tag color"),
    icon: Optional[str] = typer.Option(None, "--icon", "-i", help="Tag icon (emoji)"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
    parent: Optional[str] = typer.Option(None, "--parent", "-p", help="Parent tag name or ID"),
) -> None:
    """Create a new tag."""
    from uuid import UUID
    from .tags import TagManager, TagCreate, TagColor

    db = get_db()
    manager = TagManager(db)

    # Parse color
    try:
        tag_color = TagColor(color.lower())
    except ValueError:
        colors = ", ".join(c.value for c in TagColor)
        print_error(f"Invalid color: {color}. Use: {colors}")
        raise typer.Exit(1)

    # Find parent tag
    parent_id = None
    if parent:
        try:
            parent_id = UUID(parent)
        except ValueError:
            parent_tag = manager.get_tag_by_name(parent)
            if parent_tag:
                parent_id = parent_tag.id
            else:
                print_error(f"Parent tag not found: {parent}")
                raise typer.Exit(1)

    tag_data = TagCreate(
        name=name,
        color=tag_color,
        icon=icon,
        description=description,
        parent_id=parent_id,
    )

    tag = manager.create_tag(tag_data)
    print_success(f"Created tag: {tag.name}")
    console.print(f"  ID: [cyan]{tag.id}[/cyan]")
    console.print(f"  Color: [{tag.color.value}]{tag.color.value}[/{tag.color.value}]")


@tag_app.command("list")
def tag_list(
    tree: bool = typer.Option(False, "--tree", "-t", help="Show as hierarchy tree"),
) -> None:
    """List all tags."""
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    if tree:
        hierarchy = manager.get_tags_hierarchy()
        if not hierarchy:
            console.print("[dim]No tags found.[/dim]")
            return

        def print_tag_tree(tag, indent=0):
            prefix = "  " * indent + ("└─ " if indent > 0 else "")
            color = tag.color.value
            console.print(f"{prefix}[{color}]{tag.icon or '●'}[/{color}] {tag.name} ({tag.book_count} books)")
            for child in tag.children:
                print_tag_tree(child, indent + 1)

        console.print("[bold]Tag Hierarchy:[/bold]\n")
        for tag in hierarchy:
            print_tag_tree(tag)
    else:
        tags = manager.get_all_tags(include_children=True)
        if not tags:
            console.print("[dim]No tags found.[/dim]")
            return

        table = Table(title="Tags")
        table.add_column("Name")
        table.add_column("Color")
        table.add_column("Books")
        table.add_column("Description")

        for tag in tags:
            table.add_row(
                f"{tag.icon or ''} {tag.name}".strip(),
                f"[{tag.color.value}]{tag.color.value}[/{tag.color.value}]",
                str(tag.book_count),
                tag.description or "-",
            )

        console.print(table)


@tag_app.command("add")
def tag_add(
    book_query: str = typer.Argument(..., help="Book title or ID"),
    tag_names: list[str] = typer.Argument(..., help="Tag names to add"),
) -> None:
    """Add tags to a book."""
    from uuid import UUID
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    # Find book
    try:
        book_uuid = UUID(book_query)
        books = [db.get_book(book_uuid)]
    except ValueError:
        books = db.search_books(book_query, limit=1)

    if not books or not books[0]:
        print_error(f"Book not found: {book_query}")
        raise typer.Exit(1)

    book = books[0]
    added_tags = []

    for tag_name in tag_names:
        # Find or create tag
        tag = manager.get_tag_by_name(tag_name)
        if not tag:
            from .tags import TagCreate, TagColor
            tag = manager.create_tag(TagCreate(name=tag_name, color=TagColor.GRAY))

        result = manager.tag_book(UUID(book.id), tag.id)
        if result:
            added_tags.append(tag.name)

    if added_tags:
        print_success(f"Added tags to '{book.title}': {', '.join(added_tags)}")
    else:
        print_info("No new tags added (book already has these tags)")


@tag_app.command("remove")
def tag_remove(
    book_query: str = typer.Argument(..., help="Book title or ID"),
    tag_name: str = typer.Argument(..., help="Tag name to remove"),
) -> None:
    """Remove a tag from a book."""
    from uuid import UUID
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    # Find book
    try:
        book_uuid = UUID(book_query)
        books = [db.get_book(book_uuid)]
    except ValueError:
        books = db.search_books(book_query, limit=1)

    if not books or not books[0]:
        print_error(f"Book not found: {book_query}")
        raise typer.Exit(1)

    book = books[0]

    # Find tag
    tag = manager.get_tag_by_name(tag_name)
    if not tag:
        print_error(f"Tag not found: {tag_name}")
        raise typer.Exit(1)

    if manager.untag_book(UUID(book.id), tag.id):
        print_success(f"Removed tag '{tag_name}' from '{book.title}'")
    else:
        print_info("Tag was not on this book")


@tag_app.command("show")
def tag_show(
    tag_name: str = typer.Argument(..., help="Tag name"),
) -> None:
    """Show books with a specific tag."""
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    tag = manager.get_tag_by_name(tag_name)
    if not tag:
        print_error(f"Tag not found: {tag_name}")
        raise typer.Exit(1)

    stats = manager.get_tag_stats(tag.id)
    books = manager.get_books_by_tag(tag.id, include_children=True)

    console.print(Panel(f"[bold]{tag.icon or '●'} {tag.name}[/bold]", style=tag.color.value))

    if tag.description:
        console.print(f"[dim]{tag.description}[/dim]\n")

    # Stats
    console.print(f"[cyan]Total Books:[/cyan] {stats.total_books}")
    console.print(f"[cyan]Completed:[/cyan] {stats.completed_books}")
    if stats.average_rating:
        console.print(f"[cyan]Avg Rating:[/cyan] {stats.average_rating:.1f}/5")
    console.print(f"[cyan]Total Pages:[/cyan] {stats.total_pages:,}")

    # Books
    if books:
        console.print("\n[bold]Books:[/bold]")
        for book in books[:20]:
            console.print(f"  • {book.book_title} by {book.book_author or 'Unknown'}")
        if len(books) > 20:
            console.print(f"  [dim]... and {len(books) - 20} more[/dim]")


@tag_app.command("delete")
def tag_delete(
    tag_name: str = typer.Argument(..., help="Tag name to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Delete without confirmation"),
) -> None:
    """Delete a tag."""
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    tag = manager.get_tag_by_name(tag_name)
    if not tag:
        print_error(f"Tag not found: {tag_name}")
        raise typer.Exit(1)

    if tag.book_count > 0 and not force:
        confirm = typer.confirm(f"Tag '{tag_name}' is used by {tag.book_count} books. Delete anyway?")
        if not confirm:
            print_info("Cancelled")
            return

    if manager.delete_tag(tag.id):
        print_success(f"Deleted tag: {tag_name}")
    else:
        print_error("Failed to delete tag")


@tag_app.command("cloud")
def tag_cloud() -> None:
    """Show tag usage statistics."""
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    cloud = manager.get_tag_cloud()

    if not cloud.tags:
        console.print("[dim]No tags found.[/dim]")
        return

    console.print(Panel("[bold]Tag Cloud[/bold]", style="magenta"))

    console.print(f"[cyan]Total Tags:[/cyan] {cloud.total_tags}")
    if cloud.most_used_tag:
        console.print(f"[cyan]Most Used:[/cyan] {cloud.most_used_tag}")
    if cloud.least_used_tag:
        console.print(f"[cyan]Least Used:[/cyan] {cloud.least_used_tag}")

    console.print("\n[bold]All Tags:[/bold]")
    # Sort by book count
    sorted_tags = sorted(cloud.tags, key=lambda t: t.total_books, reverse=True)
    for tag in sorted_tags:
        bar_len = min(30, tag.total_books)
        bar = "█" * bar_len if bar_len else "░"
        console.print(f"  [{tag.tag_color.value}]{tag.tag_name:>20}[/{tag.tag_color.value}]: {bar} {tag.total_books}")


@tag_app.command("suggest")
def tag_suggest(
    book_query: str = typer.Argument(..., help="Book title or ID"),
) -> None:
    """Suggest tags for a book."""
    from uuid import UUID
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    # Find book
    try:
        book_uuid = UUID(book_query)
        books = [db.get_book(book_uuid)]
    except ValueError:
        books = db.search_books(book_query, limit=1)

    if not books or not books[0]:
        print_error(f"Book not found: {book_query}")
        raise typer.Exit(1)

    book = books[0]
    suggestions = manager.suggest_tags(UUID(book.id))

    if not suggestions:
        print_info("No tag suggestions available for this book")
        return

    console.print(f"\n[bold]Tag Suggestions for '{book.title}':[/bold]\n")

    for s in suggestions:
        confidence_bar = "●" * int(s.confidence * 5) + "○" * (5 - int(s.confidence * 5))
        existing = "[green]exists[/green]" if s.existing_tag_id else "[dim]new[/dim]"
        console.print(f"  {confidence_bar} {s.tag_name} ({existing})")
        console.print(f"      [dim]{s.reason}[/dim]")


field_app = typer.Typer(help="Manage custom metadata fields.")
app.add_typer(field_app, name="field")


@field_app.command("create")
def field_create(
    name: str = typer.Argument(..., help="Field name"),
    field_type: str = typer.Option("text", "--type", "-t", help="Field type: text, number, date, boolean, select, rating, url"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
    required: bool = typer.Option(False, "--required", "-r", help="Make field required"),
    options: Optional[str] = typer.Option(None, "--options", "-o", help="Options for select (comma-separated)"),
) -> None:
    """Create a custom metadata field."""
    from .tags import TagManager, CustomFieldCreate, FieldType, SelectOption

    db = get_db()
    manager = TagManager(db)

    # Parse field type
    try:
        ftype = FieldType(field_type.lower())
    except ValueError:
        types = ", ".join(t.value for t in FieldType)
        print_error(f"Invalid type: {field_type}. Use: {types}")
        raise typer.Exit(1)

    # Parse options
    option_list = None
    if options and ftype in (FieldType.SELECT, FieldType.MULTI_SELECT):
        option_list = [
            SelectOption(value=opt.strip(), label=opt.strip())
            for opt in options.split(",")
        ]

    field_data = CustomFieldCreate(
        name=name,
        field_type=ftype,
        description=description,
        is_required=required,
        options=option_list,
    )

    field = manager.create_field(field_data)
    print_success(f"Created field: {field.name}")
    console.print(f"  Type: {field.field_type.value}")


@field_app.command("list")
def field_list() -> None:
    """List all custom fields."""
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    fields = manager.get_all_fields()

    if not fields:
        console.print("[dim]No custom fields defined.[/dim]")
        return

    table = Table(title="Custom Fields")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Required")
    table.add_column("Usage")
    table.add_column("Description")

    for field in fields:
        table.add_row(
            field.name,
            field.field_type.value,
            "Yes" if field.is_required else "No",
            str(field.usage_count),
            field.description or "-",
        )

    console.print(table)


@field_app.command("set")
def field_set(
    book_query: str = typer.Argument(..., help="Book title or ID"),
    field_name: str = typer.Argument(..., help="Field name"),
    value: str = typer.Argument(..., help="Value to set"),
) -> None:
    """Set a custom field value for a book."""
    from uuid import UUID
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    # Find book
    try:
        book_uuid = UUID(book_query)
        books = [db.get_book(book_uuid)]
    except ValueError:
        books = db.search_books(book_query, limit=1)

    if not books or not books[0]:
        print_error(f"Book not found: {book_query}")
        raise typer.Exit(1)

    book = books[0]

    # Find field by name
    fields = manager.get_all_fields()
    field = next((f for f in fields if f.name.lower() == field_name.lower()), None)

    if not field:
        print_error(f"Field not found: {field_name}")
        raise typer.Exit(1)

    result = manager.set_field_value(UUID(book.id), field.id, value)
    if result:
        print_success(f"Set {field_name} = {result.display_value} for '{book.title}'")
    else:
        print_error("Failed to set field value (check value format)")


@field_app.command("show")
def field_show(
    book_query: str = typer.Argument(..., help="Book title or ID"),
) -> None:
    """Show custom field values for a book."""
    from uuid import UUID
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    # Find book
    try:
        book_uuid = UUID(book_query)
        books = [db.get_book(book_uuid)]
    except ValueError:
        books = db.search_books(book_query, limit=1)

    if not books or not books[0]:
        print_error(f"Book not found: {book_query}")
        raise typer.Exit(1)

    book = books[0]
    result = manager.get_book_fields(UUID(book.id))

    if not result or not result.fields:
        console.print(f"[dim]No custom fields set for '{book.title}'[/dim]")
        return

    console.print(f"\n[bold]Custom Fields for '{book.title}':[/bold]\n")

    for field in result.fields:
        console.print(f"  [cyan]{field.field_name}:[/cyan] {field.display_value}")


@field_app.command("delete")
def field_delete(
    field_name: str = typer.Argument(..., help="Field name to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Delete without confirmation"),
) -> None:
    """Delete a custom field."""
    from .tags import TagManager

    db = get_db()
    manager = TagManager(db)

    fields = manager.get_all_fields()
    field = next((f for f in fields if f.name.lower() == field_name.lower()), None)

    if not field:
        print_error(f"Field not found: {field_name}")
        raise typer.Exit(1)

    if field.usage_count > 0 and not force:
        confirm = typer.confirm(f"Field '{field_name}' has {field.usage_count} values. Delete anyway?")
        if not confirm:
            print_info("Cancelled")
            return

    if manager.delete_field(field.id):
        print_success(f"Deleted field: {field_name}")
    else:
        print_error("Failed to delete field")


# ============================================================================
# Advanced Search Commands (cross-entity search)
# ============================================================================


@search_app.command("all")
def search_all(
    query: str = typer.Argument(..., help="Search query"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Scope: books, notes, quotes, reviews, collections, lists, tags, authors"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by book status"),
    genre: Optional[str] = typer.Option(None, "--genre", "-g", help="Filter by genre"),
    favorites: bool = typer.Option(False, "--favorites", "-f", help="Only favorites"),
) -> None:
    """Search across all content."""
    from .search import SearchManager, SearchQuery, SearchScope

    db = get_db()
    manager = SearchManager(db)

    # Parse scope
    scopes = [SearchScope.ALL]
    if scope:
        try:
            scopes = [SearchScope(s.strip()) for s in scope.split(",")]
        except ValueError:
            print_error(f"Invalid scope: {scope}")
            return

    search_query = SearchQuery(
        query=query,
        scope=scopes,
        limit=limit,
        book_status=status,
        genre=genre,
        favorites_only=favorites,
    )

    results = manager.search(search_query)

    if results.total_count == 0:
        print_info(f"No results found for '{query}'")
        return

    console.print(f"\n[bold]Found {results.total_count} results[/bold] ({results.search_time_ms:.1f}ms)\n")

    table = Table()
    table.add_column("Type", style="cyan", width=10)
    table.add_column("Title", width=30)
    table.add_column("Subtitle", width=20)
    table.add_column("Snippet", width=40)

    for r in results.results:
        table.add_row(
            r.result_type.value,
            r.title[:28] if len(r.title) > 28 else r.title,
            (r.subtitle or "")[:18] if r.subtitle else "",
            r.snippet[:38] + "..." if len(r.snippet) > 38 else r.snippet,
        )

    console.print(table)

    if results.has_more:
        console.print(f"\n[dim]Showing {len(results.results)} of {results.total_count} results[/dim]")


@search_app.command("books")
def search_books_cmd(
    query: str = typer.Argument(..., help="Search query"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    genre: Optional[str] = typer.Option(None, "--genre", "-g", help="Filter by genre"),
    min_rating: Optional[float] = typer.Option(None, "--rating", "-r", help="Minimum rating"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """Search books specifically."""
    from .search import SearchManager

    db = get_db()
    manager = SearchManager(db)

    results = manager.search_books(
        query=query,
        status=status,
        genre=genre,
        min_rating=min_rating,
        limit=limit,
    )

    if not results:
        print_info(f"No books found for '{query}'")
        return

    table = Table(title=f"Books matching '{query}'")
    table.add_column("Title", style="cyan")
    table.add_column("Author")
    table.add_column("Status")
    table.add_column("Rating")

    for r in results:
        table.add_row(
            r.title[:30],
            (r.author or "")[:20],
            r.status,
            f"{r.rating:.1f}" if r.rating else "",
        )

    console.print(table)


@search_app.command("notes")
def search_notes_cmd(
    query: str = typer.Argument(..., help="Search query"),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Filter by book"),
    note_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by note type"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """Search notes specifically."""
    from .search import SearchManager
    from .library import BookTracker

    db = get_db()
    manager = SearchManager(db)
    tracker = BookTracker(db)

    book_id = None
    if book:
        book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
        if isinstance(book_obj, list):
            book_obj = book_obj[0] if book_obj else None
        if book_obj:
            book_id = book_obj.id

    results = manager.search_notes(
        query=query,
        book_id=book_id,
        note_type=note_type,
        limit=limit,
    )

    if not results:
        print_info(f"No notes found for '{query}'")
        return

    table = Table(title=f"Notes matching '{query}'")
    table.add_column("Title")
    table.add_column("Book", style="cyan")
    table.add_column("Type")
    table.add_column("Snippet")

    for r in results:
        table.add_row(
            (r.title or "Note")[:20],
            r.book_title[:20],
            r.note_type,
            r.snippet[:40],
        )

    console.print(table)


@search_app.command("quotes")
def search_quotes_cmd(
    query: str = typer.Argument(..., help="Search query"),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Filter by book"),
    speaker: Optional[str] = typer.Option(None, "--speaker", "-s", help="Filter by speaker"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """Search quotes specifically."""
    from .search import SearchManager
    from .library import BookTracker

    db = get_db()
    manager = SearchManager(db)
    tracker = BookTracker(db)

    book_id = None
    if book:
        book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
        if isinstance(book_obj, list):
            book_obj = book_obj[0] if book_obj else None
        if book_obj:
            book_id = book_obj.id

    results = manager.search_quotes(
        query=query,
        book_id=book_id,
        speaker=speaker,
        limit=limit,
    )

    if not results:
        print_info(f"No quotes found for '{query}'")
        return

    table = Table(title=f"Quotes matching '{query}'")
    table.add_column("Quote")
    table.add_column("Book", style="cyan")
    table.add_column("Speaker")

    for r in results:
        table.add_row(
            r.text_snippet[:40],
            r.book_title[:20],
            (r.speaker or "")[:15],
        )

    console.print(table)


@search_app.command("deep")
def search_deep(
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Search in titles"),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Search by author"),
    content: Optional[str] = typer.Option(None, "--content", "-c", help="Search in content"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Search by tag"),
    must: Optional[str] = typer.Option(None, "--must", help="Must include (comma-separated)"),
    should: Optional[str] = typer.Option(None, "--should", help="Should include (comma-separated)"),
    exclude: Optional[str] = typer.Option(None, "--exclude", "-x", help="Must exclude (comma-separated)"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Scope: books, notes, quotes"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """Deep search across entities with boolean operators."""
    from .search import SearchManager, AdvancedSearchQuery, SearchScope

    db = get_db()
    manager = SearchManager(db)

    # Parse scope
    scopes = [SearchScope.ALL]
    if scope:
        try:
            scopes = [SearchScope(s.strip()) for s in scope.split(",")]
        except ValueError:
            print_error(f"Invalid scope: {scope}")
            return

    query = AdvancedSearchQuery(
        title=title,
        author=author,
        content=content,
        tag=tag,
        must_include=[t.strip() for t in must.split(",")] if must else [],
        should_include=[t.strip() for t in should.split(",")] if should else [],
        must_exclude=[t.strip() for t in exclude.split(",")] if exclude else [],
        scope=scopes,
        limit=limit,
    )

    results = manager.advanced_search(query)

    if results.total_count == 0:
        print_info("No results found")
        return

    console.print(f"\n[bold]Found {results.total_count} results[/bold] ({results.search_time_ms:.1f}ms)\n")

    table = Table()
    table.add_column("Type", style="cyan", width=10)
    table.add_column("Title", width=30)
    table.add_column("Subtitle", width=20)
    table.add_column("Snippet", width=40)

    for r in results.results:
        table.add_row(
            r.result_type.value,
            r.title[:28],
            (r.subtitle or "")[:18],
            r.snippet[:38],
        )

    console.print(table)


@search_app.command("suggest")
def search_suggest(
    query: str = typer.Argument(..., help="Partial query for suggestions"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max suggestions"),
) -> None:
    """Get search suggestions (autocomplete)."""
    from .search import SearchManager

    db = get_db()
    manager = SearchManager(db)

    suggestions = manager.get_suggestions(query, limit=limit)

    if not suggestions.suggestions:
        print_info("No suggestions found")
        return

    console.print(f"\n[bold]Suggestions for '{query}':[/bold]\n")

    for s in suggestions.suggestions:
        console.print(f"  [{s.result_type.value}] {s.text} ({s.count})")


# ============================================================================
# Location Commands
# ============================================================================

location_app = typer.Typer(help="Track reading locations.")
app.add_typer(location_app, name="location")


@location_app.command("create")
def location_create(
    name: str = typer.Argument(..., help="Location name"),
    location_type: str = typer.Option("other", "--type", "-t", help="Type: home, office, cafe, library, park, commute, beach, travel, bookstore, other"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
    address: Optional[str] = typer.Option(None, "--address", "-a", help="Address"),
    icon: Optional[str] = typer.Option(None, "--icon", help="Icon emoji"),
    favorite: bool = typer.Option(False, "--favorite", "-f", help="Mark as favorite"),
) -> None:
    """Create a reading location."""
    from .locations import LocationManager, LocationCreate, LocationType

    db = get_db()
    manager = LocationManager(db)

    try:
        loc_type = LocationType(location_type)
    except ValueError:
        print_error(f"Invalid location type: {location_type}")
        return

    data = LocationCreate(
        name=name,
        location_type=loc_type,
        description=description,
        address=address,
        icon=icon,
        is_favorite=favorite,
    )
    location = manager.create_location(data)

    print_success(f"Location '{location.name}' created (ID: {location.id})")


@location_app.command("list")
def location_list(
    location_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    favorites: bool = typer.Option(False, "--favorites", "-f", help="Only show favorites"),
) -> None:
    """List reading locations."""
    from .locations import LocationManager, LocationType

    db = get_db()
    manager = LocationManager(db)

    loc_type = None
    if location_type:
        try:
            loc_type = LocationType(location_type)
        except ValueError:
            print_error(f"Invalid location type: {location_type}")
            return

    locations = manager.list_locations(location_type=loc_type, favorites_only=favorites)

    if not locations:
        print_info("No locations found")
        return

    table = Table(title="Reading Locations")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Sessions", justify="right")
    table.add_column("Minutes", justify="right")
    table.add_column("Fav")

    for loc in locations:
        table.add_row(
            f"{loc.icon or ''} {loc.name}".strip(),
            loc.location_type,
            str(loc.total_sessions),
            str(loc.total_minutes),
            "★" if loc.is_favorite else "",
        )

    console.print(table)


@location_app.command("show")
def location_show(
    location: str = typer.Argument(..., help="Location name or ID"),
) -> None:
    """Show location details."""
    from .locations import LocationManager

    db = get_db()
    manager = LocationManager(db)

    loc = manager.get_location(location) or manager.get_location_by_name(location)
    if not loc:
        print_error("Location not found")
        return

    breakdown = manager.get_location_breakdown(loc.id)

    content = f"[bold]{loc.icon or ''} {loc.name}[/bold]"
    content += f"\nType: {loc.location_type}"
    if loc.description:
        content += f"\n{loc.description}"
    if loc.address:
        content += f"\nAddress: {loc.address}"

    content += f"\n\nTotal Sessions: {breakdown.total_sessions}"
    content += f"\nTotal Minutes: {breakdown.total_minutes}"
    content += f"\nTotal Pages: {breakdown.total_pages}"
    content += f"\nAvg Session: {breakdown.average_session_minutes:.1f} min"

    if breakdown.favorite_time_of_day:
        content += f"\nBest Time: {breakdown.favorite_time_of_day}"

    if breakdown.books_read_here:
        content += f"\n\nBooks Read Here ({len(breakdown.books_read_here)}):"
        for title in breakdown.books_read_here[:5]:
            content += f"\n  - {title}"

    console.print(Panel(content, title="[cyan]Location Details[/cyan]"))


@location_app.command("log")
def location_log(
    location: str = typer.Argument(..., help="Location name or ID"),
    minutes: int = typer.Argument(..., help="Minutes read"),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Book title or ID"),
    pages: int = typer.Option(0, "--pages", "-p", help="Pages read"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Session notes"),
) -> None:
    """Log a reading session at a location."""
    from .locations import LocationManager, LocationSessionCreate
    from .library import BookTracker

    db = get_db()
    manager = LocationManager(db)
    tracker = BookTracker(db)

    # Find location
    loc = manager.get_location(location) or manager.get_location_by_name(location)
    if not loc:
        print_error(f"Location not found: {location}")
        return

    # Find book if provided
    book_id = None
    book_title = None
    if book:
        book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
        if isinstance(book_obj, list):
            book_obj = book_obj[0] if book_obj else None
        if book_obj:
            book_id = book_obj.id
            book_title = book_obj.title

    try:
        data = LocationSessionCreate(
            location_id=loc.id,
            book_id=book_id,
            minutes_read=minutes,
            pages_read=pages,
            notes=notes,
        )
        session = manager.log_session(data)

        content = f"Logged {minutes} minutes at {loc.name}"
        if book_title:
            content += f"\nBook: {book_title}"
        if pages:
            content += f"\nPages: {pages}"

        console.print(Panel(content, title="[green]Session Logged[/green]"))
    except ValueError as e:
        print_error(str(e))


@location_app.command("sessions")
def location_sessions(
    location: Optional[str] = typer.Option(None, "--location", "-l", help="Filter by location"),
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Filter by book"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max sessions to show"),
) -> None:
    """List reading sessions."""
    from .locations import LocationManager
    from .library import BookTracker

    db = get_db()
    manager = LocationManager(db)
    tracker = BookTracker(db)

    location_id = None
    if location:
        loc = manager.get_location(location) or manager.get_location_by_name(location)
        if loc:
            location_id = loc.id

    book_id = None
    if book:
        book_obj = tracker.get_book(book) or tracker.search_books(book, limit=1)
        if isinstance(book_obj, list):
            book_obj = book_obj[0] if book_obj else None
        if book_obj:
            book_id = book_obj.id

    sessions = manager.list_sessions(
        location_id=location_id,
        book_id=book_id,
        limit=limit,
    )

    if not sessions:
        print_info("No sessions found")
        return

    table = Table(title="Reading Sessions")
    table.add_column("Date")
    table.add_column("Location", style="cyan")
    table.add_column("Book")
    table.add_column("Minutes", justify="right")
    table.add_column("Pages", justify="right")

    for s in sessions:
        table.add_row(
            s.session_date.strftime("%Y-%m-%d %H:%M"),
            s.location_name[:15],
            (s.book_title or "")[:20],
            str(s.minutes_read),
            str(s.pages_read) if s.pages_read else "",
        )

    console.print(table)


@location_app.command("stats")
def location_stats() -> None:
    """Show location statistics."""
    from .locations import LocationManager

    db = get_db()
    manager = LocationManager(db)

    stats = manager.get_stats()

    content = f"""Total Locations: {stats.total_locations}
Total Sessions: {stats.total_sessions}
Total Minutes: {stats.total_minutes}
Total Pages: {stats.total_pages}

Favorite Location: {stats.favorite_location or 'N/A'}
Most Used: {stats.most_used_location or 'N/A'}"""

    if stats.minutes_by_type:
        content += "\n\nMinutes by Type:"
        for loc_type, mins in sorted(stats.minutes_by_type.items(), key=lambda x: -x[1]):
            content += f"\n  {loc_type}: {mins}"

    console.print(Panel(content, title="[cyan]Location Statistics[/cyan]"))

    # Show reading by hour chart
    if any(stats.reading_by_hour.values()):
        console.print("\n[bold]Reading by Hour of Day:[/bold]")
        max_val = max(stats.reading_by_hour.values()) or 1
        for hour in range(24):
            mins = stats.reading_by_hour.get(hour, 0)
            bar_len = int((mins / max_val) * 20)
            bar = "█" * bar_len
            if mins > 0:
                console.print(f"  {hour:02d}:00 {bar} {mins}m")


@location_app.command("delete")
def location_delete(
    location: str = typer.Argument(..., help="Location name or ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a location."""
    from .locations import LocationManager

    db = get_db()
    manager = LocationManager(db)

    loc = manager.get_location(location) or manager.get_location_by_name(location)
    if not loc:
        print_error("Location not found")
        return

    if not force:
        if not typer.confirm(f"Delete location '{loc.name}' and all its sessions?"):
            return

    if manager.delete_location(loc.id):
        print_success("Location deleted")
    else:
        print_error("Failed to delete location")


# ============================================================================
# Settings Commands
# ============================================================================

settings_app = typer.Typer(help="Manage user settings and preferences.")
app.add_typer(settings_app, name="settings")


@settings_app.command("get")
def settings_get(
    setting: str = typer.Argument(..., help="Setting name (category.key or just key)"),
) -> None:
    """Get a setting value."""
    from .settings import SettingsManager, SettingCategory

    db = get_db()
    manager = SettingsManager(db)

    # Parse category.key format
    if "." in setting:
        cat_str, key = setting.split(".", 1)
        try:
            category = SettingCategory(cat_str)
        except ValueError:
            print_error(f"Invalid category: {cat_str}")
            return
    else:
        # Search for the setting across categories
        results = manager.search_settings(setting)
        if not results:
            print_error(f"Setting not found: {setting}")
            return
        if len(results) > 1:
            console.print(f"Multiple matches for '{setting}':")
            for r in results:
                console.print(f"  {r.category.value}.{r.key}")
            return
        result = results[0]
        console.print(f"\n[bold]{result.category.value}.{result.key}[/bold]")
        console.print(f"  Value: [cyan]{result.value}[/cyan]")
        console.print(f"  Default: {result.default_value}")
        if result.description:
            console.print(f"  {result.description}")
        return

    result = manager.get_setting(category, key)
    if not result:
        print_error(f"Setting not found: {setting}")
        return

    console.print(f"\n[bold]{result.category.value}.{result.key}[/bold]")
    console.print(f"  Value: [cyan]{result.value}[/cyan]")
    console.print(f"  Default: {result.default_value}")
    if result.description:
        console.print(f"  {result.description}")


@settings_app.command("set")
def settings_set(
    setting: str = typer.Argument(..., help="Setting name (category.key)"),
    value: str = typer.Argument(..., help="New value"),
) -> None:
    """Set a setting value."""
    from .settings import SettingsManager, SettingCategory, SettingUpdate

    db = get_db()
    manager = SettingsManager(db)

    if "." not in setting:
        print_error("Setting must be in format: category.key")
        return

    cat_str, key = setting.split(".", 1)
    try:
        category = SettingCategory(cat_str)
    except ValueError:
        print_error(f"Invalid category: {cat_str}. Options: {[c.value for c in SettingCategory]}")
        return

    try:
        update = SettingUpdate(category=category, key=key, value=value)
        result = manager.set_setting(update)
        print_success(f"Set {setting} = {result.value}")
    except ValueError as e:
        print_error(str(e))


@settings_app.command("list")
def settings_list(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
) -> None:
    """List settings."""
    from .settings import SettingsManager, SettingCategory

    db = get_db()
    manager = SettingsManager(db)

    if category:
        try:
            cat = SettingCategory(category)
            cat_settings = manager.get_category_settings(cat)

            table = Table(title=f"Settings: {cat.value}")
            table.add_column("Key", style="cyan")
            table.add_column("Value")
            table.add_column("Default")
            table.add_column("Description", max_width=30)

            for s in cat_settings.settings:
                table.add_row(s.key, s.value, s.default_value, s.description or "")

            console.print(table)
        except ValueError:
            print_error(f"Invalid category: {category}")
            print_info(f"Options: {[c.value for c in SettingCategory]}")
    else:
        # Show all categories
        for cat in SettingCategory:
            cat_settings = manager.get_category_settings(cat)

            console.print(f"\n[bold magenta]{cat.value.upper()}[/bold magenta]")
            for s in cat_settings.settings:
                modified = " *" if s.value != s.default_value else ""
                console.print(f"  {s.key}: [cyan]{s.value}[/cyan]{modified}")


@settings_app.command("reset")
def settings_reset(
    setting: Optional[str] = typer.Argument(None, help="Setting to reset (category.key)"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Reset entire category"),
    all_settings: bool = typer.Option(False, "--all", "-a", help="Reset all settings"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Reset settings to defaults."""
    from .settings import SettingsManager, SettingCategory

    db = get_db()
    manager = SettingsManager(db)

    if all_settings:
        if not force and not typer.confirm("Reset ALL settings to defaults?"):
            return
        manager.reset_all()
        print_success("All settings reset to defaults")
    elif category:
        try:
            cat = SettingCategory(category)
            if not force and not typer.confirm(f"Reset all {category} settings to defaults?"):
                return
            manager.reset_category(cat)
            print_success(f"Category '{category}' reset to defaults")
        except ValueError:
            print_error(f"Invalid category: {category}")
    elif setting:
        if "." not in setting:
            print_error("Setting must be in format: category.key")
            return
        cat_str, key = setting.split(".", 1)
        try:
            cat = SettingCategory(cat_str)
            result = manager.reset_setting(cat, key)
            print_success(f"Reset {setting} to default: {result.value}")
        except ValueError as e:
            print_error(str(e))
    else:
        print_error("Specify --all, --category, or a setting name")


@settings_app.command("search")
def settings_search(
    query: str = typer.Argument(..., help="Search query"),
) -> None:
    """Search settings by name or description."""
    from .settings import SettingsManager

    db = get_db()
    manager = SettingsManager(db)

    results = manager.search_settings(query)

    if not results:
        print_info(f"No settings matching '{query}'")
        return

    table = Table(title=f"Settings matching '{query}'")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_column("Description", max_width=40)

    for r in results:
        table.add_row(
            f"{r.category.value}.{r.key}",
            r.value,
            r.description or "",
        )

    console.print(table)


@settings_app.command("backup")
def settings_backup(
    name: str = typer.Argument(..., help="Backup name"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
) -> None:
    """Create a settings backup."""
    from .settings import SettingsManager

    db = get_db()
    manager = SettingsManager(db)

    backup = manager.create_backup(name, description)
    print_success(f"Created backup: {backup.name} (ID: {backup.id})")


@settings_app.command("backups")
def settings_backups() -> None:
    """List settings backups."""
    from .settings import SettingsManager

    db = get_db()
    manager = SettingsManager(db)

    backups = manager.list_backups()

    if not backups:
        print_info("No backups found")
        return

    table = Table(title="Settings Backups")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Created")

    for b in backups:
        table.add_row(
            str(b.id),
            b.name,
            (b.description or "")[:30],
            b.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


@settings_app.command("restore")
def settings_restore(
    backup_id: int = typer.Argument(..., help="Backup ID to restore"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Restore settings from a backup."""
    from .settings import SettingsManager

    db = get_db()
    manager = SettingsManager(db)

    if not force:
        if not typer.confirm("This will overwrite all current settings. Continue?"):
            return

    try:
        manager.restore_backup(backup_id)
        print_success("Settings restored from backup")
    except ValueError as e:
        print_error(str(e))


@settings_app.command("export")
def settings_export(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file"),
) -> None:
    """Export settings to JSON."""
    import json
    from .settings import SettingsManager

    db = get_db()
    manager = SettingsManager(db)

    export = manager.export_settings()
    json_data = export.model_dump_json(indent=2)

    if output:
        with open(output, "w") as f:
            f.write(json_data)
        print_success(f"Settings exported to {output}")
    else:
        console.print(json_data)


@settings_app.command("import")
def settings_import(
    input_file: str = typer.Argument(..., help="Input JSON file"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Import settings from JSON file."""
    import json
    from .settings import SettingsManager

    db = get_db()
    manager = SettingsManager(db)

    if not force:
        if not typer.confirm("This will overwrite all current settings. Continue?"):
            return

    try:
        with open(input_file, "r") as f:
            data = json.load(f)
        manager.import_settings(data)
        print_success("Settings imported successfully")
    except FileNotFoundError:
        print_error(f"File not found: {input_file}")
    except json.JSONDecodeError:
        print_error("Invalid JSON file")
    except ValueError as e:
        print_error(str(e))


# ============================================================================
# Version Command
# ============================================================================


@app.command()
def version() -> None:
    """Show version information."""
    from . import __version__

    console.print(f"booktracker version {__version__}")


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
