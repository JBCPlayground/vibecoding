# Product Requirements Document: Notion Book Tracker

## Overview

A Notion-integrated application for tracking personal reading activity, including books read, library holds, and wishlist items.

## Problem Statement

Readers need a centralized way to:
- Track books they've finished reading with ratings and notes
- Monitor library holds and due dates
- Maintain a wishlist of books to read in the future
- Get insights into their reading habits

---

## Design Decisions (from Requirements Interview)

### Architecture

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Primary Storage** | Local SQLite + Notion | Offline-first with cloud sync |
| **Source of Truth** | Notion (authoritative) | Local is cache; Notion wins on conflicts |
| **Sync Strategy** | Periodic re-import | Monthly CSV exports from Goodreads/Calibre |
| **Offline Mode** | Full local database | All reads from SQLite, explicit sync to Notion |
| **Backup Location** | OneDrive | SQLite file synced via OneDrive |

### Data Handling

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Duplicate Resolution** | Interactive review | Pause and show conflicts for manual decision |
| **Validation Errors** | Skip and report | Continue import, generate error report |
| **New Book Status** | Keep source status | Goodreads to-read → wishlist, etc. |
| **Re-reads** | Reading log relations | One book → multiple reading sessions |
| **Audiobooks** | Same entry, format field | One record per title, format distinguishes |
| **Cover Images** | Notion file uploads | Upload to Notion for offline access |

### User Experience

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Primary Workflow** | Notion-centric | CLI for imports/exports, Notion for browsing |
| **Book Entry Method** | Title search | Search by title/author, pick from results |
| **CLI Output** | Rich tables | Colorful formatted tables with borders |
| **Notifications** | Notion reminders | Use Notion's built-in reminder system |
| **Metadata API** | Open Library | Free, no API key, open source friendly |

### Safety & Performance

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Pre-Import Backup** | Prompt user | Ask before import, allow skipping |
| **Dry-Run Mode** | Essential | Must preview all changes before committing |
| **API Rate Limits** | Very concerned | Aggressive caching, minimize API calls |
| **Data Volume** | 500-2000 books | Medium collection, batch processing needed |
| **Top Risk** | Data loss | Primary concern during migration |

### Schema & Display

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Notion Fields** | Curated + hidden | ~15 visible fields, rest hidden |
| **Visible Fields** | Reading-focused | Title, Author, Status, Rating, Dates, Progress, Cover, Series |
| **Reading Logs** | Essential | Track individual sessions with location |
| **Reading Location** | Track it | Home, commute, vacation, etc. |
| **Recommended By** | Nice to have | Optional field, fill when remembered |

### Environment

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **CLI Platform** | Desktop terminal | macOS/Linux/WSL terminal |
| **Calibre Setup** | Single library | One library with all ebooks |
| **Multi-user** | Personal only | Single user, no sharing needed |
| **Library Integration** | Manual status only | Track dates manually, no FCPL API |

---

## Implementation Decisions (from Technical Review)

### Data Flow

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Write Flow** | SQLite-first | Write to SQLite immediately, queue for Notion sync later |
| **SQLite Schema** | All 50+ fields | Complete mirror of Notion for full offline access |
| **Add Book Sync** | Queue for sync | Add to SQLite only, batch sync later with `booktracker sync` |
| **Sync Failures** | Retry with backoff | Auto-retry failed syncs with exponential backoff (1s, 2s, 4s...) |
| **Edit Conflicts** | Warn and skip | Detect conflict, warn user, don't sync until manually resolved |

### Identity & Deduplication

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Book Identity** | ISBN as primary key | ISBN is canonical; books without ISBN get generated UUID |
| **No-ISBN Dedup** | Fuzzy + confirm | Fuzzy match on title+author, always prompt user to confirm |
| **Re-import Matching** | Source IDs tracked | Store Goodreads ID, Calibre UUID for future re-imports |

### User Interface

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Conflict UI** | Side-by-side diff | Show both versions in columns, highlight differences |
| **Search Results** | Top 10 | Show 10 Open Library matches - good balance |
| **Quick Mode** | No, always confirm | Every add shows preview and requires confirmation |
| **Reading Logs** | Separate Notion DB | Dedicated database with relation to Books |

