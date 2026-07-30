import type { EventListener, HarnessApi, Task, TaskEvent, Workspace } from "./types";

interface EventSourceLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent<string>) => void) | null;
  onerror: ((event: Event) => void) | null;
  close: () => void;
}

interface BrowserApiOptions {
  fetcher?: typeof fetch;
  eventSourceFactory?: (url: string) => EventSourceLike;
  scheduleReconnect?: (callback: () => void) => unknown;
}

const safeRequestError = new Error("无法完成此操作。请检查服务状态后重试。");

export function createBrowserApi(options: BrowserApiOptions = {}): HarnessApi {
  const fetcher = options.fetcher ?? window.fetch.bind(window);
  const eventSourceFactory = options.eventSourceFactory ?? ((url) => new EventSource(url));
  const scheduleReconnect = options.scheduleReconnect ?? ((callback) => window.setTimeout(callback, 1000));
  let session: string | undefined;

  async function request<T>(path: string, body?: object): Promise<T> {
    if (body !== undefined && session === undefined) {
      const bootstrap = await fetcher("/", { credentials: "same-origin" });
      session = bootstrap.headers.get("X-Harness-Session") ?? undefined;
      if (!bootstrap.ok || session === undefined) {
        throw safeRequestError;
      }
    }
    const response = await fetcher(path, body === undefined
      ? { credentials: "same-origin" }
      : {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-Harness-Session": session! },
          body: JSON.stringify(body),
        });
    if (!response.ok) {
      throw safeRequestError;
    }
    try {
      return await response.json() as T;
    } catch {
      throw safeRequestError;
    }
  }

  function subscribeEvents(taskId: string, after: number, listener: EventListener): () => void {
    let closed = false;
    let source: EventSourceLike | undefined;
    let lastSequence = after;

    const connect = (): void => {
      if (closed) return;
      const nextSource = eventSourceFactory(`/api/tasks/${encodeURIComponent(taskId)}/events?after=${lastSequence}`);
      source = nextSource;
      nextSource.onopen = () => listener.onConnection("connected");
      nextSource.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as TaskEvent;
          if (Number.isInteger(event.sequence) && event.sequence > lastSequence) {
            lastSequence = event.sequence;
            listener.onEvent(event);
          }
        } catch {
          listener.onConnection("disconnected");
        }
      };
      nextSource.onerror = () => {
        if (closed) return;
        source?.close();
        listener.onConnection("reconnecting");
        scheduleReconnect(connect);
      };
    };
    connect();
    return () => {
      closed = true;
      source?.close();
      listener.onConnection("disconnected");
    };
  }

  return {
    connectProject: (path) => request<Workspace>("/api/projects", { path }),
    trustProject: (workspace) => request<Workspace>(`/api/projects/${workspace.id}/trust`, { fingerprint: workspace.trust_fingerprint }),
    createTask: (workspaceId, requirement) => request<Task>("/api/tasks", { workspace_id: workspaceId, requirement }),
    approvePlan: (taskId) => request<Task>(`/api/tasks/${taskId}/plan/approve`, {}),
    runTask: (taskId) => request<Task>(`/api/tasks/${taskId}/run`, {}),
    approveFinal: (taskId) => request<Task>(`/api/tasks/${taskId}/final/approve`, {}),
    getTask: (taskId) => request<Task>(`/api/tasks/${taskId}`),
    subscribeEvents,
  };
}
