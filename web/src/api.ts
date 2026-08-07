import { parseTaskEvent } from "./types";
import type { EventListener, HarnessApi, ProviderProfile, Task, Workspace } from "./types";

interface EventSourceLike { onopen: ((event: Event) => void) | null; onerror: ((event: Event) => void) | null; addEventListener: (name: string, listener: (event: MessageEvent<string>) => void) => void; removeEventListener: (name: string, listener: (event: MessageEvent<string>) => void) => void; close: () => void; }
interface BrowserApiOptions { fetcher?: typeof fetch; eventSourceFactory?: (url: string) => EventSourceLike; scheduleReconnect?: (callback: () => void) => unknown; }
const safeRequestError = new Error("无法完成此操作。请检查服务状态后重试。");

export function createBrowserApi(options: BrowserApiOptions = {}): HarnessApi {
  const fetcher = options.fetcher ?? window.fetch.bind(window);
  const eventSourceFactory = options.eventSourceFactory ?? ((url) => new EventSource(url));
  const scheduleReconnect = options.scheduleReconnect ?? ((callback) => window.setTimeout(callback, 1000));
  let session: string | undefined;
  async function request<T>(path: string, body?: object, method = "POST"): Promise<T> {
    if (body !== undefined && session === undefined) { const bootstrap = await fetcher("/", { credentials: "same-origin" }); session = bootstrap.headers.get("X-Harness-Session") ?? undefined; if (!bootstrap.ok || session === undefined) throw safeRequestError; }
    const response = await fetcher(path, body === undefined ? { credentials: "same-origin" } : { method, credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Harness-Session": session! }, body: JSON.stringify(body) });
    if (!response.ok) throw safeRequestError;
    try { return await response.json() as T; } catch { throw safeRequestError; }
  }
  function subscribeEvents(taskId: string, after: number, listener: EventListener): () => void {
    let closed = false; let source: EventSourceLike | undefined; let lastSequence = after;
    const connect = (): void => {
      if (closed) return;
      const next = eventSourceFactory(`/api/tasks/${encodeURIComponent(taskId)}/events?after=${lastSequence}`); source = next;
      let invalidated = false;
      const invalidate = (): void => {
        if (closed || invalidated) return;
        invalidated = true;
        next.removeEventListener("task-event", receive);
        next.close();
        listener.onConnection("reconnecting");
        listener.onInvalidEvent?.();
        scheduleReconnect(connect);
      };
      const receive = (message: MessageEvent<string>): void => { try { const event = parseTaskEvent(JSON.parse(message.data), taskId); if (event.sequence > lastSequence) { lastSequence = event.sequence; listener.onEvent(event); } } catch { invalidate(); } };
      next.onopen = () => { if (!invalidated) listener.onConnection("connected"); };
      next.addEventListener("task-event", receive);
      next.onerror = () => { if (closed || invalidated) return; next.removeEventListener("task-event", receive); next.close(); listener.onConnection("reconnecting"); scheduleReconnect(connect); };
      cleanup = () => next.removeEventListener("task-event", receive);
    };
    let cleanup: () => void = () => undefined;
    connect();
    return () => { closed = true; cleanup(); source?.close(); listener.onConnection("disconnected"); };
  }
  return { connectProject: (path) => request<Workspace>("/api/projects", { path }), trustProject: (workspace) => request<Workspace>(`/api/projects/${workspace.id}/trust`, { fingerprint: workspace.trust_fingerprint }), createTask: (workspaceId, requirement, providerProfileId) => request<Task>("/api/tasks", { workspace_id: workspaceId, requirement, ...(providerProfileId ? { provider_profile_id: providerProfileId } : {}) }), listProviders: () => request<ProviderProfile[]>("/api/providers"), createProvider: (kind, model) => request<ProviderProfile>("/api/providers", { kind, model }), setSessionCredential: (profileId, apiKey) => request<ProviderProfile>(`/api/providers/${encodeURIComponent(profileId)}/session-credential`, { api_key: apiKey }, "PUT"), approvePlan: (taskId) => request<Task>(`/api/tasks/${taskId}/plan/approve`, {}), runTask: (taskId) => request<Task>(`/api/tasks/${taskId}/run`, {}), approveFinal: (taskId) => request<Task>(`/api/tasks/${taskId}/final/approve`, {}), getTask: (taskId) => request<Task>(`/api/tasks/${taskId}`), subscribeEvents };
}
