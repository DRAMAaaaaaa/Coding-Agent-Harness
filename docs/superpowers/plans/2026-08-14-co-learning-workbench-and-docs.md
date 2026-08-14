# 共学回放式前端工作台与交付文档联合实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有纵向堆叠的 WebUI 重构为六阶段共学回放式工作台，并在最终界面稳定后归档历史材料、重写课程交付文档。

**Architecture:** 前三个 Task 依次建立无副作用工作流契约、组件化工作台和浏览器/响应式验收；后两个 Task 复用已批准的精确归档设计，先移动历史证据并修复路径，再按最终 UI 重写当前介绍。五个 Task 在同一隔离 worktree 严格串行，每个 Task 独立 TDD、中文提交和规约/质量双审查。

**Tech Stack:** React 19、TypeScript 6、Vite 8、Vitest 4、Testing Library、Playwright 1.61、CSS、Python 3.11、pytest、Git、Markdown。

## Global Constraints

- 复用现有 `HarnessApi`；不修改后端 API、Agent 循环、治理、存储、部署协议或事件字段。
- 不增加 WebUI Provider Probe、主动清除、真实联网验收、多任务、多 Agent、多级分支或多条长期记忆。
- 不引入 UI 组件库、图标库、状态管理库、动画库、外部字体、远程图片或运行时 CDN。
- 六阶段名称固定为“项目接入、需求描述、计划审批、执行与验证、回放与纠正、交付与经验”。
- Mock 是默认主路径；DeepSeek/Qwen 只在“高级设置”中配置现有会话 Profile。
- API Key 只存在于 `ProviderSettings` 的 React state；配置成功、失败、关闭抽屉、切换项目或组件卸载时清空，不进入事件、日志、测试快照或记忆。
- 计划、验证、diff、最终摘要的现有完整性门和最新轮次门不得弱化；状态未知或 SSE 非 connected 时 mutation 保持禁用。
- 桌面 1280–1920px 答辩优先；小于 `760px` 时阶段导航、双列证据和比较布局变为单列且可操作。
- 状态必须同时使用可见文字/符号，不只依赖颜色；保留 label、语义标题、`aria-live`、键盘焦点和 `prefers-reduced-motion`。
- 有内容的历史文档只能 Git move 归档，不得不可恢复删除；根课程必交文档保留标准文件名。
- `REFLECTION.md` 只提供 1500–2500 字学生本人写作提纲，不生成可直接提交的正文。
- 介绍只陈述当前分支可由源码、测试或部署配置定位的能力；真实外网 Provider、认证/HTTPS 和 ECS 动态验收不得虚报。
- 不提交秘密、`.env`、运行数据库、截图、构建产物或本机路径状态；不触碰 `.tmp/`、`.venv-py39-backup/` 和未跟踪 `.superpowers` 文件。
- 新建/修改的说明文档和提交说明尽量使用中文；代码标识符、命令、协议和标准文件名保持原样。
- Task 1→2→3→4→5 严格串行；每个 Task 在隔离 worktree 执行 RED→GREEN→重构、规约审查、质量审查和中文提交。

---

## 文件结构与接口边界

```text
web/src/App.tsx                         保留 HarnessApi 注入入口
web/src/workbench/workflow.ts           阶段、证据和自动推进纯函数
web/src/workbench/workflow.test.ts      六阶段/证据确定性单测
web/src/workbench/HarnessWorkbench.tsx  全局状态、SSE 与 API 操作协调
web/src/workbench/StageNavigator.tsx    六阶段导航和历史回看
web/src/workbench/TaskStatusBar.tsx     Task/SSE/全局提示
web/src/workbench/ProviderSettings.tsx  高级设置与局部 Key 生命周期
web/src/workbench/TechnicalDetails.tsx  原生 details 技术证据
web/src/workbench/EvidenceCard.tsx      状态证据卡
web/src/workbench/IntentCardView.tsx    意图、提问与纠正入口
web/src/workbench/BranchComparisonView.tsx 父子任务比较
web/src/workbench/stages/*.tsx          六个阶段视图
web/src/App.test.tsx                    工作台集成与安全门组件测试
web/src/styles.css                      专业教学工作台/响应式样式
web/e2e/harness.spec.ts                 Mock 浏览器纵向主路径与窄屏验收
tests/distribution/test_delivery_files.py 文档、归档与交付契约
docs/archive/                           历史过程证据
README.md, docs/*.md, REFLECTION.md      当前交付说明
```

## 实施前冷启动门禁

执行时先使用 `superpowers:using-git-worktrees` 从包含本计划提交的 `main` 创建 `codex/co-learning-workbench-docs`。不复制 `.env`、数据库、密钥或用户临时目录；复用仓库已有依赖，不因本计划新增依赖。

随后让一个不同类型的陌生审计员只读取：

```text
SPEC.md
docs/superpowers/plans/2026-08-14-co-learning-workbench-and-docs.md
```

提示词固定为：

```text
仅依据给定规约与计划，选择 Task 1 或 Task 2 检查能否安全冷启动。
不要读取主对话、Git 历史或其他过程文档，不要修改文件。
发现类型、阶段规则、文件接口或验收含糊时立即暂停并列出阻塞，禁止猜测。
```

主控把结论、修订和复核结果写入 `SPEC_PROCESS.md`、`PLAN.md`、`AGENT_LOG.md`。只有审计结论为 READY 才派发 Task 1。Task 4 移动本计划后，Task 5 的规范路径改为 `docs/archive/plans/2026-08-14-co-learning-workbench-and-docs.md`。

### Task 1：六阶段工作流与最新证据纯函数

**Files:**
- Create: `web/src/workbench/workflow.ts`
- Create: `web/src/workbench/workflow.test.ts`

**Interfaces:**
- Consumes: `Task`、`TaskEvent`、`IntentCard`、`Workspace` from `web/src/types.ts`。
- Produces: `WorkbenchStage`、`STAGES`、`completeDiagnostic()`、`deriveEvidence()`、`unlockedStages()`、`latestAvailableStage()`、`advanceSelectedStage()`，供 Task 2 所有组件唯一消费。

- [ ] **Step 1: 写阶段和证据 RED 测试**

