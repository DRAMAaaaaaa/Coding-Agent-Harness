import { describe, expect, it, vi } from "vitest";

import { createBrowserApi } from "./api";

describe("Browser API adapter", () => {
  it("引导会话并以精确形状发送所有 mutation", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("Harness", { headers: { "X-Harness-Session": "session-1" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "workspace-1", default_branch: "main", languages: [], trust_fingerprint: "a".repeat(64), trusted: false }), { headers: { "Content-Type": "application/json" } }));
    const api = createBrowserApi({ fetcher, eventSourceFactory: () => { throw new Error("unused"); } });

    await api.connectProject("C:\\demo\\repo");

    expect(fetcher).toHaveBeenNthCalledWith(1, "/", { credentials: "same-origin" });
    expect(fetcher).toHaveBeenNthCalledWith(2, "/api/projects", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Harness-Session": "session-1" },
      body: JSON.stringify({ path: "C:\\demo\\repo" }),
    });
  });

  it("断线后按最后事件序号重连", () => {
    const sources: Array<{ onmessage: ((event: MessageEvent<string>) => void) | null; onerror: (() => void) | null; close: () => void }> = [];
    const factory = vi.fn(() => {
      const source = { onopen: null, onmessage: null, onerror: null, close: vi.fn() };
      sources.push(source);
      return source;
    });
    const api = createBrowserApi({ fetcher: vi.fn(), eventSourceFactory: factory, scheduleReconnect: (callback) => callback() });
    const status = vi.fn();

    const stop = api.subscribeEvents("task-1", 0, { onEvent: vi.fn(), onConnection: status });
    sources[0].onmessage?.({ data: JSON.stringify({ sequence: 7, event_type: "SCAN_STARTED", payload: {} }) } as MessageEvent<string>);
    sources[0].onerror?.();

    expect(factory).toHaveBeenNthCalledWith(1, "/api/tasks/task-1/events?after=0");
    expect(factory).toHaveBeenNthCalledWith(2, "/api/tasks/task-1/events?after=7");
    expect(status).toHaveBeenCalledWith("reconnecting");
    stop();
  });
});
