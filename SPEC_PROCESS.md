# Spec Process

## 1. 过程范围

本文记录 2026-07-14 使用 Superpowers `brainstorming` 生成 Coding Agent Harness 设计与 `SPEC.md` 的过程。主开发 agent 为 OpenAI Codex。整个阶段遵守“一次一个问题”“比较多个方案”“分段确认设计”和“设计获批前不写实现代码”的门禁。

仓库开始时仅有一段 README 定位：“以确定性反馈闭环为主要贡献，能读写受限工作区、运行测试、根据失败自动修正，危险命令经过护栏和人工审批。”这段描述确定了方向，但没有目标用户、范围、状态机、数据模型、凭据方案或客观验收标准。

## 2. Brainstorming 关键节点

### 2.1 从“完整 agent”收敛到可验收场景

- **Agent 提问：** 首要目标用户是谁，最痛的问题是什么？
- **用户回答：** “我希望这是一个完整的 agent，首要目标是程序员，具体问题是需要 AI 直接操纵项目写代码。”
- **处理决策：** 将产品与代码补全工具区分，定义为可直接操作 Git 项目的本地 coding agent。

- **Agent 追问：** 第一版端到端任务的输入和交付是什么？
- **用户回答：** “程序员输入需求，agent 交付可以完成的代码和文档。”
- **修正：** “可以完成”进一步被客观化为代码 diff、测试/lint/type/build 证据和配套文档，而不是模型自行宣称完成。

### 2.2 从“支持正常项目”收敛语言范围

- **用户疑问：** “正常应该有哪些项目类型？”
- **Agent 建议：** 核心保持命令驱动，Python/Node.js 提供官方自动识别，其他语言使用自定义验证命令。
- **用户决定：** 同意。
- **影响：** 避免同时深做 Go、Rust、JVM 和 C/C++ adapter，把工程投入留给反馈闭环。

### 2.3 解决本地代码操作与公网 WebUI 的矛盾

- **Agent 指出：** 远程 WebUI 无法安全直接访问程序员电脑上的项目。
- **建议：** 本地完整服务绑定 localhost；公网只使用临时沙箱和 Mock LLM。
- **用户决定：** 同意“本地完整功能 + 公网隔离演示”。
- **影响：** 同时满足直接操作本地项目和课程公网 URL 要求，不引入远程主机访问本地文件的高风险通道。

### 2.4 Provider 与凭据

- **用户偏好：** “deepseek 或 qwen”。
- **Agent 调研：** 两者官方文档均提供 OpenAI-compatible 对话/工具调用接口。
- **建议：** 共用一个内部 provider 抽象，同时支持 DeepSeek、Qwen 和 Mock LLM；启动时选择。
- **用户决定：** 同意。
- **影响：** 不使用 provider SDK 的 agent runner，只使用底层单次对话能力。

### 2.5 治理与记忆边界

- **用户决定：** 删除、工作区外访问、安装依赖、网络、Git push 和高风险 Shell 全部需要审批。
- **用户决定：** 记忆允许项目约定、架构决策、工具、完成任务、失败经验和用户规则；隐私与 Key 绝不进入记忆。
- **Agent 补充：** 工具输出在事件/记忆前统一脱敏，审批与事件版本绑定，避免重放。

### 2.6 反馈闭环的停止条件

- **用户请求：** 希望由 Agent 推荐。
- **Agent 建议：** 同一失败指纹最多 3 轮；单任务最多 8 轮；连续 2 轮没有减少失败或改变类别即升级；单命令默认 5 分钟。
- **用户决定：** 同意。
- **影响：** 把“自我修正”从无限 ReAct 循环变为可确定性测试的预算与进展机制。

### 2.7 计划默认行为的关键修正

对话中曾出现“只有用户提到计划才生成”的表述，用户随后明确更正为：“只有当用户显式说明不需要计划时才直接生成。”Agent 以最新决定为准，并再次确认默认计划必须等待批准后才能修改代码。

