export type TaskState = "CREATED" | "SCANNING" | "PLANNING" | "WAITING_PLAN_APPROVAL" | "DECIDING" | "WAITING_ACTION_APPROVAL" | "EXECUTING" | "VERIFYING" | "CORRECTING" | "WAITING_FINAL_REVIEW" | "WAITING_USER" | "COMPLETED" | "FAILED" | "CANCELLED";
export type ConnectionState = "connected" | "reconnecting" | "disconnected";
const states = new Set<TaskState>(["CREATED", "SCANNING", "PLANNING", "WAITING_PLAN_APPROVAL", "DECIDING", "WAITING_ACTION_APPROVAL", "EXECUTING", "VERIFYING", "CORRECTING", "WAITING_FINAL_REVIEW", "WAITING_USER", "COMPLETED", "FAILED", "CANCELLED"]);

export interface RepositorySummary { tracked_count?: number; test_count?: number; dirty_count?: number; tracked_paths?: string[]; test_paths?: string[]; dirty_paths?: string[]; recent_commits?: string[]; document_paths?: string[]; }
export interface Workspace { id: string; default_branch: string; languages: string[]; trust_fingerprint: string; trusted: boolean; repository?: RepositorySummary; }
export interface Task { id: string; workspace_id: string; state: TaskState; }
export interface TaskEvent { task_id: string; sequence: number; event_type: string; payload: Record<string, unknown>; state_before: TaskState | null; state_after: TaskState | null; occurred_at: string; }
export interface EventListener { onEvent: (event: TaskEvent) => void; onConnection: (state: ConnectionState) => void; }
export interface HarnessApi { connectProject(path: string): Promise<Workspace>; trustProject(workspace: Workspace): Promise<Workspace>; createTask(workspaceId: string, requirement: string): Promise<Task>; approvePlan(taskId: string): Promise<Task>; runTask(taskId: string): Promise<Task>; approveFinal(taskId: string): Promise<Task>; getTask(taskId: string): Promise<Task>; subscribeEvents(taskId: string, after: number, listener: EventListener): () => void; }

export function parseTaskEvent(value: unknown, expectedTaskId: string): TaskEvent | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const event = value as Record<string, unknown>;
  if (event.task_id !== expectedTaskId || !Number.isInteger(event.sequence) || typeof event.sequence !== "number" || event.sequence < 0 || typeof event.event_type !== "string" || !event.event_type || !isRecord(event.payload) || !isStateOrNull(event.state_before) || !isStateOrNull(event.state_after) || typeof event.occurred_at !== "string" || Number.isNaN(Date.parse(event.occurred_at))) return undefined;
  return event as unknown as TaskEvent;
}
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function isStateOrNull(value: unknown): value is TaskState | null { return value === null || (typeof value === "string" && states.has(value as TaskState)); }
