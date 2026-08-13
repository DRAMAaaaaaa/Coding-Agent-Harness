# 共学回放式 Harness 文档整理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把仓库文档整理成“当前产品说明 + 课程必交根文档 + 可追溯历史归档”，并以可定位的代码和测试证据准确介绍共学回放式 Coding Agent Harness。

**Architecture:** Task 1 只移动历史材料、建立归档索引并修复路径；Task 2 再重写当前读者文档和学生反思提纲。两个 Task 分别采用文档契约 RED/GREEN、独立提交和规约/质量双审查，产品代码、配置与运行行为保持不变。

**Tech Stack:** Markdown、Python 3.11、pytest、Git、现有 `scripts/secret_scan.py` 与 Makefile 门禁。

## Global Constraints

- 只修改说明文档与 `tests/distribution/test_delivery_files.py` 的文档契约，不修改 Harness、WebUI、部署配置或 CI 行为。
- 根目录必须保留 `README.md`、`SPEC.md`、`PLAN.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md`、`AGENTS.md`，并新增 `REFLECTION.md`。
- 有内容的历史文档只能移动归档，不能不可恢复地删除；Git rename 历史必须可追踪。
- `REFLECTION.md` 只提供 1500–2500 字写作提纲和证据导航，正文必须由学生本人撰写。
- 介绍只陈述当前 `main` 可由源码、测试或部署配置定位的能力，不把离线 Stub、内部方法、待合并分支或未执行的外部验收写成已完成入口。
- DeepSeek/Qwen 已有 Profile、会话凭据、固定端点、任务绑定和真实运行时；当前 `main` 没有 WebUI Probe/主动清除入口，也没有真实外网任务验收。
- 真实 API Key、Token、密码、私钥、`.env`、请求头、响应正文和隐私信息不得进入文档、测试、日志或 Git。
- 新建或修改的说明性文档与提交说明尽量使用中文；代码标识符、命令和标准文件名保持原样。
- 不触碰未跟踪的 `.tmp/`、`.venv-py39-backup/` 或未被 Git 跟踪的 `.superpowers` 文件。
- 每个 Task 在隔离 worktree 中完成 RED→GREEN→重构、规约符合性审查、质量审查和中文提交；Task 2 依赖 Task 1，不能并行。

---

## 文件结构与职责

```text
README.md                    当前产品首页、快速开始、分发、安全与课程导航
SPEC.md                      课程必交批准规约；只补当前定位和归档链接
PLAN.md                      课程必交总计划与本轮状态/提交哈希
SPEC_PROCESS.md              课程必交设计/冷启动/修订过程
AGENT_LOG.md                 课程必交按时间排序事实日志
AGENTS.md                    仓库协作规则与新文档结构约定
REFLECTION.md                仅学生本人可填写的 1500–2500 字反思提纲
docs/FEATURES.md             已完成功能、证据路径和共学纵向流程
docs/DEMO.md                 可直接答辩的确定性 Mock 演示脚本
docs/DEPLOYMENT.md           本地、Docker、ECS 启停与动态验收状态
docs/SECURITY.md             治理、隔离、凭据、记忆和公网风险
docs/archive/README.md       历史材料用途、状态与证据规则索引
docs/archive/specs/          历史详细设计
docs/archive/plans/          历史精确实施计划
docs/archive/ledgers/        历史问题和延期台账
docs/archive/reports/        Git 已跟踪的 subagent 实现/审查报告
tests/distribution/test_delivery_files.py
                             文档存在性、归档、链接、叙事真实性契约
```

## 实施前冷启动门禁

执行者必须先使用 `superpowers:using-git-worktrees` 从包含本计划提交的 `main` 创建 `codex/documentation-refresh`。随后安排一个不同类型的陌生审计员，只提供：

```text
SPEC.md
docs/superpowers/plans/2026-08-14-documentation-refresh.md
```

提示词固定为：

```text
仅依据给定规约和计划，选择 Task 1 或 Task 2 检查能否冷启动。
不要读取主对话、Git 历史或其他过程文档；不要修改文件。
发现路径、状态、验收或能力声明不明确时立即暂停并列出阻塞，禁止猜测。
```