### Technical Infrastructure

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Migrations** | Alembic | Industry-standard SQLAlchemy migrations |
| **Calibre Covers** | Base64 in SQLite | Store as base64 for offline, upload to Notion on sync |
| **Test Coverage** | Comprehensive | Unit tests for all modules, integration tests, mock Notion API |
| **Start Phase** | Phase 0 first | Build SQLite + CLI foundation before ETL |

## Goals

1. Create a Notion database structure optimized for book tracking
2. Build a Python CLI tool to interact with the Notion database
3. Enable quick book entry with automatic metadata lookup (via ISBN or title)
4. Provide reading statistics and insights

## User Stories

- As a reader, I want to add books quickly by ISBN or title so I don't have to enter all details manually
- As a reader, I want to track my reading progress and status (reading, completed, on-hold, wishlist)
- As a library user, I want to track hold dates and due dates so I never miss a pickup or return
- As a reader, I want to rate and review books I've finished
- As a reader, I want to see my reading statistics (books per month, favorite genres, etc.)

## Book Data Model

### Core Fields
| Field | Type | Description |
|-------|------|-------------|
| Title | Text | Book title |
| Author | Text | Author name(s) |
| Status | Select | `Reading`, `Completed`, `On Hold`, `Wishlist`, `DNF` |
| Rating | Number (1-5) | Personal rating after completion |
| Date Started | Date | When you started reading |
| Date Finished | Date | When you completed the book |

### Library Fields
| Field | Type | Description |
|-------|------|-------------|
| Library Hold Date | Date | When the hold was placed |
| Library Due Date | Date | Return deadline |
| Pickup Location | Text | Library branch |
| Renewals | Number | Times renewed |

### Metadata Fields
| Field | Type | Description |
|-------|------|-------------|
| ISBN | Text | ISBN-10 or ISBN-13 |
| Genre | Multi-select | Book categories |
| Page Count | Number | Total pages |
| Cover | URL/File | Book cover image |
| Notes | Text | Personal notes/review |
| Source | Select | `Library`, `Owned`, `Ebook`, `Audiobook` |

## Technical Architecture

### Components

1. **Local SQLite Database** - Primary storage, offline-first reads/writes
2. **Notion Database** - Authoritative cloud storage, sync target
3. **Python CLI** - Command-line interface for all operations
4. **Open Library API** - Book metadata auto-fill (free, no API key)
5. **OneDrive Sync** - SQLite backup via cloud folder

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Workflow                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐                     │
│   │Goodreads│    │ Calibre │    │  Notion │  ◄── Primary UI     │
│   │  .csv   │    │  .csv   │    │   UI    │      for browsing   │
│   └────┬────┘    └────┬────┘    └────┬────┘                     │
│        │              │              │                           │
│        └──────────────┼──────────────┘                           │
│                       │                                          │
│                       ▼                                          │
│              ┌────────────────┐                                  │
│              │  CLI (typer)   │  ◄── Imports, exports, stats    │
│              │  Rich tables   │                                  │
│              └───────┬────────┘                                  │
│                      │                                           │
│         ┌────────────┼────────────┐                              │
│         ▼            ▼            ▼                              │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│   │  Local   │ │  Notion  │ │  Open    │                        │
│   │  SQLite  │ │   API    │ │ Library  │                        │
│   │ (cache)  │ │ (master) │ │   API    │                        │
│   └────┬─────┘ └──────────┘ └──────────┘                        │
│        │                                                         │
│        ▼                                                         │
│   ┌──────────┐                                                   │
│   │ OneDrive │  ◄── Automatic backup                            │
│   │  Sync    │                                                   │
│   └──────────┘                                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Sync Flow

```
READ Operations:
  CLI → SQLite (local) → Return data
  (Instant, works offline)

WRITE Operations:
  CLI → SQLite (local) → Add to sync_queue table
  (Instant, queued for later sync)

SYNC Operations (explicit `booktracker sync`):
  1. Check for edit conflicts (same book edited locally AND in Notion)
     → If conflict: WARN and SKIP that book (manual resolution needed)
  2. Push queued local changes to Notion
     → On API failure: Retry with exponential backoff (1s, 2s, 4s, 8s, max 5 retries)
  3. Pull Notion changes (Notion wins for non-conflicting records)
  4. Update local SQLite
  5. Clear sync_queue for successful items

CONFLICT DETECTION:
  - Track `local_modified_at` and `notion_modified_at` timestamps
  - Conflict = both changed since last sync
  - Resolution: User must choose via `booktracker resolve <book>`
```

