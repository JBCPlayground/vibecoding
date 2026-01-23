# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Booktracker is a Notion-integrated personal reading tracker. It manages books from multiple sources (Notion, Calibre, Goodreads, Open Library) with bidirectional sync to a Notion database. The local SQLite database serves as the source of truth with a sync queue for offline-first operation.

## Essential Commands

```bash
# Environment
source venv/bin/activate
pip install -r requirements.txt

# Run CLI
python -m vibecoding.booktracker.cli --help
booktracker --help  # if installed via pip install -e .

# Testing
pytest                                    # all tests
pytest tests/test_sync/test_notion.py    # specific file
pytest -k "test_create"                  # pattern match

# Code quality
black src/ tests/
flake8 src/ tests/
mypy src/
```

## Architecture

### Data Flow
```
[Notion] <--sync--> [SyncProcessor] <--> [SQLite DB] <--> [CLI]
                          |
[Calibre CSV] --import--> |
[Goodreads CSV] --------> |
[Open Library API] -----> |
```

### Key Components

**CLI** (`cli.py`): Typer-based command interface with Rich formatting. Commands: `add`, `list`, `update`, `sync`, `import calibre`, `import goodreads`.

**Sync System** (`sync/`):
- `notion.py`: NotionClient wraps Notion API with rate limiting and schema mapping
- `queue.py`: SyncProcessor handles push/pull with conflict detection and retry logic
- `conflict.py`: Detects and resolves bidirectional sync conflicts

**Database** (`db/`):
- `models.py`: SQLAlchemy ORM (Book, ReadingLog, SyncQueueItem)
- `schemas.py`: Pydantic models for validation (BookCreate, BookUpdate, BookStatus enum)
- `sqlite.py`: Database class with CRUD operations and sync queue management

**Imports** (`imports/`): CSV parsers for Calibre and Goodreads with field mapping to unified schema.

**ETL** (`etl/`): Extract-transform-load pipeline with deduplication by ISBN/title+author.

### Data Model

The Book model unifies fields from all sources:
- Core: title, author, status (reading/completed/wishlist/etc), rating (1-5)
- Notion-specific: amazon_url, progress, read_next, recommended_by
- Calibre-specific: calibre_id, calibre_uuid, file_formats, identifiers
- Goodreads-specific: goodreads_id, review, read_count, shelves
- Sync tracking: notion_page_id, local_modified_at, notion_modified_at

### Sync Queue

All local changes queue as SyncQueueItems (create/update/delete). The SyncProcessor:
1. Pushes pending local changes to Notion
2. Pulls Notion changes since last sync
3. Detects conflicts when both sides modified
4. Resolves via interactive prompt or auto (Notion wins)

## Configuration

Environment variables (or `.env` file):
- `NOTION_API_KEY`: Notion integration token
- `NOTION_DATABASE_ID`: Books database ID
- `NOTION_READING_LOGS_DB_ID`: Optional reading logs database
- `BOOKTRACKER_DB_PATH`: SQLite path (default: ~/OneDrive/booktracker/books.db)

## Status Mapping

Local → Notion status mapping:
- reading → Borrowed
- completed → Read
- wishlist → Want to Read
- on_hold → On Hold
- dnf → DNF
- owned → Owned
