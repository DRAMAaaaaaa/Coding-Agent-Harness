import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import type { HarnessApi, TaskEvent } from "./types";

function scriptedApi(): HarnessApi {
  const taskId = "00000000-0000-0000-0000-000000000001";
  const events: TaskEvent[] = [
    {
      sequence: 1,
      event_type: "PLAN_PROPOSED",
      state_before: "PLANNING",
      state_after: "WAITING_PLAN_APPROVAL",
      occurred_at: "2026-07-30T00:00:00Z",
      payload: { summary: "修复 add 函数" },
    },
    {
      sequence: 2,
      event_type: "VERIFICATION_PASSED",
      state_before: "EXECUTING",
      state_after: "WAITING_FINAL_APPROVAL",
      occurred_at: "2026-07-30T00:01:00Z",
      payload: { summary: "测试已通过", diff_summary: "src/math.ts 已修改" },
    },
  ];

  return {
    connectProject: async () => ({
      id: "00000000-0000-0000-0000-000000000010",
      default_branch: "main",
      languages: ["Python"],
      trust_fingerprint: "a".repeat(64),
      trusted: false,
      repository: { tracked_count: 4, test_count: 1, dirty_count: 0, test_paths: ["tests/test_math.py"] },
    }),
    trustProject: async (workspace) => ({ ...workspace, trusted: true }),
    createTask: async () => ({ id: taskId, workspace_id: "00000000-0000-0000-0000-000000000010", state: "WAITING_PLAN_APPROVAL" }),
    approvePlan: async () => ({ id: taskId, workspace_id: "00000000-0000-0000-0000-000000000010", state: "EXECUTING" }),
    runTask: async () => ({ id: taskId, workspace_id: "00000000-0000-0000-0000-000000000010", state: "WAITING_FINAL_APPROVAL" }),
    approveFinal: async () => ({ id: taskId, workspace_id: "00000000-0000-0000-0000-000000000010", state: "COMPLETED" }),
    getTask: async () => ({ id: taskId, workspace_id: "00000000-0000-0000-0000-000000000010", state: "WAITING_FINAL_APPROVAL" }),
    subscribeEvents: (_taskId, _after, listener) => {
      events.forEach(listener.onEvent);
      listener.onConnection("connected");
      return () => undefined;
    },
  };
}

describe("App", () => {
  it("从项目接入运行到最终 diff", async () => {
    const user = userEvent.setup();
    render(<App api={scriptedApi()} />);

    await user.type(screen.getByLabelText("项目路径"), "C:\\demo\\repo");
    await user.click(screen.getByRole("button", { name: "接入项目" }));
    expect(await screen.findByText("Python · main")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "建立信任" }));
    await user.type(screen.getByLabelText("编码需求"), "修复 add 函数");
    await user.click(screen.getByRole("button", { name: "生成计划" }));
    await user.click(await screen.findByRole("button", { name: "批准计划" }));

    expect(await screen.findByText("测试已通过")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "最终差异" })).toBeVisible();
    expect(screen.getByText("后端尚无可提交操作")).toBeVisible();
  });
});
