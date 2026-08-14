import type { IntentCard, Task, TaskEvent, Workspace } from "../types";

export type WorkbenchStage = "PROJECT" | "REQUIREMENT" | "PLAN" | "EXECUTION" | "REPLAY" | "DELIVERY";

export interface StageDefinition {
  id: WorkbenchStage;
  label: string;
  description: string;
}

export interface WorkflowSnapshot {
  workspace?: Workspace;
  task?: Task;
  events: TaskEvent[];
  cards: IntentCard[];
}

export interface WorkflowEvidence {
  plan?: TaskEvent;
  planDiagnostic?: string;
  verification?: TaskEvent;
  verificationDiagnostic?: string;
  diff?: TaskEvent;
  diffDiagnostic?: string;
  finalSummary?: TaskEvent;
  finalDiagnostic?: string;
  approvals: ReadonlyArray<{ reason: string; scope: string }>;
  hasVerificationFailure: boolean;
}

export const STAGES: readonly StageDefinition[] = [
  { id: "PROJECT", label: "项目", description: "识别并信任当前项目" },
  { id: "REQUIREMENT", label: "需求", description: "确认任务需求" },
  { id: "PLAN", label: "计划", description: "审阅执行计划" },
  { id: "EXECUTION", label: "执行", description: "执行工具操作" },
  { id: "REPLAY", label: "回放", description: "回看过程与反馈" },
  { id: "DELIVERY", label: "交付", description: "审阅最终交付" },
];

const executionStates = new Set<Task["state"]>([
  "DECIDING", "WAITING_ACTION_APPROVAL", "EXECUTING", "VERIFYING", "CORRECTING",
  "WAITING_FINAL_REVIEW", "WAITING_USER", "COMPLETED",
]);
const replayStates = new Set<Task["state"]>(["WAITING_USER", "WAITING_FINAL_REVIEW", "COMPLETED"]);
const outputLimit = /^\[OUTPUT_LIMIT\b/;

export function completeDiagnostic(payload: Record<string, unknown> | undefined): string | undefined {
  if (payload === undefined) return undefined;
  const diagnostic = diagnosticText(payload.diagnostic);
  if (diagnostic === undefined) return undefined;
  if (typeof payload.content_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(payload.content_sha256)) return undefined;
  if (!Number.isInteger(payload.content_bytes) || typeof payload.content_bytes !== "number") return undefined;
  return payload.content_bytes === new TextEncoder().encode(diagnostic).length ? diagnostic : undefined;
}

export function deriveEvidence(events: readonly TaskEvent[]): WorkflowEvidence {
  let plan: TaskEvent | undefined;
  let planDiagnostic: string | undefined;
  let verification: TaskEvent | undefined;
  let verificationDiagnostic: string | undefined;
  let diff: TaskEvent | undefined;
  let diffDiagnostic: string | undefined;
  let finalSummary: TaskEvent | undefined;
  let finalDiagnostic: string | undefined;
  let hasVerificationFailure = false;
  const approvals: Array<{ reason: string; scope: string }> = [];
  const tools = new Map<string, string>();

  for (const item of sortedEvents(events)) {
    if (item.event_type === "PLAN_PROPOSED") {
      const diagnostic = completeDiagnostic(item.payload);
      if (diagnostic !== undefined) {
        plan = item;
        planDiagnostic = diagnostic;
      }
    }
    if (item.event_type === "VERIFICATION_SUCCEEDED") {
      const diagnostic = diagnosticText(object(item.payload.run)?.diagnostic);
      if (diagnostic !== undefined) {
        verification = item;
        verificationDiagnostic = diagnostic;
        finalSummary = undefined;
        finalDiagnostic = undefined;
      }
    }
    if (item.event_type === "VERIFICATION_FAILED") hasVerificationFailure = true;
    if (item.event_type === "GOVERNANCE_BLOCKED") {
      const reason = text(item.payload.reason_code);
      const scope = text(item.payload.normalized_scope);
      if (reason !== undefined && scope !== undefined) approvals.push({ reason, scope });
    }
    if (item.event_type === "TOOL_EXECUTION_STARTED") {
      const id = text(item.payload.execution_id);
      const tool = text(object(item.payload.action)?.tool);
      if (id !== undefined && tool !== undefined) tools.set(id, tool);
    }
    if (item.event_type === "TOOL_EXECUTION_COMPLETED") {
      const result = object(item.payload.result);
      if (hasChangedPaths(result)) {
        verification = undefined;
        verificationDiagnostic = undefined;
        diff = undefined;
        diffDiagnostic = undefined;
        finalSummary = undefined;
        finalDiagnostic = undefined;
      }
      const id = text(item.payload.execution_id);
      const diagnostic = completeDiagnostic(result);
      if (id !== undefined && tools.get(id) === "git_diff" && diagnostic !== undefined) {
        diff = item;
        diffDiagnostic = diagnostic;
        finalSummary = undefined;
        finalDiagnostic = undefined;
      }
    }
    if (item.event_type === "FINAL_SUMMARY_PROPOSED") {
      const diagnostic = completeDiagnostic(item.payload);
      if (diagnostic !== undefined) {
        finalSummary = item;
        finalDiagnostic = diagnostic;
      }
    }
  }

  return { plan, planDiagnostic, verification, verificationDiagnostic, diff, diffDiagnostic, finalSummary, finalDiagnostic, approvals, hasVerificationFailure };
}

export function unlockedStages(snapshot: WorkflowSnapshot): WorkbenchStage[] {
  const stages: WorkbenchStage[] = ["PROJECT"];
  if (!snapshot.workspace?.trusted) return stages;
  stages.push("REQUIREMENT");
  if (!snapshot.task) return stages;
  stages.push("PLAN");
  if (!executionStates.has(snapshot.task.state)) return stages;
  stages.push("EXECUTION");
  const evidence = deriveEvidence(snapshot.events);
  const delivery = snapshot.task.state === "COMPLETED" || (evidence.verificationDiagnostic !== undefined && evidence.diffDiagnostic !== undefined && evidence.finalDiagnostic !== undefined);
  const replay = delivery || snapshot.cards.length > 0 || evidence.hasVerificationFailure || snapshot.events.some((event) => event.event_type === "GOVERNANCE_BLOCKED") || replayStates.has(snapshot.task.state);
  if (!replay) return stages;
  stages.push("REPLAY");
  if (delivery) stages.push("DELIVERY");
  return stages;
}

export function latestAvailableStage(snapshot: WorkflowSnapshot): WorkbenchStage {
  const stages = unlockedStages(snapshot);
  return stages[stages.length - 1];
}

export function advanceSelectedStage(selected: WorkbenchStage, previousLatest: WorkbenchStage, nextLatest: WorkbenchStage): WorkbenchStage {
  return selected === previousLatest ? nextLatest : selected;
}

function sortedEvents(events: readonly TaskEvent[]): TaskEvent[] {
  return events
    .map((event, index) => ({ event, index }))
    .sort((left, right) => (
      left.event.sequence - right.event.sequence
      || Date.parse(left.event.occurred_at) - Date.parse(right.event.occurred_at)
      || left.index - right.index
    ))
    .map(({ event }) => event);
}

function object(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function diagnosticText(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 && !outputLimit.test(trimmed) ? value : undefined;
}

function hasChangedPaths(result: Record<string, unknown> | undefined): boolean {
  return Array.isArray(result?.changed_paths) && result.changed_paths.some((path) => typeof path === "string");
}