### Tech Stack
- Python 3.10+
- `notion-client` - Official Notion SDK
- `requests` - API calls for book metadata
- `typer` - CLI framework
- `rich` - Terminal formatting (colorful tables)
- `pandas` - CSV parsing and data manipulation (ETL)
- `pydantic` - Data validation and schema models (ETL)
- `thefuzz` - Fuzzy string matching for deduplication (ETL)
- `isbnlib` - ISBN validation and metadata lookup (ETL)
- `sqlite3` - Local database (Python stdlib)

### Project Structure
```
src/vibecoding/
├── booktracker/
│   ├── __init__.py
│   ├── cli.py             # CLI commands (typer)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── sqlite.py      # Local SQLite operations
│   │   ├── models.py      # SQLAlchemy ORM models
│   │   └── schemas.py     # Pydantic validation models
│   ├── sync/
│   │   ├── __init__.py
│   │   ├── notion.py      # Notion API wrapper
│   │   ├── conflict.py    # Conflict detection & resolution
│   │   └── queue.py       # Pending sync queue
│   ├── etl/
│   │   ├── __init__.py
│   │   ├── extract.py     # CSV parsers for each source
│   │   ├── transform.py   # Schema mapping & normalization
│   │   ├── dedupe.py      # Duplicate detection & merging
│   │   ├── load.py        # SQLite + Notion bulk loader
│   │   └── interactive.py # Side-by-side conflict UI
│   ├── api/
│   │   ├── __init__.py
│   │   └── openlibrary.py # Open Library API client
│   ├── config.py          # Configuration management
│   └── backup.py          # Backup/export utilities
├── alembic/
│   ├── versions/          # Migration scripts
│   ├── env.py
│   └── alembic.ini
├── tests/
│   ├── __init__.py
│   ├── conftest.py        # Shared fixtures (mock Notion API, test DB)
│   ├── test_db/
│   │   ├── test_models.py
│   │   └── test_sqlite.py
│   ├── test_etl/
│   │   ├── test_extract.py
│   │   ├── test_transform.py
│   │   └── test_dedupe.py
│   ├── test_sync/
│   │   ├── test_notion.py
│   │   └── test_conflict.py
│   └── test_cli.py
├── data/
│   └── books.db           # SQLite database (in OneDrive folder)
```

## CLI Commands

### Book Management
```bash
# Search and add a book (primary method - interactive title search)
booktracker add "The Great Gatsby"
# → Shows search results from Open Library
# → Pick from list, auto-fills metadata

# Add by ISBN (alternative)
booktracker add --isbn 9780143127741

# Update book status
booktracker update "The Great Gatsby" --status completed --rating 5

# List books by status
booktracker list --status reading
booktracker list --status "on hold"

# Log a reading session
booktracker log "The Great Gatsby" --pages 50 --location home
```

### Sync & Backup
```bash
# Sync local SQLite with Notion (explicit)
booktracker sync

# Check sync status (pending changes)
booktracker sync --status

# Force full refresh from Notion (Notion wins)
booktracker sync --force-pull

# Backup SQLite to timestamped file
booktracker backup
```

### Import/Export (ETL)
```bash
# Dry-run import (preview changes without writing)
booktracker import all --dry-run \
  --notion ~/exports/Notion.csv \
  --calibre ~/exports/Calibre.csv \
  --goodreads ~/exports/Goodreads.csv

# Interactive import (prompts for duplicate resolution)
booktracker import all \
  --notion ~/exports/Notion.csv \
  --calibre ~/exports/Calibre.csv \
  --goodreads ~/exports/Goodreads.csv

# Import with automatic backup first
booktracker import goodreads --file export.csv --backup

# Export unified data to CSV
booktracker export --output ~/backup/books.csv
```

### Statistics & Library
```bash
# Show reading statistics (books per time period)
booktracker stats
booktracker stats --year 2025
booktracker stats --month 2025-01

# Library tracking (manual entry)
booktracker library "Book Title" --due 2025-02-15 --location "Main Branch"
booktracker library --list  # Show all active holds/loans
```

