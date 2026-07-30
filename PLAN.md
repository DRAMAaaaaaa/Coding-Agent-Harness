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
- 删除、宿主受控导入/导出、安装依赖、工具网络请求、Git push/merge、发布和高风险 Shell 必须进入版本化审批；普通 Agent 工具路径逃逸固定 `DENY/PATH_ESCAPE`，审批不能提升其路径能力。
- 同一失败指纹最多修正 3 轮；单任务最多 8 个验证—修正循环；连续 2 轮失败数未减少且类别未变化时进入 `WAITING_USER`；命令默认超时 300 秒。
- Mock LLM 核心测试不得访问网络或真实 LLM；测试和日志不得包含真实凭据。
- 一个 Workspace 同时最多一个写任务，全局默认最多 3 个并发任务；正式支持最多 10,000 个 Git 跟踪文件。
- Harness `state_root` 是宿主私有边界，不进入 LLM 或普通 Agent 工具能力；首版信任同一 OS 账户不主动篡改该目录。路径身份或 Git 注册后验不一致时不主动删除仍存在的 target/branch 等现场、不回滚 Git 已完成的副作用，并保留活动标记人工接管；禁止递归清理不确定路径。同 UID 主动篡改的独立 OS 身份/ACL/broker 加固登记为 `DW-05-001`。
- 文档和 Git 提交说明尽量使用中文；代码标识符、命令、标准文件名和第三方名称保留英文。
- 每个 Task 使用独立 `codex/` 前缀分支和 worktree；完成后在本文件勾选状态并记录提交哈希与评审结论。
- 每个 Task 固定执行顺序：失败测试 → 确认失败原因 → 最小实现 → 通过目标测试 → 重构 → 完整相关测试 → 规约符合性审查 → 代码质量审查 → 中文提交。
- 后续实现采用“可验收纵向切片”优先级：在不改变依赖和冻结接口的前提下，先连通 WebUI 输入需求、计划审批、Agent 修改、确定性反馈、最终审查和代码/文档交付，再补不阻塞首版的增强能力。
- 课程硬性要求、安全护栏、离线 Mock 核心测试、三机制演示、反馈闭环、停止逻辑、WebUI 主路径、E2E、一键测试、Docker 和双 CI 不得延期。
- 非阻塞增强只有在不影响安全、主路径或验收且存在明确替代时才可延期；决定必须写入 `DEFERRED_WORK.md`，并同步披露于当前 Task 的 `PLAN.md` 状态、`AGENT_LOG.md` 和提交说明。
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
requirements/
  windows-py311.lock                # Windows 本地开发传递依赖与哈希
  linux-py311.lock                  # Linux 容器/CI 传递依赖与哈希（Task 14）
src/coding_agent_harness/
  config.py                         # 全局与项目配置、预算、限制
  domain/{actions,events,models}.py # 共享枚举与不可变协议模型
  providers/{base,mock,openai_compatible}.py
  storage/{database,event_store,repositories}.py
  storage/migrations/{001_initial,002_governance_approvals,003_host_transfers}.sql
  governance/{paths,redaction,policy,approvals}.py
  workspace/{detector,scanner,worktrees}.py
  tools/{base,registry,files,patch,shell,git}.py
  feedback/{models,classifier,fingerprint,progress,engine}.py
  memory/{filter,store,context}.py
  agent/{parser,state_machine,orchestrator}.py
  credentials/{base,keyring_store,encrypted_store,service}.py
  artifacts/builder.py
  api/{app,dependencies,transfers}.py
  api/routes/{workspaces,tasks,approvals,transfers,settings,events}.py
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

> 当前交付顺序由 `docs/superpowers/plans/2026-07-16-minimal-viable-harness.md`
> 的 MVP-1—MVP-4 取代原 Task 5—14 横向顺序；原条目保留为完整产品路线。

**MVP Task 1 状态：** 已关闭。独立规约符合性与文档质量审查均为 CLEAN，证据见 `.superpowers/sdd/task-1-review.md`；未改变 `MVP-ISSUE-002`—`006` 的实现门禁。

| Task | 交付单元 | 依赖 | 可并行关系 | 建议分支 | 状态/提交 |
|---|---|---|---|---|---|
| 1 | 工程骨架与质量门禁 | 无 | 无 | `codex/foundation` | 完成（0aa862c、93863de；复审通过，书面回填 4325ecf） |
| 2 | 领域模型、Provider 与动作解析 | 1 | 可与 5 的扫描只读部分并行 | `codex/core-contracts` | 完成（RED 80d6175；实现 326a4b6；修复 3d9cea0；复审通过；完成提交 63415c5） |
| 3 | SQLite 事件存储与状态机 | 2 | 可与 10 并行 | `codex/event-state` | 完成（RED 5b7da3c；实现 2f010b3；修复 ec28b1b；复审通过；完成提交 3861613） |
| 4 | 治理、路径围栏、脱敏与审批 | 2、3 | 可与 5 并行 | `codex/governance` | 完成（首次合并 `8f2ae34`；WAL/路径门闩纠偏复审通过；补充合并 `873f1d4`） |
| 5 | 项目识别、扫描与 worktree | 1、2；worktree 子步骤依赖 4 的 `PathGuard` 契约 | detector/scanner 可与 4 并行，worktree 子步骤须等待 4 契约冻结 | `codex/workspaces` | 完成：最终受审范围 `6b2f21e..9d01b77`；规约与质量双门禁均为 CLEAN，`MVP-ISSUE-003/004/006/008`—`015` 已关闭；主控新鲜验证已通过，待本地合并 |
| 6 | 工具注册表和受限编码工具 | 4、5 | 无 | `codex/tools` | 完成（`0663960`；独立规约/质量审查 0 / 0 / 0、Approved；主控全量 `557 passed, 14 skipped`） |
| 7 | 验证与确定性反馈闭环 | 2、6 | 可与 8 并行 | `codex/feedback` | 待执行 |
| MVP-2 Task 6（brief） | 确定性反馈与 Mock Agent 主循环 | 2、6 | 独立 worktree | `codex/agent-loop` | 完成并已本地合并到 `p1`（技术 HEAD `c75c26a`；整阶段最终复审 0 / 0 / 0；合并后全量 `620 passed, 15 skipped`） |
| 8 | 记忆筛选、存储与上下文 | 3、4 | 可与 7 并行 | `codex/memory` | 待执行 |
| 9 | Agent 编排循环与机制演示 | 3—8 | 无 | `codex/orchestrator` | 待执行 |
| 10 | 凭据生命周期 | 1、4 | 可与 3 或 8 并行 | `codex/credentials` | 待执行 |
| MVP-3 Task 7 | 持久化 Workspace 与最小 REST/SSE | MVP-2 Task 6 | 独立 worktree | `codex/api` | 完成并已本地快进合并到 `p1`（技术/过程 Head `8fd5cde`；最终 Spec Yes、Quality Approved，Critical / Important / Minor 为 `0 / 0 / 0`，Ready to merge Yes；合并后全量 `703 passed, 15 skipped`，Ruff、mypy、Web lint/typecheck 通过，合并前同 Head 的 `pip check`、wheel/sdist 与 001/002/003 归档矩阵通过）；本 Task 无新增延期 |
| MVP-3 Task 8 | 最小单页 WebUI 与同源静态托管 | MVP-3 Task 7 | 独立 worktree | `codex/webui` | 整分支最终审查首轮返工范围 `b376716..6bd9ba4`；API 404/405、计划/终审完整证据门禁、TaskEvent fail-closed 已补 RED→GREEN 回归，治理 scope 真实 worktree 根语义正在关闭；本 Task 无新增延期，待独立最终复审与本地合并 |
| 11 | FastAPI REST/SSE 与交付产物 | 5、9、10 | 无 | `codex/api` | 待执行（完整产品后续范围） |
| 12 | React WebUI | 11 的接口契约 | 可在 API schema 冻结后与 11 后半段并行 | `codex/webui` | 待执行 |
| 13 | 端到端测试与三机制演示 | 9、11、12 | 无 | `codex/e2e-demo` | 待执行 |
| 14 | Docker、双 CI、README 与发布检查 | 13 | 无 | `codex/distribution` | 待执行 |

### 可用产品优先交付基线

批准设计见 `docs/superpowers/specs/2026-07-16-usable-product-priority-design.md`。完整产品的最短用户路径固定为：

```text
WebUI 接入项目并输入需求
→ 建立独立 worktree 与仓库地图
→ 默认生成并批准计划
→ Agent 通过受治理工具修改代码
→ 验证失败确定性回灌并改变下一动作
→ WebUI 展示审批、事件、验证与 diff
→ 用户获得可运行代码和基于事实的文档
→ Mock 演示、E2E、一键测试、Docker 与 CI 重复验收
```

Task 5—14 的发布范围和允许延期边界如下。表中的“延期候选”只有经过当前 Task 双重评审确认后才能进入 `DEFERRED_WORK.md`；未开始的计划内容不自动视为延期。

