# Coding Agent Harness — Approved Design

**Date:** 2026-07-14

**Status:** Approved during Superpowers brainstorming

**Canonical detailed specification:** [`../../../SPEC.md`](../../../SPEC.md)

## Purpose

Build a local-first coding agent for programmers. A user supplies a requirement; the agent plans by default, waits for approval, edits an isolated Git worktree, runs objective checks, corrects failures within deterministic budgets, and returns code, evidence, and documentation for final review.

The principal contribution is a deterministic feedback loop. The repository owns the loop, action parsing, tools, policy, approvals, feedback, memory, configuration, and stopping logic. A real LLM is replaceable by a scripted mock without removing the mechanisms under evaluation.

## Chosen approach

The approved architecture is an event-driven recoverable state machine. It was selected over a synchronous ReAct loop and a fixed DAG because it provides explicit pause/resume, versioned approval, crash recovery, progress detection, and deterministic transition tests while retaining dynamic coding behavior.

## Product boundary

- Local FastAPI service plus React WebUI.
- Full functionality binds to localhost and operates only on explicitly selected Git projects.
- Every task uses an isolated worktree.
- Public deployment uses an ephemeral sample repository and Mock LLM only.
- Python and Node.js receive automatic project/verification adapters; other projects supply commands.
- DeepSeek, Qwen, and Mock LLM share an internal provider contract.

## Core components

- `TaskOrchestrator`: state machine and agent loop.
- `LLMProvider`: DeepSeek, Qwen, and scripted mock adapters.
- `ContextBuilder`: repository map, search, memory, plan, and feedback selection.
- `ActionParser`: strict typed actions.
- `PolicyEngine` and `ApprovalManager`: deterministic governance and HITL.
- `ToolRegistry`: bounded read, search, patch, shell, verification, and Git tools.
- `FeedbackEngine`: check selection, classification, fingerprinting, progress, and budgets.
- `WorktreeManager`: isolation, checkpoints, diff, and Git lifecycle.
- `EventStore` and `MemoryStore`: recoverable events and filtered long-term knowledge.
- `CredentialStore`: OS keyring or password-protected authenticated encryption.
- `WebGateway`: same-origin REST commands and SSE events.

## Task flow

```text
CREATED → SCANNING → PLANNING → WAITING_PLAN_APPROVAL
        → DECIDING → WAITING_ACTION_APPROVAL / EXECUTING
        → VERIFYING → CORRECTING → DECIDING
        → WAITING_FINAL_REVIEW → COMPLETED
```

`WAITING_USER`, `FAILED`, and `CANCELLED` are reachable from running states. Explicitly skipping a plan moves from scanning to deciding, but never skips governance, verification, or final review.

## Coding-focused conveniences

- Automatic project reconnaissance and repository map.
- Task templates for feature, bug, refactor, tests, and docs.
- Context retrieval by files, text, symbols, and Git changes.
- Atomic patch editing with stale-file detection.
- Checkpoints and task-level rollback.
- Fast affected checks followed by full final verification.
- Failure deduplication, progress display, and resumable tasks.
- Git diff, commit/PR drafting, and documentation synchronized to real changes.

## Governance and secrets

Deletion, access outside the worktree, dependency installation, tool-initiated external network access, push/merge/publish, and dangerous shell commands require versioned approval. Selecting a real provider and starting or resuming a task authorizes only that task's required LLM API calls; it does not authorize network-capable tools. Repository content is untrusted data and cannot override policy.

Credentials never enter source, events, memory, logs, exceptions, snapshots, or WebUI responses. Local native runs use the OS keyring; containers use Argon2id plus AES-256-GCM authenticated encryption. The public demo accepts no real key.

## Feedback contribution

The feedback engine converts test, lint, type, and build outputs into structured categories and stable fingerprints. The same fingerprint receives at most three correction attempts; a task receives at most eight full correction cycles; two consecutive rounds without fewer failures or a changed category escalate to the user. Default command timeout is five minutes.

## Test evidence

All core mechanisms must run offline with a scripted Mock LLM. The mechanism demo deterministically shows:

1. a dangerous deletion blocked by policy;
2. an injected failure returned to the agent and followed by a changed successful action;
3. stable failure fingerprints and escalation after two no-progress rounds.

The final repository exposes `make test`, `make test-unit`, `make test-e2e`, and `make demo`, plus GitHub Actions, a GitLab `unit-test` job, Docker image build, and public Mock WebUI.

## UI and distribution

The WebUI uses Open Design's `dashboard` skill with the `Neutral Modern` design system. It provides projects, task creation, a task workbench, approvals, history, settings, and a public demo. Docker/OCI is the official distribution; release images target Linux amd64 and arm64 and are published to GHCR. The public demo is deployed as a Render Docker Web Service with documented cold-start and ephemeral-storage limits.

## Deferred scope

Multi-user tenancy, product-level multi-agent orchestration, arbitrary cloud repositories, universal AST refactoring, an IDE plugin, and autonomous deployment are explicitly deferred.
