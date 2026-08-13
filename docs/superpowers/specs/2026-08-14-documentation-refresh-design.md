# 共学回放式 Coding Harness 文档整理设计

## 1. 背景与目标

当前仓库已经实现 Coding Agent Harness 的完整 Mock 主路径，并在原有 Agent 基础上增加意图卡、失败节点提问、纠正分支和项目经验，产品定位已经从“替程序员完成代码的 Harness”演进为“与用户一起学习的共学回放式 Coding Harness”。现有 README 仍以早期本地优先 MVP 为主，历史设计、计划、问题台账和已跟踪 subagent 报告分散在多个目录，初次阅读者难以区分当前产品能力、作业必交文档与历史过程证据。

本次只整理说明文档，不修改 Harness 运行行为。目标是让老师或新用户从 README 立即理解已经完成的功能和项目特色，同时完整保留课程要求的规约、计划、过程日志和 Git 证据。

## 2. 信息架构

整理后的主要结构为：

```text
README.md                    当前产品总览与快速开始
SPEC.md                      课程必交设计规约
PLAN.md                      课程必交实现计划
SPEC_PROCESS.md              课程必交规约过程
AGENT_LOG.md                 课程必交智能体工作日志
REFLECTION.md                学生本人填写的反思提纲
AGENTS.md                    仓库协作规则
docs/
  FEATURES.md                已完成功能、纵向用户流程与产品特色
  DEMO.md                    答辩演示脚本和验收结果
  DEPLOYMENT.md              本地、Docker、ECS 运行与撤销
  SECURITY.md                治理、凭据、公网和已知安全边界
  archive/
    README.md                历史证据索引与状态说明
    specs/                   历史 brainstorming 设计
    plans/                   历史实施计划
    ledgers/                 MVP 问题与延期台账
    reports/                 已跟踪 subagent 实现/审查报告
```

根目录课程必交文件继续保留标准名称，不移动。`docs/` 顶层只保留最终读者需要直接使用的四份说明文档；过程材料统一进入 `docs/archive/`。

## 3. 当前产品叙事

所有面向读者的介绍采用统一定位：

> 一个与程序员共同学习的 Coding Agent Harness。用户提交编码需求后，Harness 在隔离 worktree 中规划、修改、验证并交付代码；用户可以通过回放理解每一步意图，在失败节点提问或创建纠正分支，并把批准的经验带入下一项任务。

介绍只陈述已经由代码、测试或部署配置支持的功能：

1. 自研 Agent 主循环、动作解析、工具分发、停止逻辑和可注入 LLM 抽象，不依赖高层 Agent Runner。
2. WebUI 中的项目接入、需求提交、计划审批、任务运行、事件时间线、验证证据、diff 与最终批准。
3. 确定性反馈闭环：测试失败分类、稳定指纹、反馈回灌、动作改变和无进展停止。
4. 代码级治理护栏：危险删除、路径逃逸、高风险命令和未批准副作用在执行前拦截。
5. 每任务独立 Git worktree、配置指纹与受控验证命令。
6. 共学回放特色：意图卡、失败节点只读提问、单级纠正分支、比较视图和经用户批准的单条项目经验。
7. DeepSeek/Qwen Profile、会话型 API Key、脱敏连接测试和主动清除；真实 Provider 不写成已驱动完整 Agent 主循环。
8. 完全离线的 Scripted Mock、确定性单元测试、三机制演示和浏览器 E2E。
9. Docker、GitHub Actions、GitLab `unit-test` 以及阿里云 ECS 公网 IP Mock 演示配置。

未完成能力只放在“已知限制与后续方向”：生产级公网认证/HTTPS、真实 Provider 驱动完整 Agent、长期多条记忆、多 Agent 调度、任意依赖安装/网络/Git push 工具和最终视觉设计。文档不得把配置存在、离线 Stub 通过或待外部验收写成产品已经完成。

## 4. 精确文件处理

### 4.1 保留并重写/整理

- `README.md`：重写为当前产品首页，包含项目简介、特色、已完成功能、快速开始、演示、分发、目录结构、安全边界、已知限制和课程交付导航。
- `docs/DEMO.md`：改成可直接答辩的 Mock 纵向演示脚本，明确预期页面和三机制证据。
- `docs/DEPLOYMENT.md`：保留已验证命令，消除过时状态，区分本地 Mock、Docker 与未完成的 ECS 动态验收。
- `docs/SECURITY.md`：按治理护栏、路径/进程、凭据、记忆、公网和剩余风险重新组织。
- `SPEC.md`：保留批准规约正文，只更新已经移动的详细设计链接和必要的当前产品定位/交付状态，不重写历史决策。
- `PLAN.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md`：保留事实与时间线，只机械更新移动后的路径引用，并记录本次整理过程。
- `AGENTS.md`：更新延期台账路径和文档结构约定，不改变 Harness 工作流与安全规则。

