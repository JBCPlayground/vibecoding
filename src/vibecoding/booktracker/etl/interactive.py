"""Interactive UI for import preview and conflict resolution.

Uses Rich library for beautiful terminal output with side-by-side
comparison of duplicate books.
"""

from enum import Enum
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from ..db.schemas import BookCreate, BookSource
from .dedupe import DuplicateMatch, merge_book_records


class ConflictResolution(str, Enum):
    """User's choice for handling a duplicate."""

    MERGE = "merge"
    KEEP_FIRST = "keep_first"
    KEEP_SECOND = "keep_second"
    KEEP_BOTH = "keep_both"
    SKIP = "skip"


console = Console()


def _format_value(value) -> str:
    """Format a value for display."""
    if value is None:
        return "[dim]—[/dim]"
    if isinstance(value, list):
        if not value:
            return "[dim]—[/dim]"
        return ", ".join(str(v) for v in value[:5])
    if isinstance(value, dict):
        if not value:
            return "[dim]—[/dim]"
        return ", ".join(f"{k}:{v}" for k, v in list(value.items())[:3])
    if isinstance(value, bool):
        return "[green]Yes[/green]" if value else "[red]No[/red]"
    return str(value)[:50]


def _highlight_difference(val1, val2) -> tuple[str, str]:
    """Highlight values that differ between two books."""
    s1 = _format_value(val1)
    s2 = _format_value(val2)

    if val1 == val2:
        return s1, s2

    # Highlight different values
    if val1 is not None and val2 is None:
        return f"[green]{s1}[/green]", s2
    if val1 is None and val2 is not None:
        return s1, f"[green]{s2}[/green]"

    return f"[yellow]{s1}[/yellow]", f"[cyan]{s2}[/cyan]"


def show_book_comparison(
    book1: BookCreate,
    book2: BookCreate,
    match: Optional[DuplicateMatch] = None,
) -> None:
    """Display side-by-side comparison of two books.

    Args:
        book1: First book to compare
        book2: Second book to compare
        match: Optional match info showing why these are duplicates
    """
    # Create comparison table
    table = Table(title="Book Comparison", show_header=True, header_style="bold")
    table.add_column("Field", style="cyan", width=20)
    table.add_column(f"Book 1 ({', '.join(s.value for s in book1.sources)})", width=35)
    table.add_column(f"Book 2 ({', '.join(s.value for s in book2.sources)})", width=35)

    # Core fields to compare
    fields = [
        ("title", "Title"),
        ("author", "Author"),
        ("status", "Status"),
        ("rating", "Rating"),
        ("isbn", "ISBN"),
        ("isbn13", "ISBN-13"),
        ("page_count", "Pages"),
        ("date_added", "Date Added"),
        ("date_finished", "Date Finished"),
        ("publisher", "Publisher"),
        ("publication_year", "Year"),
        ("series", "Series"),
        ("format", "Format"),
        ("tags", "Tags"),
    ]

    for field_name, display_name in fields:
        val1 = getattr(book1, field_name, None)
        val2 = getattr(book2, field_name, None)
        s1, s2 = _highlight_difference(val1, val2)
        table.add_row(display_name, s1, s2)

    console.print(table)

    # Show match info if available
    if match:
        console.print(
            f"\n[bold]Match Type:[/bold] {match.match_type.value} "
            f"([green]{match.confidence:.0%}[/green] confidence)"
        )
        console.print(f"[bold]Matched on:[/bold] {match.matched_field}")


