"""Transform raw CSV data to unified BookCreate schema.

Each transformer maps source-specific columns to the unified schema,
handling data cleaning, type conversion, and status normalization.
"""

from datetime import date, datetime
from typing import Any, Optional

from ..db.schemas import BookCreate, BookSource, BookStatus


class TransformError(Exception):
    """Raised when transformation fails."""

    pass


# Status mappings for each source
NOTION_STATUS_MAP = {
    "read": BookStatus.COMPLETED,
    "skimmed": BookStatus.SKIMMED,
    "borrowed": BookStatus.READING,  # Currently borrowed = reading
    "want to read": BookStatus.WISHLIST,
    "on hold": BookStatus.ON_HOLD,
    "": BookStatus.WISHLIST,
}

GOODREADS_STATUS_MAP = {
    "read": BookStatus.COMPLETED,
    "currently-reading": BookStatus.READING,
    "to-read": BookStatus.WISHLIST,
    "": BookStatus.WISHLIST,
}

# Calibre books are owned ebooks, status based on tags
CALIBRE_STATUS_MAP = {
    "ripped": BookStatus.OWNED,
    "acquired": BookStatus.OWNED,
    "": BookStatus.OWNED,
}


def _clean_isbn(value: str) -> Optional[str]:
    """Clean ISBN value, handling Goodreads ="" wrapper."""
    if not value:
        return None
    value = str(value).strip()
    # Handle Goodreads format: ="0385350597"
    if value.startswith('="') and value.endswith('"'):
        value = value[2:-1]
    # Remove any remaining quotes
    value = value.strip('"').strip("'")
    return value if value else None


