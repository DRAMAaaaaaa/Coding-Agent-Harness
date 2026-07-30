export type TaskState = "CREATED" | "SCANNING" | "PLANNING" | "WAITING_PLAN_APPROVAL" | "DECIDING" | "WAITING_ACTION_APPROVAL" | "EXECUTING" | "VERIFYING" | "CORRECTING" | "WAITING_FINAL_REVIEW" | "WAITING_USER" | "COMPLETED" | "FAILED" | "CANCELLED";
export type ConnectionState = "connected" | "reconnecting" | "disconnected";
const states = new Set<TaskState>(["CREATED", "SCANNING", "PLANNING", "WAITING_PLAN_APPROVAL", "DECIDING", "WAITING_ACTION_APPROVAL", "EXECUTING", "VERIFYING", "CORRECTING", "WAITING_FINAL_REVIEW", "WAITING_USER", "COMPLETED", "FAILED", "CANCELLED"]);

export interface RepositorySummary { tracked_count?: number; test_count?: number; dirty_count?: number; tracked_paths?: string[]; test_paths?: string[]; dirty_paths?: string[]; recent_commits?: string[]; document_paths?: string[]; }
export interface Workspace { id: string; default_branch: string; languages: string[]; trust_fingerprint: string; trusted: boolean; repository?: RepositorySummary; }
export interface Task { id: string; workspace_id: string; state: TaskState; }
export interface TaskEvent { task_id: string; sequence: number; event_type: string; payload: Record<string, unknown>; state_before: TaskState | null; state_after: TaskState | null; occurred_at: string; }
export interface EventListener { onEvent: (event: TaskEvent) => void; onConnection: (state: ConnectionState) => void; onInvalidEvent?: () => void; }
export interface HarnessApi { connectProject(path: string): Promise<Workspace>; trustProject(workspace: Workspace): Promise<Workspace>; createTask(workspaceId: string, requirement: string): Promise<Task>; approvePlan(taskId: string): Promise<Task>; runTask(taskId: string): Promise<Task>; approveFinal(taskId: string): Promise<Task>; getTask(taskId: string): Promise<Task>; subscribeEvents(taskId: string, after: number, listener: EventListener): () => void; }

export function parseTaskEvent(value: unknown, expectedTaskId: string): TaskEvent {
  if (typeof value !== "object" || value === null) throw new Error("invalid task event");
  const event = value as Record<string, unknown>;
  if (event.task_id !== expectedTaskId || !Number.isInteger(event.sequence) || typeof event.sequence !== "number" || event.sequence <= 0 || typeof event.event_type !== "string" || !event.event_type || !isRecord(event.payload) || !isStateOrNull(event.state_before) || !isStateOrNull(event.state_after) || !isRfc3339(event.occurred_at) || !hasValidConsumedPayload(event.event_type, event.payload)) throw new Error("invalid task event");
  return event as unknown as TaskEvent;
}
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function isStateOrNull(value: unknown): value is TaskState | null { return value === null || (typeof value === "string" && states.has(value as TaskState)); }
function isRfc3339(value: unknown): value is string { return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && !Number.isNaN(Date.parse(value)); }
function isContentPayload(payload: Record<string, unknown>): boolean { return typeof payload.diagnostic === "string" && typeof payload.content_sha256 === "string" && /^[0-9a-f]{64}$/.test(payload.content_sha256) && Number.isInteger(payload.content_bytes) && typeof payload.content_bytes === "number" && payload.content_bytes >= 0; }
function hasValidConsumedPayload(eventType: string, payload: Record<string, unknown>): boolean {
  if (eventType === "PLAN_PROPOSED" || eventType === "FINAL_SUMMARY_PROPOSED") return isContentPayload(payload);
  if (eventType === "TOOL_EXECUTION_STARTED") return typeof payload.execution_id === "string" && payload.execution_id.length > 0 && isRecord(payload.action) && typeof payload.action.tool === "string" && payload.action.tool.length > 0;
  if (eventType === "TOOL_EXECUTION_COMPLETED") return typeof payload.execution_id === "string" && payload.execution_id.length > 0 && isRecord(payload.result) && (payload.result.diagnostic === undefined || typeof payload.result.diagnostic === "string") && (payload.result.changed_paths === undefined || (Array.isArray(payload.result.changed_paths) && payload.result.changed_paths.every((path) => typeof path === "string")));
  if (eventType === "VERIFICATION_SUCCEEDED") return isRecord(payload.run) && typeof payload.run.name === "string" && payload.run.ok === true && (payload.run.failure_count === null || Number.isInteger(payload.run.failure_count)) && typeof payload.run.diagnostic === "string" && isRecord(payload.verification) && typeof payload.verification.name === "string" && typeof payload.verification.config_version === "string" && typeof payload.verification.trust_fingerprint === "string" && typeof payload.verification.worktree_fingerprint === "string" && Array.isArray(payload.verification.required_checks) && payload.verification.required_checks.every((check) => typeof check === "string");
  if (eventType === "GOVERNANCE_BLOCKED") return typeof payload.reason_code === "string" && typeof payload.normalized_scope === "string";
  return true;
}
