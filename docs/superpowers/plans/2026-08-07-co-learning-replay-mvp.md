# 共学回放式 Harness 精简版实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有可运行 Harness 上交付一条最小共学纵向路径：真实 Provider 运行、四类意图卡、失败节点只读提问、单级纠正分支，以及一条经用户批准并影响下一任务的项目经验。

**Architecture:** 继续以 `AgentOrchestrator` 和 `TaskEvent` 作为唯一执行循环与事实来源；意图卡由事件确定性投影，提问通过零工具 Provider 入口，纠正分支冻结父 worktree 的写租约后在新 worktree 恢复有界文本 patch，项目经验只保存最近一条用户批准记录。新增 API 与 WebUI 只服务唯一旗舰路径，不实现通用回放、凭据管理或知识管理平台。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、SQLite/aiosqlite、httpx、pytest、React 19、TypeScript 6、Vitest、Playwright。

## Global Constraints

- Python 必须为 `>=3.11,<3.12`；Node.js 必须为 `>=24,<25`；不得新增或升级依赖。
- Agent 循环、事件、治理、反馈、工具、worktree 和停止逻辑继续使用仓库自有实现，不引入高层 Agent Runner。
- DeepSeek/Qwen 地址固定；HTTP client 必须 `trust_env=False`、`follow_redirects=False`，核心测试只使用 `httpx.MockTransport`。
- 首版产品路径只接受进程内会话 API Key；Key、问题中的敏感值、检查点正文和经验敏感值不得进入日志、异常、事件、报告、浏览器存储或 Git。
- 只读提问不能获得工具 schema，不能改变 Task state、代码、审批或 worktree。
- 每个 Workspace 始终最多一个活动写 worktree；纠正分支只能在父 worktree 冻结为只读并释放写租约后创建。
- 检查点 patch 上限为 `1 MiB`，只支持已跟踪 UTF-8 文本文件的修改或删除；未跟踪文件、rename/copy、binary patch、NUL 和超限固定拒绝并进入 `WAITING_USER`。
- 问题上限 `4096` UTF-8 bytes，回答上限 `16 KiB`；项目经验上限 `2048` UTF-8 bytes。
- 所有新增时间为 UTC-aware 并以 ISO 8601 保存；排序必须有稳定 ID 次级键。
- 现有 Mock 三机制、课程安全要求、`make demo`、双 CI、Docker 和现有 WebUI 主路径不得回退。
- 每个 Task 使用 TDD、一个中文任务提交和一次合并的规约/质量审查；只对 Critical/Important 做定向返工。

---

### Task 1: 关闭已实现的 Provider 核心

**当前状态：** 已关闭。实现提交为 `437d7d7`、`765c9e9`、`4b5d977`、`25a81ff`、`7f7fde1`、`a49ad27`、`f17ac16`；`a49ad27..f17ac16` 合并规约/质量复审为 Approved，Critical / Important / Minor 均为 0。

**Files:**
- Existing: `src/coding_agent_harness/providers/registry.py`
- Existing: `tests/providers/test_registry.py`
- Modify after review: `PLAN.md`
- Modify after review: `AGENT_LOG.md`

**Interfaces:**
- Produces: `ProviderRegistry.build_for_task(task: Task) -> LLMProvider`
- Produces: `PROVIDER_ENDPOINTS: Mapping[ProviderKind, str]`
- Produces: `_default_client_factory() -> httpx.AsyncClient`，固定 `trust_env=False`、`follow_redirects=False`

- [x] **Step 1: 保存环境代理 RED 证据**

```python
async def test_registry_default_client_factory_disables_environment_and_redirects() -> None:
    await registry.build_for_task(authorized_task)
    assert client_constructor.kwargs == {"trust_env": False, "follow_redirects": False}
```

- [x] **Step 2: 最小 GREEN 与提交**

`f17ac16` 已把默认 factory 固定为 `httpx.AsyncClient(trust_env=False, follow_redirects=False)`；Provider 回归为 `42 passed`，Ruff、mypy、秘密扫描和 diff check 已通过。

- [x] **Step 3: 生成修复差异包并执行一次范围复审**

Run: `review-package docs/superpowers/plans/2026-08-07-co-learning-replay-mvp.md a49ad27 f17ac16`

