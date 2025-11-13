-- Migration: Add index on source_url for duplicate detection
-- Date: 2025-11-13
-- Description: Adds index on source_url column for faster duplicate checking

-- Create index on source_url for performance
CREATE INDEX IF NOT EXISTS ix_downloadjob_source_url ON downloadjob (source_url);
