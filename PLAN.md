# Coding Agent Harness 实施计划

> **供智能体执行者使用：** 必须使用 `subagent-driven-development`（推荐）或 `executing-plans` 逐项实施本计划。所有步骤使用 `- [ ]` 跟踪；每个行为必须先执行红—绿—重构 TDD，再依次进行规约符合性审查和代码质量审查。

**目标：** 构建一个本地优先、带 WebUI、能够在隔离 Git worktree 中根据客观验证反馈自动修正代码，并以确定性治理和有界反馈闭环为核心贡献的 Coding Agent Harness。

**架构：** 后端使用 Python 事件驱动可恢复状态机，自行实现 Agent 循环、动作解析、工具分发、治理、反馈、记忆和停止逻辑；SQLite 以追加事件和关系表保存状态。React WebUI 通过同源 REST 发命令、通过 SSE 接收事件；DeepSeek、Qwen 与 Scripted Mock 共用可注入 `LLMProvider`。

**技术栈：** Python 3.11、FastAPI、Pydantic、SQLite、httpx、React 19、TypeScript、Vite、pytest、Vitest、Playwright、Ruff、mypy、Docker、GitHub Actions、GitLab CI。

## 全局约束

- Python 最低且基准版本为 3.11；Node.js 基准版本为 24；正式容器目标为 `linux/amd64` 与 `linux/arm64`。
- 不得使用 LangChain AgentExecutor、AutoGen、CrewAI、LlamaIndex Agents 或其他高层 Agent Runner。
- LLM 只能提出严格类型化动作，不能直接调用工具；所有安全、反馈、记忆和停机机制必须由仓库代码确定性实现。
- 默认先生成并批准计划；只有用户显式设置 `skip_plan=true` 才能跳过计划，但仍不能跳过治理、完整验证和最终审查。
- 删除、工作区外访问、安装依赖、工具网络请求、Git push/merge、发布和高风险 Shell 必须进入版本化审批。
- 同一失败指纹最多修正 3 轮；单任务最多 8 个验证—修正循环；连续 2 轮失败数未减少且类别未变化时进入 `WAITING_USER`；命令默认超时 300 秒。
- Mock LLM 核心测试不得访问网络或真实 LLM；测试和日志不得包含真实凭据。
- 一个 Workspace 同时最多一个写任务，全局默认最多 3 个并发任务；正式支持最多 10,000 个 Git 跟踪文件。
- 文档和 Git 提交说明尽量使用中文；代码标识符、命令、标准文件名和第三方名称保留英文。
- 每个 Task 使用独立 `codex/` 前缀分支和 worktree；完成后在本文件勾选状态并记录提交哈希与评审结论。
- 每个 Task 固定执行顺序：失败测试 → 确认失败原因 → 最小实现 → 通过目标测试 → 重构 → 完整相关测试 → 规约符合性审查 → 代码质量审查 → 中文提交。
- 所有 Python 命令必须使用项目 `.venv` 中的 Python 3.11，不得依赖 PATH 中含义不明的 `python`；Windows 对应 `& .\.venv\Scripts\python.exe`，POSIX 对应 `.venv/bin/python`。后文简写 `python` 时均指该已验证解释器。
- Windows PowerShell 中所有 npm 命令必须显式调用 `npm.cmd`，不得依赖可能被 ExecutionPolicy 拦截的 `npm.ps1`；POSIX 使用 `npm`。后文简写 npm 时必须按此平台规则展开，`scripts/test.ps1` 也必须通过 `Get-Command npm.cmd` 调用。

## 锁定依赖