创建 `web/src/workbench/workflow.test.ts`，使用以下公开接口和测试矩阵：

```ts
import { describe, expect, it } from "vitest";
import type { IntentCard, Task, TaskEvent, Workspace } from "../types";
import {
  STAGES, advanceSelectedStage, completeDiagnostic, deriveEvidence,
  latestAvailableStage, unlockedStages,
} from "./workflow";

const workspace = (trusted: boolean): Workspace => ({
  id: "workspace-1", default_branch: "main", languages: ["Python"],
  trust_fingerprint: "a".repeat(64), trusted,
});
const task = (state: Task["state"]): Task => ({ id: "task-1", workspace_id: "workspace-1", state });
const event = (sequence: number, event_type: string, payload: Record<string, unknown>): TaskEvent => ({
  task_id: "task-1", sequence, event_type, payload,
  state_before: "EXECUTING", state_after: "EXECUTING",
  occurred_at: `2026-08-14T00:00:${String(sequence).padStart(2, "0")}Z`,
});
const content = (diagnostic: string) => ({
  diagnostic, content_sha256: "b".repeat(64),
  content_bytes: new TextEncoder().encode(diagnostic).length,
});

describe("六阶段工作流", () => {
  it.each([
    [{}, ["PROJECT"]],
    [{ workspace: workspace(false) }, ["PROJECT"]],
    [{ workspace: workspace(true) }, ["PROJECT", "REQUIREMENT"]],
    [{ workspace: workspace(true), task: task("WAITING_PLAN_APPROVAL") }, ["PROJECT", "REQUIREMENT", "PLAN"]],
    [{ workspace: workspace(true), task: task("EXECUTING") }, ["PROJECT", "REQUIREMENT", "PLAN", "EXECUTION"]],
    [{ workspace: workspace(true), task: task("WAITING_USER") }, ["PROJECT", "REQUIREMENT", "PLAN", "EXECUTION", "REPLAY"]],
  ])("按证据解锁 %#", (snapshot, expected) => {
    expect(unlockedStages({ events: [], cards: [], ...snapshot })).toEqual(expected);
  });

  it("意图卡、失败或治理阻塞解锁回放", () => {
    const base = { workspace: workspace(true), task: task("EXECUTING") };
    const card = { kind: "plan" } as IntentCard;
    expect(latestAvailableStage({ ...base, events: [], cards: [card] })).toBe("REPLAY");
    expect(latestAvailableStage({ ...base, events: [event(1, "VERIFICATION_FAILED", {})], cards: [] })).toBe("REPLAY");
    expect(latestAvailableStage({ ...base, events: [event(1, "GOVERNANCE_BLOCKED", {})], cards: [] })).toBe("REPLAY");
  });

  it("只有最新轮次完整验证、diff 和摘要解锁交付", () => {
    const events = [
      event(1, "TOOL_EXECUTION_STARTED", { execution_id: "write", action: { tool: "apply_patch" } }),
      event(2, "TOOL_EXECUTION_COMPLETED", { execution_id: "write", result: { ok: true, changed_paths: ["src/a.py"] } }),
      event(3, "VERIFICATION_SUCCEEDED", { run: { ok: true, diagnostic: "1 passed" } }),
      event(4, "TOOL_EXECUTION_STARTED", { execution_id: "diff", action: { tool: "git_diff" } }),
      event(5, "TOOL_EXECUTION_COMPLETED", { execution_id: "diff", result: { ok: true, ...content("+new") } }),
      event(6, "FINAL_SUMMARY_PROPOSED", content("完成")),
    ];
    const snapshot = { workspace: workspace(true), task: task("WAITING_FINAL_REVIEW"), events, cards: [] };
    expect(deriveEvidence(events)).toMatchObject({ verificationDiagnostic: "1 passed", diffDiagnostic: "+new", finalDiagnostic: "完成" });
    expect(latestAvailableStage(snapshot)).toBe("DELIVERY");
    expect(latestAvailableStage({ ...snapshot, events: events.filter((item) => item.sequence !== 3) })).toBe("REPLAY");
  });

  it("新修改使旧验证和旧 diff 失效", () => {
    const events = [
      event(1, "VERIFICATION_SUCCEEDED", { run: { ok: true, diagnostic: "旧通过" } }),
      event(2, "TOOL_EXECUTION_STARTED", { execution_id: "diff", action: { tool: "git_diff" } }),
      event(3, "TOOL_EXECUTION_COMPLETED", { execution_id: "diff", result: { ok: true, ...content("旧 diff") } }),
      event(4, "TOOL_EXECUTION_COMPLETED", { execution_id: "write", result: { ok: true, changed_paths: ["src/a.py"] } }),
      event(5, "FINAL_SUMMARY_PROPOSED", content("摘要")),
    ];
    expect(deriveEvidence(events)).toMatchObject({ verificationDiagnostic: undefined, diffDiagnostic: undefined });
  });

  it.each([content(""), content(`[OUTPUT_LIMIT bytes=4 sha256=${"c".repeat(64)}]`), { ...content("计划"), content_bytes: 1 }])(
    "拒绝不完整内容 %#", (payload) => expect(completeDiagnostic(payload)).toBeUndefined(),
  );

  it("自动推进不覆盖历史回看", () => {
    expect(advanceSelectedStage("PLAN", "PLAN", "EXECUTION")).toBe("EXECUTION");
    expect(advanceSelectedStage("PROJECT", "PLAN", "EXECUTION")).toBe("PROJECT");
  });

  it("阶段顺序固定", () => {
    expect(STAGES.map((stage) => stage.id)).toEqual([
      "PROJECT", "REQUIREMENT", "PLAN", "EXECUTION", "REPLAY", "DELIVERY",
    ]);
  });
});
```

- [ ] **Step 2: 运行 RED**

```powershell
npm.cmd --prefix web run test -- --run src/workbench/workflow.test.ts
```

Expected: FAIL，提示 `./workflow` 不存在；不得因测试夹具或导入 `types.ts` 失败。

- [ ] **Step 3: 实现精确公开类型与阶段推导**

创建 `web/src/workbench/workflow.ts`，公开签名固定为：

