# 智能体工作日志

本日志按时间顺序记录 AI4SE 项目的过程证据。日志中严禁出现凭据或虚构行为。

## 日志条目

### 2026-07-14 14:34 +08:00 — INIT-001

- **任务：** 从 GitHub 仓库初始化本地工作区。
- **Superpowers 技能：** `using-superpowers`。
- **提示与上下文：** 用户提供了 `https://github.com/DRAMAaaaaaa/Coding-Agent-Harness.git`，并且只授权初始化仓库。
- **智能体产出与证据：** 克隆 `origin/main`，确认提交 `d6b7f93`（`Initial commit`）处于干净的跟踪状态。未使用子智能体。
- **人工干预：** 用户在初始 README 中选择确定性反馈闭环作为项目的主要贡献。
- **经验总结：** 由于必需的规约门禁尚未通过，仓库初始化必须与产品实现保持分离。

### 2026-07-14 14:40 +08:00 — GOV-001

- **任务：** 添加初始 `.gitignore` 安全基线。
- **Superpowers 技能：** `using-superpowers`；本次属于仓库治理而非产品行为，因此没有调用 Brainstorming 或 TDD。
- **提示与上下文：** 用户明确要求添加 `.gitignore` 文件。
- **智能体产出与证据：** 添加凭据、本地配置、Harness 状态、日志、Python/Node 缓存、构建产物、IDE 文件和本地容器覆盖配置的忽略规则。`git diff --check` 通过。未使用子智能体。
- **人工干预：** 用户将本次变更范围限定为 `.gitignore`。
- **经验总结：** 在 Provider 集成或本地测试产生可能包含凭据的文件前，应先建立秘密文件排除规则。

### 2026-07-14 14:43 +08:00 — GOV-002

- **任务：** 建立其余实现前流程与安全基线。
- **Superpowers 技能：** `using-superpowers`，并采用 Codex 平台适配规则。
- **提示与上下文：** 用户批准执行计划步骤 1，并询问是否必须使用 Superpowers。
- **智能体产出与证据：** 启用 Codex 多智能体支持；添加仓库协作说明、过程日志结构、行尾与编辑器规则，以及不含凭据的环境变量示例。该治理任务范围明确，不需要委派，因此未使用子智能体。
- **人工干预：** 用户授权步骤 1，但未授权产品实现。
- **经验总结：** 即使治理任务不需要专门的设计或 TDD 技能，Superpowers 仍然是必须遵守的流程门禁。

### 2026-07-14 17:02 +08:00 — SPEC-001

- **任务：** 完成 Superpowers Brainstorming 阶段并编写获得批准的产品规约。
- **Superpowers 技能：** `brainstorming`。
- **提示与上下文：** 用户定义了一个面向程序员、能够直接修改项目并交付可运行代码与文档的编码智能体。对话明确了范围、Provider、审批、记忆边界、反馈预算、WebUI、部署、测试、CI、Docker 和架构。
- **智能体产出与证据：** 在提交 `72c8b23` 中添加 `SPEC.md`、`SPEC_PROCESS.md` 和 `docs/superpowers/specs/2026-07-14-coding-agent-harness-design.md`。提交前，`git diff --cached --check`、占位符扫描和凭据模式扫描均通过。没有生成实现代码或伪造冷启动检查结果。
- **人工干预：** 用户批准每个设计章节和完整设计；把默认计划规则修正为“除非明确跳过，否则先生成计划”；拒绝视觉伴侣；选择事件驱动的可恢复状态机。
- **经验总结：** 显式版本化审批与有界进展检测，可以把模糊的“智能体自主性”转化为确定、可测试的 Harness 行为。在 `PLAN.md` 生成前，冷启动门禁必须保持未完成状态。

### 2026-07-14 17:05 +08:00 — DOC-001

- **任务：** 将仓库协作说明和智能体工作日志改写为中文。
- **Superpowers 技能：** `using-superpowers`；本次为不改变产品设计的治理文档本地化。
- **提示与上下文：** 用户要求把 `AGENTS.md` 和 `AGENT_LOG.md` 重新写为中文。
- **智能体产出与证据：** 中文化两份文档，保留原有流程门禁、安全规则、提交证据、人工决策和经验总结；同步澄清当前仍处于实现前治理阶段。
- **人工干预：** 用户明确选择中文作为两份治理文档的正文语言。
- **经验总结：** 治理文档本地化时必须保留技术标识、命令和提交哈希的原文形式，避免翻译改变约束语义或证据可追溯性。

### 2026-07-14 17:14 +08:00 — GOV-003

- **任务：** 将中文文档与中文提交说明设为仓库长期协作规范。
- **Superpowers 技能：** `using-superpowers`；本次为仓库治理规则调整。
- **提示与上下文：** 用户规定今后的文档和 Git 提交说明应尽量使用中文，并要求把该规定写入 `AGENTS.md`。
- **智能体产出与证据：** 在 `AGENTS.md` 中增加“中文语言规范”，覆盖说明性文档、提交标题与正文、可保留英文的技术内容，以及外部模板强制英文时的处理方式。
- **人工干预：** 用户明确指定中文为后续文档和提交说明的首选语言。
- **经验总结：** 中文优先不应机械翻译标准文件名、命令或代码标识符；保留这些技术原文有助于维持准确性和工具兼容性。

### 2026-07-14 17:47 +08:00 — PLAN-001

- **任务：** 使用已批准规约生成可供子智能体执行的完整实施计划。
- **Superpowers 技能：** `writing-plans`。
- **提示与上下文：** 用户在批准设计并完成治理文档中文化后，指示进入下一步。
- **智能体产出与证据：** 在提交 `0c70462` 中新增自包含的 `PLAN.md`，划分 14 个 Task，记录精确文件、接口、依赖、可并行关系、失败测试、验证命令、两阶段评审和中文提交说明；同步更新 `SPEC.md` 与 `SPEC_PROCESS.md`。自审确认 14 个 Task 和 12 条验收映射完整，无占位符。依赖检查发现 TypeScript 7 与 `typescript-eslint` 不兼容，已改为兼容的 TypeScript 6.0.3。
- **人工干预：** 用户授权进入实施计划阶段，并要求后续文档与提交说明尽量使用中文。
- **经验总结：** 为满足陌生智能体只能读取 `SPEC.md` 与 `PLAN.md` 的冷启动条件，总计划必须自包含；官方注册表的“最新版本”仍需额外核对 peer dependency。

### 2026-07-14 17:47 +08:00 — GOV-004

- **任务：** 为陌生智能体冷启动试验准备隔离 worktree。
- **Superpowers 技能：** `using-git-worktrees`。
- **提示与上下文：** 课程和 `AGENTS.md` 要求正式实现前由无历史上下文的不同类型智能体仅依据 `SPEC.md` 与 `PLAN.md` 试运行 1—2 个 Task。
- **智能体产出与证据：** 检测到当前为普通 Git 检出，且 `.worktrees/` 尚未被忽略；按技能要求先把 `.worktrees/` 加入 `.gitignore`，再创建冷启动隔离分支。
- **人工干预：** 用户指示继续下一步，仓库既有规则明确要求执行该冷启动门禁。
- **经验总结：** 项目内 worktree 必须先由 Git 忽略，否则隔离目录本身会污染主工作区并可能被误提交。

### 2026-07-14 18:04 +08:00 — COLD-001

- **任务：** 由无历史上下文的不同角色智能体首次冷启动试运行 `PLAN.md`。
- **Superpowers 技能：** `using-git-worktrees`；按课程冷启动门禁委派“冷启动实施审计员”。
- **提示与上下文：** 审计员只获得 `SPEC.md`、`PLAN.md` 和隔离 worktree 路径，被要求选择 1—2 个 Task，遇到不确定处立即暂停且禁止联网、提交和推送。
- **智能体产出与证据：** 审计员选择 Task 1 并新增计划要求的 `tests/test_config.py`；运行 RED 命令时发现 PATH 中为 Python 3.9 且无 pytest，因此在生产实现前暂停。它没有把环境错误冒充有效 RED。试验代码只存在于 `codex/cold-start-audit`，未进入主分支。
- **人工干预：** 尚需用户批准在新的隔离 worktree 安装 `pytest==9.1.1` 及 Task 1 锁定依赖，才能完成复验。
- **经验总结：** TDD 计划必须把测试运行时作为 RED 的前置条件；“只提供 SPEC/PLAN”应限制初始上下文，而不能禁止读取选定 Task 明列的目标文件。

### 2026-07-14 18:34 +08:00 — COLD-002

- **任务：** 在获得依赖安装批准后，由第二个全新冷启动审计员复验 Task 1。
- **Superpowers 技能：** `using-git-worktrees`；不同角色子智能体冷启动审计。
- **提示与上下文：** 审计员初始只读 `SPEC.md` 与 `PLAN.md`，选定 Task 后只读其文件清单；允许在 `codex/cold-start-audit-v2` 内联网安装锁定依赖，禁止全局安装、提交和推送。
- **智能体产出与证据：** Python 3.11.9、pytest 9.1.1、预期 RED、Python 哈希锁文件和 editable install 均成功；PowerShell 将 `npm` 解析为受 ExecutionPolicy 阻止的 `npm.ps1`，审计员在该非预期错误处暂停，未取得 GREEN。它同时发现构建后端版本未锁定。
- **人工干预：** 用户明确批准隔离依赖安装；主 Agent 根据审计结果把 Windows 命令改为 `npm.cmd`，并锁定 `pip==26.1.2`、`setuptools==83.0.0` 和构建后端。
- **经验总结：** 跨平台计划不能把 `npm` 视为同一个可执行入口；即使应用依赖已锁定，构建后端和引导工具未锁定仍会迫使陌生执行者猜测。

### 2026-07-14 18:53 +08:00 — COLD-003

- **任务：** 使用第三个全新冷启动审计员验证修订后的 Task 1 能否从零取得有效 GREEN。
- **Superpowers 技能：** `using-git-worktrees`；不同角色子智能体冷启动审计；主 Agent 使用 `verification-before-completion` 独立复验。
- **提示与上下文：** v3 审计员从提交 `b17990f` 的干净 worktree 开始，初始只读 `SPEC.md` 与 `PLAN.md`，仅执行 Task 1 到首次 GREEN；沿用用户对隔离依赖安装的批准。
- **智能体产出与证据：** Python/Node 引导、哈希锁、npm.cmd、预期 RED 和首次 GREEN 均成功；审计员报告 `1 passed in 0.16s`，主 Agent 独立重跑为 `1 passed in 0.09s`。审计分支无提交、无推送，试验代码未进入主分支。
- **人工干预：** 用户批准隔离依赖安装；主 Agent 根据审计建议补充 `--strip-extras`、PowerShell 脚本参数契约和 Windows/Linux 双锁文件策略。
- **经验总结：** 冷启动的价值不在一次成功，而在陌生执行者能否准确区分环境错误、计划缺陷和产品 RED；连续复验把隐性平台假设转成了可执行文字。

### 2026-07-14 18:59 +08:00 — SDD-001

- **任务：** 启动正式 Subagent-Driven Development，并为 Task 1 创建隔离 worktree 与持久进度账本。
- **Superpowers 技能：** `subagent-driven-development`、`using-git-worktrees`。
- **提示与上下文：** 用户选择 Subagent-Driven 方式正式实施下一步；冷启动试验代码不得复用。
- **智能体产出与证据：** 从提交 `b364e19` 创建 `codex/foundation` 与 `.worktrees/foundation`，确认实现前基线干净；把 `.superpowers/` 加入忽略规则，供 SDD 进度账本和任务交接文件使用。
- **人工干预：** 用户明确选择 Subagent-Driven 实施方式。
- **经验总结：** 正式实现必须从干净分支重新执行 TDD；冷启动产物只能作为规约证据，不能成为绕过正式 RED 的实现来源。

### 2026-07-14 19:09 +08:00 — IMPL-001

- **任务：** 由基础子智能体实现 Task 1 的工程骨架、依赖锁定与一键质量门禁。
- **Superpowers 技能：** `test-driven-development`；先创建配置测试并观察到预期 `ModuleNotFoundError`，再写入最小生产实现并取得 GREEN。
- **提示与上下文：** 实现者只使用 Task 1 简报和控制器补充的精确版本上下文，未读取整份 `PLAN.md`，也未查看或复用冷启动 worktree 代码。
- **智能体产出与证据：** 建立 Python `src` 包、`HarnessSettings`、精确 Python/npm 依赖、Windows Python 3.11 哈希锁文件、React/Vite 工作区、`Makefile` 和固定参数契约的 `scripts/test.ps1`；RED 为预期导入失败，GREEN 为 `1 passed`，PowerShell `Unit`/`All` 、Ruff、mypy、pytest、ESLint 和 TypeScript 检查均退出 0。
- **人工干预：** 控制器在实现者报告简报缺少精确依赖版本后，补充 `.superpowers/sdd/task-1-context.md`；用户已批准在本 worktree 的 `.venv` 与 `web/node_modules` 中安装锁定依赖。
- **经验总结：** 在精确版本缺失时暂停猜测并请求有界上下文，可以在不扩大任务阅读范围的前提下维持可重现依赖；当前 Windows 主机未安装 GNU Make，因此 Makefile 只完成静态核对，PowerShell 实际入口已完整运行。

### 2026-07-14 19:31 +08:00 — REVIEW-001

- **任务：** 根据 Task 1 首轮规约与代码质量评审结果，修复全部 Important 问题并进入待复审状态。
- **Superpowers 技能：** `receiving-code-review`、`test-driven-development`、`verification-before-completion`；先核对反馈与现有文件，再执行纠正性 RED—GREEN 和完整验证。
- **评审发现：** 提交 `0aa862c` 的 `web/package.json` 及根锁依赖缺少 Vitest、Testing Library、jsdom 和 Playwright 六项精确版本；`tests/test_config.py` 只验证默认值，未保护五个整数字段的 `ge=1` 约束。首轮评审未通过，本条不将 Task 1 标记为完成。
- **纠正性 TDD 证据：** 在工作树临时移除五个 `ge=1` 后新增参数化测试；`python -m pytest tests/test_config.py -v` 以五个 `DID NOT RAISE ValidationError` 得到 `5 failed, 1 passed`。恢复最小 `ge=1` 实现后，同一命令得到 `6 passed`。
- **修复与提交：** 提交 `93863de` （`fix: 补齐基础依赖与配置边界测试（基础子智能体）`）补齐六项 npm 精确依赖与根锁文件，并增加五个零值拒绝回归用例；未提前添加 Vitest/E2E 脚本或伪能力。
- **验证证据：** `.venv` Python 的目标和全量 pytest 均为 `6 passed`，Ruff、mypy、`pip check`、`npm.cmd --prefix web ci`、`npm ls --depth=0`、ESLint、TypeScript 及 `scripts/test.ps1` 的 Unit/All 均退出 0，npm 报告 `found 0 vulnerabilities`。
- **平台与流程偏差：** 当前 Windows 主机仍未安装 GNU Make，因此未伪造 `make` 运行结果；当前平台的 `spawn_agent` 接口不提供 `model` 参数，无法显式指定不同模型，因此只能依靠新鲜子智能体与有界任务简报实现角色隔离，这一偏差已如实保留。
- **经验总结：** “尚未加入测试命令”不等于“依赖可从锁文件省略”；预算字段的默认值测试也不能代替边界拒绝测试。当前状态是待复审，只有后续两阶段评审通过后才可标记完成。

### 2026-07-14 19:45 +08:00 — REVIEW-002

- **任务：** 完成 Task 1 的规格符合性复审与代码质量复审，并正式关闭任务。
- **Superpowers 技能：** `subagent-driven-development`、`requesting-code-review`、`verification-before-completion`。
- **评审范围：** 从任务开始提交 `9fd2d2e` 到书面回填提交 `4325ecf`；复审材料包含任务简报、补充上下文、实现报告与完整差异包。
- **智能体产出与证据：** 新鲜评审子智能体确认首轮 3 个 Important 均已关闭：Web 测试依赖及根锁文件版本齐全，五个预算整数均有零值拒绝回归测试，`PLAN.md` 与 `AGENT_LOG.md` 状态和证据一致。规格符合性结论为通过，代码质量结论为批准；未发现新的 Critical、Important 或 Minor 问题。
- **环境限制：** 当前 Windows 主机仍未安装 GNU Make，因此不伪造 `make` 执行证据；等价的 PowerShell 一键入口及其所调用的 Python、Node 质量门禁已有新鲜成功输出，该限制不阻塞 Task 1 复审。
- **人工干预：** 无新增人工决策；用户已要求以 Subagent-Driven 方式连续推进。
- **经验总结：** 任务状态只能在修复提交、完整验证和独立复审三者全部完成后从“待复审”改为“完成”；环境中缺少可选入口时应明确记录限制，并以实际执行的等价入口作为证据。

### 2026-07-14 21:10 +08:00 — IMPL-002

- **任务：** 由核心契约子智能体实现 Task 2 的领域模型、可注入 Provider 与严格动作解析。
- **Superpowers 技能：** `test-driven-development`、`verification-before-completion`；先固化失败契约并观察产品模块缺失，再写最小实现、重构并运行完整门禁。
- **提示与上下文：** 实现者只读取 Task 2 简报、控制器补充上下文和相关技能文件，未读取整份 `SPEC.md` 或 `PLAN.md`；Task 1 已提供 Python 3.11 虚拟环境与锁定依赖。
- **RED 证据：** 宿主默认 `python` 首次解析到 Python 3.9 且缺少 pytest，该环境错误未计为 RED；改用仓库 `.venv` 后，目标命令收集阶段分别以 `coding_agent_harness.domain`、`providers`、`agent` 不存在产生 3 个预期错误。失败测试提交为 `80d6175`。
- **GREEN 与实现：** 提交 `326a4b6`（`功能：建立领域契约和可注入模型接口（核心契约子智能体）`）新增 14 状态字符串枚举、严格冻结动作/任务/事件/LLM 契约、异步 Provider `Protocol`、确定性 Scripted Mock、单次 OpenAI-compatible HTTP 适配器及无副作用动作解析器；DeepSeek/Qwen 均只通过注入配置区分，测试只使用 `httpx.MockTransport`。
- **验证证据：** 目标 pytest 为 `28 passed`，全量 pytest 为 `34 passed`；Ruff、mypy（9 个源文件）、`pip check` 均退出 0；`scripts/test.ps1 -Mode Unit` 为 `34 passed`。简报原样命令 `-Suite Unit` 也退出 0，但由于脚本参数实际名为 `Mode`，它走了默认 All 并额外通过 ESLint 与 TypeScript 检查，未将其误记为 Unit 证据。
- **安全与范围：** 未使用高层 agent runner、未真实联网、未记录真实凭据；Provider 错误仅暴露固定 `kind`/`retryable` 与脱敏文本，不保留原始响应、请求头或网络异常对象；未实现 Agent 循环、工具执行、状态存储或后续任务能力。
- **人工干预：** 控制器补充了 Task 2 的冻结状态集合、最小 Task/TaskEvent 约束和错误分类边界；用户重申每个 Task 完成后必须有明确提交，未新增接口选择。
- **经验总结：** 环境失败不能冒充产品 RED；PowerShell 调用参数即使退出 0，也必须核对实际执行分支。当前 Task 2 状态为待复审，只有规约符合性与代码质量两阶段评审通过后才能标记完成。

### 2026-07-14 21:37 +08:00 — REVIEW-003

- **任务：** 修复 Task 2 首轮评审发现的 OpenAI-compatible 自动重定向请求边界问题，并回到待复审状态。
- **Superpowers 技能：** `receiving-code-review`、`test-driven-development`、`verification-before-completion`；先核对 httpx 0.28.1 与当前调用行为，再执行纠正性 RED—GREEN 和完整验证。
- **评审发现：** 注入的 `httpx.AsyncClient(follow_redirects=True)` 会被当前 `post` 默认继承；收到 307 时 Provider 会发送第二次实际 HTTP 请求，违反“一次 `/chat/completions` HTTP 请求”契约。首轮评审不通过，本条不将 Task 2 标记为完成。
- **纠正性 TDD 证据：** 新增回归测试让 `MockTransport` 首次返回带 `Location` 的 307，并在第二次 handler 调用时明确失败；未改生产代码时单测得到 `1 failed`，失败信息为 `provider followed redirect; request count=2`，第二次 URL 为 `https://provider.example/redirected`。在该次 `post` 显式传入 `follow_redirects=False` 后，同一单测得到 `1 passed`，并断言 307 分类为 `ProviderError(kind="http_status", retryable=False)`。
- **修复与提交：** 提交 `3d9cea0`（`fix: 禁止 Provider 自动跟随重定向（核心契约子智能体）`）只修改 Provider 单次请求参数和对应回归测试，没有扩大到重试、Agent 循环或其他能力。
- **验证证据：** Provider 测试为 `16 passed`，Task 2 目标测试为 `29 passed`，全量 pytest 为 `35 passed`；Ruff、mypy（9 个源文件）、`pip check` 均退出 0；`scripts/test.ps1 -Mode Unit` 为 `35 passed`。
- **书面一致性：** `PLAN.md` 总表 Task 2 已由“进行中（实现子智能体）”修正为“待复审”，任务状态行已回填修复提交；`.superpowers/sdd/task-2-report.md` 保留首轮证据并追加本次评审修复证据。
- **人工干预：** 控制器转达并预先验证了首轮评审技术反馈，明确要求以纠正性 TDD 修复；没有新增接口或范围选择。
- **经验总结：** “调用一次 `client.post`”不等于“只产生一次传输”；可注入客户端的默认重定向策略必须在安全边界调用点显式覆盖。当前状态仍为待复审，须经后续两阶段复审才能完成。

