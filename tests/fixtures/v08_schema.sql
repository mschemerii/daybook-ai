CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'Medium',
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'Open',
    source TEXT NOT NULL DEFAULT 'User',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE journal_entries (
    entry_date TEXT PRIMARY KEY,
    completed_today TEXT NOT NULL DEFAULT '',
    in_progress TEXT NOT NULL DEFAULT '',
    blocked_waiting TEXT NOT NULL DEFAULT '',
    reflections TEXT NOT NULL DEFAULT '',
    plan_tomorrow TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_request TEXT NOT NULL,
    records_consulted TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    approved_action INTEGER
);

INSERT INTO tasks VALUES (
    7, 'Preserve café task', 'Legacy description', 'High', '2026-08-05',
    'Open', 'Meeting notes', 'Keep this note',
    '2026-07-01 01:02:03', '2026-07-02 04:05:06'
);
INSERT INTO journal_entries VALUES (
    '2026-08-04', 'Done', 'Working', 'Waiting', 'Reflection', 'Plan',
    '2026-08-04 12:00:00', '2026-08-04 13:00:00'
);
INSERT INTO memories VALUES (
    3, 'Remember this', '2026-07-03 00:00:00', '2026-07-04 00:00:00'
);
INSERT INTO audit_history VALUES (
    4, '2026-07-05 00:00:00', 'Request', '[{"type":"task","id":7}]',
    'Recommendation', 1
);