```ts
import type { IntentCard, Task, TaskEvent, Workspace } from "../types";

export type WorkbenchStage = "PROJECT" | "REQUIREMENT" | "PLAN" | "EXECUTION" | "REPLAY" | "DELIVERY";
export interface StageDefinition { id: WorkbenchStage; label: string; description: string; }
export interface WorkflowSnapshot { workspace?: Workspace; task?: Task; events: TaskEvent[]; cards: IntentCard[]; }
export interface WorkflowEvidence {
  plan?: TaskEvent; planDiagnostic?: string;
  verification?: TaskEvent; verificationDiagnostic?: string;
  diff?: TaskEvent; diffDiagnostic?: string;
  finalSummary?: TaskEvent; finalDiagnostic?: string;
  approvals: ReadonlyArray<{ reason: string; scope: string }>;
  hasVerificationFailure: boolean;
}
export const STAGES: readonly StageDefinition[];
export function completeDiagnostic(payload: Record<string, unknown> | undefined): string | undefined;
export function deriveEvidence(events: readonly TaskEvent[]): WorkflowEvidence;
export function unlockedStages(snapshot: WorkflowSnapshot): WorkbenchStage[];
export function latestAvailableStage(snapshot: WorkflowSnapshot): WorkbenchStage;
export function advanceSelectedStage(selected: WorkbenchStage, previousLatest: WorkbenchStage, nextLatest: WorkbenchStage): WorkbenchStage;
```

实现规则必须逐字对应规格：`PROJECT` 始终；Workspace trusted 解锁 `REQUIREMENT`；Task 解锁 `PLAN`；Task state 属于 `DECIDING|WAITING_ACTION_APPROVAL|EXECUTING|VERIFYING|CORRECTING|WAITING_FINAL_REVIEW|WAITING_USER|COMPLETED` 解锁 `EXECUTION`；有 card、`VERIFICATION_FAILED`、`GOVERNANCE_BLOCKED` 或 Task state 属于 `WAITING_USER|WAITING_FINAL_REVIEW|COMPLETED` 解锁 `REPLAY`；完整的最新验证/diff/摘要或 `COMPLETED` 解锁 `DELIVERY`。事件先按 `sequence`、再按 `occurred_at` 排序；最新文件修改之后才认可验证和 `git_diff`。

- [ ] **Step 4: GREEN、重构与静态门禁**

```powershell
npm.cmd --prefix web run test -- --run src/workbench/workflow.test.ts
npm.cmd --prefix web run lint
npm.cmd --prefix web run typecheck
```

Expected: workflow 测试全部 PASS，ESLint/TypeScript 退出 0。重构只允许提取 `text/object/display/latestEvent/hasChangedPaths` 私有 helper，不增加状态或依赖。

- [ ] **Step 5: 记录、双重审查并提交**

更新 `PLAN.md`/`AGENT_LOG.md` 的 Task 1 RED/GREEN 和审查事实。规约审查核对全部阶段/证据门；质量审查核对纯函数、不可变输入、事件排序和类型完整性。Critical/Important 清零后：

```powershell
git add web/src/workbench/workflow.ts web/src/workbench/workflow.test.ts PLAN.md AGENT_LOG.md
git commit -m "feat: 建立六阶段工作流契约"
```

### Task 2：组件化工作台、Provider 抽屉与专业教学视觉

**状态：** 已完成，待独立规约与代码质量审查（提交哈希将在审查通过后回填）。

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/e2e/harness.spec.ts`（只对齐桌面六阶段主路径；窄屏断言属于 Task 3）
- Create: `web/src/workbench/HarnessWorkbench.tsx`
- Create: `web/src/workbench/StageNavigator.tsx`
- Create: `web/src/workbench/TaskStatusBar.tsx`
- Create: `web/src/workbench/ProviderSettings.tsx`
- Create: `web/src/workbench/TechnicalDetails.tsx`
- Create: `web/src/workbench/EvidenceCard.tsx`
- Create: `web/src/workbench/IntentCardView.tsx`
- Create: `web/src/workbench/BranchComparisonView.tsx`
- Create: `web/src/workbench/stages/ProjectStage.tsx`
- Create: `web/src/workbench/stages/RequirementStage.tsx`
- Create: `web/src/workbench/stages/PlanStage.tsx`
- Create: `web/src/workbench/stages/ExecutionStage.tsx`
- Create: `web/src/workbench/stages/ReplayStage.tsx`
- Create: `web/src/workbench/stages/DeliveryStage.tsx`

**Interfaces:**
- Consumes: Task 1 的全部 `workflow.ts` exports 和现有 `HarnessApi`。
- Produces: 保持 `<App api={HarnessApi} />` 外部接口不变；六阶段导航、高级设置抽屉、分阶段操作与语义 CSS 类，供 Task 3 E2E 使用。

- [ ] **Step 1: 在现有 App 测试中写工作台 RED**

保留现有安全/主路径测试，增加以下测试；若旧测试需要进入特定阶段，只能通过可见阶段按钮导航，不得直接调用组件内部函数：

```tsx
it("按信任、任务和执行证据自动推进，并允许回看", async () => {
  const user = userEvent.setup();
  render(<App api={scriptedApi({ events: [taskEvents[0]] })} />);
  expect(screen.getByRole("heading", { name: "项目接入" })).toBeVisible();
  expect(screen.getByRole("button", { name: /需求描述/ })).toBeDisabled();
  await user.type(screen.getByLabelText("项目路径"), "C:\\demo\\repo");
  await user.click(screen.getByRole("button", { name: "接入项目" }));
  await user.click(await screen.findByRole("button", { name: "建立信任" }));
  expect(await screen.findByRole("heading", { name: "需求描述" })).toBeVisible();
  await user.type(screen.getByLabelText("编码需求"), "修复 add 函数");
  await user.click(screen.getByRole("button", { name: "生成计划" }));
  expect(await screen.findByRole("heading", { name: "计划审批" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "批准计划" }));
  expect(await screen.findByRole("heading", { name: "回放与纠正" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: /项目接入/ }));
  expect(screen.getByRole("button", { name: "返回当前阶段" })).toBeVisible();
});