## Setup Requirements

### Notion Setup
1. Create a Notion integration at https://www.notion.so/my-integrations
2. Create a database in Notion with the required properties
3. Share the database with the integration
4. Store the API key and database ID in environment variables

### Environment Variables
```bash
# Notion Configuration
NOTION_API_KEY=secret_xxxxx
NOTION_DATABASE_ID=xxxxx
NOTION_READING_LOGS_DB_ID=xxxxx  # Separate DB for reading logs

# Local Database (in OneDrive for automatic backup)
BOOKTRACKER_DB_PATH=~/OneDrive/booktracker/books.db

# Optional: Override cache TTL (default: 1 hour)
BOOKTRACKER_CACHE_TTL=3600
```

## ETL Phase: Data Import & Migration

### Overview

Before building the live tracking system, import existing book data from multiple sources into a unified schema. This preserves all historical reading data and unique fields from each platform.

### Source Files

| Source | File | Description |
|--------|------|-------------|
| Notion | `Notion.csv` | Existing Notion database export |
| Calibre | `Calibre.csv` | Calibre e-book library export |
| Goodreads | `Goodreads.csv` | Goodreads library export |

---

### Source Schema: Notion CSV (Actual)

Your Notion database export contains 31 fields:

| Field | Type | Maps To |
|-------|------|---------|
| Title | Text | `title` |
| Added | Date | `date_added` |
| Amazon URL | URL | `amazon_url` ★ |
| Author | Text | `author` |
| Author (L,F) | Text | `author_sort` |
| Book Series | Text | `series` |
| Comments | Text | `comments` ★ |
| Date Finished | Date | `date_finished` |
| Date Started | Date | `date_started` ★ |
| Description | Text | `description` ★ |
| FCPL URL | URL | `library_url` ★ |
| Formats | Select | `format` |
| Genres | Relation | `genres` |
| Goodreads URL | URL | `goodreads_url` ★ |
| ISBN | Text | `isbn` |
| ISBN-13 | Text | `isbn13` |
| Image | File | `cover` |
| Library | Select | `library_source` ★ |
| Log Button | Button | _(skip)_ |
| Logs | Relation | `reading_logs` ★ |
| Pages | Number | `page_count` |
| Progress | Text | `progress` ★ |
| Publish Year | Number | `publication_year` |
| Publisher | Text | `publisher` |
| Rating | Number | `rating` |
| Read Next | Checkbox | `read_next` ★ |
| Recommended By | Text | `recommended_by` ★ |
| Series Index | Number | `series_index` |
| Status | Select | `status` |
| Tags | Multi-select | `tags` ★ |
| Title (Sort) | Text | `title_sort` |

★ = Unique to Notion export

**Notion Status Values:** `Read`, `Skimmed`, `Borrowed`, `Want to Read`, `On Hold`

---

### Source Schema: Calibre CSV (Actual)

Your Calibre library export contains 22 fields:

| Field | Type | Maps To |
|-------|------|---------|
| author_sort | Text | `author_sort` |
| title_sort | Text | `title_sort` |
| pubdate | Date | `publication_date` |
| publisher | Text | `publisher` |
| series | Text | `series` |
| series_index | Number | `series_index` |
| tags | Text | `tags` |
| formats | Text | `file_formats` ★ |
| uuid | UUID | `calibre_uuid` ★ |
| title | Text | `title` |
| authors | Text | `author` |
| size | Number | `file_size` ★ |
| rating | Number | `rating` (convert 0-10 → 1-5) |
| library_name | Text | `calibre_library` ★ |
| languages | Text | `language` ★ |
| identifiers | Text | `identifiers` ★ |
| id | Number | `calibre_id` ★ |
| isbn | Text | `isbn` |
| timestamp | Date | `date_added` |
| comments | Text | `description` |
| cover | Path | `cover` |
| #text | Text | `custom_text` ★ |

★ = Unique to Calibre

**Identifiers format:** `goodreads:ID,mobi-asin:ASIN,isbn:ISBN,odid:OVERDRIVE_ID`

**Tags values observed:** `RIPPED`, `ACQUIRED`

---

### Source Schema: Goodreads CSV (Actual)

