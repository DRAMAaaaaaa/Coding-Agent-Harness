# Task 5 实施报告

## 已完成

- 增加 migration 007、项目经验卡模型、仓储与审批服务。
- 仅接受已完成任务的 `FINAL_SUMMARY_PROPOSED`，每个来源任务唯一；空值、NUL、超过 2048 UTF-8 字节及任意 Redactor 命中均整体拒绝。
- 最新卡查询固定为 `approved_at DESC, id ASC`；运行时把最新卡作为带 ID、不可信且有界的 system context 注入，并写入幂等 `PROJECT_LEARNING_APPLIED` 事件。
- 增加批准及最新经验 API；IntentProjector 可将已应用经验 ID 关联到最终交付卡。
- 增加中文延期、README、DEMO、SECURITY 和过程记录。

## 验证证据

- 聚焦：`pytest tests/learning/test_cards.py tests/storage/test_migration_007.py tests/api/test_learning.py tests/agent/test_runtime.py -q`，12 passed。
- Ruff：通过；mypy：通过；Web lint、typecheck、Vitest（26 passed）及 Vite build：通过。
- `mingw32-make demo`：三个机制均 PASS；`secret_scan.py` 与 `pip check`：通过。

## 当前状态

实现完成，待独立规约符合性与代码质量复审。已为同名测试模块建立测试包命名空间，并将全部历史迁移契约连续升级到 v7；未来数据库版本 v8 仍被拒绝。真实 Provider 联网未执行。

## 最新验证

- `mingw32-make test` 的 Python 阶段：810 passed，15 skipped；Ruff、mypy 通过。随后 Web 门禁独立验证：Vitest 28 passed，ESLint、TypeScript、Vite build 通过；Playwright 3 passed，1 skipped（Windows 跳过 POSIX 真实进程组场景）。这些是分段证据，不表述为同一次完整 `make test` 全绿。
- 本轮聚焦：12 passed；`mingw32-make demo` 三项机制均 PASS；`secret_scan.py`、`pip check`、`git diff --check` 均退出 0。

## 终审后 writer 释放修复（待复审）

- RED：真实 Playwright 旗舰路径在“批准经验→下一任务”后失败；Python/API 回归进一步精确复现，终审先写入 `FINAL_REVIEW_APPROVED`，Demo 随后因缺少 `asyncio` 导入而在释放阶段抛出 `NameError`。任务虽已完成，`.active` writer 租约未安全处理，下一任务不能创建。
- GREEN：终审后不再重置或删除子 worktree；使用 `WorktreeManager.freeze(task_id)` 先验证 linked-worktree 身份与注册，再写入私有 frozen marker 并原子释放 `.active`。子分支和 diff 现场保留，父冻结现场不变；生产 Runtime 同样遵循该时机。
- 证据：新增 `tests/demo/test_router.py` 验证终审后 child 的 frozen marker、注册 worktree、未提交 diff 均保留，且下一任务可创建；聚焦 Python 为 `5 passed`，真实 Playwright 旗舰路径为 `1 passed`，并可观察到 `PROJECT_LEARNING_APPLIED`、经验 ID/文本与先验证的 Mock 动作。

## 终审事务与旗舰 E2E 返工（待复审）

- 终审改为先 `freeze` 再持久化 `COMPLETED`；冻结失败保持 `WAITING_FINAL_REVIEW` 与 writer 租约。冻结成功而持久化失败时，重试经已冻结身份校验后可恢复完成；已完成重试同样执行幂等身份校验。
- `freeze` 对同一任务的 frozen marker 幂等，但仍验证 marker 内容、linked worktree 注册与 Git 顶层身份。Demo 不再提前移除 workspace 映射。
- `serve_demo.py` 默认恢复单任务完成回调并退出 0；`--keep-alive` 显式供 Playwright 多任务路径使用。旗舰 E2E 在子任务终审后重新读取 comparison，且下一任务通过真实 SSE `task-event` 断言第一条 `ACTION_PARSED` 为 `run_verification`。
- 新鲜证据：`pytest tests/workspace/test_worktrees.py tests/demo/test_router.py tests/demo/test_serve_cleanup.py tests/agent/test_runtime.py -q` 为 `63 passed, 1 skipped`；相关 Ruff、mypy 均通过；`npm.cmd run e2e -- --grep "真实浏览器"` 为 `1 passed`。

## 终审事务二次返工（待复审）

- frozen marker 已写入但同 owner `.active` 尚未删除的崩溃窗口现在可在重试时完成清理；不同 owner 的活动 writer 保留不动。
- `FINAL_REVIEW_APPROVED` 已落入事件流而任务状态写入失败时，下一次 `approve_final` 会从事件恢复并在单次调用内返回 `COMPLETED`。
- Demo 仅在成功 freeze 和完成持久化后才移除活动 workspace 映射；默认服务 cleanup 不再对 frozen worktree 调用 release。
- 新鲜证据：`pytest tests/workspace/test_worktrees.py tests/agent/test_orchestrator.py tests/demo/test_router.py tests/demo/test_serve_cleanup.py tests/agent/test_runtime.py -q` 为 `85 passed, 1 skipped`；相关 Ruff、mypy 均通过。