def _parse_date(value: str) -> Optional[date]:
    """Parse date from various formats."""
    if not value or value.strip() == "":
        return None

    value = str(value).strip()

    # Try common date formats
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def _parse_int(value: str) -> Optional[int]:
    """Parse integer, returning None for invalid values."""
    if not value or value.strip() == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _parse_float(value: str) -> Optional[float]:
    """Parse float, returning None for invalid values."""
    if not value or value.strip() == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_rating(value: str, scale_max: int = 5) -> Optional[int]:
    """Parse rating, normalizing to 1-5 scale.

    Args:
        value: Raw rating value
        scale_max: Maximum value of source scale (5 for Goodreads/Notion, 10 for Calibre)

    Returns:
        Rating on 1-5 scale, or None if unrated
    """
    rating = _parse_int(value)
    if rating is None or rating == 0:
        return None

    if scale_max == 10:
        # Calibre uses 0-10 scale
        rating = max(1, min(5, rating // 2))

    return max(1, min(5, rating))


def _parse_list(value: str, separator: str = ",") -> list[str]:
    """Parse comma-separated list."""
    if not value or value.strip() == "":
        return []
    return [item.strip() for item in str(value).split(separator) if item.strip()]


def _parse_identifiers(value: str) -> dict[str, str]:
    """Parse Calibre identifiers format: key:value,key:value."""
    if not value or value.strip() == "":
        return {}

    result = {}
    for pair in str(value).split(","):
        if ":" in pair:
            key, val = pair.split(":", 1)
            result[key.strip()] = val.strip()
    return result


def transform_notion_row(raw: dict[str, Any]) -> BookCreate:
    """Transform Notion CSV row to BookCreate schema.

    Notion field mappings:
    - Title -> title
    - Author -> author
    - Author (L,F) -> author_sort
    - Title (Sort) -> title_sort
    - Status -> status (mapped via NOTION_STATUS_MAP)
    - Rating -> rating
    - Added -> date_added
    - Date Started -> date_started
    - Date Finished -> date_finished
    - ISBN -> isbn
    - ISBN-13 -> isbn13
    - Pages -> page_count
    - Description -> description
    - Image -> cover
    - Publisher -> publisher
    - Publish Year -> publication_year
    - Book Series -> series
    - Series Index -> series_index
    - Formats -> format
    - Library -> library_source
    - Amazon URL -> amazon_url
    - Goodreads URL -> goodreads_url
    - FCPL URL -> library_url
    - Comments -> comments
    - Progress -> progress
    - Read Next -> read_next
    - Recommended By -> recommended_by
    - Tags -> tags
    - Genres -> genres
    """
    # Map status
    raw_status = str(raw.get("Status", "")).lower().strip()
    status = NOTION_STATUS_MAP.get(raw_status, BookStatus.WISHLIST)

    # Parse read_next checkbox
    read_next_raw = str(raw.get("Read Next", "")).lower().strip()
    read_next = read_next_raw in ("true", "yes", "1", "checked")

    # Parse tags and genres (may be comma-separated or JSON)
    tags = _parse_list(raw.get("Tags", ""))
    genres = _parse_list(raw.get("Genres", ""))

    return BookCreate(
        title=str(raw.get("Title", "")).strip(),
        title_sort=raw.get("Title (Sort)", "") or None,
        author=str(raw.get("Author", "")).strip(),
        author_sort=raw.get("Author (L,F)", "") or None,
        status=status,
        rating=_parse_rating(raw.get("Rating", "")),
        date_added=_parse_date(raw.get("Added", "")),
        date_started=_parse_date(raw.get("Date Started", "")),
        date_finished=_parse_date(raw.get("Date Finished", "")),
        isbn=_clean_isbn(raw.get("ISBN", "")),
        isbn13=_clean_isbn(raw.get("ISBN-13", "")),
        page_count=_parse_int(raw.get("Pages", "")),
        description=raw.get("Description", "") or None,
        cover=raw.get("Image", "") or None,
        publisher=raw.get("Publisher", "") or None,
        publication_year=_parse_int(raw.get("Publish Year", "")),
        series=raw.get("Book Series", "") or None,
        series_index=_parse_float(raw.get("Series Index", "")),
        format=raw.get("Formats", "") or None,
        library_source=raw.get("Library", "") or None,
        amazon_url=raw.get("Amazon URL", "") or None,
        goodreads_url=raw.get("Goodreads URL", "") or None,
        library_url=raw.get("FCPL URL", "") or None,
        comments=raw.get("Comments", "") or None,
        progress=raw.get("Progress", "") or None,
        read_next=read_next,
        recommended_by=raw.get("Recommended By", "") or None,
        tags=tags,
        genres=genres,
        sources=[BookSource.NOTION],
        source_ids={},
    )


def transform_calibre_row(raw: dict[str, Any]) -> BookCreate:
    """Transform Calibre CSV row to BookCreate schema.

    Calibre field mappings:
    - title -> title
    - title_sort -> title_sort
    - authors -> author
    - author_sort -> author_sort
    - rating -> rating (0-10 scale, normalize to 1-5)
    - timestamp -> date_added
    - pubdate -> publication_date
    - publisher -> publisher
    - series -> series
    - series_index -> series_index
    - tags -> tags
    - formats -> file_formats
    - uuid -> calibre_uuid
    - id -> calibre_id
    - size -> file_size
    - library_name -> calibre_library
    - languages -> language
    - identifiers -> identifiers
    - isbn -> isbn
    - comments -> description
    - cover -> cover
    - #text -> custom_text
    """
    # Determine status from tags
    tags_raw = str(raw.get("tags", "")).lower()
    status = BookStatus.OWNED  # Default for Calibre
    for tag, mapped_status in CALIBRE_STATUS_MAP.items():
        if tag and tag in tags_raw:
            status = mapped_status
            break

    # Parse identifiers
    identifiers = _parse_identifiers(raw.get("identifiers", ""))

    # Extract ISBN from identifiers if not in isbn field
    isbn = _clean_isbn(raw.get("isbn", ""))
    if not isbn and "isbn" in identifiers:
        isbn = identifiers["isbn"]

    # Parse file formats
    file_formats = _parse_list(raw.get("formats", ""))

    # Parse tags
    tags = _parse_list(raw.get("tags", ""))

    return BookCreate(
        title=str(raw.get("title", "")).strip(),
        title_sort=raw.get("title_sort", "") or None,
        author=str(raw.get("authors", "")).strip(),
        author_sort=raw.get("author_sort", "") or None,
        status=status,
        rating=_parse_rating(raw.get("rating", ""), scale_max=10),
        date_added=_parse_date(raw.get("timestamp", "")),
        publication_date=_parse_date(raw.get("pubdate", "")),
        publisher=raw.get("publisher", "") or None,
        series=raw.get("series", "") or None,
        series_index=_parse_float(raw.get("series_index", "")),
        tags=tags,
        file_formats=file_formats,
        calibre_uuid=raw.get("uuid", "") or None,
        calibre_id=_parse_int(raw.get("id", "")),
        file_size=_parse_int(raw.get("size", "")),
        calibre_library=raw.get("library_name", "") or None,
        language=raw.get("languages", "") or None,
        identifiers=identifiers,
        isbn=isbn,
        description=raw.get("comments", "") or None,
        cover=raw.get("cover", "") or None,
        custom_text=raw.get("#text", "") or None,
        sources=[BookSource.CALIBRE],
        source_ids={"calibre": str(raw.get("id", ""))} if raw.get("id") else {},
    )


def transform_goodreads_row(raw: dict[str, Any]) -> BookCreate:
    """Transform Goodreads CSV row to BookCreate schema.

    Goodreads field mappings:
    - Title -> title
    - Author -> author
    - Author l-f -> author_sort
    - Additional Authors -> additional_authors
    - ISBN -> isbn (strip ="" wrapper)
    - ISBN13 -> isbn13 (strip ="" wrapper)
    - My Rating -> rating
    - Average Rating -> goodreads_avg_rating
    - Publisher -> publisher
    - Binding -> format
    - Number of Pages -> page_count
    - Year Published -> publication_year
    - Original Publication Year -> original_publication_year
    - Date Read -> date_finished
    - Date Added -> date_added
    - Bookshelves -> goodreads_shelves
    - Bookshelves with positions -> goodreads_shelf_positions
    - Exclusive Shelf -> status (mapped via GOODREADS_STATUS_MAP)
    - My Review -> review
    - Spoiler -> review_spoiler
    - Private Notes -> notes
    - Read Count -> read_count
    - Owned Copies -> owned_copies
    - Book Id -> goodreads_id
    """
    # Map status from Exclusive Shelf
    raw_status = str(raw.get("Exclusive Shelf", "")).lower().strip()
    status = GOODREADS_STATUS_MAP.get(raw_status, BookStatus.WISHLIST)

    return BookCreate(
        title=str(raw.get("Title", "")).strip(),
        author=str(raw.get("Author", "")).strip(),
        author_sort=raw.get("Author l-f", "") or None,
        status=status,
        rating=_parse_rating(raw.get("My Rating", "")),
        date_added=_parse_date(raw.get("Date Added", "")),
        date_finished=_parse_date(raw.get("Date Read", "")),
        isbn=_clean_isbn(raw.get("ISBN", "")),
        isbn13=_clean_isbn(raw.get("ISBN13", "")),
        page_count=_parse_int(raw.get("Number of Pages", "")),
        publisher=raw.get("Publisher", "") or None,
        publication_year=_parse_int(raw.get("Year Published", "")),
        original_publication_year=_parse_int(raw.get("Original Publication Year", "")),
        format=raw.get("Binding", "") or None,
        additional_authors=raw.get("Additional Authors", "") or None,
        goodreads_id=_parse_int(raw.get("Book Id", "")),
        goodreads_avg_rating=_parse_float(raw.get("Average Rating", "")),
        goodreads_shelves=raw.get("Bookshelves", "") or None,
        goodreads_shelf_positions=raw.get("Bookshelves with positions", "") or None,
        review=raw.get("My Review", "") or None,
        review_spoiler=raw.get("Spoiler", "") or None,
        notes=raw.get("Private Notes", "") or None,
        read_count=_parse_int(raw.get("Read Count", "")),
        owned_copies=_parse_int(raw.get("Owned Copies", "")),
        sources=[BookSource.GOODREADS],
        source_ids=(
            {"goodreads": str(raw.get("Book Id", ""))} if raw.get("Book Id") else {}
        ),
    )


def transform_row(extracted: dict) -> BookCreate:
    """Transform an extracted row based on its source.

    Args:
        extracted: Dictionary with 'source' and 'raw' keys from extract module

    Returns:
        BookCreate schema instance
    """
    source = extracted["source"]
    raw = extracted["raw"]

    if source == "notion":
        return transform_notion_row(raw)
    elif source == "calibre":
        return transform_calibre_row(raw)
    elif source == "goodreads":
        return transform_goodreads_row(raw)
    else:
        raise TransformError(f"Unknown source: {source}")
