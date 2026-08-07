# 真实 Provider 与凭据实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 Mock Harness 上增量交付可配置、可安全保存并可由真实 Agent 任务使用的 DeepSeek/Qwen Provider，同时保持现有治理、worktree、反馈闭环和离线验收不回退。

**Architecture:** 以 SQLite `ProviderProfile` 保存非秘密配置，以 `CredentialBroker` 隔离会话、OS Keyring 和容器认证加密存储，以 `ProviderRegistry` 从已持久化任务授权构造现有 `OpenAICompatibleProvider`。真实运行时沿用 `AgentOrchestrator`、`ToolRegistry`、`EventStore` 和独立 worktree；Provider API 与最小 WebUI 只增加配置和选择入口，不进行最终视觉重构。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、SQLite/aiosqlite、httpx、keyring、Argon2id、AES-256-GCM、pytest、React 19、TypeScript 6、Vitest、Playwright。

## Global Constraints

- Python 必须为 `>=3.11,<3.12`，Node.js 必须为 `>=24,<25`。
- 使用 `pyproject.toml` 已固定的 `keyring==25.7.0`、`cryptography==49.0.0` 和 `argon2-cffi==25.1.0`；本阶段不新增依赖。
- Agent 循环、治理、动作解析、反馈、停止和任务恢复继续由本仓库实现，不使用高层 Agent Runner。
- DeepSeek 固定端点为 `https://api.deepseek.com`；Qwen 固定端点为 `https://dashscope.aliyuncs.com/compatible-mode/v1`。不允许用户提供任意 Provider URL，不跟随 HTTP 重定向。
- LLM API 授权只绑定一个已持久化任务和一个确切版本的 ProviderProfile；配置变化会使旧任务授权失效，不得授权 Shell、依赖安装、工具网络或 Git 远端操作。
- API Key、主密码和派生密钥不得进入 SQLite、日志、事件、异常、测试快照、长期记忆、命令行参数或 Git。测试只使用明确假值。
- 本机持久凭据只进入 OS Keyring；Keyring 不可用时仅支持进程内会话凭据。容器持久凭据使用 Argon2id + AES-256-GCM 文件，禁止明文回退。
- 所有核心测试使用 `httpx.MockTransport` 或 Stub，不访问真实网络；真实冒烟命令必须由用户显式执行且不进入 CI。
- 保持 `ScriptedMockProvider`、现有三机制演示、`make test`、GitHub Actions、GitLab CI 和 Docker 默认离线 Mock 行为不变。
- 每个 Task 在独立 Git worktree 中执行红—绿—重构；完成后依次进行规约符合性审查和代码质量审查，再以中文提交。
- 新建或修改的说明性文档与提交说明尽量使用中文。

## 文件职责图

- `providers/models.py`：Provider 类型、端点、配置和凭据状态的严格领域模型。
- `storage/provider_profiles.py`：只读写非秘密 ProviderProfile 和任务绑定。
- `providers/credentials.py`：凭据协议、Secret 包装、Broker 和稳定领域错误。
- `providers/keyring_credentials.py`：OS Keyring 适配器。
- `providers/encrypted_credentials.py`：容器认证加密文件适配器。
- `providers/registry.py`：从任务、Profile、凭据和授权构造 LLMProvider。
- `api/provider_routes.py`：Provider、凭据、解锁和连接检查端点。
- `runtime.py`：按 task_id 复用现有 Agent、工具、worktree 和 Provider 的运行时路由。
- `scripts/provider_smoke.py`：显式、交互式、绝不接收命令行 Key 的真实联网冒烟入口。

---

### Task 1: Provider 配置、任务绑定与 migration 004

**Files:**
- Create: `src/coding_agent_harness/providers/models.py`
- Create: `src/coding_agent_harness/storage/provider_profiles.py`
- Create: `src/coding_agent_harness/storage/migrations/004_provider_profiles.sql`
- Create: `tests/storage/test_migration_004.py`
- Create: `tests/storage/test_provider_profiles.py`
- Modify: `src/coding_agent_harness/domain/models.py`
- Modify: `src/coding_agent_harness/storage/repositories.py`
- Modify: `src/coding_agent_harness/api/dependencies.py`
- Modify: `tests/storage/test_migration_003.py`
- Modify: `tests/api/conftest.py`

