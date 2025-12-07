-- DF-World Master Database Schema
-- Tracks all imported worlds

CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY,           -- UUID or slug
    name TEXT NOT NULL,            -- World name
    altname TEXT,                  -- Alternative name
    db_path TEXT NOT NULL,         -- Path to world database
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_current INTEGER DEFAULT 0,  -- 1 if this is the active world
    has_plus INTEGER DEFAULT 0     -- 1 if imported with legends_plus.xml
);

CREATE INDEX IF NOT EXISTS idx_worlds_current ON worlds(is_current);