Expected: 原 Critical “默认 client 采用环境代理” 为 ADDRESSED；无新 Critical/Important。client 生命周期 Minor 转入 Task 2 的共享 lifespan client，不在本 Task 扩展。

- [x] **Step 4: 回填任务状态**

更新 `PLAN.md` 与 `AGENT_LOG.md`，记录复审结论和 `f17ac16`；提交：

```text
git add PLAN.md AGENT_LOG.md
git commit -m "docs: 关闭 Provider 核心任务"
```

### Task 2: 真实 Provider 最小纵向接线

**当前状态：** 已关闭。实现提交 `abac70b`，审查返工 `d39baef`，延期台账修订 `ff9e37d`、`691e272`；最终合并规约/质量复审为 Approved，Critical / Important / Minor 均为 0。

**Files:**
- Create: `src/coding_agent_harness/runtime.py`
- Create: `src/coding_agent_harness/api/provider_routes.py`
- Create: `tests/agent/test_runtime.py`
- Create: `tests/api/test_providers.py`
- Modify: `src/coding_agent_harness/providers/credentials.py`
- Modify: `src/coding_agent_harness/api/dependencies.py`
- Modify: `src/coding_agent_harness/api/app.py`
- Modify: `src/coding_agent_harness/api/routes.py`
- Modify: `tests/api/conftest.py`
- Modify: `tests/api/test_tasks.py`
- Modify: `web/src/types.ts`
- Modify: `web/src/api.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/api.test.ts`

**Interfaces:**
- Produces: `SessionOnlyCredentialStore.get(reference) -> None`；`put` 固定拒绝持久化，`delete` 幂等；`CredentialBroker.clear_session() -> None` 在应用关闭时覆盖并清空全部会话引用。
- Produces: `RuntimeOrchestratorRouter(OrchestratorPort)`，五个方法与现有 `OrchestratorPort` 完全一致。
- Produces: `GET /api/providers`、`POST /api/providers`、`PUT /api/providers/{profile_id}/session-credential`。
- Extends: `TaskRequest.provider_profile_id: UUID | None`；默认生产依赖要求非空，现有注入 Mock runtime 允许空值。
- Extends: `ApiDependencies.profiles`、`credentials`、`provider_registry` 为可选依赖；全部存在时启用真实 Provider 路径。

- [x] **Step 1: 写 API、运行时和浏览器秘密生命周期 RED**

```python
async def test_real_task_reuses_existing_feedback_loop(runtime_fixture) -> None:
    task = await runtime_fixture.create_task_with_session_provider()
    final = await runtime_fixture.run_stubbed_http_task(task.id)
    assert final.state is TaskState.WAITING_FINAL_REVIEW
    assert runtime_fixture.feedback_appeared_in_next_request()

async def test_missing_session_key_fails_before_worktree(client) -> None:
    response = await client.post("/api/tasks", json=REAL_TASK_REQUEST, headers=MUTATION_HEADERS)
    assert response.json()["code"] == "PROVIDER_CREDENTIAL_REQUIRED"
    assert not worktree_root.exists()
```

Web RED 必须证明密码输入使用 `type="password"`、不写 `localStorage/sessionStorage`、mutation 成功或失败后 state 均清空，并把 `provider_profile_id` 发给任务 API。