主控把结论和必要修订写入 `SPEC_PROCESS.md`、`PLAN.md`、`AGENT_LOG.md` 并提交。只有审计结论为 READY，才开始 Task 1。Task 1 移动计划后，Task 2 使用的新规范路径是 `docs/archive/plans/2026-08-14-documentation-refresh.md`。

### Task 1：归档历史材料并修复路径

**Files:**
- Modify: `tests/distribution/test_delivery_files.py`
- Create: `docs/archive/README.md`
- Move: `docs/superpowers/specs/*.md` → `docs/archive/specs/*.md`
- Move: `docs/superpowers/plans/*.md` → `docs/archive/plans/*.md`
- Move: `MVP_ISSUES.md` → `docs/archive/ledgers/MVP_ISSUES.md`
- Move: `DEFERRED_WORK.md` → `docs/archive/ledgers/DEFERRED_WORK.md`
- Move: `.superpowers/sdd/2026-08-07-co-learning-replay-mvp/*.md` → `docs/archive/reports/2026-08-07-co-learning-replay-mvp/*.md`
- Move: `.superpowers/sdd/2026-08-07-real-providers-and-credentials/*.md` → `docs/archive/reports/2026-08-07-real-providers-and-credentials/*.md`
- Move: `.superpowers/sdd/task-6-report.md`, `task-7-report.md`, `task-10-report.md` → `docs/archive/reports/`
- Modify path references only: `README.md`, `SPEC.md`, `PLAN.md`, `SPEC_PROCESS.md`, `AGENT_LOG.md`, `AGENTS.md`, `docs/SECURITY.md`, all moved tracked Markdown files

**Interfaces:**
- Consumes: 当前 Git 跟踪清单、批准设计 `docs/superpowers/specs/2026-08-14-documentation-refresh-design.md`、本计划。
- Produces: `docs/archive/README.md`、稳定的 `docs/archive/{specs,plans,ledgers,reports}` 路径，以及 Task 2 可依赖的无断链文档树。

- [ ] **Step 1: 写入归档映射和失败契约**

在 `tests/distribution/test_delivery_files.py` 的 `ROOT` 后加入：

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
    "docs/superpowers/specs/2026-08-14-documentation-refresh-design.md": "docs/archive/specs/2026-08-14-documentation-refresh-design.md",
    "docs/superpowers/specs/2026-08-14-public-ip-mock-demo-design.md": "docs/archive/specs/2026-08-14-public-ip-mock-demo-design.md",
    "docs/superpowers/plans/2026-07-16-minimal-viable-harness.md": "docs/archive/plans/2026-07-16-minimal-viable-harness.md",
    "docs/superpowers/plans/2026-08-07-co-learning-replay-mvp.md": "docs/archive/plans/2026-08-07-co-learning-replay-mvp.md",
    "docs/superpowers/plans/2026-08-07-real-providers-and-credentials.md": "docs/archive/plans/2026-08-07-real-providers-and-credentials.md",
    "docs/superpowers/plans/2026-08-10-ci-powershell-tests.md": "docs/archive/plans/2026-08-10-ci-powershell-tests.md",
    "docs/superpowers/plans/2026-08-10-provider-webui-probe.md": "docs/archive/plans/2026-08-10-provider-webui-probe.md",
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

并加入：

```python
def test_historical_docs_are_archived_without_losing_evidence() -> None:
    assert (ROOT / "docs/archive/README.md").is_file()
    for source, target in ARCHIVE_MOVES.items():
        assert not (ROOT / source).is_file(), source
        archived = ROOT / target
        assert archived.is_file(), target
        assert archived.stat().st_size > 0, target
```

- [ ] **Step 2: 运行测试并确认 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py::test_historical_docs_are_archived_without_losing_evidence -v
```

Expected: FAIL；失败只因 `docs/archive/README.md`/目标文件尚不存在且旧路径仍存在。

- [ ] **Step 3: 用 Git 移动精确清单**

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

不得使用通配符移动 `.superpowers`，因为该目录可能含未跟踪或受忽略的本地报告。

Expected: `git status --short` 对每一项显示 `R`，`.tmp/` 与 `.venv-py39-backup/` 仍只是原有 `??`。

随后运行以下只读 Git 审计，精确证明旧位置不再被跟踪：

```powershell
git ls-files MVP_ISSUES.md DEFERRED_WORK.md docs/superpowers .superpowers/sdd
```

Expected: 无输出。Git 索引不是运行时产品行为，因此保持为显式验收命令，不放入一键产品测试。

- [ ] **Step 4: 建立归档索引**

创建 `docs/archive/README.md`，必须包含以下内容：

```markdown
# 历史过程材料索引

