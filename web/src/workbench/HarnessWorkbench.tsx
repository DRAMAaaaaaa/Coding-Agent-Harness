import { FormEvent, useEffect, useRef, useState } from "react";
import type { BranchComparison, ConnectionState, HarnessApi, IntentCard, ProjectLearningCard, ProviderProfile, Task, TaskEvent, Workspace } from "../types";
import { ProviderSettings } from "./ProviderSettings";
import { StageNavigator } from "./StageNavigator";
import { TaskStatusBar } from "./TaskStatusBar";
import { DeliveryStage } from "./stages/DeliveryStage";
import { ExecutionStage } from "./stages/ExecutionStage";
import { PlanStage } from "./stages/PlanStage";
import { ProjectStage } from "./stages/ProjectStage";
import { ReplayStage } from "./stages/ReplayStage";
import { RequirementStage } from "./stages/RequirementStage";
import { advanceSelectedStage, deriveEvidence, latestAvailableStage, unlockedStages, type WorkbenchStage } from "./workflow";

interface HarnessWorkbenchProps { api: HarnessApi; }

export function HarnessWorkbench({ api }: HarnessWorkbenchProps) {
  const [projectPath, setProjectPath] = useState("");
  const [requirement, setRequirement] = useState("");
  const [workspace, setWorkspace] = useState<Workspace>();
  const [task, setTask] = useState<Task>();
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [stateUnknown, setStateUnknown] = useState(false);
  const [providers, setProviders] = useState<ProviderProfile[]>([]);
  const [providerId, setProviderId] = useState("");
  const [providerResetVersion, setProviderResetVersion] = useState(0);
  const [connection, setConnection] = useState<ConnectionState>("disconnected");
  const [message, setMessage] = useState("请接入本地 Git 项目后建立信任。");
  const [busy, setBusy] = useState<string>();
  const [cards, setCards] = useState<IntentCard[]>([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [correction, setCorrection] = useState("");
  const [comparison, setComparison] = useState<BranchComparison>();
  const [branchCreated, setBranchCreated] = useState(false);
  const [projectLearning, setProjectLearning] = useState<ProjectLearningCard>();
  const [learningText, setLearningText] = useState<string>();
  const [selectedStage, setSelectedStage] = useState<WorkbenchStage>("PROJECT");
  const lastSequence = useRef(0);
  const previousLatest = useRef<WorkbenchStage>("PROJECT");
  const taskId = task?.id;

  useEffect(() => { if (api.listProviders) void api.listProviders().then(setProviders).catch(() => setProviders([])); }, [api]);
  useEffect(() => {
    if (!taskId) return;
    let active = true;
    lastSequence.current = 0;
    const reconcileInvalidEvent = (): void => {
      setEvents([]); lastSequence.current = 0; setStateUnknown(true); setMessage("事件数据无效，已清空审批证据并正在与服务对账。");
      void api.getTask(taskId).then((current) => { if (active) { setTask(current); setStateUnknown(false); setMessage("任务状态已对账；请等待完整审批证据重新到达。"); } }).catch(() => { if (active) setMessage("事件数据无效且状态对账失败；请重新接入项目。"); });
    };
    const stop = api.subscribeEvents(taskId, 0, {
      onEvent: (next) => { if (next.sequence > lastSequence.current) { lastSequence.current = next.sequence; setEvents((current) => [...current, next]); } },
      onConnection: setConnection,
      onInvalidEvent: reconcileInvalidEvent,
    });
    return () => { active = false; stop(); };
  }, [api, taskId]);
  useEffect(() => {
    if (!taskId || !api.getIntentCards) return;
    let active = true;
    void api.getIntentCards(taskId).then((next) => { if (active) setCards(next); }).catch(() => { if (active) setCards([]); });
    return () => { active = false; };
  }, [api, taskId, events.length]);
  useEffect(() => {
    if (!workspace || !api.getLatestProjectLearning) return;
    let active = true;
    const workspaceId = workspace.id;
    void api.getLatestProjectLearning(workspaceId).then((card) => { if (active) setProjectLearning(card ?? undefined); }).catch(() => { if (active) setProjectLearning(undefined); });
    return () => { active = false; };
  }, [api, workspace]);

  const snapshot = { workspace, task, events, cards };
  const evidence = deriveEvidence(events);
  const unlocked = unlockedStages(snapshot);
  const latest = latestAvailableStage(snapshot);
  useEffect(() => {
    setSelectedStage((selected) => advanceSelectedStage(selected, previousLatest.current, latest));
    previousLatest.current = latest;
  }, [latest]);

  const mutationDisabled = busy !== undefined || stateUnknown || (task !== undefined && connection !== "connected");
  const run = async (key: string, action: () => Promise<void>, settleTaskId?: string): Promise<void> => {
    if (busy) return;
    setBusy(key);
    try { await action(); }
    catch {
      if (settleTaskId) { try { setTask(await api.getTask(settleTaskId)); } catch { setTask(undefined); setEvents([]); lastSequence.current = 0; setStateUnknown(true); } }
      setMessage("无法完成此操作。请检查服务状态后重试。");
    } finally { setBusy(undefined); }
  };
  const clearTaskContext = (): void => {
    setEvents([]); setCards([]); setQuestion(""); setAnswer(""); setCorrection(""); setComparison(undefined); setBranchCreated(false); lastSequence.current = 0; setStateUnknown(false);
  };
  const resetProjectContext = (): void => {
    setTask(undefined); clearTaskContext(); setLearningText(undefined); setProjectLearning(undefined); setProviderResetVersion((value) => value + 1); previousLatest.current = "PROJECT"; setSelectedStage("PROJECT");
  };
  const connectProject = (form?: FormEvent): void => { form?.preventDefault(); void run("project", async () => { setWorkspace(undefined); resetProjectContext(); const created = await api.connectProject(projectPath); setWorkspace(created); if (created.trusted) setSelectedStage("REQUIREMENT"); setMessage(created.trusted ? "当前项目已建立信任，可描述编码需求。" : "项目已接入，请审阅摘要并显式建立信任。"); }); };
  const trustProject = (): void => { if (!workspace) return; void run("trust", async () => { const trusted = await api.trustProject(workspace); setWorkspace(trusted); setSelectedStage("REQUIREMENT"); setMessage("已建立当前项目配置的信任。"); }); };
  const createTask = (form?: FormEvent): void => { form?.preventDefault(); if (!workspace) return; void run("task", async () => { try { const created = await api.createTask(workspace.id, requirement, providerId || undefined); clearTaskContext(); setTask(created); setSelectedStage("PLAN"); setMessage("计划已生成，等待计划事件到达。"); } finally { setProviderResetVersion((value) => value + 1); } }); };
  const approvePlan = (): void => { if (!task) return; void run("approve-plan", async () => { const approved = await api.approvePlan(task.id); setTask(approved); setTask(await api.runTask(task.id)); setSelectedStage("EXECUTION"); setMessage("计划已批准，任务已触发运行。"); }, task.id); };
  const continueRun = (): void => { if (!task) return; void run("run", async () => setTask(await api.runTask(task.id)), task.id); };
  const ask = (card: IntentCard): void => { if (!task || !api.askQuestion) return; void run("question", async () => setAnswer((await api.askQuestion!(task.id, card.id, question)).content)); };
  const createCorrection = (card: IntentCard): void => { if (!task || !api.createCorrectionBranch || !api.getCorrectionComparison) return; void run("correction", async () => { const branch = await api.createCorrectionBranch!(task.id, card.source_event_sequence, correction); setBranchCreated(true); const comparisonRequest = api.getCorrectionComparison!(branch.id); if (branch.child_task_id) { const child = await api.getTask(branch.child_task_id); clearTaskContext(); setBranchCreated(true); setTask(child); setSelectedStage("PLAN"); } void comparisonRequest.then(setComparison).catch(() => undefined); }); };
  const approveFinal = (): void => { if (!task) return; void run("approve-final", async () => { setTask(await api.approveFinal(task.id)); setMessage("已提交最终审查批准。"); }, task.id); };
  const approveLearning = (card: IntentCard): void => { if (!task || !api.approveProjectLearning) return; void run("project-learning", async () => { const saved = await api.approveProjectLearning!(task.id, card.source_event_sequence, learningText ?? evidence.finalDiagnostic ?? ""); setProjectLearning(saved); setMessage("项目经验已批准，将在下一任务中引用。"); }); };
  const showPlanApproval = !stateUnknown && task?.state === "WAITING_PLAN_APPROVAL" && evidence.planDiagnostic !== undefined;
  const showRun = !stateUnknown && task?.state === "DECIDING";
  const showFinalApproval = !stateUnknown && task?.state === "WAITING_FINAL_REVIEW" && evidence.verificationDiagnostic !== undefined && evidence.diffDiagnostic !== undefined && evidence.finalDiagnostic !== undefined;
  const providerLabel = providerId ? "已选择会话 Provider" : "确定性 Mock 演示";

  return <main className="workbench-shell" aria-busy={busy !== undefined}>
    <header className="workbench-header"><div><p className="eyebrow">本地 Coding Agent Harness</p><h1>共学回放式编码工作台</h1><p>在每一步查看意图、行动、证据与纠正。</p></div><TaskStatusBar task={task} connection={connection} message={message} /></header>
    <StageNavigator selected={selectedStage} latest={latest} unlocked={unlocked} onSelect={setSelectedStage} />
    <ProviderSettings key={providerResetVersion} api={api} providers={providers} selectedId={providerId} disabled={busy !== undefined} resetVersion={providerResetVersion} onProvidersChange={setProviders} onSelect={setProviderId} />
    {selectedStage === "PROJECT" && <ProjectStage path={projectPath} workspace={workspace} busy={busy !== undefined} mutationDisabled={mutationDisabled} onPath={setProjectPath} onConnect={connectProject} onTrust={trustProject} />}
    {selectedStage === "REQUIREMENT" && <RequirementStage requirement={requirement} trusted={workspace?.trusted === true} mutationDisabled={mutationDisabled} busy={busy === "task"} projectLearning={projectLearning} providerLabel={providerLabel} onRequirement={setRequirement} onCreate={createTask} />}
    {selectedStage === "PLAN" && <PlanStage diagnostic={evidence.planDiagnostic} digest={evidence.plan?.payload.content_sha256 as string | undefined} bytes={evidence.plan?.payload.content_bytes} canApprove={showPlanApproval} canRun={showRun} busy={mutationDisabled} onApprove={approvePlan} onRun={continueRun} />}
    {selectedStage === "EXECUTION" && <ExecutionStage events={events} verification={evidence.verificationDiagnostic} approvals={evidence.approvals} reconnecting={connection === "reconnecting"} finalReviewBlocked={task?.state === "WAITING_FINAL_REVIEW" && !showFinalApproval} />}
    {selectedStage === "REPLAY" && <ReplayStage cards={cards} comparison={comparison} branchCreated={branchCreated} question={question} answer={answer} correction={correction} busy={mutationDisabled} onQuestion={setQuestion} onAsk={ask} onCorrection={setCorrection} onCreateCorrection={createCorrection} />}
    {selectedStage === "DELIVERY" && <DeliveryStage verification={evidence.verificationDiagnostic} diff={evidence.diffDiagnostic} summary={evidence.finalDiagnostic} canApprove={showFinalApproval} busy={mutationDisabled} taskCompleted={task?.state === "COMPLETED"} cards={cards} learningText={learningText ?? evidence.finalDiagnostic ?? ""} onApprove={approveFinal} onLearning={setLearningText} onApproveLearning={approveLearning} />}
  </main>;
}
