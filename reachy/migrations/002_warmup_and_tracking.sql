-- Migration 002: Warmup and Open Tracking
-- Built by ISIRA Automations for Reachy

ALTER TABLE messages ADD COLUMN opened_at TEXT;
ALTER TABLE messages ADD COLUMN open_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE messages ADD COLUMN tracking_token TEXT;

ALTER TABLE accounts ADD COLUMN warmup_enabled INTEGER NOT NULL DEFAULT 1;
ALTER TABLE accounts ADD COLUMN warmup_started_at TEXT;
ALTER TABLE accounts ADD COLUMN warmup_daily_limit INTEGER NOT NULL DEFAULT 10;

CREATE INDEX IF NOT EXISTS idx_messages_tracking ON messages(tracking_token);
CREATE INDEX IF NOT EXISTS idx_messages_opened ON messages(opened_at);