本目录保存 Coding Agent Harness 的设计演进、精确计划、问题台账和已由 Git 跟踪的 subagent 报告。它们是课程过程证据，不是当前产品使用说明；当前入口以仓库根 `README.md` 和 `docs/FEATURES.md` 为准。

## 目录

- `specs/`：历次 brainstorming 形成的详细设计。
- `plans/`：历次 `writing-plans` 形成的实施计划；勾选状态反映当时过程。
- `ledgers/`：MVP 问题与延期工作台账。
- `reports/`：已提交到 Git 的实现、规约审查或质量审查报告。

## 状态判读

- 根 `SPEC.md`、`PLAN.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md` 是最终课程过程入口。
- `2026-08-07-real-providers-and-credentials.md` 已被精简的 `2026-08-07-co-learning-replay-mvp.md` 取代，不能按旧计划的未勾选项判断当前完成度。
- 报告可能记录中间 RED、返工或旧 Head；最终状态以根过程文档、提交历史和最新验证为准。
- 日志中部分 `.superpowers` 临时报告从未被 Git 跟踪或当前不存在，不伪造补档；对应提交哈希与根过程文档是最终证据。
```

- [ ] **Step 5: 机械修复已移动路径引用**

使用 `rg -n "docs/superpowers|MVP_ISSUES.md|DEFERRED_WORK.md|\.superpowers/sdd" --glob "*.md"` 定位引用，然后通过 `apply_patch` 修复所有意图指向文件当前位置的引用：

```text
docs/superpowers/specs/  -> docs/archive/specs/
docs/superpowers/plans/  -> docs/archive/plans/
MVP_ISSUES.md            -> docs/archive/ledgers/MVP_ISSUES.md
DEFERRED_WORK.md          -> docs/archive/ledgers/DEFERRED_WORK.md
.superpowers/sdd/2026-08-07-co-learning-replay-mvp/ -> docs/archive/reports/2026-08-07-co-learning-replay-mvp/
.superpowers/sdd/2026-08-07-real-providers-and-credentials/ -> docs/archive/reports/2026-08-07-real-providers-and-credentials/
.superpowers/sdd/task-6-report.md  -> docs/archive/reports/task-6-report.md
.superpowers/sdd/task-7-report.md  -> docs/archive/reports/task-7-report.md
.superpowers/sdd/task-10-report.md -> docs/archive/reports/task-10-report.md
```

根过程文档中的活动导航必须使用新路径；归档设计/计划中描述“当时源路径”或本次迁移映射的历史文字不得改成自指向目标。仅对确实移动的七份报告替换 `.superpowers/sdd/` 路径。`AGENT_LOG.md`/`SPEC_PROCESS.md` 中从未跟踪且没有目标文件的临时报告引用保持原历史文本，不创建假文件。

- [ ] **Step 6: 增加当前文档链接契约并确认 GREEN**

在测试文件顶部增加 `import re`，再加入：

```python
def test_current_markdown_links_resolve_after_archiving() -> None:
    current = (
        "README.md", "SPEC.md", "PLAN.md", "SPEC_PROCESS.md", "AGENT_LOG.md",
        "AGENTS.md", "docs/DEMO.md", "docs/DEPLOYMENT.md", "docs/SECURITY.md",
        "docs/archive/README.md",
    )
    link = re.compile(r"\[[^]]+\]\((?!https?://|mailto:)([^)#]+)(?:#[^)]+)?\)")
    for relative in current:
        document = ROOT / relative
        for target in link.findall(document.read_text(encoding="utf-8")):
            resolved = (document.parent / target).resolve()
            assert resolved.exists(), f"{relative} -> {target}"