### 2026-07-14 21:53 +08:00 — REVIEW-004

- **任务：** 完成 Task 2 修复后的规格符合性复审、代码质量复审和控制器独立验证，并正式关闭任务。
- **Superpowers 技能：** `subagent-driven-development`、`requesting-code-review`、`verification-before-completion`。
- **评审范围：** 原任务基线 `f85f2b2` 到修复书面提交 `63ad107`；更新后的评审包包含 5 笔提交的顺序、文件统计和完整统一差异。
- **复审结论：** 同一评审子智能体确认 `follow_redirects=False` 与 307 回归测试关闭了首轮 Important：即使注入客户端默认跟随重定向，Provider 仍只产生一次传输，并把 307 分类为不可重试 `http_status`。规格符合性为 Pass，代码质量为 Approved；没有新的 Critical、Important 或 Minor。
- **控制器新鲜验证：** `.venv` 中 Provider 目标测试为 `16 passed`；Ruff 为 `All checks passed!`；mypy 为 9 个源文件无问题；`pip check` 为 `No broken requirements found.`；`scripts/test.ps1 -Mode All` 收集 35 项并全部通过，同时 Web ESLint 和 TypeScript 检查退出 0。全部命令于本条记录前实际运行成功。
- **提交规则：** 用户要求每个 Task 完成后由控制器创建一次明确提交；Task 2 的最终完成状态、复审结论和验证证据在本提交中固化，实际哈希将在后续进度记录中引用。
- **人工干预：** 用户只补充逐 Task 提交规则，没有改变 Task 2 技术接口或安全边界。
- **经验总结：** 完成提交应位于实现、纠正性 TDD、完整验证和独立复审之后，作为可查阅、可回退的任务边界；提交自身无法预先记录自己的哈希，因此后续任务账本负责引用其实际值。

### 2026-07-14 22:12 +08:00 — SDD-002

- **任务：** 在独立 worktree 中启动 Task 3 的 SQLite 事件存储、任务仓储与可恢复状态机实现。
- **Superpowers 技能：** `subagent-driven-development`、`using-git-worktrees`、`test-driven-development`。
- **隔离环境：** 从提交 `04083df` 创建 `codex/event-state` 与 `E:\Coding Agent Harness\.worktrees\event-state`；根仓库的 `.worktrees/` 忽略规则已由 `git check-ignore` 验证。
- **依赖与基线：** 使用 Python 3.11 在新 worktree 的 `.venv` 中安装 Windows 哈希锁文件及 editable 项目，使用 `npm.cmd --prefix web ci` 安装根锁依赖，npm 报告 0 个漏洞；`pip check` 无损坏依赖，`scripts/test.ps1 -Mode All` 得到 35 项测试全通过，Ruff、mypy、ESLint 和 TypeScript 均退出 0。
- **提示与上下文：** Task 3 实现者只获得 Task 3 简报、控制器补充的存储/状态机契约和 TDD 技能，不读取整份 `PLAN.md` 或 `SPEC.md`；Task 2 的冻结模型作为输入接口。
- **人工干预：** 用户要求继续 Task 3，并保持逐 Task worktree、TDD、双阶段复审、中文提交、完成后合并与推送审批等既有要求不变。
- **经验总结：** worktree 隔离不会自动共享被忽略的虚拟环境和 Node 依赖；必须在新分支取得可证明的基线 GREEN 后，才能把后续失败认定为 Task 3 的产品 RED。

### 2026-07-14 22:50 +08:00 — IMPL-003

- **任务：** 由状态存储子智能体实现 Task 3 的 SQLite 事件存储、任务仓储、合法状态机与安全恢复。
- **Superpowers 技能：** `test-driven-development`、`verification-before-completion`；先创建 Task 3 测试并观察产品模块缺失，再写最小实现、重构、进行规约与代码质量自审并运行完整门禁。
- **提示与上下文：** 实现者只完整读取 Task 3 简报、控制器补充上下文和两项指定技能，未读取整份 `SPEC.md` 或 `PLAN.md`；实现基线为 `5cc4ccfcfcc746a92337a8362a5683c6107e9d60`，只消费 Task 2 冻结模型。
- **RED 证据：** 宿主默认 `python` 首次解析到 Python 3.9 且缺少 pytest，该环境错误未计为 RED；改用仓库 Python 3.11 `.venv` 后，目标命令在收集阶段因 `coding_agent_harness.storage` 与 `agent.state_machine` 缺失产生 3 个预期错误。失败测试提交为 `5b7da3cb4a58cc6fba14950aceda6f6d1425ff3c`。
- **GREEN 与实现：** 提交 `2f010b3551f1bc33c5e7e1f19cf6b47dae56c128`（`功能：实现事件存储和可恢复状态机（状态存储子智能体）`）新增固定包内幂等迁移、每连接 WAL/外键/busy timeout、可关闭数据库、参数化任务 CRUD、事务内乐观事件序号、同连接与双连接竞争控制、完整合法迁移表和不确定工具副作用恢复；为确保迁移 SQL 随 Python 包分发，仅最小增加 setuptools package-data 配置。
- **评审结论：** 规约自审确认 11 张表、事件先落盘、陈旧序号与约束失败均回滚、恢复不返回或重发动作；代码质量自审确认迁移路径固定、数据值均参数绑定、JSON 确定性序列化、连接幂等关闭。静态检查发现的 3 处 `aiosqlite.Row` 类型契约问题已在提交前修正；当前状态仍为待独立复审，不提前标记完成。
- **验证证据：** Task 3 目标 pytest 为 `61 passed`，全量 pytest 为 `96 passed`；Ruff、mypy（13 个源文件）、`pip check` 均退出 0；`scripts/test.ps1 -Mode All` 也收集并通过 96 项测试，同时 Web ESLint 与 TypeScript 检查退出 0。
- **人工干预与环境偏差：** 控制器在前一替代实例未产出文件或提交后重新派发实现者，没有改变技术范围。PowerShell 首次直接运行脚本被系统执行策略拦截，随后使用仅作用于该进程的 `-ExecutionPolicy Bypass` 成功运行同一脚本，未修改系统策略；未发生真实联网或凭据暴露。
- **经验总结：** 环境失败不能冒充产品 RED；跨 SQLite 连接的乐观并发必须依靠 `BEGIN IMMEDIATE` 与有界 busy timeout 让竞争者在取得锁后重新核对序号，才能稳定收敛为一个成功和一个领域级 `ConcurrencyError`。

### 2026-07-14 23:14 +08:00 — REVIEW-005

- **任务：** 修复 Task 3 首轮评审发现的 SQLite 锁竞争异常泄漏和同连接读写插队问题，并回到待复审状态。
- **Superpowers 技能：** `receiving-code-review`、`test-driven-development`、`verification-before-completion`；先逐项核对评审与当前实现，再执行纠正性 RED—GREEN 和完整验证。
- **评审发现：** `BEGIN IMMEDIATE` 在 busy timeout 到期时会泄漏 `sqlite3.OperationalError`；`TaskRepository.get`、`EventStore.list_for_task` 与 `Database.close` 未使用写锁，可能在同连接未提交事务中插队。两个 Important 使首轮评审不通过；另有可空 deadline 往返与业务表严格集合两项 Minor 测试缺口。
- **纠正性 TDD 证据：** 新增无 sleep 的显式持锁测试，把第二连接 `busy_timeout` 设为 0；旧实现准确泄漏 `sqlite3.OperationalError: database is locked`。使用 `asyncio.Event` 和可观测锁并以 `FIRST_COMPLETED` 调度读写交错，旧实现的任务读取、事件读取和关闭均在锁竞争事件前完成。存储测试 RED 为 `4 failed, 13 passed`；两个 Minor 断言在旧实现已通过。
- **修复与提交：** 提交 `ec28b1b4f6d4ccdd6846e96dc2ea078842450d1a`（`fix: 稳定存储竞争并串行连接操作（状态存储子智能体）`）仅将 SQLite BUSY/LOCKED 及扩展错误码的基础码转换为固定文本 `ConcurrencyError`，其他 `OperationalError` 原样传播；把原 `_write_lock` 提升为连接级 `operation_lock`，覆盖 append/list/create/get/update/close 的完整数据库生命周期。异常路径仍先 rollback，不增加 sleep 或重试。
- **GREEN 与验证证据：** 存储测试为 `17 passed`，Task 3 目标测试为 `67 passed`，全量 pytest 为 `102 passed`；Ruff、mypy（13 个源文件）、`pip check` 均退出 0；`scripts/test.ps1 -Mode All` 再次通过 102 项测试、Web ESLint 和 TypeScript 检查。
- **安全与边界：** 领域竞争异常固定为 `SQLite 写入竞争` 并使用 `from None`，不携带 SQL、任务数据或底层异常链；非 BUSY/LOCKED 的 “no such table” 回归测试确认不会误分类。并发测试只使用事件和任务调度，不依赖 wall-clock sleep；未真实联网或接触凭据。
- **人工干预：** 控制器已独立核对四项评审反馈成立并限定修复范围；没有新增接口选择或范围扩张。
- **经验总结：** 同一 aiosqlite 连接的串行 worker 不等于事务隔离：若方法只锁写入，读请求仍能排进未提交事务并看到脏数据；连接级操作锁必须覆盖 execute、fetch、commit/rollback 和 close 的完整生命周期。

### 2026-07-14 23:27 +08:00 — REVIEW-006

- **任务：** 完成 Task 3 修复后的规格符合性复审、代码质量复审、控制器独立验证与分发包检查，并正式关闭任务。
- **Superpowers 技能：** `subagent-driven-development`、`requesting-code-review`、`verification-before-completion`。
- **复审范围与结论：** 原实现派发基线 `5cc4ccf` 到修复书面提交 `7d8d462`；同一评审子智能体确认首轮两个 Important 与两个 Minor 全部关闭。规格符合性为 Pass，代码质量为 Approved；未发现新的 Critical、Important 或 Minor，允许 Task 3 完成。
- **控制器新鲜验证：** Task 3 目标测试为 `67 passed`；Ruff 为 `All checks passed!`；mypy 为 13 个源文件无问题；`pip check` 无损坏依赖；`scripts/test.ps1 -Mode All` 收集并通过 102 项测试，同时 Web ESLint 和 TypeScript 检查退出 0。
- **分发检查：** 使用 `python -m build --wheel --sdist` 成功构建 `coding_agent_harness-0.1.0-py3-none-any.whl` 与 `coding_agent_harness-0.1.0.tar.gz`；逐个检查归档，两者均且仅包含 1 个 `coding_agent_harness/storage/migrations/001_initial.sql` 条目。
- **提交规则：** 用户要求每个 Task 完成后创建明确提交；Task 3 的完成状态、复审结论与新鲜证据由本提交固化，实际哈希将在后续集成或进度记录中引用。
- **人工干预：** 用户要求继续 Task 3 并保持既有要求不变；没有新增技术接口选择。分支合并到 `p1` 与远程 push 仍作为独立集成动作处理，其中 push 必须取得明确批准。
- **经验总结：** 存储任务的完成证据不仅包括单元测试，还应验证迁移资源确实进入 wheel 与 sdist；否则源码树中的迁移成功不能证明安装后可用。

### 2026-07-15 00:46 +08:00 — SDD-003

- **任务：** 在独立 worktree 中启动 Task 4 的路径围栏、统一脱敏、确定性策略与版本化审批实现。
- **Superpowers 技能：** `subagent-driven-development`、`using-git-worktrees`、`test-driven-development`。
- **隔离环境：** 用户已把 `p1` 的 Task 1—3 历史推送到远程；控制器确认本地与 `origin/p1` 同为 `3861613` 后，从该提交创建 `codex/governance` 与 `E:\Coding Agent Harness\.worktrees\governance`。
- **依赖与基线：** 在新 worktree 中使用 Windows 哈希锁文件重建 Python 3.11 `.venv`，使用 `npm.cmd --prefix web ci` 安装根锁依赖；npm 报告 0 个漏洞。`pip check` 通过，`scripts/test.ps1 -Mode All` 得到 102 项测试全通过，Ruff、mypy、ESLint、TypeScript 均退出 0。
- **计划依赖修正：** Task 4 原文声称消费 Task 3 审批仓储，但 Task 3 实际只交付最小 `approvals` 表，没有审批仓储或版本化列。为遵守 SQLite 持久审批规约，Task 4 文件清单增加 `002_governance_approvals.sql`，并最小修改 `Database.open` 与 `001_initial.sql`，使用 `PRAGMA user_version` 幂等顺序升级；审批仓储仍封装在 `governance/approvals.py`，不扩展后续 API。
- **人工干预：** 用户要求在已推送 Task 1—3 后继续执行，其他 TDD、双阶段复审、中文提交、逐 Task 完成提交和 push 审批要求保持不变。
- **经验总结：** 当计划声称消费的底层接口并未实际交付时，应在实现前把必要的最小持久化演进写回计划；用内存替身掩盖缺口会破坏崩溃恢复和审批重放防护。

### 2026-07-15 01:10 +08:00 — IMPL-004

- **任务：** 由治理子智能体实现 Task 4 的路径围栏、统一脱敏、确定性策略、SQLite 版本化迁移与一次性审批。
- **Superpowers 技能：** `test-driven-development`、`verification-before-completion`；实现者只完整读取 Task 4 简报、控制器补充上下文、指定技能与 implementer 模板，未读取整份 `SPEC.md` 或 `PLAN.md`。
- **RED 证据：** 宿主默认 `python` 首次解析到 Python 3.9 且缺少 pytest，该环境错误未计为 RED；改用工作树 `.venv` 的 Python 3.11 后，`python -m pytest tests/governance -v` 在收集阶段因 `coding_agent_harness.governance` 不存在产生 4 个预期错误。四个治理测试文件的独立 RED 提交为 `5a2b8cb`。
- **实现与迁移：** 提交 `c14d50d`（`安全：实现路径围栏和版本化审批（治理子智能体）`）新增基于 `Path.resolve`/`Path.is_relative_to` 的路径围栏、递归 JSON 脱敏副本、固定次序精确 token 策略、`PRAGMA user_version` 001→002 迁移，以及复用 `operation_lock + BEGIN IMMEDIATE` 的 SQLite 审批管理器。旧 v1 审批被保留为拒绝、已消费、已过期的 legacy 记录；审批绑定动作、事件序号、规范化范围、任务状态和配置版本，消费后持久拒绝重放。
- **纠正性 TDD：** GREEN 后自审新增 JSON 引号密钥、Shell `git push`、任务落盘取消、SQLite BUSY、pending/not-found 区分等回归，旧实现得到 `5 failed, 7 passed`；补强后又用命令包装器和缺失参数用例得到 `6 failed, 2 passed`。最小修复覆盖带引号赋值、Shell 包装器精确 token、落盘取消检查与固定领域错误。最终门禁还捕获 `read_file` 五类路径字段优先级回归（4 failed），修正为至少一个受围栏字段后恢复 GREEN。
- **验证证据：** 最新治理目标为 `68 passed, 1 skipped`；`pip check` 无损坏依赖；`scripts/test.ps1 -Mode All` 收集 171 项并得到 `170 passed, 1 skipped`，Ruff、mypy、Web ESLint 和 TypeScript 均退出 0。唯一跳过项是当前 Windows 账户不能创建目录符号链接；路径穿越、同前缀兄弟目录、非既有尾部和 Windows 大小写核心用例均实际通过。首次直接调用 PowerShell 脚本被系统执行策略阻止，随后使用仅当前进程生效的 `-ExecutionPolicy Bypass` 成功执行同一脚本。
- **分发检查：** `python -m build --wheel --sdist` 成功构建 wheel 与 sdist；逐项检查归档，`001_initial.sql` 和 `002_governance_approvals.sql` 在两种产物中都各恰好出现一次。
- **安全与范围：** 未真实联网、未使用真实凭据、未使用 sleep 竞争或高层 Agent runner；真实 Provider 的 LLM 授权与工具网络规则完全分离，伪造 `provider_authorized` 不能绕过。未实现工具执行、Workspace 扫描、反馈、记忆、Agent 主循环或 Web API。
- **人工干预：** 控制器在各安全检查点询问材料读取、RED/GREEN、静态门禁和分发状态，未改变冻结接口或安全语义。
- **经验总结：** 安全规则不仅要识别直接命令，还必须用精确 token 覆盖 `sudo`、`python -m` 与 Shell 解释器包装；完成前新鲜全门禁能够发现局部测试未暴露的规则优先级回归。当前 Task 4 仅标为待复审，须先后通过独立规约符合性审查和代码质量审查。

### 2026-07-15 01:35 +08:00 — REVIEW-007

- **任务：** 修复 Task 4 首轮规格符合性与代码质量评审提出的治理绕过、审批异常泄漏、恶意异常脱敏、环境变量名边界和 legacy 证明缺口；修复后保持待复审。
- **Superpowers 技能：** `receiving-code-review`、`test-driven-development`、`verification-before-completion`；先逐项核对评审意见与当前代码，再按 Critical→Important→Minor 分组执行纠正性 RED—GREEN。
- **首轮评审结论：** Spec Fail / Changes requested。Critical 为策略仅依赖相邻 token 且未覆盖直接/字段网络动作；Important 为审批公开边界泄漏 FK/CHECK、非法输入及非锁 SQLite 异常，以及恶意异常 `__str__` 二次失败；Minor 为环境名无标识符/平台大小写语义和 legacy 仅查字段未通过公开管理器证明。由于独立双阶段复审未通过，`PLAN.md` 步骤 6 恢复为未完成。
- **纠正性 TDD A：** 新增 `git -C . push`、带全局选项的 pip/docker、`npm.cmd`/`pnpm.cmd`、直接 curl、未知工具 `url/uri`、授权伪造和安全反例。旧实现得到 `11 failed, 4 passed`；最小修复统一剥离 `.exe/.cmd/.bat/.com/.ps1`，对已知命令保守扫描后续精确 operation，并显式分类工具名和网络字段，A 组转为 `15 passed`、完整策略转为 `56 passed`。随后直接 `git.cmd` operation 未进入 scope 的回归先 `1 failed`，修复后 `1 passed`。
- **纠正性 TDD B：** 不存在 task、六类越界上下文、构造绕过、非法决定/actor/time 与非锁 SQLite 异常在旧实现共 `10 failed`，真实泄漏 `FOREIGN KEY constraint failed`、`CHECK constraint failed`、`ValueError` 和 `no such table`。修复后增加有界冻结字段与 `INVALID_CONTEXT/INVALID_DECISION/INVALID_TIME/STORAGE_ERROR`，不存在 task 固定 `NOT_FOUND`，公开数据库错误使用 `from None`；B 组 `10 passed`、审批文件 `24 passed`。BUSY/DUPLICATE 语义未改变，普通 `Exception` 与控制流 `BaseException` 分支明确分离。
- **纠正性 TDD C/D/E：** 恶意异常 `__str__` 用例旧实现 `1 failed` 并传播含秘密二次异常，修复后固定消息并使脱敏文件先达 `8 passed`；环境名前缀/Windows 大小写用例旧实现 `2 failed`，改用 Unicode 标识符边界、Windows 不敏感/POSIX 敏感后脱敏文件 `10 passed`。UUID 旧审批 + 非取消 active task 的公开 `consume` 在旧实现已固定拒绝，因此 E 如实记录为 characterization `1 passed`，未伪造 RED。
- **修复提交：** `269c1ae`（`fix: 封堵治理绕过并稳定审批错误（治理子智能体）`）只修改 Task 4 三个治理模块及对应测试，不实现工具执行、扫描、反馈、记忆、Agent 循环或 Web API。
- **最终验证：** 治理目标 `97 passed, 1 skipped`；全量 pytest `199 passed, 1 skipped`；Ruff、mypy（17 个源文件）、`pip check`、`git diff --check` 均通过。`scripts/test.ps1 -Mode All` 收集 200 项并得到 `199 passed, 1 skipped`，Web ESLint 与 TypeScript 均通过。唯一 skip 仍是当前 Windows 账户不能创建目录符号链接的单一 OS 能力用例。
- **分发检查：** wheel/sdist 重建成功；逐项检查归档，`001_initial.sql` 与 `002_governance_approvals.sql` 在两种产物中均各恰好一份。
- **人工干预：** 控制器已按 `receiving-code-review` 独立验证评审成立并给出完整修复边界；未新增技术选择，未要求或发生真实网络与凭据操作。
- **经验总结：** 安全策略不能把 argv 邻接当作语法保证；已知命令的全局选项和 Windows 启动器必须在不执行字符串的前提下规范化。公开审批边界也必须把所有可预期输入/存储失败收敛为不含 SQL 或业务值的固定领域错误。Task 4 当前仍待独立复审，不提前勾选步骤 6。
### 2026-07-15 11:47 +08:00 — GOV-005

- **任务：** 按替换后的 `AGENTS.md` 重新执行 `SPEC.md` 最终复核与实施计划自审门禁。
- **Superpowers 技能：** `using-superpowers`、`brainstorming`、`writing-plans`。
- **提示与上下文：** 新规则把当前阶段重置为等待 `SPEC.md` 最终批准，即使仓库已有计划、冷启动和 Task 1—4 历史，也禁止继续新增 Harness 实现。主 Agent 因此暂停 `codex/governance`，只读核对文件与 Git 状态，并请用户明确批准。
- **人工干预：** 用户回复“允许”，再次批准当前 `SPEC.md`；该回复只解除规约复核门禁，不跳过计划自审和陌生智能体冷启动。
- **计划产出：** 保留原 14 Task 架构，回填 Task 3 完成哈希，并把 Task 4 二轮评审发现转为精确的纠正性 RED—GREEN：包管理器安装别名、解释器全局选项/编码命令、畸形网络字段、普通参数误判，以及迁移协调器必须在写锁内重读版本的双连接测试。
- **安全与范围：** 本阶段未修改产品实现、未安装依赖、未联网、未推送，也未读取或输出任何凭据。
- **经验总结：** 当最新仓库规则重置阶段门禁时，历史完成事实不能代替新的明确批准；但计划应做增量自审，避免无意义重写已经通过冷启动验证的部分。

