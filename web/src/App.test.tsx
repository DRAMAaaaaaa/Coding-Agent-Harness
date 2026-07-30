import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { HarnessApi, TaskEvent, Workspace } from "./types";

const taskId = "00000000-0000-0000-0000-000000000001";
const workspace: Workspace = { id: "00000000-0000-0000-0000-000000000010", default_branch: "main", languages: ["Python"], trust_fingerprint: "a".repeat(64), trusted: false, repository: { tracked_count: 4, test_count: 1, dirty_count: 0, test_paths: ["tests/test_math.py"] } };
const event = (sequence: number, event_type: string, payload: Record<string, unknown>, before: TaskEvent["state_before"], after: TaskEvent["state_after"]): TaskEvent => ({ task_id: taskId, sequence, event_type, payload, state_before: before, state_after: after, occurred_at: `2026-07-30T00:00:${String(sequence).padStart(2, "0")}Z` });
const content = (diagnostic: string): Record<string, unknown> => ({ content_sha256: "a".repeat(64), content_bytes: new TextEncoder().encode(diagnostic).length, diagnostic });
const taskEvents = [
  event(1, "PLAN_PROPOSED", content("修复 add 的真实计划"), "PLANNING", "WAITING_PLAN_APPROVAL"),
  event(2, "TOOL_EXECUTION_STARTED", { execution_id: "diff-1", action: { tool: "git_diff" } }, "EXECUTING", "EXECUTING"),
  event(3, "TOOL_EXECUTION_COMPLETED", { execution_id: "diff-1", result: { ok: true, ...content("diff --git a/src/add.py") } }, "EXECUTING", "EXECUTING"),
  event(4, "VERIFICATION_SUCCEEDED", { run: { name: "test", ok: true, failure_count: null, diagnostic: "1 passed" }, verification: { name: "test", config_version: "v1", trust_fingerprint: "b".repeat(64), worktree_fingerprint: "c".repeat(64), required_checks: ["test"] } }, "VERIFYING", "VERIFYING"),
  event(5, "FINAL_SUMMARY_PROPOSED", content("add 已修复"), "VERIFYING", "WAITING_FINAL_REVIEW"),
];
const latestTaskEvents = [
  event(1, "PLAN_PROPOSED", content("修复 add 的真实计划"), "PLANNING", "WAITING_PLAN_APPROVAL"),
  event(2, "TOOL_EXECUTION_COMPLETED", { execution_id: "write-1", result: { ok: true, changed_paths: ["src/add.py"] } }, "EXECUTING", "EXECUTING"),
  event(3, "TOOL_EXECUTION_STARTED", { execution_id: "diff-1", action: { tool: "git_diff" } }, "EXECUTING", "EXECUTING"),
  event(4, "TOOL_EXECUTION_COMPLETED", { execution_id: "diff-1", result: { ok: true, ...content("diff --git a/src/add.py\n-old") } }, "EXECUTING", "EXECUTING"),
  event(5, "VERIFICATION_SUCCEEDED", { run: { name: "test", ok: true, failure_count: null, diagnostic: "旧轮次通过" }, verification: { name: "test", config_version: "v1", trust_fingerprint: "b".repeat(64), worktree_fingerprint: "c".repeat(64), required_checks: ["test"] } }, "VERIFYING", "VERIFYING"),
  event(6, "TOOL_EXECUTION_COMPLETED", { execution_id: "write-2", result: { ok: true, changed_paths: ["src/add.py"] } }, "EXECUTING", "EXECUTING"),
  event(7, "TOOL_EXECUTION_STARTED", { execution_id: "diff-2", action: { tool: "git_diff" } }, "EXECUTING", "EXECUTING"),
  event(8, "TOOL_EXECUTION_COMPLETED", { execution_id: "diff-2", result: { ok: true, ...content("diff --git a/src/add.py\n+new") } }, "EXECUTING", "EXECUTING"),
  event(9, "VERIFICATION_SUCCEEDED", { run: { name: "test", ok: true, failure_count: null, diagnostic: "第二轮通过" }, verification: { name: "test", config_version: "v1", trust_fingerprint: "b".repeat(64), worktree_fingerprint: "c".repeat(64), required_checks: ["test"] } }, "VERIFYING", "VERIFYING"),
  event(10, "FINAL_SUMMARY_PROPOSED", content("第二轮最终摘要"), "VERIFYING", "WAITING_FINAL_REVIEW"),
];