def test_current_process_docs_point_to_archive_instead_of_old_locations() -> None:
    current = ("README.md", "SPEC.md", "PLAN.md", "SPEC_PROCESS.md", "AGENT_LOG.md", "AGENTS.md")
    content = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in current)
    assert "docs/superpowers/" not in content
    assert "`MVP_ISSUES.md`" not in content
    assert "`DEFERRED_WORK.md`" not in content
```

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py -v
git diff --check
```

Expected: distribution 测试全部 PASS 或仅 Docker CLI 能力测试明确 SKIP；差异检查退出 0。

- [ ] **Step 7: 更新过程状态并进行双重审查**

在 `PLAN.md` 把 Task 1 标为“完成（提交待生成）”；在 `AGENT_LOG.md` 追加 worktree、RED/GREEN、移动数量、路径例外和未触碰用户文件。规约审查必须逐项核对 `ARCHIVE_MOVES`；质量审查必须检查断链、重复文档、历史语义被意外改写和未跟踪文件污染。Critical/Important 清零后再提交。

- [ ] **Step 8: 提交 Task 1**

```powershell
git add -A -- README.md SPEC.md PLAN.md SPEC_PROCESS.md AGENT_LOG.md AGENTS.md docs tests/distribution/test_delivery_files.py
git commit -m "docs: 归档历史过程文档"
```

Expected: 生成一个以 rename 为主的中文提交；把哈希回填到 `PLAN.md`/`AGENT_LOG.md` 的后续 Task 2 提交中。

### Task 2：重写当前介绍文档与课程交付导航

**Files:**
- Modify: `tests/distribution/test_delivery_files.py`
- Modify: `README.md`
- Create: `docs/FEATURES.md`
- Modify: `docs/DEMO.md`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `docs/SECURITY.md`
- Create: `REFLECTION.md`
- Modify: `SPEC.md`, `PLAN.md`, `SPEC_PROCESS.md`, `AGENT_LOG.md`, `AGENTS.md`

**Interfaces:**
- Consumes: Task 1 的 `docs/archive/` 稳定路径；当前代码证据 `src/coding_agent_harness/{agent,feedback,governance,learning,replay,providers,runtime.py}`、`web/src/App.tsx`、`scripts/mechanism_demo.py` 与现有测试。
- Produces: 面向读者的统一共学产品叙事、可答辩演示、准确安全/部署边界和课程交付导航。

- [ ] **Step 1: 把现有 README 契约改成当前叙事并写 RED**

将 `test_readme_documents_real_mvp_commands_and_limits()` 改为：

```python
def test_readme_documents_current_co_learning_product_and_limits() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in (
        "项目简介", "产品特色", "已完成功能", "安装", "运行", "演示",
        "分发", "目录结构", "安全边界", "已知限制", "第三方组件与许可证", "课程交付导航",
    ):
        assert f"## {heading}" in readme
    for phrase in (
        "共学回放式 Coding Agent Harness",
        "意图卡", "纠正分支", "项目经验", "ScriptedMockProvider",
        "尚未提供用户认证或 HTTPS",
        "WebUI 尚未提供连接测试和主动清除",
        "真实外网 Provider 任务尚未验收",
    ):
        assert phrase in readme
    for command in ("make test", "make test-unit", "make test-e2e", "make demo"):
        assert command in readme
    docker_runs = [line for line in readme.splitlines() if line.startswith("docker run ")]
    assert any(":/workspace/project:ro" in line and ":/state" in line for line in docker_runs)
```

再增加：

```python
def test_features_are_evidence_backed_and_reflection_is_student_authored() -> None:
    features = (ROOT / "docs/FEATURES.md").read_text(encoding="utf-8")
    for phrase in (
        "需求 → 计划审批 → 隔离修改 → 确定性验证 → 回放与纠正 → 经验批准 → 交付",
        "src/coding_agent_harness/agent/orchestrator.py",
        "src/coding_agent_harness/feedback/engine.py",
        "src/coding_agent_harness/learning/intent.py",
        "src/coding_agent_harness/replay/branches.py",
        "scripts/mechanism_demo.py",
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

- [ ] **Step 2: 运行测试并确认 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py::test_readme_documents_current_co_learning_product_and_limits tests/distribution/test_delivery_files.py::test_features_are_evidence_backed_and_reflection_is_student_authored -v
```