**Interfaces:**
- Consumes: `Database.operation_lock`、现有 `TaskRepository` 和 `Redactor`。
- Produces:

```python
class ProviderKind(StrEnum):
    DEEPSEEK = "deepseek"
    QWEN = "qwen"

class ProviderProfile(BaseModel):
    id: UUID
    kind: ProviderKind
    model: str
    version: int
    created_at: datetime
    updated_at: datetime

class ProviderProfileRepository:
    async def create(self, profile: ProviderProfile) -> ProviderProfile: ...
    async def get(self, profile_id: UUID) -> ProviderProfile | None: ...
    async def list(self) -> tuple[ProviderProfile, ...]: ...
    async def update_model(self, profile_id: UUID, model: str) -> ProviderProfile: ...
```

`Task` 新增 `provider_profile_id: UUID | None = None`、`provider_profile_version: int | None = None` 与 `llm_api_authorized_at: datetime | None = None`。三者必须同时为空或同时非空；已有 Mock 任务保持三者为空。Profile 从 version 1 开始，修改 model 时在同一事务递增 version；任务授权绑定确切 version。

- [ ] **Step 1: 写 migration 和严格模型 RED 测试**

```python
async def test_v3_only_applies_004_and_preserves_existing_task(tmp_path: Path) -> None:
    database = await open_v3_fixture(tmp_path / "v3.db")
    row = await fetch_task_provider_columns(database)
    assert row == (None, None)
    assert await user_version(database) == 4

def test_task_requires_profile_and_authorization_together() -> None:
    with pytest.raises(ValidationError):
        Task.model_validate({
            **existing_task().model_dump(),
            "provider_profile_id": uuid4(),
        })
```

- [ ] **Step 2: 运行 RED 并确认失败原因**

Run: `.venv\Scripts\python.exe -m pytest tests/storage/test_migration_004.py tests/storage/test_provider_profiles.py tests/storage/test_migration_003.py -v`

Expected: FAIL，明确指出缺少 migration 004、`ProviderProfile`、Repository 或 Task 字段；不得出现联网或真实 Key 请求。

- [ ] **Step 3: 实现 migration 004 和模型**

`004_provider_profiles.sql` 必须创建 `provider_profiles`，并为 `tasks` 增加可空外键和授权时间：

```sql
CREATE TABLE provider_profiles (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('deepseek', 'qwen')),
    model TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
ALTER TABLE tasks ADD COLUMN provider_profile_id TEXT REFERENCES provider_profiles(id);
ALTER TABLE tasks ADD COLUMN provider_profile_version INTEGER;
ALTER TABLE tasks ADD COLUMN llm_api_authorized_at TEXT;
CREATE INDEX tasks_provider_profile_idx ON tasks(provider_profile_id);
CREATE TRIGGER tasks_provider_binding_insert
BEFORE INSERT ON tasks
WHEN (NEW.provider_profile_id IS NULL) != (NEW.provider_profile_version IS NULL)
  OR (NEW.provider_profile_id IS NULL) != (NEW.llm_api_authorized_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'invalid provider binding'); END;
CREATE TRIGGER tasks_provider_binding_update
BEFORE UPDATE OF provider_profile_id, provider_profile_version, llm_api_authorized_at ON tasks
WHEN (NEW.provider_profile_id IS NULL) != (NEW.provider_profile_version IS NULL)
  OR (NEW.provider_profile_id IS NULL) != (NEW.llm_api_authorized_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'invalid provider binding'); END;
```

模型名去除首尾空白后必须为 1—128 个 UTF-8 字节，拒绝控制字符；Repository 使用参数化 SQL、事务回滚和稳定 `ProviderProfileNotFoundError`，不得持久化任何凭据字段。

- [ ] **Step 4: 扩展 TaskRepository 与 LocalTaskRunner**

`TaskRepository` 的列集合、创建与读取必须覆盖两个新字段。`TaskRunner.create` 和 `LocalTaskRunner.create` 增加仅限关键字参数：