以下版本在 2026-07-14 从 [PyPI](https://pypi.org/) 与 [npm Registry](https://www.npmjs.com/) 官方注册表核对。实现 Task 1 时写入锁文件；若版本已撤回，只允许更新到兼容补丁版，并在 `AGENT_LOG.md` 说明原因。

### Python 运行依赖

```text
fastapi==0.139.0
uvicorn==0.51.0
pydantic==2.13.4
pydantic-settings==2.14.2
httpx==0.28.1
aiosqlite==0.22.1
keyring==25.7.0
cryptography==49.0.0
argon2-cffi==25.1.0
PyYAML==6.0.3
```

### Python 开发依赖

```text
pip==26.1.2
setuptools==83.0.0
pytest==9.1.1
pytest-asyncio==1.4.0
pytest-cov==7.1.0
ruff==0.15.21
mypy==2.3.0
pip-tools==7.5.3
```

### Web 运行与开发依赖

```text
react@19.2.7
react-dom@19.2.7
react-router-dom@7.18.1
vite@8.1.4
typescript@6.0.3
vitest@4.1.10
@vitejs/plugin-react@6.0.3
@types/react@19.2.17
@types/react-dom@19.2.3
@types/node@24.13.3
@testing-library/react@16.3.2
@testing-library/user-event@14.6.1
@testing-library/jest-dom@6.9.1
jsdom@29.1.1
eslint@10.7.0
@eslint/js@10.0.1
typescript-eslint@8.64.0
eslint-plugin-react-hooks@7.1.1
eslint-plugin-react-refresh@0.5.3
@playwright/test@1.61.1
```

## 文件结构与职责

```text
src/coding_agent_harness/
  config.py                         # 全局与项目配置、预算、限制
  domain/{actions,events,models}.py # 共享枚举与不可变协议模型
  providers/{base,mock,openai_compatible}.py
  storage/{database,event_store,repositories}.py
  storage/migrations/001_initial.sql
  governance/{paths,redaction,policy,approvals}.py
  workspace/{detector,scanner,worktrees}.py
  tools/{base,registry,files,patch,shell,git}.py
  feedback/{models,classifier,fingerprint,progress,engine}.py
  memory/{filter,store,context}.py
  agent/{parser,state_machine,orchestrator}.py
  credentials/{base,keyring_store,encrypted_store,service}.py
  artifacts/builder.py
  api/{app,dependencies}.py
  api/routes/{workspaces,tasks,approvals,settings,events}.py
  demo.py
web/src/
  api/{client,events,types}.ts
  components/{AppShell,StatusBadge,EventTimeline,DiffPanel,ApprovalCard}.tsx
  pages/{ProjectsPage,NewTaskPage,TaskPage,ApprovalsPage,SettingsPage,DemoPage}.tsx
  App.tsx、main.tsx、styles.css
tests/                              # 与后端模块一一对应的单元/集成测试
web/src/**/*.test.tsx               # 组件与页面测试
e2e/                                # Playwright 与临时 Git fixture
examples/mock-project/              # 公网演示可重建示例项目
scripts/{test.ps1,mechanism_demo.py} # Windows 等价命令与确定性演示
```

## 共享接口契约

后续 Task 必须使用以下名称和签名，不得自行改名；确需修改时先更新本计划并记录原因。

```python
class LLMProvider(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...

class Tool(Protocol):
    name: str
    async def run(self, action: ToolAction, context: ToolContext) -> ToolResult: ...

class EventStore:
    async def append(self, event: TaskEvent, expected_sequence: int) -> TaskEvent: ...
    async def list_for_task(self, task_id: UUID, after: int = 0) -> list[TaskEvent]: ...

class PolicyEngine:
    def evaluate(self, action: ToolAction, context: PolicyContext) -> PolicyResult: ...

class FeedbackEngine:
    def evaluate(self, task: Task, run: VerificationRun) -> FeedbackDecision: ...

class TaskOrchestrator:
    async def step(self, task_id: UUID) -> TaskState: ...
    async def resume(self, task_id: UUID) -> TaskState: ...
```

`TaskState` 的合法状态固定为 `CREATED`、`SCANNING`、`PLANNING`、`WAITING_PLAN_APPROVAL`、`DECIDING`、`WAITING_ACTION_APPROVAL`、`EXECUTING`、`VERIFYING`、`CORRECTING`、`WAITING_FINAL_REVIEW`、`WAITING_USER`、`COMPLETED`、`FAILED`、`CANCELLED`。

## Task 依赖、并行与状态

| Task | 交付单元 | 依赖 | 可并行关系 | 建议分支 | 状态/提交 |
|---|---|---|---|---|---|
| 1 | 工程骨架与质量门禁 | 无 | 无 | `codex/foundation` | 待执行 |
| 2 | 领域模型、Provider 与动作解析 | 1 | 可与 5 的扫描只读部分并行 | `codex/core-contracts` | 待执行 |
| 3 | SQLite 事件存储与状态机 | 2 | 可与 10 并行 | `codex/event-state` | 待执行 |
| 4 | 治理、路径围栏、脱敏与审批 | 2、3 | 可与 5 并行 | `codex/governance` | 待执行 |
| 5 | 项目识别、扫描与 worktree | 1、2 | 可与 4 并行 | `codex/workspaces` | 待执行 |
| 6 | 工具注册表和受限编码工具 | 4、5 | 无 | `codex/tools` | 待执行 |
| 7 | 验证与确定性反馈闭环 | 2、6 | 可与 8 并行 | `codex/feedback` | 待执行 |
| 8 | 记忆筛选、存储与上下文 | 3、4 | 可与 7 并行 | `codex/memory` | 待执行 |
| 9 | Agent 编排循环与机制演示 | 3—8 | 无 | `codex/orchestrator` | 待执行 |
| 10 | 凭据生命周期 | 1、4 | 可与 3 或 8 并行 | `codex/credentials` | 待执行 |
| 11 | FastAPI REST/SSE 与交付产物 | 5、9、10 | 无 | `codex/api` | 待执行 |
| 12 | React WebUI | 11 的接口契约 | 可在 API schema 冻结后与 11 后半段并行 | `codex/webui` | 待执行 |
| 13 | 端到端测试与三机制演示 | 9、11、12 | 无 | `codex/e2e-demo` | 待执行 |
| 14 | Docker、双 CI、README 与发布检查 | 13 | 无 | `codex/distribution` | 待执行 |

---

### Task 1：工程骨架、依赖锁定与一键质量门禁

**目标：** 建立可安装的 Python 包、React 工作区、统一命令和最小 CI 骨架，为后续 TDD 提供稳定入口。

**文件：**

- 新建：`pyproject.toml`、`requirements.lock`、`Makefile`、`scripts/test.ps1`
- 新建：`src/coding_agent_harness/__init__.py`、`src/coding_agent_harness/config.py`
- 新建：`tests/test_config.py`、`tests/conftest.py`
- 新建：`web/package.json`、`web/package-lock.json`、`web/tsconfig.json`、`web/vite.config.ts`、`web/eslint.config.js`
- 修改：`.env.example`、`.gitignore`

**接口：**

- 产出：`HarnessSettings`；基础阶段可用的 `make test-unit`、`make test` 与 `scripts/test.ps1`。本 Task 的 `test-unit` 只运行现有 pytest；Task 7 定义反馈预算模型，Task 6 定义命令限制上下文；Task 12 在真实前端测试存在后加入 Vitest，`make demo` 在 Task 9 加入，`make test-e2e` 在 Task 13 加入。
- 消费：无。

- [ ] **步骤 1：验证并准备 Python 3.11 测试环境**

依赖安装属于需批准动作。执行以下 `pip install` 前必须取得用户明确批准；冷启动审计禁止联网时，应由宿主预装依赖或提供离线 wheelhouse，不能把安装失败计为 TDD RED。

Windows PowerShell：

```text
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe --version
& .\.venv\Scripts\python.exe -m pip install --upgrade pip==26.1.2 setuptools==83.0.0
& .\.venv\Scripts\python.exe -m pip install pytest==9.1.1
& .\.venv\Scripts\python.exe -c "import pytest; assert pytest.__version__ == '9.1.1'; print(pytest.__version__)"
```

POSIX：

```text
python3.11 -m venv .venv
.venv/bin/python --version
.venv/bin/python -m pip install --upgrade pip==26.1.2 setuptools==83.0.0
.venv/bin/python -m pip install pytest==9.1.1
.venv/bin/python -c "import pytest; assert pytest.__version__ == '9.1.1'; print(pytest.__version__)"
```

预期：解释器输出 `Python 3.11.x`，pytest 输出 `9.1.1`。任一命令失败时暂停并报告环境问题，不得继续写生产实现。

- [ ] **步骤 2：创建失败配置测试**

```python
from coding_agent_harness.config import HarnessSettings


def test_safe_defaults_are_bounded() -> None:
    settings = HarnessSettings()
    assert settings.bind_host == "127.0.0.1"
    assert settings.command_timeout_seconds == 300
    assert settings.max_task_cycles == 8
    assert settings.max_same_fingerprint == 3
    assert settings.no_progress_limit == 2
    assert settings.max_concurrent_tasks == 3
```

- [ ] **步骤 3：确认红色结果**

Windows 运行：`& .\.venv\Scripts\python.exe -m pytest tests/test_config.py -v`

POSIX 运行：`.venv/bin/python -m pytest tests/test_config.py -v`

预期：收集失败，提示 `ModuleNotFoundError: No module named 'coding_agent_harness'`。

- [ ] **步骤 4：写入锁定依赖和最小配置实现**

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HarnessSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HARNESS_", extra="forbid")
    bind_host: str = "127.0.0.1"
    command_timeout_seconds: int = Field(default=300, ge=1)
    max_task_cycles: int = Field(default=8, ge=1)
    max_same_fingerprint: int = Field(default=3, ge=1)
    no_progress_limit: int = Field(default=2, ge=1)
    max_concurrent_tasks: int = Field(default=3, ge=1)
```

`pyproject.toml` 使用“锁定依赖”中的 Python 精确版本，设置 `requires-python = ">=3.11,<3.12"`、`src` 包布局、pytest `asyncio_mode = "auto"`、Ruff 行宽 100 和 mypy strict。构建后端固定为以下内容，不得自行选择版本：

```toml
[build-system]
requires = ["setuptools==83.0.0"]
build-backend = "setuptools.build_meta"
```

`web/package.json` 使用列出的 npm 精确版本，禁止 `^` 与 `~`。

- [ ] **步骤 5：生成并校验锁文件**

运行：

```text
python -m pip install pip-tools==7.5.3
python -m piptools compile --extra dev --generate-hashes --allow-unsafe --output-file requirements.lock pyproject.toml
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
```

Windows PowerShell：

```text
npm.cmd --prefix web install --package-lock-only
npm.cmd --prefix web ci
```

POSIX：

```text
npm --prefix web install --package-lock-only
npm --prefix web ci
```

这些安装命令沿用步骤 1 的同一次用户批准。预期：生成包含哈希和精确传递版本的 `requirements.lock` 与 `web/package-lock.json`，项目以 editable 方式安装，命令退出码均为 0。

- [ ] **步骤 6：实现统一命令并转绿**

`Makefile` 在本 Task 提供 `test-unit`（pytest）和 `test`（Ruff、mypy、pytest、ESLint、TypeScript 配置检查）。后续 Task 只在实际能力存在时加入 Vitest、`demo` 和 `test-e2e`，禁止使用返回成功的空实现或临时跳过。

运行：`python -m pytest tests/test_config.py -v`

预期：`1 passed`。

- [ ] **步骤 7：执行质量检查与双阶段评审**

运行：`ruff check src tests && mypy src && python -m pytest tests/test_config.py -v`

预期：全部退出 0。规约符合性审查确认默认值与 `SPEC.md` 一致；代码质量审查确认锁文件无高层 Agent 框架、`.env.example` 无真实 Key。

- [ ] **步骤 8：提交并回填状态**

```text
git add pyproject.toml requirements.lock Makefile scripts/test.ps1 src tests web .env.example .gitignore PLAN.md AGENT_LOG.md
git commit -m "构建：建立工程骨架与质量门禁（基础子智能体）"
```

---

### Task 2：领域模型、可注入 Provider 与严格动作解析

**目标：** 冻结跨模块类型契约，让 Scripted Mock、DeepSeek/Qwen 适配器和非法动作拒绝都能离线测试。

**文件：**

- 新建：`src/coding_agent_harness/domain/actions.py`、`events.py`、`models.py`
- 新建：`src/coding_agent_harness/providers/base.py`、`mock.py`、`openai_compatible.py`
- 新建：`src/coding_agent_harness/agent/parser.py`
- 新建：`tests/domain/test_actions.py`、`tests/providers/test_contract.py`、`tests/agent/test_parser.py`

**接口：**

- 产出：`TaskState`、`ToolAction`、`CompleteAction`、`LLMRequest`、`LLMResponse`、`LLMProvider`、`ScriptedMockProvider`、`OpenAICompatibleProvider`、`ActionParser.parse(raw: str) -> AgentAction`。
- 消费：Task 1 的 `HarnessSettings`。

- [ ] **步骤 1：先写非法动作和 Mock 序列失败测试**

```python
import pytest
from pydantic import ValidationError
from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.providers.mock import ScriptedMockProvider
from coding_agent_harness.providers.base import LLMRequest


def test_parser_rejects_unknown_tool_and_extra_fields() -> None:
    parser = ActionParser(allowed_tools={"read_file"})
    with pytest.raises(ValidationError):
        parser.parse('{"kind":"tool","tool":"shell","arguments":{},"extra":1}')


async def test_scripted_mock_is_deterministic() -> None:
    provider = ScriptedMockProvider(['{"kind":"complete","summary":"完成"}'])
    response = await provider.complete(LLMRequest(messages=[]))
    assert response.content.endswith('"完成"}')
    assert provider.requests == [LLMRequest(messages=[])]
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/domain tests/providers tests/agent/test_parser.py -v`

预期：导入失败，指出 `domain.actions` 或 `providers.mock` 不存在。

- [ ] **步骤 3：实现严格判别联合与 Provider 协议**

```python
class ToolAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["tool"] = "tool"
    tool: str
    arguments: dict[str, JsonValue]
    idempotency_key: str


class CompleteAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["complete"] = "complete"
    summary: str


AgentAction = Annotated[ToolAction | CompleteAction, Field(discriminator="kind")]
```

`ActionParser` 必须先 `json.loads`，再用 Pydantic `TypeAdapter(AgentAction)` 校验，最后校验 `ToolAction.tool` 位于注入的工具名集合；JSON 中的 shell 字符串不得在解析阶段执行。

- [ ] **步骤 4：实现 OpenAI-compatible 单次调用适配器契约**

```python
class OpenAICompatibleProvider:
    def __init__(self, client: httpx.AsyncClient, base_url: str, model: str, api_key: str):
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "messages": request.messages, "temperature": 0},
        )
        response.raise_for_status()
        return LLMResponse(content=response.json()["choices"][0]["message"]["content"])
