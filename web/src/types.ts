export type ConnectionState = "connected" | "reconnecting" | "disconnected";

export interface RepositorySummary {
  tracked_count?: number;
  test_count?: number;
  dirty_count?: number;
  tracked_paths?: string[];
  test_paths?: string[];
  dirty_paths?: string[];
  recent_commits?: string[];
  document_paths?: string[];
}

export interface Workspace {
  id: string;
  default_branch: string;
  languages: string[];
  trust_fingerprint: string;
  trusted: boolean;
  repository?: RepositorySummary;
}

export interface Task {
  id: string;
  workspace_id: string;
  state: string;
}

export interface TaskEvent {
  sequence: number;
  event_type: string;
  state_before?: string;
  state_after?: string;
  occurred_at?: string;
  payload: Record<string, unknown>;
}

export interface EventListener {
  onEvent: (event: TaskEvent) => void;
  onConnection: (state: ConnectionState) => void;
}

export interface HarnessApi {
  connectProject(path: string): Promise<Workspace>;
  trustProject(workspace: Workspace): Promise<Workspace>;
  createTask(workspaceId: string, requirement: string): Promise<Task>;
  approvePlan(taskId: string): Promise<Task>;
  runTask(taskId: string): Promise<Task>;
  approveFinal(taskId: string): Promise<Task>;
  getTask(taskId: string): Promise<Task>;
  subscribeEvents(taskId: string, after: number, listener: EventListener): () => void;
}
