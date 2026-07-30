import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { HarnessApi, TaskEvent, Workspace } from "./types";

const taskId = "00000000-0000-0000-0000-000000000001";
const workspace: Workspace = { id: "00000000-0000-0000-0000-000000000010", default_branch: "main", languages: ["Python"], trust_fingerprint: "a".repeat(64), trusted: false, repository: { tracked_count: 4, test_count: 1, dirty_count: 0, test_paths: ["tests/test_math.py"] } };
const event = (sequence: number, event_type: string, payload: Record<string, unknown>, before: TaskEvent["state_before"], after: TaskEvent["state_after"]): TaskEvent => ({ task_id: taskId, sequence, event_type, payload, state_before: before, state_after: after, occurred_at: "2026-07-30T00:00:00Z" });
const taskEvents = [
  event(1, "PLAN_PROPOSED", { content_sha256: "a".repeat(64), content_bytes: 12, diagnostic: "修复 add 的真实计划" }, "PLANNING", "WAITING_PLAN_APPROVAL"),
  event(2, "TOOL_EXECUTION_STARTED", { execution_id: "diff-1", action: { tool: "git_diff" } }, "EXECUTING", "EXECUTING"),
  event(3, "TOOL_EXECUTION_COMPLETED", { execution_id: "diff-1", result: { ok: true, diagnostic: "diff --git a/src/add.py" } }, "EXECUTING", "EXECUTING"),
  event(4, "VERIFICATION_SUCCEEDED", { run: { name: "test", ok: true, diagnostic: "1 passed" }, verification: { name: "test", config_version: "v1", trust_fingerprint: "b".repeat(64), worktree_fingerprint: "c".repeat(64), required_checks: ["test"] } }, "VERIFYING", "VERIFYING"),
];

function scriptedApi(): HarnessApi & { approveFinal: ReturnType<typeof vi.fn> } {
  const api = {
    connectProject: vi.fn(async (path: string) => ({ ...workspace, id: path.includes("second") ? "workspace-2" : workspace.id })),
    trustProject: vi.fn(async (item: Workspace) => ({ ...item, trusted: true })),
    createTask: vi.fn(async () => ({ id: taskId, workspace_id: workspace.id, state: "WAITING_PLAN_APPROVAL" as const })),
    approvePlan: vi.fn(async () => ({ id: taskId, workspace_id: workspace.id, state: "DECIDING" as const })),
    runTask: vi.fn(async () => ({ id: taskId, workspace_id: workspace.id, state: "WAITING_FINAL_REVIEW" as const })),
    approveFinal: vi.fn(async () => ({ id: taskId, workspace_id: workspace.id, state: "COMPLETED" as const })),
    getTask: vi.fn(async () => ({ id: taskId, workspace_id: workspace.id, state: "WAITING_FINAL_REVIEW" as const })),
    subscribeEvents: (_taskId: string, _after: number, listener: { onEvent: (value: TaskEvent) => void; onConnection: (state: "connected") => void }) => { taskEvents.forEach(listener.onEvent); listener.onConnection("connected"); return () => undefined; },
  };
  return api;
}

describe("App", () => {
  it("展示真实计划、验证和 diff，并完成最终批准", async () => {
    const user = userEvent.setup();
    const api = scriptedApi();
    render(<App api={api} />);
    await user.type(screen.getByLabelText("项目路径"), "C:\\demo\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    await user.click(await screen.findByRole("button", { name: "建立信任" }));
    await user.type(screen.getByLabelText("编码需求"), "修复 add 函数");
    await user.click(screen.getByRole("button", { name: "生成计划" }));
    expect(await screen.findByText("修复 add 的真实计划")).toBeVisible();
    expect(screen.getByText("1 passed")).toBeVisible();
    expect(screen.getByText("diff --git a/src/add.py")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "批准计划" }));
    await user.click(await screen.findByRole("button", { name: "批准最终审查" }));
    expect(api.approveFinal).toHaveBeenCalledWith(taskId);
  });

  it("切换项目会清空旧任务上下文", async () => {
    const user = userEvent.setup();
    render(<App api={scriptedApi()} />);
    await user.type(screen.getByLabelText("项目路径"), "C:\\demo\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    await user.click(await screen.findByRole("button", { name: "建立信任" }));
    await user.type(screen.getByLabelText("编码需求"), "修复 add 函数");
    await user.click(screen.getByRole("button", { name: "生成计划" }));
    expect(await screen.findByText("修复 add 的真实计划")).toBeVisible();
    await user.clear(screen.getByLabelText("项目路径"));
    await user.type(screen.getByLabelText("项目路径"), "C:\\second\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    expect(screen.queryByText("修复 add 的真实计划")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批准计划" })).not.toBeInTheDocument();
  });
});