- [x] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/agent/test_runtime.py tests/api/test_providers.py tests/api/test_tasks.py -q`

Run: `npm.cmd --prefix web run test -- --run`

Expected: FAIL，缺少 runtime、Provider routes 和 Web 类型/入口。

- [x] **Step 3: 实现最小 session Provider API 与依赖生命周期**

`POST /api/providers` 只接受 `{kind, model}`；session credential 只接受 `{api_key}`，1–192 UTF-8 bytes、拒绝 NUL。所有 mutation 复用现有 Origin/session guard。响应只返回：

```json
{"id":"uuid","kind":"deepseek","model":"deepseek-chat","version":1,"configured":true}
```

`create_app` 默认创建共享 `httpx.AsyncClient(trust_env=False, follow_redirects=False)`、Profile repository、session-only Broker 和 Registry；Registry 的 `client_factory` 固定返回该共享 client，不为每个 Task 创建连接池。关闭顺序为停止请求 → `aclose()` HTTP client → `CredentialBroker.clear_session()` → 关闭数据库。

- [x] **Step 4: 实现真实 RuntimeOrchestratorRouter**

从 `DemoOrchestratorRouter._for` 提取共用构造逻辑到 `runtime.py`。真实 router 用 `ProviderRegistry.build_for_task(task)` 构造 Provider；工具固定为 `read_file/search/apply_patch/run_verification/git_status/git_diff`。`PolicyContext.llm_api_authorized=True` 只描述 LLM 调用，不能授权 Shell、安装、工具网络或远程 Git。

创建真实任务前按顺序验证 Profile 存在、session credential configured、Profile version 当前，再把 profile ID/version/当前 UTC 时间与 Task 同次持久化；任何失败发生在 worktree 创建前。

- [x] **Step 5: 实现最小 WebUI 输入**

沿用现有单页，只增加 Provider 类型、model、API Key 与已配置 Profile 下拉框。API Key 只存在 React state；切换项目、任务、请求成功或失败均立即设为 `""`。不实现 edit/delete/probe/unlock/persistence 选择。

- [x] **Step 6: 运行 GREEN 与静态检查**

Run: `.venv\Scripts\python.exe -m pytest tests/providers tests/agent/test_runtime.py tests/agent/test_real_tool_loop.py tests/api/test_providers.py tests/api/test_tasks.py -q`

Run: `.venv\Scripts\python.exe -m ruff check src tests`

Run: `.venv\Scripts\python.exe -m mypy src`

Run: `npm.cmd --prefix web run test -- --run`

Run: `npm.cmd --prefix web run lint && npm.cmd --prefix web run typecheck`

Run: `npm.cmd --prefix web run build`

Run: `.venv\Scripts\python.exe scripts\secret_scan.py`

Expected: PASS；所有 HTTP 使用 Stub/MockTransport，响应、事件、异常和 DOM 均无假 secret。

- [x] **Step 7: 合并任务审查并提交**

审查重点：worktree 前置拒绝、共享 client 关闭、Key 生命周期、真实 runtime 复用现有反馈闭环、Mock 路径不回退。

```text
git add src/coding_agent_harness/runtime.py src/coding_agent_harness/api src/coding_agent_harness/providers/credentials.py tests/agent tests/api web/src PLAN.md AGENT_LOG.md
git commit -m "feat: 连通真实 Provider 最小主路径"
```

### Task 3: 四类意图卡与失败节点只读提问

**当前状态：** 已关闭。实现提交 `e979612`，审查返工 `e0a0f5f`，报告修订 `4b9b952`；最终合并规约/质量复审为 Approved，Critical / Important / Minor 均为 0。

**Files:**
- Create: `src/coding_agent_harness/learning/__init__.py`
- Create: `src/coding_agent_harness/learning/intent.py`
- Create: `src/coding_agent_harness/learning/questions.py`
- Create: `src/coding_agent_harness/api/learning_routes.py`
- Create: `tests/learning/test_intent.py`
- Create: `tests/learning/test_questions.py`
- Create: `tests/api/test_learning.py`
- Modify: `src/coding_agent_harness/api/dependencies.py`
- Modify: `src/coding_agent_harness/api/app.py`
- Modify: `web/src/types.ts`
- Modify: `web/src/api.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`

**Interfaces:**

```python
class IntentKind(StrEnum):
    PLAN = "plan"
    FIRST_EDIT = "first_edit"
    VERIFICATION_FAILURE = "verification_failure"
    FINAL_DELIVERY = "final_delivery"

class IntentCard(BaseModel):
    id: str
    task_id: UUID
    kind: IntentKind
    intent: str
    evidence_sequences: tuple[int, ...]
    action: str
    expected_result: str
    actual_result: str
    status: str
    source_event_sequence: int
    learning_card_id: UUID | None = None

class IntentProjector:
    def project(self, task_id: UUID, events: Sequence[TaskEvent]) -> tuple[IntentCard, ...]: ...

class QuestionService:
    async def ask(self, task_id: UUID, card_id: str, question: str) -> ReadOnlyAnswer: ...
