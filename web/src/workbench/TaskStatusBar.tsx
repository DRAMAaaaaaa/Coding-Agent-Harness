import type { ConnectionState, Task, TaskState } from "../types";

const STATUS: Partial<Record<TaskState, string>> = {
  WAITING_PLAN_APPROVAL: "等待计划批准", DECIDING: "等待运行", WAITING_ACTION_APPROVAL: "等待危险动作处理",
  EXECUTING: "正在执行", WAITING_FINAL_REVIEW: "等待最终审查", WAITING_USER: "等待用户处理", COMPLETED: "已完成",
};

interface TaskStatusBarProps { task?: Task; connection: ConnectionState; message: string; }

export function TaskStatusBar({ task, connection, message }: TaskStatusBarProps) {
  const status = task ? STATUS[task.state] ?? task.state : "尚未创建任务";
  const connectionText = connection === "connected" ? "已连接" : connection === "reconnecting" ? "正在重连" : "未连接";
  return <>
    <p className="status" aria-live="polite">{status} · SSE：{connectionText}</p>
    <p className="message" role="status">{message}</p>
  </>;
}
