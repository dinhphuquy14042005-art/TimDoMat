PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (name IN ('finder', 'owner', 'admin'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    type TEXT NOT NULL CHECK (type IN ('lost', 'found')),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    district TEXT NOT NULL,
    location TEXT NOT NULL,
    incident_date TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'hidden')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS verification_requests (
    id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    claimant_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    details TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    risk_score INTEGER NOT NULL DEFAULT 50 CHECK (risk_score BETWEEN 0 AND 100),
    risk_level TEXT NOT NULL DEFAULT 'medium' CHECK (risk_level IN ('low', 'medium', 'high')),
    risk_reasons TEXT NOT NULL DEFAULT '[]',
    meeting_location TEXT,
    meeting_at TEXT,
    meeting_is_public INTEGER NOT NULL DEFAULT 0 CHECK (meeting_is_public IN (0, 1)),
    meeting_safety_warning INTEGER NOT NULL DEFAULT 0 CHECK (meeting_safety_warning IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at TEXT,
    reviewed_by_user_id INTEGER REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS post_private_clues (
    post_id TEXT PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    clue_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id INTEGER PRIMARY KEY,
    admin_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_posts_type_status_date
    ON posts(type, status, incident_date DESC);
CREATE INDEX IF NOT EXISTS idx_posts_district_status
    ON posts(district, status);
CREATE INDEX IF NOT EXISTS idx_verification_requests_post_status
    ON verification_requests(post_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_log_created_at
    ON admin_audit_log(created_at DESC);

INSERT OR IGNORE INTO roles(name) VALUES ('finder'), ('owner'), ('admin');
