-- Add run/task separation and tags to leads so a single database can hold
-- leads from many discovery runs and tasks without mixing them. Deduplication
-- remains global by dedupe_key; tags/run/task only describe provenance.
ALTER TABLE leads ADD COLUMN run_id TEXT;
ALTER TABLE leads ADD COLUMN run TEXT;
ALTER TABLE leads ADD COLUMN run_name TEXT;
ALTER TABLE leads ADD COLUMN task_id TEXT;
ALTER TABLE leads ADD COLUMN task TEXT;
ALTER TABLE leads ADD COLUMN task_name TEXT;
ALTER TABLE leads ADD COLUMN tags TEXT NOT NULL DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_leads_task ON leads(task);
CREATE INDEX IF NOT EXISTS idx_leads_run ON leads(run_id);
CREATE INDEX IF NOT EXISTS idx_leads_tags ON leads(tags);