```

- [x] **Step 1: 写确定性投影与零工具 RED**

同一乱序输入先按 sequence 排序，固定投影四张卡；重复事件不产生重复卡。`FIRST_EDIT` 使用首个 `TOOL_EXECUTION_COMPLETED.result.changed_paths` 非空事件；失败卡绑定 `VERIFICATION_FAILED` 和最近的 `VERIFICATION_RECORDED/FEEDBACK_RECORDED`；最终卡绑定 `FINAL_SUMMARY_PROPOSED`。

```python
async def test_question_is_zero_tool_and_state_preserving(fixture) -> None:
    before = await fixture.task_and_files()
    answer = await fixture.questions.ask(TASK_ID, FAILURE_CARD_ID, "为什么失败？")
    after = await fixture.task_and_files()
    assert answer.content == "Stub explanation"
    assert after == before
    assert fixture.registered_tools == ()
```

- [x] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/learning/test_intent.py tests/learning/test_questions.py tests/api/test_learning.py -q`

Expected: FAIL，`learning` package 与 routes 不存在。

- [x] **Step 3: 实现纯投影器和 QuestionService**

卡片 ID 固定为 `{task_id}:{kind}:{source_event_sequence}`。所有字符串经 Redactor 后分别限制为 8 KiB；不保存 raw chain-of-thought。问题先校验 1–4096 UTF-8 bytes，再调用任务 Registry Provider。`LLMRequest` 只包含卡片、问题和最多 8 KiB 的事件摘要；Provider 接口本身不接收 ToolRegistry。

追加 `LEARNING_QUESTION_ASKED/ANSWERED/FAILED` 事件时 `state_before == state_after == 当前 Task state`。失败事件只保存稳定 Provider kind，不保存第三方正文。

- [x] **Step 4: 增加最小 API 与卡片 UI**

端点固定为：

```text
GET  /api/tasks/{task_id}/intent-cards
POST /api/tasks/{task_id}/questions  {card_id, question}
```

只有 failure card 显示问题输入和按钮；提交后显示回答。UI 不渲染 HTML，不显示隐藏 prompt 或未脱敏 payload。

- [x] **Step 5: GREEN、静态检查、审查与提交**

Run: `.venv\Scripts\python.exe -m pytest tests/learning tests/api/test_learning.py tests/storage/test_event_store.py -q`

Run: `.venv\Scripts\python.exe -m ruff check src tests && .venv\Scripts\python.exe -m mypy src`

Run: `npm.cmd --prefix web run test -- --run && npm.cmd --prefix web run lint && npm.cmd --prefix web run typecheck`

Run: `npm.cmd --prefix web run build && .venv\Scripts\python.exe scripts\secret_scan.py`

Expected: PASS；重复投影稳定，提问无工具、无状态变化、无文件变化。

```text
git add src/coding_agent_harness/learning src/coding_agent_harness/api tests/learning tests/api web/src PLAN.md AGENT_LOG.md
git commit -m "feat: 提供意图卡与只读提问"
```

### Task 4: 单级纠正分支与简化比较

**当前状态：** 已关闭。实现 `bc46400`，审查返工 `304b83e`，兼容迁移 `e7fccd9`；最终合并规约/质量复审为 Approved，Critical / Important 为 0 / 0，Task 5 文档 Minor 已在启动前修正。

**Files:**
- Create: `src/coding_agent_harness/storage/migrations/005_correction_branches.sql`
- Create: `src/coding_agent_harness/storage/migrations/006_correction_branch_child_reservation.sql`
- Create: `src/coding_agent_harness/replay/__init__.py`
- Create: `src/coding_agent_harness/replay/checkpoints.py`
- Create: `src/coding_agent_harness/replay/branches.py`
- Create: `src/coding_agent_harness/storage/correction_branches.py`
- Create: `src/coding_agent_harness/api/replay_routes.py`
- Create: `tests/replay/test_checkpoints.py`
- Create: `tests/replay/test_branches.py`
- Create: `tests/api/test_replay.py`
- Create: `tests/storage/test_migration_005.py`
- Modify: `src/coding_agent_harness/agent/orchestrator.py`
- Modify: `src/coding_agent_harness/api/dependencies.py`
- Modify: `src/coding_agent_harness/api/app.py`
- Modify: `src/coding_agent_harness/workspace/worktrees.py`
- Modify: `tests/workspace/test_worktrees.py`
- Modify: `tests/distribution/test_delivery_files.py`
- Modify: `web/src/types.ts`
- Modify: `web/src/api.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`

**Interfaces:**