```

测试使用 `httpx.MockTransport` 分别断言 DeepSeek/Qwen base URL 配置和请求字段，不连接网络；错误按 `ProviderError(kind, retryable)` 分类。

- [ ] **步骤 5：运行目标测试并重构**

运行：`python -m pytest tests/domain tests/providers tests/agent/test_parser.py -v`

预期：全部通过；Scripted Mock 的脚本耗尽时抛出明确 `ScriptExhaustedError`。

- [ ] **步骤 6：评审与提交**

规约符合性审查重点：无高层 runner、Mock 完全可替换、未知字段拒绝。代码质量审查重点：模型不可变、Provider 不记录 API Key、异常不含请求头。

```text
git add src/coding_agent_harness/domain src/coding_agent_harness/providers src/coding_agent_harness/agent/parser.py tests/domain tests/providers tests/agent/test_parser.py PLAN.md AGENT_LOG.md
git commit -m "功能：建立领域契约和可注入模型接口（核心契约子智能体）"
```

---

### Task 3：SQLite 事件存储、任务仓储与可恢复状态机

**目标：** 以追加事件和乐观序号实现持久化、合法迁移与安全恢复。

**文件：**

- 新建：`src/coding_agent_harness/storage/migrations/001_initial.sql`
- 新建：`src/coding_agent_harness/storage/database.py`、`event_store.py`、`repositories.py`
- 新建：`src/coding_agent_harness/agent/state_machine.py`
- 新建：`tests/storage/test_event_store.py`、`test_recovery.py`、`tests/agent/test_state_machine.py`

**接口：**

- 产出：`Database.open(path)`、`EventStore.append/list_for_task`、`TaskRepository.create/get/update_state`、`StateMachine.transition(current, event_type)`、`recover_task(events)`。
- 消费：Task 2 的 `TaskState`、`TaskEvent`、`Task`。

- [ ] **步骤 1：写事件并发和非法迁移失败测试**

```python
async def test_append_rejects_stale_sequence(event_store, task_event) -> None:
    first = await event_store.append(task_event, expected_sequence=0)
    assert first.sequence == 1
    with pytest.raises(ConcurrencyError):
        await event_store.append(task_event, expected_sequence=0)


def test_state_machine_rejects_execution_before_plan_approval() -> None:
    with pytest.raises(IllegalTransition):
        StateMachine().transition(TaskState.PLANNING, "ACTION_PROPOSED")
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/storage tests/agent/test_state_machine.py -v`

预期：导入失败，存储与状态机模块不存在。

- [ ] **步骤 3：实现事务、迁移和状态映射**

`001_initial.sql` 必须创建 `workspaces`、`tasks`、`task_events`、`plans`、`actions`、`approvals`、`tool_executions`、`verification_runs`、`artifacts`、`memory_records`、`credential_references`；启用外键和 WAL；`task_events(task_id, sequence)` 唯一。

```python
LEGAL_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.CREATED: {TaskState.SCANNING, TaskState.CANCELLED},
    TaskState.SCANNING: {TaskState.PLANNING, TaskState.DECIDING, TaskState.WAITING_USER, TaskState.FAILED},
    TaskState.PLANNING: {TaskState.WAITING_PLAN_APPROVAL, TaskState.WAITING_USER, TaskState.FAILED},
    TaskState.WAITING_PLAN_APPROVAL: {TaskState.PLANNING, TaskState.DECIDING, TaskState.WAITING_USER, TaskState.CANCELLED},
    TaskState.DECIDING: {TaskState.EXECUTING, TaskState.WAITING_ACTION_APPROVAL, TaskState.VERIFYING, TaskState.WAITING_USER, TaskState.FAILED},
    TaskState.WAITING_ACTION_APPROVAL: {TaskState.EXECUTING, TaskState.DECIDING, TaskState.WAITING_USER, TaskState.CANCELLED},
    TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.DECIDING, TaskState.WAITING_USER, TaskState.FAILED},
    TaskState.VERIFYING: {TaskState.CORRECTING, TaskState.WAITING_FINAL_REVIEW, TaskState.WAITING_USER, TaskState.FAILED},
    TaskState.CORRECTING: {TaskState.DECIDING, TaskState.WAITING_USER, TaskState.FAILED},
    TaskState.WAITING_FINAL_REVIEW: {TaskState.COMPLETED, TaskState.CANCELLED},
    TaskState.WAITING_USER: {TaskState.DECIDING, TaskState.CANCELLED, TaskState.FAILED},
}
```

所有运行状态额外允许 `CANCELLED`；`COMPLETED`、`FAILED`、`CANCELLED` 为终态。

- [ ] **步骤 4：实现恢复规则并转绿**

恢复时重放 TaskEvent；最后事件为“工具开始”但没有对应“工具完成/失败”时，状态必须变为 `WAITING_USER`，原因码 `UNCERTAIN_SIDE_EFFECT`，不得重发工具调用。

运行：`python -m pytest tests/storage tests/agent/test_state_machine.py -v`

预期：事件序号、WAL、重放、非法迁移和不确定副作用测试全部通过。

- [ ] **步骤 5：评审与提交**

规约符合性审查重点：事件先落盘、恢复不重复副作用。代码质量审查重点：事务回滚、连接关闭、SQL 参数化、迁移幂等。

```text
git add src/coding_agent_harness/storage src/coding_agent_harness/agent/state_machine.py tests/storage tests/agent/test_state_machine.py PLAN.md AGENT_LOG.md
git commit -m "功能：实现事件存储和可恢复状态机（状态存储子智能体）"
```

---

### Task 4：路径围栏、统一脱敏、策略引擎与版本化审批

**目标：** 用确定性代码拦截六类危险动作，并防止路径逃逸和审批重放。

**文件：**

- 新建：`src/coding_agent_harness/governance/paths.py`、`redaction.py`、`policy.py`、`approvals.py`
- 新建：`tests/governance/test_paths.py`、`test_redaction.py`、`test_policy.py`、`test_approvals.py`

**接口：**

- 产出：`PathGuard.resolve(candidate) -> Path`、`Redactor.sanitize(value)`、`PolicyEngine.evaluate`、`ApprovalManager.request/decide/consume`。
- 消费：Task 2 动作模型、Task 3 审批仓储与事件序号。

- [ ] **步骤 1：写六类危险动作与符号链接逃逸失败测试**

```python
@pytest.mark.parametrize("tool,args", [
    ("delete_path", {"path": "src/a.py"}),
    ("read_file", {"path": "../secret"}),
    ("shell", {"argv": ["pip", "install", "x"]}),
    ("shell", {"argv": ["curl", "https://example.com"]}),
    ("git", {"operation": "push"}),
    ("shell", {"argv": ["rm", "-rf", "/"]}),
])
def test_dangerous_actions_require_approval(policy, tool, args) -> None:
    result = policy.evaluate(make_action(tool, args), trusted_context())
    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/governance -v`

预期：导入失败，`PolicyEngine` 不存在。

- [ ] **步骤 3：实现规范化路径和确定性规则**

`PathGuard` 必须先解析 worktree 根，再解析候选路径与既有父目录的符号链接，最后用 `Path.is_relative_to(root)` 判断；不得仅使用字符串前缀。

```python
class PolicyResult(BaseModel):
    decision: PolicyDecision
    reason_code: str
    normalized_scope: str
    event_sequence: int


