# MVP-3 Task 7 实施报告

## RED 证据

2026-07-27 在未实现 `api`、`WorkspaceRepository` 与 `003` 迁移时运行：

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/api tests/storage/test_workspace_repository.py -q
```

结果为退出码 `1`，pytest 在收集 `tests/api/conftest.py` 时稳定报告
`ModuleNotFoundError: No module named 'coding_agent_harness.api'`。这证明新增 API
用户路径在实现前不存在；仓储测试同时指定了真实 SQLite 的 create/get/list/重启信任持久化契约。

实现期间，FastAPI 参数位置与严格 JSON 往返分别出现独立失败；已按错误栈定位为 Query 声明和
`model_validate` 对 JSON 数组的严格 tuple 拒绝，并改用明确 `Query` 与
`model_validate_json(strict=True)`。不使用 sleep 型并发等待。

## GREEN 与分发证据

实现后的聚焦与相关回归命令为：

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests/api tests/storage tests/governance tests/agent -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m build --wheel --sdist --no-isolation
```

最新结果分别为 `407 passed, 2 skipped`、Ruff 通过、mypy 检查 46 个源文件通过，且
wheel/sdist 均包含 `001_initial.sql`、`002_governance_approvals.sql`、
`003_mvp_workspaces.sql` 各一份。归档检查使用 Python 标准库 `zipfile` 与 `tarfile`，不依赖网络或额外安装。

## 规约返工

规约审查发现默认 API 伪造编排状态、任务启动未复检信任、SSE 传输未脱敏等问题。返工改为：默认 runtime 缺失时 fail closed；测试注入真实 `AgentOrchestrator` 与 `ScriptedMockProvider`；启动前重新检测并撤销过期信任；事件响应脱敏并限制大小；受控 SafeGit 分支解析、root_key 唯一、重复信任拒绝、项目摘要与任务读取端点。返工后 API/storage 为 `13 passed`，storage/governance/agent 为 `399 passed, 2 skipped`；Ruff、mypy、build 与归档检查通过。

二轮返工新增摘要 commit canary 脱敏和独立迁移 003 冻结矩阵；新增 API/storage/migration 聚焦结果为 `17 passed`。

三轮仅补真实组合回归：默认 runtime 零副作用、真实 Agent 计划事件链、配置纯函数和 v2 approval 全字段快照。

四轮补强配置变化的零副作用观察：真实 task 数、state_root 递归条目和记录型 runner 调用均保持不变。

## 质量返工 QA（C1、I1、I3）

按 `task-7-quality-review.md` 仅处理 C1、I1、I3。RED 分别证明：未知 Host 可取得 token 并进入业务依赖、首页缺少 `no-store`、Repository 构造失败后数据库关闭次数为 0、外置数据库路径未被配置拒绝。GREEN 后，可信 Host/Origin 仅来自冻结配置；默认 authority 固定为 `127.0.0.1:8000` 与 `localhost:8000`，测试显式配置 `testserver`。所有请求先校验 Host，mutation 再以配置 Origin 与常量时间 session 比较，首页禁止缓存。

自建数据库打开后立即进入 `try/finally`；Repository、Scanner、SafeGit、runtime 四个构造故障注入均证明关闭恰好一次，外部注入数据库仍归调用方所有。`HarnessSettings` 解析并冻结私有路径，数据库必须位于 `state_root`；数据库、WAL、SHM 的父目录显式进入 API 私有根集合，接入项目与任一私有根重叠时 fail closed。

聚焦 `session/app/projects/config` 为 `30 passed`，API 全套为 `22 passed`，API + workspace repository + 003 migration + config 为 `43 passed`。按返工范围未运行 399 回归或构建。

## 质量返工 QB（I2、I4、I5）

本轮只处理 async 阻塞、计划失败孤儿和异常误分类。TDD 首轮分别取得：Agent 公共故障记录缺失 `1 failed`；API 响应性/Provider/异常矩阵 `9 failed, 2 passed`；worktree 取消收敛 `1 failed`。实现以单个依赖级 `BlockingWorker + CapacityLimiter` 承载 Detector、Scanner、SafeGit 分支解析及 WorktreeManager；事件/线程探针在每个只读阻塞端口中反向请求首页并得到 200，不使用 sleep。worktree 创建与 Task 持久化放入受 shield 保护的单一异步任务，收到取消时持续等待确定结果并观察异常，内部结果不可观察时固定为 `WorktreeUncertainError`。