```python
async def create(
    self,
    workspace: Workspace,
    task_id: UUID,
    requirement: str,
    *,
    provider_profile_id: UUID | None = None,
    provider_profile_version: int | None = None,
    llm_api_authorized_at: datetime | None = None,
) -> Task: ...
```

旧调用无需修改即可继续创建 Mock 任务。

- [ ] **Step 5: 运行聚焦 GREEN 与 migration 回归**

Run: `.venv\Scripts\python.exe -m pytest tests/storage/test_migration_004.py tests/storage/test_provider_profiles.py tests/storage/test_migration_003.py tests/storage/test_recovery.py tests/api/test_tasks.py -v`

Expected: PASS；v0 依次执行 001—004，v3 只执行 004，v4 重开不执行 DDL，future database 使用版本 5 验证拒绝且不变异。

- [ ] **Step 6: 静态检查、双重评审和提交**

Run: `.venv\Scripts\python.exe -m ruff check src tests`

Run: `.venv\Scripts\python.exe -m mypy src`

先做规约符合性审查，再做代码质量审查；关闭 Critical/Important 后提交：

```text
git add src/coding_agent_harness/providers/models.py src/coding_agent_harness/storage/provider_profiles.py src/coding_agent_harness/storage/migrations/004_provider_profiles.sql src/coding_agent_harness/domain/models.py src/coding_agent_harness/storage/repositories.py src/coding_agent_harness/api/dependencies.py tests/storage/test_migration_004.py tests/storage/test_provider_profiles.py tests/storage/test_migration_003.py tests/api/conftest.py PLAN.md AGENT_LOG.md
git commit -m "feat: 持久化 Provider 配置与任务授权"
```

### Task 2: 会话、OS Keyring 与容器认证加密凭据

**Files:**
- Create: `src/coding_agent_harness/providers/credentials.py`
- Create: `src/coding_agent_harness/providers/keyring_credentials.py`
- Create: `src/coding_agent_harness/providers/encrypted_credentials.py`
- Create: `tests/providers/test_credentials.py`
- Modify: `src/coding_agent_harness/config.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: `ProviderProfile.id`；已固定依赖 `keyring`、`argon2-cffi` 和 `cryptography`。
- Produces:

```python
class CredentialPersistence(StrEnum):
    SESSION = "session"
    PERSISTENT = "persistent"

class CredentialStatus(BaseModel):
    configured: bool
    persistence: CredentialPersistence | None
    unlocked: bool

class PersistentCredentialStore(Protocol):
    def put(self, reference: str, secret: SecretStr) -> None: ...
    def get(self, reference: str) -> SecretStr | None: ...
    def delete(self, reference: str) -> None: ...

class UnlockableCredentialStore(PersistentCredentialStore, Protocol):
    @property
    def unlocked(self) -> bool: ...
    def unlock(self, master_password: SecretStr) -> None: ...
    def lock(self) -> None: ...

class CredentialBroker:
    async def put(self, profile_id: UUID, secret: SecretStr, persistence: CredentialPersistence) -> None: ...
    async def get(self, profile_id: UUID) -> SecretStr | None: ...
    async def delete(self, profile_id: UUID) -> None: ...
    async def status(self, profile_id: UUID) -> CredentialStatus: ...
    async def unlock(self, master_password: SecretStr) -> None: ...
    async def lock(self) -> None: ...
```

- [ ] **Step 1: 写凭据 RED 测试**

测试必须包含：Secret `repr` 不泄漏、会话凭据不写盘、Keyring 仅使用固定 service/name、Keyring 故障 fail closed、加密文件不含明文、错误主密码和篡改密文固定拒绝、临时文件替换失败保留旧 vault、Broker 删除同时清理会话和持久位置。

```python
def test_encrypted_store_rejects_tamper_without_secret_leak(tmp_path: Path) -> None:
    store = EncryptedCredentialStore(tmp_path / "credentials.v1", SecretStr("master-pass"))
    store.put("provider-profile:1", SecretStr("fake-provider-secret"))
    tamper_ciphertext(tmp_path / "credentials.v1")
    with pytest.raises(CredentialVaultError) as captured:
        store.get("provider-profile:1")
    assert "fake-provider-secret" not in repr(captured.value)
```

- [ ] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_credentials.py tests/test_config.py -v`