### 4.2 新建

- `docs/FEATURES.md`：按“需求 → 计划 → 隔离修改 → 确定性验证 → 回放/提问/纠正 → 经验批准 → 交付”的用户流程解释功能，并用单独章节总结主要工程贡献。
- `docs/archive/README.md`：解释每类历史材料的用途，标注废止计划、当前替代计划和课程证据关系。
- `REFLECTION.md`：仅创建 1500–2500 字学生反思写作提纲、建议证据位置和“必须由学生本人撰写”的声明；不生成可直接提交的反思正文。

### 4.3 移动归档

- `docs/superpowers/specs/*.md` → `docs/archive/specs/`
- `docs/superpowers/plans/*.md` → `docs/archive/plans/`
- `MVP_ISSUES.md`、`DEFERRED_WORK.md` → `docs/archive/ledgers/`
- 已由 Git 跟踪的 `.superpowers/sdd/**/*.md` → `docs/archive/reports/`，保留原有子目录名称以避免报告重名。

本次不移动未跟踪、受忽略或只存在于本机的 `.superpowers` 文件，不删除 `.tmp/`、`.venv-py39-backup/` 或任何用户环境文件。

### 4.4 删除

不删除有内容的历史说明文档。完成移动并确认无跟踪文件后，空的 `docs/superpowers/` 和已清空的已跟踪 `.superpowers/sdd/` 路径由 Git 自然消失；这属于空目录消除，不是证据删除。

## 5. 链接与可追溯性

所有受影响的 Markdown 路径必须更新，重点包括：

- `docs/superpowers/specs/` → `docs/archive/specs/`
- `docs/superpowers/plans/` → `docs/archive/plans/`
- `MVP_ISSUES.md` → `docs/archive/ledgers/MVP_ISSUES.md`
- `DEFERRED_WORK.md` → `docs/archive/ledgers/DEFERRED_WORK.md`
- 已实际移动的 `.superpowers/sdd/` 报告 → `docs/archive/reports/` 对应路径

对日志中引用但从未被 Git 跟踪、当前也不存在的 `.superpowers` 临时报告，不伪造或新建文件；保留其历史文字，并在归档索引说明某些详细临时报告只存在于开发会话，Git 提交哈希和根过程文档才是最终证据。

## 6. 验收与测试

文档整理采用文档契约测试保护：

1. 根目录存在课程要求的 `SPEC.md`、`PLAN.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md`、`README.md`、`REFLECTION.md`。
2. README 包含课程要求章节，并明确“共学回放式 Coding Harness”、已完成功能和已知限制。
3. `docs/FEATURES.md` 只列可由源码/测试定位的功能，不使用“全部完成”“生产可用”等虚假措辞。
4. `docs/archive/` 包含索引，历史设计、计划、台账和已跟踪报告均已移动。
5. 不再存在被 Git 跟踪的 `docs/superpowers/*.md`、根 `MVP_ISSUES.md`、根 `DEFERRED_WORK.md` 或 `.superpowers/sdd/*.md`。
6. Markdown 相对链接、反引号路径引用和课程必交导航指向存在文件；历史临时报告引用作为明确例外登记。
7. 秘密扫描、`git diff --check`、文档契约测试和完整一键测试通过；文档移动不得改变 Harness 行为。

## 7. 提交策略

本次使用隔离 worktree 和 TDD。单一文档整理 Task 内分两次提交：先完成结构移动与链接修复，再完成面向用户的 README/FEATURES/DEMO/DEPLOYMENT/SECURITY 重写及课程交付索引。Task 完成后进行规约符合性与文档质量审查，最终合并到 `main` 前取得新鲜验证。

## 8. 批准记录

用户于 2026-08-14 要求：更新所有介绍文档，使其介绍最新的协助学习 Harness；介绍已经完成的功能和特色；整理现有文档，删除无用内容并保留需要提交的文档。用户随后选择把历史 Superpowers 设计与计划移动归档，并批准上述提交导向的目录结构。经盘点，本设计将所有有内容的历史说明作为过程证据移动保存，不做不可恢复删除。