type ApiOptions = { events?: TaskEvent[]; connectProject?: HarnessApi["connectProject"]; getTask?: HarnessApi["getTask"]; approvePlan?: HarnessApi["approvePlan"] };

function scriptedApi(options: ApiOptions = {}): HarnessApi & { approveFinal: ReturnType<typeof vi.fn>; getTask: ReturnType<typeof vi.fn>; approvePlan: ReturnType<typeof vi.fn> } {
  const api = {
    connectProject: options.connectProject ?? vi.fn(async (path: string) => ({ ...workspace, id: path.includes("second") ? "workspace-2" : workspace.id })),
    trustProject: vi.fn(async (item: Workspace) => ({ ...item, trusted: true })),
    createTask: vi.fn(async () => ({ id: taskId, workspace_id: workspace.id, state: "WAITING_PLAN_APPROVAL" as const })),
    approvePlan: options.approvePlan ?? vi.fn(async () => ({ id: taskId, workspace_id: workspace.id, state: "DECIDING" as const })),
    runTask: vi.fn(async () => ({ id: taskId, workspace_id: workspace.id, state: "WAITING_FINAL_REVIEW" as const })),
    approveFinal: vi.fn(async () => ({ id: taskId, workspace_id: workspace.id, state: "COMPLETED" as const })),
    getTask: options.getTask ?? vi.fn(async () => ({ id: taskId, workspace_id: workspace.id, state: "WAITING_FINAL_REVIEW" as const })),
    subscribeEvents: (_taskId: string, _after: number, listener: { onEvent: (value: TaskEvent) => void; onConnection: (state: "connected") => void }) => { (options.events ?? taskEvents).forEach(listener.onEvent); listener.onConnection("connected"); return () => undefined; },
  };
  return api as unknown as HarnessApi & { approveFinal: ReturnType<typeof vi.fn>; getTask: ReturnType<typeof vi.fn>; approvePlan: ReturnType<typeof vi.fn> };
}

async function createTrustedTask(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(screen.getByLabelText("项目路径"), "C:\\demo\\repo");
  await user.click(screen.getByRole("button", { name: "接入项目" }));
  await user.click(await screen.findByRole("button", { name: "建立信任" }));
  await user.type(screen.getByLabelText("编码需求"), "修复 add 函数");
  await user.click(screen.getByRole("button", { name: "生成计划" }));
}