Your Goodreads export contains 24 fields:

| Field | Type | Maps To |
|-------|------|---------|
| Book Id | Number | `goodreads_id` ★ |
| Title | Text | `title` |
| Author | Text | `author` |
| Author l-f | Text | `author_sort` |
| Additional Authors | Text | `additional_authors` ★ |
| ISBN | Text | `isbn` |
| ISBN13 | Text | `isbn13` |
| My Rating | Number | `rating` |
| Average Rating | Number | `goodreads_avg_rating` ★ |
| Publisher | Text | `publisher` |
| Binding | Text | `format` |
| Number of Pages | Number | `page_count` |
| Year Published | Number | `publication_year` |
| Original Publication Year | Number | `original_publication_year` ★ |
| Date Read | Date | `date_finished` |
| Date Added | Date | `date_added` |
| Bookshelves | Text | `goodreads_shelves` ★ |
| Bookshelves with positions | Text | `goodreads_shelf_positions` ★ |
| Exclusive Shelf | Select | `status` |
| My Review | Text | `review` ★ |
| Spoiler | Text | `review_spoiler` ★ |
| Private Notes | Text | `notes` |
| Read Count | Number | `read_count` ★ |
| Owned Copies | Number | `owned_copies` ★ |

★ = Unique to Goodreads

**Exclusive Shelf values:** `read`, `currently-reading`, `to-read`

**ISBN format note:** Values wrapped as `="0385350597"` - need to strip `=""` wrapper

---

### Unified Output Schema

The merged schema preserves ALL unique fields from all three sources (50+ fields total):

#### Core Fields (Common)
| Field | Type | Source(s) |
|-------|------|-----------|
| `id` | UUID | Generated |
| `title` | Text | All |
| `title_sort` | Text | Notion, Calibre |
| `author` | Text | All |
| `author_sort` | Text | All |
| `status` | Enum | All |
| `rating` | Number (1-5) | All |
| `date_added` | Date | All |
| `date_started` | Date | Notion |
| `date_finished` | Date | Notion, Goodreads |
| `isbn` | Text | All |
| `isbn13` | Text | Notion, Goodreads |
| `page_count` | Number | Notion, Goodreads |
| `description` | Text | Notion, Calibre |
| `cover` | URL/Path | All |
| `publisher` | Text | All |
| `tags` | List[Text] | Notion, Calibre |

#### Series Fields
| Field | Type | Source(s) |
|-------|------|-----------|
| `series` | Text | Notion, Calibre |
| `series_index` | Number | Notion, Calibre |

#### Publication Fields
| Field | Type | Source |
|-------|------|--------|
| `publication_date` | Date | Calibre |
| `publication_year` | Number | Notion, Goodreads |
| `original_publication_year` | Number | Goodreads |
| `language` | Text | Calibre |

#### Format & Source Fields
| Field | Type | Source |
|-------|------|--------|
| `format` | Text | Notion, Goodreads (binding type: Kindle, Paperback, etc.) |
| `file_formats` | List[Text] | Calibre (epub, mobi, kfx, etc.) |
| `file_size` | Number | Calibre |
| `library_source` | Text | Notion (Calibre Library, Public Library) |

#### Notion-Specific Fields
| Field | Type | Description |
|-------|------|-------------|
| `amazon_url` | URL | Amazon product link |
| `goodreads_url` | URL | Goodreads book page |
| `library_url` | URL | FCPL catalog link |
| `comments` | Text | User comments/notes |
| `progress` | Text | Reading progress (e.g., "33%") |
| `read_next` | Boolean | Flagged for next read |
| `recommended_by` | Text | Who recommended the book |
| `reading_logs` | List | Notion relation to reading sessions |
| `genres` | List | Notion relation to genre database |

#### Goodreads-Specific Fields
| Field | Type | Description |
|-------|------|-------------|
| `goodreads_id` | Number | Goodreads book ID |
| `additional_authors` | Text | Co-authors, translators |
| `goodreads_avg_rating` | Number | Community average rating |
| `goodreads_shelves` | Text | User's shelf names |
| `goodreads_shelf_positions` | Text | Shelf positions with order |
| `review` | Text | Full review text |
| `review_spoiler` | Text | Spoiler flag |
| `notes` | Text | Private notes |
| `read_count` | Number | Times read |
| `owned_copies` | Number | Physical copies owned |