def resolve_conflict_interactive(
    match: DuplicateMatch,
    default: ConflictResolution = ConflictResolution.MERGE,
) -> tuple[ConflictResolution, Optional[BookCreate]]:
    """Interactively resolve a duplicate conflict.

    Args:
        match: The duplicate match to resolve
        default: Default resolution if user just presses enter

    Returns:
        Tuple of (resolution choice, merged book if applicable)
    """
    console.print("\n" + "=" * 60)
    console.print("[bold yellow]DUPLICATE DETECTED[/bold yellow]")
    console.print("=" * 60 + "\n")

    show_book_comparison(match.book1, match.book2, match)

    console.print("\n[bold]Options:[/bold]")
    console.print("  [cyan]1[/cyan] - Merge (combine data from both)")
    console.print("  [cyan]2[/cyan] - Keep first book only")
    console.print("  [cyan]3[/cyan] - Keep second book only")
    console.print("  [cyan]4[/cyan] - Keep both as separate entries")
    console.print("  [cyan]5[/cyan] - Skip both (don't import)")

    default_num = {
        ConflictResolution.MERGE: "1",
        ConflictResolution.KEEP_FIRST: "2",
        ConflictResolution.KEEP_SECOND: "3",
        ConflictResolution.KEEP_BOTH: "4",
        ConflictResolution.SKIP: "5",
    }[default]

    choice = Prompt.ask(
        "\nYour choice",
        choices=["1", "2", "3", "4", "5"],
        default=default_num,
    )

    resolution_map = {
        "1": ConflictResolution.MERGE,
        "2": ConflictResolution.KEEP_FIRST,
        "3": ConflictResolution.KEEP_SECOND,
        "4": ConflictResolution.KEEP_BOTH,
        "5": ConflictResolution.SKIP,
    }

    resolution = resolution_map[choice]
    merged_book = None

    if resolution == ConflictResolution.MERGE:
        merged_book = merge_book_records([match.book1, match.book2])
        console.print("\n[green]Books will be merged.[/green]")
        show_merged_preview(merged_book)
    elif resolution == ConflictResolution.KEEP_FIRST:
        merged_book = match.book1
        console.print("\n[green]Keeping first book.[/green]")
    elif resolution == ConflictResolution.KEEP_SECOND:
        merged_book = match.book2
        console.print("\n[green]Keeping second book.[/green]")
    elif resolution == ConflictResolution.KEEP_BOTH:
        console.print("\n[yellow]Both books will be imported separately.[/yellow]")
    else:
        console.print("\n[red]Both books will be skipped.[/red]")

    return resolution, merged_book


def show_merged_preview(book: BookCreate) -> None:
    """Show preview of a merged book."""
    table = Table(title="Merged Book Preview", show_header=True)
    table.add_column("Field", style="cyan", width=20)
    table.add_column("Value", width=50)

    fields = [
        ("title", "Title"),
        ("author", "Author"),
        ("status", "Status"),
        ("rating", "Rating"),
        ("isbn", "ISBN"),
        ("page_count", "Pages"),
        ("sources", "Sources"),
    ]

    for field_name, display_name in fields:
        value = getattr(book, field_name, None)
        table.add_row(display_name, _format_value(value))

    console.print(table)


