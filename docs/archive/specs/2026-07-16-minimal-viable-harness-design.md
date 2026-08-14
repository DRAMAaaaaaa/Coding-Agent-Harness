# 最小可用 Coding Agent Harness 设计

## 1. 决策背景

原计划按 14 个 Task 横向补齐所有能力，已经完成 Task 1—4，并在 Task 5 交付了项目识别、仓库地图和 worktree 的大部分实现。最终整分支冷审查发现 Task 5 仍存在会绕过路径隔离或隐式执行仓库代码的安全缺口，因此 Task 5 不能合并。

本设计把后续工作收缩为一个可验收纵向切片：首版只要求 Scripted Mock LLM 驱动完整 Harness 流程，保留 DeepSeek/Qwen 通用接口但不以真实联网调用作为验收条件。Python 和 Node.js 项目均保留。

## 2. MVP 目标

程序员能够在 WebUI 中选择本地 Git 项目、输入编码需求、审阅计划，并让 Harness 在独立 worktree 中通过受治理工具修改代码。测试失败必须形成确定性反馈，Mock Agent 收到反馈后改变下一动作，最终交付可运行代码、测试证据、Git diff 和基于事实的文档。

首版必须同时满足：

- Agent 循环、动作解析、工具调度、治理、反馈和停止逻辑由本仓库实现。
- Python 与 Node.js 项目能够识别验证命令并生成变化可失效的信任指纹。
- 默认先审批计划；危险动作由确定性策略拦截，审批不能提升路径能力。
- 每个写任务使用独立 worktree，主工作区不被提前修改。
- Mock LLM 测试、机制演示和浏览器 E2E 完全离线、无需 API Key。
- 提供一键测试、Docker WebUI、GitHub Actions 和 GitLab `unit-test`。

## 3. 明确不进入首版的能力

- 长期记忆、向量检索和跨任务经验推荐。
- 多 Workspace 并发调度和多 Agent 并行执行。
- 任意 Shell、交互式终端和可扩展第三方工具生态。
- 真实 DeepSeek/Qwen 联网验收；首版只保留 Provider 接口。
- Git push、merge、release、依赖安装和工具网络请求。
- 高级凭据管理界面、主题、动画、高级筛选和多浏览器矩阵。
- Git LFS、加密 filter 或其他外部 checkout filter 的正式执行；MVP 必须在运行外部 filter 前拒绝并说明限制。

这些内容不得伪装成已经完成；实施计划必须把合法延期登记到 `DEFERRED_WORK.md`。

## 4. 架构边界

### 4.1 项目入口层

负责路径身份、Git 安全执行、项目识别、仓库地图、配置指纹和 worktree 生命周期。路径比较必须统一普通 Windows 路径、扩展 drive 和扩展 UNC 的可证明别名；设备命名空间和无法证明安全的关系固定拒绝。所有 containment 检查都必须发生在文件探测或目录创建之前。

内部 Git 命令使用绝对 Git 可执行文件和受控环境。安全基线至少包括：

- `core.fsmonitor` 使用空值禁用，不能使用在旧 Git 中会被解释为 hook 路径的 `false`。
- `core.hooksPath` 指向宿主私有、身份已验证的空目录。
- `git log` 强制 `--no-show-signature`；后续 diff 强制禁用 external diff/textconv。
- 清除继承的 Git 配置注入、外部 diff、SSH、askpass、对象替代和工作树覆盖变量；禁用协议、终端提示、懒拉取和后台维护。
- `worktree add` 先使用 `--no-checkout`，在 materialize 前审计活动 filter；MVP 发现外部 filter 固定拒绝，不执行其 clean/smudge/process。
- status、add、materialize、release 和 remove 都使用同一安全边界，不能只保护扫描阶段。

### 4.2 Harness 核心层

核心层包含自有状态机、计划门禁、工具注册表、治理中间件、确定性反馈引擎和停止逻辑。允许的工具只有：

- `read_file`
- `search`
- `apply_patch`
- `run_verification`
- `git_status`
- `git_diff`
- `delete_file`（必须审批）

