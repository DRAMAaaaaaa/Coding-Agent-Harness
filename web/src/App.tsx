import { FormEvent, useEffect, useRef, useState } from "react";

import type { ConnectionState, HarnessApi, Task, TaskEvent, Workspace } from "./types";

interface AppProps {
  api: HarnessApi;
}

const STATUS: Record<string, string> = {
  WAITING_PLAN_APPROVAL: "⏸ 等待计划批准",
  EXECUTING: "↻ 正在执行",
  WAITING_FINAL_APPROVAL: "✓ 等待最终审查",
  WAITING_USER: "⚠ 等待用户处理",
  COMPLETED: "✓ 已完成",
};

function statusLabel(state: string | undefined): string {
  return state === undefined ? "○ 尚未创建任务" : (STATUS[state] ?? `● ${state}`);
}

function detail(payload: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string") return value;
    if (Array.isArray(value) && value.every((item) => typeof item === "string")) return value.join(", ");
  }
  return undefined;
}

export function App({ api }: AppProps) {
  const [projectPath, setProjectPath] = useState("");
  const [requirement, setRequirement] = useState("");
  const [workspace, setWorkspace] = useState<Workspace>();
  const [task, setTask] = useState<Task>();
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("disconnected");
  const [message, setMessage] = useState("请接入本地 Git 项目后建立信任。");
  const lastSequence = useRef(0);
  const taskId = task?.id;

  useEffect(() => {
    if (taskId === undefined) return;
    lastSequence.current = 0;
    return api.subscribeEvents(taskId, 0, {
      onEvent: (event) => {
        if (event.sequence > lastSequence.current) {
          lastSequence.current = event.sequence;
          setEvents((current) => [...current, event]);
        }
      },
      onConnection: setConnection,
    });
  }, [api, taskId]);

  const safely = async (operation: () => Promise<void>): Promise<void> => {
    try {
      await operation();
    } catch {
      setMessage("无法完成此操作。请检查服务状态后重试。");
    }
  };

  const connectProject = (event: FormEvent): void => {
    event.preventDefault();
    void safely(async () => {
      const created = await api.connectProject(projectPath);
      setWorkspace(created);
      setMessage("项目已接入，请审阅摘要并显式建立信任。");
    });
  };

  const createTask = (event: FormEvent): void => {
    event.preventDefault();
    if (workspace === undefined) return;
    void safely(async () => {
      const created = await api.createTask(workspace.id, requirement);
      setEvents([]);
      setTask(created);
      setMessage("计划已生成，等待您的批准。");
    });
  };

  const verificationPassed = events.some((event) => event.event_type.includes("VERIFICATION_PASSED"));
  const finalDiff = events.map((event) => detail(event.payload, ["diff_summary", "diff"]))
    .find((value) => value !== undefined);
  const pendingApprovals = events.filter((event) => event.event_type.includes("APPROVAL") || event.payload.reason_code !== undefined);

  return (
    <main className="app-shell">
      <header>
        <p className="eyebrow">本地 Coding Agent Harness</p>
        <h1>受治理的编码任务工作台</h1>
        <p className="status" aria-live="polite">{statusLabel(task?.state)} · SSE：{connection === "connected" ? "● 已连接" : connection === "reconnecting" ? "↻ 正在重连" : "○ 未连接"}</p>
        <p className="message" role="status">{message}</p>
      </header>

      <section aria-labelledby="project-heading">
        <h2 id="project-heading">项目接入</h2>
        <form onSubmit={connectProject}>
          <label htmlFor="project-path">项目路径</label>
          <div className="inline-form">
            <input id="project-path" value={projectPath} onChange={(event) => setProjectPath(event.target.value)} required />
            <button type="submit">接入项目</button>
          </div>
        </form>
        {workspace && <div className="summary" aria-live="polite">
          <p>{workspace.languages.join(", ") || "未识别语言"} · {workspace.default_branch}</p>
          <p>已跟踪 {workspace.repository?.tracked_count ?? 0} 项，测试 {workspace.repository?.test_count ?? 0} 项，未提交变更 {workspace.repository?.dirty_count ?? 0} 项。</p>
          {workspace.repository?.test_paths?.length ? <p>测试位置：{workspace.repository.test_paths.join(", ")}</p> : null}
          {!workspace.trusted && <button type="button" onClick={() => void safely(async () => {
            setWorkspace(await api.trustProject(workspace));
            setMessage("已建立当前项目配置的信任。");
          })}>建立信任</button>}
          {workspace.trusted && <p>✓ 当前项目已建立信任</p>}
        </div>}
      </section>

      <section aria-labelledby="requirement-heading">
        <h2 id="requirement-heading">需求输入</h2>
        <form onSubmit={createTask}>
          <label htmlFor="requirement">编码需求</label>
          <textarea id="requirement" value={requirement} onChange={(event) => setRequirement(event.target.value)} required />
          <button type="submit" disabled={!workspace?.trusted}>生成计划</button>
        </form>
      </section>

      <section aria-labelledby="plan-heading">
        <h2 id="plan-heading">计划审批</h2>
        <p>{events.find((event) => event.event_type === "PLAN_PROPOSED") ? "已收到计划事件，请批准后运行。" : "尚未收到计划。"}</p>
        <button type="button" disabled={task?.state !== "WAITING_PLAN_APPROVAL"} onClick={() => task && void safely(async () => {
          await api.approvePlan(task.id);
          setTask(await api.runTask(task.id));
          setMessage("计划已批准，任务已触发运行。");
        })}>批准计划</button>
      </section>

      <section aria-labelledby="timeline-heading">
        <h2 id="timeline-heading">事件时间线</h2>
        <p aria-live="polite">{connection === "reconnecting" ? "↻ 事件流断开，正在重连。" : "○ 事件按序号续传。"}</p>
        <ol>{events.map((event) => <li key={event.sequence}><strong>#{event.sequence} {event.event_type}</strong>{detail(event.payload, ["summary", "reason_code"]) ? `：${detail(event.payload, ["summary", "reason_code"])}` : ""}</li>)}</ol>
      </section>

      <section aria-labelledby="approval-heading">
        <h2 id="approval-heading">危险动作审批</h2>
        {pendingApprovals.length === 0 ? <p>当前没有待审批危险动作。<span>后端尚无可提交操作</span>。</p> : pendingApprovals.map((event) => <article key={event.sequence} className="approval"><p>原因：{detail(event.payload, ["reason", "reason_code"]) ?? "事件未提供"}</p><p>精确范围：{detail(event.payload, ["scope", "paths", "path", "target"]) ?? "事件未提供"}</p><p>后端尚无可提交操作。</p></article>)}
      </section>

      <section aria-labelledby="review-heading">
        <h2 id="review-heading">测试与最终审查</h2>
        <p>{verificationPassed ? <>✓ <span>测试已通过</span></> : "○ 等待测试结果"}</p>
        <button type="button" disabled={task?.state !== "WAITING_FINAL_APPROVAL"} onClick={() => task && void safely(async () => {
          setTask(await api.approveFinal(task.id));
          setMessage("已提交最终审查批准。");
        })}>批准最终审查</button>
        <h2>最终差异</h2>
        <pre>{finalDiff ?? "尚无差异摘要。"}</pre>
      </section>
    </main>
  );
}
