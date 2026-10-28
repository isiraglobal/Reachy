PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS icp_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT,
    rating REAL,
    reviews_count INTEGER,
    phone TEXT,
    website TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    employee_count INTEGER,
    source TEXT NOT NULL,
    source_url TEXT,
    source_query TEXT,
    discovered_at TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    normalized_at TEXT,
    qualification_score INTEGER,
    qualification_reason TEXT,
    qualification_evidence TEXT,
    flags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leads_domain ON leads(website);
CREATE INDEX IF NOT EXISTS idx_leads_city_state ON leads(city, state);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(qualification_score);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    normalized_email TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    discovery_method TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (verification_status IN ('valid','invalid','catch_all','unknown','unverified')),
    verification_method TEXT,
    verification_detail TEXT,
    verified_at TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (lead_id, normalized_email)
);

CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(normalized_email);
CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(verification_status);

CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    icp_profile_id INTEGER REFERENCES icp_profiles(id),
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT','SAMPLE_READY','APPROVED','BLOCKED','ARCHIVED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS list_leads (
    list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (list_id, lead_id)
);

CREATE TABLE IF NOT EXISTS sample_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    seed INTEGER NOT NULL,
    sample_json TEXT NOT NULL,
    threshold INTEGER NOT NULL DEFAULT 2,
    incorrect_count INTEGER,
    decision TEXT CHECK (decision IN ('APPROVED','REJECTED')),
    reviewer TEXT,
    notes TEXT,
    failure_pattern TEXT,
    decisions_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS list_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL UNIQUE REFERENCES lists(id) ON DELETE CASCADE,
    sample_review_id INTEGER NOT NULL REFERENCES sample_reviews(id),
    approved_by TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS suppression (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    normalized_email TEXT NOT NULL UNIQUE,
    reason TEXT NOT NULL
        CHECK (reason IN ('unsubscribe','complaint','hard_bounce','manual','legal')),
    source TEXT,
    campaign_id INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    provider TEXT NOT NULL CHECK (provider IN ('gmail','smtp','mock')),
    config_json TEXT NOT NULL DEFAULT '{}',
    scopes TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING_AUTH'
        CHECK (status IN ('PENDING_AUTH','ACTIVE','PAUSED','REVOKED','ERROR')),
    daily_limit INTEGER NOT NULL DEFAULT 10,
    sends_today INTEGER NOT NULL DEFAULT 0,
    sends_today_date TEXT,
    authorized_at TEXT,
    revoked_at TEXT,
    last_sync_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_secrets (
    account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    ciphertext BLOB NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    list_id INTEGER NOT NULL REFERENCES lists(id),
    account_id INTEGER REFERENCES accounts(id),
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT','PREVIEW','APPROVED','RUNNING','PAUSED','COMPLETED','STOPPED','FAILED')),
    policy_json TEXT NOT NULL DEFAULT '{}',
    test_mode INTEGER NOT NULL DEFAULT 1,
    dry_run INTEGER NOT NULL DEFAULT 1,
    target_jurisdiction TEXT,
    sender_identity TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT,
    approved_by TEXT,
    started_at TEXT,
    paused_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);

CREATE TABLE IF NOT EXISTS campaign_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    subject_template TEXT NOT NULL,
    body_template TEXT NOT NULL,
    delay_days INTEGER NOT NULL DEFAULT 0,
    UNIQUE (campaign_id, step_number)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    account_id INTEGER REFERENCES accounts(id),
    step_number INTEGER NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('PLANNED','BLOCKED','QUEUED','SENDING','ACCEPTED','SENT','FAILED','CANCELLED','UNCERTAIN','SKIPPED')),
    idempotency_key TEXT NOT NULL UNIQUE,
    from_email TEXT,
    to_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    message_id_header TEXT,
    provider_message_id TEXT,
    policy_snapshot TEXT,
    scheduled_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    accepted_at TEXT,
    sent_at TEXT,
    cancelled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (campaign_id, contact_id, step_number)
);

CREATE INDEX IF NOT EXISTS idx_messages_queue ON messages(state, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_messages_campaign ON messages(campaign_id);

CREATE TABLE IF NOT EXISTS message_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_message ON message_events(message_id);

CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id),
    campaign_id INTEGER REFERENCES campaigns(id),
    lead_id INTEGER REFERENCES leads(id),
    contact_id INTEGER REFERENCES contacts(id),
    provider_reply_id TEXT NOT NULL,
    message_id_header TEXT,
    in_reply_to TEXT,
    from_email TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    received_at TEXT NOT NULL,
    classification TEXT NOT NULL
        CHECK (classification IN ('interested','not_interested','referral','out_of_office','automated','unsubscribe','complaint','uncertain')),
    classification_source TEXT NOT NULL,
    stop_followups INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (account_id, provider_reply_id)
);

CREATE INDEX IF NOT EXISTS idx_replies_contact ON replies(contact_id);
CREATE INDEX IF NOT EXISTS idx_replies_campaign ON replies(campaign_id);

CREATE TABLE IF NOT EXISTS reply_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reply_id INTEGER NOT NULL UNIQUE REFERENCES replies(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL'
        CHECK (status IN ('PENDING_APPROVAL','APPROVED','SENT','REJECTED')),
    created_at TEXT NOT NULL,
    approved_at TEXT,
    approved_by TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS health_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    metrics_json TEXT NOT NULL,
    status TEXT NOT NULL,
    alerts_json TEXT NOT NULL DEFAULT '[]',
    computed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_health_account ON health_snapshots(account_id, computed_at);