`AgentOrchestrator.record_runtime_failure` 只经状态机、EventStore 和 `_emit` 写入合法事件，不由 API 直接更新 Repository。Provider/ScriptedMock 计划失败后任务幂等进入 `WAITING_USER`，reason payload 脱敏且事件序号连续；API 的 503 携带 `details.task_id`，GET 可查询任务和 reason 事件，worktree/`.active` 保留。active marker 现在安全返回所属 task ID；重复请求固定返回同一可恢复 ID，marker 无效则为 uncertain 而不是 busy。

错误矩阵以具体领域类型区分 `WORKSPACE_BUSY`、`WORKTREE_UNCERTAIN`、`INVALID_TASK_STATE`、`PROVIDER_UNAVAILABLE` 和 `RUNTIME_UNAVAILABLE`，factory 与方法调用使用同一类型边界；`ProviderError` 的 `ScriptExhaustedError` 子类不再落入 `RuntimeError` 泛捕，未知 `ValueError` 仍为脱敏 500。新鲜限定验证为 API `38 passed`；Agent 加 worktree/process `127 passed, 1 skipped`；Ruff 通过，mypy 检查 46 个源文件通过。按要求未运行全量或构建，未触碰 QC。

## QB 独立复审返工

复审发现 task/worktree 已持久化后的未知 propose 异常仍会通过全局 500 丢失 task ID，且裸 `KeyError` 被误归类为非法状态。新增三条确定性回归：未知 Provider 实现异常、`record_runtime_failure` 二次异常、approve 内部裸 KeyError。RED 分别为前两项 `2 failed, 10 passed` 和 KeyError `1 failed, 4 passed`。

实现只收紧现有边界：任何未知 propose 异常都先丢弃脱敏后的异常值，再 best-effort 记录 `RUNTIME_FAILURE`，最后返回固定 `500 INTERNAL_ERROR` 与 `details.task_id`；记录失败也不会覆盖原 Provider/runtime 响应或丢失 task 身份。裸 `KeyError` 不再进入 `INVALID_TASK_STATE`，只有 `TaskStateError` 保持 409。GREEN 聚焦为 `7 passed, 16 deselected`；API 全套 `41 passed`，Ruff 和 46 个源文件的 mypy 均通过。未触碰 QC，未运行全量或构建。

## 质量返工 QC（I6、I7、M1）

本轮只收紧任务需求、Workspace 恢复与 SSE 事件读取边界。I6 的两个 RED 证明 90,000 UTF-8 bytes 的 CJK 需求会被 API 接受，并在 Repository 内被静默替换；I7 的真实 SQLite 篡改矩阵证明 root 已能拒绝，但 git_root 与独立 trust_fingerprint 列仍被信任；M1 的三个 RED 证明缺少公共有界批次方法、SSE 仍调用无界读取，且超大事件仅剩 sequence/payload。

GREEN 后，API 与 Repository 统一使用共享 `MAX_REQUIREMENT_BYTES` 的 UTF-8 字节规则：超限 API 请求返回 422，真实 task 计数及 state_root 条目保持不变，持久层防御性检查直接拒绝而不改写需求。Workspace 从行恢复时分别严格规范化 root/git_root，要求两者的 path key 均匹配持久化 root_key、`same_path` 成立，并核对 profile 与独立指纹列；三类篡改均 fail closed。EventStore 新增最大 100 条的公共批次读取，SSE 按最后 sequence 循环读取固定批次；超大事件仅将 payload 替换为结构化脱敏标记，task_id、sequence、event_type、状态和时间字段全部保留。

直接相关四文件回归为 `53 passed`，API + storage 回归为 `89 passed`；Ruff 与 47 个源文件的 mypy 通过。未运行全量或构建，未联网、安装、merge 或 push。

## QC 独立复审返工

复审指出 I6 仍存在脱敏扩张发生在 worktree 创建之后的时序缺口。真实回归以 `token=x ` 重复 8,192 次构造恰好 65,536 UTF-8 bytes 的原始需求；实际 `TaskRepository` Redactor 将其扩张到上限之外。首轮 API 返回 500，正常 65,536-byte 未扩张输入为 201，证明问题只在 Repository 规范化后的第二边界。

实现把 Repository 的完整准备过程公开为单一无副作用路径：`prepare_requirement()` 依次执行原始字节校验、既有 Redactor 脱敏和最终字节校验，并返回不可变的 `PreparedRequirement`。`LocalTaskRunner` 在任何 worktree worker、marker 或 Task 副作用前取得该结果，持久化通过 `create_prepared()` 原样复用，不在 API 重建脱敏规则。API 只捕获明确的 `RequirementTooLargeError` 并映射为 `422 VALIDATION_ERROR`；未知异常仍为脱敏 500。