```python
class Checkpoint(BaseModel):
    parent_task_id: UUID
    source_event_sequence: int
    base_commit: str
    patch_sha256: str
    patch_bytes: int
    file_name: str

class CorrectionBranch(BaseModel):
    id: UUID
    workspace_id: UUID
    parent_task_id: UUID
    source_event_sequence: int
    child_task_id: UUID | None
    status: Literal["CREATING", "READY", "UNCERTAIN"]
    created_at: datetime

class CorrectionBranchService:
    async def create(self, parent_task_id: UUID, source_event_sequence: int, correction: str) -> CorrectionBranch: ...
    async def compare(self, branch_id: UUID) -> BranchComparison: ...
```

- [x] **Step 1: 写失败暂停、检查点边界和单写者 RED**

`AgentOrchestrator(pause_on_verification_failure=True)` 在 `VERIFICATION_FAILED` 后追加 `USER_INPUT_REQUIRED(reason_code="LEARNING_CHECKPOINT")` 并返回；默认 `False` 保持现有 Mock 三机制自动反馈。

检查点测试覆盖 1 MiB 边界、UTF-8、NUL、binary、untracked、rename、摘要篡改。worktree 测试证明 `freeze(task_id)` 保留父 target/branch、写入私有 frozen marker、移除精确 `.active` owner，随后只允许一个新 writer；`assert_writable(task_id)` 对冻结父任务固定失败，Runtime 在每次 `run_until_wait` 前调用它。