| Task | 发布必需范围 | 允许评估的延期候选 |
|---|---|---|
| 5 | Python/Node 识别、受限仓库地图、脏工作区保护、每任务独立 worktree | 其他语言生态识别、更丰富的历史摘要 |
| 6 | 统一注册表、读/搜/原子 patch/删除、受限 Shell、Git 状态/diff/checkpoint、全部策略前置 | 不在冻结接口中的便利工具、交互式 Shell |
| 7 | 失败分类、稳定指纹、快速/完整验证、3/8/2 预算与确定性决策 | 无；本 Task 是主要贡献的一部分 |
| 8 | 六类记忆白名单、秘密整条拒绝、来源、删除、确定性检索和上下文预算 | 向量检索、跨项目推荐、自动知识合并 |
| 9 | 计划门禁、自有可恢复 Agent 循环、停止逻辑和三个离线机制演示 | 无；完整 Agent 与机制演示不得延期 |
| 10 | DeepSeek/Qwen 本机钥匙串、容器加密存储、状态/更新/清除、公网禁用和全路径不回显 | 计划外 Provider 的专用凭据体验 |
| 11 | WebUI 所需 REST/SSE、会话防护、003 迁移、精确一次宿主传输和审查产物 | 额外查询接口、非验收所需的产物格式 |
| 12 | 项目/新任务/任务/审批/设置/Demo 主页面，SSE 重连、键盘操作和凭据清空 | 动画、主题、高级筛选、窄屏编辑 |
| 13 | 真实临时 Git fixture、三机制 E2E、四个一键命令和无网络重复验证 | 额外浏览器矩阵、长时间性能场景 |
| 14 | Docker、本地与部署文档、GitHub/GitLab CI、README、秘密审计和最终交付门禁 | 课程与首版部署之外的发布渠道 |

每个 Task 收尾时必须完成以下延期审计：

1. 对照本表和该 Task 原始验收项列出未交付内容。
2. 不满足延期条件的内容继续作为阻塞项，不得宣布 Task 完成。
3. 合法延期写入 `DEFERRED_WORK.md`，包含影响、替代、触发条件和证据。
4. 规约审查确认没有把安全或验收要求伪装为延期项；质量审查确认临时替代不会形成隐式失效路径。
5. `PLAN.md` 状态和 `AGENT_LOG.md` 明确写“无延期”或列出延期编号。

---

### Task 1：工程骨架、依赖锁定与一键质量门禁

**目标：** 建立可安装的 Python 包、React 工作区、统一命令和最小 CI 骨架，为后续 TDD 提供稳定入口。

**文件：**

- 新建：`pyproject.toml`、`requirements/windows-py311.lock`、`Makefile`、`scripts/test.ps1`
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
python -m piptools compile --extra dev --generate-hashes --allow-unsafe --strip-extras --output-file requirements/windows-py311.lock pyproject.toml
python -m pip install -r requirements/windows-py311.lock
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

这些安装命令沿用步骤 1 的同一次用户批准。预期：生成包含哈希和精确传递版本的 `requirements/windows-py311.lock` 与 `web/package-lock.json`，没有 extras 语义警告，项目以 editable 方式安装，命令退出码均为 0。Linux 传递依赖必须在 Task 14 的 Linux 容器中独立生成 `requirements/linux-py311.lock`，不得复制 Windows 解析结果。

- [ ] **步骤 6：实现统一命令并转绿**

`Makefile` 在本 Task 提供 `test-unit`（pytest）和 `test`（Ruff、mypy、pytest、ESLint、TypeScript 配置检查）。后续 Task 只在实际能力存在时加入 Vitest、`demo` 和 `test-e2e`，禁止使用返回成功的空实现或临时跳过。

`scripts/test.ps1` 的基础参数契约固定为：

```powershell
param(
    [ValidateSet("Unit", "All")]
    [string]$Mode = "All"
)
$Python = (Resolve-Path ".venv\Scripts\python.exe").Path
$Npm = (Get-Command npm.cmd -ErrorAction Stop).Source
if ($Mode -eq "Unit") {
    & $Python -m pytest
    exit $LASTEXITCODE
}
& $Python -m ruff check src tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m mypy src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Npm --prefix web run lint
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Npm --prefix web run typecheck
exit $LASTEXITCODE
```

Task 13 在保持默认 `All` 的前提下，把 ValidateSet 扩展为 `Unit|E2E|All|Demo`。

运行：`python -m pytest tests/test_config.py -v`

预期：`1 passed`。

- [ ] **步骤 7：执行质量检查与双阶段评审**

运行：`ruff check src tests && mypy src && python -m pytest tests/test_config.py -v`

预期：全部退出 0。规约符合性审查确认默认值与 `SPEC.md` 一致；代码质量审查确认锁文件无高层 Agent 框架、`.env.example` 无真实 Key。

- [ ] **步骤 8：提交并回填状态**

```text
git add pyproject.toml requirements/windows-py311.lock Makefile scripts/test.ps1 src tests web .env.example .gitignore PLAN.md AGENT_LOG.md
git commit -m "构建：建立工程骨架与质量门禁（基础子智能体）"
```

---

### Task 2：领域模型、可注入 Provider 与严格动作解析

**目标：** 冻结跨模块类型契约，让 Scripted Mock、DeepSeek/Qwen 适配器和非法动作拒绝都能离线测试。

**状态：** 待复审。RED 提交：`80d6175`；实际实现提交：`326a4b6`；首轮评审修复提交：`3d9cea0`。

**文件：**

- 新建：`src/coding_agent_harness/domain/actions.py`、`events.py`、`models.py`
- 新建：`src/coding_agent_harness/providers/base.py`、`mock.py`、`openai_compatible.py`
- 新建：`src/coding_agent_harness/agent/parser.py`
- 新建：`tests/domain/test_actions.py`、`tests/providers/test_contract.py`、`tests/agent/test_parser.py`

**接口：**

- 产出：`TaskState`、`ToolAction`、`CompleteAction`、`LLMRequest`、`LLMResponse`、`LLMProvider`、`ScriptedMockProvider`、`OpenAICompatibleProvider`、`ActionParser.parse(raw: str) -> AgentAction`。
- 消费：Task 1 的 `HarnessSettings`。

- [x] **步骤 1：先写非法动作和 Mock 序列失败测试**

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

- [x] **步骤 2：确认红色结果**

运行：`python -m pytest tests/domain tests/providers tests/agent/test_parser.py -v`

预期：导入失败，指出 `domain.actions` 或 `providers.mock` 不存在。

- [x] **步骤 3：实现严格判别联合与 Provider 协议**

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

- [x] **步骤 4：实现 OpenAI-compatible 单次调用适配器契约**

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

- [x] **步骤 5：运行目标测试并重构**

运行：`python -m pytest tests/domain tests/providers tests/agent/test_parser.py -v`

预期：全部通过；Scripted Mock 的脚本耗尽时抛出明确 `ScriptExhaustedError`。

- [ ] **步骤 6：评审与提交（实现已提交，等待规约符合性与代码质量复审）**

规约符合性审查重点：无高层 runner、Mock 完全可替换、未知字段拒绝。代码质量审查重点：模型不可变、Provider 不记录 API Key、异常不含请求头。

```text
git add src/coding_agent_harness/domain src/coding_agent_harness/providers src/coding_agent_harness/agent/parser.py tests/domain tests/providers tests/agent/test_parser.py PLAN.md AGENT_LOG.md
git commit -m "功能：建立领域契约和可注入模型接口（核心契约子智能体）"
```

---

### Task 3：SQLite 事件存储、任务仓储与可恢复状态机

**目标：** 以追加事件和乐观序号实现持久化、合法迁移与安全恢复。

**状态：** 待复审。RED 提交：`5b7da3c`；实际实现提交：`2f010b3`；首轮评审修复提交：`ec28b1b`。

**文件：**

- 新建：`src/coding_agent_harness/storage/migrations/001_initial.sql`
- 新建：`src/coding_agent_harness/storage/database.py`、`event_store.py`、`repositories.py`
- 新建：`src/coding_agent_harness/agent/state_machine.py`
- 新建：`tests/storage/test_event_store.py`、`test_recovery.py`、`tests/agent/test_state_machine.py`

**接口：**

- 产出：`Database.open(path)`、`EventStore.append/list_for_task`、`TaskRepository.create/get/update_state`、`StateMachine.transition(current, event_type)`、`recover_task(events)`。
- 消费：Task 2 的 `TaskState`、`TaskEvent`、`Task`。

- [x] **步骤 1：写事件并发和非法迁移失败测试**

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

- [x] **步骤 2：确认红色结果**

运行：`python -m pytest tests/storage tests/agent/test_state_machine.py -v`

预期：导入失败，存储与状态机模块不存在。

- [x] **步骤 3：实现事务、迁移和状态映射**

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

- [x] **步骤 4：实现恢复规则并转绿**

恢复时重放 TaskEvent；最后事件为“工具开始”但没有对应“工具完成/失败”时，状态必须变为 `WAITING_USER`，原因码 `UNCERTAIN_SIDE_EFFECT`，不得重发工具调用。

运行：`python -m pytest tests/storage tests/agent/test_state_machine.py -v`

预期：事件序号、WAL、重放、非法迁移和不确定副作用测试全部通过。

- [x] **步骤 5：评审与提交**

规约符合性审查重点：事件先落盘、恢复不重复副作用。代码质量审查重点：事务回滚、连接关闭、SQL 参数化、迁移幂等。

```text
git add src/coding_agent_harness/storage src/coding_agent_harness/agent/state_machine.py tests/storage tests/agent/test_state_machine.py PLAN.md AGENT_LOG.md
git commit -m "功能：实现事件存储和可恢复状态机（状态存储子智能体）"
```

---

### Task 4：路径围栏、统一脱敏、策略引擎与版本化审批

**目标：** 用确定性代码拦截危险动作、固定拒绝普通工具路径逃逸，并防止审批重放。

**文件：**