it("高级设置以 Mock 为默认并在关闭时清空 Key、恢复焦点", async () => {
  const user = userEvent.setup();
  render(<App api={{ ...scriptedApi(), listProviders: vi.fn(async () => []), createProvider: vi.fn(), setSessionCredential: vi.fn() }} />);
  const opener = screen.getByRole("button", { name: "高级设置" });
  await user.click(opener);
  expect(screen.getByRole("dialog", { name: "Provider 高级设置" })).toBeVisible();
  const key = screen.getByLabelText("API Key");
  await user.type(key, "test-session-key");
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "Provider 高级设置" })).not.toBeInTheDocument();
  expect(opener).toHaveFocus();
  await user.click(opener);
  expect(screen.getByLabelText("API Key")).toHaveValue("");
  expect(screen.getByText(/没有连接测试和主动清除/)).toBeVisible();
  await user.keyboard("{Escape}");
  await user.type(screen.getByLabelText("项目路径"), "C:\\demo\\repo");
  await user.click(screen.getByRole("button", { name: "接入项目" }));
  await user.click(await screen.findByRole("button", { name: "建立信任" }));
  expect(await screen.findByText("确定性 Mock 演示")).toBeVisible();
});

it("技术详情默认折叠并可展开原始事件", async () => {
  const user = userEvent.setup();
  render(<App api={scriptedApi()} />);
  await createTrustedTask(user);
  await user.click(await screen.findByRole("button", { name: "批准计划" }));
  await user.click(screen.getByRole("button", { name: /执行与验证/ }));
  const details = screen.getByText("技术详情").closest("details");
  expect(details).not.toHaveAttribute("open");
  await user.click(screen.getByText("技术详情"));
  expect(screen.getByRole("listitem").filter({ hasText: "VERIFICATION_SUCCEEDED" })).toBeVisible();
});
```

补充现有纠正失败测试：`createCorrectionBranch` reject 后 `纠正说明` 保持原值；已有 `comparison` 后页面不再出现“从此纠正”。补充 SSE reconnect 测试：导航仍可回看，mutation 按钮 disabled。

同时先把 `web/e2e/harness.spec.ts` 的桌面主路径改为按阶段操作：信任后等待“需求描述”，创建任务后等待“计划审批”，失败事件到达后点击“回放与纠正”再提问/纠正，子任务计划出现后进入“计划审批”，证据齐全后进入“交付与经验”。本 Task 不增加 `720px` 断言。

- [ ] **Step 2: 运行 RED**

```powershell
npm.cmd --prefix web run test -- --run src/App.test.tsx
npm.cmd --prefix web run build
npm.cmd --prefix web run e2e -- harness.spec.ts
```

Expected: Vitest 和 Playwright 新契约 FAIL，原因是缺少六阶段按钮/标题、抽屉、技术详情；服务正常启动，不得以超时、导入错误或夹具错误代替预期 RED。

- [ ] **Step 3: 建立组件公开契约**

`web/src/App.tsx` 收缩为：

```tsx
import type { HarnessApi } from "./types";
import { HarnessWorkbench } from "./workbench/HarnessWorkbench";

