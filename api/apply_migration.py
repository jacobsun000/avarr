#!/usr/bin/env python3
"""Apply database migration to add watched/starred columns.

This script safely adds the watched and starred columns to the downloadjob table.
It can be run multiple times safely - it will skip if columns already exist.
"""

import sqlite3
import sys
from pathlib import Path


def get_db_path() -> Path:
    """Get the database file path from settings or use default."""
    try:
        from avarr.settings import get_settings
        settings = get_settings()
        db_url = settings.database_url
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
            if db_path.startswith("./"):
                db_path = db_path[2:]
            return Path(db_path).resolve()
    except Exception as e:
        print(f"Warning: Could not load settings ({e}), using default path")

    return Path("storage.db").resolve()


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def index_exists(cursor: sqlite3.Cursor, index_name: str) -> bool:
    """Check if an index exists."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,)
    )
    return cursor.fetchone() is not None


def apply_migration(db_path: Path) -> None:
    """Apply the migration to add watched and starred columns."""
    if not db_path.exists():
        print(f"Error: Database file not found at {db_path}")
        sys.exit(1)

    print(f"Applying migration to: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        changes_made = False

        # Check if columns already exist
        watched_exists = column_exists(cursor, "downloadjob", "watched")
        starred_exists = column_exists(cursor, "downloadjob", "starred")

        # Add watched column if it doesn't exist
        if not watched_exists:
            print("Adding 'watched' column...")
            cursor.execute(
                "ALTER TABLE downloadjob ADD COLUMN watched BOOLEAN NOT NULL DEFAULT 0"
            )
            cursor.execute("CREATE INDEX ix_downloadjob_watched ON downloadjob (watched)")
            print("✓ Added 'watched' column with index")
            changes_made = True
        else:
            print("✓ Column 'watched' already exists")

        # Add starred column if it doesn't exist
        if not starred_exists:
            print("Adding 'starred' column...")
            cursor.execute(
                "ALTER TABLE downloadjob ADD COLUMN starred BOOLEAN NOT NULL DEFAULT 0"
            )
            cursor.execute("CREATE INDEX ix_downloadjob_starred ON downloadjob (starred)")
            print("✓ Added 'starred' column with index")
            changes_made = True
        else:
            print("✓ Column 'starred' already exists")

        # Add source_url index if it doesn't exist
        source_url_index_exists = index_exists(cursor, "ix_downloadjob_source_url")
        if not source_url_index_exists:
            print("Adding index on 'source_url' for duplicate detection...")
            cursor.execute(
                "CREATE INDEX ix_downloadjob_source_url ON downloadjob (source_url)"
            )
            print("✓ Added 'source_url' index")
            changes_made = True
        else:
            print("✓ Index 'ix_downloadjob_source_url' already exists")

        conn.commit()

        if changes_made:
            print("\n✅ Migration completed successfully!")
        else:
            print("\n✅ All migrations already applied")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    import os

    db_path = get_db_path()
    print(f"Database location: {db_path}")

    if not db_path.exists():
        print("\nNo database found. Migration will be applied automatically when the app creates the database.")
        sys.exit(0)

    # Check for --yes flag or non-interactive mode
    auto_yes = "--yes" in sys.argv or "-y" in sys.argv or not sys.stdin.isatty()

    if auto_yes:
        apply_migration(db_path)
    else:
        response = input("\nProceed with migration? [Y/n]: ")
        if response.lower() in ("", "y", "yes"):
            apply_migration(db_path)
        else:
            print("Migration cancelled")
