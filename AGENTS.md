# 仓库协作说明

## 项目目的

构建一个以确定性反馈闭环为主要贡献的 Coding Agent Harness。最终交付的 harness 必须由本仓库自行实现，不得把核心能力委托给高层 Agent 框架。

## 强制 Superpowers 工作流

1. 使用 `brainstorming`，并获得用户对 `SPEC.md` 的批准。
2. 使用 `writing-plans` 生成 `PLAN.md`；计划必须列出准确的文件、依赖、预期先失败的测试和验证命令。
3. 开始实现前，安排不同类型的智能体仅依据 `SPEC.md` 和 `PLAN.md` 执行冷启动检查，并把发现记录到 `SPEC_PROCESS.md`。
4. 独立功能必须在隔离的 Git worktree 中开发。
5. 每项行为都必须采用红—绿—重构的 TDD 流程实现。
6. 每项任务完成后，先进行规约符合性审查，再进行代码质量审查。
7. 只有在验证证据仍然有效时，才可使用 `finishing-a-development-branch`。

在步骤 1—3 全部完成前，不得编写 harness 实现代码。

## Harness 实现边界

- Agent 循环、LLM 抽象、动作解析器、工具分发器、记忆、治理、反馈、配置和停止逻辑必须由本仓库代码实现。
- LLM 接口必须可注入，使 Mock/Stub 实现能够驱动确定性的离线测试。
- 不得使用 LangChain AgentExecutor、AutoGen、CrewAI、LlamaIndex Agents 等高层 Agent Runner 提供产品的循环或治理能力。
- 护栏和反馈验证器必须编码为确定性机制，不能只依赖提示词约束。

## 安全规则

- 禁止提交真实 API Key、Token、密码、私钥、凭据数据库、`.env` 文件或包含秘密的日志。
- `.env.example` 和文档只能使用占位值。
- 禁止在终端输出、测试、异常、快照或 `AGENT_LOG.md` 中回显凭据。
- 如果凭据发生暴露，必须立即停止相关工作、轮换凭据、从 Git 历史中移除泄露内容，并在不记录凭据值的前提下说明事故。

## 验证与过程证据

- 持续更新 `PLAN.md` 中的任务状态和提交哈希。
- `AGENT_LOG.md` 必须按时间顺序记录事实，包括使用的技能、相关上下文、智能体产出或提交、人工干预和经验总结。
- 宣称任务完成前，必须取得最新命令输出，证明相关测试、Lint/类型检查、构建和机制演示均已通过。
- 最终仓库必须提供一键测试、Mock LLM 机制覆盖、GitHub Actions、包含 `unit-test` 作业的 `.gitlab-ci.yml`、Docker 分发和可部署的 WebUI。

## 当前阶段

仓库仍处于实现前治理阶段。Brainstorming 设计及规约文档已经提交，当前等待用户对书面 `SPEC.md` 做最终复核；`PLAN.md` 尚未生成，陌生智能体冷启动检查也尚未执行。因此仍禁止编写 harness 实现代码。
