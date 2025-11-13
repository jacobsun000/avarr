-- Migration: Add watched and starred flags to downloadjob table
-- Date: 2025-11-13
-- Description: Adds watched and starred boolean columns with indexes

-- Add watched column (default False)
ALTER TABLE downloadjob ADD COLUMN watched BOOLEAN NOT NULL DEFAULT 0;

-- Add starred column (default False)
ALTER TABLE downloadjob ADD COLUMN starred BOOLEAN NOT NULL DEFAULT 0;

-- Create indexes for better query performance
CREATE INDEX ix_downloadjob_watched ON downloadjob (watched);
CREATE INDEX ix_downloadjob_starred ON downloadjob (starred);
