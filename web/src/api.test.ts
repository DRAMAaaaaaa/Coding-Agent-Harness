import { describe, expect, it, vi } from "vitest";

import { createBrowserApi } from "./api";
import type { TaskEvent } from "./types";

const taskId = "00000000-0000-0000-0000-000000000001";
const event: TaskEvent = {
  task_id: taskId,
  sequence: 7,
  event_type: "PLAN_PROPOSED",
  payload: { content_sha256: "a".repeat(64), content_bytes: 12, diagnostic: "真实计划" },
  state_before: "PLANNING",
  state_after: "WAITING_PLAN_APPROVAL",
  occurred_at: "2026-07-30T00:00:00Z",
};

function json(value: object): Response {
  return new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
}

describe("Browser API adapter", () => {
  it("以真实 Task 7 形状消费 task-event、续传且关闭后不重连", () => {
    const listeners = new Map<string, (event: MessageEvent<string>) => void>();
    const source: {
      onopen: ((event: Event) => void) | null;
      onmessage: ((event: MessageEvent<string>) => void) | null;
      onerror: ((event: Event) => void) | null;
      addEventListener: (name: string, handler: (value: MessageEvent<string>) => void) => void;
      removeEventListener: (name: string, handler: (value: MessageEvent<string>) => void) => void;
      close: () => void;
    } = {
      onopen: null,
      onmessage: null,
      onerror: null,
      addEventListener: vi.fn((name: string, handler: (value: MessageEvent<string>) => void) => listeners.set(name, handler)),
      removeEventListener: vi.fn((name: string) => listeners.delete(name)),
      close: vi.fn(),
    };
    const factory = vi.fn(() => source);
    const api = createBrowserApi({ fetcher: vi.fn(), eventSourceFactory: factory, scheduleReconnect: (callback) => callback() });
    const received = vi.fn();
    const connection = vi.fn();

    const stop = api.subscribeEvents(taskId, 0, { onEvent: received, onConnection: connection });
    listeners.get("task-event")?.({ data: JSON.stringify(event) } as MessageEvent<string>);
    source.onerror?.(new Event("error"));

    expect(received).toHaveBeenCalledWith(event);
    expect(factory).toHaveBeenNthCalledWith(1, `/api/tasks/${taskId}/events?after=0`);
    expect(factory).toHaveBeenNthCalledWith(2, `/api/tasks/${taskId}/events?after=7`);
    stop();
    source.onerror?.(new Event("error"));
    expect(factory).toHaveBeenCalledTimes(2);
    expect(source.removeEventListener).toHaveBeenCalledWith("task-event", expect.any(Function));
  });

  it("为每个 mutation 使用同一会话和精确请求形状", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("Harness", { headers: { "X-Harness-Session": "session-1" } }))
      .mockResolvedValueOnce(json({ id: "workspace-1", default_branch: "main", languages: [], trust_fingerprint: "a".repeat(64), trusted: false }))
      .mockResolvedValueOnce(json({ id: "workspace-1", default_branch: "main", languages: [], trust_fingerprint: "a".repeat(64), trusted: true }))
      .mockResolvedValueOnce(json({ id: taskId, workspace_id: "workspace-1", state: "WAITING_PLAN_APPROVAL" }))
      .mockResolvedValueOnce(json({ id: taskId, workspace_id: "workspace-1", state: "DECIDING" }))
      .mockResolvedValueOnce(json({ id: taskId, workspace_id: "workspace-1", state: "WAITING_FINAL_REVIEW" }))
      .mockResolvedValueOnce(json({ id: taskId, workspace_id: "workspace-1", state: "COMPLETED" }));
    const api = createBrowserApi({ fetcher, eventSourceFactory: () => { throw new Error("unused"); } });

    const workspace = await api.connectProject("C:\\demo\\repo");
    await api.trustProject(workspace);
    await api.createTask(workspace.id, "修复 add 函数");
    await api.approvePlan(taskId);
    await api.runTask(taskId);
    await api.approveFinal(taskId);

    const options = (body: object) => ({ method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Harness-Session": "session-1" }, body: JSON.stringify(body) });
    expect(fetcher).toHaveBeenNthCalledWith(1, "/", { credentials: "same-origin" });
    expect(fetcher).toHaveBeenNthCalledWith(2, "/api/projects", options({ path: "C:\\demo\\repo" }));
    expect(fetcher).toHaveBeenNthCalledWith(3, "/api/projects/workspace-1/trust", options({ fingerprint: "a".repeat(64) }));
    expect(fetcher).toHaveBeenNthCalledWith(4, "/api/tasks", options({ workspace_id: "workspace-1", requirement: "修复 add 函数" }));
    expect(fetcher).toHaveBeenNthCalledWith(5, `/api/tasks/${taskId}/plan/approve`, options({}));
    expect(fetcher).toHaveBeenNthCalledWith(6, `/api/tasks/${taskId}/run`, options({}));
    expect(fetcher).toHaveBeenNthCalledWith(7, `/api/tasks/${taskId}/final/approve`, options({}));
  });
});