class PolicyEngine:
    def evaluate(self, action: ToolAction, context: PolicyContext) -> PolicyResult:
        for rule in self._rules:
            if result := rule(action, context):
                return result
        return PolicyResult(decision=PolicyDecision.ALLOW, reason_code="SAFE", normalized_scope="", event_sequence=context.event_sequence)
```

- [ ] **步骤 4：实现脱敏与一次性审批**

脱敏识别 Bearer、常见 API Key 赋值、私钥头、环境变量名和值；替换为 `[REDACTED]`，审计事件只保存规则名。审批绑定 `action_id + event_sequence + normalized_scope + expires_at`，消费后立即失效；状态或配置版本变化必须拒绝。

- [ ] **步骤 5：转绿并补充回归测试**

运行：`python -m pytest tests/governance -v`

预期：六类危险行为、路径穿越、符号链接逃逸、过期/重放/错版本审批和敏感字符串测试全部通过。

- [ ] **步骤 6：评审与提交**

规约符合性审查重点：真实 Provider 的 LLM API 授权不扩展到工具网络。代码质量审查重点：规则次序无绕过、Windows 大小写路径、异常也先脱敏。

```text
git add src/coding_agent_harness/governance tests/governance PLAN.md AGENT_LOG.md
git commit -m "安全：实现路径围栏和版本化审批（治理子智能体）"
```

---

### Task 5：项目识别、仓库地图与每任务独立 worktree

**目标：** 安全接入本地 Git 项目，识别 Python/Node.js 验证命令，并隔离任务修改。

**文件：**

- 新建：`src/coding_agent_harness/workspace/detector.py`、`scanner.py`、`worktrees.py`
- 新建：`tests/workspace/test_detector.py`、`test_scanner.py`、`test_worktrees.py`
- 新建：`tests/fixtures/python_project/pyproject.toml`、`tests/fixtures/python_project/src/sample.py`、`tests/fixtures/python_project/tests/test_sample.py`
- 新建：`tests/fixtures/node_project/package.json`、`tests/fixtures/node_project/src/math.ts`、`tests/fixtures/node_project/tests/math.test.ts`

**接口：**

- 产出：`ProjectDetector.detect(root) -> ProjectProfile`、`WorkspaceScanner.scan(root) -> RepositoryMap`、`WorktreeManager.create(task_id, base_commit) -> WorktreeInfo`。
- 消费：Task 2 `Workspace`、Task 4 `PathGuard`。

- [ ] **步骤 1：写 Python/Node 识别与文件上限失败测试**

```python
def test_detects_python_and_node_commands(tmp_git_repo) -> None:
    (tmp_git_repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_git_repo / "package.json").write_text('{"scripts":{"test":"vitest run","build":"vite build"}}', encoding="utf-8")
    profile = ProjectDetector().detect(tmp_git_repo)
    assert profile.commands.test == ["python", "-m", "pytest"]
    assert profile.commands.build == ["npm", "run", "build"]


def test_scanner_rejects_more_than_10000_tracked_files(fake_git) -> None:
    fake_git.tracked_files = [f"f{i}" for i in range(10001)]
    with pytest.raises(WorkspaceLimitError):
        WorkspaceScanner(fake_git).scan(Path("repo"))
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/workspace -v`

预期：导入失败，workspace 模块不存在。

- [ ] **步骤 3：实现只读扫描与命令识别**

仅通过参数数组调用 `git -C <root> ls-files -z`、`git log -n 20` 和 `git status --porcelain=v1`；忽略依赖/构建目录；README/AGENTS/配置读取均受大小限制。自定义 `.harness.yml` schema 只允许 `test`、`lint`、`typecheck`、`build` 的 argv 数组、timeout 与 env allowlist，首次执行进入信任审批。

- [ ] **步骤 4：实现 worktree 隔离**

分支名固定为 `harness/task-<uuid前8位>`；worktree 放在 Harness 状态目录而不是项目目录内；创建前拒绝非 Git、基准提交不存在和同 Workspace 已有写任务。不得清理或覆盖主工作区脏改动。

- [ ] **步骤 5：转绿、性能与双平台边界检查**

运行：`python -m pytest tests/workspace -v`

预期：识别、限制、脏主工作区保护、worktree 创建/释放和 Windows 空格路径测试通过；10,000 文件合成扫描基准低于 5 秒（CI 慢机只记录，不作硬失败；本机验收硬目标 5 秒）。

- [ ] **步骤 6：评审与提交**

规约符合性审查确认 Python/Node 默认识别、自定义命令信任、10,000 文件边界和主工作区保护；代码质量审查确认 Git 参数数组、临时目录清理与跨平台路径测试。

```text
git add src/coding_agent_harness/workspace tests/workspace tests/fixtures PLAN.md AGENT_LOG.md
git commit -m "功能：实现项目识别和任务工作树（工作区子智能体）"
```

---

### Task 6：工具注册表、原子文件工具、受限 Shell 与 Git 工具

**目标：** 在统一分发、策略和标准结果下提供编码所需工具。

**文件：**

- 新建：`src/coding_agent_harness/tools/base.py`、`registry.py`、`files.py`、`patch.py`、`shell.py`、`git.py`
- 新建：`tests/tools/test_registry.py`、`test_files.py`、`test_patch.py`、`test_shell.py`、`test_git.py`

**接口：**

- 产出：`ToolContext`、`ToolResult`、`ToolRegistry.dispatch(action, context)` 和工具 `read_file`、`search`、`apply_patch`、`shell`、`git_status`、`git_diff`、`checkpoint`。
- 消费：Task 4 `PolicyEngine/PathGuard/Redactor`，Task 5 worktree。

- [ ] **步骤 1：写策略先于执行和原子 patch 冲突测试**

```python
async def test_registry_never_runs_tool_before_approval(registry, dangerous_action, context) -> None:
    result = await registry.dispatch(dangerous_action, context)
    assert result.status == "approval_required"
    assert context.runner.calls == []