### 2026-07-15 12:20 +08:00 — COLD-004

- **任务：** 由第四个无历史上下文的陌生智能体仅依据 `SPEC.md` 与 `PLAN.md` 复核 Task 4，并用 Task 5 检查相邻接口。
- **Superpowers 技能：** `using-git-worktrees`、`receiving-code-review`；冷启动智能体没有读取过程文档、Git 历史、其他 worktree 或主对话。
- **隔离与基线：** 从 `38e605f` 创建 `codex/cold-start-audit-v4`；复用既有 Python 3.11 依赖但强制从审计工作树导入，pytest 基线为 `102 passed`，没有安装依赖或联网。
- **审计结论：** Fail。阻塞项为当前 RED 起点不真实、接口未冻结、迁移状态机/并发证明不唯一、包管理器与解释器包装器缺口、虚构工具名、Task 5 并行边界，以及工作区外访问审批与普通工具围栏语义冲突。
- **人工干预：** 用户批准采用宿主受控导入/导出：普通工具越界固定拒绝，审批只授权精确的一次性文件复制，不提升 Agent 工具能力。
- **计划修订：** 把步骤 1—5 标为历史证据，当前返工从步骤 6 的纠正性 RED 开始；冻结治理/审批签名、迁移锁内状态机和原子消费；补充 SQL 次序替身、双连接集成、包装器矩阵与安全反例，并拆清 Task 5 的可并行部分。
- **安全与范围：** 未修改产品实现、未执行测试命令字符串、未联网、未推送、未接触凭据。修订计划仍须由新的陌生智能体复验，当前门禁保持关闭。

### 2026-07-15 12:38 +08:00 — COLD-005

- **任务：** 由第五个无历史上下文智能体仅依据 `SPEC.md` 与 `PLAN.md` 复核 Task 4 与 Task 11 的治理—宿主传输边界。
- **隔离与基线：** 从 `9d97513` 创建 `codex/cold-start-audit-v5`；Python 基线 `102 passed`，未安装依赖或联网。
- **审计结论：** Fail。Task 4 的纠正性起点已明确，但 `HostTransfer` 没有持久模型与冻结服务契约，审批消费和文件复制无法原子完成，崩溃后存在丢失或重放歧义；路径字段矩阵、包装器语法、审批权威状态和迁移细节仍不够唯一。
- **计划修订：** 新增 `003_host_transfers.sql`、`TransferRecord/HostTransferService`、状态机与 ID 语义；审批消费和传输 `EXECUTING` 在同一事务绑定，文件采用临时写、fsync、原子替换，任何不确定副作用恢复为 `UNCERTAIN` 且不自动重试。补充逐工具越界矩阵、包装器语法表、条件更新、迁移 busy 与 legacy 固定值。
- **安全与范围：** 审计员未读取禁区材料；本轮仍只修改规约和计划，不修改产品实现、不联网、不推送、不接触凭据。门禁保持关闭，等待新审计智能体复验。

### 2026-07-15 12:54 +08:00 — COLD-006

- **任务：** 第六次无历史冷启动复验 Task 4 与 Task 11。
- **结论：** Fail，但主体契约已可执行；剩余 Critical 是 `env -S/--split-string` 的二次命令拆分绕过，以及已有目标缺少完整文件身份导致同内容 inode 替换不失效。
- **修订：** `env -S/--split-string` 固定进入 `HIGH_RISK_SHELL` 并补 RED；HostTransfer 增加 `target_identity`，003、scope 与每次执行校验均绑定完整身份。同步冻结 shell cwd、Windows 解释器名称、003 迁移矩阵和幂等重复请求语义。
- **安全与范围：** 只修改文档计划；没有产品代码、依赖安装、联网、推送或凭据操作。门禁等待新的复验。

### 2026-07-15 13:02 +08:00 — COLD-007

- **任务：** 第七次无历史冷启动复验 Task 4 与 Task 11。
- **结论：** Task 4 可安全启动，但总体 Fail；Task 11 的 workspace/task 身份入口、源父目录身份和 action ID 绑定仍有歧义。
- **修订：** 传输 API 固定接收 `task_id`；记录并绑定 `source_parent_identity`；`action_id` 固定为 `transfer:<transfer_id>`，在 transfer、approval、scope 和 003 唯一约束中保持一致。
- **安全与范围：** 仅修改计划和过程记录，未修改实现、安装依赖、联网或推送。等待新审计智能体复验。

### 2026-07-15 13:09 +08:00 — COLD-008

- **任务：** 第八次无历史冷启动复验 Task 4 与 Task 11。
- **结论：** Pass；无 Critical、无 Important。Task 4 可从步骤 6 的纠正性 RED 立即恢复；Task 11 契约通过但依赖未满足，仍不得提前实施。
- **Minor 处理：** 把三次文件校验明确为 source parent/source/target parent/target 四组身份，并固定临时文件名包含 transfer ID；不扩展范围。
- **安全与范围：** 审计员仅读 `SPEC.md` 与 `PLAN.md`，未修改、联网或读取其他材料。冷启动门禁正式关闭。

### 2026-07-15 20:31 +08:00 — IMPL-004-R2

- **任务：** 从 Task 4 简报步骤 6 恢复二轮评审纠偏，分组修复真实工具路径 schema、命令包装器、版本化迁移并发、审批权威上下文与宿主内部传输边界。
- **Superpowers 技能：** `test-driven-development`、`systematic-debugging`、`verification-before-completion`；实现者只完整读取 Task 4 简报与技能说明，没有重读整份 `SPEC.md`/`PLAN.md`。
- **策略 RED—GREEN：** `fd8bf48` 得到 `21 failed, 8 passed`，精确暴露安装别名、解释器选项、畸形网络字段、路径逃逸可审批和任意 argv 扫描；`ee161ba` 以真实 schema 和命令位置解析转绿，策略文件最终 `90 passed`。
- **迁移 RED—GREEN：** `c893e15` 得到 3 个精确失败；`bde90e0` 恢复 001 原始 blob、把事务/版本管理移到协调器、给 002 增加 task config_version，并以两个真实连接证明 legacy 仅迁移一次。WAL 竞争连续证伪三个局部方案后，按控制器确认调整初始化顺序；双实例回归连续 10 次通过且最终均为 v2/WAL。
- **审批 RED—GREEN：** `3e57b38` 得到 8 个精确失败；`0cc6914` 使五个公开方法在同一写事务读取 tasks state/config 与最大事件序号，并实现条件决定/消费及两个原子数据库回调。两个真实连接的决定和消费均只有一个赢家，回调异常时绑定写入与审批共同回滚。
- **宿主边界 RED—GREEN：** `7f9a078` 得到 `4 failed, 3 passed`；`4bd4075` 只增加 `host_import/host_export` 内部精确审批和脱敏 scope，普通工具仍固定拒绝越界。没有实现 Task 11 服务/API、transfer 持久表或 003 migration。
- **新鲜验证：** focused `128 passed`；governance `144 passed, 1 skipped`；全量 `246 passed, 1 skipped`；Ruff、mypy（17 个源文件）、pip check、PowerShell All、Web ESLint、TypeScript、wheel/sdist 构建及归档内容检查均通过。唯一 skip 为 Windows 符号链接权限。
- **安全与人工干预：** 未执行测试字符串中的命令，未接触凭据、推送、合并或删除工作树。控制器仅确认 WAL 初始化架构调整；未扩大 Task 4 接口范围。
- **经验总结：** 迁移互斥必须先由 SQLite 写锁建立，再做可能引发连接间竞争的持久 journal-mode 切换；busy timeout 不能替代正确的锁获取顺序。当前仍待独立规约符合性与代码质量审查，不宣称评审通过。

### 2026-07-15 21:06 +08:00 — IMPL-004-R3

- **任务：** 修复独立评审追加发现的补丁/命令语法 fail-open、审批任意 callable 副作用边界、调用方状态优先级和宿主动作来源伪造问题。
- **Superpowers 技能：** `receiving-code-review`、`systematic-debugging`、`test-driven-development`、`verification-before-completion`；逐项核对评审事实，按三个独立行为组执行 RED—GREEN，未启动子智能体。
- **策略 RED—GREEN：** `55d504a` 得到 `11 failed, 2 passed`；`12a4328` 支持真实 `*** Move to:`，零合法/畸形补丁头固定拒绝，`command -v/-V` 只在包装器前缀生效，并按包管理器语法消费已知选项值、对未知选项保守审批。聚焦 `13 passed`，策略文件 `103 passed`。
- **审批 RED—GREEN：** `aeb5168` 得到 6 个精确失败；`57f5733` 保留公开 Callable 注解但运行时只接受精确冻结数据库 mutation，管理器自行参数化执行受 approval/task 绑定的 INSERT/UPDATE，任意 callable 不调用且固定 `INVALID_MUTATION`。合法声明与审批创建/消费原子提交，声明 SQL 失败共同回滚；数据库活动而调用方声称取消时返回 `STALE_STATE`。审批文件 `41 passed`。
- **宿主来源 RED—GREEN：** `3996d60` 得到 6 个精确失败；`1927bd0` 增加独立严格 `HostTransferAction` 与 `evaluate_internal`，普通 `evaluate(ToolAction)` 对 `host_import/host_export` 固定 `DENY/INVALID_ACTION`。没有修改 `AgentAction`、LLM schema、工具注册表、Task 6/11 或新增 003 migration。
- **安全与人工干预：** 未执行测试字符串中的命令，未联网、未安装依赖、未接触凭据、未推送或合并。控制器确认受限 mutation 和宿主来源边界的接口方向。
- **新鲜验证：** focused `146 passed`；governance `162 passed, 1 skipped`；全量与 PowerShell All 均为 `264 passed, 1 skipped`。Ruff、mypy（17 个源文件）、pip check、Web ESLint/TypeScript、无隔离 wheel/sdist 构建均通过；两种归档的 001/002 各 1 份、003 为 0。唯一 skip 为本机 Windows 符号链接权限。
- **当前状态：** 纠偏实现与全门禁已完成，仍等待独立规约符合性/代码质量复审；不提前宣称 Task 4 完成。

### 2026-07-15 21:26 +08:00 — IMPL-004-R4

- **任务：** 修复第二轮独立复审发现的审批 mutation 非唯一绑定/命中数缺口，以及 slash 选项被通用路径扫描全局豁免的问题。
- **Superpowers 技能：** `receiving-code-review`、`systematic-debugging`、`test-driven-development`、`verification-before-completion`；先核对实现与反例，再按审批、策略两组独立 RED—GREEN。
- **审批 RED—GREEN：** `4fb248e` 聚焦得到 `5 failed, 2 passed`：仅 TASK_ID/仅 APPROVAL_ID 的 INSERT、仅 TASK_ID 的 UPDATE WHERE、UPDATE 零命中/双命中均错误提交；正确双绑定 INSERT 与单行 UPDATE 已通过。`c28525a` 强制 INSERT values 和 UPDATE WHERE 同时含两项绑定，且 UPDATE `rowcount != 1` 固定 `INVALID_MUTATION`，审批消费和业务更新共同回滚。
- **策略 RED—GREEN：** `00ac97e` 得到 `2 failed, 1 passed`：`echo /s` 错误 ALLOW、`rm /s` 错误进入审批而未先拒绝，合法 cmd 前缀保持通过。`c55c07b` 把 slash 语法限定到实际解包后的 cmd 前缀索引，普通命令的 `/...` 重新作为绝对路径候选围栏。
- **验证插曲：** 审批全文件首次运行中，既有双实例 WAL 用例出现一次 `database is locked`；未修改迁移代码或测试，原命令重跑后 `46 passed`，随后完整 focused/governance/full/PowerShell All 中该用例均通过。
- **新鲜验证：** focused `154 passed`；governance `170 passed, 1 skipped`；全量与 PowerShell All 均为 `272 passed, 1 skipped`。Ruff、mypy（17 个源文件）、pip check、Web ESLint/TypeScript、无隔离 wheel/sdist 构建及归档 001/002 各 1、003 为 0 均通过；唯一 skip 为 Windows 符号链接权限。
- **范围与状态：** 未联网、安装、推送、合并，未实现 Task 6/11、003 migration 或传输服务。第二轮问题已纠偏，仍等待下一轮独立规约符合性与代码质量复审，不宣称 Task 4 完成。

### 2026-07-15 21:46 +08:00 — IMPL-004-R5

- **任务：** 修复第三轮独立复审发现的发布/远程变更命令全局 option 值遮蔽 operation 问题。
- **Superpowers 技能：** `receiving-code-review`、`systematic-debugging`、`test-driven-development`、`verification-before-completion`；核对冻结 reason 与通用 `_operation` 数据流后，执行一组 RED—GREEN。
- **RED：** `8ae3c37` 新增 26 个聚焦案例，旧实现得到 `15 failed, 11 passed`。六个评审反例、pnpm/yarn publish、未知/缺值 option 均暴露 fail-open 或错误 reason；docker 已知 option、三种等号形式及七个安全反例证明既有正常边界。
- **GREEN：** `ab95989` 为 `git/npm/pnpm/yarn/twine/docker/gh` 建立命令专属无值/带值 option 表，统一 `_parse_operation` 支持分离值与非空等号值；package install/publish 复用同一 parser。git 不可靠解析固定 `GIT_REMOTE_CHANGE`，发布命令固定 `PUBLISH`；npm/pnpm/yarn 明示 publish 时由发布 reason 优先，既有未知普通 package option 仍保留 `DEPENDENCY_INSTALL`。
- **新鲜验证：** focused `180 passed`；governance `196 passed, 1 skipped`；全量与 PowerShell All 均为 `298 passed, 1 skipped`。Ruff、mypy（17 个源文件）、pip check、Web ESLint/TypeScript、无隔离 wheel/sdist 构建及归档 001/002 各 1、003 为 0 均通过；唯一 skip 为 Windows 符号链接权限。
- **范围与状态：** 未联网、安装、推送、合并，未实现 Task 6/11、003 migration 或传输服务。第三轮问题已纠偏，仍等待独立规约符合性与代码质量复审，不宣称 Task 4 完成。

### 2026-07-15 22:00 +08:00 — IMPL-004-R6

- **任务：** 修复第四轮独立复审发现的 WAL 切换锁竞争公开错误边界：复查仍非 WAL 时不得泄漏原始 `sqlite3.OperationalError` 文本。
- **Superpowers 技能：** `receiving-code-review`、`systematic-debugging`、`test-driven-development`、`verification-before-completion`；先核对冻结 busy 错误和既有映射函数，再用确定性连接桩执行单组 RED—GREEN。
- **RED：** `71aec0b` 新增三个分支用例；聚焦运行得到 `1 failed, 2 passed`。锁竞争且复查非 WAL 的失败中原样出现桩注入的底层错误文本，另外两条既有边界——复查 WAL 成功、非锁异常保持原样——已通过。
- **GREEN：** `e3d991b` 仅把 `_ensure_wal_mode` 的锁竞争非 WAL 分支交给既有 `_raise_migration_error`，得到固定 `MigrationBusyError("数据库迁移正忙")`；不吞掉非锁型 `OperationalError`，不改变其他迁移顺序或事务逻辑。
- **新鲜验证：** focused `183 passed`；governance `199 passed, 1 skipped`；全量与 PowerShell All 均为 `301 passed, 1 skipped`。Ruff、Mypy（17 个源文件）、`pip check`、Web ESLint/TypeScript、无隔离 wheel/sdist 构建均通过；wheel/sdist 内 001/002 各 1 份、003 为 0。唯一 skip 仍为本机 Windows 符号链接权限。
- **范围与状态：** 未联网、安装、推送、合并，未实现 Task 6/11、003 migration 或传输服务。第四轮问题已纠偏，仍等待独立规约符合性与代码质量复审，不宣称 Task 4 完成。

### 2026-07-15 22:10 +08:00 — REVIEW-004-FINAL

- **任务：** 对 Task 4 从同步基线 `35e89d0` 到实现头 `7b27d38` 的 27 个提交完成最终独立规约符合性审查、代码质量审查和控制器侧新鲜验证。
- **Superpowers 技能：** `subagent-driven-development`、`requesting-code-review`、`receiving-code-review`、`verification-before-completion`；所有 Critical/Important 发现均先复现，再交回实现者按 RED—GREEN 修复并重新生成完整审查包。
- **独立审查：** 第五轮审查无 Critical、Important 或 Minor；`Spec: PASS`，`Quality: APPROVED`。重点复验 WAL 锁竞争固定映射、锁内迁移版本、策略路径与远程操作、受限 mutation 双绑定/单行命中、数据库权威状态和 `HostTransferAction` 来源隔离，均未发现回归。
- **控制器新鲜验证：** `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1 -Mode All` 得到 `301 passed, 1 skipped`，Ruff、mypy（17 个源文件）、Web ESLint 与 TypeScript 均通过；`pip check` 返回 `No broken requirements found.`；无隔离 wheel/sdist 构建成功，两个归档中的 001/002 各 1 份、003 为 0；`git diff --check 35e89d0..HEAD` 退出 0。
- **环境限制：** 唯一 skip 是当前 Windows 账户没有创建测试目录符号链接的权限；其余路径围栏测试已执行。
- **范围与安全：** 未联网、安装依赖、推送、合并或删除工作树；未接触凭据，未实施 Task 6/11、003 migration 或宿主传输服务。
- **结论：** Task 4 的实现、独立双重审查和控制器验证均完成；下一步进入开发分支收尾，是否本地合并回 `p1` 仍需按 Git 安全流程处理。

### 2026-07-16 01:13 +08:00 — IMPL-004-R7

- **任务：** 在 Task 4 已本地合并后修复双实例迁移的 WAL owner–waiter 竞态；不重试迁移 DDL 或 WAL 写入，不增加进程全局锁、锁文件、依赖或 003 migration，并把 Task 4 恢复为待复审。
- **Superpowers 技能：** `test-driven-development`、`systematic-debugging`、`verification-before-completion`，并按 TDD 要求补读 `testing-anti-patterns.md`；先以确定性桩取得 RED，再做最小 GREEN，真实偶发失败出现后立即回到 Phase 1 而未叠加猜测性修复。
- **首轮 RED—GREEN：** `a6a5702` 用可控单调时钟/等待器和分步连接桩覆盖 BUSY→delete→wal、持续 delete 超时、观察查询 BUSY、观察非锁错误及游标关闭；旧实现聚焦为 `5 failed, 1 passed`。`3bf8365` 增加私有有界观察状态机：WAL 成功者为 owner，竞争者为 waiter，只接受精确 `wal`，观察 BUSY 继续、非锁错误原样传播，所有读取游标在 `finally` 关闭，且绝不重试 WAL 写入。
- **失败与系统诊断：** 首轮无插桩真实双连接 50 次复验在第 33 次以 `MigrationBusyError` 超时，故首版 GREEN 未被视为完成。Recording 证明迁移版本游标没有显式 `CLOSE`，但 aiosqlite 与 sqlite3 barrier 对照中关闭/不关闭两组始终至少有一个 WAL owner，证伪其为 no-owner 根因。随后无内部插桩的 legacy v1 复刻 `500/500` 成功；控制器受控阻塞证据进一步确认初始 `PRAGMA journal_mode=WAL` 可约耗时 `5498.8ms` 后才返回 BUSY，首版从尝试前计时会使 waiter 收到 contention 时预算已经耗尽。
- **第二轮 RED—GREEN：** `00a4353` 让初始 WAL 桩先推进 5.5 秒再抛 BUSY，首观察 WAL、次观察 WAL及持续 delete 三项在首版稳定得到 `3 failed`。`cd8f3b5` 只把 5 秒 deadline 的创建移到 lock-contention 分支，使 waiter 从收到 BUSY 时取得完整观察预算；owner 路径、迁移顺序、DDL 次数和 WAL 写入次数均未改变。WAL 聚焦 `6 passed`，审批文件 `52 passed`。
- **集成与新鲜门禁：** 最终无插桩双连接 legacy 迁移复验 `50/50`；governance `202 passed, 1 skipped`，全量 pytest 与 `scripts/test.ps1 -Mode All` 均为 `304 passed, 1 skipped`。Ruff 全通过，mypy 17 个源文件无问题，`pip check` 无破损依赖，Web ESLint/TypeScript 通过；无隔离 wheel/sdist 构建成功，两种归档内 001/002 各 1 份、003 为 0。唯一 skip 仍为本机 Windows 符号链接权限。
- **范围、安全与状态：** 未联网、安装依赖、推送、合并、删除工作树或接触凭据；临时诊断仅在外部进程运行且未写入仓库。纠偏实现和门禁已完成，但原 REVIEW-004-FINAL 结论已被本次合并后回归取代；Task 4 与 PLAN 步骤 7 均恢复待独立规约符合性/代码质量复审，不提前宣称完成。

### 2026-07-16 02:18 +08:00 — IMPL-004-R8

