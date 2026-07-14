# Agent Log

This chronological log records process evidence for the AI4SE project. It must never contain credentials or fabricated actions.

## Entries

### 2026-07-14 14:34 +08:00 — INIT-001

- **Task:** Initialize the local workspace from the GitHub repository.
- **Superpowers skill:** `using-superpowers`.
- **Prompt / context:** The human supplied `https://github.com/DRAMAaaaaaa/Coding-Agent-Harness.git` and authorized repository initialization only.
- **Agent output / evidence:** Cloned `origin/main`; verified clean tracking state at commit `d6b7f93` (`Initial commit`). No subagent was used.
- **Human intervention:** The human selected a deterministic feedback loop as the project's main contribution in the initial README.
- **Lesson:** Repository initialization must remain separate from product implementation because the required specification gates have not passed.

### 2026-07-14 14:40 +08:00 — GOV-001

- **Task:** Add the initial `.gitignore` security baseline.
- **Superpowers skill:** `using-superpowers`; brainstorming and TDD were intentionally not invoked because this was repository governance rather than product behavior.
- **Prompt / context:** The human explicitly requested a `.gitignore` file.
- **Agent output / evidence:** Added ignore rules for credentials, local configuration, harness state, logs, Python/Node caches, build artifacts, IDE files, and local container overrides. `git diff --check` passed. No subagent was used.
- **Human intervention:** The human limited the requested change to `.gitignore`.
- **Lesson:** Secret exclusions should be established before any provider integration or local testing creates credential-bearing files.

### 2026-07-14 14:43 +08:00 — GOV-002

- **Task:** Establish the remaining pre-implementation process and security baseline.
- **Superpowers skill:** `using-superpowers` with the Codex platform adaptation.
- **Prompt / context:** The human approved execution of plan step 1 and asked whether Superpowers was required.
- **Agent output / evidence:** Enabled Codex multi-agent support; added repository instructions, process-log structure, line-ending/editor rules, and a credential-free environment template. No subagent was used because this bounded governance task did not benefit from delegation.
- **Human intervention:** The human authorized step 1 but not product implementation.
- **Lesson:** Superpowers is required as a process gate even when specialized design or TDD skills do not apply to a governance-only change.

### 2026-07-14 17:02 +08:00 — SPEC-001

- **Task:** Complete the Superpowers brainstorming phase and write the approved product specification.
- **Superpowers skill:** `brainstorming`.
- **Prompt / context:** The human defined a programmer-focused coding agent that directly edits projects and delivers working code plus documentation. The dialogue resolved scope, providers, approvals, memory boundaries, feedback budgets, WebUI, deployment, testing, CI, Docker, and architecture.
- **Agent output / evidence:** Added `SPEC.md`, `SPEC_PROCESS.md`, and `docs/superpowers/specs/2026-07-14-coding-agent-harness-design.md` in commit `72c8b23`. `git diff --cached --check`, placeholder scanning, and a credential-pattern scan passed before commit. No implementation code or cold-start result was produced.
- **Human intervention:** The human approved each design section and the complete design; corrected the default planning rule to “plan unless explicitly skipped”; declined a visual companion; selected the event-driven recoverable state machine.
- **Lesson:** Explicitly versioned approvals and bounded progress detection turn vague “agent autonomy” into deterministic, testable harness behavior. The cold-start gate must remain pending until `PLAN.md` exists.