Expected: FAIL，缺少 Credential 类型和三个存储实现。

- [ ] **Step 3: 实现凭据协议与 Broker**

引用格式固定为 `provider-profile:<UUID>`。Broker 接收一个满足 `BlockingCallRunner.run(function, *args)` 的有界线程执行器，所有 Keyring、KDF、加密文件和 `fsync` 操作通过该执行器运行，取消时必须等待线程产生已观察结果。Broker 查询时会话凭据优先；`SESSION` 绝不调用持久 Store；`PERSISTENT` 失败不得回退为明文或静默改为会话保存。所有异常只使用稳定原因码，不拼接第三方异常正文。

- [ ] **Step 4: 实现 Keyring 和认证加密文件**

Keyring service 固定为 `coding-agent-harness`。加密文件 JSON envelope 固定包含 `version=1`、Argon2id 参数、16-byte base64 salt、12-byte nonce 和 ciphertext；明文是按引用排序的 JSON map。KDF 固定为 Argon2id `time_cost=3`、`memory_cost=65536 KiB`、`parallelism=1`、`hash_len=32`，读取时拒绝缺失、非整数、非正数或超出这些固定上限的参数，避免攻击者构造高资源 envelope。AES-256-GCM 的 associated data 固定为 `coding-agent-harness:credentials:v1`。写入同目录独占临时文件，flush、`fsync` 后原子替换；解密或 JSON schema 失败统一抛出 `CredentialVaultError("CREDENTIAL_VAULT_INVALID")`。

`HarnessSettings` 增加：

```python
credential_backend: Literal["keyring", "encrypted"] = "keyring"
credential_vault_path: Path | None = None
```

vault path 必须位于 `state_root`；encrypted backend 启动时保持 locked，主密码只能经运行期 unlock API 注入内存。

- [ ] **Step 5: 运行 GREEN、秘密探针和静态检查**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_credentials.py tests/test_config.py -v`

Run: `.venv\Scripts\python.exe -m ruff check src tests`

Run: `.venv\Scripts\python.exe -m mypy src`

Expected: 全部 PASS；测试 vault 与异常的字符串表示均不包含假秘密。

- [ ] **Step 6: 双重评审和提交**

规约审查必须逐项检查“不明文回退、Keyring 不可用仅会话、容器 locked”；质量审查必须检查原子写、KDF 参数上限、取消/异常和 Secret 生命周期。通过后提交：

```text
git add src/coding_agent_harness/providers/credentials.py src/coding_agent_harness/providers/keyring_credentials.py src/coding_agent_harness/providers/encrypted_credentials.py src/coding_agent_harness/config.py tests/providers/test_credentials.py tests/test_config.py PLAN.md AGENT_LOG.md
git commit -m "feat: 实现安全凭据保险库"
```

### Task 3: 固定端点与受限 ProviderRegistry

**Files:**
- Create: `src/coding_agent_harness/providers/registry.py`
- Create: `tests/providers/test_registry.py`
- Modify: `src/coding_agent_harness/providers/openai_compatible.py`
- Modify: `src/coding_agent_harness/providers/base.py`
- Modify: `tests/providers/test_contract.py`

**Interfaces:**
- Consumes: `ProviderProfileRepository`、`CredentialBroker`、`Task.provider_profile_id`、`Task.provider_profile_version`、`Task.llm_api_authorized_at`。
- Produces:

```python
PROVIDER_ENDPOINTS: Mapping[ProviderKind, str]

class ProviderRegistry:
    async def build_for_task(self, task: Task) -> LLMProvider: ...
    async def probe(self, profile_id: UUID) -> LLMResponse: ...

class ProviderConfigurationError(RuntimeError):
    code: str
```

- [ ] **Step 1: 写固定端点、授权和输出限制 RED 测试**

```python
async def test_registry_rejects_task_without_exact_profile_authorization() -> None:
    task = task_with(profile_id=PROFILE_A, authorized_at=None)
    with pytest.raises(ProviderConfigurationError, match="LLM_AUTHORIZATION_REQUIRED"):
        await registry.build_for_task(task)

async def test_provider_rejects_response_over_two_mebibytes() -> None:
    provider = provider_with_stub_stream(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ProviderError) as captured:
        await provider.complete(LLMRequest(messages=[]))
    assert captured.value.kind == "response_too_large"
