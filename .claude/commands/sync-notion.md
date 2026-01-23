---
allowed-tools: Bash(pwd), Bash(test*), Bash(source venv/bin/activate*), Bash(python*), Bash(cd*), Read
description: Sync book database with Notion
---

# /sync-notion Command

Synchronize the local book tracker database with Notion.

## Context

- Current directory: !`pwd`
- Virtual environment exists: !`test -d venv && echo "yes" || echo "no"`

## Environment Check

Before syncing, verify:
1. The virtual environment exists at `./venv`
2. Environment variables are set (NOTION_API_KEY, NOTION_DATABASE_ID)

Check environment with:
```bash
source venv/bin/activate && python -c "from vibecoding.booktracker.config import get_config; c = get_config(); print('Notion configured:', c.has_notion_config())"
```

## Sync Options

The CLI provides several sync modes. Choose based on user input or default to full sync:

### Full Sync (default)
Push local changes AND pull Notion changes:
```bash
source venv/bin/activate && python -m vibecoding.booktracker.cli sync
```

### Push Only
Push local changes to Notion (don't pull):
```bash
source venv/bin/activate && python -m vibecoding.booktracker.cli sync --push
```

### Pull Only
Pull changes from Notion (don't push):
```bash
source venv/bin/activate && python -m vibecoding.booktracker.cli sync --pull
```

### Force Pull
Force a full refresh from Notion:
```bash
source venv/bin/activate && python -m vibecoding.booktracker.cli sync --force-pull
```

### Status Only
Check sync status without syncing:
```bash
source venv/bin/activate && python -m vibecoding.booktracker.cli sync --status
```

### Non-Interactive
Auto-resolve conflicts (Notion wins):
```bash
source venv/bin/activate && python -m vibecoding.booktracker.cli sync --yes
```

## Argument Handling

Parse the user's argument to determine the sync mode:

| User Input | Action |
|------------|--------|
| `/sync-notion` | Full sync (push + pull) |
| `/sync-notion status` | Show sync status only |
| `/sync-notion push` | Push local changes only |
| `/sync-notion pull` | Pull from Notion only |
| `/sync-notion force` | Force full pull from Notion |
| `/sync-notion auto` | Full sync, auto-resolve conflicts |

## Workflow

1. **Check Environment**
   - Verify venv exists
   - Verify Notion is configured

2. **Report Current State**
   - Show pending items count
   - Show total books and synced count

3. **Execute Sync**
   - Run appropriate sync command based on arguments
   - Display progress and results

4. **Report Results**
   - Books pushed to Notion
   - Books pulled from Notion
   - Conflicts resolved
   - Any errors encountered

## Error Handling

Common issues and solutions:

| Error | Solution |
|-------|----------|
| `NOTION_API_KEY not set` | Set environment variable or add to `.env` file |
| `NOTION_DATABASE_ID not set` | Set environment variable or add to `.env` file |
| Rate limited | Wait and retry (automatic with --yes flag) |
| Conflict detected | Choose local, Notion, or skip |

## Example Output

```
Pushing local changes to Notion...
Pushing: 100%|████████████████| 5/5

Pulling changes from Notion...
Pulling: 100%|████████████████| 12/12

========================================
Sync Complete
========================================
  Pushed to Notion: 5
  Pulled from Notion: 7
  Conflicts resolved: 2
```

## Related Files

- Notion client: `src/vibecoding/booktracker/sync/notion.py`
- Sync processor: `src/vibecoding/booktracker/sync/queue.py`
- CLI command: `src/vibecoding/booktracker/cli.py` (line 726)
- Config: `src/vibecoding/booktracker/config.py`