async def test_patch_rejects_stale_digest(patch_tool, context) -> None:
    result = await patch_tool.run(make_patch(expected_sha256="wrong"), context)
    assert result.error_code == "STALE_FILE"
    assert context.path("a.py").read_text() == "old\n"
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/tools -v`

预期：导入失败，工具注册表不存在。

- [ ] **步骤 3：实现标准结果和只读工具**

```python
class ToolResult(BaseModel):
    status: Literal["ok", "error", "approval_required", "cancelled"]
    summary: str
    duration_ms: int
    error_code: str | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)
    truncated: bool = False
```

文件读取默认最大 1 MiB、搜索最多 200 条、输出默认最大 64 KiB；所有结果经 Redactor 后才写事件。

- [ ] **步骤 4：实现原子 patch、Shell 和 Git**

patch 在同目录临时文件写入、fsync、校验新内容后原子替换；使用预期 SHA-256 防止覆盖并发改动。Shell 仅接受 argv 数组，不接受拼接字符串；固定 cwd 为 worktree，清除代理/凭据环境变量，使用进程组超时和取消。Git 工具只使用参数数组；push/merge 永远走审批。

- [ ] **步骤 5：转绿并覆盖错误分类**

运行：`python -m pytest tests/tools -v`

预期：路径越界、过时 patch、命令失败、超时、取消、截断、环境清理、Git diff/checkpoint 测试全部通过。

- [ ] **步骤 6：评审与提交**

规约符合性审查确认全部工具受策略、路径和验证约束；代码质量审查确认子进程释放、输出上限、原子替换和错误码一致。

```text
git add src/coding_agent_harness/tools tests/tools PLAN.md AGENT_LOG.md
git commit -m "功能：实现受治理的编码工具集（工具子智能体）"
```

---

### Task 7：验证选择、失败分类、稳定指纹与进展预算

**目标：** 实现项目主要贡献——可确定性验证和有界自我修正反馈闭环。

**文件：**

- 新建：`src/coding_agent_harness/feedback/models.py`、`classifier.py`、`fingerprint.py`、`progress.py`、`engine.py`
- 新建：`tests/feedback/test_classifier.py`、`test_fingerprint.py`、`test_progress.py`、`test_engine.py`

**接口：**

- 产出：`FailureCategory`、`VerificationRun`、`FeedbackDecision`、`FailureClassifier.classify`、`fingerprint_failures`、`ProgressTracker.observe`、`FeedbackEngine.evaluate`。
- 消费：Task 2 `Task`，Task 6 `ToolResult` 和验证命令执行能力。

- [ ] **步骤 1：写稳定指纹和 3/8/2 预算失败测试**

```python
def test_fingerprint_ignores_paths_and_timing_noise() -> None:
    a = "FAILED C:/tmp/a/test_x.py::test_one - AssertionError in 0.12s"
    b = "FAILED /tmp/b/test_x.py::test_one - AssertionError in 0.98s"
    assert fingerprint_failures(a) == fingerprint_failures(b)


def test_two_no_progress_rounds_wait_for_user(engine, task) -> None:
    first = engine.evaluate(task, run(failures=2, category="test", fingerprint="same"))
    second = engine.evaluate(first.task, run(failures=2, category="test", fingerprint="same"))
    assert second.next_state is TaskState.WAITING_USER
    assert second.reason_code == "NO_PROGRESS"
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/feedback -v`

预期：导入失败，feedback 模块不存在。

- [ ] **步骤 3：实现分类和标准化指纹**

分类至少区分 `TEST_FAILURE`、`LINT_FAILURE`、`TYPE_FAILURE`、`BUILD_FAILURE`、`COMMAND_MISSING`、`CONFIGURATION_ERROR`、`TIMEOUT`、`CANCELLED`、`TOOL_ERROR`。指纹只使用类别、测试节点/诊断码、规范化消息；移除绝对路径、行号、耗时、随机临时目录和 ANSI 颜色，但不能移除断言核心文本。

- [ ] **步骤 4：实现快速/完整验证与预算决策**

修改后选择受影响快速检查；完成候选强制运行 test、lint、typecheck、build 中所有已配置命令。无配置时返回 `NO_VERIFICATION_CONFIG` 并进入 `WAITING_USER`。同指纹第 3 次失败、总循环第 8 次或连续第 2 次无进展时停止自动修正。

```python
class FeedbackDecision(BaseModel):
    next_state: TaskState
    reason_code: str
    feedback_for_llm: str
    task: Task
    progress: Literal["improved", "changed", "stalled", "passed"]
```

- [ ] **步骤 5：转绿并检查确定性**

连续运行两次：`python -m pytest tests/feedback -v`

预期：两次均全部通过，序列化指纹与状态决策一致。

- [ ] **步骤 6：评审与提交**

规约符合性审查重点：反馈是代码机制、完整验收不可跳过、测试输出不作为指令。代码质量审查重点：规则无时间/路径噪声、预算 off-by-one 正确。

```text
git add src/coding_agent_harness/feedback tests/feedback PLAN.md AGENT_LOG.md
git commit -m "功能：实现确定性反馈闭环（反馈子智能体）"
```

---

### Task 8：记忆白名单、敏感拒绝与预算化上下文

**目标：** 只持久化允许的长期知识，并按任务相关性选择上下文。

**文件：**

- 新建：`src/coding_agent_harness/memory/filter.py`、`store.py`、`context.py`
- 新建：`tests/memory/test_filter.py`、`test_store.py`、`test_context.py`

**接口：**

- 产出：`MemoryFilter.validate(record)`、`MemoryStore.add/search/delete`、`ContextBuilder.build(task, budget_chars)`。
- 消费：Task 3 SQLite、Task 4 Redactor、Task 5 RepositoryMap。

- [ ] **步骤 1：写白名单与秘密拒绝失败测试**

```python
@pytest.mark.parametrize("kind", ["project_convention", "architecture_decision", "tool_note", "completed_task", "failure_lesson", "user_requirement"])
def test_allowed_memory_types_are_stored(memory_store, kind) -> None:
    memory_store.add(record(kind=kind, content="使用 pytest"))
    assert memory_store.search("pytest")[0].kind == kind


def test_secret_is_rejected_without_echo(memory_store) -> None:
    with pytest.raises(SensitiveMemoryError) as exc:
        memory_store.add(record(kind="tool_note", content="HARNESS_LLM_API_KEY=test-only-credential"))
    assert "test-only-credential" not in str(exc.value)
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/memory -v`

预期：导入失败，memory 模块不存在。

- [ ] **步骤 3：实现白名单、脱敏和检索**

MemoryRecord 必须带来源事件、Workspace、标签、置信度、更新时间；不复制源码全文。检索首版使用 SQLite FTS5 或确定性 token overlap + recency 排序，不引入向量服务。敏感命中拒绝整条写入并只记录规则编号。

- [ ] **步骤 4：实现上下文预算**

上下文顺序固定为：系统工具 schema → 当前需求/批准计划 → 最近结构化反馈 → 相关仓库地图/搜索片段 → 允许记忆；超过预算时从最低相关记忆开始丢弃，不截断 JSON schema 或当前失败。

- [ ] **步骤 5：转绿、评审与提交**

运行：`python -m pytest tests/memory -v`

预期：允许类型、禁止隐私/Key、相关性、来源、删除和预算测试通过。

规约符合性审查确认六类允许记忆和全部禁止内容；代码质量审查确认检索排序确定、来源可追溯和异常不回显秘密。

```text
git add src/coding_agent_harness/memory tests/memory PLAN.md AGENT_LOG.md
git commit -m "功能：实现安全记忆和上下文选择（记忆子智能体）"
```

---

### Task 9：计划门禁、Agent 主循环、停止逻辑与离线机制演示

**目标：** 组装仓库自有的完整 Agent 循环，并用 Scripted Mock 确定性证明治理、反馈改变动作和无进展升级。

**文件：**

- 新建：`src/coding_agent_harness/agent/orchestrator.py`
- 新建：`src/coding_agent_harness/demo.py`
- 新建：`scripts/mechanism_demo.py`
- 新建：`tests/agent/test_orchestrator.py`、`test_plan_gate.py`、`test_recovery_loop.py`
- 新建：`tests/demo/test_mechanism_demo.py`

**接口：**

- 产出：`TaskOrchestrator.step/resume`、`run_mechanism_demo() -> DemoReport`。
- 消费：Tasks 2—8 的 Provider、解析、事件、治理、工具、反馈、记忆与状态机。

- [ ] **步骤 1：写默认计划门禁失败测试**

```python
async def test_default_task_does_not_modify_before_plan_approval(harness) -> None:
    task = await harness.create_task("修改问候语", skip_plan=False)
    await harness.orchestrator.step(task.id)
    assert await harness.state(task.id) is TaskState.WAITING_PLAN_APPROVAL
    assert harness.tools.write_calls == []


