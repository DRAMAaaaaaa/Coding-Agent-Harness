CREATE TABLE provider_profiles (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('deepseek', 'qwen')),
    model TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

ALTER TABLE tasks ADD COLUMN provider_profile_id TEXT REFERENCES provider_profiles(id);
ALTER TABLE tasks ADD COLUMN provider_profile_version INTEGER;
ALTER TABLE tasks ADD COLUMN llm_api_authorized_at TEXT;

CREATE INDEX tasks_provider_profile_idx ON tasks(provider_profile_id);

CREATE TRIGGER tasks_provider_binding_insert
BEFORE INSERT ON tasks
WHEN (NEW.provider_profile_id IS NULL) != (NEW.provider_profile_version IS NULL)
  OR (NEW.provider_profile_id IS NULL) != (NEW.llm_api_authorized_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'invalid provider binding'); END;

CREATE TRIGGER tasks_provider_binding_update
BEFORE UPDATE OF provider_profile_id, provider_profile_version, llm_api_authorized_at ON tasks
WHEN (NEW.provider_profile_id IS NULL) != (NEW.provider_profile_version IS NULL)
  OR (NEW.provider_profile_id IS NULL) != (NEW.llm_api_authorized_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'invalid provider binding'); END;
