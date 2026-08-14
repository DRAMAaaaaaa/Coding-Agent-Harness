# DeepSeek/Qwen WebUI 真实连接测试设计

## 1. 背景与目标

仓库已经自行实现统一的 `LLMProvider`、DeepSeek/Qwen 固定端点、OpenAI-compatible 适配器、Provider Profile、会话凭据 Broker、任务绑定和 `ProviderRegistry.probe()`。当前 WebUI 也能够创建 Profile 并提交仅存在于后端内存的会话 API Key，但尚未暴露连接测试和主动清除能力，因此不能通过最终用户路径证明真实 Provider 可访问。

本次恢复 `DW-MVP-003` 的一部分：在现有 WebUI 中增加 DeepSeek/Qwen Provider 选择、会话凭据、真实连接测试和清除操作。本次使用用户已有的 DeepSeek Key 对 `deepseek-chat` 执行一次真实最小请求；Qwen 实现同一产品能力和完整离线契约，但由于用户当前没有 Qwen Key，必须明确记录“真实联网未执行”。

成功标准是用户可以在 WebUI 中安全输入 Key、显式触发固定最小请求并看到脱敏结果。真实 Provider 不在本次范围内驱动 Coding Agent 主循环，现有确定性 Mock 演示继续作为核心 Harness 验收路径。

## 2. 范围

### 2.1 本次交付

- WebUI 同时展示 DeepSeek 和 Qwen，默认模型分别为 `deepseek-chat` 与 `qwen-plus`。
- 用户可以创建或选择 Provider Profile，通过密码输入框提交会话 Key。
- 用户可以点击“配置并测试连接”，触发真实 Provider Probe。
- Probe 成功后，前端密码框立即清空；Key 仅保留在后端当前进程的会话内存中，以便用户重复测试或后续显式使用。
- 用户可以主动清除指定 Profile 的会话凭据；清除操作幂等。
- 页面仅展示配置状态和脱敏 Probe 结果，不展示 Key、请求头或模型响应正文。
- DeepSeek 完成一次人工触发的真实联网验收，并记录不含秘密的验收事实。
- Qwen 完成离线 HTTP Stub、API 和 WebUI 测试，但保持“真实联网未执行”。

### 2.2 明确不做

- 不让 DeepSeek/Qwen 驱动真实 Coding Agent 任务。
- 不持久化 API Key，不增加 Keyring、加密 Vault、`.env` 或浏览器存储回退。
- 不接受用户自定义 Provider URL，不增加通用网络工具能力。
- 不把真实网络请求加入 CI、`make test` 或 Mock 三机制演示。
- 不完成 Provider Profile 编辑/删除、最终视觉设计或多用户部署。

## 3. 架构与数据流

沿用现有组件，不建立第二套 Provider 客户端：

```text
WebUI 密码框
  -> PUT 会话凭据
  -> CredentialBroker / SessionOnlyCredentialStore
  -> POST Provider Probe
  -> ProviderRegistry.probe()
  -> OpenAICompatibleProvider
  -> 固定 DeepSeek/Qwen 官方端点
  -> 脱敏 ProbeResult
```

前端选择 Provider 和模型后，复用已有 Profile 创建与会话凭据接口。新增 Probe 路由调用现有 `ProviderRegistry.probe()`；新增清除路由调用 `CredentialBroker.delete(profile_id)`。Probe、更新和清除均使用现有 `ProviderBindingCoordinator` 对相同 Profile 串行化，避免测试过程中 Key 被替换或删除。

Probe 请求固定为“只回复 OK”，并通过 Provider 请求模型设置很小的最大输出 Token。端点仍由 `PROVIDER_ENDPOINTS` 固定，HTTP 客户端继续使用 `trust_env=False`、`follow_redirects=False` 和短超时。用户无法通过请求改变 URL、提示内容或网络目标。

## 4. API 契约

### 4.1 测试连接

`POST /api/providers/{profile_id}/probe`

成功响应只包含：