- **最终规则：** 默认计划并等待批准；仅在用户明确跳过计划时直接执行。
- **教训：** 涉及默认安全行为时必须复述最终语义，不能从相近表述猜测。

### 2.8 架构方案选择

Agent 比较了三种方案：

1. 事件驱动、可恢复状态机。
2. 简单同步 ReAct 循环。
3. 固定工作流/DAG。

用户选择方案一。原因是它最适合计划审批、危险动作 HITL、反馈预算、崩溃恢复和离线状态迁移测试；额外复杂度与课程的工程深度目标相符。

## 3. 至少三轮关键迭代摘要

| 轮次 | 初始表述 | 追问暴露的问题 | 最终决策 |
|---|---|---|---|
| 1 | 完整 agent，直接写代码 | 谁使用、何为完成不明确 | 程序员输入需求，交付 diff、通过的验证和文档 |
| 2 | 支持正常项目 | “正常”可能扩张为所有语言 | Python/Node.js 官方适配，其他项目自定义命令 |
| 3 | 必须有公网 WebUI | 公网无法安全访问本地项目 | localhost 完整产品 + Render Mock 沙箱演示 |
| 4 | DeepSeek 或 Qwen | 选择单一供应商会增加迁移成本 | 共用 provider 抽象，同时支持两者与 Mock |
| 5 | 自我修正 | 无停止条件会无限循环 | 3/8 预算、2 轮无进展、5 分钟命令超时 |
| 6 | 计划行为出现相反表述 | 默认是否执行关系到安全 | 默认计划并审批，明确跳过才直接执行 |

## 4. AI 建议与人工决策

### 4.1 AI 提出且用户采纳

- 通用命令驱动内核，Python/Node.js 官方适配。
- 本地完整服务与公网 Mock 演示分离。
- DeepSeek/Qwen 共用内部 provider 抽象。
- 双层反馈预算和无进展检测。
- Python/FastAPI/SQLite + React/TypeScript 技术栈。
- 每任务独立 Git worktree。
- 事件驱动可恢复状态机。
- 面向 coding 的仓库地图、原子 patch、快速/完整验证、checkpoint、diff 和 Git 助手。
- Open Design `dashboard` + `Neutral Modern` 的桌面工作台方向。

### 4.2 用户提出或强化

- 产品必须是完整 coding agent，而非代码建议器。
- 所有列举的高风险类别都必须审批。
- 隐私、Key 等绝不能进入记忆。
- 只需要 WebUI 作为用户入口，不把公共 HTTP API 作为首版产品功能。
- 默认必须先生成并批准计划；用户明确不要计划时才直接执行。

### 4.3 被推翻、修正或延期

- **被用户修正：** 一度出现“用户提到计划才生成”的方向，最终反转为默认计划优先。
- **视觉伴侣：** Agent 在进入 WebUI 布局时按技能要求提出；用户先接受后立即改为不需要，后续全部使用文字，未启动视觉服务器。
- **延期：** 多 agent 产品编排、云端任意仓库、全语言 AST 重构和 IDE 插件，以保护反馈闭环深度。
- **未采用：** 简单 ReAct 循环和固定 DAG，前者治理/恢复过浅，后者对动态编码任务不够灵活。

## 5. 分段批准记录

用户逐段确认了：

1. 总体架构。
2. 编码便捷功能与延期范围。
3. 数据流和状态机。
4. 安全与错误处理。
5. 测试、机制演示与验收。
6. 数据模型与记忆。
7. WebUI 与内部接口。
8. 非功能、分发和部署。
9. 用户故事。
10. 风险、非目标与边界。

用户最终明确回复“批准”，授权写入规约文档。

## 6. Brainstorming 方法反思

### 做得好的地方

- 一次一个问题迫使“完整 agent”“正常项目”“可以完成”等模糊词变成可验收约束。
- 分段批准降低了长规约中隐藏误解的风险。
- 多方案比较让事件驱动状态机成为有理由的选择，而非直接套用熟悉架构。
- 对默认计划行为的复述捕获了用户更正，避免形成相反的安全默认值。