async def test_explicit_skip_plan_still_uses_policy_and_verification(harness) -> None:
    task = await harness.create_task("直接修改", skip_plan=True)
    await harness.orchestrator.step(task.id)
    assert harness.policy.calls
    assert harness.verifier.calls
```

- [ ] **步骤 2：写反馈改变下一动作失败测试**

```python
async def test_failure_feedback_changes_next_mock_action(scripted_harness) -> None:
    result = await scripted_harness.run_to_pause_or_finish()
    assert result.provider.requests[1].messages[-1]["name"] == "verification_feedback"
    assert result.actions[0].arguments["replacement"] == "broken"
    assert result.actions[1].arguments["replacement"] == "fixed"
    assert result.state is TaskState.WAITING_FINAL_REVIEW
```

- [ ] **步骤 3：确认红色结果**

运行：`python -m pytest tests/agent tests/demo -v`

预期：`TaskOrchestrator` 或 `run_mechanism_demo` 导入失败。

- [ ] **步骤 4：实现单步可恢复循环**

`step()` 每次最多完成一个外部副作用，并按以下固定顺序：读取已落盘状态 → 构建上下文 → Provider 调用 → 解析动作 → 策略判定 → 写“开始”事件 → 工具执行 → 写“结果”事件 → 必要验证 → FeedbackDecision → 状态迁移。Provider 失败只在“无副作用且 retryable”时最多重试 2 次。

- [ ] **步骤 5：实现三个确定性演示场景**

`DemoReport` 必须包含：

1. `governance_blocked=True`，危险删除进入 `WAITING_ACTION_APPROVAL` 且 runner 零调用。
2. `feedback_changed_action=True`，第一轮验证失败被写入第二次 LLMRequest，第二动作不同并通过。
3. `no_progress_escalated=True`，稳定指纹连续两轮无进展后进入 `WAITING_USER`。

脚本退出码：三项都成立为 0，否则为 1；输出仅打印固定摘要和事件 ID，不打印源码/秘密。

- [ ] **步骤 6：转绿与完整核心回归**

运行：

```text
python -m pytest tests/agent tests/demo -v
python scripts/mechanism_demo.py
```

预期：测试全部通过；脚本输出三项 `PASS`，退出 0；执行两次输出的状态序列一致。

- [ ] **步骤 7：评审与提交**

规约符合性审查重点：主循环完全自有、LLM 不可绕过治理/验证、停止预算生效。代码质量审查重点：一步一副作用、幂等键、取消和异常边界。

```text
git add src/coding_agent_harness/agent/orchestrator.py src/coding_agent_harness/demo.py scripts/mechanism_demo.py tests/agent tests/demo Makefile PLAN.md AGENT_LOG.md
git commit -m "功能：完成智能体循环和机制演示（编排子智能体）"
```

---

### Task 10：本机钥匙串与容器认证加密凭据生命周期

**目标：** 实现录入、状态、更新和清除，不在任何返回、日志、事件或记忆中暴露明文。

**文件：**

- 新建：`src/coding_agent_harness/credentials/base.py`、`keyring_store.py`、`encrypted_store.py`、`service.py`
- 新建：`tests/credentials/test_keyring_store.py`、`test_encrypted_store.py`、`test_service.py`

**接口：**

- 产出：`CredentialStore.set/get/delete`、`CredentialService.configure/status/clear`、`CredentialStatus(provider, configured, updated_at)`。
- 消费：Task 1 设置、Task 4 Redactor。

- [ ] **步骤 1：写不回显与密文篡改失败测试**

```python
def test_status_never_contains_secret(service) -> None:
    service.configure("deepseek", "test-only-credential")
    status = service.status("deepseek")
    assert status.configured is True
    assert "test-only-credential" not in status.model_dump_json()


def test_encrypted_store_rejects_tampering(store_file, master_password) -> None:
    store = EncryptedCredentialStore(store_file, master_password)
    store.set("qwen", "secret")
    corrupt_last_byte(store_file)
    with pytest.raises(CredentialIntegrityError):
        store.get("qwen")
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/credentials -v`

预期：导入失败，credentials 模块不存在。

- [ ] **步骤 3：实现两个 Store**

Keyring service 名固定为 `coding-agent-harness`，用户名为 provider。容器文件使用 Argon2id 生成 32 字节密钥、随机 16 字节 salt、AES-256-GCM 随机 12 字节 nonce和版本化 envelope；写入权限限制为当前用户，更新使用原子替换。错误消息不得包含 Key。

- [ ] **步骤 4：实现服务与 `.env` 开发备用警告**

状态只返回 provider、configured、updated_at、backend。公网 demo 配置必须拒绝 configure；`.env` 后端默认禁用，启用时启动日志固定输出明文风险警告但不输出值。

- [ ] **步骤 5：转绿、评审与提交**

运行：`python -m pytest tests/credentials -v`

预期：录入、覆盖、状态、清除、错误主密码、篡改、权限、公网拒绝和日志无明文测试通过。

规约符合性审查确认本机钥匙串、容器认证加密与公网禁用；代码质量审查确认随机数来源、原子写入、文件权限和所有错误路径的脱敏。

```text
git add src/coding_agent_harness/credentials tests/credentials PLAN.md AGENT_LOG.md
git commit -m "安全：实现凭据完整生命周期（凭据子智能体）"
```

---

### Task 11：FastAPI REST、SSE、会话防护与审查产物

**目标：** 为本地 WebUI 提供同源内部接口、可续传事件和最终审查包。

**文件：**

- 新建：`src/coding_agent_harness/artifacts/builder.py`
- 新建：`src/coding_agent_harness/api/app.py`、`dependencies.py`
- 新建：`src/coding_agent_harness/api/routes/workspaces.py`、`tasks.py`、`approvals.py`、`settings.py`、`events.py`
- 新建：`tests/api/test_workspaces.py`、`test_tasks.py`、`test_approvals.py`、`test_events.py`、`test_security.py`
- 新建：`tests/artifacts/test_builder.py`

**接口：**

- 产出：`create_app(container) -> FastAPI`；`POST /api/workspaces`、`POST /api/tasks`、`POST /api/tasks/{id}/plan-decision`、`POST /api/approvals/{id}/decision`、`POST /api/tasks/{id}/{pause|resume|cancel|finalize}`、`GET /api/tasks/{id}`、`GET /api/tasks/{id}/events`、`GET/PUT/DELETE /api/settings/credentials/{provider}`、`GET /health`。
- 消费：Tasks 5、9、10 服务接口。

- [ ] **步骤 1：写未授权、过期审批和 SSE 续传失败测试**

```python
def test_mutation_requires_session_token(client) -> None:
    response = client.post("/api/tasks", json={"workspace_id":"x", "request":"改代码"})
    assert response.status_code == 401