- 新建：`src/coding_agent_harness/governance/paths.py`、`redaction.py`、`policy.py`、`approvals.py`
- 新建：`src/coding_agent_harness/storage/migrations/002_governance_approvals.sql`
- 修改：`src/coding_agent_harness/storage/database.py`（`001_initial.sql` 内容保持不变）
- 新建：`tests/governance/test_paths.py`、`test_redaction.py`、`test_policy.py`、`test_approvals.py`

**接口：**

- 产出：以下冻结接口；Task 4 实现者不得自行改名、改变同步/异步形式或增加隐式宿主权限。
- 消费：Task 2 动作模型；Task 3 的数据库连接、`operation_lock`、最小 `approvals` 表与事件序号。

```python
class PolicyContext(BaseModel):
    workspace_root: Path
    task_state: TaskState
    event_sequence: int
    config_version: str
    llm_api_authorized: bool


class ApprovalContext(BaseModel):
    action_id: str
    event_sequence: int
    normalized_scope: str
    task_state: TaskState
    config_version: str

class PathGuard:
    def __init__(self, root: Path) -> None: ...
    def resolve(self, candidate: str | Path) -> Path: ...


class Redactor:
    def sanitize(self, value: object) -> RedactionResult: ...


class PolicyEngine:
    def evaluate(self, action: ToolAction, context: PolicyContext) -> PolicyResult: ...


class ApprovalManager:
    def __init__(self, database: Database, clock: Callable[[], datetime], uuid_factory: Callable[[], UUID]) -> None: ...
    async def request(self, task_id: UUID, reason_code: str, context: ApprovalContext, expires_at: datetime) -> ApprovalRecord: ...
    async def request_and_apply(
        self,
        task_id: UUID,
        reason_code: str,
        context: ApprovalContext,
        expires_at: datetime,
        apply: Callable[[aiosqlite.Connection, ApprovalRecord], Awaitable[None]],
    ) -> ApprovalRecord: ...
    async def decide(self, approval_id: UUID, decision: ApprovalDecision, actor: str, context: ApprovalContext) -> ApprovalRecord: ...
    async def consume(self, approval_id: UUID, context: ApprovalContext) -> ApprovalRecord: ...
    async def consume_and_apply(
        self,
        approval_id: UUID,
        context: ApprovalContext,
        apply: Callable[[aiosqlite.Connection, datetime], Awaitable[None]],
    ) -> ApprovalRecord: ...


class Database:
    @property
    def operation_lock(self) -> asyncio.Lock: ...


@dataclass(frozen=True)
class Migration:
    version: int
    sql: str


def _split_migration_statements(sql: str) -> tuple[str, ...]: ...
async def _apply_one_migration_locked(connection: aiosqlite.Connection, migration: Migration) -> bool: ...
async def _apply_migrations(connection: aiosqlite.Connection) -> None: ...
```

Task 3 只交付最小 `approvals` 表，没有审批仓储和版本化上下文字段。Task 4 必须通过 `002_governance_approvals.sql` 升级既有表、为 `tasks` 增加 `config_version TEXT NOT NULL DEFAULT 'v1'`，并把持久仓储封装在 `governance/approvals.py`；不得用进程内状态替代 SQLite 审批。`001_initial.sql` 保持内容不变且不自行写版本；所有迁移 SQL 都不得包含 `BEGIN`、`COMMIT` 或 `PRAGMA user_version`。协调器按三位文件名前缀排序，对每个下一版本执行：`BEGIN IMMEDIATE` → 在锁内读取 `user_version` → 若仍需升级则用 `sqlite3.complete_statement` 切分并逐条执行该 SQL → 设置对应 `user_version` → `COMMIT`；异常必须 `ROLLBACK`。fresh v0 必须依次执行 001、002，legacy v1 只执行 002，v2 重开不执行 DDL，未来版本固定拒绝。

`Database.operation_lock` 只串行同一个 Python `Database` 实例；跨实例互斥由 SQLite `BEGIN IMMEDIATE` 提供。每个连接固定 `busy_timeout=5000ms`；超时只返回固定 `MigrationBusyError("数据库迁移正忙")`，不得重试 DDL 或泄漏 SQL。002 对 legacy 审批的回填固定为：`action_id="legacy:<id>"`、`reason_code="LEGACY_APPROVAL"`、`event_sequence=0`、`task_state="CANCELLED"`、`config_version="legacy-v1"`、`decision="DENIED"`、`decided_by="migration"`、1970 UTC 过期且 `consumed_at` 非空；原 ID、task ID 和 created_at 保留。

**状态：** 返工可恢复。已有 RED `5a2b8cb`、实现 `c14d50d`、首轮修复 `269c1ae`；2026-07-15 用户重新批准 `SPEC.md`，第八轮陌生智能体冷启动以无 Critical/Important 的 Pass 结论关闭门禁。当前必须从步骤 6 继续纠正性 TDD。

- [x] **步骤 1：历史初始 RED——写危险动作与符号链接逃逸测试（提交 `5a2b8cb`）**

```python
@pytest.mark.parametrize("tool,args", [
    ("delete_path", {"path": "src/a.py"}),
    ("shell", {"argv": ["pip", "install", "x"]}),
    ("shell", {"argv": ["curl", "https://example.com"]}),
    ("shell", {"argv": ["git", "push", "origin", "main"]}),
    ("shell", {"argv": ["rm", "-rf", "/"]}),
])
def test_dangerous_actions_require_approval(policy, tool, args) -> None:
    result = policy.evaluate(make_action(tool, args), trusted_context())
    assert result.decision is PolicyDecision.REQUIRE_APPROVAL


def test_agent_tool_path_escape_is_denied(policy) -> None:
    result = policy.evaluate(make_action("read_file", {"path": "../secret"}), trusted_context())
    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "PATH_ESCAPE"
```

- [x] **步骤 2：历史初始 RED——确认模块缺失（仅描述初始分支，不是当前返工起点）**

运行：`python -m pytest tests/governance -v`

历史预期：导入失败，`PolicyEngine` 不存在；证据已固化在 `5a2b8cb`。当前 `codex/governance` 已有实现，后续执行者必须从步骤 6 的纠正性失败测试开始，不得再次声称模块缺失。

- [x] **步骤 3：历史实现——规范化路径和确定性规则（提交 `c14d50d`）**

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

`PathGuard` 只返回 worktree 内路径；普通 Agent 工具越界必须固定 `DENY/PATH_ESCAPE`。宿主受控导入/导出由后续 API 服务构造内部动作并使用独立的一次性审批，不把外部路径交给普通工具执行。

- [x] **步骤 4：历史实现——脱敏与一次性审批（提交 `c14d50d`）**

脱敏识别 Bearer、常见 API Key 赋值、私钥头、环境变量名和值；替换为 `[REDACTED]`，审计事件只保存规则名。审批绑定 `action_id + event_sequence + normalized_scope + expires_at`，消费后立即失效；状态或配置版本变化必须拒绝。

- [x] **步骤 5：历史修复——首轮评审转绿（提交 `269c1ae`）**

运行：`python -m pytest tests/governance -v`

历史预期：当时计划的危险行为、路径穿越、符号链接逃逸、过期/重放/错版本审批和敏感字符串测试通过；二轮审计新增的路径逃逸固定拒绝、受控导入/导出和命令语法边界以步骤 6 为准。

- [x] **步骤 6：为二轮评审缺口执行纠正性 RED—GREEN**

先补充以下参数化测试；旧实现必须准确失败，不能把环境错误计为 RED：

```python
@pytest.mark.parametrize("argv", [
    ["npm", "i", "x"],
    ["npm", "ci"],
    ["npm.cmd", "ci"],
    ["pnpm", "i", "x"],
    ["yarn"],
    ["uv", "sync"],
    ["python", "-m", "pip", "install", "x"],
    ["py.exe", "-m", "uv", "pip", "install", "x"],
    ["corepack", "pnpm", "add", "x"],
])
def test_package_manager_install_forms_require_approval(policy, argv) -> None:
    result = policy.evaluate(make_action("shell", {"argv": argv}), trusted_context())
    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert result.reason_code == "DEPENDENCY_INSTALL"


@pytest.mark.parametrize("argv", [
    ["bash", "--noprofile", "-c", "curl https://example.com"],
    ["bash", "--noprofile", "-c", "rm -rf /"],
    ["powershell", "-NoProfile", "-Command", "Invoke-WebRequest https://example.com"],
    ["cmd", "/d", "/c", "curl https://example.com"],
    ["powershell", "-EncodedCommand", "YwB1AHIAbAA="],
    ["env", "-S", "npm install x", "echo", "safe"],
    ["env", "--split-string", "curl https://example.com", "echo", "safe"],
])
def test_interpreter_options_cannot_hide_code_execution(policy, argv) -> None:
    result = policy.evaluate(make_action("shell", {"argv": argv}), trusted_context())
    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert result.reason_code == "HIGH_RISK_SHELL"


def test_malformed_network_field_is_denied(policy) -> None:
    action = make_action("network_helper", {"url": ["https://example.com"]})
    result = policy.evaluate(action, trusted_context())
    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "INVALID_ACTION"


def test_agent_path_escape_cannot_be_approved(policy) -> None:
    result = policy.evaluate(
        make_action("read_file", {"path": "../secret", "approval_id": "forged"}),
        trusted_context(),
    )
    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "PATH_ESCAPE"


@pytest.mark.parametrize("tool", ["host_import", "host_export"])
def test_host_transfer_uses_separate_exact_approval(policy, tool) -> None:
    result = policy.evaluate(
        make_internal_action(tool, source="C:/input/a.py", target="src/a.py"),
        trusted_context(),
    )
    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert result.reason_code == "EXTERNAL_TRANSFER"


def test_command_names_in_plain_arguments_are_not_executed(policy) -> None:
    result = policy.evaluate(
        make_action("shell", {"argv": ["echo", "npm", "install"]}),
        trusted_context(),
    )
    assert result.decision is PolicyDecision.ALLOW


@pytest.mark.parametrize("argv", [
    ["git", "status"],
    ["pip", "list"],
    ["docker", "images"],
    ["npm", "test"],
    ["python", "-m", "pytest"],
])
def test_safe_commands_remain_allowed(policy, argv) -> None:
    result = policy.evaluate(make_action("shell", {"argv": argv}), trusted_context())
    assert result.decision is PolicyDecision.ALLOW


@pytest.mark.parametrize(("tool", "arguments"), [
    ("read_file", {"path": "../secret"}),
    ("search", {"path": "../outside", "query": "x"}),
    ("apply_patch", {"patch": "*** Delete File: ../outside.txt"}),
    ("delete_path", {"path": "../outside.txt"}),
    ("shell", {"argv": ["rm", "../outside.txt"]}),
])
def test_every_real_tool_denies_path_escape_before_risk_approval(policy, tool, arguments) -> None:
    result = policy.evaluate(make_action(tool, arguments), trusted_context())
    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "PATH_ESCAPE"
```