### 不满意或形式成本较高的地方

- 对明确的小决策仍需逐轮确认，交互时间较长。
- 视觉伴侣的邀请在用户已偏好文字时产生一次无效往返。
- 设计阶段能验证一致性，却不能替代真实代码、平台路径和 provider 契约测试。

## 7. 实施计划生成过程

用户完成设计批准并指示“进行下一步”后，主 Agent 使用 Superpowers `writing-plans` 把 `SPEC.md` 转换为 `PLAN.md`。计划阶段仍未编写任何 Harness 实现代码。

### 7.1 计划结构决策

初步考虑过把核心、WebUI 和交付拆成多个计划文件，但课程冷启动要求陌生智能体只能读取 `SPEC.md` 与 `PLAN.md`。因此最终采用一份完全自包含的根计划，并在内部划分 14 个可独立审查的 Task；每个 Task 都列出目标、准确文件、接口、失败测试、最小实现方向、验证命令、两阶段评审和中文提交说明。

计划显式记录 Task 依赖和可并行关系。Task 1 冻结工程基线；领域契约完成后，治理与 Workspace、反馈与记忆、事件存储与凭据可按依赖并行；编排、API、WebUI、E2E 和分发依次汇合。正式执行时，每个独立功能仍须使用 worktree 和新鲜子智能体。

### 7.2 依赖与自审修正

主 Agent 从 PyPI 和 npm 官方注册表核对直接依赖版本，并检查关键 Node peer dependency。自审发现最新版 `typescript-eslint@8.64.0` 声明 TypeScript 必须 `<6.1.0`，与最初选择的 `typescript@7.0.2` 冲突，因此在提交计划前改为兼容的 `typescript@6.0.3`，并增加与 Node.js 24 对应的 `@types/node@24.13.3`。

`writing-plans` 自审还发现并修正了以下问题：新文件不能使用 `git commit -am` 遗漏暂存；基础 Task 不能用返回成功的临时 SKIP 假装 E2E/demo 已存在；状态机必须包含 `WAITING_ACTION_APPROVAL`；每个 Task 必须分别写明规约符合性审查和代码质量审查；所有验收项必须映射到明确 Task 与证据。

## 8. 陌生智能体冷启动门禁

### 8.1 第一次冷启动试运行

主 Agent 在提交 `PLAN.md` 后创建隔离分支 `codex/cold-start-audit`，启动无先前会话历史的“冷启动实施审计员”。初始材料只有 `SPEC.md` 和 `PLAN.md`，并要求其选择 1—2 个 Task、按 TDD 推进、遇到不确定处立即暂停、不提交也不推送。

审计员选择 Task 1，新建了与计划一致的 `tests/test_config.py`，随后运行计划给出的 RED 命令：

```text
python -m pytest tests/test_config.py -v
```

实际输出不是预期的产品导入失败，而是：

```text
E:\python3.9\python.exe: No module named pytest
```

审计员正确把它判定为环境错误而非有效 RED，并在 Task 1 步骤 2 暂停；没有创建生产代码，没有安装依赖，没有提交或推送。因为 Task 2—14 都有前置依赖，它没有越级选择第二个 Task。

### 8.2 暂停问题、责任与差距

| 发现 | 责任判断 | 处理 |
|---|---|---|
| Task 1 在 RED 之后才安排依赖准备，干净环境没有 pytest | `PLAN.md` 顺序缺陷 | 在失败测试前增加 Python 3.11/pytest 前置检查与安装步骤；环境错误不得算 RED |
| PATH 中 `python` 实际为 3.9，计划只写 `python` | `PLAN.md` 命令不精确 + 宿主环境差异 | 规定所有命令必须使用项目 `.venv` 的 Python 3.11，并给出 Windows/POSIX 精确命令 |
| Task 1 声明产出 `FeedbackBudget`、`CommandLimits`，却无字段与测试 | `PLAN.md` 接口范围错误 | Task 1 只产出 `HarnessSettings`；其余类型移到实际定义它们的 Task 6/7 |
| 审计提示禁止读取除 SPEC/PLAN 外任何文件，但 Task 要修改 `.env.example`/`.gitignore` | 主 Agent 的冷启动提示过严，不是产品规约缺陷 | 澄清“仅提供 SPEC/PLAN”是初始上下文限制；选定 Task 后可读取其文件清单中的目标文件 |
| 冷启动环境禁止联网且无 pytest | 外部前置条件，不能靠猜测解决 | 依赖安装前请求用户批准；批准后在新隔离 worktree 用全新审计员复验 |

