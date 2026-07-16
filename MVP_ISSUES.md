# MVP 问题台账

本台账记录 2026-07-16 对 Task 5 整分支冷审查及后续根因调查发现的问题。安全阻塞项不得延期或通过文档声明规避。

| ID | 级别 | 问题 | 当前状态 | MVP 处理 |
|---|---|---|---|---|
| MVP-ISSUE-001 | Critical | Windows 普通路径与 `\\?\\` drive/UNC 别名未统一，`state_root` 可能与 Git 根实际重叠后仍通过检查 | 关闭 | MVP Task 2 已在任何写入前使用统一路径身份与双向 containment；提交 `26c1222` 的独立规约与质量复审均为 CLEAN，见 `.superpowers/sdd/task-2-rereview.md` |
| MVP-ISSUE-002 | Critical | `ls-files/status/log/worktree add/remove` 可通过 fsmonitor、hooks、GPG 或 filter 隐式执行仓库/用户配置中的外部程序 | 关闭 | MVP Task 3 提交 `e50f343` 的独立规约与质量审查均为 CLEAN，见 `.superpowers/sdd/task-3-review.md` |
| MVP-ISSUE-003 | Important | `pyproject.toml`/`package.json` 推导命令不要求信任，配置变化无法使旧审批失效 | 实现完成，待复审 | MVP Task 4 已实现 `verification-trust/v1`，绑定三源 raw 摘要与规范化有效配置；双重评审前不得关闭 |
| MVP-ISSUE-004 | Important | Python/Node fixture 只断言 argv，不能证明建议验证命令在独立目录中可运行 | 实现完成，待复审 | MVP Task 4 已修复 Python src package，并让 Node 24 四项命令离线自包含；双重评审前不得关闭 |
| MVP-ISSUE-005 | Minor | scanner 对不存在候选在宿主路径解析前返回，可能探测或保留工作区外 Windows 路径 | 关闭 | MVP Task 2 已在任何 `exists/stat` 前完成宿主语义解析和 containment；提交 `26c1222` 的独立规约与质量复审均为 CLEAN，见 `.superpowers/sdd/task-2-rereview.md` |
| MVP-ISSUE-006 | Minor | 10,000 文件性能测试在 CI 中硬断言 5 秒，与计划的“慢机只记录”冲突 | 实现完成，待复审 | MVP Task 4 已让 CI 只验证功能并记录耗时，本机独立基准仍验收小于 5 秒；双重评审前不得关闭 |
| MVP-ISSUE-007 | Minor | `PLAN.md` 总表、Task 5 小节和过程报告的状态曾互相矛盾 | 关闭 | MVP Task 1 的独立规约与文档质量审查均确认执行顺序和状态一致，见 `.superpowers/sdd/task-1-review.md` |
| MVP-ISSUE-008 | Important | Detector 在拒绝三类符号链接/reparse 配置前先执行 follow-target `exists`，底层 opener 也在无 no-follow 保护下打开目标 | 返工中 | 三入口必须先以 `lstat`/reparse 属性分类且记录型 opener 零调用；默认 opener 必须在打开前拒绝静态链接，并在打开后复验句柄身份 |
| MVP-ISSUE-009 | Minor | `PLAN.md` 总表与 Task 5 报告把历史 2 Critical、2 Important、3 Minor 误写成当前状态 | 返工中 | 当前状态统一为整分支规约审查 1 Important、1 Minor 正在返工；历史数量继续保留，不提前关闭 003/004/006 |

## 已确认的根因边界

- `Path.resolve()` 的字符串结果不是 Windows 文件系统身份；`samefile()` 只能补证既有对象，不能单独解决不存在尾部的 containment。
- 固定 argv 和 `shell=False` 不能证明 Git 不执行外部程序。Git 会合并多层配置，并在表面只读或 worktree 命令中调用 fsmonitor、GPG、hooks 和 filter。
- 旧 Git 可能把 `core.fsmonitor=false` 当成名为 `false` 的 hook 路径；安全禁用值必须为空。
- `npm run test` 外层 argv 不变不代表脚本语义不变；信任指纹必须绑定原始配置摘要和最终有效命令。

## MVP Task 1/2 关闭证据

- MVP Task 1：独立规约符合性与文档质量审查均为 CLEAN，Critical/Important/Minor 均为 0，见 `.superpowers/sdd/task-1-review.md`；Task 状态据此关闭。
- MVP Task 2：提交 `26c1222` 的修复后独立规约符合性与代码质量审查均为 CLEAN，Critical/Important/Minor 均为 0，见 `.superpowers/sdd/task-2-rereview.md`；`MVP-ISSUE-001/005` 据此关闭。

- RED：固定 Python 3.11 执行 path identity、scanner、worktree focused 集，得到 `15 failed, 40 passed, 3 skipped`；失败证明未知设备命名空间未拒绝、scanner 在拒绝 Windows 逃逸前调用 `exists`、既有对象未用 `samefile` 补证、权限错误未 fail closed，以及扩展 drive 别名可在 `mkdir` 前绕过重叠检查。
- GREEN：同一 focused 集为 `58 passed, 3 skipped`；提交前新鲜 governance/storage/workspace 回归为 `338 passed, 6 skipped`；Ruff、mypy 与 `git diff --check` 均退出 0。
- 首次审查发现的扩展组件 Important 已由统一验证器修复；最终复审 CLEAN 后关闭。

## MVP Task 3 关闭证据