路径规则优先级固定为：参数结构错误 `DENY/INVALID_ACTION` → 普通工具任何路径逃逸 `DENY/PATH_ESCAPE` → worktree 内删除等危险动作 `REQUIRE_APPROVAL` → 其余规则。实际路径 schema 固定为：`read_file.path`、`search.path`、`delete_path.path`；`apply_patch.patch` 必须解析每个 `Add/Update/Delete/Move` 文件头并逐一围栏；`shell.cwd` 省略时固定使用 worktree，提供非字符串值时 `DENY/INVALID_ACTION`，提供字符串但规范化后不等于 worktree 时 `DENY/PATH_ESCAPE`。Shell argv 中明确的绝对路径、盘符/UNC 路径或 `..` 路径 token 也逐一围栏，URL 与已识别命令选项不当作路径；`git_status/git_diff/checkpoint` 不接受调用方路径字段，额外字段固定拒绝。

策略解析只识别真实命令位置，不得扫描任意后续参数。可执行文件先取 basename、`casefold()`，再剥离 `.exe/.cmd/.bat/.com/.ps1`；包装器最多嵌套 4 层，超过上限固定 `REQUIRE_APPROVAL/HIGH_RISK_SHELL`。语法表固定为：`sudo` 无值选项 `-E/-H/-K/-k/-n/-S/-V/-v`，带值选项 `-u/--user/-g/--group/-h/--host/-p/--prompt/-C/--chdir/-R/--chroot/-T/--command-timeout`；`env` 无值选项 `-i/--ignore-environment/-0/--null`，带值选项仅 `-u/--unset/-C/--chdir`，并跳过 `NAME=VALUE`；`env -S/--split-string` 因会重新拆分命令字符串而不在本 Harness 中模拟 shellwords，固定 `REQUIRE_APPROVAL/HIGH_RISK_SHELL`；`command` 只允许 `-p` 后继续解析，`-v/-V` 作为只读命令直接结束；`nohup` 无包装器选项；`corepack` 只继续解析 `npm/pnpm/yarn`；`python/python3/py` 允许无值选项 `-B/-E/-I/-O/-OO/-P/-q/-s/-S/-u/-v/-V/-x` 与带值选项 `-W/-X`，随后必须出现 `-m` 才作为模块命令。各包装器支持 `--` 结束自身选项；已识别包装器出现未知选项、缺失选项值或不完整嵌套时保守要求审批，不猜测后续 token。

包管理器语法至少覆盖 `npm/pnpm install|i|add|ci`、裸 `yarn`、`yarn install|add`、`pip/pip3 install`、`uv pip install|sync|add`、`python|py -m pip|uv ...` 与 `poetry install|add`；安全反例 `git status`、`pip list`、`docker images`、`npm test`、`python -m pytest`、`echo npm install` 必须保持允许。Shell 解释器精确覆盖 `bash/sh/zsh/cmd/powershell/pwsh`；通过统一后缀规范化同样覆盖 `bash.exe/sh.exe/zsh.exe/cmd.exe/cmd.com/powershell.exe/pwsh.exe`，不另行猜测其他启动器。识别 `-c`、`/c`、`-Command`、`-EncodedCommand`/`-Enc`；解释器出现未知选项或无法可靠解析的代码执行形态保守要求审批。

迁移测试分两层且都不得使用 `sleep`：第一层给迁移协调器注入记录 SQL 调用次序的连接替身，确定性断言每次迁移必须先成功执行 `BEGIN IMMEDIATE`、后读取 `PRAGMA user_version`，旧实现因先读版本而稳定失败；第二层先构造 `user_version=1` 且含 UUID legacy 审批的数据库，使用 `asyncio.gather(Database.open(path), Database.open(path))` 同时打开作集成回归。两个连接最终都必须看到 `user_version=2`，legacy 行只能迁移一次且仍为拒绝、已消费、已过期，业务表集合不增加。另测 fresh v0 依次 001→002、v2 重开幂等和未来版本拒绝。

```python
async def test_migration_acquires_write_lock_before_reading_version() -> None:
    connection = RecordingConnection(user_version=1)
    applied = await _apply_one_migration_locked(
        connection,
        Migration(version=2, sql="CREATE TABLE marker (id INTEGER);"),
    )
    assert applied is True
    assert connection.statements[:2] == ["BEGIN IMMEDIATE", "PRAGMA user_version"]
    assert connection.statements[-2:] == ["PRAGMA user_version = 2", "COMMIT"]
```

审批并发测试使用两个真实连接和 `asyncio.gather`，同一已批准记录只能有一个 `consume` 成功。`request/request_and_apply/decide/consume/consume_and_apply` 均在 `operation_lock + BEGIN IMMEDIATE` 内读取 `tasks.state/config_version` 和 `MAX(task_events.sequence)` 作为权威状态，调用方 `ApprovalContext` 只用于精确匹配，不能覆盖数据库事实。`request_and_apply` 与 `consume_and_apply` 的冻结 `Callable` 注解保持不变，但运行时只接受 `approvals.py` 定义的精确冻结 `ApprovalDatabaseMutation` 声明；管理器只自行参数化执行 INSERT/UPDATE，校验操作、标识符与 approval/task 绑定，不调用任意 callable。未知声明或任意 callable 固定 `INVALID_MUTATION`，内部错误不泄漏；合法声明分别与审批创建或消费原子提交、失败时共同回滚。`decide` 使用 `decision='PENDING'` 条件更新并测试两名决策者只有一个成功；消费使用带 `decision='APPROVED' AND consumed_at IS NULL AND expires_at > now` 及完整上下文条件的单条 `UPDATE`。受影响行数为零时在同一事务重读并稳定映射为过期、拒绝、权威状态变化或 `REPLAYED`。

宿主导入/导出审批使用独立严格 `HostTransferAction` 的内部动作名 `host_import`/`host_export`，仅允许经 `PolicyEngine.evaluate_internal` 评估；普通 `evaluate(ToolAction)` 遇到同名工具固定 `DENY/INVALID_ACTION`。`normalized_scope` 必须包含脱敏后的规范化源、目标和方向；这些动作不进入 LLM 工具 schema。普通 `read_file`、`apply_patch`、`shell` 等工具即使携带该审批 ID，也不得访问外部路径。修复后运行：

```text
python -m pytest tests/governance/test_policy.py tests/governance/test_approvals.py -v
python -m pytest tests/governance -v
```

预期：聚焦测试与全部治理测试通过；不得真实访问网络或执行测试中的命令字符串。

纠偏证据（2026-07-15）：策略、迁移、审批权威上下文和宿主内部边界均分别取得精确 RED 后转绿；focused 为 `128 passed`，治理目标为 `144 passed, 1 skipped`，全量为 `246 passed, 1 skipped`。实现提交截至 `4bd4075`；独立规约符合性审查与代码质量审查尚未执行，步骤 7 保持未完成。

追加评审纠偏（2026-07-15）：补丁真实 `Move to:` 头/零合法头 fail-open、`command` 非前缀 `-v`、包管理器带值选项绕过由 RED `55d504a` 转为 GREEN `12a4328`；任意审批 callable 与调用方取消状态伪造由 RED `aeb5168` 转为受限声明 GREEN `57f5733`；普通 ToolAction 伪造宿主来源由 RED `3996d60` 转为显式内部动作 GREEN `1927bd0`。最新 focused `146 passed`、治理 `162 passed, 1 skipped`、全量/PowerShell All `264 passed, 1 skipped`；Ruff、mypy（17 个源文件）、pip check、Web lint/typecheck、无隔离 wheel/sdist 构建与归档 001/002 各 1、003 为 0 均通过。未实现 Task 6/11、003 migration 或传输服务；步骤 7 仍等待独立两阶段复审。