#### Calibre-Specific Fields
| Field | Type | Description |
|-------|------|-------------|
| `calibre_id` | Number | Calibre internal ID |
| `calibre_uuid` | UUID | Calibre unique identifier |
| `calibre_library` | Text | Source library name |
| `identifiers` | Dict | External IDs (ASIN, Goodreads, OverDrive) |
| `custom_text` | Text | Custom #text column |

#### Library Tracking Fields (New)
| Field | Type | Description |
|-------|------|-------------|
| `library_hold_date` | Date | When hold was placed |
| `library_due_date` | Date | Return deadline |
| `pickup_location` | Text | Library branch |
| `renewals` | Number | Times renewed |

#### Reading Log Fields (Essential)
Each reading session is tracked with:

| Field | Type | Description |
|-------|------|-------------|
| `log_id` | UUID | Unique session ID |
| `book_id` | UUID | FK to book |
| `date` | Date | Session date |
| `pages_read` | Number | Pages completed this session |
| `start_page` | Number | Where reading began |
| `end_page` | Number | Where reading ended |
| `duration_minutes` | Number | Time spent reading |
| `location` | Text | Where read (home, commute, vacation, etc.) |
| `notes` | Text | Session-specific notes |

**Re-reads**: Multiple reading sessions for the same book are supported. Each complete read-through can be identified by tracking start page = 1.

#### Source Tracking
| Field | Type | Description |
|-------|------|-------------|
| `source` | List[Enum] | `notion`, `calibre`, `goodreads`, `manual` |
| `source_ids` | Dict | Original IDs from each source |
| `import_date` | Date | When record was imported |

---

### ETL Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Notion.csv  │     │ Calibre.csv │     │Goodreads.csv│
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Extract   │     │   Extract   │     │   Extract   │
│  & Validate │     │  & Validate │     │  & Validate │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │     ┌─────────────────────────┐       │
       │     │  Skip invalid records   │       │
       │     │  Generate error report  │       │
       │     └─────────────────────────┘       │
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Transform  │     │  Transform  │     │  Transform  │
│  to Schema  │     │  to Schema  │     │  to Schema  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────┬───────┴───────────┬───────┘
                   ▼                   │
            ┌─────────────┐            │
            │   Dedupe    │◄───────────┘
            │  Detection  │
            └──────┬──────┘
                   │
                   ▼
            ┌─────────────┐
            │ Interactive │  ◄── User reviews each conflict
            │   Review    │      Shows diff, picks winner
            └──────┬──────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
  ┌───────────┐         ┌───────────┐
  │  DRY RUN  │         │   LIVE    │
  │  Report   │         │   Mode    │
  │  (--dry)  │         │           │
  └───────────┘         └─────┬─────┘
                              │
                   ┌──────────┴──────────┐
                   ▼                     ▼
            ┌─────────────┐       ┌─────────────┐
            │    Load     │       │    Load     │
            │  to SQLite  │       │  to Notion  │
            └─────────────┘       └─────────────┘
```

### ETL Implementation

#### Project Structure Addition
```
src/vibecoding/
├── booktracker/
│   ├── etl/
│   │   ├── __init__.py
│   │   ├── extract.py      # CSV parsers for each source
│   │   ├── transform.py    # Schema mapping & normalization
│   │   ├── dedupe.py       # Duplicate detection & merging
│   │   ├── load.py         # Notion API bulk loader
│   │   └── schemas.py      # Pydantic models for validation
```

#### CLI Commands
```bash
# Import from a single source
booktracker import notion --file ~/exports/Notion.csv
booktracker import calibre --file ~/exports/Calibre.csv
booktracker import goodreads --file ~/exports/Goodreads.csv

# Import all sources at once
booktracker import all \
  --notion ~/exports/Notion.csv \
  --calibre ~/exports/Calibre.csv \
  --goodreads ~/exports/Goodreads.csv

# Preview import without writing (dry run)
booktracker import goodreads --file export.csv --dry-run