- RED：Git 2.31.1 的 `GIT_TRACE` 证明 `core.fsmonitor=false` 执行名为 `false` 的外部 hook，空值不执行；真实 scanner fsmonitor/GPG sentinel、scanner clean filter gate、创建前 hook/filter gate与 release 当前 index/工作树重审均取得预期失败。
- GREEN：SafeGit 固定绝对 Git、最小宿主环境、空 hooks/global config/global attributes、协议拒绝、`core.fsmonitor=` 与 `log --no-show-signature`；清除继承的 Git 配置/目录/index/objects/alternates/diff/SSH/askpass/exec-path。创建使用宿主临时 index 审计 filter、`worktree add --no-checkout`、`read-tree` 和 `checkout-index`，materialize 前再次审计；release 在 status/remove 前审计当前 index 与工作树。
- Sentinel：活动 filter 在 marker/branch/target 任何副作用前拒绝；scanner、创建、materialize 和 release 均未产生 fsmonitor、GPG、hook、clean、smudge 或 process marker；发现 release filter 时 target 与 `.active` 保留。
- 独立审查覆盖 `26c1222..e50f343`，规约符合性为 PASS/CLEAN，代码质量与安全性为 APPROVED/CLEAN，Critical/Important/Minor 均为 0；复审 focused 为 `23 passed`，workspace 为 `98 passed, 4 skipped`。据此关闭 `MVP-ISSUE-002`。

## MVP Task 4 实现证据（待独立复审）

- RED：detector focused 为 `14 failed, 13 passed, 1 skipped`。失败证明 package/pyproject 推导命令没有 trust、raw 配置变化不使审批失效、旧 harness 摘要不符合版本化 manifest、无命令配置错误要求 trust、模型不拒绝不一致组合，以及独立 fixture 的 Python 导入和 Node 外部依赖失败。
- GREEN：`verification-trust/v1` 对 `.harness.yml`、`package.json`、`pyproject.toml` 的 raw bytes 分别 SHA256，缺失源显式为 `null`，再绑定规范化 commands、env allowlist、timeout 和领域分隔；focused 为 `27 passed, 1 skipped`。Python fixture 使用 `src/sample/__init__.py` 与 pytest `pythonpath`，Node 24 只使用 `node:test`、`node:assert/strict`、`node --check`，独立副本清除 `PYTHONPATH/NODE_PATH` 后真实执行。
- `MVP-ISSUE-006` 的 CI 用例不再断言 wall clock，只验证 10,000 文件功能并记录耗时；本机独立基准为 `0.88s`。当前 workspace 为 `109 passed, 4 skipped`，全量为 `499 passed, 6 skipped`，Ruff、mypy、pip check 与 `git diff --check` 均通过。`MVP-ISSUE-003/004/006` 在新的独立规约与质量审查前保持“实现完成，待复审”。

## MVP-1 整分支规约返工证据（待复审）

- 新整分支规约审查发现 1 Important、1 Minor：Detector 对 `.harness.yml`、`package.json`、`pyproject.toml` 在拒绝 symlink/reparse 前先调用会跟随目标的 `exists`，且根计划总表与 Task 5 报告仍把历史问题数量写成当前状态。
- 三入口消费者级 RED 为 `3 failed, 6 skipped`，均精确失败于 follow-target `exists`；可注入记录型 opener 为零调用。Windows reparse 契约另取得 `3 failed, 3 passed` 的 RED，默认 opener 的 pre-open reparse 契约取得 `1 failed`。
- 当前实现改为先 `lstat` 并检查 `FILE_ATTRIBUTE_REPARSE_POINT`，缺失、链接/reparse 和非普通文件确定性分类；POSIX 默认 opener 使用 `O_NOFOLLOW|O_CLOEXEC`，Windows/通用路径在打开前拒绝静态链接，打开后仍由 `fstat/lstat/samestat` 复验。最终门禁与提交证据补录后仍须重新进行整分支规约符合性审查；`MVP-ISSUE-003/004/006/008/009` 均不得在该审查前关闭。

## MVP Task 1 状态一致性关闭证据

- `.superpowers/sdd/task-1-review.md` 的规约符合性与文档质量结论均为 CLEAN，明确确认根 `PLAN.md`、精简计划、`MVP_ISSUES.md` 与 `AGENT_LOG.md` 使用唯一的 MVP-1—MVP-4 首版顺序，原 Task 5—14 只作完整产品路线；据此关闭 `MVP-ISSUE-007`。

## MVP-0 执行顺序冻结

- 首版唯一执行顺序来自 `docs/superpowers/plans/2026-07-16-minimal-viable-harness.md`：MVP-1 安全项目接入、MVP-2 最小工具/反馈/Agent、MVP-3 API/WebUI、MVP-4 演示与交付。
- 根 `PLAN.md` 的原 Task 5—14 保留为完整产品路线和历史接口依据，不再作为首版横向执行顺序。
- `DW-MVP-001`—`DW-MVP-006` 只登记批准设计明确排除的非首版能力；`MVP-ISSUE-001`—`006` 仍必须由 MVP-1 关闭，不能通过延期规避。

## 关闭规则

每个问题只有同时满足以下条件才能标记为关闭：

1. 存在能在旧实现上得到预期 RED 的最小回归测试。
2. 最小实现转绿，相关测试与全量门禁通过。
3. 独立规约审查和代码质量审查均无 Critical/Important。
4. `PLAN.md`、`AGENT_LOG.md` 和本台账记录真实提交与验证证据。