第二轮复审纠偏（2026-07-15）：审批声明由 RED `4fb248e`（`5 failed, 2 passed`）转为 GREEN `c28525a`，INSERT values 和 UPDATE WHERE 均必须同时含 `APPROVAL_ID`/`TASK_ID`，UPDATE 命中数必须恰为 1，否则固定 `INVALID_MUTATION` 并回滚审批消费。slash 路径由 RED `00ac97e`（`2 failed, 1 passed`）转为 GREEN `c55c07b`，`/d`、`/s`、`/c` 只在实际 `cmd` 前缀位置豁免，普通命令的 `/...` 仍先经路径围栏。最新 focused `154 passed`、治理 `170 passed, 1 skipped`、全量/PowerShell All `272 passed, 1 skipped`；其余静态、前端、构建和归档门禁均通过。步骤 7 仍等待新一轮独立两阶段复审。

第三轮复审纠偏（2026-07-15）：远程/发布命令全局选项由 RED `8ae3c37`（`15 failed, 11 passed`）转为 GREEN `ab95989`。`git/npm/pnpm/yarn/twine/docker/gh` 使用各自确定性的无值/带值 option 表，统一 parser 消费分离值与 `--option=value`，npm/pnpm/yarn 的 install/publish 共用同一 operation parser；未知、缺值和无法可靠解析的远程命令按冻结 `GIT_REMOTE_CHANGE`/`PUBLISH` fail-closed，安全 `git status`、package test、docker images、gh issue 等保持 ALLOW。最新 focused `180 passed`、治理 `196 passed, 1 skipped`、全量/PowerShell All `298 passed, 1 skipped`；其余静态、前端、构建和归档门禁均通过。步骤 7 继续等待独立两阶段复审。

第四轮复审纠偏（2026-07-15）：WAL 锁竞争公开错误边界由 RED `71aec0b`（聚焦 `1 failed, 2 passed`）转为 GREEN `e3d991b`。确定性连接桩证明三条分支：切换 WAL 遇锁且复查仍非 WAL 时固定抛出 `MigrationBusyError("数据库迁移正忙")`，不泄漏底层 SQLite 文本；复查已为 WAL 时视为其他连接已完成切换并成功返回；非锁型 `OperationalError` 按冻结边界保持原异常向上抛出。最新 focused `183 passed`、治理 `199 passed, 1 skipped`、全量与 PowerShell All 均为 `301 passed, 1 skipped`；Ruff、Mypy（17 个源文件）、`pip check`、Web ESLint/TypeScript、无隔离 wheel/sdist 构建均通过，两个归档内 001/002 各 1 份、003 为 0。步骤 7 继续等待独立两阶段复审。

最终复审与控制器验证（2026-07-15）：第五轮独立任务审查覆盖 `35e89d0..7b27d38` 的 27 个提交，结论为 `Spec: PASS`、`Quality: APPROVED`，Critical/Important/Minor 均为 0。控制器随后重新运行 `scripts/test.ps1 -Mode All`，得到 `301 passed, 1 skipped`，Ruff、mypy、Web ESLint/TypeScript 全部通过；`pip check` 无破损依赖，无隔离 wheel/sdist 构建成功，两个归档内 001/002 各 1 份、003 为 0，`git diff --check` 通过。唯一 skip 为本机 Windows 符号链接权限；Task 4 至此完成，未实施 Task 6/11 或 003 migration。

合并后 WAL owner–waiter 回归纠偏（2026-07-16）：`a6a5702` 先以可控时钟、等待函数和连接桩固化 owner/waiter 状态机 RED（聚焦 `5 failed, 1 passed`），`3bf8365` 只观察持久 `journal_mode`、关闭读取游标并在 5 秒内等待 owner；首轮真实双连接 50 次复验在第 33 次仍超时，故未沿用完成结论。Phase 1 无插桩复刻 legacy v1 取得 `500/500`，并证伪“未关闭 `user_version` cursor 导致双 waiter”；随后受控阻塞证明确认初始 WAL 尝试可在约 `5498.8ms` 后才返回 BUSY，而首版 deadline 已提前耗尽。`00a4353` 以 BUSY 前推进 5.5 秒的首观察 WAL、次观察 WAL和持续 delete 固化 `3 failed`，`cd8f3b5` 仅把 waiter 的 5 秒 deadline 改为从收到 lock contention 时开始，不重试 WAL 或迁移 DDL。最终无插桩双连接复验 `50/50`；governance `202 passed, 1 skipped`，全量与 PowerShell All 均为 `304 passed, 1 skipped`；Ruff、mypy（17 个源文件）、`pip check`、Web ESLint/TypeScript、无隔离 wheel/sdist 构建与归档 001/002 各 1、003 为 0 均通过。原完成证据已被后续纠偏取代，步骤 7 恢复待独立规约符合性与代码质量复审。

异常优先级与初始化门闩补强（2026-07-16）：独立审查结论为 `Spec: FAIL`、`Quality: CHANGES_REQUIRED`，唯一 Important 是 `_fetchone_closed` 的 `finally` 会让关闭异常覆盖读取主异常。RED `6044ac5` 得到 `2 failed, 2 passed`，GREEN `30508e1` 在读取失败时仍尝试关闭、吞掉次要关闭异常并用 bare raise 保留原对象/traceback；读取成功后的关闭失败仍原样传播。修复后双连接独立复验 `50/50`，但随后完整 governance 又真实出现一次迁移 waiter 超时（`1 failed, 205 passed, 1 skipped`，总耗时 6.85 秒），因此停止门禁并重新处理架构。用户批准同事件循环、规范化绝对数据库路径的进程内初始化门闩；RED `7c3cb53` 以 Event 握手得到 `4 failed, 1 passed`，证明同路径/等价路径会在 SQLite 外串行、不同路径可并行、首初始化异常会释放门闩、不同 loop 不复用锁。GREEN `ba48c9f` 以短线程锁保护 `WeakKeyDictionary[loop → WeakValueDictionary[path → asyncio.Lock]]` 的创建，异步锁覆盖 connect、PRAGMA、migrations 与 WAL；跨进程和跨 loop 仍使用既有 SQLite 协调。最终真实双连接 `100/100`、governance 连续 `10/10` 轮；聚焦 `15 passed`，governance `211 passed, 1 skipped`，全量与 PowerShell All 均为 `313 passed, 1 skipped`；Ruff、mypy（17 个源文件）、`pip check`、Web ESLint/TypeScript、无隔离构建和归档 001/002 各 1、003 为 0 均通过。步骤 7 继续待新的独立双重复审。