def test_sse_resumes_after_last_event_id(client, seeded_task, token) -> None:
    response = client.get(
        f"/api/tasks/{seeded_task}/events",
        headers={"Last-Event-ID":"2", "X-Harness-Session":token},
    )
    assert "id: 3" in response.text
    assert "id: 2" not in response.text
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/api tests/artifacts -v`

预期：导入失败，API app 不存在。

- [ ] **步骤 3：实现命令路由与安全中间件**

启动生成随机会话令牌，只通过启动终端和首屏注入提供；所有 mutation 校验同源 Origin 与 `X-Harness-Session`。服务默认绑定 `127.0.0.1`；公网 demo 使用独立只读/受限配置。错误响应为 `{code, message, details, event_id}` 且先脱敏。

- [ ] **步骤 4：实现 SSE 与 ArtifactBuilder**

SSE 每条事件含递增 `id`、`event: task-event`、脱敏 JSON data；支持 `Last-Event-ID` 补发和 15 秒心跳。ArtifactBuilder 仅从实际 diff、VerificationRun 和事件生成 summary、diff、checks、docs，关联 event sequence；diff 变化后旧包失效。

- [ ] **步骤 5：转绿与接口契约导出**

运行：`python -m pytest tests/api tests/artifacts -v`

预期：REST、会话令牌、Origin、审批版本、SSE 续传/断线和文档不虚构测试通过。保存 OpenAPI 快照到 `web/src/api/openapi.json`，作为 Task 12 类型实现依据。

- [ ] **步骤 6：评审与提交**

规约符合性审查确认内部接口仅服务 WebUI、同源会话保护和事件补发；代码质量审查确认依赖注入边界、连接取消、事件去重和响应 schema 稳定。

```text
git add src/coding_agent_harness/artifacts src/coding_agent_harness/api tests/api tests/artifacts web/src/api/openapi.json PLAN.md AGENT_LOG.md
git commit -m "功能：提供本地接口和事件流（接口子智能体）"
```

---

### Task 12：React 编码工作台 WebUI

**目标：** 按 Open Design `dashboard` 与 `Neutral Modern` 方向实现桌面优先、可键盘操作的项目与任务工作台。

**文件：**

- 新建：`web/index.html`
- 新建：`web/src/api/client.ts`、`events.ts`、`types.ts`
- 新建：`web/src/components/AppShell.tsx`、`StatusBadge.tsx`、`EventTimeline.tsx`、`DiffPanel.tsx`、`ApprovalCard.tsx`
- 新建：`web/src/pages/ProjectsPage.tsx`、`NewTaskPage.tsx`、`TaskPage.tsx`、`ApprovalsPage.tsx`、`SettingsPage.tsx`、`DemoPage.tsx`
- 新建：`web/src/App.tsx`、`main.tsx`、`styles.css`
- 新建：对应 `web/src/**/*.test.tsx`

**接口：**

- 产出：项目页、新任务页、任务工作台、审批中心、历史/设置/演示页面；`HarnessApi` 与 `TaskEventStream`。
- 消费：Task 11 OpenAPI/REST/SSE 契约。

- [ ] **步骤 1：写计划门禁和审批卡失败组件测试**

```tsx
it("计划未批准时禁用执行并展示批准按钮", async () => {
  render(<TaskPage api={fakeApi({state: "WAITING_PLAN_APPROVAL"})} taskId="t1" />);
  expect(await screen.findByRole("button", {name: "批准计划"})).toBeEnabled();
  expect(screen.getByRole("button", {name: "执行下一步"})).toBeDisabled();
});