- **任务与审查结论：** 处理合并后独立审查的 `Spec: FAIL` / `Quality: CHANGES_REQUIRED` 唯一 Important，并在修复后再次出现真实 WAL 超时后，按用户批准架构增加同 loop、同规范化路径的进程内初始化门闩；跨进程与跨 loop 继续使用 SQLite `BEGIN IMMEDIATE` 和 WAL waiter。
- **Superpowers 技能：** `receiving-code-review`、`test-driven-development`、`systematic-debugging`、`verification-before-completion`，并用 `brainstorming` 核对用户已批准的冻结设计；所有生产修改均在精确 RED 后实施，没有添加公共接口、文件锁、依赖、003 或 Task 11 内容。
- **游标异常 RED—GREEN：** `_fetchone_closed` 原 `finally` 在 fetch/close 双失败时稳定抛 `CLOSE_SECONDARY`。RED `6044ac5` 以非锁 `OperationalError` 和自定义 `BaseException` 得到 `2 failed, 2 passed`，同时冻结“读取成功后关闭失败传播”和“双成功返回”。GREEN `30508e1` 在读取失败时仍尝试关闭，次要关闭失败不覆盖主异常，并用 bare raise 保留同一异常对象和 traceback；读取成功路径不吞关闭失败。helper/WAL 聚焦 `10 passed`，审批文件 `56 passed`。
- **再次失败与停线：** 异常修复后无插桩双连接先通过 `50/50`，但随后完整 governance 在同一集成用例再次抛固定 `MigrationBusyError`，结果为 `1 failed, 205 passed, 1 skipped`、总耗时 6.85 秒；紧随命令自动继续的全量通过未被用于覆盖该失败。按约定立即停止剩余门禁并报告；新进程顺序运行全部假时钟 WAL 测试和真实用例为 `7 passed`，真实 call 0.05 秒，但未把单次重跑作为修复证据。
- **初始化门闩 RED—GREEN：** 用户批准后，RED `7c3cb53` 用纯 Event 调度握手得到 `4 failed, 1 passed`：旧实现同路径与等价路径会在首初始化完成前第二次 connect，异常路径也提前进入，且没有 loop 隔离 gate；不同路径并行已通过。GREEN `ba48c9f` 先对路径 `resolve(strict=False) + normcase`，以短 `threading.Lock` 原子维护 `WeakKeyDictionary[loop → WeakValueDictionary[path → asyncio.Lock]]`，再于线程锁外用路径 gate 覆盖 connect、PRAGMA、migrations、WAL 和异常清理。同 loop 同路径在 SQLite 外等待且不持连接，不同路径并行，不同 loop 不复用 asyncio.Lock，弱引用避免永久增长。
- **压力与新鲜门禁：** 最终无插桩真实双连接迁移 `100/100`，governance 连续 `10/10` 轮；最终聚焦 `15 passed`，governance `211 passed, 1 skipped`，全量与 PowerShell All 均为 `313 passed, 1 skipped`。Ruff 全通过，mypy 17 个源文件无问题，`pip check` 无破损依赖，Web ESLint/TypeScript 通过；无隔离 wheel/sdist 构建成功，两种归档内 001/002 各 1、003 为 0。唯一 skip 仍为本机 Windows 符号链接权限。
- **范围、安全与状态：** 未联网、安装、推送、合并、删除工作树或接触凭据；没有实现 003、Task 11 或新公共接口。Task 4 和 PLAN 步骤 7 保持待新的独立规约符合性/代码质量复审，不宣称完成。

### 2026-07-16 03:30 +08:00 — IMPL-004-R9

- **任务与审查结论：** 处理新一轮独立审查的 `Spec: FAIL` / `Quality: CHANGES_REQUIRED` 唯一 Important：Windows 普通驱动器路径与 `\\?\` 扩展驱动器路径、普通 UNC 与 `\\?\UNC\` 扩展 UNC 指向同一 SQLite 文件时，旧实现仍产生不同的初始化门闩键。只读事实检查确认 `Path.resolve(strict=False)` 和 `normcase` 会规范普通路径的大小写，却保留扩展命名空间前缀。
- **Superpowers 技能：** `receiving-code-review`、`brainstorming`、`test-driven-development`、`systematic-debugging`、`verification-before-completion`；依照已冻结的精确前缀设计先固化失败，再做最小实现和新鲜验证。
- **RED—GREEN：** RED `e897586` 用普通/扩展驱动器 Event 握手冻结“首个 open 释放前只允许一次 connect”，并以路径键单元矩阵覆盖扩展驱动器、扩展 UNC、大小写等价和不同路径区分，聚焦得到 `4 failed, 61 deselected`。GREEN `723272d` 仅在 Windows 的 `resolve(strict=False)` 之后精确折叠大小写不敏感的 `\\?\UNC\` 前缀和带盘符根的 `\\?\` 前缀，原样保留后缀；不使用子串替换，不折叠或测试 `\\.\`，未改变门闩/WAL 生命周期。相同聚焦转为 `4 passed, 61 deselected`，普通/扩展握手单测为 `1 passed`。
- **重复验证异常与归因：** 首次 PowerShell 外层 100 轮命令由执行工具配置 120 秒超时，但异常迟至 2615464ms 才以 124 退出，未返回可定位的轮次输出，因此不计为产品或通过证据。按 `systematic-debugging` 改用外部 Python 驱动，每轮启动全新的 pytest 子进程并设 15 秒子进程超时，原真实双连接用例有效取得 `100/100`；总耗时 55.9 秒，单轮 0.515—0.703 秒，无非零退出或产品挂起，表明前一次是外层 repeater/执行工具异常。
- **完整门禁：** 最终聚焦 `19 passed, 46 deselected`，governance `215 passed, 1 skipped`，全量 pytest 和 `scripts/test.ps1 -Mode All` 均为 `317 passed, 1 skipped`；Ruff 全通过，mypy 17 个源文件无问题，`pip check` 无破损依赖，Web ESLint/TypeScript 通过。`python -m build --no-isolation` 成功生成 wheel/sdist，两种归档内 001/002 各 1 份、003 为 0。
- **范围、安全与状态：** 未联网、安装、推送、合并、删除工作树或接触凭据；未扩展 Task 11/003，未改变锁生命周期或 WAL 状态机。Task 4 与 PLAN 步骤 7 继续待独立规约符合性/代码质量复审，不宣称完成。

### 2026-07-16 03:47 +08:00 — IMPL-004-R10

- **任务与审查结论：** 处理窄复审的 `Spec: FAIL` / `Quality: CHANGES_REQUIRED` 唯一 Important。`_collapse_windows_extended_path` 的 `str.isalpha()` 接受 Unicode 字母，因此非 ASCII 拉丁、西里尔和汉字首字符也会被当成 Windows drive-root 并错误去除 `\\?\` 前缀；冻结边界只允许 ASCII `[A-Za-z]:\\` 或 `[A-Za-z]:/`。
- **Superpowers 技能：** `receiving-code-review`、`brainstorming`、`test-driven-development`、`verification-before-completion`；审查要求已给出并批准精确设计，故未扩展新的架构或公共接口。
- **RED—GREEN：** RED `a58b962` 参数化覆盖 `é`、西里尔、汉字、`\\.\`、`\\?\Volume{...}\`、`\\?\GLOBALROOT\`、截断及嵌入前缀的原值保留，并增加 ASCII A/a/Z/z 折叠与路径键大小写等价正例；旧实现稳定得到 `3 failed, 12 passed, 63 deselected`，只失败于三种 Unicode 字母。GREEN `23e5f31` 仅把 `isalpha()` 改为显式 ASCII 字母成员判断，不改变其他条件或调用链；相同聚焦为 `15 passed, 63 deselected`，目标 Ruff 和 mypy 均通过。
- **压力与完整门禁：** 门闩/WAL/路径键聚焦为 `32 passed, 46 deselected`。原真实双连接用例用外部 Python 驱动、每轮独立 pytest 子进程和 15 秒硬超时有效取得 `100/100`，总耗时 57.716 秒，单轮 0.539—1.248 秒，无超时或非零退出。governance 为 `228 passed, 1 skipped`，全量 pytest 与 PowerShell All 均为 `330 passed, 1 skipped`；Ruff 全通过，mypy 17 个源文件无问题，`pip check` 无破损依赖，Web ESLint/TypeScript 通过。
- **构建与范围：** `python -m build --no-isolation` 成功生成 wheel/sdist，两个归档内 001/002 各 1、003 为 0。未联网、安装、推送、合并、删除工作树、接触凭据或扩展 Task 11/003；未改变门闩或 WAL 生命周期。Task 4 与 PLAN 步骤 7 继续待独立双重复审，不宣称完成。

### 2026-07-16 03:57 +08:00 — REVIEW-004-POSTMERGE-FINAL

- **任务：** 对 Task 4 首次本地合并后暴露的 WAL 并发回归、游标异常优先级、路径级初始化门闩和 Windows extended-path 键进行最终独立双重审查与控制器验证。
- **Superpowers 技能：** `systematic-debugging`、`brainstorming`、`test-driven-development`、`subagent-driven-development`、`requesting-code-review`、`receiving-code-review`、`verification-before-completion`；每次真实失败均停止完成声明，按根因证据取得新的 RED 后再修复。
- **独立审查：** 最终窄复审范围 `90187a9..c704c6b`，Critical、Important、Minor 均为 0；`Spec: PASS`，`Quality: APPROVED`。ASCII/extended drive 与 UNC、非 ASCII/设备命名空间负例、不同路径区分、初始化取消/异常释放、loop/path 弱引用门闩、WAL waiter 和游标主异常边界均符合冻结要求。
- **稳定性证据：** 原真实双连接迁移用例由独立审查者以每轮新 pytest 子进程和 15 秒硬期限再次运行 `100/100`；没有超时或非零退出。此前无法定位轮次的外层重复器 124 超时仍保留为工具异常事实，没有计入产品通过证据。
- **控制器新鲜验证：** `scripts/test.ps1 -Mode All` 得到 `330 passed, 1 skipped`，Ruff、mypy（17 个源文件）、Web ESLint 与 TypeScript 全部通过；`pip check` 无破损依赖；无隔离 wheel/sdist 构建成功，两个归档内 001/002 各 1、003 为 0；`git diff --check` 和工作树检查清洁。
- **范围与安全：** 唯一 skip 仍是 Windows 符号链接权限；未联网、安装、推送、删除工作树或接触凭据，未新增锁文件、依赖、公共接口、003 migration 或 Task 11 实现。
- **结论：** Task 4 合并后补充纠偏完成，可将 `codex/governance` 的新增提交本地补充合并回 `p1`；远端推送仍未获授权。

### 2026-07-16 — DESIGN-PRODUCT-PRIORITY

- **用户决策：** 后续优先形成真正可使用、可演示、可验收的完整产品；未完成的非阻塞部分保留为之后修复的明确记录。用户批准“可验收纵向切片”方案，并确认课程硬性要求、安全护栏、离线 Mock、确定性反馈闭环、WebUI、E2E、CI 和 Docker 均不得延期。
- **Superpowers 技能：** 使用 `brainstorming` 探索三种排序方式，选定纵向闭环优先；本轮只形成书面设计，未开始 Task 5 或修改实现代码。
- **设计产物：** 新增 `docs/superpowers/specs/2026-07-16-usable-product-priority-design.md`，冻结最短产品闭环、不可延期门禁、可延期判定、`DEFERRED_WORK.md` 台账字段及完成规则。
- **后续门禁：** 等待用户复核书面设计；批准后使用 `writing-plans` 更新 `PLAN.md`，再进入后续实现。未联网、安装依赖、推送或接触凭据。

### 2026-07-16 — PLAN-PRODUCT-PRIORITY

- **用户批准：** 用户复核并批准 `docs/superpowers/specs/2026-07-16-usable-product-priority-design.md`，允许把纵向闭环优先级落实到后续计划。
- **Superpowers 技能：** 使用 `writing-plans` 更新现有主计划；本次只修改计划、延期台账和过程记录，没有开始 Task 5 实现。
- **计划变化：** 修正 Task 4 为已完成；为 Task 5—14 冻结发布必需范围、可评估的延期候选、最短完整用户路径和逐 Task 延期审计门禁。
- **延期台账：** 新增 `DEFERRED_WORK.md`，定义唯一编号、状态、优先级、登记条件、影响/替代/恢复/证据字段。当前没有已批准延期项，未开始的 Task 不计为延期。
- **范围与安全：** 没有降低课程硬性验收、安全、Mock、反馈闭环、WebUI、E2E、Docker 或 CI 要求；未联网、安装依赖、推送或接触凭据。

### 2026-07-16 07:18 +08:00 — IMPL-005-START

- **任务与隔离：** 在既有隔离 worktree `codex/workspaces` 开始 Task 5（项目识别、受限仓库地图与每任务独立 worktree）；开始时工作树清洁，Task 1—4 已合入基线。
- **Superpowers 技能：** 已读取 `using-superpowers`（其子智能体停止条款适用），并使用 `writing-plans`、`executing-plans`、`test-driven-development`；生产代码前先校正计划并设计真实 Git RED。
- **已批准纠偏：** 用户批准 Task 5 新增最小严格类型化 `Workspace`、`ProjectProfile`、`RepositoryMap`、`WorktreeInfo`，把 `Workspace` 从错误的 Task 2 消费项改为本 Task 产出；Task 11 的 003 以后补齐 Workspace 持久化字段、仓储和 `host_transfers`。本 Task 不修改 001/002、不新增迁移、不实现 Task 6。
- **延期与安全起点：** Task 5 的 Python/Node 识别、有界仓库地图、脏主工作区保护和独立 worktree 均为发布必需范围，当前无延期；不联网、不安装依赖、不推送、不接触凭据。

### 2026-07-16 08:05 +08:00 — IMPL-005

- **实现提交：** `9159e01`（`功能：实现项目识别和任务工作树（工作区子智能体）`）。
- **实现范围：** 新增严格运行期 `Workspace`、`ProjectProfile`、`RepositoryMap`、`WorktreeInfo` 与验证命令/仓库文档模型；实现 Python/Node 默认命令识别、严格 `.harness.yml` argv/timeout/env allowlist schema、配置指纹和首次执行信任标志；实现只使用 argv 的 `ls-files -z`、`log -n 20`、`status --porcelain=v1` 有界扫描；实现外置状态目录、原子单写标记及真实 Git worktree 创建/安全释放。
- **TDD RED—GREEN：** detector 初始 RED 为 `ModuleNotFoundError: coding_agent_harness.workspace`，首轮 GREEN 为 `10 passed, 1 skipped`；撤回未被初始断言证明的 fixture 分支后，Python build/Node scripts RED 为 `2 failed`，恢复最小通用逻辑后转绿。scanner 初始 RED 为缺失 `workspace.scanner`；首轮 GREEN `6 passed, 1 skipped`；真实仓库子目录可被 Git 向上解析造成路径基准混用的纠正 RED 为 `2 failed`，直属非链接 `.git` 根标记校验后转绿。worktree 初始 RED 为缺失 `workspace.worktrees`，首轮 GREEN `8 passed`；runner 在 `git worktree add` 启动时抛 `OSError` 的纠正 RED 为 `1 failed`，归并失败清理后转绿为 `9 passed`。
- **测试基础设施纠偏：** 全量 pytest 第一遍把独立 `tests/fixtures/python_project/tests/test_sample.py` 当 Harness 测试收集并因 fixture `src` 不在顶层导入路径报错；根因是静态项目 fixture 未排除。`tests/conftest.py` 精确忽略 `fixtures` 后全量恢复，未修改 fixture 的独立项目结构。
- **新鲜验证：** `python -m pytest tests/workspace -q --durations=10` 为 `29 passed, 2 skipped`，10,000 文件合成扫描耗时 `0.40s`；`ruff check src tests` 全通过；`mypy src` 检查 22 个源文件无问题；全量 pytest 为 `359 passed, 3 skipped`；`git diff --check` 通过。两个 Task 5 skip 均为本机 Windows 无符号链接权限，第三个为既有同类 skip。
- **自审与延期：** Python/Node、严格自定义命令信任标志、10,000/10,001 边界、README/AGENTS/配置大小限制、Git argv、空格路径、脏主工作区保护、同 Workspace 单写、分支/目标/基准冲突、失败清理和脏任务安全释放均有覆盖。Task 5 发布必需范围无延期，`DEFERRED_WORK.md` 保持无记录；其他语言仍是未开始增强候选，不登记延期。
- **范围与安全：** 未修改 001/002、未新增 003 或仓储、未实现 Task 6；未联网、安装依赖、推送、合并、操作主 worktree 或接触凭据。当前实现者验证通过但仍待独立规约符合性和代码质量审查，不宣称 Task 5 终审完成。

### 2026-07-16 08:42 +08:00 — IMPL-005-R1

- **纠偏提交：** `970cda8`（`fix: 加固 Task 5 路径与有界读取`）。
- **审查结论与技能：** 首轮独立规约审查为 FAIL，包含 1 个 Critical（Harness 状态子路径 symlink/junction 逃逸及失败清理越界）和 1 个 Important（配置/文档 `stat` 后完整读取的 TOCTOU 与非严格上限）。使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development` 和 `verification-before-completion`，先验证根因再逐项 RED—GREEN。
- **Critical RED—GREEN：** 预置 `state_root/worktrees` junction 的确定性 RED 为 `DID NOT RAISE WorktreeStateError`；git add 失败时把 `worktrees` 原子换为 junction 后，旧 `_cleanup_failed_create` 删除了外部 sentinel，目标用例为 `FileNotFoundError`。GREEN 复用 Task 4 `PathGuard`，以已解析状态根建立围栏，在构造、create/release、活动标记与失败清理前重新解析；越界清理不执行 `rmtree`。目标为 `2 passed, 1 skipped`，其中 symlink 正例仅因本机权限 skip，junction 与路径交换均有效执行。
- **Important RED—GREEN：** detector/scanner 各增加增长与句柄重定向用例；RED 共 `4 failed`，均证明旧构造器没有可注入的低层 opener 边界。新增共享 `BoundedFileReader`，从同一句柄取得 `fstat`、与路径 `lstat` 比对普通文件身份，身份不符在读取前拒绝；有效句柄只执行一次 `read(limit + 1)`。GREEN `4 passed`，增长场景分别记录唯一读取尺寸 17 和 9，重定向场景读取次数为 0。
- **新鲜验证：** `Python 3.11.9`；workspace 为 `35 passed, 3 skipped in 6.80s`，10,000 文件扫描 `0.39s`；`ruff check src tests` 全通过；`mypy src` 检查 23 个源文件无问题；全量 pytest 为 `365 passed, 4 skipped in 9.67s`；`git diff --check` 通过。三个 Task 5 skip 均为本机 Windows 无 symlink 权限，junction 回归未跳过；全量第四个是既有 Task 4 同类 skip。
- **范围与延期：** 未改迁移、Task 4 契约、依赖或 Task 6；未联网、安装、推送、合并、操作主 worktree或接触凭据。两项审查发现均已覆盖，Task 5 仍无延期，等待独立规约复审后再进入代码质量审查。

### 2026-07-16 09:32 +08:00 — IMPL-005-R2

- **R2 提交：** `8c153ed`（`fix: 采用工作树不确定状态安全接管`）。
- **架构结论与用户授权：** R1 规约复审仍 FAIL。独立分析确认在 Python 3.11、Windows/Linux 和外部 Git CLI 组合下，无法仅靠同一进程的路径检查跨平台绝对阻止同 UID 恶意原生进程在检查后交换父目录。用户批准首版采用“宿主私有 `state_root` + 后验验证 + 不确定即保留现场人工接管”的 fail-safe 边界，并把独立 OS 身份/ACL/broker 加固登记为 `DW-05-001`。
- **TDD RED：** 首轮因缺少 `WorktreeUncertainError` 得到收集错误；仅添加错误类型后，5 个状态机目标全部失败：add 非零仍抛普通创建错误并清理现场、未启动 OSError 仍调用 `branch -d`、add 返回 0 不检查注册、remove 假成功与残留注册仍删除 marker。另一个 release 路径身份交换用例稳定 RED 为泄漏 `WorktreeStateError`。
- **GREEN 状态机（经 R3 收窄）：** Git add 返回非零后不主动删除仍存在的 target/branch 等现场、不回滚 Git 已完成的副作用并保留 marker，抛固定 `WorktreeUncertainError`；后续 create 被 `.active` 阻塞。只有 runner 抛专用“进程确定未启动”异常才只删除本次 marker，不递归 target、不处理 branch，并允许下一任务继续；普通 `OSError` 不再带有未启动语义。add 返回 0 后验证目标仍在私有状态根、目标自身 Git 根、worktree 注册的 path/HEAD/branch；remove 返回 0 后验证目标消失且注册移除。任何身份、注册或结果不一致均保留 marker、进入人工处理；生产代码完全移除 `shutil.rmtree` 与自动 branch 删除。
- **文档与延期：** `SPEC.md` 9.2/14 明确 state_root 不进入 LLM/普通工具，首版信任同一 OS 账户不主动篡改；正常用户并发仅指项目/worktree 编辑，不宣称抵御同 UID 恶意进程。`PLAN.md` 冻结 Task 6/13 必须验证普通工具访问 state_root 固定 `DENY/PATH_ESCAPE`。`DEFERRED_WORK.md` 新增 P1 `DW-05-001`，记录用户影响、临时替代和恢复门禁。
- **新鲜验证：** `Python 3.11.9`；workspace `39 passed, 3 skipped in 9.93s`；10,000 文件小于 5 秒硬断言通过且未进入 0.43 秒以上的前十慢项；Ruff 全通过；mypy 检查 23 个源文件无问题；全量 pytest `369 passed, 4 skipped in 12.09s`；`git diff --check` 通过。三个 Task 5 skip 均为本机 symlink 权限，junction 与路径交换测试有效运行；第四个为既有 Task 4 同类 skip。
- **范围与残余风险：** 未新增依赖、迁移或 Task 6 代码，未联网、推送、合并或接触凭据。残余风险被准确限定为同 UID 原生进程可制造拒绝服务/人工恢复状态，当前没有提供独立身份隔离保证；R2 实现与验证完成，等待独立规约复审。