interface AppProps { api: HarnessApi; }
export function App({ api }: AppProps) { return <HarnessWorkbench api={api} />; }
```

各组件公开 props 固定为最小领域值/回调，禁止组件直接访问浏览器 API：

```ts
// StageNavigator
{ selected: WorkbenchStage; latest: WorkbenchStage; unlocked: readonly WorkbenchStage[]; onSelect(stage): void }
// TaskStatusBar
{ task?: Task; connection: ConnectionState; message: string }
// ProviderSettings
{ api: Pick<HarnessApi, "listProviders" | "createProvider" | "setSessionCredential">; providers: ProviderProfile[]; selectedId: string; disabled: boolean; resetVersion: number; onProvidersChange(next): void; onSelect(id): void }
// TechnicalDetails
{ events: readonly TaskEvent[]; children?: ReactNode }
// IntentCardView
{ card: IntentCard; question: string; answer: string; correction: string; busy: boolean; branchExists: boolean; onQuestion(value): void; onAsk(): void; onCorrection(value): void; onCreateCorrection(): void }
// BranchComparisonView
{ comparison: BranchComparison }
```

六个 stage 组件只渲染各自数据和调用传入回调。`HarnessWorkbench` 保留现有 `run()`、SSE 生命周期、项目/任务清理和 API handler；所有计划/验证/diff/摘要选择改为调用 `deriveEvidence()`，阶段解锁只调用 `unlockedStages()`/`latestAvailableStage()`。

- [ ] **Step 4: 实现阶段导航和自动推进**

`HarnessWorkbench` 初始化 `selectedStage="PROJECT"`、`previousLatest` ref；每次 `latest` 改变时调用：

```tsx
setSelectedStage((selected) => advanceSelectedStage(selected, previousLatest.current, latest));
previousLatest.current = latest;
```

项目接入开始前同时执行 `setSelectedStage("PROJECT")`、清理旧上下文并递增 `providerResetVersion`。`StageNavigator` 使用六个 `<button>`，未解锁 disabled；当前项 `aria-current="step"`。当 `selected !== latest` 时显示“返回当前阶段”。页面正文同一时刻只渲染一个 stage，已解锁内容通过导航回看。

- [ ] **Step 5: 实现 Provider 抽屉和局部凭据生命周期**

`ProviderSettings` 内部持有 `open/apiKey/providerKind/providerModel`。默认模型切换：DeepSeek=`deepseek-chat`，Qwen=`qwen-plus`。`close()` 必须 `setApiKey("")`、`setOpen(false)`、在下一帧 `openerRef.current?.focus()`；`useEffect([resetVersion])` 清空 Key；组件卸载后局部 state 自然销毁，不在 cleanup 中调用 setState。dialog 打开时监听 `Escape`，并对 `Tab/Shift+Tab` 在 dialog 内的 button/input/select 间循环。配置 handler 使用 `try/finally { setApiKey("") }`，响应只加入 Profile，不展示或记录 Key。

可见边界原样包含：

```text
会话凭据不会持久保存。当前 WebUI 没有连接测试和主动清除；真实外网 Provider 任务尚未验收。
```

- [ ] **Step 6: 实现六阶段视图与共学优先展示**

- `ProjectStage`：项目路径、仓库摘要、建立信任。
- `RequirementStage`：显示“确定性 Mock 演示”或选中 Profile、项目经验、需求输入。
- `PlanStage`：完整计划、sha256/bytes、批准/继续；不完整证据显示阻塞卡。
- `ExecutionStage`：当前状态、最近验证、治理拦截、简化进度；`TechnicalDetails` 内才显示完整事件。
- `ReplayStage`：`IntentCardView` 列表和 `BranchComparisonView`；无卡片时解释等待意图证据。
- `DeliveryStage`：验证、diff、摘要、终审批准和完成后的经验批准。

创建纠正分支失败不得清空 `correction`；成功后设置 comparison 并切换 child task。`branchExists` 为 comparison 已存在或当前 card 已有关联分支的本地成功状态，阻止再次显示创建表单。

- [ ] **Step 7: 实现专业教学视觉与响应式 CSS**

在 `styles.css` 定义 CSS custom properties：

```css
:root {
  --canvas: #f3f6fb; --surface: #ffffff; --ink: #152238; --muted: #526077;
  --primary: #174a8b; --primary-soft: #e9f1fb; --success: #16794b;
  --warning: #a45b00; --danger: #b42318; --border: #ccd5e2;
  --code: #101828; --code-ink: #f8fafc;
}
```

建立 `.workbench-shell`、`.workbench-header`、`.stage-nav`、`.stage-button`、`.stage-panel`、`.evidence-grid`、`.comparison-grid`、`.provider-backdrop`、`.provider-dialog`、`.technical-details`、`.status-*`。桌面 `.stage-nav` sticky，`.evidence-grid`/`.comparison-grid` 使用两列；精确的 `<760px` 单列规则留给 Task 3 的浏览器 RED/GREEN。添加 `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; } }`。焦点 outline 不低于 `3px`。

- [ ] **Step 8: GREEN 与回归**

```powershell
npm.cmd --prefix web run test -- --run src/workbench/workflow.test.ts src/App.test.tsx src/api.test.ts
npm.cmd --prefix web run lint
npm.cmd --prefix web run typecheck
npm.cmd --prefix web run build
npm.cmd --prefix web run e2e -- harness.spec.ts
```

Expected: 全部 Vitest 和桌面 Playwright 主路径 PASS；ESLint、TypeScript、Vite build 退出 0。构建产物 `web/dist` 不提交。

- [ ] **Step 9: 记录、双重审查并提交**

规约审查核对六阶段、抽屉 Key 生命周期、无后端扩展、最新证据门和可访问性；质量审查重点检查组件 props、effect cleanup、focus trap、旧状态泄露与测试可读性。Critical/Important 清零后：

```powershell
git add web/src/App.tsx web/src/App.test.tsx web/src/styles.css web/src/workbench web/e2e/harness.spec.ts PLAN.md AGENT_LOG.md
git commit -m "feat: 构建共学回放式前端工作台"
```

### Task 3：浏览器主路径、窄屏与可访问性验收

**Files:**
- Modify: `web/e2e/harness.spec.ts`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: Task 2 可见六阶段按钮/标题、“高级设置”“技术详情”“返回当前阶段”和现有 API 主路径。
- Produces: 在 Task 2 已通过的桌面浏览器主路径上增加 `760px` 断点的确定性布局与键盘可访问性证据。

- [ ] **Step 1: 增加窄屏浏览器契约并取得 RED**

Task 2 已对齐桌面六阶段主路径。本 Task 只在同一个服务器生命周期、关闭页面前增加窄屏断言：

```ts
await page.setViewportSize({ width: 720, height: 900 });
await page.getByRole("button", { name: /回放与纠正/ }).click();
const comparison = page.getByLabel("纠正分支比较");
await expect(comparison).toBeVisible();
expect(await comparison.evaluate((element) => getComputedStyle(element).gridTemplateColumns)).not.toMatch(/\s/);
await page.getByRole("button", { name: "高级设置" }).focus();
await expect(page.getByRole("button", { name: "高级设置" })).toBeFocused();
```

```powershell
npm.cmd --prefix web run build
npm.cmd --prefix web run e2e -- harness.spec.ts
```

Expected: RED，完整桌面流程先成功，最终 `720px` 的 `.comparison-grid` computed columns 仍为两列而失败；不得以服务超时或主路径回退代替预期响应式失败。

- [ ] **Step 2: 对齐稳定选择器和响应式语义**

只修复 E2E 暴露的响应式契约。在 `styles.css` 增加 `@media (max-width: 759px)`：`.stage-nav`、`.evidence-grid`、`.comparison-grid`、`.inline-form` 单列，stage nav 取消 sticky；比较根节点保持 `aria-label="纠正分支比较"` 和 `.comparison-grid`，computed `grid-template-columns` 必须为单列；高级设置按钮可聚焦。不得为测试加入隐藏文字或 `data-testid`。

- [ ] **Step 3: 运行浏览器 GREEN 和 Web 全门禁**

```powershell
npm.cmd --prefix web run test -- --run
npm.cmd --prefix web run lint
npm.cmd --prefix web run typecheck
npm.cmd --prefix web run build
npm.cmd --prefix web run e2e -- harness.spec.ts
```

Expected: Vitest、ESLint、TypeScript、Vite、Playwright 全部通过；主路径仍确认 fixture Git HEAD/状态不变和 worktree 回收。若 Playwright 依赖本机构建，必须按 build→e2e 顺序记录。

- [ ] **Step 4: 记录、双重审查并提交**

规约审查检查真实浏览器覆盖六阶段、失败提问、纠正、交付、经验和窄屏；质量审查检查断言稳定性、进程清理、无网络、无脆弱 CSS selector。Critical/Important 清零后：

```powershell
git add web/e2e/harness.spec.ts web/src PLAN.md AGENT_LOG.md
git commit -m "test: 验收共学工作台浏览器主路径"
```

### Task 4：归档历史材料并修复全部路径

**Files:**
- Modify: `tests/distribution/test_delivery_files.py`
- Create: `docs/archive/README.md`
- Move: `docs/superpowers/specs/*.md` → `docs/archive/specs/*.md`
- Move: `docs/superpowers/plans/*.md` → `docs/archive/plans/*.md`
- Move: `MVP_ISSUES.md`, `DEFERRED_WORK.md` → `docs/archive/ledgers/`
- Move only tracked reports: `.superpowers/sdd/**/*.md` → `docs/archive/reports/` preserving existing subdirectories
- Modify path references: root/current Markdown and moved tracked Markdown

**Interfaces:**
- Consumes: Git tracked Markdown inventory at Task start。
- Produces: stable `docs/archive/{specs,plans,ledgers,reports}` and no tracked files at obsolete locations; Task 5 reads the combined plan from `docs/archive/plans/2026-08-14-co-learning-workbench-and-docs.md`。

- [ ] **Step 1: 写精确移动 RED 契约**

在 `tests/distribution/test_delivery_files.py` 定义以下完整映射；不得在实施时增删条目：

```python
ARCHIVE_MOVES = {
    "MVP_ISSUES.md": "docs/archive/ledgers/MVP_ISSUES.md",
    "DEFERRED_WORK.md": "docs/archive/ledgers/DEFERRED_WORK.md",
    "docs/superpowers/specs/2026-07-14-coding-agent-harness-design.md": "docs/archive/specs/2026-07-14-coding-agent-harness-design.md",
    "docs/superpowers/specs/2026-07-16-minimal-viable-harness-design.md": "docs/archive/specs/2026-07-16-minimal-viable-harness-design.md",
    "docs/superpowers/specs/2026-07-16-usable-product-priority-design.md": "docs/archive/specs/2026-07-16-usable-product-priority-design.md",
    "docs/superpowers/specs/2026-08-07-co-learning-replay-harness-design.md": "docs/archive/specs/2026-08-07-co-learning-replay-harness-design.md",
    "docs/superpowers/specs/2026-08-10-ci-powershell-tests-design.md": "docs/archive/specs/2026-08-10-ci-powershell-tests-design.md",
    "docs/superpowers/specs/2026-08-10-provider-webui-probe-design.md": "docs/archive/specs/2026-08-10-provider-webui-probe-design.md",
    "docs/superpowers/specs/2026-08-14-co-learning-workbench-ui-design.md": "docs/archive/specs/2026-08-14-co-learning-workbench-ui-design.md",
    "docs/superpowers/specs/2026-08-14-documentation-refresh-design.md": "docs/archive/specs/2026-08-14-documentation-refresh-design.md",
    "docs/superpowers/specs/2026-08-14-public-ip-mock-demo-design.md": "docs/archive/specs/2026-08-14-public-ip-mock-demo-design.md",
    "docs/superpowers/plans/2026-07-16-minimal-viable-harness.md": "docs/archive/plans/2026-07-16-minimal-viable-harness.md",
    "docs/superpowers/plans/2026-08-07-co-learning-replay-mvp.md": "docs/archive/plans/2026-08-07-co-learning-replay-mvp.md",
    "docs/superpowers/plans/2026-08-07-real-providers-and-credentials.md": "docs/archive/plans/2026-08-07-real-providers-and-credentials.md",
    "docs/superpowers/plans/2026-08-10-ci-powershell-tests.md": "docs/archive/plans/2026-08-10-ci-powershell-tests.md",
    "docs/superpowers/plans/2026-08-10-provider-webui-probe.md": "docs/archive/plans/2026-08-10-provider-webui-probe.md",
    "docs/superpowers/plans/2026-08-14-co-learning-workbench-and-docs.md": "docs/archive/plans/2026-08-14-co-learning-workbench-and-docs.md",
    "docs/superpowers/plans/2026-08-14-documentation-refresh.md": "docs/archive/plans/2026-08-14-documentation-refresh.md",
    "docs/superpowers/plans/2026-08-14-public-ip-mock-demo.md": "docs/archive/plans/2026-08-14-public-ip-mock-demo.md",
    ".superpowers/sdd/2026-08-07-co-learning-replay-mvp/task-2-report.md": "docs/archive/reports/2026-08-07-co-learning-replay-mvp/task-2-report.md",
    ".superpowers/sdd/2026-08-07-co-learning-replay-mvp/task-3-report.md": "docs/archive/reports/2026-08-07-co-learning-replay-mvp/task-3-report.md",
    ".superpowers/sdd/2026-08-07-co-learning-replay-mvp/task-5-report.md": "docs/archive/reports/2026-08-07-co-learning-replay-mvp/task-5-report.md",
    ".superpowers/sdd/2026-08-07-real-providers-and-credentials/task-3-implementer-report.md": "docs/archive/reports/2026-08-07-real-providers-and-credentials/task-3-implementer-report.md",
    ".superpowers/sdd/task-6-report.md": "docs/archive/reports/task-6-report.md",
    ".superpowers/sdd/task-7-report.md": "docs/archive/reports/task-7-report.md",
    ".superpowers/sdd/task-10-report.md": "docs/archive/reports/task-10-report.md",
}
```

测试：

```python
def test_historical_docs_are_archived_without_losing_evidence() -> None:
    assert (ROOT / "docs/archive/README.md").is_file()
    for source, target in ARCHIVE_MOVES.items():
        assert not (ROOT / source).is_file(), source
        archived = ROOT / target
        assert archived.is_file(), target
        assert archived.stat().st_size > 0, target
