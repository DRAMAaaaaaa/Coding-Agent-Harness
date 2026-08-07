# Task 3 实施报告

## 范围

- 使用 `TaskEvent` 作为唯一事实源，确定性投影 `plan`、`first_edit`、`verification_failure`、`final_delivery` 四类 IntentCard。
- 仅失败卡允许 QuestionService 提问；请求通过已绑定任务的 Provider，`LLMRequest` 仅含 `messages`，没有工具 schema 或 ToolRegistry。
- 新增只读 API 与最小 WebUI 卡片/提问展示；未实现通用回放、分支纠正、长期记忆或 UI 美化。

## RED/GREEN 证据

- RED：`python -m pytest tests/learning/test_intent.py tests/learning/test_questions.py tests/api/test_learning.py -q` 在 `learning` 包尚不存在时，以 `ModuleNotFoundError` 失败。
- GREEN：相同测试在实现后通过（4 passed）。WebUI 新增失败卡提问测试先因找不到“失败原因提问”失败，最小实现后 `vitest --run` 通过（25 passed）。
- 静态验证：Ruff 与 mypy 均通过；Web lint、typecheck、build、秘密扫描均通过；`git diff --check` 无输出。

## 文件

- `src/coding_agent_harness/learning/intent.py`、`questions.py`：事件投影、UTF-8 8 KiB 截断脱敏、失败节点只读问答与审计事件。
- `src/coding_agent_harness/api/learning_routes.py`：卡片读取与提问端点。
- `web/src/App.tsx`、`api.ts`、`types.ts`：最小失败卡提问界面。
- `tests/learning/`、`tests/api/test_learning.py`、`web/src/App.test.tsx`：离线 Stub/Mock 覆盖。

## 风险、延期与依赖

- 失败问答仍会追加状态保持的 `LEARNING_QUESTION_*` 事件，这是审计记录，不改变任务状态、代码、审批或 worktree；Provider 失败事件仅记录稳定的 `provider_kind`。
- 未使用真实网络、真实 Key 或新增依赖。所有测试使用 Stub/Mock Provider。
- `tests/storage/test_event_store.py` 的表集合断言目前失败：现有数据库包含 `provider_profiles`，但该旧测试的 `BUSINESS_TABLES` 未包含它；与本 Task 未接触存储迁移无关，未在本范围内修改。
- 无本 Task 合法延期项。

## 提交

- 实现提交 hash：`33fe0a54419f9648f98454d4a1e34c985dc7c89d`。