### 2026-07-16 — IMPL-005-R3

- **R3 提交与审查结论：** R2 独立规约复审仍为 FAIL，唯一 Critical 指出任意 `GitRunner.run()` 的普通 `OSError` 不能证明子进程未启动；唯一 Minor 要求文档准确表述为“不主动删除仍存在现场、不回滚 Git 已完成副作用并保留 marker”。纠偏提交为 `cfac874`（`fix: 区分 Git 进程启动失败与不确定状态`）。
- **Superpowers 技能：** 使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development` 和 `verification-before-completion`；先核对审查意见与原实现，再以失败测试冻结 runner 的进程生命周期契约。
- **RED 证据：** 首轮因缺少 `GitProcessNotStartedError/GitProcessUncertainError` 得到导入收集错误；只添加异常类型后，三个目标稳定为 `3 failed`：Popen 构造 `OSError` 原样泄漏、communicate 启动后失败未映射为不确定、普通 `OSError` 在已创建 branch/target/sentinel 后仍被旧代码删除 marker 并误报普通创建失败。
- **GREEN 与兼容性：** `SubprocessGitRunner` 改为显式 `Popen`；仅构造阶段 `OSError` 映射为 `GitProcessNotStartedError`，communicate/启动后异常或缺失 returncode 映射为 `GitProcessUncertainError`。正常 scanner 只读命令仍使用同一 argv/cwd、捕获 bytes stdout/stderr、保留真实 returncode，既有非零退出处理未变。`WorktreeManager` 只有捕获专用未启动异常时才删除本次 marker；普通 `OSError`、启动后和未知异常均保留 Git 已完成副作用及 `.active`，后续 writer 固定被阻塞。三个目标转为 `3 passed`。
- **新鲜验证：** `Python 3.11.9`；workspace `42 passed, 3 skipped in 10.31s`；`ruff check src tests` 全通过；mypy 检查 23 个源文件无问题；全量 pytest `372 passed, 4 skipped in 12.23s`；`git diff --check` 通过。三个 Task 5 skip 仍为本机 symlink 权限，第四个为既有 Task 4 同类 skip。
- **范围、延期与状态：** 文档同步为“不主动删除仍存在的 target/branch 等现场、不回滚 Git 已完成副作用并保留 `.active`”；`DW-05-001` 的 OS 身份/ACL/broker 边界未改变。未新增依赖、迁移或 Task 6 实现，未联网、推送、合并或接触凭据。R3 实现者验证完成，但 Task 5 仍待独立规约复审，不能提前进入代码质量审查或宣称完成。

### 2026-07-16 — DOC-005-R4

- **最终规约审查：** Task 5 实现结论为 PASS；唯一 Minor 是 `DEFERRED_WORK.md` 把 worktree 与 Harness 私有状态目录的包含关系写反。
- **文档纠正：** 仅将该句纠正为“worktree 放在 Harness 私有状态目录中、项目目录外”，与 `SPEC.md:250` 和 `PLAN.md` Task 5 一致；未改写既有历史，待独立复审。

### 2026-07-16 — IMPL-005-R5-QUALITY

- **审查结论与提交：** 最终规约审查已 PASS；独立代码质量审查提出 5 个 Important。使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development`、`executing-plans`、`using-git-worktrees` 与 `verification-before-completion`，在既有隔离 worktree `codex/workspaces` 逐项 RED—GREEN；核心纠偏提交为 `ef31b8b`（`fix: 修复 Task 5 代码质量边界`）。
- **状态路径 RED—GREEN：** 精确重叠分支起初仅错误消息不匹配，祖先重叠稳定为 `DID NOT RAISE WorktreeStateError`；新增双向真实路径包含检查并在每次状态子路径解析后再次拒绝落入 Git 根，目标 `3 passed`，构造失败前未创建 `worktrees`。
- **Git runner RED—GREEN：** 初始 runner 选择集为 `5 failed, 1 passed`，证明缺少构造参数、超时、输出上限、kill/wait 与资源关闭；第二临时文件打开失败的资源用例另得 `1 failed`。GREEN 使用临时文件承接 stdout/stderr、50ms 有界轮询、默认 300 秒与每流 64 MiB 上限；超时/超限/communicate 或 wait 异常执行 best-effort kill、communicate、wait，`ExitStack` 始终关闭资源，清理失败仍为 `GitProcessUncertainError`，Popen 构造失败保持 `GitProcessNotStartedError`。最终 runner 8 个参数化行为通过，正常 bytes/returncode 保持兼容。
- **status RED—GREEN：** 真实 Git 与 argv 契约共 `3 failed`，旧输出把中文转义文本当路径、按 ` -> ` 错切且未使用 `-z`。GREEN 改为 `status --porcelain=v1 -z`，按 NUL bytes 解析普通及 rename/copy 双路径并用 `os.fsdecode`；真实 Git 覆盖中文、空格、单引号与 rename，公开 scanner 协议用例覆盖 Windows 文件系统不能创建的 ASCII ` -> ` 与双引号路径，目标 `3 passed`。
- **release RED—GREEN：** 预检 runner `OSError` 原样泄漏、remove 已产生副作用后返回非零仍误报普通失败，目标为 `2 failed, 1 passed`。GREEN 将只读 status runner 异常映射为 `WorktreeReleaseError("无法检查任务工作树状态")`；remove 仅专用未启动异常是普通失败，非零、普通 `OSError`、启动后或未知异常均为 `WorktreeUncertainError`，保留 marker 并阻塞下一 writer；专用未启动兼容测试同时证明 worktree/marker 保留。
- **深不可变 RED—GREEN：** trusted profile 与 repository map 两个用例均因内部 list 仍有 `append` 而失败。GREEN 将 argv、languages、env allowlist、tracked/documents/test/recent/dirty 序列改为 tuple，detector/scanner 构造同步；原地 append/元素赋值不可用，trust fingerprint 不变，`model_dump(mode="json")` 仍输出数组。
- **新鲜验证：** Python `3.11.9`；五组 focused `19 passed in 5.05s`；workspace `58 passed, 3 skipped in 18.44s`；10,000 文件 `0.40s`；Ruff `All checks passed!`；mypy `Success: no issues found in 23 source files`；全量 pytest `388 passed, 4 skipped in 20.70s`；`git diff --check` 退出 0。三个 workspace skip 均为既有 Windows symlink 权限，第四个是既有 Task 4 同类 skip，未新增 skip。
- **范围与 concern：** 未联网、安装、推送、修改迁移或实现 Task 6；未接触凭据。`worktrees.py` 无需拆分，本轮仅增加双向隔离检查和 release 错误状态机；`DW-05-001` 边界未改变。当前待独立质量复审，不提前勾选 Task 5 最终完成。

### 2026-07-16 — IMPL-005-R6-QUALITY-REREVIEW

- **复审结论与技能：** 最终规约审查仍为 PASS；独立质量复审提出 1 个 Important 与 2 个 Minor。使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development` 和 `verification-before-completion` 核对根因、逐项 RED—GREEN，并把 runner 独立为 `workspace/processes.py`；核心提交为 `f9f0b72`（`fix: 有界治理 Git 子进程输出`）。
- **Important RED—GREEN：** 原 runner 接受 `NaN`/正负无穷 timeout，并以 `TemporaryFile` 把无界输出转移到磁盘。非有限参数测试先证明 `NaN` 与正无穷未拒绝；缺失 `workspace.processes` 的 focused 测试先在收集阶段 RED。GREEN 以 `math.isfinite` 严格拒绝非有限 timeout，双 PIPE reader 各按固定 64 KiB chunk 并发读取、只保留 `limit+1`、超限立即 best-effort kill 后继续 drain 到 EOF，再 join/wait/关闭资源。真实双流子进程、携带真实 `.args` 的超时替身、kill/wait/join/read/close 清理失败、部分 PIPE 初始化和正常路径 close 失败均有确定性覆盖；后两条纠正 RED 分别证明旧分支遗留已取得的 pipe，以及 close 失败曾被误报成功。
- **Minor 文档纠偏：** 报告顶部与实现摘要改为当前事实，初始结果明确标为历史快照；延期审计准确记录既有 `DW-05-001`，不再声称台账为空。`PLAN.md` 文件清单加入 `processes.py`/`test_processes.py`，进程治理描述与最终实现一致。
- **新鲜验证：** 固定使用 `E:\Coding Agent Harness\.venv\Scripts\python.exe`（Python 3.11.9）并设置 `PYTHONPATH=src`。processes focused `10 passed in 0.24s`；workspace `60 passed, 3 skipped in 22.55s`；10,000 文件单测 `1 passed`、call `0.73s`；Ruff `All checks passed!`；mypy `Success: no issues found in 24 source files`；全量 pytest `390 passed, 4 skipped in 24.54s`；`git diff --check` 退出 0。三个 workspace skip 与全量第四个 skip 均为既有 Windows symlink 权限，未新增 skip。
- **环境与范围：** 一次误用系统 Python 3.9 因缺少 pytest 在收集前失败，已明确排除为工具环境误调用，不计产品 RED 或门禁证据；随后所有有效命令均使用固定 Python 3.11。未联网、安装依赖、推送、修改迁移、实现 Task 6 或接触凭据；`DW-05-001` 范围不变。当前仅待独立质量复审，不提前标记 Task 5 最终完成。

### 2026-07-16 — IMPL-005-R7-HOST-INTERRUPT

- **复审结论与技能：** 最新独立质量复审只提出 1 个 Important：`SubprocessGitRunner.run()` 仅捕获 `Exception`，启动后的 `KeyboardInterrupt/SystemExit` 可绕过回收。使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development` 与 `verification-before-completion` 验证继承与控制流，核心提交为 `cf2a84a`（`fix: 清理后传播 Git 进程宿主中断`）。
- **TDD RED：** 参数化 `KeyboardInterrupt("host interrupt")` 与 `SystemExit(23)`，让第一次 `wait()` 抛出宿主中断，并让 cleanup 的 stdout `close()` 再抛 `SystemExit`。旧实现虽原样传播初始中断，但两项均失败于 `process.killed == False`，证明没有进入 kill/wait/join/close，而不是替身或异常类型错误。
- **最小 GREEN：** 仅将启动后受管生命周期边界改为捕获 `BaseException` 以执行 `_cleanup_started_process`；清理的 kill/wait/join/close 各自隔离 `BaseException` 并继续后续回收。若原异常属于普通 `Exception`，仍映射为 `GitProcessUncertainError`；否则用裸 `raise` 原样传播原对象，cleanup 的二次中断不能覆盖它。测试断言原对象身份、kill、第二次 wait、双 PIPE 关闭和两个 reader 线程均已终止。
- **新鲜验证：** 固定 Python 3.11.9 与 `PYTHONPATH=src`；中断目标 `2 passed in 0.17s`；processes `12 passed in 0.20s`；workspace `62 passed, 3 skipped in 21.60s`；10,000 文件 call `0.64s`；Ruff 全通过；mypy 检查 24 个源文件无问题；全量 pytest `392 passed, 4 skipped in 23.86s`；`git diff --check` 退出 0。未新增 skip。
- **范围与门禁：** 未扩大 Task 5、未修改迁移或实现 Task 6，未联网、安装、push、merge 或接触凭据；`DW-05-001` 不变。当前等待新的独立质量复审，不提前标记 Task 5 完成。

### 2026-07-16 — REVIEW-005-FINAL

- **独立最终复核：** 最终规约审查为 PASS，最终代码质量审查为 APPROVED；生产代码与测试的 Critical、Important、Minor 均为 0。复核确认核心 `cf2a84a` 在普通启动后/cleanup `Exception` 与宿主级 `BaseException` 之间保持正确分类，参数化 `KeyboardInterrupt/SystemExit` 覆盖清理后原样传播。
- **复核证据：** `tests/workspace/test_processes.py` 为 `12 passed`，`git diff --check` 退出 0。唯一 ignored 文档 Minor 是 `.superpowers/sdd/task-5-report.md` 顶部仍笼统声称所有启动后/cleanup 异常均为不确定状态，且历史导航只写 R1—R6；现已改为普通 `Exception` 映射不确定、宿主级 `BaseException` 清理后原样传播，并更新为 R1—R7。
- **完成与范围：** `PLAN.md` Task 5 步骤 6 已勾选；`.superpowers/sdd/progress.md` 同步为 complete、review clean。没有修改生产代码、测试或 `DEFERRED_WORK.md`，没有运行全量测试、联网、merge 或 push；批准的 `DW-05-001` 保持不变。

### 2026-07-16 — REVIEW-005-WHOLE-BRANCH

- **结论撤回：** 新的整分支冷审查对 `6b2f21e..61d4560` 给出 Spec compliant=No、Quality approved=No、Ready to merge=No；此前阶段性 PASS/APPROVED 不能作为合并依据。
- **阻塞问题：** 发现 Windows 扩展路径别名可绕过 state/Git 根重叠检查，以及 Git 的 fsmonitor、hooks、签名程序和 checkout filter 可在扫描、worktree add/remove 中隐式执行外部代码；另有配置信任指纹缺失和 fixture 不可运行等问题。完整台账写入 `MVP_ISSUES.md`。
- **根因调查：** 三个只读调查智能体分别复现路径身份、Git 隐式执行和信任/fixture 问题。确认 `core.fsmonitor=false` 在旧 Git 中可能执行名为 `false` 的程序，安全值必须为空；`git log` 必须显式 `--no-show-signature`；worktree materialize 前必须审计并拒绝首版不支持的外部 filter。
- **用户决策：** 用户要求重新规划并只保留必要功能，批准“现有实现上的纵向 MVP”方案。首版以 Scripted Mock 跑通完整 Harness，保留 Python/Node 和 DeepSeek/Qwen 接口，不要求真实模型联网验收。

### 2026-07-16 — DESIGN-MVP-001

- **技能：** 使用 `brainstorming` 重新确认目标、范围、替代方案、架构、安全边界和验收标准；设计获得用户逐段批准。
- **书面设计：** 新增 `docs/superpowers/specs/2026-07-16-minimal-viable-harness-design.md`，把后续交付压缩为 MVP-0—MVP-4 五个纵向实施单元。
- **过程状态：** Task 5 恢复为安全返工中；本次只修改设计、问题台账和过程文档，不修改生产代码，不 merge/push，不声称安全问题已修复。

### 2026-07-16 — PLAN-MVP-001

- **技能：** 用户确认书面 MVP 设计后，使用 `writing-plans` 生成精简实施计划。
- **计划结构：** 新计划把交付分为 MVP-0—MVP-4，并拆成 10 个可独立 TDD、评审和提交的 Task；MVP-1 先关闭 Task 5 全部安全阻塞项，随后实现工具/反馈/Agent、API/WebUI 和交付门禁。
- **范围控制：** 计划不包含长期记忆、真实模型联网、依赖安装、工具网络、Git 远程操作或外部 filter 执行；所有非首版能力要求在 Task 1 登记到 `DEFERRED_WORK.md`。
- **实现状态：** 本次只写计划，不修改生产代码、不运行实现测试、不 merge/push。

### 2026-07-16 — DOC-MVP-001

- **任务与技能：** 执行 MVP-0 Task 1，使用 `executing-plans`、`using-git-worktrees` 和 `verification-before-completion`；完整读取仓库 `AGENTS.md`、任务简报、批准的最小可用产品设计与实施计划，并确认在隔离分支 `codex/workspaces` 中工作。
- **执行顺序：** 根 `PLAN.md` 明确由精简计划的 MVP-1—MVP-4 取代原 Task 5—14 横向顺序，原条目只保留为完整产品路线；`MVP_ISSUES.md` 将状态一致性问题标为“已修，待复审”，不提前关闭。
- **延期登记：** `DEFERRED_WORK.md` 新增 `DW-MVP-001`—`DW-MVP-006`，分别登记长期记忆、多任务/多 Agent、真实 DeepSeek/Qwen 联网验收、依赖安装/工具网络/Git 远端操作、外部 checkout filter 正式执行和高级 UI；每项均记录用户影响、MVP 替代和恢复条件。既有 `DW-05-001` 保持不变。
- **验证与范围：** 本任务只修改 `DEFERRED_WORK.md`、`PLAN.md`、`AGENT_LOG.md` 和 `MVP_ISSUES.md`，不修改生产代码或测试，不联网、不安装依赖、不 merge/push、不接触凭据。按任务简报执行占位符扫描与 `git diff --check`，证据记录在忽略的 `.superpowers/sdd/task-1-report.md`；追踪变更以 `docs: 冻结最小可用产品执行顺序` 提交，随后等待独立规约符合性审查和代码质量审查。

### 2026-07-16 — IMPL-MVP-002

- **任务与技能：** 执行 MVP Task 2“统一路径身份并在文件访问前拒绝逃逸”；完整读取 `AGENTS.md`、任务简报、`MVP_ISSUES.md`、`superpowers:test-driven-development`、`superpowers:verification-before-completion` 及测试反模式说明。固定使用 `E:\Coding Agent Harness\.venv\Scripts\python.exe`，在既有隔离 worktree `codex/workspaces` 上从基线 `b72215c` 开始。
- **TDD RED：** 首轮因缺少共享模块得到 1 个收集错误，只添加旧语义等价接口骨架后重新取得有效行为 RED：`15 failed, 40 passed, 3 skipped`。失败覆盖未知 `\\.\`/GLOBALROOT/Volume/畸形扩展命名空间未拒绝、硬链接身份未用 `samefile` 补证、解析权限错误原样泄漏、5 类 Windows drive-relative/绝对 drive/UNC/反斜杠逃逸在拒绝前触发 `exists`，以及 `\\?\` drive 别名与 Git 根重叠却执行 `mkdir`。
- **最小 GREEN 与重构：** 新增共享 `governance.path_identity`，统一 `collapse_windows_extended_path/path_key/same_path/is_within/paths_overlap`；PathGuard、Database、WorktreeManager 和 Scanner 全部迁移。WorktreeManager 在首次 `mkdir` 前执行双向物理重叠检查；scanner 先按宿主语义拒绝 Windows 逃逸，再以缓存的父目录身份完成 containment，最后才允许 `exists/stat`；POSIX 保留反斜杠文件名语义。既有对象以 `samefile` 补证，权限、网络或重解析错误固定 fail closed。
- **严格于简报伪代码之处：** `\\?\C:\...` 与 `\\?\UNC\server\share\...` 中出现 `.`/`..` 不被折叠为普通路径，因为扩展命名空间不保证与 Win32 常规规范化语义等价；畸形 UNC、NT `\??\`、`\\.\`、GLOBALROOT 和 Volume GUID 均固定拒绝。该收紧遵循已批准的“只折叠可证明别名、未知设备命名空间 fail closed”不变量。
- **验证证据：** 实现阶段 focused 集为 `58 passed, 3 skipped`；提交前新鲜 governance/storage/workspace 为 `338 passed, 6 skipped in 25.92s`；Ruff 输出 `All checks passed!`；mypy 输出 `Success: no issues found in 25 source files`；`git diff --check` 退出 0。首次新鲜重跑因新增 UNC 根测试误用 raw string 在收集阶段暴露语法错误，修正测试源码后从头重跑，未将环境/测试语法错误冒充产品 RED。
- **范围、人工干预与延期：** 控制器要求立即收敛读取并汇报 RED/GREEN；未改变技术边界。未修改 Git runner、信任指纹、fixture、迁移或 Task 3+，未联网、安装依赖、merge/push 或接触凭据。未新增延期；`MVP-ISSUE-006` 保持待后续指定 Task 处理。当前仅为实现完成、待独立双重复审，不提前关闭 `MVP-ISSUE-001/005`。

### 2026-07-16 — IMPL-MVP-002-R1-PATH-COMPONENTS

- **审查输入与技能：** 首次独立双阶段审查只提出 1 个 Important：扩展 drive/UNC 仍放行尾随点/空格、DOS 保留名、ADS、普通 Win32 非法字符、控制字符和非根 `/`，且 WorktreeManager 可能先执行 `mkdir`。完整读取审查、简报与原实现报告，使用 `systematic-debugging`、`test-driven-development`、`verification-before-completion` 及测试反模式说明；根因是共享折叠器只排除空组件和精确 `.`/`..`，drive 分支还会在校验前把 `/` 归一化。
- **TDD RED：** 新增 drive/UNC 失败参数矩阵，并直接经过 PathGuard、Database key 和 WorktreeManager；后者对每类未证明形式记录 `Path.mkdir` 调用。Windows 真实探针用 `\\?\` 创建尾随点目录，证明扩展对象存在而普通 Win32 路径不存在。旧实现得到 `66 failed, 120 passed, 3 skipped`，失败均由旧放行或消费者过早丢失原始分隔符触发。
- **最小 GREEN 与兼容性：** `path_identity` 使用统一保守组件验证器，拒绝尾随点/空格、DOS 设备名及带扩展形式、ADS/冒号、`<>:\"/\\|?*`、U+0000—U+001F 和非根 `/`；UNC 的 server/share 与剩余组件使用同一规则。PathGuard、Database 和 WorktreeManager 在字符串转为 `Path` 前调用共享折叠器，避免 WindowsPath 先归一化 `/`。正向回归保留正常 Unicode、`.git`、连续中间点以及 drive 根位置 `/`。
- **GREEN 与当前状态：** focused 集为 `186 passed, 3 skipped in 35.83s`；governance/storage/workspace 回归为 `407 passed, 6 skipped in 43.14s`；定向 Ruff 全通过，定向 mypy 检查 4 个源文件无问题。当前仍为“实现完成，待复审”，`MVP-ISSUE-001/005` 未关闭；最终全量 Ruff、mypy、差异检查与 amend 哈希记录在 Task 2 实现报告中。
- **范围：** 未修改 scanner、Git runner、安全 Git 环境、信任指纹、fixture、迁移或 Task 3+；未联网、安装依赖、merge、push 或接触凭据。未新增延期，`DW-05-001` 与 `MVP-ISSUE-006` 边界不变。
- **最终新鲜门禁：** 新增回归 focused `69 passed, 120 deselected in 7.82s`；governance/storage/workspace `407 passed, 6 skipped in 42.36s`；Ruff `All checks passed!`；mypy `Success: no issues found in 25 source files`；`git diff --check` 退出 0。修复按要求 amend 到 Task 2 原提交，不新增第二个 Task 2 提交；新哈希记录在忽略的实现报告并等待独立复审。