产出与预期的直接差距是：获得了正确的测试文件，但没有取得有效 RED，因此不能进入 GREEN。该结果证明计划初稿尚不足以支持干净环境自主执行。

### 8.3 关键修订前后

```diff
- 产出：HarnessSettings、FeedbackBudget、CommandLimits
+ 产出：HarnessSettings；反馈预算与命令限制分别由 Task 7 与 Task 6 定义

- 步骤 1：创建失败配置测试
+ 步骤 1：用 Python 3.11 创建 .venv，验证并安装 pytest==9.1.1
+ 步骤 2：创建失败配置测试

- 运行：python -m pytest tests/test_config.py -v
+ Windows：& .\.venv\Scripts\python.exe -m pytest tests/test_config.py -v
+ POSIX：.venv/bin/python -m pytest tests/test_config.py -v

- 审计员只能读取 SPEC.md 与 PLAN.md
+ 初始上下文只有 SPEC.md 与 PLAN.md；选定 Task 后可读取该 Task 明列的目标文件
```

### 8.4 当前门禁状态

第一次冷启动已产生有效缺陷证据，但尚未通过：修订后的 Task 1 仍需在获得依赖安装授权后，由另一个全新无历史审计员复验。复验通过并由用户确认前，仍禁止开始正式 Harness 实现。

### 8.5 第二次冷启动复验

用户明确批准在新隔离 worktree 中创建 Python 3.11 `.venv`，并从 PyPI/npm 安装 Task 1 锁定依赖。主 Agent 创建 `codex/cold-start-audit-v2`，启动第二个无历史审计员。该审计员只选择 Task 1，并验证了：

- Python 3.11.9 与 pytest 9.1.1 可用。
- RED 命令精确失败为 `ModuleNotFoundError: No module named 'coding_agent_harness'`，符合计划预期。
- `pip-tools==7.5.3`、Python 锁文件、锁定依赖和 editable install 均成功。
- 没有执行提交、推送或全局安装。

审计员随后在首个非预期错误处暂停：PowerShell 把 `npm` 解析为 `E:\nodejs\npm.ps1`，系统 ExecutionPolicy 禁止脚本运行，因此 `npm --prefix web install --package-lock-only` 退出 1。它没有擅自改用 `npm.cmd`，也没有把未验证实现宣称为 GREEN。

审计员还指出，Task 1 没有指定 Python 构建后端及其精确版本。它为了试验选择 `setuptools>=80`，这是超出计划的猜测，应由计划负责，而不是归咎于执行者。

### 8.6 第二次修订

主 Agent 从 PyPI 官方注册表核对 `pip==26.1.2` 和 `setuptools==83.0.0`，并对 `PLAN.md` 做出以下修订：

```diff
- Windows 与 POSIX 均使用 npm
+ Windows PowerShell 必须显式使用 npm.cmd；POSIX 使用 npm

- 未指定 Python 构建后端
+ [build-system]
+ requires = ["setuptools==83.0.0"]
+ build-backend = "setuptools.build_meta"

- piptools compile --generate-hashes ...
+ piptools compile --generate-hashes --allow-unsafe ...

+ Python 引导工具锁定 pip==26.1.2 与 setuptools==83.0.0
```

第二次复验仍未取得 GREEN。下一步必须从本次修订提交创建第三个全新隔离 worktree，只复验 Task 1 到首次 GREEN；在其通过前，正式实现门禁仍关闭。