GREEN 后，扩张输入为 422，task count 保持 0，workspace worktree 目录、`.active` 和 state_root 快照均无新增；正常边界仍创建任务并精确持久化。I6 聚焦为 `4 passed`，API + storage 回归为 `91 passed`，mypy 检查 47 个源文件通过。未触碰 I7/M1、QA/QB，未运行全量或构建，也未联网、安装、merge 或 push。

## 整阶段最终审查 I1/I2 返工

最终审查复现了两个组合缺口：真实 worktree 创建成功后，SQLite 插入失败会留下无 Task 所有者的工作树和 `.active`；项目接入端点则把 detector、scanner 和 branch resolver 抛出的未知 `RuntimeError`/`ValueError` 统一误报为 `400 INVALID_PROJECT`。首组 RED 使用真实 Git、真实 SQLite trigger 和真实 API，得到任务存储故障 `500`、六项未知端口异常全部 `400`，合计 `7 failed`。补偿不确定分支另以所有权变化探针验证：若不执行安全补偿，响应会错误成为 `TASK_STORAGE_UNAVAILABLE`，而不是 `WORKTREE_UNCERTAIN`。

GREEN 后，`LocalTaskRunner` 复用创建工作树的同一 `WorktreeManager`：`create_prepared()` 失败时只释放本次 task ID；释放成功后抛出专用 `TaskStorageUnavailableError`，API 固定返回脱敏、可重试的 `503 TASK_STORAGE_UNAVAILABLE`；释放失败、所有权变化或结果不可确认时固定升级为 `503 WORKTREE_UNCERTAIN`，保留现场且不清理其他 owner。真实 SQLite 故障测试断言首次请求无 Task、无 task worktree、无 `.active`，移除故障后重试为 201，不受幽灵 owner 阻塞。

项目端点新增窄化的 `ProjectPathError` 与 `DefaultBranchError`：仅路径解析/私有状态重叠、`ProjectDetectionError`、`RepositoryScanError` 和默认分支领域失败映射为 400；端口抛出的未知内置异常继续进入全局脱敏 500。核心与不确定分支为 `8 passed`，task/project 聚焦为 `43 passed`，API + worktree + storage 组合回归为 `147 passed, 1 skipped`。本轮未处理 M1 文档关闭、未运行全量或构建，也未联网、安装、merge 或 push。

## 最终独立审查 C1/I1 返工

本轮只处理 `task-7-final-review.md` 的 C1/I1，并使用 `systematic-debugging`、`test-driven-development` 与 `verification-before-completion`。C1 的最小 RED 使用真实 SQLite 和运行期生成的 canary，证明 `WorkspaceRepository.create()` 未拒绝敏感赋值，结果为 `1 failed`；I1 的 Agent/真实 ASGI Provider barrier RED 为 `2 failed`，分别证明 `CREATED → WAITING_USER` 缺少合法事件路径，以及取消请求后任务持久化停在 `PLANNING`。测试和输出均未记录 canary 原值。

C1 的 GREEN 在 `profile_json` 形成后、进入任何仓储 INSERT 前使用既有 `Redactor` 检查完整序列化内容；命中规则即抛出固定的 `SensitiveWorkspaceProfileError`，不持久化脱敏副本，避免 profile 与信任指纹分叉。`get/list/trust/revoke` 读取现有行时使用同一判定，外部篡改的敏感 profile 会 fail closed。真实 detector→API 和直接 SQLite 探针确认响应/异常不含 canary、Workspace 行数保持为零；聚焦为 `3 passed`。

I1 的 GREEN 在路由进入任务副作用前预分配 `task_id`，用独立受观察任务运行 `propose_plan()`；ASGI 取消时先取消并收敛 Provider 计划操作，再通过公开 `AgentOrchestrator.record_runtime_failure(task_id, "REQUEST_CANCELLED")` 和合法 `USER_INPUT_REQUIRED` 事件幂等进入 `WAITING_USER`，确认恢复操作收敛后原样传播 `CancelledError`。重复取消由 shielded recovery barrier 收敛，不遗留未观察后台任务。真实 Git/SQLite/ASGI 重启探针确认 GET 与 `/run` 均读取原任务为 `WAITING_USER`，重复 POST 返回 `.active` 中的原 task ID，且没有第二个 worktree；核心为 `2 passed`，四个直接相关测试文件为 `70 passed`。

限定回归命令为 `pytest tests/api tests/storage tests/agent tests/workspace/test_worktrees.py -q`。首轮唯一失败是冻结状态机契约仍缺少本次所需的 `CREATED → WAITING_USER`；精确更新契约后重跑为 `219 passed, 1 skipped`。Ruff 为 `All checks passed!`，mypy 为 `Success: no issues found in 47 source files`。本轮未运行全量或构建，未触碰 WebUI/Task 8，未联网、安装、merge 或 push。