### 2026-07-16 — IMPL-MVP-003-GIT-SAFETY

- **任务与技能：** 执行 MVP Task 3“建立不隐式执行仓库代码的 Git 边界”；完整读取 `AGENTS.md`、Task 3 简报、批准的 MVP 设计/计划、现有 workspace 实现与测试，以及 `systematic-debugging`、`test-driven-development`、`verification-before-completion`。固定使用 `E:\Coding Agent Harness\.venv\Scripts\python.exe` 与绝对 Git `E:\Git-Example\Git\cmd\git.exe`，基线为 `26c1222`。
- **版本根因探针：** 本机 Git `2.31.1.windows.1` 的 `GIT_TRACE` 明确显示 `-c core.fsmonitor=false` 会两次执行名为 `false` 的外部 hook；`-c core.fsmonitor=` 只执行内建 status。安全配置据此固定为空值，未因版本差异放宽门禁。缺失 ref 的 `show-ref --verify` 在本版本返回 128 而非 1，测试只按 Git 契约断言非零。
- **TDD RED：** 真实 scanner fsmonitor/GPG sentinel 首先失败并产生 marker；SafeGit env/config、ProcessRequest cwd/env/stdin、提交 filter gate、创建前 hook/filter、scanner status 前 filter、release 当前 index/工作树重审，以及 materialize 前二次审计均分别取得预期 RED。release 用例在临时移除 gate 后两项均落到错误的 dirty 状态，恢复 gate 后转为 `UnsupportedGitFilterError` 并保留现场。
- **最小 GREEN 与重构：** 新增 `SafeGit`，固定绝对 executable、最小宿主环境、空 hooks/global config/global attributes、协议拒绝、`core.fsmonitor=`、`gc.auto=0`、`maintenance.auto=false` 与 `log --no-show-signature`；清除继承的 Git config/dir/worktree/index/objects/alternates/diff/SSH/askpass/exec-path。`ProcessRequest/ProcessRunner` 增加显式 cwd/env/有界 stdin，同时保留双 PIPE、每流 `limit+1`、总超时和 kill/drain/wait/join/close。scanner、创建、materialize 与 release 均先用 `check-attr` 拒绝活动 filter；创建使用 `worktree add --no-checkout`、`read-tree` 与 `checkout-index`，不自行重写 checkout。
- **Sentinel 与状态语义：** 活动 filter 在 marker、branch、target 任何副作用前拒绝；真实 sentinel 证明 scanner/worktree create/materialize/release 不执行 fsmonitor、GPG、post-checkout、clean、smudge 或 process。release 在当前 index 或工作树发现 filter 时保留 target 与 `.active`；既有未启动、启动后不确定、后验失败和宿主中断的资源/现场语义全部回归。
- **关闭与当前状态：** `.superpowers/sdd/task-1-review.md` 与 `task-2-rereview.md` 均为 CLEAN，据此把 MVP Task 1/2 与 `MVP-ISSUE-001/005` 登记为关闭。MVP Task 3 仅标记“实现完成，待独立复审”，`MVP-ISSUE-002` 未关闭。
- **验证、范围与延期：** 实现阶段 git-safety 为 `8 passed`，workspace 为 `98 passed, 4 skipped`，Ruff 与 mypy 均退出 0；提交前最终门禁与提交哈希记录在 Task 3 报告。未修改 detector 信任指纹、fixture、Agent、依赖或迁移，未联网、merge、push 或接触凭据；未新增延期，现有 `DW-05-001` 与 `DW-MVP-005` 边界不变。

### 2026-07-16 — IMPL-MVP-004-VERIFICATION-TRUST

- **任务、技能与基线：** 执行 MVP Task 4“绑定全部验证配置并修复离线 fixture”；完整读取 `AGENTS.md`、Task 4 简报、`MVP_ISSUES.md`、detector/models/fixture/tests，以及 `using-superpowers`、`test-driven-development`、`verification-before-completion` 和测试反模式说明。固定使用 `E:\Coding Agent Harness\.venv\Scripts\python.exe` 与 Node `v24.15.0`，Windows npm 启动器为 `E:\nodejs\npm.cmd`；基线为 `e50f343`，工作分支为隔离 worktree `codex/workspaces`。
- **旧行为探针与 TDD RED：** 将 Python/Node fixture 复制到系统临时目录，忽略 cache/node_modules，清除 `PYTHONPATH/NODE_PATH` 并限制 PATH；旧 Python test 因 `ModuleNotFoundError: sample` 返回 2，旧 Node test/lint/typecheck/build 因缺少 vitest/eslint/tsc 均返回 1。随后 detector focused 得到 `14 failed, 13 passed, 1 skipped`，证明 package/pyproject 推导命令无 trust、raw 变化不失效、旧 harness 摘要不是 v1 manifest、无命令状态错误、模型不拒绝不一致组合，以及 Windows 返回不可由 `shell=False` 启动的 `npm`。
- **最小 GREEN：** 每个存在的 `.harness.yml`、`package.json`、`pyproject.toml` 只做一次有界读取，raw bytes 分别 SHA256，缺失源显式为 `null`；绑定规范化 commands、env allowlist、timeout，以 canonical JSON 和 `coding-agent-harness\0verification-trust\0v1\0` 领域分隔生成 64 位摘要。只要存在任一命令即要求 trust；无命令才允许 false/None，模型后置校验拒绝其他组合。Windows 推导 `npm.cmd`，其他平台推导 `npm`。focused 转为 `27 passed, 1 skipped`。
- **离线 fixture 与性能门禁：** Python 改为 `src/sample/__init__.py` 并配置 pytest `pythonpath=["src"]`；Node 声明 ESM，仅使用 `node:test`、`node:assert/strict` 和 `node --check`。独立副本中 Node 四命令均返回 0，且没有 `NODE_PATH` 或 `node_modules`。10,000 文件 CI 测试只断言功能并记录耗时，不再硬断言 wall clock；本机独立基准 call 为 `0.88s`，满足小于 5 秒目标。
- **验证、台账与范围：** 实现阶段 workspace 为 `109 passed, 4 skipped`，全量为 `499 passed, 6 skipped`；Ruff、mypy、pip check 与 `git diff --check` 均退出 0。Task 3 独立双审已 CLEAN，据此关闭 `MVP-ISSUE-002`；Task 1 独立文档双审确认状态一致，据此关闭 `MVP-ISSUE-007`；`MVP-ISSUE-003/004/006` 只标记“实现完成，待复审”。未新增延期，未联网、安装依赖、接触凭据、实现 MVP-2、merge 或 push；整分支双审与主控新鲜验证前不得合并回 `p1`。

### 2026-07-16 — IMPL-MVP-004-R1-CONFIG-NOFOLLOW

- **审查输入与技能：** 整分支规约符合性审查提出 1 Important、1 Minor；完整读取 `AGENTS.md`、审查报告、Task 4 brief/report/review、批准的 MVP 设计/计划，并使用 `systematic-debugging`、`test-driven-development`、`verification-before-completion`。根因是 Detector 三入口先 `Path.exists()`，默认 opener 又先打开后补验，导致静态 symlink 目标已被 follow/open。
- **TDD RED：** `.harness.yml`、`package.json`、`pyproject.toml` 三入口消费者级契约得到 `3 failed, 6 skipped`，三项均精确失败于 follow-target `exists`，记录型 opener 零调用；Windows 可注入 reparse 契约单独得到 `3 failed, 3 passed`；默认 opener 的 pre-open reparse 契约得到 `1 failed`。POSIX 真实根外普通文件/FIFO symlink 用例在当前 Windows 按平台跳过，并以 2 秒子进程 timeout 防止旧实现阻塞 CI。
- **最小 GREEN：** Detector 不再使用 `exists()`，而是在固定直属配置路径上先 `lstat`，以 mode 与 `FILE_ATTRIBUTE_REPARSE_POINT` 分类缺失、symlink/reparse、非普通文件和可读普通文件。默认 opener 在 POSIX 使用 `os.open(O_NOFOLLOW|O_CLOEXEC)`；Windows/通用路径先拒绝静态 symlink/reparse，再打开，并保留 reader 的 `fstat/lstat/samestat` 打开后复验。同 UID 主动竞争仍按 `DW-05-001` 记录，没有扩大威胁模型。
- **阶段证据与状态：** detector focused 为 `34 passed, 7 skipped`；定向 Ruff 全通过，mypy 检查 26 个源文件无问题。根 `PLAN.md` 与 Task 5 报告顶部已统一为“当前 1 Important、1 Minor 正在返工”，同时保留历史 2 Critical、2 Important、3 Minor；新增 `MVP-ISSUE-008/009`，且 003/004/006 不提前关闭。完整门禁、amend 哈希和最终状态仍待本轮后续记录；不得据此进入代码质量审查或合并。
- **提交前新鲜门禁：** detector `34 passed, 7 skipped in 2.43s`；workspace `116 passed, 10 skipped in 38.35s`；全量 pytest `506 passed, 12 skipped in 45.01s`；Ruff `All checks passed!`；mypy `Success: no issues found in 26 source files`；pip check `No broken requirements found.`；`git diff --check` 退出 0。12 个 skip 均为平台能力门禁，其中新增 6 个仅在 POSIX 运行的真实根外普通文件/FIFO symlink 组合；Windows 仍由不依赖 symlink 权限的可注入零调用契约覆盖。验证后只 amend Task 4 单一提交，不进入代码质量审查或合并。

### 2026-07-16 — DOC-MVP-004-R1-SPEC-MINOR

- **复审 Minor 修复：** 使用 `receiving-code-review` 与 `verification-before-completion` 核对返工后规约复审、`PLAN.md` 和 `MVP_ISSUES.md`；仅纠正 Task 5 报告“当前问题”段残留的旧阶段结论，明确当前仍等待整分支规约复审，并把先前规约 PASS 与质量审查/返工保留为历史证据。未修改生产代码、测试或 `MVP-ISSUE-003/004/006`。

### 2026-07-22 — IMPL-MVP-1-FINAL-QUALITY-FIX

- **任务、技能与边界：** 作为 MVP-1 最终质量返工智能体，从 clean `9d92e05` 开始，完整阅读 `AGENTS.md`、最终质量报告、`SPEC.md`、批准的 MVP 设计/计划，并使用 `systematic-debugging`、`test-driven-development`、`verification-before-completion` 与 `requesting-code-review`。固定 Python 为 `E:\Coding Agent Harness\.venv\Scripts\python.exe`、Git 为 `2.31.1.windows.1`；未扩展 MVP-2、未联网、未安装依赖、未 merge/push。
- **根因与版本探针：** 初始探针确认 Git 2.31.1 的 `config --local --no-includes -z --list` 输出为 `key\nvalue\0`，能看到 include/includeIf 声明但不展开外部配置；但质量复审进一步证明该命令仍先做 repository discovery，会受 primary/linked `commondir` 与 `extensions.worktreeConfig`/`config.worktree` 影响，因此不能作为审计根。固定 Git 随后在无仓库的 `%TEMP%` cwd 中对显式 common config 执行 `config --file <path> --no-includes --get` 与 `-z --list`，两者均退出 0，支撑无 repository discovery 的最终架构。其余根因仍是不受信 containment 与受信配置身份补证混用、`is_symlink()` 不识别 junction，以及最终 `same_path` 位于异常映射外。
- **TDD RED：** 首轮四组独立最小复现共 `17 failed`，覆盖跨 anchor 零探测、四类 repository-local 配置、两层 junction/trusted linked gitfile 与最终 identity 异常。质量复审追加 drive-relative `Z:payload`、rooted-relative `\payload` 的 PathGuard/path identity/Policy/registration 回归，旧实现得到 `6 failed, 246 deselected`；primary `commondir` 重定向、`config.worktree` reparse 与 trusted linked `commondir` 改写得到 `3 failed, 21 deselected`。切换 exact-file audit 后的 `21 failed` 均定位为 synthetic runner 对 `-C` 的旧假设，修正 fixture 后未保留为产品 RED。
- **最小 GREEN：** Windows 路径关系对含 drive/root 但非 absolute 的输入在任何 identity probe 前 fail closed，PathGuard 在普通相对路径拼接前调用该门禁；显式受信 Worktree 配置继续使用 `trusted_paths_overlap`。SafeGit 对 primary 拒绝任何 `commondir`，对 linked 每命令 no-follow 有界复验 `commondir` 身份与严格 `../..` 内容，拒绝 `extensions.worktreeConfig` 和任何 `config.worktree`；随后在安全 cwd 对已验证 common config 执行 `config --file <approved-config> --no-includes -z --list`，audit request 无 `-C` 且先于每条 protected request。scanner toplevel、trusted linked context、safety assets 和最终 `WorktreeUncertainError` 映射保持原修复。
- **新鲜证据与状态：** 独立规约审查为 CLEAN。最终 focused 为 `292 passed, 6 skipped`；governance/storage/workspace 为 `466 passed, 13 skipped`；全量 pytest 为 `536 passed, 13 skipped`；Ruff `All checks passed!`；mypy 为 26 个源文件无问题；pip check 无损坏依赖。独立质量审查确认全部生产阻塞已修复，只要求本条及 `PLAN.md`、`MVP_ISSUES.md` 同步已替换的安全机制，现等待同一审查者复核；`MVP-ISSUE-003/004/006` 保持待复审，`DW-05-001` 未改变，Task 5 状态仍为“质量返工中”。

### 2026-07-22 — IMPL-MVP-1-FINAL-SCANNER-NOFOLLOW

- **任务、技能与边界：** 最终整分支规约门禁发现 scanner tracked path no-follow Important 后，完整阅读 `AGENTS.md`、`.superpowers/sdd/mvp1-final-spec-gate.md`、scanner 实现/测试和最新质量返工报告，并使用 `systematic-debugging`、`test-driven-development`、`verification-before-completion`。基线父提交为 `9d92e05`；`5c2b60b` 是 amend 前历史哈希，当前稳定技术提交 `af11fea` 已包含 `MVP-ISSUE-010`—`014` 的技术修复。本轮只修复 `MVP-ISSUE-014` 与对应过程状态，不实现 MVP-2、不联网、不安装依赖、不 merge/push。
- **根因与 TDD RED：** 根因是 `_validate_tracked_path()` 在 no-follow 分类前调用 `candidate.exists()`，会 follow tracked symlink/reparse 的外部或 UNC 目标。消费者级 Windows reparse 注入契约在旧实现得到 `1 failed, 1 skipped`，精确失败于 `scanner.py:220` 的 `exists`，记录为 `[('exists', linked-to-unc.txt)]`；真实 symlink 用例因当前账户无创建 symlink 权限跳过。该平台限制不阻塞 Windows reparse 注入契约。
- **最小 GREEN 与回归：** candidate 在任何 `exists`、follow-target `stat` 或 `resolve` 前先 `lstat`；缺失路径保持返回，symlink/reparse 固定映射为 `RepositoryScanError`，普通对象才继续 containment。GREEN 目标为 `1 passed, 1 skipped` 且记录的 follow-target `exists/stat/resolve` 调用为空；scanner 全文件为 `20 passed, 3 skipped`。真实临时父仓加入受控子仓 gitlink 后 scanner 返回 `('.gitmodules', 'README.md', 'nested')`，普通文件、缺失 tracked 路径与 gitlink 语义保持。
- **当前状态与台账：** `PLAN.md`、本日志、`MVP_ISSUES.md` 与 Task 5 报告均将 `5c2b60b` 标为 amend 前历史哈希，并记录当前稳定技术提交 `af11fea` 已包含 `MVP-ISSUE-010`—`014` 的技术修复；历史审查数量明确为快照。`MVP-ISSUE-003/004/006/008`—`014` 均未提前关闭。scanner focused 为 `20 passed, 3 skipped`，governance/storage/workspace 为 `467 passed, 14 skipped`，全量 pytest 为 `537 passed, 14 skipped`；Ruff、mypy、pip check 与差异检查通过。技术修复已提交，当前等待最终整分支规约/质量门禁。

### 2026-07-23 — DOC-MVP-1-FINAL-GATE-SYNC

- **文档同步：** 完整复核 `AGENTS.md` 与 `.superpowers/sdd/mvp1-final-spec-rereview.md` 后，仅同步 `PLAN.md`、`MVP_ISSUES.md`、本日志及忽略的 Task 5 过程报告。`5c2b60b` 明确标为 amend 前历史哈希；当前稳定技术提交 `af11fea` 已包含 `MVP-ISSUE-010`—`014` 的技术修复；当前状态统一为“技术修复已提交，等待最终整分支规约/质量门禁”。
- **门禁与范围：** `MVP-ISSUE-003/004/006/008`—`014` 全部保持待复审，未提前关闭。未修改生产代码、测试或设计，未联网、安装依赖、merge、push 或接触凭据；关键词一致性检查与 `git diff --check` 均通过。忽略的 `.superpowers/sdd/mvp1-final-docs-report.md` 仅作过程证据，不进入提交。

### 2026-07-23 — IMPL-MVP-1-SCANNER-PARENT-NOFOLLOW

- **任务、技能与范围：** 最终质量门禁发现父目录 reparse 的唯一 Important 后，完整阅读 `AGENTS.md`、`.superpowers/sdd/mvp1-final-quality-gate.md`、scanner 实现/测试和最新质量返工报告，并使用 `systematic-debugging`、`test-driven-development`、`verification-before-completion`。本轮只处理 `MVP-ISSUE-015`，不扩大到其他模块、MVP-2、网络、依赖安装、merge 或 push。
- **根因、TDD 与最小修复：** 真实本地 `mklink /J` 父 junction 的消费者级 RED 为 `1 failed, 23 deselected`：旧实现先对 `dir/file.txt` 执行 leaf `lstat`，再以会 follow 的父目录解析得到“路径越界”。GREEN 从已解析 root 按 `PurePosixPath.parts` 无缓存逐级执行 no-follow `lstat`；每个既有非叶组件只允许普通、非 symlink/reparse 目录，父缺失维持既有返回，且只在安全父下检查 leaf。没有引入布尔 containment 缓存；同 UID 主动竞争继续由 `DW-05-001` 覆盖。
- **当前证据与状态：** scanner 全文件为 `27 passed, 3 skipped in 10.77s`，覆盖多级父、真实 junction、Windows reparse 属性、父非目录、父/leaf 缺失、普通嵌套文件、真实 gitlink、POSIX 反斜杠和 10,000/10,001。`MVP-ISSUE-015` 技术修复已提交为 `c376216`；`PLAN.md`、本日志、`MVP_ISSUES.md` 及 Task 5 报告当前统一等待最终规约与质量双门禁，`MVP-ISSUE-003/004/006/008`—`015` 均未提前关闭。
- **新鲜验证：** governance/storage/workspace 为 `474 passed, 14 skipped in 94.07s`；全量 pytest 为 `544 passed, 14 skipped in 96.23s`；Ruff、mypy（26 个源文件）和 `pip check` 均通过。差异检查已通过；状态保持等待最终规约与质量双门禁，不据此提前关闭任何问题。

### 2026-07-23 — DOC-MVP-1-CLOSURE

- **关闭事实：** 完整复核 `.superpowers/sdd/mvp1-post-parent-spec-clean.md` 与 `.superpowers/sdd/mvp1-post-parent-quality-clean.md`；最终受审范围为 `6b2f21e..9d01b77`，规约与质量门禁均为 CLEAN，Critical / Important / Minor 均为 `0 / 0 / 0`，质量报告确认 Ready to merge：Yes。
- **验证证据：** 最终报告记录 scanner `27 passed, 3 skipped`、governance/storage/workspace `474 passed, 14 skipped`、全量 pytest `544 passed, 14 skipped`；Ruff、mypy、pip check 与 diff check 均通过。
- **状态与范围：** 据此关闭 MVP-1、兼容保留的原 Task 5 项目接入阶段、MVP Task 2/3/4，以及 `MVP-ISSUE-003/004/006/008`—`015`；允许本地合并，但尚未合并。仅更新过程文档；未联网、安装依赖、merge 或 push。

### 2026-07-23 — VERIFY-MVP-1-CONTROLLER

