# MVP 问题台账

本台账记录 2026-07-16 对 Task 5 整分支冷审查及后续根因调查发现的问题。安全阻塞项不得延期或通过文档声明规避。

| ID | 级别 | 问题 | 当前状态 | MVP 处理 |
|---|---|---|---|---|
| MVP-ISSUE-001 | Critical | Windows 普通路径与 `\\?\\` drive/UNC 别名未统一，`state_root` 可能与 Git 根实际重叠后仍通过检查 | 实现完成，待复审 | MVP-1 已在任何写入前使用统一路径身份与双向 containment；首次审查发现的特殊 Win32 组件放行已用统一验证器修复，WorktreeManager 参数矩阵证明 `mkdir=0`；待重新双重复审 |
| MVP-ISSUE-002 | Critical | `ls-files/status/log/worktree add/remove` 可通过 fsmonitor、hooks、GPG 或 filter 隐式执行仓库/用户配置中的外部程序 | 阻塞 | MVP-1 引入统一安全 Git 环境、`--no-show-signature`、`--no-checkout` 和 filter 执行前拒绝 |
| MVP-ISSUE-003 | Important | `pyproject.toml`/`package.json` 推导命令不要求信任，配置变化无法使旧审批失效 | 阻塞 | MVP-1 对源配置摘要和最终有效命令生成版本化指纹 |
| MVP-ISSUE-004 | Important | Python/Node fixture 只断言 argv，不能证明建议验证命令在独立目录中可运行 | 阻塞 | MVP-1 修复 Python fixture；Node 改为离线自包含验证，并增加真实子进程测试 |
| MVP-ISSUE-005 | Minor | scanner 对不存在候选在宿主路径解析前返回，可能探测或保留工作区外 Windows 路径 | 实现完成，待复审 | MVP-1 已在任何 `exists/stat` 前完成宿主语义解析和 containment；RED/GREEN 见下方实现证据 |
| MVP-ISSUE-006 | Minor | 10,000 文件性能测试在 CI 中硬断言 5 秒，与计划的“慢机只记录”冲突 | 待修 | MVP-1 将硬门禁限定为本机基准，CI 只验证功能并记录耗时 |
| MVP-ISSUE-007 | Minor | `PLAN.md` 总表、Task 5 小节和过程报告的状态曾互相矛盾 | 已修，待复审 | MVP-0 以精简计划的 MVP-1—MVP-4 作为唯一首版执行顺序；原 Task 5—14 仅保留为完整产品路线 |

## 已确认的根因边界

- `Path.resolve()` 的字符串结果不是 Windows 文件系统身份；`samefile()` 只能补证既有对象，不能单独解决不存在尾部的 containment。
- 固定 argv 和 `shell=False` 不能证明 Git 不执行外部程序。Git 会合并多层配置，并在表面只读或 worktree 命令中调用 fsmonitor、GPG、hooks 和 filter。
- 旧 Git 可能把 `core.fsmonitor=false` 当成名为 `false` 的 hook 路径；安全禁用值必须为空。
- `npm run test` 外层 argv 不变不代表脚本语义不变；信任指纹必须绑定原始配置摘要和最终有效命令。

## MVP Task 2 实现证据（待独立复审）

- RED：固定 Python 3.11 执行 path identity、scanner、worktree focused 集，得到 `15 failed, 40 passed, 3 skipped`；失败证明未知设备命名空间未拒绝、scanner 在拒绝 Windows 逃逸前调用 `exists`、既有对象未用 `samefile` 补证、权限错误未 fail closed，以及扩展 drive 别名可在 `mkdir` 前绕过重叠检查。
- GREEN：同一 focused 集为 `58 passed, 3 skipped`；提交前新鲜 governance/storage/workspace 回归为 `338 passed, 6 skipped`；Ruff、mypy 与 `git diff --check` 均退出 0。
- 当前只标记“实现完成，待复审”。`MVP-ISSUE-001/005` 必须在独立规约符合性审查和代码质量审查均无 Critical/Important 后才能关闭。

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