```

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py::test_historical_docs_are_archived_without_losing_evidence -v
```

Expected: FAIL，归档索引/目标不存在且旧源仍存在。

- [ ] **Step 2: 使用显式 Git move 建立归档**

```powershell
New-Item -ItemType Directory -Force docs\archive\ledgers, docs\archive\reports\2026-08-07-co-learning-replay-mvp, docs\archive\reports\2026-08-07-real-providers-and-credentials
git mv docs\superpowers\specs docs\archive\specs
git mv docs\superpowers\plans docs\archive\plans
git mv MVP_ISSUES.md docs\archive\ledgers\MVP_ISSUES.md
git mv DEFERRED_WORK.md docs\archive\ledgers\DEFERRED_WORK.md
git mv .superpowers\sdd\2026-08-07-co-learning-replay-mvp\task-2-report.md docs\archive\reports\2026-08-07-co-learning-replay-mvp\task-2-report.md
git mv .superpowers\sdd\2026-08-07-co-learning-replay-mvp\task-3-report.md docs\archive\reports\2026-08-07-co-learning-replay-mvp\task-3-report.md
git mv .superpowers\sdd\2026-08-07-co-learning-replay-mvp\task-5-report.md docs\archive\reports\2026-08-07-co-learning-replay-mvp\task-5-report.md
git mv .superpowers\sdd\2026-08-07-real-providers-and-credentials\task-3-implementer-report.md docs\archive\reports\2026-08-07-real-providers-and-credentials\task-3-implementer-report.md
git mv .superpowers\sdd\task-6-report.md docs\archive\reports\task-6-report.md
git mv .superpowers\sdd\task-7-report.md docs\archive\reports\task-7-report.md
git mv .superpowers\sdd\task-10-report.md docs\archive\reports\task-10-report.md
```

