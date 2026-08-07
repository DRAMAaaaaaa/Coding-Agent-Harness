# Task 2 实施报告

## 范围

已实现会话凭据存储、Provider Profile 的最小 API、任务 Provider 绑定前置校验、真实运行时路由，以及 Web Provider/API Key 输入。

## RED 证据

首次运行：

```text
ImportError: cannot import name 'SessionOnlyCredentialStore'
```

并且 Provider 路由测试在实现前不存在对应端点。

## GREEN / 验证原始摘要

```text
80 passed in 46.71s
```

覆盖 `tests/providers`、`tests/agent/test_runtime.py`、`tests/agent/test_real_tool_loop.py`、`tests/api/test_providers.py` 和 `tests/api/test_tasks.py`。

```text
All checks passed!
Success: no issues found in 56 source files
```

```text
23 passed
tsc --noEmit
eslint .
vite build ✓
```

Ruff、mypy 和 `scripts/secret_scan.py` 均以退出码 0 结束；`git diff --check` 无输出。

## 提交哈希

`abac70b feat: 连通真实 Provider 最小主路径`

## 变更文件

- `src/coding_agent_harness/providers/credentials.py`
- `src/coding_agent_harness/api/provider_routes.py`
- `src/coding_agent_harness/api/dependencies.py`
- `src/coding_agent_harness/api/app.py`
- `src/coding_agent_harness/api/routes.py`
- `src/coding_agent_harness/runtime.py`
- `tests/agent/test_runtime.py`
- `tests/api/test_providers.py`
- `web/src/types.ts`
- `web/src/App.tsx`
- `web/src/App.test.tsx`
- `web/src/api.ts`

## 审查返工状态

- 基线为 `abac70b`，本轮审查 Critical / Important / Minor=`0/4/2`；I1— I3 已修复，状态为“返工完成，待复审”。
- I1 覆盖任务创建失败时清空 Web 会话 API Key；I2 使用 `RuntimeOrchestratorRouter`、可注入受限工具执行器和 `httpx.MockTransport` 验证失败反馈进入下一次真实 Provider 请求，且 `delete_file` 被六工具白名单拒绝；I3 用同 profile 租约串行真实绑定和 `update_model()`，保留 TaskRepository CAS。
- 两个 Minor 依精简计划登记但不在本 Task 处理；未扩展 Task 3。

## 复审 Minor 延期

- **M1：** `tests/api/test_providers.py` 的“NUL 与超长 Key 拒绝”测试名实际只覆盖超长 Key；NUL 拒绝缺少直接行为测试。
- **M2：** Provider mutation 复用 `SessionGuard`，但新增测试没有 Origin/session 的拒绝用例，也没有 Key 不进入事件、存储或异常响应的直接行为断言。
- **M3：** 单进程 `ProviderBindingCoordinator._locks` 不回收无 waiter 的 profile lock；长期持续创建 profile 时可能累积小对象。
- **决定：** 三项均为单进程本地 MVP Minor，不影响安全主路径或 Task 2 验收。依用户成本策略，本 Task 不返工；后续 Provider 管理/维护任务复核，Web 测试边界可引用 `DEFERRED_WORK.md` 的 `DW-MVP-006`。Task 2 状态保持“返工完成，待复审”。

## 秘密、网络、依赖

- 未接触真实秘密；测试仅使用占位值。
- 未进行真实网络访问；未创建实际 Provider 请求。
- 未安装或升级依赖。
