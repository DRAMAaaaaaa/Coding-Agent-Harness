BEGIN IMMEDIATE;

ALTER TABLE approvals RENAME TO approvals_legacy_v1;

CREATE TABLE approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    action_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    event_sequence INTEGER NOT NULL CHECK (event_sequence >= 0),
    normalized_scope TEXT NOT NULL,
    task_state TEXT NOT NULL,
    config_version TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('PENDING', 'APPROVED', 'DENIED')),
    decided_by TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    consumed_at TEXT,
    UNIQUE (
        task_id,
        action_id,
        event_sequence,
        normalized_scope,
        task_state,
        config_version
    ),
    CHECK (
        (decision = 'PENDING' AND decided_by IS NULL AND decided_at IS NULL)
        OR (decision IN ('APPROVED', 'DENIED') AND decided_by IS NOT NULL AND decided_at IS NOT NULL)
    )
);

INSERT INTO approvals (
    id,
    task_id,
    action_id,
    reason_code,
    event_sequence,
    normalized_scope,
    task_state,
    config_version,
    decision,
    decided_by,
    expires_at,
    created_at,
    decided_at,
    consumed_at
)
SELECT
    id,
    task_id,
    'legacy:' || id,
    'LEGACY_APPROVAL',
    0,
    '',
    'CANCELLED',
    'legacy-v1',
    'DENIED',
    'migration',
    '1970-01-01T00:00:00+00:00',
    COALESCE(created_at, '1970-01-01T00:00:00+00:00'),
    COALESCE(created_at, '1970-01-01T00:00:00+00:00'),
    COALESCE(created_at, '1970-01-01T00:00:00+00:00')
FROM approvals_legacy_v1;

DROP TABLE approvals_legacy_v1;

CREATE INDEX approvals_task_decision_idx
    ON approvals (task_id, decision, expires_at);
CREATE INDEX approvals_action_context_idx
    ON approvals (action_id, event_sequence, config_version);

PRAGMA user_version = 2;

COMMIT;
