import { describe, expect, it } from "vitest";
import type { IntentCard, Task, TaskEvent, Workspace } from "../types";
import {
  STAGES, advanceSelectedStage, completeDiagnostic, deriveEvidence,
  latestAvailableStage, unlockedStages,
} from "./workflow";

const workspace = (trusted: boolean): Workspace => ({
  id: "workspace-1", default_branch: "main", languages: ["Python"],
  trust_fingerprint: "a".repeat(64), trusted,
});
const task = (state: Task["state"]): Task => ({ id: "task-1", workspace_id: "workspace-1", state });
const event = (sequence: number, event_type: string, payload: Record<string, unknown>): TaskEvent => ({
  task_id: "task-1", sequence, event_type, payload,
  state_before: "EXECUTING", state_after: "EXECUTING",
  occurred_at: `2026-08-14T00:00:${String(sequence).padStart(2, "0")}Z`,
});
const content = (diagnostic: string) => ({
  diagnostic, content_sha256: "b".repeat(64),
  content_bytes: new TextEncoder().encode(diagnostic).length,
});

describe("六阶段工作流", () => {
  it.each([
    [{}, ["PROJECT"]],
    [{ workspace: workspace(false) }, ["PROJECT"]],
    [{ workspace: workspace(true) }, ["PROJECT", "REQUIREMENT"]],
    [{ workspace: workspace(true), task: task("WAITING_PLAN_APPROVAL") }, ["PROJECT", "REQUIREMENT", "PLAN"]],
    [{ workspace: workspace(true), task: task("EXECUTING") }, ["PROJECT", "REQUIREMENT", "PLAN", "EXECUTION"]],
    [{ workspace: workspace(true), task: task("WAITING_USER") }, ["PROJECT", "REQUIREMENT", "PLAN", "EXECUTION", "REPLAY"]],
  ])("按证据解锁 %#", (snapshot, expected) => {
    expect(unlockedStages({ events: [], cards: [], ...snapshot })).toEqual(expected);
  });

  it("意图卡、失败或治理阻塞解锁回放", () => {
    const base = { workspace: workspace(true), task: task("EXECUTING") };
    const card = { kind: "plan" } as IntentCard;
    expect(latestAvailableStage({ ...base, events: [], cards: [card] })).toBe("REPLAY");
    expect(latestAvailableStage({ ...base, events: [event(1, "VERIFICATION_FAILED", {})], cards: [] })).toBe("REPLAY");
    expect(latestAvailableStage({ ...base, events: [event(1, "GOVERNANCE_BLOCKED", {})], cards: [] })).toBe("REPLAY");
  });

  it("只有最新轮次完整验证、diff 和摘要解锁交付", () => {
    const events = [
      event(1, "TOOL_EXECUTION_STARTED", { execution_id: "write", action: { tool: "apply_patch" } }),
      event(2, "TOOL_EXECUTION_COMPLETED", { execution_id: "write", result: { ok: true, changed_paths: ["src/a.py"] } }),
      event(3, "VERIFICATION_SUCCEEDED", { run: { ok: true, diagnostic: "1 passed" } }),
      event(4, "TOOL_EXECUTION_STARTED", { execution_id: "diff", action: { tool: "git_diff" } }),
      event(5, "TOOL_EXECUTION_COMPLETED", { execution_id: "diff", result: { ok: true, ...content("+new") } }),
      event(6, "FINAL_SUMMARY_PROPOSED", content("完成")),
    ];
    const snapshot = { workspace: workspace(true), task: task("WAITING_FINAL_REVIEW"), events, cards: [] };
    expect(deriveEvidence(events)).toMatchObject({ verificationDiagnostic: "1 passed", diffDiagnostic: "+new", finalDiagnostic: "完成" });
    expect(latestAvailableStage(snapshot)).toBe("DELIVERY");
    expect(latestAvailableStage({ ...snapshot, events: events.filter((item) => item.sequence !== 3) })).toBe("REPLAY");
  });

  it("新修改使旧验证和旧 diff 失效", () => {
    const events = [
      event(1, "VERIFICATION_SUCCEEDED", { run: { ok: true, diagnostic: "旧通过" } }),
      event(2, "TOOL_EXECUTION_STARTED", { execution_id: "diff", action: { tool: "git_diff" } }),
      event(3, "TOOL_EXECUTION_COMPLETED", { execution_id: "diff", result: { ok: true, ...content("旧 diff") } }),
      event(4, "TOOL_EXECUTION_COMPLETED", { execution_id: "write", result: { ok: true, changed_paths: ["src/a.py"] } }),
      event(5, "FINAL_SUMMARY_PROPOSED", content("摘要")),
    ];
    expect(deriveEvidence(events)).toMatchObject({ verificationDiagnostic: undefined, diffDiagnostic: undefined });
  });

  it("完整当前轮次证据解锁交付", () => {
    const events = [
      event(1, "VERIFICATION_SUCCEEDED", { run: { ok: true, diagnostic: "通过" } }),
      event(2, "TOOL_EXECUTION_STARTED", { execution_id: "diff", action: { tool: "git_diff" } }),
      event(3, "TOOL_EXECUTION_COMPLETED", { execution_id: "diff", result: { ok: true, ...content("diff") } }),
      event(4, "FINAL_SUMMARY_PROPOSED", content("摘要")),
    ];
    expect(latestAvailableStage({ workspace: workspace(true), task: task("EXECUTING"), events, cards: [] })).toBe("DELIVERY");
  });

  it("较晚的验证或 diff 使更早摘要失效", () => {
    const events = [
      event(1, "FINAL_SUMMARY_PROPOSED", content("旧摘要")),
      event(2, "VERIFICATION_SUCCEEDED", { run: { ok: true, diagnostic: "新验证" } }),
      event(3, "TOOL_EXECUTION_STARTED", { execution_id: "diff", action: { tool: "git_diff" } }),
      event(4, "TOOL_EXECUTION_COMPLETED", { execution_id: "diff", result: { ok: true, ...content("新 diff") } }),
    ];
    expect(deriveEvidence(events)).toMatchObject({ finalDiagnostic: undefined });
    expect(latestAvailableStage({ workspace: workspace(true), task: task("EXECUTING"), events, cards: [] })).toBe("EXECUTION");
  });

  it.each([content(""), content(`[OUTPUT_LIMIT bytes=4 sha256=${"c".repeat(64)}]`), { ...content("计划"), content_bytes: 1 }])(
    "拒绝不完整内容 %#", (payload) => expect(completeDiagnostic(payload)).toBeUndefined(),
  );

  it.each(["   ", ` \t[OUTPUT_LIMIT bytes=4 sha256=${"c".repeat(64)}]`])(
    "拒绝空白或带前置空白的截断诊断 %#", (diagnostic) => {
      expect(completeDiagnostic(content(diagnostic))).toBeUndefined();
      expect(deriveEvidence([event(1, "VERIFICATION_SUCCEEDED", { run: { ok: true, diagnostic } })]).verificationDiagnostic).toBeUndefined();
    },
  );

  it("按实际时间而非带偏移字符串排序，并稳定保留完全相同时间的输入顺序", () => {
    const early = { ...event(10, "PLAN_PROPOSED", content("真实较早")), occurred_at: "2026-08-14T00:30:00+09:00" };
    const late = { ...event(10, "PLAN_PROPOSED", content("真实较晚")), occurred_at: "2026-08-13T16:00:00Z" };
    expect(deriveEvidence([late, early]).planDiagnostic).toBe("真实较晚");

    const sameTime = "2026-08-14T00:00:00Z";
    const first = { ...event(11, "PLAN_PROPOSED", content("先到")), occurred_at: sameTime };
    const second = { ...event(11, "PLAN_PROPOSED", content("后到")), occurred_at: sameTime };
    expect(deriveEvidence([first, second]).planDiagnostic).toBe("后到");
  });

  it("自动推进不覆盖历史回看", () => {
    expect(advanceSelectedStage("PLAN", "PLAN", "EXECUTION")).toBe("EXECUTION");
    expect(advanceSelectedStage("PROJECT", "PLAN", "EXECUTION")).toBe("PROJECT");
  });

  it("阶段顺序固定", () => {
    expect(STAGES.map((stage) => stage.id)).toEqual([
      "PROJECT", "REQUIREMENT", "PLAN", "EXECUTION", "REPLAY", "DELIVERY",
    ]);
  });
});
