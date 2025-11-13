# Database Migrations

This directory contains SQL migration scripts for the Avarr database.

## Applying Migrations

### Option 1: Using the Python migration script (Recommended)

From the `api/` directory:

```bash
uv run python apply_migration.py
```

This script will:
- Automatically locate your database file
- Check if migration is needed
- Apply changes safely (can be run multiple times)
- Create indexes for performance

### Option 2: Manual SQLite commands

If you prefer to apply the SQL directly:

```bash
sqlite3 storage.db < migrations/001_add_watched_starred.sql
```

Or interactively:

```bash
sqlite3 storage.db
sqlite> .read migrations/001_add_watched_starred.sql
sqlite> .exit
```

### Option 3: Backup and recreate (loses data)

If you don't need to preserve existing jobs:

```bash
# Backup first
mv storage.db storage.db.backup

# The app will create a new database with the correct schema on next run
```

## Migration History

- `001_add_watched_starred.sql` - Adds `watched` and `starred` boolean flags to jobs
- `002_add_source_url_index.sql` - Adds index on `source_url` for duplicate detection performance