# Export unified data back to CSV
booktracker export --output ~/backup/books.csv
```

### Deduplication Strategy

Books are matched and merged using this priority:

1. **ISBN Match** - Exact ISBN/ISBN13 match (highest confidence)
2. **Title + Author Match** - Normalized title + author name
3. **Fuzzy Match** - Levenshtein distance < 0.15 on title+author

#### Merge Rules
When duplicates are found, merge with these priorities:

| Field | Priority |
|-------|----------|
| `title` | Goodreads > Calibre > Notion |
| `author` | Goodreads > Calibre > Notion |
| `isbn` | First non-null |
| `rating` | Most recent |
| `date_finished` | Most recent |
| `notes` | Concatenate all (with source labels) |
| `genres` | Union of all |
| Source-specific fields | Preserve all |

### Data Cleaning Rules

#### Goodreads ISBN Cleaning
ISBNs are wrapped in Excel formula format: `="0385350597"`
```python
def clean_goodreads_isbn(value: str) -> str:
    """Strip ="" wrapper from Goodreads ISBN fields."""
    if value and value.startswith('="') and value.endswith('"'):
        return value[2:-1]
    return value
```

#### Calibre Rating Conversion
Calibre uses 0-10 scale, convert to 1-5:
```python
def convert_calibre_rating(rating: int) -> int:
    """Convert Calibre 0-10 rating to 1-5 scale."""
    if rating == 0:
        return None  # Unrated
    return max(1, min(5, rating // 2))
```

#### Calibre Identifiers Parsing
Parse comma-separated key:value pairs:
```python
# Input: "goodreads:48651321,mobi-asin:B07NN1V8YW,isbn:9781615196241"
# Output: {"goodreads": "48651321", "mobi-asin": "B07NN1V8YW", "isbn": "9781615196241"}
```

#### Notion Date Parsing
Dates in format: `May 21, 2025 7:01 AM` or date ranges: `May 24, 2025 → May 25, 2025`

#### Notion URL Cleaning
Relation fields contain Notion URLs that need extraction:
```
Fiction (https://www.notion.so/Fiction-1eeda780c0bb80b7ac17f4e2c10a9ae5?pvs=21)
```

### Validation Rules

- **Title**: Required, non-empty
- **Rating**: Must be 1-5 (convert Calibre 0-10 scale)
- **Dates**: Valid ISO format, not in future
- **ISBN**: Valid ISBN-10 or ISBN-13 checksum (after cleaning)
- **Status**: Map to unified enum (`reading`, `completed`, `on_hold`, `wishlist`, `dnf`, `skimmed`, `owned`)

### Status Mapping

| Source | Original Value | Maps To |
|--------|----------------|---------|
| Goodreads | `read` | `completed` |
| Goodreads | `currently-reading` | `reading` |
| Goodreads | `to-read` | `wishlist` |
| Notion | `Read` | `completed` |
| Notion | `Skimmed` | `skimmed` |
| Notion | `Borrowed` | `reading` |
| Notion | `Want to Read` | `wishlist` |
| Notion | `On Hold` | `on_hold` |
| Calibre | (no status field) | `owned` (ebook in library) |

#### Unified Status Enum
```python
class BookStatus(Enum):
    READING = "reading"
    COMPLETED = "completed"
    SKIMMED = "skimmed"
    ON_HOLD = "on_hold"       # Library hold
    WISHLIST = "wishlist"     # Want to read
    DNF = "dnf"               # Did not finish
    OWNED = "owned"           # In Calibre library, not yet read
```

---

## Implementation Phases

### Phase 0: Local Database & Core Infrastructure
- [ ] Set up SQLite database schema (books, reading_logs, sync_queue)
- [ ] Implement Pydantic models for unified book schema
- [ ] Implement SQLAlchemy ORM models
- [ ] Set up Alembic for database migrations
- [ ] Configure SQLite file location (OneDrive folder for backup)
- [ ] Basic CLI skeleton with typer + rich
- [ ] Set up pytest with comprehensive test structure
- [ ] Create mock fixtures for Notion API testing

### Phase 1: ETL & Data Migration
- [ ] Build CSV extractors for Notion, Calibre, Goodreads
- [ ] Implement field mapping transformations
- [ ] Build deduplication engine (ISBN + fuzzy matching)
- [ ] Create interactive conflict resolution UI
- [ ] Implement dry-run mode with detailed preview report
- [ ] Add pre-import backup prompt
- [ ] Create validation error report generator
- [ ] Load to SQLite (local)
- [ ] Batch load to Notion with rate limiting

### Phase 2: Notion Sync
- [ ] Implement Notion API client wrapper with aggressive caching
- [ ] Build sync queue for pending local changes
- [ ] Implement "Notion wins" conflict resolution
- [ ] Add `sync`, `sync --status`, `sync --force-pull` commands
- [ ] Track sync timestamps for incremental updates

### Phase 3: Book Entry & Metadata
- [ ] Integrate Open Library API
- [ ] Implement title search with interactive selection
- [ ] Auto-populate book details from search results
- [ ] Upload cover images to Notion
- [ ] Add `add` command with rich table preview

### Phase 4: Reading Logs
- [ ] Create reading_logs table (date, pages, duration, location)
- [ ] Implement `log` command for session tracking
- [ ] Link logs to books (one book → many logs)
- [ ] Calculate progress from cumulative pages
- [ ] Track reading location (home, commute, vacation, etc.)

### Phase 5: Library Features
- [ ] Library hold/due date tracking (manual entry)
- [ ] Configure Notion reminders on due date fields
- [ ] Add `library` command for hold management
- [ ] List active holds/loans

### Phase 6: Statistics & Insights
- [ ] Reading statistics: books per month/year
- [ ] Reading pace trends over time
- [ ] Rich table/chart output for stats
- [ ] Export stats to CSV

## Success Metrics

- **Book Entry**: Add a book via title search in under 15 seconds
- **Offline Access**: All reads work without internet connection
- **Data Safety**: Zero data loss during ETL migration (verified by dry-run)
- **Sync Reliability**: Local ↔ Notion sync completes without manual intervention
- **Statistics**: Books per month/year available on demand
- **Library Tracking**: All holds tracked with Notion reminders on due dates

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| **Data loss during migration** | Mandatory dry-run preview, pre-import backup prompt |
| **Notion API rate limits** | Aggressive caching, batch operations, local SQLite cache |
| **Notion API changes** | Abstract behind client wrapper, version pin SDK |
| **Sync conflicts** | "Notion wins" policy, clear conflict resolution |
| **SQLite corruption** | OneDrive auto-backup, export command |

## Open Questions (Deferred)

1. Should the app support multiple Notion databases (e.g., separate for different years)?
2. Mobile-friendly quick-add solution (iOS Shortcuts, Raycast extension)?
3. Automated Goodreads sync via unofficial API vs. manual CSV export?

## Notion Database Configuration

### Visible Fields (Reading-Focused ~15 fields)
These fields are shown by default in Notion table view:

| Field | Type | Purpose |
|-------|------|---------|
| Title | Title | Book name |
| Cover | Files | Book cover image |
| Author | Text | Primary author |
| Status | Select | Reading, Completed, Wishlist, etc. |
| Rating | Number | 1-5 stars |
| Progress | Text | e.g., "67%" or "pg 234" |
| Date Started | Date | When reading began |
| Date Finished | Date | Completion date |
| Series | Text | Series name |
| Series Index | Number | Position in series |
| Format | Select | Kindle, Paperback, Audiobook, etc. |
| Library Due Date | Date | With Notion reminder |
| Pages | Number | Total page count |
| Genre | Multi-select | Categories |
| Read Next | Checkbox | Priority flag |

### Hidden Fields (Available but collapsed)
All other fields from unified schema are present but hidden by default.

---

## Dependencies

```
# Core
notion-client>=2.0.0
requests>=2.28.0
typer>=0.9.0
rich>=13.0.0
python-dotenv>=1.0.0

# Database
# sqlite3 (Python stdlib - no install needed)
sqlalchemy>=2.0.0      # ORM for SQLite
alembic>=1.13.0        # Database migrations

# ETL
pandas>=2.0.0
pydantic>=2.0.0
thefuzz>=0.20.0        # Fuzzy string matching for deduplication
isbnlib>=3.10.0        # ISBN validation and lookup
tqdm>=4.65.0           # Progress bars for bulk imports

# Testing
pytest>=8.0.0
pytest-cov>=4.0.0      # Coverage reporting
pytest-mock>=3.12.0    # Mocking for Notion API tests
responses>=0.24.0      # Mock HTTP responses for API tests
```