```

覆盖 DeepSeek/Qwen 精确 URL、无凭据、vault locked、profile 不存在、任务 profile 或 version 不匹配、redirect、HTTP 分类、connect/read/write/pool timeout、2 MiB 响应上限、异常不泄漏请求头或响应正文。

- [ ] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_registry.py tests/providers/test_contract.py -v`

Expected: FAIL，缺少 Registry 和有界流式读取。

- [ ] **Step 3: 加固 OpenAICompatibleProvider**

Adapter 构造时接收已验证的固定 base URL；使用 `AsyncClient.stream`，累计响应不得超过 2 MiB，`follow_redirects=False`。`ProviderError` 只保留 `kind`、`retryable` 和稳定中文/英文诊断，不保存原始异常、response、request、header 或 body。

- [ ] **Step 4: 实现 ProviderRegistry**

Registry 只从 `PROVIDER_ENDPOINTS` 选择 URL；model 来自已验证 Profile；Key 从 Broker 临时读取。`build_for_task` 同时验证任务已绑定 profile、确切 profile version 和授权时间；配置 version 已变化时抛出 `PROVIDER_AUTHORIZATION_STALE`。`probe` 只发送固定最小消息“只回复 OK”，并且只能由显式 API 调用触发。

- [ ] **Step 5: 运行 GREEN、全 Provider 回归和静态检查**

Run: `.venv\Scripts\python.exe -m pytest tests/providers -v`

Run: `.venv\Scripts\python.exe -m ruff check src tests`

Run: `.venv\Scripts\python.exe -m mypy src`

Expected: PASS；Mock 契约不变，所有 HTTP 测试使用 `MockTransport`。

- [ ] **Step 6: 双重评审和提交**

```text
git add src/coding_agent_harness/providers/registry.py src/coding_agent_harness/providers/openai_compatible.py src/coding_agent_harness/providers/base.py tests/providers/test_registry.py tests/providers/test_contract.py PLAN.md AGENT_LOG.md
git commit -m "feat: 构建受限真实 Provider 注册表"
```

### Task 4: Provider、凭据与连接检查 API

**Files:**
- Create: `src/coding_agent_harness/api/provider_routes.py`
- Create: `tests/api/test_providers.py`
- Modify: `src/coding_agent_harness/api/app.py`
- Modify: `src/coding_agent_harness/api/dependencies.py`
- Modify: `src/coding_agent_harness/api/routes.py`
- Modify: `tests/api/conftest.py`
- Modify: `tests/api/test_security.py`

**Interfaces:**
- Consumes: Profile Repository、CredentialBroker、ProviderRegistry、现有 `SessionGuard` 和 `BlockingWorker`。
- Produces:

```text
GET    /api/providers
POST   /api/providers
PATCH  /api/providers/{profile_id}
PUT    /api/providers/{profile_id}/credential
DELETE /api/providers/{profile_id}/credential
POST   /api/providers/{profile_id}/probe
POST   /api/credential-vault/unlock
```

- [ ] **Step 1: 写 API schema、安全和零泄漏 RED 测试**

`POST /api/providers` 只接受 `{kind, model}`；credential 只接受 `{api_key, persistence}`；unlock 只接受 `{master_password}`。API Key 必须为 1—8192 个 UTF-8 字节，主密码必须为 12—1024 个 UTF-8 字节；二者都拒绝 NUL。所有 mutation 复用 Origin + session token。GET 只返回 profile、`configured/persistence/unlocked` 和更新时间，任何响应均不得出现提交的 Key 或主密码。

```python
async def test_credential_response_and_events_never_echo_secret(client: AsyncClient) -> None:
    response = await client.put(path, json={"api_key": "fake-secret", "persistence": "session"}, headers=headers)
    assert response.status_code == 200
    assert "fake-secret" not in response.text
    assert "fake-secret" not in await serialized_events(client)
```

另测：未知 Host、错误 Origin、额外字段、空/超长 Key、locked vault、Keyring 失败、凭据删除幂等、profile 更新递增 version、probe 只调用一次固定 Provider 且不授权任何工具。本阶段不删除 Profile；用户通过清除凭据停用它，避免跨 SQLite 与外部凭据 Store 的非原子删除。

