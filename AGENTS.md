# Repository Instructions

## Project purpose

Build a Coding Agent Harness whose main contribution is a deterministic feedback loop. The delivered harness must be implemented by this repository rather than delegated to a high-level agent framework.

## Mandatory Superpowers workflow

1. Use `brainstorming` and obtain human approval of `SPEC.md`.
2. Use `writing-plans` to produce `PLAN.md` with exact files, dependencies, failing tests, and verification commands.
3. Before implementation, run a cold-start check with a different agent type using only `SPEC.md` and `PLAN.md`; record findings in `SPEC_PROCESS.md`.
4. Use isolated git worktrees for independent features.
5. Implement every behavior with red-green-refactor TDD.
6. After each task, perform specification-compliance review before code-quality review.
7. Use `finishing-a-development-branch` only after verification evidence is current.

Do not write harness implementation code until steps 1-3 are complete.

## Harness implementation boundaries

- Implement the agent loop, LLM abstraction, action parser, tool dispatcher, memory, governance, feedback, configuration, and stopping logic in repository-owned code.
- Keep the LLM interface injectable so mock/stub implementations can drive deterministic offline tests.
- Do not use a high-level agent runner such as LangChain AgentExecutor, AutoGen, CrewAI, or LlamaIndex agents to supply the product's loop or governance.
- Encode guardrails and feedback validators as deterministic mechanisms, not prompt-only instructions.

## Security rules

- Never commit real API keys, tokens, passwords, private keys, credential databases, `.env` files, or secret-bearing logs.
- Use only placeholders in `.env.example` and documentation.
- Never echo credentials in terminal output, tests, exceptions, snapshots, or `AGENT_LOG.md`.
- If a credential is exposed, stop, rotate it, remove it from Git history, and document the incident without recording the value.

## Verification and process evidence

- Keep `PLAN.md` updated with task status and commit hashes.
- Keep `AGENT_LOG.md` chronological and factual; record the skill used, relevant context, agent output or commit, human intervention, and lesson learned.
- A completion claim requires fresh command output proving the relevant tests, lint/type checks, build, and mechanism demo pass.
- The final repository must provide one-command tests, mock-LLM mechanism coverage, GitHub Actions, the required `.gitlab-ci.yml` `unit-test` job, Docker distribution, and a deployable WebUI.

## Current phase

The repository is in the pre-implementation governance phase. Commands and technology-specific conventions remain undecided until `SPEC.md` is approved.