Windows 扩展路径门闩纠偏（2026-07-16）：新一轮独立审查仍为 `Spec: FAIL`、`Quality: CHANGES_REQUIRED`，唯一 Important 是 Windows 普通驱动器路径与 `\\?\` 扩展驱动器路径、普通 UNC 与 `\\?\UNC\` 扩展 UNC 会指向同一 SQLite 文件，却生成不同门闩键。RED `e897586` 用普通/扩展驱动器 Event 握手及路径键单元矩阵稳定得到 `4 failed`，覆盖扩展驱动器、扩展 UNC 的大小写等价和不同路径保持区分。GREEN `723272d` 只在 `Path.resolve(strict=False)` 后、Windows 平台上精确折叠大小写不敏感的 `\\?\UNC\` 前缀和具有盘符根的 `\\?\` 前缀，保留全部后缀；不做子串替换、不折叠或测试 `\\.\`，也未改动初始化锁生命周期或 WAL 状态机。普通/扩展驱动器确定性握手为 `1 passed`。首次外层 PowerShell 100 轮命令被执行工具在配置 120 秒超时后异常迟至 2615464ms 才以 124 退出，且没有可定位轮次，故不计为通过；随后按系统化诊断改用外部 Python 驱动、每轮新建 pytest 子进程并设置 15 秒子进程超时，原真实双连接用例有效取得 `100/100`，总计 55.9 秒、单轮 0.515—0.703 秒，没有产品挂起。最终聚焦 `19 passed, 46 deselected`，governance `215 passed, 1 skipped`，全量与 PowerShell All 均为 `317 passed, 1 skipped`；Ruff、mypy（17 个源文件）、`pip check`、Web ESLint/TypeScript、无隔离构建全部通过，wheel/sdist 内 001/002 各 1、003 为 0。步骤 7 继续待新的独立双重复审。

Windows ASCII 盘符边界纠偏（2026-07-16）：窄复审结论为 `Spec: FAIL`、`Quality: CHANGES_REQUIRED`，唯一 Important 是 `_collapse_windows_extended_path` 使用 Unicode `str.isalpha()`，会把 `\\?\é:\...`、西里尔与汉字首字符误判为 Windows 盘符并移除扩展前缀。RED `a58b962` 参数化冻结非 ASCII 拉丁/西里尔/汉字、`\\.\`、`\\?\Volume{...}\`、`\\?\GLOBALROOT\` 以及截断/嵌入前缀必须原样保留，同时确认 ASCII `A-Z/a-z` 扩展盘符继续折叠且路径键大小写等价；旧实现精确得到 `3 failed, 12 passed, 63 deselected`。GREEN `23e5f31` 只把 `isalpha()` 改为显式 ASCII 字母成员判断，未改变前缀、后缀、路径键、门闩或 WAL 的其余逻辑；相同聚焦转为 `15 passed, 63 deselected`。包含门闩/WAL/路径键的聚焦集合为 `32 passed, 46 deselected`。原真实双连接用例以每轮新 pytest 子进程和 15 秒硬超时有效复验 `100/100`，总计 57.716 秒、单轮 0.539—1.248 秒。governance 为 `228 passed, 1 skipped`，全量与 PowerShell All 均为 `330 passed, 1 skipped`；独立 Ruff、mypy（17 个源文件）、`pip check`、Web ESLint/TypeScript、无隔离构建均通过，wheel/sdist 内 001/002 各 1、003 为 0。步骤 7 继续待新的独立双重复审。

合并后补充纠偏最终复审（2026-07-16）：独立窄复审覆盖 `90187a9..c704c6b`，Critical/Important/Minor 均为 0，结论为 `Spec: PASS`、`Quality: APPROVED`。审查确认 ASCII 盘符、extended drive/UNC、非 ASCII 与设备命名空间负例、初始化门闩、WAL owner–waiter 和游标异常边界均无回归；原真实双连接测试再次以每轮 15 秒硬期限取得 `100/100`。控制器随后重新运行 `scripts/test.ps1 -Mode All`，得到 `330 passed, 1 skipped`；Ruff、mypy、Web ESLint/TypeScript、`pip check`、无隔离 wheel/sdist 构建和归档矩阵全部通过，001/002 各 1、003 为 0，工作树与差异检查清洁。Task 4 的合并后纠偏至此完成，可补充合并回 `p1`。

- [x] **步骤 7：评审与提交（纠偏实现头 `c704c6b`，补充完成证据见本提交）**

规约符合性审查重点：真实 Provider 的 LLM API 授权不扩展到工具网络；所有依赖安装入口和解释器代码执行形态均不能绕过；并发迁移在锁内重读版本。代码质量审查重点：只解析实际命令位置、规则次序无绕过且安全命令无误报、Windows 大小写路径、异常也先脱敏。

```text
git add src/coding_agent_harness/governance src/coding_agent_harness/storage/database.py src/coding_agent_harness/storage/migrations tests/governance PLAN.md AGENT_LOG.md
git commit -m "安全：实现路径围栏和版本化审批（治理子智能体）"
```

---

### Task 5：项目识别、仓库地图与每任务独立 worktree

**目标：** 安全接入本地 Git 项目，识别 Python/Node.js 验证命令，并隔离任务修改。

**状态：** 完成。最终受审范围为 `6b2f21e..9d01b77`；`.superpowers/sdd/mvp1-post-parent-spec-clean.md` 与 `.superpowers/sdd/mvp1-post-parent-quality-clean.md` 均为 CLEAN（Critical / Important / Minor 均为 0）。`c376216` 是 `MVP-ISSUE-015` 技术修复，`9d01b77` 是最终受审 Head；`MVP-ISSUE-003/004/006/008`—`015` 已据此关闭。评审、主控新鲜验证与提交前关闭步骤已完成，待本地合并；`DW-05-001` 仍只覆盖同 UID 主动篡改。

**MVP Task 2 状态：** 已关闭。提交 `26c1222` 的修复后独立规约符合性审查与代码质量审查均为 CLEAN，证据见 `.superpowers/sdd/task-2-rereview.md`；据此关闭 `MVP-ISSUE-001/005`。

- RED：path identity/scanner/worktree focused 集为 `15 failed, 40 passed, 3 skipped`，代表性失败为扩展 drive 重叠未在 `mkdir` 前拒绝、Windows 逃逸在拒绝前触发 `exists`、未知设备命名空间未 fail closed、既有对象未用 `samefile` 补证。
- 首次审查修复 RED：drive/UNC 的尾随点/空格、DOS 保留名及带扩展形式、ADS/冒号、Win32 非法字符、控制字符和非根 `/`，连同 PathGuard、Database key、WorktreeManager 零 `mkdir` 消费者回归，共得到 `66 failed, 120 passed, 3 skipped`；Windows 真实尾随点对象探针同时证明旧折叠并非普通路径等价。
- 修复 GREEN：统一保守的 Win32 组件验证只折叠可证明等价的扩展 drive/UNC；focused 集为 `186 passed, 3 skipped`，governance/storage/workspace 回归为 `407 passed, 6 skipped`。正常 Unicode、合法中间点和根位置 `/` 保持可用；独立复审 CLEAN 后 `MVP-ISSUE-001/005` 已关闭。
- 延期审计：本 Task 未新增延期，也未改变 `DW-05-001`；`MVP-ISSUE-006` 仍由后续指定 Task 调整 CI wall-clock 门禁，本 Task 仅避免路径身份检查造成性能回退。

**MVP Task 3 状态：** 已关闭。提交 `e50f343` 的独立规约符合性审查为 PASS/CLEAN、代码质量与安全性审查为 APPROVED/CLEAN，证据见 `.superpowers/sdd/task-3-review.md`；据此关闭 `MVP-ISSUE-002`。

- RED：Git 2.31.1 最小探针证明 `core.fsmonitor=false` 会执行名为 `false` 的外部 hook，而空值不会；真实 scanner sentinel 证明旧边界执行 fsmonitor/GPG；创建前 filter、scanner status 前 clean filter 与 release 重审回归均先得到预期失败。
- GREEN：新增绝对 Git 与最小受控环境、空 hooks/global config/global attributes、`core.fsmonitor=`、`log --no-show-signature`、提交/current filter gate、`worktree add --no-checkout` 和安全 materialize。创建 filter 拒绝发生在 marker/branch/target 前；release 对当前 index 与工作树重审，异常时保留现场。
- 实现验证：`tests/workspace/test_git_safety.py -v` 为 `8 passed`；独立复审 focused 为 `23 passed`、workspace 为 `98 passed, 4 skipped`，Critical/Important/Minor 均为 0。

**MVP Task 4 状态：** 已关闭。其相关实现已纳入最终受审范围 `6b2f21e..9d01b77`；最终规约与质量双门禁均为 CLEAN，据此关闭 `MVP-ISSUE-003/004/006`。

- RED：detector focused 为 `14 failed, 13 passed, 1 skipped`，覆盖推导命令无 trust、package/pyproject raw 变化不失效、旧 harness 指纹不符合 v1 manifest、无命令状态错误、模型不一致组合和独立 fixture 真实失败。
- GREEN：三源 raw SHA256、缺失显式 `null`、有效 commands/env allowlist/timeout 与领域分隔组成 `verification-trust/v1`；重复检测稳定、源增删失效，模型拒绝 trust 不一致。Python fixture 改为 src package，Node 24 四命令仅用内置能力并在独立副本运行；focused 为 `27 passed, 1 skipped`。
- 验证：workspace 为 `109 passed, 4 skipped`，全量为 `499 passed, 6 skipped`；Ruff、mypy、pip check 与差异检查均通过。10,000 文件 CI 用例只验证功能并记录耗时，本机独立基准为 `0.88s`。未新增或改变延期项。

**MVP-1 最终整分支门禁状态：** 已关闭。受审范围 `6b2f21e..9d01b77` 的最终规约报告与质量报告均为 CLEAN，Critical / Important / Minor 均为 0；质量报告确认 Ready to merge：Yes。主控在关闭提交 `eceac96` 后重新取得全量 pytest `544 passed, 14 skipped`、Ruff、mypy、Web lint/typecheck、pip check、构建与 diff check 全部通过的证据。`MVP-ISSUE-003/004/006/008`—`015` 已关闭；待本地合并，且没有扩大到 MVP-2。`scripts/test.ps1` 对未准备依赖的隔离 worktree 存在假阳性风险，已登记为 `MVP-ISSUE-016`，由 MVP-4 Task 9 修复，不回开 MVP-1。

- RED：四组 focused 为 `17 failed`。不同 anchor 的 PathGuard、Policy、`same_path/is_within` 与 worktree 注册均记录到拒绝前 identity probe；local config 四类配置未 gate，真实 Git 读取 outside ignore/重定向 worktree；两层 junction 构造成功且 trusted linked API 缺失；最终 `same_path` 泄漏原异常。
- 质量复审追加 RED：drive-relative `Z:payload` 与 rooted-relative `\payload` 在 PathGuard、Policy、path identity 与 worktree registration 的零探测契约为 `6 failed, 246 deselected`；primary `commondir`、`config.worktree` reparse 和 trusted linked `commondir` 改写为 `3 failed, 21 deselected`。后者证明 `config --local` 审计本身仍依赖可被仓库元数据改变的 repository discovery，旧 GREEN 证据据此作废。
- 最终 GREEN：普通路径关系在纯相对路径拼接前拒绝含 drive/root 但非 absolute 的 Windows 输入；受信配置仍使用独立物理补证。SafeGit 先 no-follow 验证 primary/linked 上下文，主仓拒绝任何 `commondir`，linked 每命令复验 `commondir` 身份与内容严格为 `../..`，拒绝 `extensions.worktreeConfig` 和任何 `config.worktree`；审计改为在安全 cwd 对已验证的精确 common config 执行 `config --file <approved-config> --no-includes -z --list`，完全脱离 repository discovery。safety assets 与最终 create 的既有修复保持不变。
- 历史新鲜验证快照：focused `292 passed, 6 skipped`；governance/storage/workspace `466 passed, 13 skipped`；全量 pytest `536 passed, 13 skipped`；Ruff `All checks passed!`；mypy 检查 26 个源文件无问题；pip check 无损坏依赖。scanner no-follow 修复后的实施验证为 scanner `20 passed, 3 skipped`、governance/storage/workspace `467 passed, 14 skipped`、全量 pytest `537 passed, 14 skipped`，Ruff/mypy/pip check/差异检查通过；技术修复已包含于 `af11fea`，最终整分支规约与质量门禁仍待完成。

**文件：**

- 新建：`src/coding_agent_harness/workspace/models.py`、`files.py`、`detector.py`、`processes.py`、`scanner.py`、`worktrees.py`
- 新建：`tests/workspace/test_detector.py`、`test_processes.py`、`test_scanner.py`、`test_worktrees.py`
- 新建：`tests/fixtures/python_project/pyproject.toml`、`tests/fixtures/python_project/src/sample/__init__.py`、`tests/fixtures/python_project/tests/test_sample.py`
- 新建：`tests/fixtures/node_project/package.json`、`tests/fixtures/node_project/src/math.ts`、`tests/fixtures/node_project/tests/math.test.ts`

**接口：**

- 产出：最小严格类型化 `Workspace`、`ProjectProfile`、`RepositoryMap`、`WorktreeInfo`，以及 `ProjectDetector.detect(root) -> ProjectProfile`、`WorkspaceScanner.scan(root) -> RepositoryMap`、`WorktreeManager.create(task_id, base_commit) -> WorktreeInfo`。
- 消费：Task 4 `PathGuard`。Task 5 不消费不存在的 Task 2 `Workspace`；本 Task 产出的 `Workspace` 先作为运行期模型，Task 11 的 003 迁移再补齐其持久化字段、仓储和 `host_transfers`，本 Task 不修改 001/002 或新增迁移。

步骤 1—3 的 detector/scanner 只读部分不消费 `PathGuard`，可与 Task 4 并行；步骤 4 的 `WorktreeManager` 必须等待 Task 4 的 `PathGuard` 契约通过复审并合并，禁止在并行分支复制或猜测路径围栏实现。

- [x] **步骤 1：写 Python/Node 识别与文件上限失败测试**

```python
def test_detects_python_and_node_commands(tmp_git_repo) -> None:
    (tmp_git_repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_git_repo / "package.json").write_text('{"scripts":{"test":"vitest run","build":"vite build"}}', encoding="utf-8")