- [x] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/replay tests/workspace/test_worktrees.py tests/storage/test_migration_005.py tests/api/test_replay.py -q`

Expected: FAIL，缺少 migration 005、replay package 和 `freeze`。

- [x] **Step 3: 实现 migration 005 与幂等仓储**

```sql
CREATE TABLE correction_branches (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    parent_task_id TEXT NOT NULL REFERENCES tasks(id),
    source_event_sequence INTEGER NOT NULL CHECK (source_event_sequence > 0),
    child_task_id TEXT REFERENCES tasks(id),
    status TEXT NOT NULL CHECK (status IN ('CREATING','READY','UNCERTAIN')),
    base_commit TEXT NOT NULL,
    patch_sha256 TEXT NOT NULL,
    patch_bytes INTEGER NOT NULL CHECK (patch_bytes BETWEEN 1 AND 1048576),
    checkpoint_file_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(parent_task_id, source_event_sequence)
);
```

Service 先只读捕获 patch 到内存，再由 Repository 用 `BEGIN IMMEDIATE` 预留唯一记录；只有赢得 `CREATING` 记录的 owner 可以写 checkpoint 或执行 worktree 副作用。并发第二请求读取并返回同一记录；若首请求停在 `CREATING`，重试固定返回 `BRANCH_CREATION_UNCERTAIN`，不得重复 worktree 副作用。

- [x] **Step 4: 实现安全检查点和父 worktree 冻结**

只接受 `git status --porcelain=v1 -z` 表明没有 untracked/rename/copy，以及 `git diff --no-ext-diff --no-color --binary HEAD --` 产生的 UTF-8、无 NUL、无 `GIT binary patch`、不超过 1 MiB 的 patch。以 `O_EXCL` 临时文件、flush/fsync、`os.replace` 写入 `state_root/checkpoints/{branch_id}.patch`，数据库只保存文件名和摘要。

`WorktreeManager.freeze(task_id)` 必须验证 marker owner、linked worktree 注册和 Git 身份；先创建私有 frozen marker并 fsync，再删除 `.active`。`assert_writable(task_id)` 只接受当前 `.active` owner 且拒绝 frozen marker。任一后验不确定固定抛 `WorktreeUncertainError`，不删除父现场。

- [x] **Step 5: 实现唯一子任务和比较**

扩展 `LocalTaskRunner.create(..., base_commit="HEAD", initial_patch: bytes | None = None)`；有 patch 时在新 worktree 通过 `SafeGit.run(..., ["apply", "--whitespace=nowarn", "-"], stdin=patch)` 恢复，失败保留子现场并把 branch 标成 `UNCERTAIN`。

任何副作用前先用 `ProviderRegistry.build_for_task(parent)` 复验父任务的精确 Profile/version 与 session credential。子任务复制该绑定，需求为原 requirement 与经过 Redactor/8 KiB 限长的用户 correction。TaskRunner 持久化后由同一 `RuntimeOrchestratorRouter.propose_plan(child_id)` 生成计划；若 Provider 此时失败，记录稳定 runtime failure 并保留已创建 child，不重建 worktree。比较只读取父 checkpoint、父/子事件，返回两边 task state、最近验证摘要和最终 diff；不执行 LLM。

- [x] **Step 6: 增加 API/UI**

```text
POST /api/tasks/{task_id}/correction-branches {source_event_sequence, correction}
GET  /api/correction-branches/{branch_id}/comparison
```

只有 `verification_failure` 卡显示“从此纠正”。UI 只并排显示状态、验证摘要和 diff 文本，不做通用时间轴。

- [x] **Step 7: GREEN、迁移矩阵、审查与提交**

Run: `.venv\Scripts\python.exe -m pytest tests/replay tests/workspace/test_worktrees.py tests/storage/test_migration_005.py tests/api/test_replay.py tests/agent/test_orchestrator.py -q`

Run: `.venv\Scripts\python.exe -m ruff check src tests && .venv\Scripts\python.exe -m mypy src`

Run: `npm.cmd --prefix web run test -- --run && npm.cmd --prefix web run lint && npm.cmd --prefix web run typecheck`

Run: `npm.cmd --prefix web run build && .venv\Scripts\python.exe scripts\secret_scan.py`

Expected: PASS；原自动反馈 demo 不变，父轨迹和 worktree 内容不变，只有写租约被冻结。

```text
git add src/coding_agent_harness/replay src/coding_agent_harness/storage src/coding_agent_harness/workspace src/coding_agent_harness/agent src/coding_agent_harness/api tests web/src PLAN.md AGENT_LOG.md
git commit -m "feat: 支持单级纠正分支"
```

### Task 5: 单条项目经验与最终旗舰验收

**当前状态：** 已关闭。实现与返工提交为 `b0a7a00`、`81b3d3d`、`e689fc1`、`9f9b25f`、`1f61d5d`、`3be3d5c`、`2c765a8`、`e71d6b0`；最终合并规约/质量复审为 Spec Yes、Approved，Critical / Important / Minor 均为 0，Ready to merge Yes。

**Files:**
- Create: `src/coding_agent_harness/storage/migrations/007_project_learning.sql`
- Create: `src/coding_agent_harness/learning/cards.py`
- Create: `src/coding_agent_harness/storage/project_learning.py`
- Create: `tests/learning/test_cards.py`
- Create: `tests/storage/test_migration_007.py`
- Modify: `src/coding_agent_harness/agent/orchestrator.py`
- Modify: `src/coding_agent_harness/runtime.py`
- Modify: `src/coding_agent_harness/api/learning_routes.py`
- Modify: `src/coding_agent_harness/api/dependencies.py`
- Modify: `src/coding_agent_harness/api/app.py`
- Modify: `tests/agent/test_runtime.py`
- Modify: `tests/api/test_learning.py`
- Modify: `tests/distribution/test_delivery_files.py`
- Modify: `web/src/types.ts`
- Modify: `web/src/api.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `web/e2e/harness.spec.ts`
- Modify: `README.md`
- Modify: `docs/DEMO.md`
- Modify: `docs/SECURITY.md`
- Modify: `DEFERRED_WORK.md`
- Modify: `PLAN.md`
- Modify: `AGENT_LOG.md`

**Interfaces:**

```python
class ProjectLearningCard(BaseModel):
    id: UUID
    workspace_id: UUID
    text: str
    source_task_id: UUID
    source_event_sequence: int
    approved_at: datetime

class ProjectLearningService:
    async def approve(self, task_id: UUID, source_event_sequence: int, text: str) -> ProjectLearningCard: ...
    async def latest_for_workspace(self, workspace_id: UUID) -> ProjectLearningCard | None: ...
```

- [x] **Step 1: 写批准门、敏感拒绝和实际影响 RED**

```python
async def test_only_approved_latest_card_changes_next_action(fixture) -> None:
    await fixture.reject_candidate("旧规则")
    approved = await fixture.approve_completed_task("先运行聚焦测试再修改")
    next_task = await fixture.create_next_task()
    assert fixture.provider_request(next_task).contains(str(approved.id))
    assert fixture.next_action(next_task).tool == "run_verification"
```