```json
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "status": "passed"
}
```

接口不返回模型回复正文。Profile 不存在、凭据未配置或 Provider 失败时，返回既有 API 错误信封和稳定错误代码。

### 4.2 清除会话凭据

`DELETE /api/providers/{profile_id}/session-credential`

成功后返回同一 Profile 的脱敏状态，`configured=false`。重复清除仍返回成功，不泄漏该 Profile 是否曾持有 Key。

## 5. 错误与安全处理

Provider/HTTP 异常映射为有限稳定类别：

- `AUTHENTICATION_FAILED`
- `RATE_LIMITED`
- `TIMEOUT`
- `NETWORK_UNAVAILABLE`
- `INVALID_PROVIDER_RESPONSE`
- `PROVIDER_UNAVAILABLE`

WebUI 为这些代码提供中文说明，但不得显示上游响应正文、Authorization Header、API Key 或完整异常对象。所有错误路径都必须清空前端密码输入值。

API Key 不得进入 `localStorage`、`sessionStorage`、URL、SQLite、任务事件、SSE、日志、异常、截图、测试快照、`AGENT_LOG.md` 或 Git。真实验收由用户在本地 WebUI 中亲自输入；智能体不请求、读取或记录 Key。页面刷新或后端退出会丢失会话 Key；用户可以通过“清除凭据”立即撤销。

## 6. WebUI 交互

现有 Provider 区域保留单页结构，只做最小增量：

1. 选择 DeepSeek 或 Qwen；切换时设置对应默认模型并清空密码输入。
2. 输入 Key 后点击“配置并测试连接”。
3. 前端创建/复用 Profile、提交会话 Key并调用 Probe；请求发出后立即清空输入。
4. 状态依次显示“正在测试”“连接测试通过”或脱敏失败说明。
5. 已配置 Profile 提供“测试连接”和“清除凭据”，避免每次都创建重复 Profile。
6. Qwen 可以正常配置和测试，但交付文档在实际测试前始终标记“真实联网未验收”。

## 7. TDD 与验收

所有实现采用红—绿—重构：

- Provider 离线契约覆盖固定端点、固定提示、输出上限、禁止重定向、环境代理关闭、成功解析和错误映射。
- API 测试覆盖 Probe 成功、Profile 不存在、未配置凭据、401、429、超时、网络失败、非法/过大响应、清除幂等和并发协调。
- 秘密负向测试证明 Key 不进入响应、事件、数据库、日志或异常文本。
- Web 组件测试覆盖双 Provider 默认模型、密码输入、提交后清空、测试状态、失败状态、主动清除和切换 Provider 清空。
- Playwright 使用 HTTP Stub 完成“配置 -> Probe 通过 -> 清除”的离线纵向切片。
- 最终运行完整 `make test`、Mock 三机制演示、秘密扫描、依赖检查和差异检查。

真实联网验收不进入自动测试。实现和离线门禁通过后启动本地 WebUI，由用户输入 DeepSeek Key并点击测试。验收记录只保存 UTC 时间、Provider、模型和 `passed/failed`；不保存 Key、提示、请求头或回复正文。

## 8. 文档与延期状态

更新 README、安全说明和 Demo 文档，说明会话 Key 生命周期、真实 Probe 的人工触发方式、费用/网络边界以及 CI 仍完全离线。

DeepSeek 真实 Probe 通过后，`DW-MVP-003` 更新为“部分完成：DeepSeek 已真实联网验收，Qwen 因无凭据未执行”，不能标记 `RESOLVED`。`DW-MVP-006` 仍保持延期，因为持久凭据、Vault UI 和高级 WebUI 不属于本次范围。

## 9. 批准记录

用户于 2026-08-10 逐项批准：WebUI Probe 方案、DeepSeek/Qwen 双选项、后端会话内存凭据、Probe 后复用与主动清除、仅执行最小真实连接测试而不驱动完整 Agent，以及本设计的架构、安全、错误处理、UI、测试和验收边界。