- [ ] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_providers.py tests/api/test_security.py -v`

Expected: FAIL，路由不存在或依赖容器缺少 Provider 能力。

- [ ] **Step 3: 实现独立 provider router 和依赖注入**

Provider route 不并入已经较大的任务 `routes.py`。CredentialBroker 复用共享 `BlockingWorker`，其 `abandon_on_cancel=False` 语义保证同步凭据副作用不会在后台失联。probe 是用户点击产生的一次精确 LLM 网络授权；只返回 `ok/provider/model/error_code`，不得返回模型正文或第三方错误正文。

- [ ] **Step 4: 实现生命周期组合**

`create_app` 默认 lifespan 创建 Profile Repository、CredentialBroker、共享 `httpx.AsyncClient(trust_env=False, follow_redirects=False)` 和 ProviderRegistry；关闭顺序先停止新请求，再关闭 HTTP client、清空会话凭据、锁定 encrypted vault，最后关闭数据库。测试依赖允许完整注入 Stub。

- [ ] **Step 5: 运行 GREEN 与 API 回归**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_providers.py tests/api/test_security.py tests/api/test_projects.py tests/api/test_tasks.py -v`

Run: `.venv\Scripts\python.exe -m ruff check src tests`

Run: `.venv\Scripts\python.exe -m mypy src`

Expected: PASS；失败响应保持 `{code,message,details,event_id}`，凭据值无匹配。

- [ ] **Step 6: 双重评审和提交**

```text
git add src/coding_agent_harness/api/provider_routes.py src/coding_agent_harness/api/app.py src/coding_agent_harness/api/dependencies.py src/coding_agent_harness/api/routes.py tests/api/test_providers.py tests/api/conftest.py tests/api/test_security.py PLAN.md AGENT_LOG.md
git commit -m "feat: 提供 Provider 与凭据安全 API"
```

### Task 5: 将真实 Provider 绑定到现有 Agent 运行时

**Files:**
- Create: `src/coding_agent_harness/runtime.py`
- Create: `tests/agent/test_runtime.py`
- Modify: `src/coding_agent_harness/api/routes.py`
- Modify: `src/coding_agent_harness/api/dependencies.py`
- Modify: `src/coding_agent_harness/api/app.py`
- Modify: `src/coding_agent_harness/demo.py`
- Modify: `tests/api/test_tasks.py`
- Modify: `tests/agent/test_real_tool_loop.py`

**Interfaces:**
- Consumes: `ProviderRegistry.build_for_task`、`AgentOrchestrator`、`ActionParser`、`ToolRegistry`、`WorktreeManager`、Workspace trust profile。
- Produces:

```python
class RuntimeOrchestratorRouter(OrchestratorPort):
    async def propose_plan(self, task_id: UUID) -> Task: ...
    async def approve_plan(self, task_id: UUID) -> Task: ...
    async def run_until_wait(self, task_id: UUID) -> Task: ...
    async def approve_final(self, task_id: UUID) -> Task: ...
    async def record_runtime_failure(self, task_id: UUID, reason_code: str) -> Task: ...
```

- [ ] **Step 1: 写任务授权、真实 Provider 选择和 Mock 不回退 RED 测试**

测试场景：已配置 DeepSeek/Qwen Profile 的任务把授权时间与 profile 原子写入；未配置/locked profile 在创建 worktree 前拒绝；任务 A 不能使用任务 B 的 profile 授权；真实 Stub Provider 驱动现有计划与工具循环；Mock demo 不需要 profile；`PolicyContext.llm_api_authorized=True` 不允许任何 Shell/工具网络。

```python
async def test_real_provider_task_reuses_existing_feedback_loop(runtime_fixture: RuntimeFixture) -> None:
    task = await runtime_fixture.create_real_task(provider="deepseek")
    final = await runtime_fixture.run_scripted_http_task(task.id)
    assert final.state is TaskState.WAITING_FINAL_REVIEW
    assert runtime_fixture.feedback_was_in_next_provider_request()
```

