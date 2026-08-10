# DeepSeek/Qwen WebUI 真实连接测试实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 WebUI 中安全配置会话型 DeepSeek/Qwen 凭据、显式测试真实连接并主动清除凭据，同时保持 Coding Agent Demo 完全由确定性 Mock 驱动。

**Architecture:** 复用 `ProviderRegistry` 与 `OpenAICompatibleProvider`，用独立的 `provider_probe_registry` 将真实 Probe 和 Mock Agent Provider 分开。API 只返回稳定脱敏状态；WebUI 提交后立即清空密码输入，后端只在当前进程会话内保存 Key。自动测试全部使用 HTTP Stub，最后由用户在本地 WebUI 中亲自输入 DeepSeek Key完成一次人工联网验收。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、httpx、SQLite、React 19、TypeScript、Vitest、Testing Library、Playwright、pytest。

## Global Constraints

- 实施前使用 `superpowers:using-git-worktrees` 从包含批准规格 `ea08737` 和本计划提交的 `p1` 当前 HEAD 创建隔离分支 `codex/provider-webui-probe`；不得在当前 `p1` 工作区编写实现。
- Windows worktree 不得直接递归清理指向共享 `.venv` 或 `web/node_modules` 的 Junction；清理前必须先验证并解除联接。
- 每个 Task 必须执行 RED -> GREEN -> REFACTOR，完成规约符合性审查和代码质量审查后单独提交，提交说明尽量使用中文。
- 真实 API Key 只能由用户在 WebUI 密码框输入；不得请求用户发送 Key，不得由智能体读取、打印、截图、持久化或写入日志。
- Provider URL 固定为 `https://api.deepseek.com/v1` 与 `https://dashscope.aliyuncs.com/compatible-mode/v1`；用户不能覆盖。
- `trust_env=False`、`follow_redirects=False`；Probe 使用固定提示“只回复 OK”和 `max_tokens=8`。
- 真实网络请求不得进入 CI、`make test`、Playwright 或 Mock 三机制演示。
- DeepSeek 真实 Probe 通过后，`DW-MVP-003` 仍保持 `DEFERRED`，正文更新为 DeepSeek 已验收、Qwen 因无凭据未执行。
- 每个 Task 结束更新本计划状态、根 `PLAN.md`、`AGENT_LOG.md` 和审查报告；记录事实但不记录秘密或上游响应正文。

## 文件与职责

- `src/coding_agent_harness/providers/base.py`：为请求增加有界输出 Token 字段，为错误保留安全的 HTTP 状态数字。
- `src/coding_agent_harness/providers/openai_compatible.py`：发送输出上限并保留稳定、脱敏的传输错误分类。
- `src/coding_agent_harness/providers/registry.py`：固定 Probe 提示、输出上限和网络超时。
- `src/coding_agent_harness/api/dependencies.py`：区分 Mock Agent Provider 和真实 Probe Provider。
- `src/coding_agent_harness/api/provider_routes.py`：实现 Probe、清除、锁协调与错误映射。
- `src/coding_agent_harness/api/app.py`：生产工厂把同一个真实 Registry 注入任务与 Probe 边界。
- `scripts/serve_demo.py`：Demo Agent 保持 Mock，同时为 WebUI 提供独立真实 Probe Registry，并在退出时清空/关闭资源。
- `web/src/types.ts`、`web/src/api.ts`：定义 Probe 结果和客户端方法。
- `web/src/App.tsx`：实现双 Provider、配置并测试、重复测试、清除和脱敏状态。
- `tests/providers/*`、`tests/api/test_providers.py`、`web/src/*.test.*`、`web/e2e/harness.spec.ts`：提供离线确定性验收。
- `docs/PROVIDER_ACCEPTANCE.md`：只记录真实验收的时间、Provider、模型、结果和 Qwen 未执行原因。

---

### Task 1：Provider Probe 核心与安全 API

