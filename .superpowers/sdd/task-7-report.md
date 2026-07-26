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
