ALTER TABLE workspaces ADD COLUMN root TEXT;
ALTER TABLE workspaces ADD COLUMN root_key TEXT;
ALTER TABLE workspaces ADD COLUMN git_root TEXT;
ALTER TABLE workspaces ADD COLUMN default_branch TEXT;
ALTER TABLE workspaces ADD COLUMN profile_json TEXT;
ALTER TABLE workspaces ADD COLUMN trust_fingerprint TEXT;
ALTER TABLE workspaces ADD COLUMN created_at TEXT;
ALTER TABLE workspaces ADD COLUMN trust_state TEXT NOT NULL DEFAULT 'UNTRUSTED'
    CHECK (trust_state IN ('UNTRUSTED', 'TRUSTED'));
ALTER TABLE workspaces ADD COLUMN trusted_at TEXT;
ALTER TABLE workspaces ADD COLUMN trusted_fingerprint TEXT;

CREATE UNIQUE INDEX workspaces_root_key_unique
    ON workspaces(root_key)
    WHERE root_key IS NOT NULL;