**Files:**
- Modify: `src/coding_agent_harness/providers/base.py`
- Modify: `src/coding_agent_harness/providers/openai_compatible.py`
- Modify: `src/coding_agent_harness/providers/registry.py`
- Modify: `src/coding_agent_harness/api/dependencies.py`
- Modify: `src/coding_agent_harness/api/provider_routes.py`
- Modify: `src/coding_agent_harness/api/app.py`
- Modify: `scripts/serve_demo.py`
- Test: `tests/providers/test_contract.py`
- Test: `tests/providers/test_registry.py`
- Test: `tests/api/test_providers.py`
- Test: `tests/demo/test_serve_cleanup.py`

**Interfaces:**
- Consumes: `CredentialBroker.get/delete`、`ProviderBindingCoordinator.hold`、`ProviderProfileRepository.get`、`ProviderRegistry.probe`。
- Produces: `LLMRequest.max_output_tokens: int | None`、`ProviderError.status_code: int | None`、`ApiDependencies.provider_probe_registry: ProviderRegistry | None`、`POST /api/providers/{profile_id}/probe`、`DELETE /api/providers/{profile_id}/session-credential`。

- [ ] **Step 1: 写 Provider 请求上限和安全错误 RED 测试**

在 `tests/providers/test_contract.py` 增加请求上限和安全状态断言：

```python
request = LLMRequest(
    messages=[{"role": "user", "content": "只回复 OK"}],
    max_output_tokens=8,
)
response = await provider.complete(request)
assert response == LLMResponse(content="OK")
assert json.loads(requests[0].content)["max_tokens"] == 8

with pytest.raises(ProviderError) as captured:
    await authentication_provider.complete(LLMRequest(messages=[]))
assert captured.value.kind == "http_status"
assert captured.value.status_code == 401
assert "upstream-secret" not in str(captured.value)
```

同时断言 `max_output_tokens=0` 和 `129` 被 Pydantic 拒绝，未设置上限的普通 Agent 请求保持现有 JSON 契约。

- [ ] **Step 2: 写 Registry 固定 Probe RED 测试**

在 `tests/providers/test_registry.py` 将现有 Probe 测试收紧为：

```python
response = await registry(handler=handler).probe(PROFILE_ID)
assert response.content == "OK"
assert observed_request == LLMRequest(
    messages=[{"role": "user", "content": "只回复 OK"}],
    max_output_tokens=8,
)
```

再通过替换 `httpx.AsyncClient` 构造器，断言默认客户端 `trust_env is False`、`follow_redirects is False` 且总超时为 10 秒、连接超时为 5 秒。

- [ ] **Step 3: 写 Probe/清除 API 和协调 RED 测试**

在 `tests/api/test_providers.py` 增加：

```python
probed = await client.post(f"/api/providers/{profile_id}/probe", headers=headers)
assert probed.status_code == 200
assert probed.json() == {
    "provider": "deepseek", "model": "deepseek-chat", "status": "passed"
}
assert "test-session-provider-key" not in probed.text

cleared = await client.delete(
    f"/api/providers/{profile_id}/session-credential", headers=headers
)
assert cleared.status_code == 200
assert cleared.json()["configured"] is False
```

使用 `monkeypatch` 替换 `ProviderRegistry.probe`，依次抛出 401、429、timeout、network、response_schema 与 response_too_large，断言 API 只返回 `AUTHENTICATION_FAILED`、`RATE_LIMITED`、`TIMEOUT`、`NETWORK_UNAVAILABLE`、`INVALID_PROVIDER_RESPONSE`，响应不含异常正文和假 Key。使用两个 `asyncio.Event` 阻塞 Probe，并发启动 DELETE，证明 DELETE 必须等待同一 Profile 的 Probe 释放锁。