Expected: FAIL；原因是旧 README 标题/状态过时且 `docs/FEATURES.md`、`REFLECTION.md` 尚不存在。

- [ ] **Step 3: 重写 README 产品首页**

README 开头使用以下定位，不改写成营销承诺：

```markdown
# 共学回放式 Coding Agent Harness

## 项目简介

这是一个与程序员共同学习的 Coding Agent Harness。用户提交编码需求后，Harness 在隔离 worktree 中规划、修改、验证并交付代码；用户可以通过回放理解每一步意图，在失败节点提问或创建单级纠正分支，并把批准的项目经验带入下一项任务。
```

其余章节按测试规定的顺序组织，并满足：

- “产品特色”突出可解释回放、确定性反馈闭环、代码级治理和经用户批准的学习，不宣称通用自主开发。
- “已完成功能”链接到 `docs/FEATURES.md`，列出自研循环、WebUI 主路径、反馈、治理、worktree、共学、Provider 接线、Mock 测试、双 CI 和 Docker。
- “安装/运行/演示/分发”保留现有可执行命令、只读项目挂载、状态卷、WebUI 地址和安全 Key 配置方式。
- “安全边界”链接到 `docs/SECURITY.md`；明确公网 HTTP 无认证、真实 Key 不用于公网 Mock 演示。
- “已知限制”准确写明 WebUI Probe/主动清除、真实外网 Provider 任务、HTTPS/认证、多条长期记忆、多 Agent、依赖/网络/Git push 工具和最终视觉设计尚未完成。
- “第三方组件与许可证”从 `pyproject.toml`、`web/package.json`、已安装包元数据或依赖上游许可证文件核对后列出直接运行依赖与主要构建/测试工具；不得猜测许可证，无法从本地证据确认时只链接其上游 LICENSE 并标明需学生复核。
- “课程交付导航”链接根五份必交过程文档、`REFLECTION.md`、`.gitlab-ci.yml`、`docs/DEMO.md` 和 `docs/archive/README.md`。

- [ ] **Step 4: 创建可定位的功能说明**

创建 `docs/FEATURES.md`，一级结构固定为：

```markdown
# 已完成功能与产品特色
## 一条完整的共学交付路径
## 自研 Harness 内核
## 确定性反馈闭环
## 治理、隔离与停止
## 意图回放、提问与纠正
## 经批准的项目经验
## Provider 与 Mock 边界
## 工程化交付
## 已知限制
```

第一节必须原样出现流程句：

```text
需求 → 计划审批 → 隔离修改 → 确定性验证 → 回放与纠正 → 经验批准 → 交付
```

每个功能段至少给出一个反引号代码证据路径和一个测试/演示证据路径。Provider 段明确：真实运行时已接线；WebUI Probe/主动清除和真实外网任务验收未完成；公网答辩继续使用确定性 Mock。

- [ ] **Step 5: 重组演示、部署和安全说明**

`docs/DEMO.md` 固定为“准备 → 5 分钟 WebUI 主路径 → 三机制证据 → 结束检查”：演示项目接入、需求、计划批准、运行、意图卡、失败提问、纠正分支、比较、项目经验批准与最终交付；三机制继续使用 `make demo`，不得触网。

`docs/DEPLOYMENT.md` 保留已经验证的源码、Docker、Compose 和 ECS 命令；把状态明确分成：静态配置/测试已通过、Docker daemon/Nginx 容器/ECS 外网浏览器仍需实机验收、演示后撤销 80 端口。

`docs/SECURITY.md` 按以下顺序整理：

```markdown
## 治理护栏
## 工作区、worktree 与进程边界
## Provider 凭据
## 项目经验与隐私
## 公网 Mock 演示
## 已知剩余风险
```

明确 API Key 不进入记忆/日志/Git，项目经验只能保存用户批准的项目约定/架构经验，不能保存隐私或凭据；公网 HTTP 无身份认证且会话头明文，只允许短时在场 Mock 演示。