不得通配移动 `.superpowers`，不得触碰未跟踪/受忽略报告。`git ls-files MVP_ISSUES.md DEFERRED_WORK.md docs/superpowers .superpowers/sdd` 必须无输出。

- [ ] **Step 3: 建立索引并修复导航路径**

`docs/archive/README.md` 说明 specs/plans/ledgers/reports 用途、旧计划可能被取代、中间报告不代表最终状态、从未跟踪临时报告不伪造。精确替换活动导航：

```text
docs/superpowers/specs/ -> docs/archive/specs/
docs/superpowers/plans/ -> docs/archive/plans/
MVP_ISSUES.md -> docs/archive/ledgers/MVP_ISSUES.md
DEFERRED_WORK.md -> docs/archive/ledgers/DEFERRED_WORK.md
已移动的七份 .superpowers/sdd 路径 -> docs/archive/reports 对应路径
```

归档文档中描述“当时源路径”或本次迁移映射的历史文字不改成自指向；从未跟踪报告引用保留并由索引解释。

- [ ] **Step 4: 增加链接契约并取得 GREEN**

在测试顶部增加 `import re`，再加入：

```python
def test_current_markdown_links_resolve_after_archiving() -> None:
    current = (
        "README.md", "SPEC.md", "PLAN.md", "SPEC_PROCESS.md", "AGENT_LOG.md", "AGENTS.md",
        "docs/DEMO.md", "docs/DEPLOYMENT.md", "docs/SECURITY.md", "docs/archive/README.md",
    )
    link = re.compile(r"\[[^]]+\]\((?!https?://|mailto:)([^)#]+)(?:#[^)]+)?\)")
    for relative in current:
        document = ROOT / relative
        for target in link.findall(document.read_text(encoding="utf-8")):
            assert (document.parent / target).resolve().exists(), f"{relative} -> {target}"


def test_current_process_docs_point_to_archive_instead_of_old_locations() -> None:
    current = ("README.md", "SPEC.md", "PLAN.md", "SPEC_PROCESS.md", "AGENT_LOG.md", "AGENTS.md")
    content = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in current)
    assert "docs/superpowers/" not in content
    assert "`MVP_ISSUES.md`" not in content
    assert "`DEFERRED_WORK.md`" not in content
```

```powershell
.\.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py -v
git diff --check
```

Expected: distribution 全 PASS 或 Docker CLI 明确 SKIP；差异检查退出 0。

- [ ] **Step 5: 记录、双重审查并提交**

规约审查逐项核对移动清单与未跟踪保护；质量审查检查断链、重复文档、历史语义和 rename 可追踪性。Critical/Important 清零后：

```powershell
git add -A -- README.md SPEC.md PLAN.md SPEC_PROCESS.md AGENT_LOG.md AGENTS.md docs tests/distribution/test_delivery_files.py
git commit -m "docs: 归档历史过程文档"
```

### Task 5：按最终工作台重写交付说明与学生反思提纲

**Files:**
- Modify: `tests/distribution/test_delivery_files.py`
- Modify: `README.md`, `SPEC.md`, `PLAN.md`, `SPEC_PROCESS.md`, `AGENT_LOG.md`, `AGENTS.md`
- Create: `REFLECTION.md`, `docs/FEATURES.md`
- Modify: `docs/DEMO.md`, `docs/DEPLOYMENT.md`, `docs/SECURITY.md`

**Interfaces:**
- Consumes: Task 1–3 最终六阶段 UI 和 Task 4 archive paths。
- Produces: current product homepage, evidence-backed features, five-minute demo, accurate deployment/security boundaries, student-only reflection outline。

- [ ] **Step 1: 写当前产品文档 RED 契约**

把旧 README 测试替换并新增测试：

```python
def test_readme_documents_current_co_learning_product_and_limits() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in (
        "项目简介", "产品特色", "已完成功能", "安装", "运行", "演示", "分发",
        "目录结构", "安全边界", "已知限制", "第三方组件与许可证", "课程交付导航",
    ):
        assert f"## {heading}" in readme
    for phrase in (
        "共学回放式 Coding Agent Harness", "项目接入", "需求描述", "计划审批",
        "执行与验证", "回放与纠正", "交付与经验", "意图卡", "纠正分支",
        "项目经验", "ScriptedMockProvider", "尚未提供用户认证或 HTTPS",
        "WebUI 尚未提供连接测试和主动清除", "真实外网 Provider 任务尚未验收",
    ):
        assert phrase in readme
    for command in ("make test", "make test-unit", "make test-e2e", "make demo"):
        assert command in readme
    docker_runs = [line for line in readme.splitlines() if line.startswith("docker run ")]
    assert any(":/workspace/project:ro" in line and ":/state" in line for line in docker_runs)


def test_features_are_evidence_backed_and_reflection_is_student_authored() -> None:
    features = (ROOT / "docs/FEATURES.md").read_text(encoding="utf-8")
    for phrase in (
        "需求 → 计划审批 → 隔离修改 → 确定性验证 → 回放与纠正 → 经验批准 → 交付",
        "src/coding_agent_harness/agent/orchestrator.py",
        "src/coding_agent_harness/feedback/engine.py",
        "src/coding_agent_harness/learning/intent.py",
        "src/coding_agent_harness/replay/branches.py",
        "web/src/workbench/workflow.ts", "scripts/mechanism_demo.py",
    ):
        assert phrase in features
    reflection = (ROOT / "REFLECTION.md").read_text(encoding="utf-8")
    assert "1500–2500 字" in reflection
    assert "必须由学生本人撰写" in reflection
    for heading in (
        "Superpowers 技能", "TDD", "subagent-driven", "SPEC / PLAN",
        "Prompt / Context", "凭据与分发", "方法论批判", "如果重做",
    ):
        assert f"## {heading}" in reflection
```