- [ ] **Step 4: 运行 RED 并保存失败证据**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/providers/test_contract.py tests/providers/test_registry.py tests/api/test_providers.py tests/demo/test_serve_cleanup.py -v
```

Expected: FAIL，明确显示 `LLMRequest` 不接受 `max_output_tokens`、缺少 `provider_probe_registry`、Probe/DELETE 路由返回 404 或 Demo 未管理真实 Probe 资源；不得出现导入错误以外的无关失败。

- [ ] **Step 5: 实现最小 Provider 核心**

在 `base.py` 使用严格边界：

```python
from pydantic import BaseModel, ConfigDict, Field, JsonValue

class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    messages: list[dict[str, JsonValue]]
    max_output_tokens: int | None = Field(default=None, ge=1, le=128)

class ProviderError(RuntimeError):
    def __init__(
        self, message: str, *, kind: str, retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.status_code = status_code
```

在 `OpenAICompatibleProvider.complete()` 只在字段存在时加入：

```python
payload: dict[str, object] = {
    "model": self._model,
    "messages": request.messages,
    "temperature": 0,
}
if request.max_output_tokens is not None:
    payload["max_tokens"] = request.max_output_tokens
```

非成功响应的 `ProviderError` 只保存整数 `response.status_code`，不保存 response/request 对象。`ProviderRegistry.probe()` 固定构造 `max_output_tokens=8`。默认与生产客户端统一使用 `httpx.Timeout(10.0, connect=5.0)`。

- [ ] **Step 6: 实现独立 Probe 依赖和 API**

在 `ApiDependencies` 增加：

```python
provider_probe_registry: ProviderRegistry | None = None
```

生产 `create_app()` 将真实 Registry 同时赋给 `provider_registry` 和 `provider_probe_registry`。Demo 保持 `provider_registry=router.provider_registry`，另行创建真实 Profile Repository、`CredentialBroker(SessionOnlyCredentialStore(), worker)`、`ProviderRegistry` 和 Binding，并赋给 `provider_probe_registry`。Demo 退出时先 `credentials.clear_session()`，再关闭 Probe 的 `httpx.AsyncClient`。

在 `provider_routes.py` 中，PUT、POST Probe 和 DELETE 均调用 `sessions.require_mutation(request)`，检查 profiles/credentials/binding/probe registry 后执行：

```python
async with active.provider_binding.hold(profile_id):
    profile = await _require_profile(active, profile_id)
    await active.credentials.put(profile_id, body.api_key, CredentialPersistence.SESSION)

async with active.provider_binding.hold(profile_id):
    profile = await _require_profile(active, profile_id)
    await active.provider_probe_registry.probe(profile_id)
    return {"provider": profile.kind.value, "model": profile.model, "status": "passed"}

async with active.provider_binding.hold(profile_id):
    profile = await _require_profile(active, profile_id)
    await active.credentials.delete(profile_id)
    return await _profile_response(profile, active.credentials)
```

401/403 映射 HTTP 401 + `AUTHENTICATION_FAILED`；429 映射 HTTP 429 + `RATE_LIMITED`；timeout 映射 504；network 映射 503；response_schema/response_too_large 映射 502；其他 Provider 错误映射 503 + `PROVIDER_UNAVAILABLE`。所有消息使用固定中文，不拼接 `str(error)`。

- [ ] **Step 7: 运行 GREEN、静态检查与重构**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/providers/test_contract.py tests/providers/test_registry.py tests/api/test_providers.py tests/demo/test_serve_cleanup.py -v
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe scripts\secret_scan.py
```

Expected: 聚焦测试全部 PASS；Ruff、mypy、秘密扫描退出 0。重构只允许提取 Provider route 的 `_runtime_unavailable`、`_require_profile` 和 `_probe_error` 私有 helper，不改变公开响应。

- [ ] **Step 8: 规约审查、质量审查与提交**

先由独立规约审查者只依据批准规格和本计划检查范围、秘密边界、Mock/真实分离；通过后由另一名质量审查者检查取消、资源关闭、锁死、错误保留和测试质量。Critical/Important 必须归零，Minor 要么修复要么登记合法延期。

```powershell
git add src/coding_agent_harness/providers/base.py src/coding_agent_harness/providers/openai_compatible.py src/coding_agent_harness/providers/registry.py src/coding_agent_harness/api/dependencies.py src/coding_agent_harness/api/provider_routes.py src/coding_agent_harness/api/app.py scripts/serve_demo.py tests/providers/test_contract.py tests/providers/test_registry.py tests/api/test_providers.py tests/demo/test_serve_cleanup.py PLAN.md AGENT_LOG.md
git commit -m "feat: 提供安全的 Provider 连接测试 API"
```

---

### Task 2：WebUI Provider Demo 与离线浏览器验收

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/api.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/src/api.test.ts`
- Modify: `web/src/App.test.tsx`
- Modify: `web/e2e/harness.spec.ts`

**Interfaces:**
- Consumes: Task 1 的 Probe/DELETE API。
- Produces: `ProviderProbeResult`、`HarnessApi.probeProvider(profileId)`、`HarnessApi.clearSessionCredential(profileId)` 和可演示的 Provider 状态区。

- [ ] **Step 1: 写 API 客户端 RED 测试**

在 `web/src/api.test.ts` 断言：

```typescript
await api.probeProvider("provider-1");
expect(fetch).toHaveBeenCalledWith(
  "/api/providers/provider-1/probe",
  expect.objectContaining({ method: "POST" }),
);

await api.clearSessionCredential("provider-1");
expect(fetch).toHaveBeenCalledWith(
  "/api/providers/provider-1/session-credential",
  expect.objectContaining({ method: "DELETE" }),
);
```

- [ ] **Step 2: 写组件交互 RED 测试**

在 `web/src/App.test.tsx` 增加以下独立行为：

```typescript
expect(screen.getByLabelText("模型")).toHaveValue("deepseek-chat");
await user.selectOptions(screen.getByLabelText("类型"), "qwen");
expect(screen.getByLabelText("模型")).toHaveValue("qwen-plus");
expect(screen.getByLabelText("API Key")).toHaveValue("");

await user.type(screen.getByLabelText("API Key"), "test-session-key");
await user.click(screen.getByRole("button", { name: "配置并测试连接" }));
expect(await screen.findByText("DeepSeek / deepseek-chat 连接测试通过")).toBeVisible();
expect(screen.getByLabelText("API Key")).toHaveValue("");

await user.click(screen.getByRole("button", { name: "清除凭据" }));
expect(await screen.findByText("会话凭据已清除")).toBeVisible();
```

补充 Probe 失败测试，API 错误只显示既有通用中文错误；测试 DOM 不包含假 Key 或上游错误正文。

- [ ] **Step 3: 运行 Web RED**

Run:

```powershell
npm.cmd --prefix web run test -- --run
```

Expected: FAIL，缺少 `probeProvider`、`clearSessionCredential`、默认模型切换和新按钮；现有 28 个测试继续通过或只因接口类型缺失无法编译。

- [ ] **Step 4: 实现类型、客户端和最小状态机**

在 `types.ts` 增加：

```typescript
export interface ProviderProbeResult {
  provider: "deepseek" | "qwen";
  model: string;
  status: "passed";
}
```

为 `HarnessApi` 增加两个方法，并在 `createHarnessApi()` 中实现 POST/DELETE。`App.tsx` 使用固定默认值：

```typescript
const defaultModels = { deepseek: "deepseek-chat", qwen: "qwen-plus" } as const;
```

切换 Provider 时同步模型、清空 `apiKey` 与旧 Probe 消息。配置流程复用同 kind/model 的现有 Profile，否则创建一个；写入会话 Key 后调用 Probe，在 `finally` 中执行 `setApiKey("")`。已配置 Profile 显示“测试连接”和“清除凭据”；清除成功后替换列表中的 `configured` 状态并清空选择。

- [ ] **Step 5: 写并运行离线 Playwright Probe 场景**

在现有旗舰测试访问页面前用 `page.route` 为 `/api/providers*` 建立只存在于测试进程的 HTTP Stub，维护 `configured` 布尔值；其他 REST/SSE 继续访问真实 localhost Demo 服务。场景执行：

```typescript
await page.getByLabel("API Key").fill("e2e-session-key");
await page.getByRole("button", { name: "配置并测试连接" }).click();
await expect(page.getByText("DeepSeek / deepseek-chat 连接测试通过")).toBeVisible();
await expect(page.getByLabel("API Key")).toHaveValue("");
await page.getByRole("button", { name: "清除凭据" }).click();
await expect(page.getByText("会话凭据已清除")).toBeVisible();
await expect(page.locator("body")).not.toContainText("e2e-session-key");
```

Stub 必须断言 Probe 请求不含 Key；会话 Key 只出现在 PUT 请求体，且测试不得打印请求体。

- [ ] **Step 6: 运行 Web GREEN 与聚焦后端回归**

Run:

```powershell
npm.cmd --prefix web run lint
npm.cmd --prefix web run typecheck
npm.cmd --prefix web run test -- --run
npm.cmd --prefix web run build
npm.cmd --prefix web run e2e
.\.venv\Scripts\python.exe -m pytest tests/api/test_providers.py tests/providers -v
```

Expected: ESLint、TypeScript、Vitest、Vite、Playwright 和 Provider 聚焦 pytest 全部退出 0；浏览器测试仍不访问真实 Provider。

- [ ] **Step 7: 规约审查、质量审查与提交**

规约审查重点确认只有 Probe 联网、真实 Agent 仍为 Mock；质量审查重点确认密码状态在成功/失败/切换后清空、按钮并发禁用、可访问名称和错误不泄漏。Critical/Important 归零后提交：

```powershell
git add web/src/types.ts web/src/api.ts web/src/App.tsx web/src/styles.css web/src/api.test.ts web/src/App.test.tsx web/e2e/harness.spec.ts PLAN.md AGENT_LOG.md
git commit -m "feat: 在 WebUI 演示 Provider 连接测试"
```

---

### Task 3：真实 DeepSeek 验收、中文交付文档与分支收尾

**Files:**
- Create: `docs/PROVIDER_ACCEPTANCE.md`
- Modify: `README.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/DEMO.md`
- Modify: `DEFERRED_WORK.md`
- Modify: `PLAN.md`
- Modify: `AGENT_LOG.md`

**Interfaces:**
- Consumes: Task 1/2 的可运行 WebUI Probe。
- Produces: 不含秘密的真实 DeepSeek 验收证据和准确的延期状态。

- [ ] **Step 1: 先完成全部离线门禁**

Run:

```powershell
mingw32-make test
mingw32-make demo
.\.venv\Scripts\python.exe scripts\secret_scan.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: Python、Ruff、mypy、Vitest、ESLint、TypeScript、Vite、Playwright、三机制演示、秘密扫描、依赖检查和差异检查全部退出 0。任一失败都先按 `systematic-debugging` 修复，禁止进入真实联网步骤。

- [ ] **Step 2: 启动仅绑定 localhost 的 WebUI Demo**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\serve_demo.py --ready-file .tmp\provider-ready.json --host 127.0.0.1 --port 8000 --max-seconds 900 --keep-alive
```

Expected: `.tmp/provider-ready.json` 给出 `http://127.0.0.1:8000`；服务不监听公网地址。向用户发送该本地 URL，等待用户亲自在页面输入 DeepSeek Key并点击“配置并测试连接”。智能体不读取页面密码输入值，不截图包含输入过程的页面。

- [ ] **Step 3: 取得一次真实 DeepSeek 结果**

验收条件：页面显示 `DeepSeek / deepseek-chat 连接测试通过`，密码框为空，Profile 显示已配置。随后由用户点击“清除凭据”，页面显示“会话凭据已清除”。如果失败，只记录稳定错误代码并停止，不把失败改写成通过；根据错误类型决定是否修复代码或让用户检查账户/额度。

- [ ] **Step 4: 写入准确的中文验收与安全文档**

`docs/PROVIDER_ACCEPTANCE.md` 必须记录本次实际观察到的 UTC 时间、`deepseek`、`deepseek-chat`、`passed`、触发入口为本地 WebUI，以及“未保存 Key/请求头/响应正文”。Qwen 条目固定记录 `not_executed`，原因为“用户当前未提供 Qwen 凭据”。

README 增加 WebUI 操作步骤和“真实 Probe 不等于真实 Agent 任务”；安全文档说明会话生命周期和清除行为；Demo 文档区分离线机制演示与显式真实 Probe。`DEFERRED_WORK.md` 保留 `DW-MVP-003=DEFERRED`，追加 DeepSeek 完成证据和 Qwen 剩余边界；`DW-MVP-006` 只移除 Probe/会话清除部分，持久凭据和高级 UI 继续延期。

- [ ] **Step 5: 文档 RED/GREEN 契约与秘密复验**

先在 `tests/distribution/test_delivery_files.py` 增加断言：README/安全/Demo/验收文档包含 DeepSeek 已验收、Qwen 未执行、真实 Agent 仍为 Mock、会话 Key 不持久化；RED 应因文档尚未更新失败。更新文档后运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py tests/distribution/test_secret_scan.py -v
.\.venv\Scripts\python.exe scripts\secret_scan.py
git diff --check
```

Expected: 聚焦测试、秘密扫描和差异检查退出 0；任何生成的 `.tmp/provider-ready.json`、数据库、日志或截图不得进入 Git。

- [ ] **Step 6: 最终双重评审和新鲜全量验证**

独立规约审查逐条映射批准设计九节和本计划三个 Task；质量审查检查真实网络边界、资源关闭、Key 生命周期、错误脱敏、文档真实性和延期状态。Critical/Important 归零后重新运行：

```powershell
mingw32-make test
mingw32-make demo
.\.venv\Scripts\python.exe scripts\secret_scan.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: 所有命令退出 0，并且真实 Provider 不被第二次调用。

- [ ] **Step 7: 提交、推送并创建 PR**

```powershell
git add docs/PROVIDER_ACCEPTANCE.md README.md docs/SECURITY.md docs/DEMO.md DEFERRED_WORK.md tests/distribution/test_delivery_files.py PLAN.md AGENT_LOG.md
git commit -m "docs: 记录 DeepSeek 真实连接验收"
git push -u origin codex/provider-webui-probe
```

使用 GitHub 创建 `codex/provider-webui-probe -> p1` PR，描述三个 Task 提交、RED/GREEN 证据、双重评审结论、全量验证，以及 Qwen 未联网的明确限制。等待 PR CI 通过，不自动合并；保留 worktree 处理审查反馈。

## 计划自审结论

- [x] 批准规格中的架构、API、安全、WebUI、测试、真实验收和延期状态均映射到具体 Task。
- [x] Mock Agent Registry 与真实 Probe Registry 已分离，Demo 不会因新增 Probe 而调用真实模型执行代码。
- [x] 类型签名在首次消费前定义；API、前端和文档使用一致的 Provider/模型/状态名称。
- [x] 所有自动测试离线；只有用户在 localhost WebUI 中显式点击会产生一次真实 DeepSeek 请求。
- [x] 计划没有未决占位、伪造真实结果或要求用户在聊天中提供 Key。
- [x] 每个 Task 包含 RED、GREEN、聚焦验证、两阶段审查和中文提交。