profile = ProjectDetector().detect(tmp_git_repo)
assert profile.commands.test == ("python", "-m", "pytest")
npm = "npm.cmd" if os.name == "nt" else "npm"
assert profile.commands.build == (npm, "run", "build")


def test_scanner_rejects_more_than_10000_tracked_files(fake_git) -> None:
    fake_git.tracked_files = [f"f{i}" for i in range(10001)]
    with pytest.raises(WorkspaceLimitError):
        WorkspaceScanner(fake_git).scan(Path("repo"))
```

- [x] **步骤 2：确认红色结果**

运行：`python -m pytest tests/workspace -v`

预期：导入失败，workspace 模块不存在。

- [x] **步骤 3：实现只读扫描与命令识别**

仅通过参数数组调用 `git -C <root> ls-files -z`、`git log -n 20` 和 `git status --porcelain=v1 -z`；status 按 NUL bytes 解析普通及 rename/copy 双路径，并以 `os.fsdecode` 保留跨平台真实路径。`processes.py` 的 Git runner 默认超时 300 秒且以 `math.isfinite` 拒绝非有限值，stdout/stderr 各限 64 MiB；跨 Windows/Linux 使用两个 PIPE reader 线程固定 64 KiB chunk 并发读取，每流只保留 `limit+1`、超限立即 best-effort kill，之后仍 drain 到 EOF 并 join/wait/关闭 pipe。超时、超限和普通启动后/cleanup 异常进入不确定状态；`KeyboardInterrupt`、`SystemExit` 等宿主级 `BaseException` 也必须先完成 best-effort kill/wait/join/close，再原样传播且不得被 cleanup 异常覆盖。不使用无界临时磁盘。忽略依赖/构建目录；README/AGENTS/配置读取均受大小限制。自定义 `.harness.yml` schema 只允许 `test`、`lint`、`typecheck`、`build` 的 argv 数组、timeout 与 env allowlist，首次执行进入信任审批。运行期安全序列使用 tuple 深不可变表示，JSON 仍序列化为数组，信任指纹关联命令不能在模型内部被原地修改。

- [x] **步骤 4：实现 worktree 隔离**

分支名固定为 `harness/task-<uuid前8位>`；worktree 放在不暴露给 LLM/普通工具的 Harness 私有状态目录，而不是项目目录内；`state_root` 与 Git 根任一方向的真实路径重叠均在创建目录前拒绝，create 前再次保证 workspace state/target 不落入 Git 根。创建前拒绝非 Git、基准提交不存在和同 Workspace 已有写任务。Git add 已启动或 create/release 后验不一致时，不主动删除仍存在的 target/branch 等现场、不回滚 Git 已完成的副作用，并保留 `.active` 进入人工接管；只有 runner 抛出专用“进程确定未启动”异常时可安全删除本次 marker，普通 `OSError` 不具备该语义。release 的只读 status runner 异常映射为领域失败并保留 marker；remove 只有专用未启动异常是普通失败，任意非零或启动后/未知异常均进入不确定状态并阻塞下一 writer。不得递归清理不确定路径或清理/覆盖主工作区脏改动。

- [x] **步骤 5：转绿、性能与双平台边界检查**

运行：`python -m pytest tests/workspace -v`

预期：识别、限制、脏主工作区保护、worktree 创建/释放和 Windows 空格路径测试通过；10,000 文件合成扫描基准低于 5 秒（CI 慢机只记录，不作硬失败；本机验收硬目标 5 秒）。

- [x] **步骤 6：评审、验证与提交前关闭（最终双门禁 CLEAN；允许本地合并，尚未合并）**

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

- 产出：`ToolContext`、`ToolResult`、`ToolRegistry.dispatch(action, context)` 和工具 `read_file`、`search`、`apply_patch`、`delete_path`、`shell`、`git_status`、`git_diff`、`checkpoint`。`delete_path` 是实际注册工具，执行前必须消费 Task 4 的精确一次性审批；Git push/merge 只通过受治理 Shell 或后续显式能力提供，不把虚构的 `git` 工具写入测试。
- 消费：Task 4 `PolicyEngine/PathGuard/Redactor`，Task 5 worktree。

Harness `state_root` 永久不属于 worktree，也不进入普通 `read_file`、`search`、`apply_patch`、`delete_path`、`shell` 或 Git 工具的可访问范围；审批不能提升该能力。Task 6 聚焦测试和后续 Task 13 集成/E2E 必须验证访问 `state_root` 固定返回 `DENY/PATH_ESCAPE`，不能仅依赖 state_root 未出现在提示词中。

`apply_patch` 的 Task 5 协作边界：同一 Workspace 最多一个 Harness 写任务；同目录 `O_EXCL` 锁线性化所有遵守协议的 Harness 实例。create 使用原子 no-replace；replace 在持锁下、`os.replace` 前复验 `expected_sha256`，已在复验前完成的编辑返回 `STALE_CONTENT`。普通跨平台文件系统没有按 SHA-256 条件原子 replace；忽略锁的同 UID 外部进程若恰在最终复验与 replace 之间改写，属于 SPEC 9.2 已批准的外部竞争边界。检测到身份或摘要不一致必须 fail closed，现场不确定时人工接管。

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
- 新建：`src/coding_agent_harness/storage/migrations/003_host_transfers.sql`
- 新建：`src/coding_agent_harness/api/app.py`、`dependencies.py`、`transfers.py`
- 新建：`src/coding_agent_harness/api/routes/workspaces.py`、`tasks.py`、`approvals.py`、`transfers.py`、`settings.py`、`events.py`
- 新建：`tests/api/test_workspaces.py`、`test_tasks.py`、`test_approvals.py`、`test_transfers.py`、`test_events.py`、`test_security.py`
- 新建：`tests/artifacts/test_builder.py`

**接口：**

- 产出：`create_app(container) -> FastAPI`；`POST /api/workspaces`、`POST /api/tasks`、`POST /api/tasks/{id}/plan-decision`、`POST /api/approvals/{id}/decision`、`POST /api/transfers`、`POST /api/transfers/{id}/execute`、`POST /api/tasks/{id}/{pause|resume|cancel|finalize}`、`GET /api/tasks/{id}`、`GET /api/tasks/{id}/events`、`GET/PUT/DELETE /api/settings/credentials/{provider}`、`GET /health`。
- 消费：Tasks 4、5、9、10 服务接口。`POST /api/transfers` 只能由已认证用户创建 `host_import` 或 `host_export` 内部动作并返回审批；`execute` 必须消费精确一次性审批后由宿主复制，不能调用普通 Agent 文件或 Shell 工具。import 的目标和 export 的源必须通过 `PathGuard` 位于 worktree；外部端在审批前规范化并展示，执行时重新校验文件身份与目标，状态或文件变化使审批失效。

```python
class TransferDirection(StrEnum):
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"


class TransferState(StrEnum):
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


class PathIdentity(BaseModel):
    resolved_path: str
    device: int
    inode: int


class FileIdentity(PathIdentity):
    size: int
    mtime_ns: int
    sha256: str


class TransferRecord(BaseModel):
    id: UUID
    task_id: UUID
    action_id: str
    approval_id: UUID
    direction: TransferDirection
    external_path: str
    workspace_path: str
    source_parent_identity: PathIdentity
    source_identity: FileIdentity
    target_parent_identity: PathIdentity
    target_identity: FileIdentity | None
    expected_target_sha256: str | None
    idempotency_key: str
    event_sequence: int
    config_version: str
    state: TransferState
    result_sha256: str | None


class HostTransferService:
    async def request(self, task_id: UUID, direction: TransferDirection, source: str, target: str, idempotency_key: str) -> TransferRecord: ...
    async def execute(self, transfer_id: UUID, approval_context: ApprovalContext) -> TransferRecord: ...
    async def recover(self, transfer_id: UUID) -> TransferRecord: ...
