# CL1-3 实施报告：Provider Registry 与受限 HTTP Adapter

## 结论

实现范围限定为 Task 3。`ProviderRegistry` 仅选择内置的 DeepSeek/Qwen 固定端点，任务绑定、配置版本、凭据与 vault 状态全部 fail-closed；OpenAI-compatible adapter 使用有界流式读取且不保留外部错误或 HTTP 对象。未发生真实网络请求或凭据读取。

## TDD 证据

- RED：新增 `tests/providers/test_registry.py` 与 adapter 边界测试后，运行 `.venv\\Scripts\\python.exe -m pytest tests/providers/test_registry.py tests/providers/test_contract.py -v`，退出 1；收集失败原因为 `ModuleNotFoundError: coding_agent_harness.providers.registry`，即缺失目标 Registry。
- GREEN：实现最小 Registry、固定映射和流式读取后，运行同一命令，结果为 `28 passed`。
- 重构后回归：`.venv\\Scripts\\python.exe -m pytest tests/providers -v`，结果为 `41 passed`。

## 实现与覆盖

- 新增 `src/coding_agent_harness/providers/registry.py`：只读 `MappingProxyType` 固定端点；验证任务三项授权绑定、Profile 存在与精确 version；稳定配置码覆盖未授权、Profile 缺失、授权过期、无凭据、锁定/不可用 vault；`probe()` 仅发送固定消息“只回复 OK”。
- 更新 `openai_compatible.py`：`AsyncClient.stream`、`follow_redirects=False`、累计响应严格限制 2 MiB；HTTP 状态、网络、connect/read/write/pool timeout 和响应解析错误映射为稳定 `ProviderError(kind, retryable)`，不保存第三方异常、request、response、header 或 body。
- 测试均通过 `httpx.MockTransport` 提供离线传输，覆盖固定 URL、拒绝重定向、配置失败、最小 probe 请求、超限响应、HTTP 分类、四类 timeout 及异常脱敏。

## 自审

- 规约符合性：固定端点不接受用户 base URL；model 仅来自已验证 Profile；key 只由 Broker 在运行时提供；没有高层 Agent runner 或真实联网。
- 代码质量：无响应全量读取；错误文本仅有稳定诊断；类型检查通过；变更仅涉及 Task 3 文件、计划与过程记录。
- 安全：`scripts/secret_scan.py` 与 `git diff --check` 均退出 0；测试只含显然的占位值，未写入任何实际凭据。

## 新鲜验证命令

```text
.venv\Scripts\python.exe -m pytest tests/providers -v        # 41 passed
.venv\Scripts\python.exe -m ruff check src tests              # All checks passed!
.venv\Scripts\python.exe -m mypy src                          # Success: no issues found in 54 source files
.venv\Scripts\python.exe scripts/secret_scan.py               # exit 0
git diff --check                                                # exit 0
```

## 文件

- `src/coding_agent_harness/providers/registry.py`
- `src/coding_agent_harness/providers/openai_compatible.py`
- `src/coding_agent_harness/providers/base.py`
- `tests/providers/test_registry.py`
- `tests/providers/test_contract.py`
- `PLAN.md`
- `AGENT_LOG.md`