保留既有交付契约所依赖的精确安全术语：`state_root`、`同一 UID`、`不确定副作用`、`只读`、`localhost`、`公网部署尚未验收`、`Scripted Mock`、`make demo` 和 `不访问网络`；`.env.example` 继续只使用 Mock 和占位 Key。

- [ ] **Step 6: 创建学生本人反思提纲**

创建 `REFLECTION.md`，开头必须是：

```markdown
# 课程项目反思（学生填写提纲）

> 本文件最终需要 1500–2500 字，必须由学生本人撰写。AI 只能辅助整理证据或润色，并按课程要求标注；提交前请删除所有方括号提示并写入自己的真实判断。
```

随后使用测试规定的八个二级标题；每节只放 2–4 个方括号问题和可查证文件/提交提示，不生成第一人称结论。末尾加入“提交前自检”，检查字数、个人案例、AI 辅助标注和无秘密。

- [ ] **Step 7: 对齐课程根文档与协作规则**

- `SPEC.md`：保留批准规约正文，增加当前共学定位与 `docs/FEATURES.md`/归档索引导航；不改写历史决策。
- `SPEC_PROCESS.md`：记录本轮 brainstorm 的“介绍已完成功能”“移动而非删除”“反思不得代写”和 Provider 证据勘误。
- `AGENTS.md`：把延期台账路径改为 `docs/archive/ledgers/DEFERRED_WORK.md`，增加当前说明文档/历史归档边界；不改变强制 Superpowers 和安全规则。
- `PLAN.md`：登记 Task 1 哈希、Task 2 状态与新路径。
- `AGENT_LOG.md`：记录技能、证据核对、RED/GREEN、人工批准、审查结论和提交哈希，不记录凭据。

- [ ] **Step 8: 运行聚焦 GREEN 与真实性检查**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py -v
rg -n "全部完成|生产可用|WebUI.*连接测试通过|真实外网.*通过" README.md docs/FEATURES.md docs/DEMO.md docs/DEPLOYMENT.md docs/SECURITY.md
git diff --check
```

Expected: distribution 测试全部 PASS 或 Docker CLI 能力测试明确 SKIP；`rg` 不出现无边界的虚假完成声明；差异检查退出 0。

- [ ] **Step 9: 执行完整门禁与双重审查**

```powershell
mingw32-make test
mingw32-make demo
.\.venv\Scripts\python.exe scripts\secret_scan.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: Python/前端单测、Lint、mypy、TypeScript、构建、Playwright、三机制演示、秘密扫描、依赖检查和差异检查全部退出 0；任何 Docker 能力 SKIP 必须原样记录，不能改写成通过。

规约审查逐条映射批准设计第 2–6 节；质量审查检查功能声明是否可定位、命令是否仍可执行、链接是否有效、历史是否完整、反思是否越界代写。Critical/Important/Minor 清零后提交。

- [ ] **Step 10: 提交 Task 2 并准备分支收尾**

```powershell
git add README.md SPEC.md PLAN.md SPEC_PROCESS.md AGENT_LOG.md AGENTS.md REFLECTION.md docs tests/distribution/test_delivery_files.py
git commit -m "docs: 更新共学式 Harness 交付说明"
```

Expected: Task 2 形成一个中文提交并包含 Task 1 哈希。随后使用 `superpowers:verification-before-completion` 获取最终 Head 新鲜证据，再使用 `superpowers:finishing-a-development-branch`；只有分支无未解决审查项且远端没有分叉时，才可非强制推送并快进合并 `main`。

## 计划自审结论

- [x] 批准设计的信息架构、移动清单、当前产品叙事、交付文档、反思边界、路径修复和验收均映射到具体 Task。
- [x] Task 1 与 Task 2 的接口、依赖和规范新路径已写明；两个 Task 不能并行。
- [x] 每个 Task 都包含确定性 RED、最小 GREEN、聚焦验证、双重审查和中文提交。
- [x] Provider 声明已按当前 `main` 复核：真实运行时存在，WebUI Probe/主动清除和真实外网任务验收不宣称完成。
- [x] 计划不移动未跟踪 `.superpowers` 文件，不触碰 `.tmp/`、`.venv-py39-backup/`，也不生成学生反思正文。
- [x] 没有 `TBD`、`TODO`、未定义接口或伪造验证结果。
