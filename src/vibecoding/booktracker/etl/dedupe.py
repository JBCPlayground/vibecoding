"""Deduplication logic for book imports.

Identifies duplicate books using:
1. ISBN matching (primary, most reliable)
2. Fuzzy title + author matching (fallback for books without ISBN)

Books are merged by combining data from all sources, with configurable
priority for conflicting fields.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from thefuzz import fuzz

from ..db.schemas import BookCreate, BookSource, BookStatus


class MatchType(str, Enum):
    """Type of duplicate match."""

    ISBN = "isbn"
    ISBN13 = "isbn13"
    FUZZY = "fuzzy"
    CALIBRE_ID = "calibre_id"
    GOODREADS_ID = "goodreads_id"


@dataclass
class DuplicateMatch:
    """Represents a potential duplicate match between books."""

    book1: BookCreate
    book2: BookCreate
    match_type: MatchType
    confidence: float  # 0.0 - 1.0
    matched_field: str  # The field that matched

    def __repr__(self) -> str:
        return (
            f"DuplicateMatch({self.book1.title!r} <-> {self.book2.title!r}, "
            f"type={self.match_type.value}, confidence={self.confidence:.2f})"
        )


@dataclass
class DedupeResult:
    """Result of deduplication process."""

    unique_books: list[BookCreate] = field(default_factory=list)
    merged_books: list[BookCreate] = field(default_factory=list)
    duplicates: list[DuplicateMatch] = field(default_factory=list)
    conflicts: list[DuplicateMatch] = field(default_factory=list)  # Need manual resolution


# Fuzzy matching thresholds
TITLE_MATCH_THRESHOLD = 90  # Minimum score for title match
AUTHOR_MATCH_THRESHOLD = 85  # Minimum score for author match
COMBINED_MATCH_THRESHOLD = 88  # Minimum combined score


def normalize_string(s: str) -> str:
    """Normalize string for comparison."""
    if not s:
        return ""
    # Lowercase, strip whitespace, remove common prefixes
    s = s.lower().strip()
    # Remove "the " prefix for better matching
    if s.startswith("the "):
        s = s[4:]
    # Remove punctuation variations
    for char in ".,;:!?'\"()-":
        s = s.replace(char, "")
    # Collapse whitespace
    return " ".join(s.split())


def match_isbn(book1: BookCreate, book2: BookCreate) -> Optional[DuplicateMatch]:
    """Check if two books match by ISBN."""
    # Check ISBN
    if book1.isbn and book2.isbn:
        if book1.isbn == book2.isbn:
            return DuplicateMatch(
                book1=book1,
                book2=book2,
                match_type=MatchType.ISBN,
                confidence=1.0,
                matched_field=f"isbn={book1.isbn}",
            )

    # Check ISBN-13
    if book1.isbn13 and book2.isbn13:
        if book1.isbn13 == book2.isbn13:
            return DuplicateMatch(
                book1=book1,
                book2=book2,
                match_type=MatchType.ISBN13,
                confidence=1.0,
                matched_field=f"isbn13={book1.isbn13}",
            )

    # Cross-check ISBN and ISBN-13
    if book1.isbn and book2.isbn13:
        # ISBN-10 to ISBN-13 comparison (last digits)
        if book1.isbn in book2.isbn13:
            return DuplicateMatch(
                book1=book1,
                book2=book2,
                match_type=MatchType.ISBN,
                confidence=0.95,
                matched_field=f"isbn={book1.isbn} in isbn13={book2.isbn13}",
            )

    if book1.isbn13 and book2.isbn:
        if book2.isbn in book1.isbn13:
            return DuplicateMatch(
                book1=book1,
                book2=book2,
                match_type=MatchType.ISBN,
                confidence=0.95,
                matched_field=f"isbn={book2.isbn} in isbn13={book1.isbn13}",
            )

    return None


def match_source_ids(book1: BookCreate, book2: BookCreate) -> Optional[DuplicateMatch]:
    """Check if two books match by source IDs (Calibre ID, Goodreads ID)."""
    # Check Goodreads ID
    if book1.goodreads_id and book2.goodreads_id:
        if book1.goodreads_id == book2.goodreads_id:
            return DuplicateMatch(
                book1=book1,
                book2=book2,
                match_type=MatchType.GOODREADS_ID,
                confidence=1.0,
                matched_field=f"goodreads_id={book1.goodreads_id}",
            )

    # Check Calibre UUID
    if book1.calibre_uuid and book2.calibre_uuid:
        if book1.calibre_uuid == book2.calibre_uuid:
            return DuplicateMatch(
                book1=book1,
                book2=book2,
                match_type=MatchType.CALIBRE_ID,
                confidence=1.0,
                matched_field=f"calibre_uuid={book1.calibre_uuid}",
            )

    # Check identifiers dict for goodreads ID
    b1_gr = book1.source_ids.get("goodreads") or (
        book1.identifiers.get("goodreads") if book1.identifiers else None
    )
    b2_gr = book2.source_ids.get("goodreads") or (
        book2.identifiers.get("goodreads") if book2.identifiers else None
    )
    if b1_gr and b2_gr and b1_gr == b2_gr:
        return DuplicateMatch(
            book1=book1,
            book2=book2,
            match_type=MatchType.GOODREADS_ID,
            confidence=1.0,
            matched_field=f"goodreads_id={b1_gr}",
        )

    return None


def match_fuzzy(book1: BookCreate, book2: BookCreate) -> Optional[DuplicateMatch]:
    """Check if two books match by fuzzy title + author comparison."""
    title1 = normalize_string(book1.title)
    title2 = normalize_string(book2.title)
    author1 = normalize_string(book1.author)
    author2 = normalize_string(book2.author)

    if not title1 or not title2 or not author1 or not author2:
        return None

    # Calculate similarity scores
    title_score = fuzz.ratio(title1, title2)
    author_score = fuzz.ratio(author1, author2)

    # Also try token sort ratio for titles with different word order
    title_token_score = fuzz.token_sort_ratio(title1, title2)
    title_score = max(title_score, title_token_score)

    # Check if scores meet thresholds
    if title_score >= TITLE_MATCH_THRESHOLD and author_score >= AUTHOR_MATCH_THRESHOLD:
        combined_score = (title_score + author_score) / 2
        if combined_score >= COMBINED_MATCH_THRESHOLD:
            return DuplicateMatch(
                book1=book1,
                book2=book2,
                match_type=MatchType.FUZZY,
                confidence=combined_score / 100.0,
                matched_field=f"title={title_score}%, author={author_score}%",
            )

    return None


def find_duplicates(
    books: list[BookCreate],
    existing_books: Optional[list[BookCreate]] = None,
) -> list[DuplicateMatch]:
    """Find all duplicate pairs in a list of books.

    Args:
        books: List of books to check for duplicates
        existing_books: Optional list of existing books to check against

    Returns:
        List of DuplicateMatch objects for all potential duplicates
    """
    duplicates = []
    all_books = books + (existing_books or [])

    # Build ISBN index for fast lookup
    isbn_index: dict[str, list[int]] = {}
    isbn13_index: dict[str, list[int]] = {}

    for i, book in enumerate(all_books):
        if book.isbn:
            isbn_index.setdefault(book.isbn, []).append(i)
        if book.isbn13:
            isbn13_index.setdefault(book.isbn13, []).append(i)

    # Find ISBN duplicates
    seen_pairs: set[tuple[int, int]] = set()

    for isbn, indices in isbn_index.items():
        if len(indices) > 1:
            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    idx1, idx2 = indices[i], indices[j]
                    pair = (min(idx1, idx2), max(idx1, idx2))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        duplicates.append(
                            DuplicateMatch(
                                book1=all_books[idx1],
                                book2=all_books[idx2],
                                match_type=MatchType.ISBN,
                                confidence=1.0,
                                matched_field=f"isbn={isbn}",
                            )
                        )

    for isbn13, indices in isbn13_index.items():
        if len(indices) > 1:
            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    idx1, idx2 = indices[i], indices[j]
                    pair = (min(idx1, idx2), max(idx1, idx2))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        duplicates.append(
                            DuplicateMatch(
                                book1=all_books[idx1],
                                book2=all_books[idx2],
                                match_type=MatchType.ISBN13,
                                confidence=1.0,
                                matched_field=f"isbn13={isbn13}",
                            )
                        )

    # Check source IDs for remaining books
    for i in range(len(all_books)):
        for j in range(i + 1, len(all_books)):
            pair = (i, j)
            if pair in seen_pairs:
                continue

            match = match_source_ids(all_books[i], all_books[j])
            if match:
                seen_pairs.add(pair)
                duplicates.append(match)
                continue

            # Fuzzy match for books without ISBN
            book1, book2 = all_books[i], all_books[j]
            if not book1.isbn and not book1.isbn13 and not book2.isbn and not book2.isbn13:
                match = match_fuzzy(book1, book2)
                if match:
                    seen_pairs.add(pair)
                    duplicates.append(match)

    return duplicates


def merge_book_records(
    books: list[BookCreate],
    priority_order: Optional[list[BookSource]] = None,
) -> BookCreate:
    """Merge multiple book records into one, combining data from all sources.

    Args:
        books: List of book records to merge (same book from different sources)
        priority_order: Priority order for conflicting scalar fields.
                       Default: [NOTION, GOODREADS, CALIBRE, MANUAL]

    Returns:
        Merged BookCreate with data from all sources
    """
    if not books:
        raise ValueError("Cannot merge empty list of books")

    if len(books) == 1:
        return books[0]

    # Default priority: Notion > Goodreads > Calibre > Manual
    if priority_order is None:
        priority_order = [
            BookSource.NOTION,
            BookSource.GOODREADS,
            BookSource.CALIBRE,
            BookSource.MANUAL,
            BookSource.OPENLIBRARY,
        ]

    # Sort books by priority
    def get_priority(book: BookCreate) -> int:
        for source in book.sources:
            if source in priority_order:
                return priority_order.index(source)
        return len(priority_order)

    sorted_books = sorted(books, key=get_priority)

    # Start with highest priority book
    base = sorted_books[0]

    # Collect all sources and source_ids
    all_sources = set()
    all_source_ids: dict[str, str] = {}
    all_identifiers: dict[str, str] = {}
    all_tags: set[str] = set()
    all_genres: set[str] = set()
    all_file_formats: set[str] = set()

    for book in books:
        all_sources.update(book.sources)
        all_source_ids.update(book.source_ids)
        if book.identifiers:
            all_identifiers.update(book.identifiers)
        if book.tags:
            all_tags.update(book.tags)
        if book.genres:
            all_genres.update(book.genres)
        if book.file_formats:
            all_file_formats.update(book.file_formats)

    # Build merged record, filling in missing fields from lower priority sources
    merged_data = base.model_dump()

    # Fields to merge (take first non-null value by priority)
    scalar_fields = [
        "title",
        "title_sort",
        "author",
        "author_sort",
        "status",
        "rating",
        "date_added",
        "date_started",
        "date_finished",
        "isbn",
        "isbn13",
        "page_count",
        "description",
        "cover",
        "cover_base64",
        "publisher",
        "series",
        "series_index",
        "publication_date",
        "publication_year",
        "original_publication_year",
        "language",
        "format",
        "file_size",
        "library_source",
        "amazon_url",
        "goodreads_url",
        "library_url",
        "comments",
        "progress",
        "read_next",
        "recommended_by",
        "goodreads_id",
        "additional_authors",
        "goodreads_avg_rating",
        "goodreads_shelves",
        "goodreads_shelf_positions",
        "review",
        "review_spoiler",
        "notes",
        "read_count",
        "owned_copies",
        "calibre_id",
        "calibre_uuid",
        "calibre_library",
        "custom_text",
        "library_hold_date",
        "library_due_date",
        "pickup_location",
        "renewals",
    ]

    for field_name in scalar_fields:
        if merged_data.get(field_name) is None:
            for book in sorted_books[1:]:
                book_data = book.model_dump()
                if book_data.get(field_name) is not None:
                    merged_data[field_name] = book_data[field_name]
                    break

    # Merge list/dict fields
    merged_data["sources"] = list(all_sources)
    merged_data["source_ids"] = all_source_ids
    merged_data["identifiers"] = all_identifiers
    merged_data["tags"] = list(all_tags)
    merged_data["genres"] = list(all_genres)
    merged_data["file_formats"] = list(all_file_formats)

    return BookCreate(**merged_data)


def deduplicate_books(
    books: list[BookCreate],
    existing_books: Optional[list[BookCreate]] = None,
    auto_merge_threshold: float = 0.95,
) -> DedupeResult:
    """Deduplicate a list of books, merging high-confidence duplicates.

    Args:
        books: List of books to deduplicate
        existing_books: Optional existing books to check against
        auto_merge_threshold: Confidence threshold for automatic merging

    Returns:
        DedupeResult with unique, merged, and conflicting books
    """
    result = DedupeResult()

    # Find all duplicates
    duplicates = find_duplicates(books, existing_books)

    # Group books by duplicate clusters
    # Build union-find structure
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Map books to indices
    all_books = books + (existing_books or [])
    book_to_idx = {id(book): i for i, book in enumerate(all_books)}

    # Union duplicate pairs
    for dup in duplicates:
        idx1 = book_to_idx[id(dup.book1)]
        idx2 = book_to_idx[id(dup.book2)]

        if dup.confidence >= auto_merge_threshold:
            union(idx1, idx2)
            result.duplicates.append(dup)
        else:
            result.conflicts.append(dup)

    # Group books by cluster
    clusters: dict[int, list[BookCreate]] = {}
    for i, book in enumerate(books):  # Only include new books
        root = find(i)
        clusters.setdefault(root, []).append(book)

    # Merge clusters
    for root, cluster_books in clusters.items():
        if len(cluster_books) == 1:
            result.unique_books.append(cluster_books[0])
        else:
            merged = merge_book_records(cluster_books)
            result.merged_books.append(merged)

    return result