describe("App", () => {
  it("展示真实计划、验证和 diff，并完成最终批准", async () => {
    const user = userEvent.setup();
    const api = scriptedApi();
    render(<App api={api} />);
    await createTrustedTask(user);
    expect(await screen.findByText("修复 add 的真实计划")).toBeVisible();
    expect(screen.getByText("1 passed")).toBeVisible();
    expect(screen.getByText("diff --git a/src/add.py")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "批准计划" }));
    await user.click(await screen.findByRole("button", { name: "批准最终审查" }));
    expect(api.approveFinal).toHaveBeenCalledWith(taskId);
  });

  it("只显示最新一轮修改后的验证、diff 与最终摘要", async () => {
    const user = userEvent.setup();
    render(<App api={scriptedApi({ events: latestTaskEvents })} />);
    await createTrustedTask(user);
    expect(await screen.findByText("第二轮通过")).toBeVisible();
    expect(screen.getByText(/diff --git a\/src\/add\.py\s+\+new/)).toBeVisible();
    expect(screen.queryByText("旧轮次通过")).not.toBeInTheDocument();
    expect(screen.queryByText(/diff --git a\/src\/add\.py\s+-old/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "批准计划" }));
    expect(await screen.findByRole("button", { name: "批准最终审查" })).toBeVisible();
  });

  it("新一轮修改没有验证时，旧验证不能用于最终批准", async () => {
    const user = userEvent.setup();
    render(<App api={scriptedApi({ events: latestTaskEvents.filter((item) => item.sequence !== 9) })} />);
    await createTrustedTask(user);
    await user.click(screen.getByRole("button", { name: "批准计划" }));
    expect(await screen.findByText(/等待测试结果/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "批准最终审查" })).not.toBeInTheDocument();
  });

  it.each([
    ["空计划", content("")],
    ["截断计划", content(`[OUTPUT_LIMIT bytes=5000 sha256=${"b".repeat(64)}]`)],
    ["元数据不一致", { ...content("真实计划"), content_bytes: 1 }],
  ])("%s 不可批准", async (_name, planPayload) => {
    const user = userEvent.setup();
    render(<App api={scriptedApi({ events: [event(1, "PLAN_PROPOSED", planPayload, "PLANNING", "WAITING_PLAN_APPROVAL")] })} />);
    await createTrustedTask(user);
    expect(screen.queryByRole("button", { name: "批准计划" })).not.toBeInTheDocument();
    expect(screen.getByText(/计划内容不完整/)).toBeVisible();
  });

  it.each([
    ["缺少当前 diff", taskEvents.filter((item) => item.event_type !== "TOOL_EXECUTION_COMPLETED")],
    ["缺少当前最终摘要", taskEvents.filter((item) => item.event_type !== "FINAL_SUMMARY_PROPOSED")],
    ["diff 已截断", taskEvents.map((item) => item.event_type === "TOOL_EXECUTION_COMPLETED" ? event(item.sequence, item.event_type, { execution_id: "diff-1", result: { ok: true, ...content(`[OUTPUT_LIMIT bytes=5000 sha256=${"b".repeat(64)}]`) } }, item.state_before, item.state_after) : item)],
  ])("%s 时不可最终批准", async (_name, events) => {
    const user = userEvent.setup();
    render(<App api={scriptedApi({ events })} />);
    await createTrustedTask(user);
    await user.click(screen.getByRole("button", { name: "批准计划" }));
    expect(screen.queryByRole("button", { name: "批准最终审查" })).not.toBeInTheDocument();
    expect(screen.getByText(/终审证据不完整/)).toBeVisible();
  });

  it("非法事件会清空审批证据并在对账失败时禁用变更", async () => {
    const user = userEvent.setup();
    const api = scriptedApi({ getTask: vi.fn(async () => { throw new Error("get failed"); }) });
    api.subscribeEvents = (_taskId, _after, listener) => {
      taskEvents.forEach(listener.onEvent);
      listener.onConnection("connected");
      listener.onInvalidEvent?.();
      return () => undefined;
    };
    render(<App api={api} />);
    await createTrustedTask(user);
    expect(await screen.findByText(/事件数据无效/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "批准计划" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批准最终审查" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成计划" })).toBeDisabled();
  });

  it("切换项目会清空旧任务上下文", async () => {
    const user = userEvent.setup();
    render(<App api={scriptedApi()} />);
    await createTrustedTask(user);
    expect(await screen.findByText("修复 add 的真实计划")).toBeVisible();
    await user.clear(screen.getByLabelText("项目路径"));
    await user.type(screen.getByLabelText("项目路径"), "C:\\second\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    expect(screen.queryByText("修复 add 的真实计划")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批准计划" })).not.toBeInTheDocument();
  });

  it("接入新项目失败后，不保留旧项目的信任与任务上下文", async () => {
    const user = userEvent.setup();
    const connectProject = vi.fn(async (path: string): Promise<Workspace> => { void path; return workspace; }).mockResolvedValueOnce(workspace).mockRejectedValueOnce(new Error("connect failed"));
    render(<App api={scriptedApi({ connectProject })} />);
    await createTrustedTask(user);
    await user.clear(screen.getByLabelText("项目路径"));
    await user.type(screen.getByLabelText("项目路径"), "C:\\second\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    expect(await screen.findByText("无法完成此操作。请检查服务状态后重试。")).toBeVisible();
    expect(screen.queryByText(/当前项目已建立信任/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批准计划" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成计划" })).toBeDisabled();
  });

  it("任务变更和状态收敛都失败时，清空旧任务并禁用变更控件", async () => {
    const user = userEvent.setup();
    const api = scriptedApi({ approvePlan: vi.fn(async (failedTaskId: string) => { void failedTaskId; throw new Error("mutation failed"); }), getTask: vi.fn(async (failedTaskId: string) => { void failedTaskId; throw new Error("get failed"); }) });
    render(<App api={api} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    expect(await screen.findByText("无法完成此操作。请检查服务状态后重试。")).toBeVisible();
    expect(screen.queryByRole("button", { name: "批准计划" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批准最终审查" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成计划" })).toBeDisabled();
  });
});
