import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { HarnessApi, ProjectLearningCard, TaskEvent, Workspace } from "./types";

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

async function goToStage(user: ReturnType<typeof userEvent.setup>, name: string): Promise<void> {
  await user.click(await screen.findByRole("button", { name }));
}

describe("App", () => {
  it("按信任、任务和执行证据自动推进，并允许回看", async () => {
    const user = userEvent.setup();
    render(<App api={scriptedApi({ events: [taskEvents[0]] })} />);

    expect(screen.getByRole("heading", { name: "项目接入" })).toBeVisible();
    expect(screen.getByRole("button", { name: "需求描述" })).toBeDisabled();
    await user.type(screen.getByLabelText("项目路径"), "C:\\demo\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    await user.click(await screen.findByRole("button", { name: "建立信任" }));
    expect(await screen.findByRole("heading", { name: "需求描述" })).toBeVisible();
    await user.type(screen.getByLabelText("编码需求"), "修复 add 函数");
    await user.click(screen.getByRole("button", { name: "生成计划" }));
    await goToStage(user, "计划审批");
    expect(await screen.findByRole("heading", { name: "计划审批" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "批准计划" }));
    expect(await screen.findByRole("heading", { name: "执行与验证" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "项目接入" }));
    expect(screen.getByRole("button", { name: "返回当前阶段" })).toBeVisible();
  });

  it("高级设置默认 Mock，关闭时清空 Key 并恢复焦点", async () => {
    const user = userEvent.setup();
    render(<App api={{ ...scriptedApi(), listProviders: vi.fn(async () => []), createProvider: vi.fn(), setSessionCredential: vi.fn() }} />);

    const opener = screen.getByRole("button", { name: "高级设置" });
    await user.click(opener);
    expect(screen.getByRole("dialog", { name: "Provider 高级设置" })).toBeVisible();
    await user.type(screen.getByLabelText("API Key"), "test-session-key");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Provider 高级设置" })).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
    await user.click(opener);
    expect(screen.getByLabelText("API Key")).toHaveValue("");
    expect(screen.getByText(/没有连接测试和主动清除/)).toBeVisible();
  });

  it("技术详情默认折叠，展开后显示原始事件", async () => {
    const user = userEvent.setup();
    render(<App api={scriptedApi()} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "交付与经验");
    await user.click(await screen.findByRole("button", { name: "执行与验证" }));
    const details = screen.getByText("技术详情").closest("details");
    expect(details).not.toHaveAttribute("open");
    await user.click(screen.getByText("技术详情"));
    expect(screen.getAllByRole("listitem").find((item) => item.textContent?.includes("VERIFICATION_SUCCEEDED"))).toBeVisible();
  });

  it("只在最终交付卡中由用户批准经验，并在下一任务入口展示已批准卡", async () => {
    const user = userEvent.setup();
    const approvedCard = { id: "learning-1", workspace_id: workspace.id, text: "先运行聚焦测试", source_task_id: taskId, source_event_sequence: 5, approved_at: "2026-08-07T00:00:00Z" };
    const approveProjectLearning = vi.fn(async () => approvedCard);
    const getLatestProjectLearning = vi.fn(async () => approvedCard);
    const api = {
      ...scriptedApi(),
      getIntentCards: vi.fn(async () => [{ id: "final-card", task_id: taskId, kind: "final_delivery" as const, intent: "交付", evidence_sequences: [5], action: "批准", expected_result: "保存", actual_result: "完成", status: "ready", source_event_sequence: 5, learning_card_id: null }]),
      approveProjectLearning,
      getLatestProjectLearning,
    };
    render(<App api={api} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "交付与经验");
    await user.click(await screen.findByRole("button", { name: "批准最终审查" }));
    const learningInput = await screen.findByLabelText("项目经验");
    expect(learningInput).toHaveValue("add 已修复");
    await user.clear(learningInput);
    await user.type(learningInput, approvedCard.text);
    await user.click(screen.getByRole("button", { name: "批准经验" }));
    expect(approveProjectLearning).toHaveBeenCalledWith(taskId, 5, approvedCard.text);
    await goToStage(user, "需求描述");
    expect(await screen.findByText(`经验 ID：${approvedCard.id}`)).toBeVisible();
    expect(screen.getByLabelText("下一任务项目经验")).toHaveTextContent(approvedCard.text);
  });

  it("失败卡可创建纠正分支并展示并排比较", async () => {
    const user = userEvent.setup();
    const createCorrectionBranch = vi.fn(async () => ({ id: "branch-1", workspace_id: workspace.id, parent_task_id: taskId, source_event_sequence: 1, child_task_id: "child-1", status: "READY" as const, created_at: "2026-08-07T00:00:00Z" }));
    const getCorrectionComparison = vi.fn(async () => ({ branch_id: "branch-1", parent_state: "WAITING_USER", child_state: "WAITING_FINAL_REVIEW", parent_verification: "parent failed", child_verification: "child passed", parent_diff: "- old", child_diff: "+ new" }));
    const api = { ...scriptedApi({ events: [taskEvents[0], event(2, "VERIFICATION_FAILED", { reason_code: "TEST_FAILURE" }, "WAITING_USER", "WAITING_USER")] }), getIntentCards: vi.fn(async () => [{ id: "failure-card", task_id: taskId, kind: "verification_failure" as const, intent: "verification_failure", evidence_sequences: [2], action: "VERIFICATION_FAILED", expected_result: "通过", actual_result: "失败", status: "recorded", source_event_sequence: 2, learning_card_id: null }]), createCorrectionBranch, getCorrectionComparison };
    render(<App api={api} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "回放与纠正");
    expect(await screen.findByText("VERIFICATION_FAILED")).toBeVisible();
    expect(screen.getByText("通过")).toBeVisible();
    expect(screen.getByText("recorded")).toBeVisible();
    expect(screen.getByText("2")).toBeVisible();
    await user.type(await screen.findByLabelText("纠正说明"), "补充边界");
    await user.click(screen.getByRole("button", { name: "从此纠正" }));
    expect(createCorrectionBranch).toHaveBeenCalledWith(taskId, 2, "补充边界");
    await Promise.resolve();
    await goToStage(user, "回放与纠正");
    expect(await screen.findByText(/child passed/)).toBeVisible();
    expect(screen.getByText("+ new")).toBeVisible();
  });

  it("创建纠正分支失败后保留用户的纠正说明", async () => {
    const user = userEvent.setup();
    const api = {
      ...scriptedApi({ events: [taskEvents[0], event(2, "VERIFICATION_FAILED", { reason_code: "TEST_FAILURE" }, "WAITING_USER", "WAITING_USER")] }),
      getIntentCards: vi.fn(async () => [{ id: "failure-card", task_id: taskId, kind: "verification_failure" as const, intent: "失败", evidence_sequences: [2], action: "验证", expected_result: "通过", actual_result: "失败", status: "recorded", source_event_sequence: 2, learning_card_id: null }]),
      createCorrectionBranch: vi.fn(async () => { throw new Error("offline"); }),
      getCorrectionComparison: vi.fn(),
    };
    render(<App api={api} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "回放与纠正");
    const correction = await screen.findByLabelText("纠正说明");
    await user.type(correction, "保留我的思路");
    await user.click(screen.getByRole("button", { name: "从此纠正" }));
    expect(await screen.findByRole("status")).toBeVisible();
    expect(screen.getByLabelText("纠正说明")).toHaveValue("保留我的思路");
  });

  it("分支已创建但比较请求失败后不重复显示纠正入口", async () => {
    const user = userEvent.setup();
    const api = {
      ...scriptedApi({ events: [taskEvents[0], event(2, "VERIFICATION_FAILED", { reason_code: "TEST_FAILURE" }, "WAITING_USER", "WAITING_USER")] }),
      getIntentCards: vi.fn(async () => [{ id: "failure-card", task_id: taskId, kind: "verification_failure" as const, intent: "失败", evidence_sequences: [2], action: "验证", expected_result: "通过", actual_result: "失败", status: "recorded", source_event_sequence: 2, learning_card_id: null }]),
      createCorrectionBranch: vi.fn(async () => ({ id: "branch-1", workspace_id: workspace.id, parent_task_id: taskId, source_event_sequence: 2, child_task_id: null, status: "READY" as const, created_at: "2026-08-14T00:00:00Z" })),
      getCorrectionComparison: vi.fn(async () => { throw new Error("comparison offline"); }),
    };
    render(<App api={api} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "回放与纠正");
    await user.type(await screen.findByLabelText("纠正说明"), "创建之后不重复");
    await user.click(screen.getByRole("button", { name: "从此纠正" }));
    await Promise.resolve();
    expect(screen.queryByLabelText("纠正说明")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "从此纠正" })).not.toBeInTheDocument();
  });

  it("比较立即 reject 且子任务获取失败时不留下未处理 rejection", async () => {
    const user = userEvent.setup();
    let rejectChild: ((reason?: unknown) => void) | undefined;
    let comparisonRejectionHandled = false;
    let childFetchSawComparisonHandler = false;
    const child = new Promise<never>((_resolve, reject) => { rejectChild = reject; });
    const immediateRejectedComparison = {
      then: (_resolve: (value: never) => unknown, reject: (reason: unknown) => unknown) => {
        comparisonRejectionHandled = true;
        reject(new Error("comparison offline"));
        return Promise.resolve(undefined);
      },
    } as unknown as Promise<never>;
    const api = {
      ...scriptedApi({ events: [taskEvents[0], event(2, "VERIFICATION_FAILED", { reason_code: "TEST_FAILURE" }, "WAITING_USER", "WAITING_USER")] }),
      getIntentCards: vi.fn(async () => [{ id: "failure-card", task_id: taskId, kind: "verification_failure" as const, intent: "失败", evidence_sequences: [2], action: "验证", expected_result: "通过", actual_result: "失败", status: "recorded", source_event_sequence: 2, learning_card_id: null }]),
      createCorrectionBranch: vi.fn(async () => ({ id: "branch-1", workspace_id: workspace.id, parent_task_id: taskId, source_event_sequence: 2, child_task_id: "child-1", status: "READY" as const, created_at: "2026-08-14T00:00:00Z" })),
      getCorrectionComparison: vi.fn(() => immediateRejectedComparison),
      getTask: vi.fn(async (): Promise<{ id: string; workspace_id: string; state: "WAITING_PLAN_APPROVAL" }> => { childFetchSawComparisonHandler = comparisonRejectionHandled; return await child; }),
    };
    render(<App api={api} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "回放与纠正");
    await user.type(await screen.findByLabelText("纠正说明"), "保持收口");
    await user.click(screen.getByRole("button", { name: "从此纠正" }));
    rejectChild?.(new Error("child unavailable"));
    expect(await screen.findByRole("status")).toBeVisible();
    expect(childFetchSawComparisonHandler).toBe(true);
  });

  it("新项目建立后忽略旧纠正分支的慢比较结果", async () => {
    const user = userEvent.setup();
    let resolveComparison: ((value: { branch_id: string; parent_state: string; child_state: string | null; parent_verification: string | null; child_verification: string | null; parent_diff: string; child_diff: string | null }) => void) | undefined;
    const comparison = new Promise<{ branch_id: string; parent_state: string; child_state: string | null; parent_verification: string | null; child_verification: string | null; parent_diff: string; child_diff: string | null }>((resolve) => { resolveComparison = resolve; });
    const api = {
      ...scriptedApi({ events: [taskEvents[0], event(2, "VERIFICATION_FAILED", { reason_code: "TEST_FAILURE" }, "WAITING_USER", "WAITING_USER")], connectProject: vi.fn(async (path: string) => ({ ...workspace, id: path.includes("new") ? "workspace-new" : workspace.id, trusted: path.includes("new") })) }),
      getIntentCards: vi.fn(async () => [{ id: "failure-card", task_id: taskId, kind: "verification_failure" as const, intent: "失败", evidence_sequences: [2], action: "验证", expected_result: "通过", actual_result: "失败", status: "recorded", source_event_sequence: 2, learning_card_id: null }]),
      createCorrectionBranch: vi.fn(async () => ({ id: "branch-1", workspace_id: workspace.id, parent_task_id: taskId, source_event_sequence: 2, child_task_id: null, status: "READY" as const, created_at: "2026-08-14T00:00:00Z" })),
      getCorrectionComparison: vi.fn(async () => await comparison),
    };
    render(<App api={api} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "回放与纠正");
    await user.type(await screen.findByLabelText("纠正说明"), "旧比较");
    await user.click(screen.getByRole("button", { name: "从此纠正" }));
    await goToStage(user, "项目接入");
    const path = screen.getByLabelText("项目路径");
    await user.clear(path);
    await user.type(path, "C:\\new\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    await user.click(await screen.findByRole("button", { name: "生成计划" }));
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "回放与纠正");
    await act(async () => {
      resolveComparison?.({ branch_id: "branch-1", parent_state: "WAITING_USER", child_state: null, parent_verification: "旧比较失败", child_verification: null, parent_diff: "- old", child_diff: null });
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.queryByText(/旧比较失败/)).not.toBeInTheDocument();
  });

  it("新任务不预填旧任务的提问和纠正说明", async () => {
    const user = userEvent.setup();
    const secondTask = { id: "00000000-0000-0000-0000-000000000002", workspace_id: workspace.id, state: "WAITING_PLAN_APPROVAL" as const };
    const api = {
      ...scriptedApi({ events: [taskEvents[0], event(2, "VERIFICATION_FAILED", { reason_code: "TEST_FAILURE" }, "WAITING_USER", "WAITING_USER")] }),
      createTask: vi.fn().mockResolvedValueOnce({ id: taskId, workspace_id: workspace.id, state: "WAITING_PLAN_APPROVAL" as const }).mockResolvedValueOnce(secondTask),
      getIntentCards: vi.fn(async () => [{ id: "failure-card", task_id: taskId, kind: "verification_failure" as const, intent: "失败", evidence_sequences: [2], action: "验证", expected_result: "通过", actual_result: "失败", status: "recorded", source_event_sequence: 2, learning_card_id: null }]),
    };
    render(<App api={api} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "回放与纠正");
    await user.type(await screen.findByLabelText("失败原因提问"), "旧任务的问题");
    await user.type(await screen.findByLabelText("纠正说明"), "旧任务的纠正");
    await goToStage(user, "需求描述");
    const requirement = screen.getByLabelText("编码需求");
    await user.clear(requirement);
    await user.type(requirement, "新任务");
    await user.click(screen.getByRole("button", { name: "生成计划" }));
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "回放与纠正");
    expect(await screen.findByLabelText("失败原因提问")).toHaveValue("");
    expect(screen.getByLabelText("纠正说明")).toHaveValue("");
  });

  it("纠正分支切换子任务时清空父证据，子计划事件到达前不可批准", async () => {
    const user = userEvent.setup();
    let resolveComparison: ((value: never) => void) | undefined;
    const comparison = new Promise<never>((resolve) => { resolveComparison = resolve; });
    const childTask = { id: "child-1", workspace_id: workspace.id, state: "WAITING_PLAN_APPROVAL" as const };
    const api = {
      ...scriptedApi({ events: [taskEvents[0], event(2, "VERIFICATION_FAILED", { reason_code: "TEST_FAILURE" }, "WAITING_USER", "WAITING_USER")] }),
      getIntentCards: vi.fn(async () => [{ id: "failure-card", task_id: taskId, kind: "verification_failure" as const, intent: "失败", evidence_sequences: [2], action: "验证", expected_result: "通过", actual_result: "失败", status: "recorded", source_event_sequence: 2, learning_card_id: null }]),
      createCorrectionBranch: vi.fn(async () => ({ id: "branch-1", workspace_id: workspace.id, parent_task_id: taskId, source_event_sequence: 2, child_task_id: childTask.id, status: "READY" as const, created_at: "2026-08-14T00:00:00Z" })),
      getCorrectionComparison: vi.fn(async () => await comparison),
      getTask: vi.fn(async (id: string) => id === childTask.id ? childTask : { id: taskId, workspace_id: workspace.id, state: "WAITING_FINAL_REVIEW" as const }),
    };
    api.subscribeEvents = (id, _after, listener) => { if (id === taskId) { [taskEvents[0], event(2, "VERIFICATION_FAILED", { reason_code: "TEST_FAILURE" }, "WAITING_USER", "WAITING_USER")].forEach(listener.onEvent); } listener.onConnection("connected"); return () => undefined; };
    render(<App api={api} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "回放与纠正");
    await user.type(await screen.findByLabelText("纠正说明"), "补充边界");
    await user.click(screen.getByRole("button", { name: "从此纠正" }));
    await goToStage(user, "计划审批");
    expect(await screen.findByRole("heading", { name: "计划审批" })).toBeVisible();
    expect(screen.queryByText("修复 add 的真实计划")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批准计划" })).not.toBeInTheDocument();
    expect(resolveComparison).toBeDefined();
  });

  it("切换项目时不让慢速项目经验回写到新项目", async () => {
    const user = userEvent.setup();
    let resolveA: ((value: { id: string; workspace_id: string; text: string; source_task_id: string; source_event_sequence: number; approved_at: string } | null) => void) | undefined;
    let resolveB: ((value: { id: string; workspace_id: string; text: string; source_task_id: string; source_event_sequence: number; approved_at: string } | null) => void) | undefined;
    const api = scriptedApi({ connectProject: vi.fn(async (path: string) => ({ ...workspace, id: path.includes("second") ? "workspace-b" : "workspace-a", trusted: true })) });
    api.getLatestProjectLearning = vi.fn((id: string): Promise<ProjectLearningCard | null> => new Promise((resolve) => { if (id === "workspace-a") resolveA = resolve; else resolveB = resolve; }));
    render(<App api={api} />);
    await user.type(screen.getByLabelText("项目路径"), "C:\\first\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    await goToStage(user, "项目接入");
    await user.clear(screen.getByLabelText("项目路径"));
    await user.type(screen.getByLabelText("项目路径"), "C:\\second\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    resolveA?.({ id: "old", workspace_id: "workspace-a", text: "旧项目经验", source_task_id: taskId, source_event_sequence: 1, approved_at: "2026-08-14T00:00:00Z" });
    await Promise.resolve();
    expect(screen.queryByText("旧项目经验")).not.toBeInTheDocument();
    resolveB?.({ id: "new", workspace_id: "workspace-b", text: "新项目经验", source_task_id: taskId, source_event_sequence: 1, approved_at: "2026-08-14T00:00:00Z" });
    expect(await screen.findByText("新项目经验")).toBeVisible();
  });

  it("SSE 重连时保留已解锁阶段回看并禁用任务变更", async () => {
    const user = userEvent.setup();
    const api = scriptedApi({ events: [taskEvents[0]] });
    api.subscribeEvents = (_id, _after, listener) => { listener.onEvent(taskEvents[0]); listener.onConnection("reconnecting"); return () => undefined; };
    render(<App api={api} />);
    await createTrustedTask(user);
    expect(await screen.findByText(/正在重连/)).toBeVisible();
    expect(screen.getByRole("button", { name: "批准计划" })).toBeDisabled();
    await goToStage(user, "项目接入");
    expect(screen.getByRole("heading", { name: "项目接入" })).toBeVisible();
  });

  it("仅为失败卡展示只读提问并显示回答", async () => {
    const user = userEvent.setup();
    const askQuestion = vi.fn(async () => ({ content: "Stub explanation" }));
    const api = { ...scriptedApi({ events: [taskEvents[0], event(2, "VERIFICATION_FAILED", { reason_code: "TEST_FAILURE" }, "WAITING_USER", "WAITING_USER")] }), getIntentCards: vi.fn(async () => [{ id: "failure-card", task_id: taskId, kind: "verification_failure" as const, intent: "verification_failure", evidence_sequences: [2], action: "VERIFICATION_FAILED", expected_result: "验证通过", actual_result: "失败", status: "recorded", source_event_sequence: 2, learning_card_id: null }]), askQuestion };
    render(<App api={api} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "回放与纠正");
    await user.type(await screen.findByLabelText("失败原因提问"), "为什么失败？");
    await user.click(screen.getByRole("button", { name: "提问" }));
    expect(askQuestion).toHaveBeenCalledWith(taskId, "failure-card", "为什么失败？");
    expect(await screen.findByText("Stub explanation")).toBeVisible();
  });

  it("会话 Provider 密钥使用 password 输入，并在配置后清空", async () => {
    const user = userEvent.setup();
    const createProvider = vi.fn(async () => ({ id: "provider-1", kind: "deepseek" as const, model: "deepseek-chat", version: 1, configured: false }));
    const setSessionCredential = vi.fn(async () => ({ id: "provider-1", kind: "deepseek" as const, model: "deepseek-chat", version: 1, configured: true }));
    render(<App api={{ ...scriptedApi(), listProviders: vi.fn(async () => []), createProvider, setSessionCredential }} />);

    await user.click(screen.getByRole("button", { name: "高级设置" }));
    const key = screen.getByLabelText("API Key");
    expect(key).toHaveAttribute("type", "password");
    await user.type(key, "test-session-key");
    await user.click(screen.getByRole("button", { name: "配置会话 Provider" }));

    expect(await screen.findByRole("option", { name: "deepseek: deepseek-chat" })).toBeVisible();
    expect(setSessionCredential).toHaveBeenCalledWith("provider-1", "test-session-key");
    await user.click(screen.getByRole("button", { name: "高级设置" }));
    expect(screen.getByLabelText("API Key")).toHaveValue("");
  });

  it("会话 Provider 密钥在配置失败和切换项目后均清空", async () => {
    const user = userEvent.setup();
    const api = { ...scriptedApi(), listProviders: vi.fn(async () => []), createProvider: vi.fn(async () => { throw new Error("offline"); }), setSessionCredential: vi.fn() };
    render(<App api={api} />);
    await user.click(screen.getByRole("button", { name: "高级设置" }));
    const key = screen.getByLabelText("API Key");
    await user.type(key, "test-session-key");
    await user.click(screen.getByRole("button", { name: "配置会话 Provider" }));
    expect(await screen.findByRole("status")).toBeVisible();
    expect(key).toHaveValue("");
    await user.type(key, "another-test-key");
    await user.keyboard("{Escape}");
    await user.type(screen.getByLabelText("项目路径"), "C:\\demo\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    await user.click(screen.getByRole("button", { name: "高级设置" }));
    expect(screen.getByLabelText("API Key")).toHaveValue("");
  });

  it("任务创建失败也清空会话 Provider 密钥", async () => {
    const user = userEvent.setup();
    const api = { ...scriptedApi({ connectProject: vi.fn(async () => ({ ...workspace, trusted: true })) }), listProviders: vi.fn(async () => [{ id: "provider-1", kind: "deepseek" as const, model: "deepseek-chat", version: 1, configured: true }]), createProvider: vi.fn(), setSessionCredential: vi.fn(), createTask: vi.fn(async () => { throw new Error("offline"); }) };
    render(<App api={api} />);
    await user.type(screen.getByLabelText("项目路径"), "C:\\demo\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    await user.click(screen.getByRole("button", { name: "高级设置" }));
    await user.type(screen.getByLabelText("API Key"), "test-session-key");
    await user.selectOptions(screen.getByLabelText("已配置 Profile"), "provider-1");
    await user.keyboard("{Escape}");
    await user.type(screen.getByLabelText("编码需求"), "修复失败");
    await user.click(screen.getByRole("button", { name: "生成计划" }));
    expect(await screen.findByRole("status")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "高级设置" }));
    expect(screen.getByLabelText("API Key")).toHaveValue("");
  });
  it("展示真实计划、验证和 diff，并完成最终批准", async () => {
    const user = userEvent.setup();
    const api = scriptedApi();
    render(<App api={api} />);
    await createTrustedTask(user);
    expect(await screen.findByText("修复 add 的真实计划")).toBeVisible();
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "交付与经验");
    expect(screen.getByText("1 passed")).toBeVisible();
    expect(screen.getByText("diff --git a/src/add.py")).toBeVisible();
    await user.click(await screen.findByRole("button", { name: "批准最终审查" }));
    expect(api.approveFinal).toHaveBeenCalledWith(taskId);
  });

  it("只显示最新一轮修改后的验证、diff 与最终摘要", async () => {
    const user = userEvent.setup();
    render(<App api={scriptedApi({ events: latestTaskEvents })} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
    await goToStage(user, "交付与经验");
    expect(await screen.findByText("第二轮通过")).toBeVisible();
    expect(screen.getByText(/diff --git a\/src\/add\.py\s+\+new/)).toBeVisible();
    expect(screen.queryByText("旧轮次通过")).not.toBeInTheDocument();
    expect(screen.queryByText(/diff --git a\/src\/add\.py\s+-old/)).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "批准最终审查" })).toBeVisible();
  });

  it("新一轮修改没有验证时，旧验证不能用于最终批准", async () => {
    const user = userEvent.setup();
    render(<App api={scriptedApi({ events: latestTaskEvents.filter((item) => item.sequence !== 9) })} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
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
    expect(await screen.findByText(/计划内容不完整/)).toBeVisible();
  });

  it.each([
    ["缺少当前 diff", taskEvents.filter((item) => item.event_type !== "TOOL_EXECUTION_COMPLETED")],
    ["缺少当前最终摘要", taskEvents.filter((item) => item.event_type !== "FINAL_SUMMARY_PROPOSED")],
    ["diff 已截断", taskEvents.map((item) => item.event_type === "TOOL_EXECUTION_COMPLETED" ? event(item.sequence, item.event_type, { execution_id: "diff-1", result: { ok: true, ...content(`[OUTPUT_LIMIT bytes=5000 sha256=${"b".repeat(64)}]`) } }, item.state_before, item.state_after) : item)],
  ])("%s 时不可最终批准", async (_name, events) => {
    const user = userEvent.setup();
    render(<App api={scriptedApi({ events })} />);
    await createTrustedTask(user);
    await user.click(await screen.findByRole("button", { name: "批准计划" }));
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
    await goToStage(user, "需求描述");
    expect(screen.getByRole("button", { name: "生成计划" })).toBeDisabled();
  });

  it("切换项目会清空旧任务上下文", async () => {
    const user = userEvent.setup();
    render(<App api={scriptedApi()} />);
    await createTrustedTask(user);
    expect(await screen.findByText("修复 add 的真实计划")).toBeVisible();
    await goToStage(user, "项目接入");
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
    await goToStage(user, "项目接入");
    await user.clear(screen.getByLabelText("项目路径"));
    await user.type(screen.getByLabelText("项目路径"), "C:\\second\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    expect(await screen.findByText("无法完成此操作。请检查服务状态后重试。")).toBeVisible();
    expect(screen.queryByText(/当前项目已建立信任/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批准计划" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "需求描述" })).toBeDisabled();
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
    await goToStage(user, "需求描述");
    expect(screen.getByRole("button", { name: "生成计划" })).toBeDisabled();
  });
});