另测：非 `COMPLETED` task 拒绝；非 final-delivery event 拒绝；Redactor 命中、NUL、空值、>2048 bytes 整条拒绝；排序为 `approved_at DESC, id ASC`。

- [x] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/learning/test_cards.py tests/storage/test_migration_007.py tests/agent/test_runtime.py tests/api/test_learning.py -q`

Expected: FAIL，migration 007、repository 和 service 不存在。

- [x] **Step 3: 实现 migration、批准与下一任务注入**

```sql
CREATE TABLE project_learning_cards (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    text TEXT NOT NULL,
    source_task_id TEXT NOT NULL REFERENCES tasks(id),
    source_event_sequence INTEGER NOT NULL CHECK (source_event_sequence > 0),
    approved_at TEXT NOT NULL,
    UNIQUE(source_task_id)
);
CREATE INDEX project_learning_latest_idx
    ON project_learning_cards(workspace_id, approved_at DESC, id ASC);
```

批准前复验 Task 为 `COMPLETED`、来源事件为该 Task 的 `FINAL_SUMMARY_PROPOSED`。敏感过滤只要 Redactor 发生替换就拒绝整条。Runtime 构造 task orchestrator 时加载最近一条，把 `{card_id,text}` 作为独立、有界且不可信的 project context，并在首次 `propose_plan` 前幂等追加 `PROJECT_LEARNING_APPLIED`；它不能修改工具集合、治理或审批。IntentProjector 把 card ID 放入 plan card。

- [x] **Step 4: 增加 API/UI 与唯一旗舰 E2E**

```text
POST /api/tasks/{task_id}/project-learning {source_event_sequence, text}
GET  /api/projects/{workspace_id}/project-learning/latest
```

最终交付卡以 final summary 预填一条可编辑经验，只有用户点击批准才保存。下一任务顶部显示经验 ID 与文本。Playwright 只新增一个确定性场景：失败卡 → 提问 → 纠正分支 → 新分支验证通过 → 比较 → 最终批准 → 批准经验 → 下一任务首卡引用并改变 Mock 动作。

- [x] **Step 5: 更新延期和中文文档**

`DEFERRED_WORK.md` 登记 Provider 管理/持久凭据 UI/probe/smoke、通用或加密检查点、多级分支、复杂学习卡和最终视觉设计；每项写明当前替代、影响和重新启动条件。README/DEMO/SECURITY 只描述真实存在的入口，真实联网未执行时明确写“未执行”。

- [x] **Step 6: 运行最终新鲜验收**

Run: `mingw32-make test`

Run: `mingw32-make demo`

Run: `.venv\Scripts\python.exe scripts\secret_scan.py`

Run: `.venv\Scripts\python.exe -m pip check`

Expected: Python 全量、Ruff、mypy、Vitest、ESLint、TypeScript、Vite、现有 Playwright、唯一新增旗舰 E2E、三机制 demo、秘密扫描和依赖一致性全部退出 0。CI 不访问真实 Provider。

- [x] **Step 7: 最终合并审查与提交**

审查逐条对照 `SPEC.md` 16 节，确认所有延期合法且现有课程门禁不回退。Critical/Important 为 0 且 Step 6 证据仍新鲜后提交：

```text
git add src tests web README.md docs DEFERRED_WORK.md PLAN.md AGENT_LOG.md
git commit -m "feat: 交付共学回放式 Harness 精简版"
```

随后使用 `superpowers:finishing-a-development-branch`，把 `codex/cl1-providers` 本地合并回 `p1`；不自动 push。

## 计划自审

- [x] `SPEC.md` 16.1—16.5 均映射到 Task 1—5。
- [x] Task 2 先交付 Provider 主路径，Task 3 只消费稳定 runtime/事件，Task 4 只消费失败卡，Task 5 只消费已完成轨迹和 runtime context。
- [x] 父 worktree 冻结解决现有单写者与纠正分支并存的冲突，没有放宽并发写安全。
- [x] 所有新增类型在首次消费前定义；API、错误边界、字节上限、排序和迁移 SQL 均无占位。
- [x] 每个 Task 都有 RED、GREEN、聚焦验证、合并审查和中文提交。
- [x] 全量测试只在最终 Task 运行；安全负向测试和现有课程门禁没有延期。
