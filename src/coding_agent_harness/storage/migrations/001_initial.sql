CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    requirement TEXT NOT NULL,
    state TEXT NOT NULL,
    step_budget INTEGER NOT NULL CHECK (step_budget >= 0),
    time_budget_seconds REAL NOT NULL CHECK (time_budget_seconds > 0),
    created_at TEXT NOT NULL,
    deadline_at TEXT
);

CREATE TABLE IF NOT EXISTS task_events (
    task_id TEXT NOT NULL REFERENCES tasks(id),
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    state_before TEXT,
    state_after TEXT,
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (task_id, sequence)
);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    content TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    action_type TEXT,
    payload TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    decision TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS tool_executions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    tool_name TEXT,
    status TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS verification_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    status TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    artifact_type TEXT,
    location TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS memory_records (
    id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(id),
    content TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS credential_references (
    id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(id),
    provider TEXT,
    reference TEXT NOT NULL,
    created_at TEXT
);
