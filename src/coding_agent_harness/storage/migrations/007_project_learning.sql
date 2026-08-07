CREATE TABLE project_learning_cards (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    text TEXT NOT NULL,
    source_task_id TEXT NOT NULL REFERENCES tasks(id),
    source_event_sequence INTEGER NOT NULL CHECK (source_event_sequence > 0),
    approved_at TEXT NOT NULL,
    UNIQUE(source_task_id)
);
CREATE INDEX project_learning_latest_idx
    ON project_learning_cards(workspace_id, approved_at DESC, id ASC);