- **主控新鲜门禁：** 在关闭提交 `eceac96` 后，固定 `PYTHONPATH` 指向当前 worktree 的 `src`，取得 Ruff 全通过、mypy 26 个源文件无问题、全量 pytest `544 passed, 14 skipped in 67.18s`、Web ESLint 与 TypeScript typecheck 通过、`pip check` 无损坏依赖、Python sdist/wheel 构建成功以及 `git diff --check 6b2f21e..HEAD` 通过的证据。
- **一键入口诊断：** 当前 PowerShell 环境没有名为 `make` 的入口；仓库等价脚本 `scripts/test.ps1` 又假设 worktree 内存在 `.venv`。首次运行时 `Resolve-Path` 失败后脚本仍继续，并可能由后续命令覆盖退出码；第二次在 Python 门禁通过后因 worktree 缺少 `web/node_modules` 于 ESLint 启动前失败。主控核对主仓库与 worktree 的 `package.json`/`package-lock.json` SHA-256 完全一致后，只在被忽略目录建立本地 junction 复用已批准依赖，再次运行等价一键入口并取得全部真实门禁通过。该假阳性风险登记为 `MVP-ISSUE-016`，由 MVP-4 Task 9 修复，不回开 MVP-1。
- **边界：** 没有修改生产代码或测试，没有联网、重新安装依赖、推送或接触凭据；当前仅待把 `codex/workspaces` 本地合并到 `p1`。

### 2026-07-26 — IMPL-MVP-2-TOOLS

- **任务与范围：** 在隔离 worktree `codex/tools` 实现 MVP-2 Task 5 的受治理最小编码工具集；使用 `test-driven-development` 与 `verification-before-completion`。范围未包含 shell、任意 Git、网络或依赖安装工具，未修改 `MVP-ISSUE-016`，未联网、未 merge、未 push。
- **TDD RED→GREEN：** 新增工具测试后，`PYTHONPATH=src .venv\Scripts\python.exe -m pytest tests/tools -q` 首次因 `coding_agent_harness.tools` 不存在而出现 5 个收集错误；实现最小接口后转为 `7 passed`。结构化文件工具策略测试先因返回 `INVALID_ACTION` 失败，补齐解析和 `PathGuard` 路径处理后转绿。
- **提交与新鲜验证：** 提交 `4636189 feat: 实现受治理的最小编码工具集` 包含 CAS 原子替换、审批门控删除、有界搜索、信任指纹重检验证及固定 Git status/diff。focused `tests/tools tests/governance` 为 `305 passed, 2 skipped`；Ruff、mypy 均通过；全量 pytest 为 `552 passed, 14 skipped`，`git diff --check` 通过。当前仅等待独立规约与代码质量审查。

### 2026-07-26 — IMPL-MVP-2-TOOLS-REWORK

- **审查返工与 TDD：** 确认审查提出的 1 个 Critical 与 2 个 Important 均成立。文件工具新增“写入临时文件后并发创建/改写目标”的确定性 RED：旧实现两种路径均返回 `OK` 并覆盖并发内容；改为同目录 `O_EXCL` CAS 协调、创建 `link` no-replace、替换写前复验后转绿。受治理 `search({query})` 的 RED 复现策略返回 `INVALID_ACTION`，统一协议且拒绝未知字段后转绿；失效 verification 以计数失败 runner 验证 `STALE_CONFIG` 且零调用。
- **新鲜验证与边界：** focused `tests/tools tests/governance` 为 `309 passed, 2 skipped`，Ruff、mypy 通过；全量 pytest 为 `556 passed, 14 skipped`，`git diff --check` 通过。仅修复 Task 5 审查项，未扩展功能；未联网、安装依赖、merge 或 push，`MVP-ISSUE-016` 未修改；Task 5 实现提交已 amend，继续等待独立规约/质量审查。

### 2026-07-26 — IMPL-MVP-2-TOOLS-CAS-BOUNDARY

- **批准的契约收口：** 同一 Workspace 最多一个 Harness 写任务；同目录 `O_EXCL` 协作锁线性化所有遵守协议的 Harness 实例。create 使用原子 no-replace；replace 在持锁且最终 replace 前复验 `expected_sha256`，复验前完成的编辑返回 `STALE_CONTENT`。
- **明确限制与证据：** 普通跨平台文件系统不存在按 SHA-256 条件原子 replace。忽略锁的同 UID 外部进程若恰在最终复验与 replace 之间改写，属于 SPEC 9.2 已批准的外部竞争边界；已检测到身份或摘要不一致 fail closed，现场不确定则人工接管。测试名称和断言新增 Harness 协作锁 `CAS_BUSY` 与预替换摘要变化 `STALE_CONTENT` 覆盖；未删除复验或弱化 PathGuard/审批，未联网、安装依赖、merge 或 push。

### 2026-07-26 — REVIEW-MVP-2-TOOLS-FINAL

- **独立复审：** Task 5 最终提交 `0663960` 的规约符合性与代码质量复审均通过，Critical / Important / Minor 为 `0 / 0 / 0`，Task quality 为 Approved；定向复验为 `8 passed`。此前 search 策略协议、失效验证 runner 零调用和协作 CAS 契约均已收口。
- **主控新鲜门禁：** `scripts/test.ps1 -Mode All` 取得全量 pytest `557 passed, 14 skipped`，Ruff 检查 33 个源文件通过、mypy 无问题，Web ESLint 与 TypeScript typecheck 通过；`pip check` 无损坏依赖，`git diff --check 07dfa31..HEAD` 通过，工作树干净。
- **状态与范围：** MVP-2 Task 5 据此完成，Task 6 尚未开始；未联网、安装依赖、merge 或 push，`MVP-ISSUE-016` 仍由 MVP-4 Task 9 处理。

### 2026-07-26 — IMPL-MVP-2-AGENT-LOOP

- **任务与范围：** 在隔离 worktree `codex/agent-loop` 按 `.superpowers/sdd/task-6-brief.md` 实现确定性反馈与离线 Mock Agent 主循环；未联网、未安装依赖、未处理 `MVP-ISSUE-016`、未 merge 或 push。
- **技能与 TDD：** 使用 `test-driven-development`、`systematic-debugging`、`verification-before-completion`。先新增反馈 3/8/2 预算、失败反馈改变下一动作、事件序列/危险动作阻断和工具开始状态的测试；RED 首轮因 `feedback` 与 `orchestrator` 模块不存在而收集失败，状态机目标测试则稳定失败于未知 `TOOL_EXECUTION_STARTED`。最小实现后转绿。
- **实现事实：** 新增固定失败分类、去临时路径/行列/耗时噪声的指纹、3 次同指纹与 8 次验证预算、两轮无进展升级；新增注入式 Provider/Parser/ToolRegistry/EventStore/TaskRepository 编排器。每个 LLM、解析、治理、工具开始/结束、验证和反馈决定均落盘为事件；未完成工具 started 由既有恢复逻辑转为 `UNCERTAIN_SIDE_EFFECT`，不自动重放；`delete_file` 在执行前确定性阻断。
- **类型纠偏与验证：** 严格 mypy 首轮定位到 LLM 消息和事件载荷的 `JsonValue` 不变型边界；仅收紧编排器注解后 `mypy src` 通过。聚焦 `tests/feedback tests/agent tests/providers tests/storage -q` 为 `100 passed`；全量 pytest 为 `566 passed, 14 skipped`；Ruff、mypy（39 个源文件）及 `git diff --check` 均通过。
- **状态：** 实现随本提交提交，等待独立规约符合性审查和代码质量审查；未将任务标记为完成。独立审查应特别确认最终摘要动作与后续机制演示接口仍由后续范围承接。

### 2026-07-26 — IMPL-MVP-2-AGENT-LOOP-REWORK

- **审查核实：** 独立审查提出的 4 个 Important 与 1 个 Minor 均成立：未知失败数被默认记为 0 会造成假 `NO_PROGRESS`；Mock 未覆盖两次 patch 与 `CompleteAction` 摘要；原断言未消费反馈证据；时间预算未使用 `time_budget_seconds`；报告计数必须使用真实全量结果。
- **TDD RED → GREEN：** 新增未知失败数反馈、两次 patch/失败输出回灌/最终摘要、端到端两轮未知失败数和 `deadline_at=None` 时间预算测试。RED 分别表现为 `failure_count=None` 校验失败、无 `FINAL_SUMMARY_RECORDED`、第二轮反馈错误停为 `NO_PROGRESS`，以及预算耗尽后仍请求耗尽的 Mock。GREEN 后未知计数不触发无进展，可靠 `N failed|N errors` 才参与比较；成功验证先落盘成功事件，随后 `CompleteAction` 落盘摘要并进入 `WAITING_FINAL_REVIEW`；时间预算取创建时间加时长与可选 deadline 的较早值。
- **新鲜验证：** focused `tests/feedback tests/agent tests/providers tests/storage -q` 为 `104 passed`；全量 pytest 为 `570 passed, 14 skipped`；Ruff、mypy（39 个源文件）和 `git diff --check` 均通过。仅在原 Task 6 提交上 amend，未联网、安装依赖、merge、push 或处理 `MVP-ISSUE-016`。
- **状态：** 审查返工随本提交修正，继续等待独立规约符合性与代码质量复审，未标记任务完成。

### 2026-07-27 — IMPL-MVP-2-AGENT-LOOP-VERIFICATION-FRESHNESS

- **审查返工与 TDD：** 新增“验证通过 → 修改工具 → CompleteAction”反例，RED 稳定进入 `WAITING_FINAL_REVIEW`，证明历史任意 `VERIFICATION_SUCCEEDED` 会错误授权过期验证；同时新增只读 search 后完成摘要的回归，保证只读不错误失效。GREEN 改为反向读取持久化事件：最近一次 `changed_paths` 非空的 `TOOL_EXECUTION_COMPLETED` 晚于成功验证时固定拒绝摘要并进入 `WAITING_USER/VERIFICATION_REQUIRED`；无变更的读取事件不影响验证新鲜度，重启后仍由同一 EventStore 事件流得出相同结论。
- **新鲜验证：** focused `tests/feedback tests/agent tests/providers tests/storage -q` 为 `106 passed`；全量 pytest 为 `572 passed, 14 skipped`；Ruff、mypy（39 个源文件）和 `git diff --check` 通过。仅 amend 当前同名 Task 6 提交，未联网、安装依赖、merge、push 或处理 `MVP-ISSUE-016`。
- **状态：** 验证新鲜度返工已随本提交修正，继续等待独立规约符合性与代码质量复审，未标记任务完成。

### 2026-07-26 — REVIEW-MVP-2-AGENT-LOOP-FINAL

- **独立复审：** Task 6 最终提交 `b9ac938` 的规约符合性与代码质量复审通过，Critical / Important / Minor 为 `0 / 0 / 0`，Task quality 为 Approved；定向复验为 `65 passed`，Ruff 通过。原 4 个 Important、1 个 Minor及验证新鲜度回归均已关闭。
- **主控新鲜门禁：** `scripts/test.ps1 -Mode All` 取得全量 pytest `572 passed, 14 skipped`，Ruff、mypy（39 个源文件）、Web ESLint 与 TypeScript typecheck 全部通过；`pip check` 无损坏依赖，`git diff --check 6e9c805..HEAD` 通过，工作树在写入本记录前干净。
- **状态与范围：** MVP-2 Task 6 据此完成，下一门禁为 MVP-2 整阶段审查；未联网、安装依赖、merge、push 或处理 `MVP-ISSUE-016`。

### 2026-07-27 — IMPL-MVP-2-FINAL-REWORK-A

- **范围与技能：** 仅执行 MVP-2 最终返工 A：C1 的 worktree 根身份隔离、受限 `read_file`，以及 I1 的真实 ToolRegistry/PolicyEngine/CAS/受控 runner Mock 闭环。使用 `test-driven-development` 与 `verification-before-completion`；不提前修改返工 B 的验证信任契约、返工 C 的事件脱敏或返工 D 的审批契约。
- **RED → GREEN：** RepositoryMap 根目录落在 worktree 外的 search 用例先失败并泄露 `private.py`，现固定返回 `PATH_ESCAPE`。新增的 `read_file` 用例先得到 `UNSUPPORTED_TOOL`，实现后以 64 KiB 上限、普通文件/无跟随打开和 UTF-8 解码边界返回稳定结果。真实临时 Git worktree 集成用例最初暴露 Windows checkout 字节摘要与文本摘要不一致，改为从实际字节计算 CAS SHA-256；随后验证错误输出通过 `FEEDBACK_RECORDED` 进入下一次 Mock 请求。
- **实现事实：** `search` 要求 RepositoryMap 根与 ToolRegistry 的 PathGuard 根一致，并逐级 no-follow 检查受追踪候选项；`read_file` 不支持越界、符号链接、超限或非 UTF-8 内容。集成测试依次实际读取当前文件、使用当前 SHA 写入错误补丁、由受控 runner 返回失败、让反馈进入下一请求、使用错误版本的新 SHA 写入修复补丁、验证通过并记录最终摘要；通过同一真实注册表/策略的删除请求未移除文件。
- **当前证据与状态：** 聚焦命令 `PYTHONPATH=src .venv\Scripts\python.exe -m pytest tests/tools tests/agent/test_real_tool_loop.py -q` 为 `15 passed, 1 skipped`（唯一 skip 为 Windows 无创建符号链接权限）；Ruff 与 3 个变更源文件的 mypy 均通过，`git diff --check` 通过。返工 A 已随指定标题提交，返工 B 保持待执行。

### 2026-07-27 — IMPL-MVP-2-FINAL-REWORK-B

- **范围与技能：** 仅执行返工 B 的 C2/I4：显式验证批准绑定、实际 argv 的 PolicyEngine 复核，以及完整验证新鲜度门禁。使用 `test-driven-development`；未修改返工 C 的事件/Provider 脱敏或返工 D 的审批消费契约。
- **RED → GREEN：** 新增的显式批准测试先因 `VerificationApproval` 缺失无法收集，补齐模型后，无批准与不匹配指纹的验证先暴露为实际调用 runner；现在均固定拒绝且 runner 零调用。完整门禁的 RED 显示“仅 lint 成功”仍进入最终审查，现要求所有当前必需检查都在同一当前快照、配置版本和信任指纹下成功。
- **实现事实：** ToolContext 需要独立的 `VerificationApproval`（审批标识、配置版本、信任指纹），重新 detect 后校验其与当前 profile 一致；实际 argv 被构造成 shell ToolAction 并交 PolicyEngine，curl、pip install、git push 与 shell 解释器固定拒绝，安全 pytest 才可执行。成功验证持久化检查名、配置版本、信任指纹、受 PathGuard/RepositoryMap 约束的确定性 worktree 快照和必需检查集合；CompleteAction 重新取当前证据，拒绝漏检、外部编辑、配置变化及最后修改前的结果，只读工具不失效。
- **当前证据与状态：** `tests/tools/test_verification.py tests/agent/test_orchestrator.py tests/agent/test_real_tool_loop.py` 为 `19 passed`；Ruff、mypy（4 个变更源文件）和 `git diff --check` 通过。返工 B 已随指定标题提交；返工 C 保持待执行。

### 2026-07-27 — IMPL-MVP-2-FINAL-REWORK-B-SNAPSHOT

- **根因与范围：** 独立复审确认 B 的唯一 Important：旧快照只遍历构造 RepositoryMap 时的 `tracked_files`，验证后出现的未跟踪普通文件不会改变指纹。仅修复动态快照；未触及返工 C/D。
- **RED → GREEN：** 在真实临时 Git worktree 中，先通过 test 验证，再由 Provider 在 CompleteAction 返回前创建未跟踪 `external.py`；旧实现错误进入 `WAITING_FINAL_REVIEW`，新实现固定进入 `WAITING_USER/VERIFICATION_REQUIRED`。补充断言证明受跟踪文件改写改变快照、未跟踪文件改变快照，而删除/重命名已跟踪文件使快照不可用并 fail closed。
- **实现与证据：** 快照现在 no-follow、有界遍历当前 worktree 文件系统，动态纳入所有普通文件并区分已跟踪/未跟踪；`.git` 被排除，若显式 state_root 位于 worktree 内则拒绝读取并不放行。目录、链接/reparse、非普通文件、遍历/读取错误、大小/数量上限以及静态已跟踪文件缺失均固定返回不可用。聚焦 `tests/tools/test_verification.py tests/agent/test_orchestrator.py tests/agent/test_real_tool_loop.py` 为 `21 passed`；Ruff、mypy（4 个源文件）和 diff check 通过。待 amend 同名 B 提交，返工 C 保持待执行。

### 2026-07-27 — IMPL-MVP-2-FINAL-REWORK-B-SCAN-BOUND

- **审查返工与根因：** 复审继续指出快照动态扫描仅限制普通文件数、单文件大小和总字节数；空目录不计入上述预算，因而可以使扫描无界。
- **TDD RED → GREEN：** 先新增 10,001 个空目录的用例，旧行为返回验证证据，因而输出明确的断言失败；同时新增 65 层目录深度的 RED 用例。GREEN 后，对当前 worktree 扫描使用确定性的 10,000 目录、10,000 条目和 64 层深度预算；枚举错误、symlink/reparse 或任何超限均固定 fail closed。
- **状态：** 仅 amend 同一个返工 B 提交，未触及返工 C/D、网络、依赖安装、merge 或 push。

### 2026-07-27 — IMPL-MVP-2-FINAL-REWORK-C

- **范围与 TDD：** 返工 C 先以真实 EventStore 和后续 LLMRequest 的序列化扫描固定秘密泄露 RED，并以重启后 started 无 finished 的恢复 RED 固定事件链要求。GREEN 后，编排器在事件/LLM 边界使用 Redactor、长度与 SHA-256 摘要，不持久化原始 LLM 回复、patch/content、完整 action、ToolResult 或验证输出；反馈以不可信诊断分隔回灌。
- **恢复语义：** 检测到未完成执行时以乐观序号追加 UNCERTAIN_SIDE_EFFECT_DETECTED，持久化 reason_code 与 execution_id；重复恢复不重复追加。resume_after_uncertain 仅允许显式 retry/continue/cancel，绝不重放旧 execution，事件重放保持连续。
- **验证：** agent 60 passed、storage 32 passed、governance redaction 10 passed、providers 16 passed；Ruff、mypy（6 个源文件）和差异检查通过。未触及返工 D、网络、依赖安装、merge 或 push。

### 2026-07-27 — IMPL-MVP-2-FINAL-REWORK-C-REVIEW

- **复审纠偏：** 验证事件改为专用安全 run 元数据；先脱敏、再计算摘要哈希，并对整个已投影 payload 施加 64 KiB 上限。70 KiB 输出与低熵秘密回归证明不保存原始 output 或其哈希。取消不确定执行后清除恢复投影，重启保持 CANCELLED。

### 2026-07-27 — IMPL-MVP-2-FINAL-REWORK-D

- **审批与停止语义：** 删除审批 ID 仅作为 Registry 消费传输字段，策略只接收已剥离该字段的精确删除动作；ApprovalManager 在消费事务内核对预期 task_id。此处曾把 brief 的“连续 2 轮”错误解释为基线后的第三次失败才停机；整阶段最终复审已按 brief 冻结示例纠正为第一条观察后，相同类别且失败数相同或恶化的第二次评估立即 `WAITING_USER/NO_PROGRESS`，指纹与总验证预算仍优先。
- **删除审批端到端矩阵：** 将原 2 项集成测试扩展为 13 项，全部使用迁移后的真实 SQLite、`Task`/`TaskRepository`、`ApprovalManager`、`PolicyEngine`、两个独立 `ToolRegistry`、真实 JSON UUID 与磁盘文件。覆盖无审批、pending、rejected、expired、过期 scope/event/config、跨 task、替换 path/SHA、replay、双连接并发消费，以及审批消费后删除前的确定性外部改写；所有拒绝均核验文件内容和 `approvals.consumed_at`，成功/并发/消费后 CAS 分支均核验恰好一次真实删除调用。
- **TDD 与资源清理：** 生产漏洞已在前序返工关闭，因此新增 11 个收集用例首次运行即与既有 2 项一起直接 GREEN（`13 passed`），未发现需要修改生产代码的新 RED。并发以 `asyncio.Barrier` 同步启动，不使用 sleep；消费后改写通过窄包装真实 `delete_regular_file` 确定性注入。每个数据库均由 fixture 或 async context 的 `try/finally` 在 2 秒边界内关闭，并发任务在 `finally` 取消并回收，断言失败也不遗留 aiosqlite 工作线程。
- **聚焦验证：** 删除审批 integration、Registry、ApprovalManager、PolicyEngine 与反馈引擎合计 `243 passed`。本轮只补测试矩阵和过程证据，未修改生产实现、联网、安装依赖、merge 或 push；最终 Ruff、mypy 与差异门禁在 amend 前重新取得新鲜输出。

### 2026-07-27 — IMPL-MVP-2-FINAL-CROSS-STAGE-REWORK

