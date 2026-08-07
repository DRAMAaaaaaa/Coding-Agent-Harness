CREATE TABLE correction_branches (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    parent_task_id TEXT NOT NULL REFERENCES tasks(id),
    source_event_sequence INTEGER NOT NULL CHECK (source_event_sequence > 0),
    child_task_id TEXT REFERENCES tasks(id),
    status TEXT NOT NULL CHECK (status IN ('CREATING','READY','UNCERTAIN')),
    base_commit TEXT NOT NULL,
    patch_sha256 TEXT NOT NULL,
    patch_bytes INTEGER NOT NULL CHECK (patch_bytes BETWEEN 1 AND 1048576),
    checkpoint_file_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(parent_task_id, source_event_sequence)
);