it("危险动作展示原因和精确影响范围", () => {
  render(<ApprovalCard approval={dangerousApproval} onDecision={vi.fn()} />);
  expect(screen.getByText("删除文件")).toBeVisible();
  expect(screen.getByText("src/obsolete.py")).toBeVisible();
});
```

- [ ] **步骤 2：确认红色结果**

Windows 运行：`npm.cmd --prefix web run test -- --run`

POSIX 运行：`npm --prefix web run test -- --run`

预期：组件模块不存在，测试因 `TaskPage` 不存在而失败。

- [ ] **步骤 3：实现 API 客户端、SSE 重连和应用骨架**

`HarnessApi` 为每次 mutation 添加 session header；`TaskEventStream` 保存最后 event ID、指数退避重连并去重。AppShell 提供项目、任务、审批、设置和演示导航，焦点可见，状态同时使用文本/图标而非仅颜色。

- [ ] **步骤 4：实现任务工作台和危险审批**

工作台固定区域：目标/计划、当前状态与预算、事件时间线、工具/验证详情、diff、最终产物。审批卡展示类别、原因、规范化范围、命令 argv、过期时间和批准/拒绝按钮；服务返回 409 时刷新而不重复批准。

- [ ] **步骤 5：实现设置、Demo 和响应式只读视图**

凭据输入使用 password，保存后立即清空 DOM value，只显示 configured/updated_at；Demo 页展示三机制固定场景。窄屏保证查看，不承诺完整 diff 编辑。

- [ ] **步骤 6：转绿并执行可访问性检查**

运行：

```text
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web run test -- --run
npm --prefix web run build
```

Windows PowerShell 将上述四条命令中的 `npm` 全部替换为 `npm.cmd`；POSIX 保持 `npm`。

预期：全部退出 0；页面测试覆盖键盘导航、断线补发、过期审批、凭据清空和非颜色状态表达。

- [ ] **步骤 7：评审与提交**

规约符合性审查重点：WebUI 是首版唯一用户入口、公网 demo 不接受真实 Key。代码质量审查重点：类型与 OpenAPI 一致、无 dangerouslySetInnerHTML 渲染仓库内容、SSE 清理。

```text
git add web PLAN.md AGENT_LOG.md
git commit -m "功能：实现编码智能体网页工作台（界面子智能体）"
```

---

### Task 13：端到端 fixture、机制演示和一键测试闭环

**目标：** 在完全离线 Mock 模式下，从 WebUI/API 驱动真实临时 Git 项目，并证明三项必需机制。

**文件：**

- 新建：`e2e/fixtures/python_project/pyproject.toml`、`e2e/fixtures/python_project/src/calculator.py`、`e2e/fixtures/python_project/tests/test_calculator.py`
- 新建：`e2e/fixtures/node_project/package.json`、`e2e/fixtures/node_project/src/math.ts`、`e2e/fixtures/node_project/tests/math.test.ts`
- 新建：`e2e/task-flow.spec.ts`、`e2e/governance.spec.ts`、`e2e/feedback.spec.ts`
- 新建：`e2e/playwright.config.ts`
- 新建：`examples/mock-project/README.md`、`examples/mock-project/src/calculator.py`、`examples/mock-project/tests/test_calculator.py`
- 修改：`Makefile`、`scripts/test.ps1`、`scripts/mechanism_demo.py`

**接口：**

- 产出：无跳过的 `make test`、`make test-unit`、`make test-e2e`、`make demo`。
- 消费：Tasks 9、11、12 的完整系统。

- [ ] **步骤 1：写 E2E 失败场景**

```ts
test("失败反馈使 Mock 改变下一动作并交付通过证据", async ({page}) => {
  await createMockTask(page, "修复 add 函数");
  await approvePlan(page);
  await expect(page.getByText("TEST_FAILURE")).toBeVisible();
  await expect(page.getByText("反馈已回灌，下一动作已改变")).toBeVisible();
  await expect(page.getByText("WAITING_FINAL_REVIEW")).toBeVisible();
  await expect(page.getByText("pytest: PASS")).toBeVisible();
});
```

- [ ] **步骤 2：确认红色结果**

运行：`make test-e2e`

预期：失败，因为 `test-e2e` 目标或 Playwright 服务尚未实现。

- [ ] **步骤 3：建立可重建 fixture 和测试服务**

每个 E2E 测试复制 fixture 到临时目录、`git init`、设置测试身份、创建基准提交；测试后删除临时 worktree。服务使用 Scripted Mock、临时 SQLite、随机端口，不访问网络；浏览器只连接 localhost。

- [ ] **步骤 4：接入完整测试链并实现四个一键命令**

`make test-unit` 必须运行后端单测和 Vitest；`make test-e2e` 运行 Playwright；`make test` 运行 lint/type/build/unit/e2e；`make demo` 运行 CLI 三机制演示。PowerShell 脚本提供等价 `-Mode Unit|E2E|All|Demo`。

- [ ] **步骤 5：转绿并重复验证确定性**

运行：

```text
make test-unit
make demo
make demo
make test-e2e
make test
```

预期：全部退出 0；两次 demo 的状态序列和三项 PASS 一致；核心测试无网络请求和 API Key。

- [ ] **步骤 6：评审与提交**

规约符合性审查逐项观看危险拦截、失败回灌改变动作、无进展升级三场景；代码质量审查确认 fixture 隔离、进程/浏览器清理、重复执行确定性和无网络依赖。

```text
git add e2e examples scripts Makefile PLAN.md AGENT_LOG.md
git commit -m "测试：完成离线端到端验证和三机制演示（测试子智能体）"
```

---

### Task 14：Docker/OCI、双 CI、README 与交付审计

**目标：** 提供新机器可运行的容器、本地源码流程、每次 push 自动测试/构建和课程要求的最终文档。

**文件：**

- 新建：`Dockerfile`、`.dockerignore`、`compose.yaml`、`render.yaml`
- 新建：`.github/workflows/ci.yml`、`.github/workflows/release.yml`、`.gitlab-ci.yml`
- 新建：`docs/SECURITY.md`、`docs/DEPLOYMENT.md`、`docs/DEMO.md`
- 新建：`REFLECTION.md`（仅建立用户填写框架，不代写用户个人反思）
- 修改：`README.md`、`.env.example`、`PLAN.md`、`AGENT_LOG.md`
- 新建：`tests/distribution/test_delivery_files.py`

**接口：**

- 产出：`docker build`、`docker run`、GHCR 多架构发布、Render Mock 部署、GitHub Actions、GitLab `unit-test`。
- 消费：完整应用与一键测试。

- [ ] **步骤 1：写交付文件失败测试**

```python
def test_required_delivery_contract(repo_root: Path) -> None:
    workflow = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    gitlab = (repo_root / ".gitlab-ci.yml").read_text(encoding="utf-8")
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    assert "make test" in workflow and "docker build" in workflow
    assert "unit-test:" in gitlab
    for heading in ["项目简介", "安装", "运行", "分发", "目录结构", "安全边界", "凭据配置", "已知限制"]:
        assert f"## {heading}" in readme
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/distribution/test_delivery_files.py -v`

预期：失败，指出 CI/Docker/README 必需内容缺失。

- [ ] **步骤 3：实现 Docker 与本地运行文档**

Docker 多阶段构建前端和 Python 运行层，最终非 root 用户运行；只暴露应用端口，项目与状态必须显式挂载。`docker run` 文档展示 localhost 模式、状态卷、单项目挂载和容器主密码的安全输入方式，不把密码写入镜像/命令历史。公网镜像固定 Mock 模式并禁用凭据、任意路径和外部网络工具。

- [ ] **步骤 4：实现 GitHub/GitLab CI**

GitHub `ci.yml` 每次 push/PR 执行 `make test`、秘密扫描和 `docker build`；release workflow 在 tag 上使用 Buildx 发布 `linux/amd64,linux/arm64` 到 GHCR。`.gitlab-ci.yml` 必须存在精确 job 名 `unit-test` 并执行离线 `make test-unit`。CI 不注入真实 LLM Key。

- [ ] **步骤 5：完成 README 和部署资料**

README 必含课程指定章节、DeepSeek/Qwen Key 的本机钥匙串/容器加密流程、Mock 使用、四个 make 命令、Docker 架构、Render 冷启动/临时文件限制、WebUI URL（部署完成后填写真实 URL，不得占位）。`REFLECTION.md` 只提供问题标题并明确由用户以 1500—2500 字亲自完成。

- [ ] **步骤 6：转绿并执行全量新鲜验证**

运行：

```text
python -m pytest tests/distribution/test_delivery_files.py -v
make test
make demo
docker build -t coding-agent-harness:test .
docker run --rm coding-agent-harness:test python scripts/mechanism_demo.py
```

预期：测试、Lint、类型检查、前端构建、E2E、三机制演示和容器冷启动均退出 0。

- [ ] **步骤 7：秘密与历史审计**

运行：

```text
git grep -n -I -E '(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY)'
git log -p --all -- . ':!*.lock' | rg -n '(sk-[A-Za-z0-9_-]{16,}|PRIVATE KEY)'
```

预期：两项均无匹配；若命中，立即停止、轮换、清理历史并按 `AGENTS.md` 记录事故。

- [ ] **步骤 8：最终两阶段评审、提交与分支收尾**

先执行规约符合性审查，逐条对照 `SPEC.md` 13 节验收标准；再执行代码质量审查与供应链审计。Critical 问题清零且上述证据仍为最新后，才调用 `finishing-a-development-branch`。

```text
git add Dockerfile .dockerignore compose.yaml render.yaml .github .gitlab-ci.yml docs README.md .env.example REFLECTION.md tests/distribution PLAN.md AGENT_LOG.md
git commit -m "交付：完成容器、持续集成和项目文档（交付子智能体）"
```

## `SPEC.md` 验收覆盖矩阵

| `SPEC.md` 验收项 | 主要 Task | 直接证据 |
|---|---|---|
| 1. 添加 Git 项目、识别并拒绝无效/越界路径 | 4、5、11、12 | 路径围栏单测、Workspace API 与项目页测试 |
| 2. 默认计划审批；显式跳过才直接执行 | 3、9、12 | `test_plan_gate.py` 与 WebUI 计划按钮测试 |
| 3. 每任务独立 worktree，主分支不提前变化 | 5、13 | worktree 集成测试与临时 Git E2E |
| 4. DeepSeek/Qwen 共用接口，Mock 可替换 | 2、9 | Provider 契约测试与 Scripted Mock 主循环测试 |
| 5. 六类危险动作和过期审批拦截 | 4、6、13 | 参数化策略测试与治理 E2E |
| 6. Python/Node 快速和完整验证、自定义命令 | 5、7、13 | 两类 fixture、选择器和 E2E |
| 7. 失败分类、指纹、3/8/2 预算 | 7、9、13 | Feedback 单测、主循环和机制演示 |
| 8. 服务重启恢复；不确定副作用不重放 | 3、9 | 事件重放和恢复循环测试 |
| 9. 凭据录入、状态、更新、清除且无明文 | 4、10、11、12 | 凭据单测、API/UI 测试和秘密扫描 |
| 10. 一键测试、演示和 Docker 冷启动 | 13、14 | `make test`、`make demo`、容器演示命令 |
| 11. GitHub Actions 与 GitLab `unit-test` | 14 | 交付契约测试和真实 CI 结果 |
| 12. 公网 Mock WebUI 展示三项机制 | 12—14 | Demo 页 E2E 与部署后的真实 URL 检查 |

## 实施期间的状态维护规则

1. 每个 Task 开始时把表格状态改为“进行中（worktree/智能体）”。
2. 每个 Task 通过两阶段评审后改为“完成（提交哈希）”；失败或返工如实记录。
3. 每次子智能体产出、人工修改、评审结论与经验都追加到 `AGENT_LOG.md`。
4. 并行 worktree 只处理表格明确允许并行的 Task；共享接口变更必须先合并契约 Task。
5. 不得把最终部署 URL、镜像 digest 或 CI 通过状态预先写成成功；只能依据真实外部结果回填。

## 计划完成后的强制门禁

本计划完成并提交后，正式实现仍不得开始。必须先启动一个不包含当前对话或记忆的不同类型智能体，初始上下文仅提供 `SPEC.md` 和 `PLAN.md`，要求它选择 1—2 个 Task 尝试冷启动，并在任何不确定处立即暂停而不是猜测。选定 Task 后，审计员可以读取该 Task “文件”清单中明确列出的目标文件，以便安全修改既有内容；不得读取其他过程文档、Git 历史或主对话。主智能体必须把暂停点、误读、产出差距和修订 diff 写入 `SPEC_PROCESS.md`；修订完成并再次获得用户确认后，方可选择 `subagent-driven-development` 或 `executing-plans` 开始实现。