- **审查核实与 TDD：** 完整读取 MVP-2 整阶段最终复审和 Task 6 brief，使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development` 与 `verification-before-completion`。新增测试首轮为 `17 failed, 34 passed, 1 skipped`：第二次相同/恶化仍错误进入 `CORRECTING`；Registry 没有结构化 observation 且 Provider 收不到 read/普通失败；tracked/untracked/config 在 runner 返回前变化仍可能签发成功证据或未返回冻结竞态码。失败均对应 3 个 Important，未出现无关 RED。
- **真实观察闭环：** 新增严格 `ToolObservation`。Registry 从 `BoundedFileReader` 实际返回的原始 bytes 计算 read SHA-256，并为 read/search/Git 成功输出及普通工具失败生成 file/output/failure 观察。Orchestrator 在 EventStore 前统一用同一 Redactor 投影，施加 16 KiB 字段、24 KiB observation、最多 4 条/32 KiB Provider 观察预算；只回灌上一条 `LLM_RESPONSE_RECEIVED` 后的近期观察，并以 `UNTRUSTED_TOOL_OBSERVATION`/BEGIN/END 数据边界标记，超限或无效结构 fail closed。观察驱动 Mock 从真实 read observation 解析首个 CAS SHA，第二个 SHA 从自己上一条 patch 内容派生；反馈到达后才改变第二次 patch，文件秘密和原始 patch 均不落盘或进入后续请求。
- **验证竞态与 3/8/2：** `run_verification` 保留 pre-run profile/snapshot，runner 成功后重建 post 上下文；任一 post 不可用、trust/config 变化或 worktree 指纹不等均返回可重试的 `WORKTREE_CHANGED_DURING_VERIFICATION`，evidence 固定为 `None`。真实 tracked/untracked/config 三类 runner 均不能进入最终审查，后续 CompleteAction 返回 `VERIFICATION_REQUIRED`。反馈无改善按 brief 的两次调用冻结；failure_count 下降、类别变化或未知计数继续修正，第三次同 fingerprint 和第八次总预算仍按原优先级停机。
- **聚焦证据与范围：** agent（含真实闭环）、verification/Registry/search、feedback、C3 redaction、storage、providers 合计 `156 passed, 1 skipped`；单独三机制组合为 `51 passed, 1 skipped`，Ruff 通过，mypy 检查 39 个源文件无问题。未运行全量测试，未联网、安装依赖、merge 或 push；本提交完成后仍需独立规约符合性与代码质量复审。
- **最终复审 observation 纠偏：** 唯一 Important 复现为 `11 failed, 8 passed`：`run_verification` 的 STALE_CONFIG、approval、policy 和三类 worktree 竞态失败均没有 failure observation，普通验证失败下一请求也只有 runner 输出而缺稳定 code。`_with_observation()` 现仅允许成功验证不生成通用观察，所有失败统一产生 `kind=failure`、稳定 code 与有界 diagnostic；验证反馈固定为 `RESULT_CODE` 加 `UNTRUSTED_RUNNER_OUTPUT` 数据段，runner 的“1 passed”不能再遮蔽 `WORKTREE_CHANGED_DURING_VERIFICATION` 或被表述为验证成功。tracked/untracked/config 真实集成均断言无 evidence、完成不放行、下一 Provider 请求含失败 observation/code/不可信 runner 标签；普通 `VERIFICATION_FAILED` code 可见，C3 脱敏与限长测试继续纳入最终聚焦。最终限定的 agent/真实闭环、verification、feedback 与 redaction 为 `99 passed`。

### 2026-07-27 — REVIEW-MVP-2-FINAL-CLEAN

- **整阶段最终复审：** 受审范围 `07dfa31..c75c26a`。原 3 个 Critical、5 个 Important，以及返工后发现的工具观察回灌、验证期间 worktree 竞态、brief 冻结两轮停机和验证失败 code 可见性均已关闭；最终结论为 Spec compliant、Critical / Important / Minor `0 / 0 / 0`、Ready to merge。
- **主控新鲜门禁：** `scripts/test.ps1 -Mode All` 得到 `620 passed, 15 skipped`；Ruff、mypy（39 个源文件）、Web ESLint、TypeScript typecheck、`pip check` 与 `git diff --check 07dfa31..HEAD` 全部通过，工作树在写入本记录前干净。
- **状态与范围：** MVP-2 Task 5/6 完成，等待按既定选择本地合并到 `p1`；未联网、安装依赖、push 或处理 `MVP-ISSUE-016`。

### 2026-07-27 — MERGE-MVP-2-TO-P1

- **本地集成：** 按用户既定选择，将 `codex/agent-loop` 以 fast-forward 从 `6e9c805` 合并到 `p1`，保留 Task 6 与四个整阶段返工的独立提交记录；未执行 pull、push 或任何网络请求。
- **合并后验证：** 在 `p1` 重新运行 `scripts/test.ps1 -Mode All`，得到 `620 passed, 15 skipped`；Ruff、mypy、Web ESLint、TypeScript typecheck、`pip check` 与 `git diff --check 07dfa31..HEAD` 全部通过。
- **清理事实：** Git worktree 注册与本地分支 `codex/agent-loop` 已删除，两个依赖 junction 只删除链接本身且主仓库依赖仍存在。Windows 进程仍短暂占用已清空的 `.worktrees/agent-loop` 目录，三次安全重试后仅保留空目录；不含代码或状态，不影响 Git 与产品验证。

### 2026-07-27 — IMPL-MVP-3-TASK-7-REST-SSE

- **范围与技能：** 在隔离 `codex/api` worktree 实现 MVP-3 Task 7；已完整阅读 `AGENTS.md`、Task brief、批准计划与规约，使用 `test-driven-development`、`systematic-debugging`、`verification-before-completion`。未联网、安装依赖、修改 001/002、merge 或 push；未实现 WebUI、记忆、凭据、host transfer 或真实 Provider。
- **RED → GREEN：** 首轮 `tests/api tests/storage/test_workspace_repository.py` 因 `coding_agent_harness.api` 不存在稳定收集失败，证据保存在 `.superpowers/sdd/task-7-report.md`。随后以真实 SQLite、真实迁移、真实 ProjectDetector/WorkspaceScanner/WorktreeManager 与 SSE 测试转绿。调试中按堆栈定位并修复 FastAPI Query 参数位置、严格 JSON tuple 往返、UUID 显式边界解析与任务工作树构造遗漏的状态枚举；未使用 sleep 型并发。
- **实现事实：** 新增 003 workspace 迁移和严格 `WorkspaceRepository`，持久化规范路径、profile JSON、信任指纹及信任状态；旧不完整行固定拒绝。FastAPI 工厂以依赖容器注入存储、扫描器、任务 runner 和编排器；项目接入只接受本地 Git 根且拒绝 state_root 重叠，信任必须重新检测精确 fingerprint。mutation 采用同源 Origin 与常量时间会话 token 门禁，错误统一为脱敏固定体；任务创建使用真实隔离 worktree，默认停在计划审批；SSE 按持久化序号续传。
- **新鲜验证：** `pytest tests/api tests/storage tests/governance tests/agent -q` 为 `407 passed, 2 skipped`；Ruff、mypy（46 个源文件）和 `git diff --check` 通过。wheel/sdist 构建成功，归档检查均证实 001/002/003 各一份。待独立规约符合性和代码质量复审后才可将计划状态改为完成。

### 2026-07-27 — REWORK-MVP-3-TASK-7-SPEC

- **审查核实与 TDD：** 使用 `receiving-code-review`、`test-driven-development`、`systematic-debugging` 与 `verification-before-completion` 完整核实 Task 7 规约审查的 3 Critical、7 Important、1 Minor。新增真实 AgentOrchestrator/ScriptedMockProvider 计划门禁、非法最终批准、配置改变后零任务、SSE token canary、摘要和框架错误形状回归。
- **实现收敛：** 默认服务不再伪造状态；缺失真实 runtime 时 task/编排端点固定 503，测试注入真实事件驱动 AgentOrchestrator。任务启动前复检 profile/fingerprint 并原子撤销过期信任；事件流在响应边界 Redactor 脱敏并屏蔽宿主私有字段；项目响应返回有界无源码摘要；框架 404/405/422 使用固定错误体。分支解析改为注入的 SafeGit，003 使用 path_key root_key 唯一，重复信任不刷新时间，并提供任务读取端点。
- **新鲜验证：** API/storage 聚焦 `13 passed`；storage/governance/agent 回归 `399 passed, 2 skipped`；Ruff、mypy（46 files）、build、wheel/sdist 001/002/003 各一份和 diff check 均通过。未联网、安装、merge、push 或扩展 Task 8。

### 2026-07-27 — REWORK-MVP-3-TASK-7-SPEC-ROUND2

- **二轮返工：** 仓库摘要在 API 边界经 Redactor 投影并有总量上限，commit canary 不下发；默认路径选择抽成纯函数。新增独立 `test_migration_003.py`，覆盖 fresh 001→002→003、真实 v2 仅 003、v3 不重放 DDL 与未来版本拒绝；真实 API 回归补充摘要 canary、重复信任、过期信任、非法最终批准与读取状态。
- **证据：** `tests/api tests/storage/test_workspace_repository.py tests/storage/test_migration_003.py -q` 为 `17 passed`；后续回归、静态检查、构建和归档在 amend 前重新执行。

### 2026-07-27 — REWORK-MVP-3-TASK-7-SPEC-ROUND3

- **测试补强：** 新增默认无 runtime 的真实 app/SQLite 零任务零 worktree 回归；真实 Agent 五事件计划序列；Windows 扩展命名空间 helper 与 SQLite alias（Windows 条件）；v2 approval 全字段快照；配置纯函数四平台路径分支和显式覆盖。未改生产代码。

### 2026-07-27 — REWORK-MVP-3-TASK-7-SPEC-ROUND4

- **零副作用回归：** 过期信任用例现在在修改配置前后比较真实 SQLite task 数、state_root 的递归相对条目快照，并以记录型 TaskRunner 断言 create 调用为零；因此可证明 409 `STALE_PROJECT_TRUST` 发生在任务、active marker、目标 worktree 或分支副作用之前。

### 2026-07-27 — REWORK-MVP-3-TASK-7-QUALITY-QA

- **范围与技能：** 仅修复质量审查 C1、I1、I3；使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development` 与 `verification-before-completion`。未处理 QB/QC，未联网、安装、merge、push，也未运行 399 回归或构建。
- **RED → GREEN：** 未知 `evil.example` Host 原可先取得 token 再进入 mutation 业务依赖，启动构造失败时数据库关闭次数为 0，且数据库可显式落在私有状态根外。现由冻结 `HarnessSettings` 提供可信 Host/Origin 与私有路径：所有请求在路由前校验 Host，mutation 额外校验配置 Origin 和常量时间 session，首页使用 `Cache-Control: no-store`；自建数据库打开后立即受 `try/finally` 保护；数据库必须位于 `state_root`，数据库/WAL/SHM 父目录均参与项目重叠拒绝。
- **验证事实：** Repository、Scanner、SafeGit、runtime 四类真实 lifespan 故障注入均关闭自建数据库恰好一次，外部注入数据库保持可用；聚焦测试 `30 passed`、API `22 passed`、含 workspace repository/003/config 的规约集合 `43 passed`。静态检查与差异门禁在提交前重新取得新鲜证据。

### 2026-07-27 — REWORK-MVP-3-TASK-7-QUALITY-QB

- **范围与技能：** 仅处理质量审查 I2、I4、I5；完整核对 Task 7 brief、质量报告、QA 复审、Agent 状态机、Provider 层级与 worktree 副作用契约，并使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development` 和 `verification-before-completion`。未处理 QC、未联网或安装依赖，未运行全量/构建，也未 merge/push。
- **RED → GREEN：** Agent 首个 RED 为缺少 `record_runtime_failure`（`1 failed`）；API 故障矩阵与响应性首轮为 `9 failed, 2 passed`，取消收敛探针单独为 `1 failed`。GREEN 后，Detector、Scanner、SafeGit 分支解析和 WorktreeManager 创建均经同一依赖级 `CapacityLimiter` 的 worker thread；事件循环内的并发首页探针在三类只读端口执行期间均返回 200。worktree 创建与 Task 所有权持久化由 shielded task 收敛，取消后先等待线程及数据库结果，再传播取消；无法观察的内部取消固定升级为 `WorktreeUncertainError`，不遗留未观察 task。
- **故障一致性与分类：** Provider/ScriptedMock 计划失败通过 `AgentOrchestrator.record_runtime_failure` 和合法 `USER_INPUT_REQUIRED` 事件幂等转为 `WAITING_USER`，payload 经既有 Redactor/限长投影；API 返回 `503 PROVIDER_UNAVAILABLE` 并携带 `details.task_id`，GET 可读取任务和 reason 事件，真实 worktree 与 `.active` 保留。重复 POST 从受控 active marker 取回原 task ID 并返回 `409 WORKSPACE_BUSY`，不创建第二 worktree；损坏 marker 固定升级为 `WORKTREE_UNCERTAIN`。路由只捕获 busy/conflict、uncertain、`TaskStateError`、`ProviderError`/`ScriptExhaustedError` 和 `RuntimeUnavailableError`，factory 使用同一类型边界；未知异常仍由全局 500 脱敏处理。
- **新鲜限定验证：** API 全套 `38 passed`；Agent 全套加 worktree/process 回归 `127 passed, 1 skipped`；Ruff 为 `All checks passed!`，mypy 为 `Success: no issues found in 46 source files`。唯一 skip 为既有平台能力门禁；未运行全量或构建。差异检查在提交前单独执行。

### 2026-07-27 — REWORK-MVP-3-TASK-7-QUALITY-QB-REREVIEW

- **复审核实与范围：** 完整读取 QB 独立复审并使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development` 与 `verification-before-completion`；只修复两个 Important，不触碰 QC。根因是 task/worktree 落盘后的未知 propose 异常仍交给无 task 上下文的全局 500，以及 `_orchestrator_task` 把无领域含义的裸 `KeyError` 与 `TaskStateError` 合并捕获。
- **RED → GREEN：** 未知 propose 与故障记录二次异常的首轮为 `2 failed, 10 passed`；裸 KeyError 精确矩阵为 `1 failed, 4 passed`。GREEN 后，未知 propose 固定返回脱敏 `500 INTERNAL_ERROR` 且 `details.task_id` 指向真实已持久化任务，并 best-effort 调用公共 `record_runtime_failure`；故障事件记录自身异常被脱敏吞掉，Provider 原 `503` 与 task ID 仍保留，GET 仍能定位任务。`_orchestrator_task` 只将 `TaskStateError` 映射为 409，裸 KeyError 由全局边界返回脱敏 500。
- **新鲜验证与边界：** 三类复审聚焦 `7 passed, 16 deselected`；API 全套 `41 passed`；Ruff 通过，mypy 检查 46 个源文件通过。未运行全量或构建，未联网、安装、merge、push；差异检查在提交前执行。

### 2026-07-27 — REWORK-MVP-3-TASK-7-QUALITY-QC

- **范围与技能：** 仅处理质量审查 I6、I7、M1；完整读取 Task 7 brief、质量报告及 QA/QB 复审，使用 `systematic-debugging`、`test-driven-development` 和 `verification-before-completion`。未修改 QA/QB 行为，未联网、安装依赖、运行全量/构建、merge 或 push。
- **RED → GREEN：** 30,000 个 CJK 字符（90,000 UTF-8 bytes）原被 API 以 201 接受且 Repository 静默替换，首轮为 `2 failed`；持久化 `git_root` 或独立 `trust_fingerprint` 列被篡改后仍可读取，首轮为 `2 failed, 1 passed`；EventStore 缺少有界批次接口、SSE 使用无界读取且超大事件丢失信封，首轮为 `3 failed`。GREEN 后三组聚焦依次为 `2 passed`、`3 passed`、`3 passed`。
- **实现事实：** 任务需求统一经共享 `MAX_REQUIREMENT_BYTES` 的 UTF-8 字节规则验证，API 超限固定 422 且任务表、state_root/worktree 无副作用，Repository 保留同规则的防御性拒绝而不再静默改写。Workspace 恢复分别规范化 root/git_root，要求二者路径键均等于持久化 root_key 且物理同一，并核对 profile 与独立信任指纹列。EventStore 提供上限 100 的公共批次读取；SSE 以 sequence 游标固定分批，超大事件只替换 payload 并保留完整 TaskEvent 信封。
- **限定验证：** 四个直接相关测试文件为 `53 passed`，API + storage 回归为 `89 passed`；Ruff 和 mypy（47 个源文件）通过。最终差异检查和提交前新鲜证据另行取得。

### 2026-07-27 — REWORK-MVP-3-TASK-7-QUALITY-QC-REREVIEW

- **复审核实与范围：** 完整读取 QC 独立复审，使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development` 与 `verification-before-completion`；仅修复 I6 的脱敏扩张时点，不修改已通过的 I7/M1 或 QA/QB。
- **RED → GREEN：** 真实 API/Git/SQLite 回归使用 `token=x ` 重复 8,192 次，证明原始值恰为 65,536 UTF-8 bytes、经实际 Repository Redactor 后超限；首轮稳定返回 500，而正常未扩张的 65,536-byte 需求为 201。修复后扩张输入固定为 `422 VALIDATION_ERROR`，真实 task 计数为 0，workspace worktree 目录、`.active` 和 state_root 条目均无新增；正常边界仍为 201 且持久化内容精确一致。
- **单一准备边界：** `TaskRepository.prepare_requirement()` 是唯一的原始字节校验、真实 Redactor 脱敏和最终字节校验路径，产出 `PreparedRequirement`；`LocalTaskRunner` 在启动 worktree worker 前完成准备，随后 `create_prepared()` 只复用该结果。仅明确的 `RequirementTooLargeError` 在 API 映射为 422，既有未知 `ValueError` 继续由内部错误边界映射为脱敏 500。
- **限定验证：** 四项 I6 聚焦为 `4 passed`；API + storage 回归为 `91 passed`，mypy 检查 47 个源文件通过。Ruff、差异检查和提交前状态在提交前重新取得；未联网、安装、运行全量/构建、merge 或 push。

### 2026-07-27 — REWORK-MVP-3-TASK-7-FINAL-I1-I2

- **范围与技能：** 仅处理 Task 7 整阶段最终审查 I1/I2；完整读取 Task brief、最终质量报告及 QA/QB/QC 复审，使用 `systematic-debugging`、`test-driven-development` 与 `verification-before-completion`。未处理 M1，未联网、安装、运行全量/构建、merge 或 push。
- **RED → GREEN：** 真实 Git/SQLite/API 首组 RED 为 `7 failed`：SQLite trigger 使 Task 插入失败后原响应为 500，detector/scanner/branch 的六项未知 `RuntimeError`/`ValueError` 均被误报为 400。补偿不确定分支的变异 RED 证明，不执行所有权校验时会谎报普通存储失败。GREEN 后，存储失败只安全释放本次 task worktree；成功补偿固定为可重试的 `503 TASK_STORAGE_UNAVAILABLE`，所有权变化、清理失败或结果不确定固定为 `503 WORKTREE_UNCERTAIN` 并保留其他 owner 的 marker/目录。移除 SQLite 故障后同一 Workspace 可重试成功，不存在幽灵 owner。
- **异常边界：** 项目路径与默认分支使用专用领域异常；只有路径解析/私有状态重叠、项目检测、仓库扫描和默认分支领域失败返回 400。依赖端口的未知内置异常由全局边界脱敏为 500，不再伪装用户输入错误。
- **限定证据：** 核心与不确定分支 `8 passed`，task/project 聚焦 `43 passed`，API + worktree + storage 组合回归 `147 passed, 1 skipped`；静态检查和差异门禁在提交前重新取得。

### 2026-07-30 — CLOSE-MVP-3-TASK-7-PROCESS-GATE

- **技能与状态核对：** 使用 `subagent-driven-development`、`requesting-code-review` 与 `verification-before-completion` 恢复 Task 7 收尾；以 `p1` 的 `340edfb` 为基线核对 `codex/api` 的七个技术提交 `b706439..9691b03`，工作树在过程回填前保持干净。
- **独立复审结论：** QA、QB、QC 的限定复审均已清零；整阶段最终技术复验确认 SQLite 落盘补偿、worktree 不确定状态和项目异常边界已关闭，Technical Spec 为 Yes、Technical Quality 为 Approved，Critical / Important / Minor 为 `0 / 0 / 0`。
- **延期审计：** Task 7 的 Workspace 持久化、REST/SSE、同源会话防护、运行期恢复、UTF-8 数据边界和有界事件流均已交付，没有遗漏发布必需范围；本 Task 无新增延期，也未改变既有 `DW-05-001` 与 `DW-MVP-001`—`DW-MVP-006`。WebUI、三机制演示、Docker 和双 CI 仍属于后续未开始 Task，不在本 Task 伪装为延期。
- **待执行门禁：** 本条仅关闭 PLAN/日志/延期声明的过程缺口；主控仍须在当前 Head 上取得全量测试、Ruff、mypy、Web lint/typecheck、`pip check`、wheel/sdist 构建、003 归档矩阵和差异检查的新鲜证据，随后才能宣布 Task 7 完成或本地合并。

### 2026-07-30 — REWORK-MVP-3-TASK-7-FINAL-C1-I1

- **范围与技能：** 只处理最终独立审查 C1/I1；完整读取 Task 7 brief、final review、既有报告与仓库约束，使用 `systematic-debugging`、`test-driven-development` 和 `verification-before-completion`。未扩张到 WebUI/Task 8、联网、依赖、凭据管理、全量构建、merge 或 push。
- **RED：** C1 的真实 SQLite canary 探针为 `1 failed`，证明敏感命令赋值可进入 `profile_json`；I1 的 Agent 状态机与真实 ASGI/SQLite/Git Provider barrier 为 `2 failed`，证明 CREATED 无合法等待恢复路径且请求取消后任务停在 PLANNING。所有失败输出只描述布尔/状态，不回显 canary 值。
- **GREEN 设计：** Workspace 仓储在完整 profile 序列化后、任何 INSERT 前调用既有 Redactor，命中敏感规则即抛固定领域错误且不持久化脱敏副本；现有行恢复和信任更新入口复用同一 fail-closed 判定。任务路由先分配 task ID；计划操作在独立可观察任务中运行，取消时先取消并收敛 Provider，再以公开 `record_runtime_failure` 和固定 `REQUEST_CANCELLED` 事件恢复为 WAITING_USER，恢复落盘后原样传播取消；重复取消由 barrier 验证不会遗留后台任务。
- **验证事实：** C1 聚焦 `3 passed`，I1 核心 `2 passed`，四个直接相关文件 `70 passed`。限定 API+storage+agent+worktree 回归首轮唯一失败为冻结状态机契约未包含新合法迁移；更新契约后新鲜重跑为 `219 passed, 1 skipped`。Ruff 通过，mypy 检查 47 个源文件通过；提交前另行取得差异与工作区检查证据。