```

路由 `{id}` 始终是 `transfer_id`，不是 `approval_id`；响应同时返回两个 ID。API 请求必须提交 `task_id`，服务通过该任务的持久 worktree 解析 worktree 内端，不接受 `workspace_id` 推断活跃任务。`action_id` 固定为 `transfer:<transfer_id>` 并同时写入 `TransferRecord` 与 `ApprovalContext.action_id`，禁止使用 approval ID 或临时序号替代。`003_host_transfers.sql` 创建 `host_transfers` 表，保存以上字段并对 `action_id`、`approval_id`、`idempotency_key` 分别建唯一约束；路径与文件身份是执行数据，不能从脱敏展示 scope 反向解析。`source_parent_identity` 始终保存源文件既有父目录的完整 path/device/inode；`target_identity` 在目标已存在时保存完整 `resolved_path/device/inode/size/mtime_ns/sha256`，目标不存在时为 `None`，不能只靠 SHA-256 判断未变化。`Approval.normalized_scope` 只用于精确绑定和展示，其确定性 JSON 含 action ID、direction、两端规范化路径、source parent/source identity、target parent/target identity、expected target digest、transfer ID。`HostTransferService.request` 必须通过 `ApprovalManager.request_and_apply` 在同一事务创建 approval 与 transfer，禁止留下无 transfer 的可执行审批；审批拒绝或过期后 transfer 固定转为 `FAILED`。

`POST /api/transfers` 强制要求非空 `Idempotency-Key` 请求头并传入服务；相同 key 且规范化 direction/source/target/文件身份完全一致时返回既有记录和 HTTP 200；同一 key 对应不同请求时返回 HTTP 409/`IDEMPOTENCY_CONFLICT`，不得泄漏唯一约束异常。

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


def test_external_transfer_requires_exact_one_time_approval(client, token, seeded_task) -> None:
    requested = client.post(
        "/api/transfers",
        headers={"X-Harness-Session": token, "Idempotency-Key": "import-a-v1"},
        json={"task_id": seeded_task.id, "direction": "import", "source": "C:/input/a.py", "target": "src/a.py"},
    )
    assert requested.status_code == 202
    transfer_id = requested.json()["transfer_id"]
    assert requested.json()["approval_id"]
    assert client.post(f"/api/transfers/{transfer_id}/execute", headers={"X-Harness-Session": token}).status_code == 409


def test_approved_transfer_executes_once(client, token, approved_transfer) -> None:
    first = client.post(
        f"/api/transfers/{approved_transfer.id}/execute",
        headers={"X-Harness-Session": token},
    )
    second = client.post(
        f"/api/transfers/{approved_transfer.id}/execute",
        headers={"X-Harness-Session": token},
    )
    assert first.status_code == 200
    assert second.status_code == 409


@pytest.mark.parametrize("changed", ["source", "target", "symlink"])
def test_transfer_rejects_file_identity_change(client, token, approved_transfer, changed) -> None:
    approved_transfer.mutate(changed)
    response = client.post(
        f"/api/transfers/{approved_transfer.id}/execute",
        headers={"X-Harness-Session": token},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "STALE_TRANSFER"


def test_target_same_content_with_new_inode_is_stale(client, token, approved_transfer) -> None:
    approved_transfer.replace_target_with_same_bytes_new_inode()
    response = client.post(
        f"/api/transfers/{approved_transfer.id}/execute",
        headers={"X-Harness-Session": token},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "STALE_TRANSFER"
```

- [ ] **步骤 2：确认红色结果**

运行：`python -m pytest tests/api tests/artifacts -v`

预期：导入失败，API app 不存在。

- [ ] **步骤 3：实现命令路由与安全中间件**

启动生成随机会话令牌，只通过启动终端和首屏注入提供；所有 mutation 校验同源 Origin 与 `X-Harness-Session`。服务默认绑定 `127.0.0.1`；公网 demo 使用独立只读/受限配置。错误响应为 `{code, message, details, event_id}` 且先脱敏。`transfers.py` 只接受 `import|export`、单个普通文件和精确源/目标；创建请求计算并持久化源身份、目标现有摘要和幂等键，只生成审批，不复制。目录递归、通配符、设备路径、公网 demo 和 Agent 自发请求固定拒绝。

执行状态机固定为：`WAITING_APPROVAL` → 在消费审批前首次校验两端解析路径、source parent/source identity、target parent/target identity 和预期目标摘要 → 使用 `ApprovalManager.consume_and_apply` 在同一 SQLite 事务原子消费审批并把 transfer 改为 `EXECUTING` → 副作用前再次执行相同校验 → 在目标同目录以 `.harness-transfer-<transfer_id>.tmp` 创建独占临时文件、flush、`fsync`，第三次执行全部身份校验后用原子替换落盘 → 新事务记录 `COMPLETED/result_sha256`。首次校验失败不消费审批并返回 `STALE_TRANSFER`；进入 `EXECUTING` 后校验失败记录 `FAILED`。进入 `EXECUTING` 后若进程中断、临时文件残留、目标已替换但完成事件未落盘或结果无法确认，恢复时一律变为 `UNCERTAIN`、清理可确认未发布的临时文件且绝不自动重试，等待用户检查并创建新 transfer。import 的目标和 export 的源必须通过 `PathGuard` 位于 worktree；外部端及其既有父目录的解析身份在批准与执行时一致。覆盖已有目标必须把其批准时 SHA-256 纳入审批；目标从不存在变为存在同样固定 `STALE_TRANSFER`。

故障注入测试必须覆盖：原子绑定前失败仍可重新执行；绑定后、原子替换前崩溃恢复为 `UNCERTAIN` 且不复制；替换后、`COMPLETED` 落盘前崩溃恢复为 `UNCERTAIN` 且目标只变化一次；重启不得重放；普通工具携带 transfer 或 approval ID 仍不能越界。所有注入使用事件/Stub，不使用 `sleep`。

003 迁移回归必须覆盖且不得使用 `sleep`：fresh v0 严格执行 001→002→003；已有 v2 数据库只执行 003且既有 approvals 内容逐字段不变；两个 `Database.open()` 并发打开 v2 后都看到 v3 且只建一份 `host_transfers`；v3 重开不执行 DDL；`user_version>3` 固定拒绝。wheel 与 sdist 中 001/002/003 必须各恰好一份。

- [ ] **步骤 4：实现 SSE 与 ArtifactBuilder**

SSE 每条事件含递增 `id`、`event: task-event`、脱敏 JSON data；支持 `Last-Event-ID` 补发和 15 秒心跳。ArtifactBuilder 仅从实际 diff、VerificationRun 和事件生成 summary、diff、checks、docs，关联 event sequence；diff 变化后旧包失效。

- [ ] **步骤 5：转绿与接口契约导出**

运行：`python -m pytest tests/api tests/artifacts -v`

预期：REST、会话令牌、Origin、审批版本、一次性受控导入/导出、普通工具不能消费传输审批、SSE 续传/断线和文档不虚构测试通过。保存 OpenAPI 快照到 `web/src/api/openapi.json`，作为 Task 12 类型实现依据。

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

- 新建：`Dockerfile`、`.dockerignore`、`compose.yaml`、`render.yaml`、`requirements/linux-py311.lock`
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

Docker 多阶段构建前端和 Python 运行层，最终非 root 用户运行；只暴露应用端口，项目与状态必须显式挂载。先在 `python:3.11` Linux 构建阶段用与 Task 1 相同的 pip-tools 命令生成 `requirements/linux-py311.lock`，再与仓库版本逐字比较；不一致时 CI 失败并要求显式更新。Windows 使用 `requirements/windows-py311.lock`，两者都由同一个 `pyproject.toml` 直接依赖集合生成。`docker run` 文档展示 localhost 模式、状态卷、单项目挂载和容器主密码的安全输入方式，不把密码写入镜像/命令历史。公网镜像固定 Mock 模式并禁用凭据、任意路径和外部网络工具。

Linux 锁文件生成命令固定为：

```text
python -m piptools compile --extra dev --generate-hashes --allow-unsafe --strip-extras --output-file requirements/linux-py311.lock pyproject.toml
```

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
git add Dockerfile .dockerignore compose.yaml render.yaml requirements/linux-py311.lock .github .gitlab-ci.yml docs README.md .env.example REFLECTION.md tests/distribution PLAN.md AGENT_LOG.md
git commit -m "交付：完成容器、持续集成和项目文档（交付子智能体）"
```

## `SPEC.md` 验收覆盖矩阵

| `SPEC.md` 验收项 | 主要 Task | 直接证据 |
|---|---|---|
| 1. 添加 Git 项目、识别并拒绝无效/越界路径 | 4、5、11、12 | 路径围栏单测、Workspace API 与项目页测试 |
| 2. 默认计划审批；显式跳过才直接执行 | 3、9、12 | `test_plan_gate.py` 与 WebUI 计划按钮测试 |
| 3. 每任务独立 worktree，主分支不提前变化 | 5、13 | worktree 集成测试与临时 Git E2E |
| 4. DeepSeek/Qwen 共用接口，Mock 可替换 | 2、9 | Provider 契约测试与 Scripted Mock 主循环测试 |
| 5. 危险动作、受控导入/导出、路径逃逸拒绝和过期审批拦截 | 4、6、11、13 | 参数化策略测试、宿主传输 API 测试与治理 E2E |
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