- [ ] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/agent/test_runtime.py tests/agent/test_real_tool_loop.py tests/api/test_tasks.py -v`

Expected: FAIL，缺少 Runtime router、TaskRequest profile 字段或真实运行时组合。

- [ ] **Step 3: 提取通用 task runtime builder**

把 `DemoOrchestratorRouter._for` 中通用的 worktree、仓库地图、PathGuard、SafeGit、ToolRegistry 和 AgentOrchestrator 构造迁入 `runtime.py`；Demo 只注入 `ScriptedMockProvider` 和 `DemoProcessRunner`。真实 router 从 Task 加载 profile 和授权，经 Registry 构造 Provider。允许工具固定为 `read_file/search/apply_patch/run_verification/git_status/git_diff`；删除、Shell、安装、网络和远端 Git 仍不可用。

- [ ] **Step 4: 扩展任务创建 API**

`TaskRequest` 增加 `provider_profile_id: UUID | None = None`。显式 profile 时，API 必须在创建 worktree 前确认 Profile 存在、Credential configured 且 vault unlocked，然后在同一次 Task 持久化中写入 profile ID、当前 profile version 和当前 UTC 授权时间；无 profile 只允许注入的 Mock runtime，默认生产 runtime 返回 `PROVIDER_REQUIRED`。任务运行前再次复验 version，变化后进入 `WAITING_USER` 并要求重新确认，不能静默使用新模型。

- [ ] **Step 5: 运行 GREEN、机制 demo 和全 Python 回归**

Run: `.venv\Scripts\python.exe -m pytest tests/agent/test_runtime.py tests/agent/test_real_tool_loop.py tests/api/test_tasks.py -v`

Run: `mingw32-make demo`

Run: `.venv\Scripts\python.exe -m pytest`

Expected: 聚焦与全量 PASS；demo 仍只输出三项 PASS；所有真实 Provider 路径由 Stub 驱动。

- [ ] **Step 6: 静态检查、双重评审和提交**

Run: `.venv\Scripts\python.exe -m ruff check src tests`

Run: `.venv\Scripts\python.exe -m mypy src`

```text
git add src/coding_agent_harness/runtime.py src/coding_agent_harness/api/routes.py src/coding_agent_harness/api/dependencies.py src/coding_agent_harness/api/app.py src/coding_agent_harness/demo.py tests/agent/test_runtime.py tests/agent/test_real_tool_loop.py tests/api/test_tasks.py PLAN.md AGENT_LOG.md
git commit -m "feat: 将真实 Provider 接入 Agent 运行时"
```

### Task 6: 最小 WebUI、显式冒烟命令与阶段验收

**Files:**
- Create: `scripts/provider_smoke.py`
- Create: `tests/providers/test_provider_smoke.py`
- Modify: `web/src/types.ts`
- Modify: `web/src/api.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/api.test.ts`
- Modify: `web/e2e/harness.spec.ts`
- Modify: `Makefile`
- Modify: `scripts/test.ps1`
- Modify: `README.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/DEMO.md`
- Modify: `DEFERRED_WORK.md`
- Modify: `PLAN.md`
- Modify: `AGENT_LOG.md`

**Interfaces:**
- Consumes: Task 4 Provider API 和 Task 5 的 `provider_profile_id` 任务入口。
- Produces: 当前 WebUI 中最小 Provider 配置/状态/选择功能；`make provider-smoke PROVIDER=deepseek MODEL=deepseek-chat` 的显式真实联网入口。

- [ ] **Step 1: 写 Web 和 smoke RED 测试**

Web 测试覆盖：创建 DeepSeek/Qwen profile、隐藏输入 Key、选择 session/persistent、状态只显示“已配置”、删除后清空状态、probe 显示稳定结果、创建任务时发送 profile ID、切换 Workspace/任务不保留 Key 输入值。不得进行最终时间线或视觉重构。

smoke 测试注入 `getpass` 和 MockTransport，证明 Key 不来自 argv/env、不被打印，成功只输出 `PASS deepseek deepseek-chat`，失败只输出稳定 error kind。

- [ ] **Step 2: 运行 RED**

Run: `npm.cmd --prefix web run test -- --run`

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_provider_smoke.py -v`

Expected: FAIL，缺少功能入口和 smoke 脚本。

- [ ] **Step 3: 实现最小 WebUI 功能**