def show_import_preview(
    books: list[BookCreate],
    duplicates_count: int = 0,
    conflicts_count: int = 0,
) -> bool:
    """Show preview of books to be imported and confirm.

    Args:
        books: List of books that will be imported
        duplicates_count: Number of auto-merged duplicates
        conflicts_count: Number of conflicts requiring resolution

    Returns:
        True if user confirms import, False otherwise
    """
    console.print("\n" + "=" * 60)
    console.print("[bold]IMPORT PREVIEW[/bold]")
    console.print("=" * 60 + "\n")

    # Summary stats
    stats_table = Table(show_header=False, box=None)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Count", justify="right")

    stats_table.add_row("Books to import:", f"[green]{len(books)}[/green]")
    stats_table.add_row("Auto-merged duplicates:", f"[yellow]{duplicates_count}[/yellow]")
    stats_table.add_row("Conflicts to resolve:", f"[red]{conflicts_count}[/red]")

    console.print(stats_table)

    # Show source breakdown
    source_counts: dict[str, int] = {}
    for book in books:
        for source in book.sources:
            source_counts[source.value] = source_counts.get(source.value, 0) + 1

    if source_counts:
        console.print("\n[bold]By Source:[/bold]")
        for source, count in sorted(source_counts.items()):
            console.print(f"  {source}: {count}")

    # Show status breakdown
    status_counts: dict[str, int] = {}
    for book in books:
        status_counts[book.status.value] = status_counts.get(book.status.value, 0) + 1

    if status_counts:
        console.print("\n[bold]By Status:[/bold]")
        for status, count in sorted(status_counts.items()):
            console.print(f"  {status}: {count}")

    # Show sample of books
    console.print("\n[bold]Sample Books:[/bold]")
    sample_table = Table(show_header=True)
    sample_table.add_column("Title", width=30)
    sample_table.add_column("Author", width=20)
    sample_table.add_column("Status", width=12)
    sample_table.add_column("Source", width=15)

    for book in books[:10]:
        sources = ", ".join(s.value for s in book.sources)
        sample_table.add_row(
            book.title[:30],
            book.author[:20],
            book.status.value,
            sources,
        )

    if len(books) > 10:
        sample_table.add_row(f"... and {len(books) - 10} more", "", "", "")

    console.print(sample_table)

    # Confirm
    console.print()
    return Confirm.ask("Proceed with import?", default=True)


def show_import_results(
    imported: int,
    skipped: int,
    errors: list[tuple[str, str]],
) -> None:
    """Show results after import completes.

    Args:
        imported: Number of books successfully imported
        skipped: Number of books skipped
        errors: List of (title, error_message) tuples
    """
    console.print("\n" + "=" * 60)
    console.print("[bold]IMPORT COMPLETE[/bold]")
    console.print("=" * 60 + "\n")

    if imported > 0:
        console.print(f"[green]Successfully imported: {imported} books[/green]")

    if skipped > 0:
        console.print(f"[yellow]Skipped: {skipped} books[/yellow]")

    if errors:
        console.print(f"\n[red]Errors: {len(errors)} books[/red]")
        error_table = Table(show_header=True, title="Import Errors")
        error_table.add_column("Title", width=30)
        error_table.add_column("Error", width=40)

        for title, error in errors[:20]:
            error_table.add_row(title[:30], error[:40])

        if len(errors) > 20:
            error_table.add_row(f"... and {len(errors) - 20} more errors", "")

        console.print(error_table)


def show_dry_run_results(
    books: list[BookCreate],
    duplicates: list[DuplicateMatch],
    conflicts: list[DuplicateMatch],
) -> None:
    """Show results of a dry-run import.

    Args:
        books: Books that would be imported
        duplicates: Auto-merged duplicates
        conflicts: Conflicts requiring resolution
    """
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]DRY RUN RESULTS[/bold cyan]")
    console.print("[dim]No changes were made to the database[/dim]")
    console.print("=" * 60 + "\n")

    console.print(f"[bold]Would import:[/bold] {len(books)} books")
    console.print(f"[bold]Would auto-merge:[/bold] {len(duplicates)} duplicate pairs")
    console.print(f"[bold]Would need resolution:[/bold] {len(conflicts)} conflicts")

    if duplicates:
        console.print("\n[bold yellow]Auto-merge Duplicates:[/bold yellow]")
        for i, dup in enumerate(duplicates[:5], 1):
            console.print(
                f"  {i}. {dup.book1.title!r} = {dup.book2.title!r} "
                f"({dup.match_type.value}, {dup.confidence:.0%})"
            )
        if len(duplicates) > 5:
            console.print(f"  ... and {len(duplicates) - 5} more")

    if conflicts:
        console.print("\n[bold red]Conflicts Requiring Resolution:[/bold red]")
        for i, conflict in enumerate(conflicts[:5], 1):
            console.print(
                f"  {i}. {conflict.book1.title!r} vs {conflict.book2.title!r} "
                f"({conflict.match_type.value}, {conflict.confidence:.0%})"
            )
        if len(conflicts) > 5:
            console.print(f"  ... and {len(conflicts) - 5} more")