安装依赖、网络请求、Git push/merge/release 和任意 Shell 在首版固定拒绝。验证命令只能来自已批准且当前指纹仍一致的项目配置。

`apply_patch` 在同一 Workspace 内假定最多一个 Harness 写任务；同目录 `O_EXCL` 锁协调遵守协议的实例。创建用原子 no-replace，替换在持锁且最终 replace 前复验 SHA-256，已检测到的变化 fail closed。跨平台文件系统不提供按摘要条件原子 replace；忽略锁的同 UID 外部进程在最终复验与 replace 之间的竞争由 SPEC 9.2 明确排除，现场不确定时不自动回滚，转人工接管。

### 4.3 Provider 层

`ScriptedMockProvider` 按预置响应序列驱动演示，不根据隐藏网络服务生成答案。DeepSeek/Qwen 继续实现相同 Provider 协议，但真实调用不属于首版验收门禁。

### 4.4 服务与 WebUI

SQLite 保存任务、事件、审批和恢复所需状态；FastAPI 提供 REST 与 SSE。WebUI 只提供六项核心操作：项目接入、输入需求、批准计划、查看执行事件、处理危险动作审批、查看测试和最终 diff。

服务重启后可以恢复确定状态；已开始但结果不确定的副作用不得自动重放，任务进入人工处理状态。

## 5. 完整数据流

```text
项目接入与安全扫描
→ 验证命令信任
→ 输入需求
→ Mock 生成计划
→ 用户批准计划
→ 创建隔离 worktree
→ Mock 产生工具动作
→ 治理判定并执行
→ 验证失败形成结构化反馈
→ Mock 根据反馈改变下一动作
→ 验证通过与最终审查
→ WebUI 展示 diff、测试证据和交付文档
```

只有普通测试失败允许进入自动修正。路径拒绝、策略拒绝、审批失效、配置变化和副作用不确定必须停止或等待用户，不允许 Agent 自行绕过。

## 6. 确定性演示

仓库提供一个内置 Python 编码 fixture。Mock 第一次提交一个可预测的错误修改，验证器产生固定失败分类与指纹；第二次响应必须引用该反馈并产生不同动作，随后测试通过。演示还必须包含一个危险删除或高风险命令请求，由治理护栏确定性拦截。

Node.js 使用不依赖联网安装的固定 fixture 验证项目识别、信任指纹和验证命令。普通用户项目可以接入，但首版不会替用户安装依赖。

## 7. 验收标准

1. Python 演示从 WebUI 输入需求一直运行到最终 diff，且真实修改临时 Git worktree。
2. 第一次验证失败，反馈进入下一次 Mock 输入，下一动作与前一次不同并最终转绿。
3. 危险动作在工具执行前被拦截并记录原因。
4. Python/Node 配置首次执行要求信任；任一源配置变化使旧指纹失效。
5. Windows 路径别名、路径逃逸、Git fsmonitor/hooks/GPG/filter/环境注入均有离线回归测试。
6. `make test` 或 PowerShell 等价命令覆盖后端、前端和 E2E；核心 Mock 测试不联网。
7. GitHub Actions 每次 push 运行测试并构建镜像；GitLab 存在精确的 `unit-test` 作业。
8. Docker 能启动可操作的 WebUI；最终文档只陈述实际验证结果。

## 8. 实施单元

- **MVP-0：** 问题台账、范围、设计和精简计划。
- **MVP-1：** 安全项目接入、信任指纹和独立 worktree。
- **MVP-2：** 最小工具集、确定性反馈和 Agent 主循环。
- **MVP-3：** FastAPI、SSE 和最小 WebUI。
- **MVP-4：** 浏览器 E2E、三机制演示、一键测试、Docker、双 CI 和交付文档。

每个实施单元仍使用独立提交、红—绿—重构、规约审查、质量审查和主控新鲜验证。MVP-1 未通过前不得继续 Agent 执行主路径。

## 9. 设计结论

选择在现有实现上修复并纵向贯通，不重写已验证的 Task 1—4，也不继续原 14 Task 的横向扩张。首版的成功标准是“一个安全、真实、可重复、可演示的完整 Harness 流程”，而不是功能数量。