```powershell
.\.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py::test_readme_documents_current_co_learning_product_and_limits tests/distribution/test_delivery_files.py::test_features_are_evidence_backed_and_reflection_is_student_authored -v
```

Expected: FAIL，旧 README 过时且 FEATURES/REFLECTION 不存在。

- [ ] **Step 2: 重写 README 与 FEATURES**

README 使用定位：用户提交需求后，Harness 在隔离 worktree 规划、修改、验证和交付；用户通过六阶段工作台理解意图、在失败节点提问/纠正，并把批准经验带入下一任务。保留精确安装、源码运行、Docker 只读挂载、状态卷、一键命令、公网 Mock 风险和课程导航。

`docs/FEATURES.md` 固定章节：完整共学路径、自研内核、确定性反馈、治理/隔离/停止、六阶段工作台、意图回放/提问/纠正、项目经验、Provider/Mock 边界、工程交付、已知限制。每个已完成项至少列一个源码和一个测试/演示路径；不得写“全部完成”或“生产可用”。

- [ ] **Step 3: 重写 DEMO、DEPLOYMENT、SECURITY**

- `DEMO.md`：准备 → 五分钟六阶段 WebUI 主路径 → `make demo` 三机制 → 结束检查；所有按钮/标题使用最终 UI 文案，不触网。
- `DEPLOYMENT.md`：保留已验证源码/Docker/Compose/ECS 命令，明确静态配置已测、Docker daemon/Nginx/ECS 浏览器仍需实机验收、演示后撤销 80。
- `SECURITY.md`：治理护栏；工作区/worktree/进程；Provider 凭据；项目经验/隐私；公网 Mock；剩余风险。保留 `state_root`、同一 UID、不确定副作用、只读、localhost、公网部署尚未验收、Scripted Mock、不访问网络等既有契约词。

- [ ] **Step 4: 创建学生本人反思提纲与许可证说明**

`REFLECTION.md` 开头明确 1500–2500 字、必须学生本人撰写、AI 仅可辅助整理/润色并标注。八节为 Superpowers 技能、TDD、subagent-driven、SPEC / PLAN、Prompt / Context、凭据与分发、方法论批判、如果重做；每节只给问题和证据路径，不写第一人称答案。

README 的许可证表以仓库锁定证据为准：React/React DOM/React Router/Vite/Vitest/ESLint=`MIT`，TypeScript/Playwright=`Apache-2.0`（来自 `web/package-lock.json` 对应包条目）。Python 直接依赖必须从当前锁文件/已安装 distribution metadata 或各包上游 LICENSE 逐项核对；无法确认的条目链接上游 LICENSE 并标记学生复核，不猜测。表格至少列“组件、锁定版本、用途、许可证、证据”。

- [ ] **Step 5: 对齐根过程文档与当前状态**

`SPEC.md` 只补当前共学定位/导航；`SPEC_PROCESS.md` 记录前端逐节选择、文档移动、Provider 勘误和反思边界；`AGENTS.md` 使用 archive ledger 路径并定义当前/历史文档边界；`PLAN.md`/`AGENT_LOG.md` 登记五个 Task 的提交、RED/GREEN、审查和最终未验收项。

- [ ] **Step 6: 聚焦 GREEN、完整门禁和双重审查**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py tests/distribution/test_secret_scan.py -v
mingw32-make test
mingw32-make demo
.\.venv\Scripts\python.exe scripts\secret_scan.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: Python、Vitest、ESLint、mypy、TypeScript、Vite、Playwright、三机制、秘密扫描、pip 与 diff 全部退出 0；Docker capability skip 原样记录。规约审查核对两个批准设计和本计划；质量审查检查声明可定位、命令、链接、许可证、历史完整和反思不越界。Critical/Important/Minor 清零后提交。

- [ ] **Step 7: 提交并准备整分支收尾**

```powershell
git add README.md SPEC.md PLAN.md SPEC_PROCESS.md AGENT_LOG.md AGENTS.md REFLECTION.md docs tests/distribution/test_delivery_files.py
git commit -m "docs: 更新共学工作台交付说明"
```

随后使用 `superpowers:verification-before-completion` 获取最终 Head 新鲜全量证据，使用 `superpowers:requesting-code-review` 做 `merge-base..HEAD` 整分支审查，最后使用 `superpowers:finishing-a-development-branch`。只有远端无分叉、审查无 Critical/Important/Minor 且动态未验收项没有被虚报时，才按用户既有授权非强制推送功能分支、快进合并并推送 `main`；禁止 force push。

## 计划自审结论

- [x] 前端设计的信息架构、阶段规则、组件边界、错误处理、凭据清理、响应式和三层测试均映射到 Task 1–3。
- [x] 文档设计的完整移动清单、路径规则、当前叙事、课程必交物、许可证与反思边界均映射到 Task 4–5。
- [x] `WorkbenchStage`、`WorkflowSnapshot`、`WorkflowEvidence` 和全部纯函数签名在 Task 1 定义，Task 2/3 只消费相同接口。
- [x] 五个 Task 严格串行，每个 Task 有确定性 RED、GREEN、聚焦门禁、双重审查和中文提交。
- [x] 不修改后端、不增加依赖、不触网、不移动未跟踪报告、不代写反思、不触碰用户临时目录。
- [x] 没有 TBD/TODO、模糊占位、未定义类型或伪造成功状态。