沿用当前单页布局和样式，只增加 Provider 配置区与任务 Provider 下拉框。API Key 使用 `type=password`、关闭 autocomplete、mutation 完成或失败后立即清空组件 state；不得写 localStorage/sessionStorage、URL、SSE 或 DOM 日志。encrypted backend locked 时显示解锁入口，主密码提交后同样立即清空。

- [ ] **Step 4: 实现显式 smoke 命令与文档**

`provider_smoke.py` 的 argv 只接受 `--provider` 和 `--model`；使用 `getpass.getpass` 读取 Key；复用固定端点和 OpenAI adapter；不会写 Vault。Makefile 目标不属于 `test`，CI 不调用：

```text
provider-smoke:
	"$(PYTHON)" scripts/provider_smoke.py --provider "$(PROVIDER)" --model "$(MODEL)"
```

README 和安全文档说明 Keyring、会话模式、容器 unlock、任务级网络授权、真实 smoke 与 CI 离线边界。没有真实凭据时明确记录“未执行”，不得写成通过。

- [ ] **Step 5: 增加离线 E2E 纵向切片**

Playwright 使用临时 Git 项目、Stub Provider API 和假凭据 Store，完成 profile 创建、凭据状态、任务选择 Provider、计划生成、批准、反馈修正和最终 diff。收尾继续证明 fixture 主分支未变且临时 worktree/进程回收。

- [ ] **Step 6: 运行阶段新鲜验证**

Run: `mingw32-make test`

Run: `mingw32-make demo`

Run: `.venv\Scripts\python.exe scripts\secret_scan.py`

Run: `.venv\Scripts\python.exe -m pip check`

Expected: Python、Ruff、mypy、Vitest、ESLint、TypeScript、Vite、Playwright、Mock 三机制、秘密扫描和依赖一致性全部退出 0。不得为了测试真实 Provider 而在 CI 注入 Key。

- [ ] **Step 7: 可选真实冒烟与如实记录**

仅当用户明确提供并授权使用本机凭据时运行：

```text
mingw32-make provider-smoke PROVIDER=deepseek MODEL=deepseek-chat
```

或：

```text
mingw32-make provider-smoke PROVIDER=qwen MODEL=qwen-plus
```

Expected: 只输出一行 PASS；失败时只记录 Provider、model、稳定 error kind 和时间，不记录 Key、请求或响应正文。没有凭据则跳过并记录环境限制。

- [ ] **Step 8: 最终双重评审、延期审计和提交**

规约审查逐条覆盖 `SPEC.md` 16.3 和本计划全局约束；质量审查重点覆盖 Secret 生命周期、取消/关闭、API fail-closed、真实运行时与 Mock 回归。只有 Critical/Important 为 0 且验证证据仍新鲜时提交：

```text
git add web/src/types.ts web/src/api.ts web/src/App.tsx web/src/App.test.tsx web/src/api.test.ts web/e2e/harness.spec.ts scripts/provider_smoke.py tests/providers/test_provider_smoke.py Makefile scripts/test.ps1 README.md docs/SECURITY.md docs/DEMO.md DEFERRED_WORK.md PLAN.md AGENT_LOG.md
git commit -m "feat: 交付真实 Provider 最小可用版本"
```

若 DeepSeek/Qwen 统一契约、产品接线、凭据生命周期和至少一个真实 smoke 均通过，可把 `DW-MVP-003` 标记为 `RESOLVED`；没有真实 smoke 时保持 `DEFERRED`。`DW-MVP-006` 继续保持 `DEFERRED`，因为最终共学 UI 尚未设计。

## 计划自审结论

- [x] `SPEC.md` 16.1—16.4 的 CL-1 要求均能映射到 Task 1—6。
- [x] 所有新增类型和方法均在首次消费前由前置 Task 定义。
- [x] 所有 Provider 核心测试离线，真实 smoke 与 CI 明确分离。
- [x] Mock、治理、worktree、反馈、三机制和一键测试均有回归命令。
- [x] 计划没有未决占位、跨 Task 隐式引用或未指定的错误处理步骤。
- [x] 每个 Task 都有 RED、GREEN、静态检查、两阶段评审和中文提交。
