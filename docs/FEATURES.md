# 当前功能与证据

本文只描述仓库已有源码、测试或离线演示可定位的能力；不表示“全部完成”或“生产可用”。完整路径是：**需求 → 计划审批 → 隔离修改 → 确定性验证 → 回放与纠正 → 经验批准 → 交付**。

## 完整共学路径

用户从项目接入和需求描述开始，审阅计划后在隔离任务环境内执行；当前验证、差异与摘要完整时才能最终批准，并可把最终交付批准为项目经验。源码：`src/coding_agent_harness/agent/orchestrator.py`、`web/src/workbench/HarnessWorkbench.tsx`；证据：`tests/agent/test_orchestrator.py`、`web/src/App.test.tsx`。

## 自研内核

Agent 循环、动作解析、工具分发、状态机、Provider 抽象和停止逻辑均在本仓库实现并可注入 Mock。源码：`src/coding_agent_harness/agent/orchestrator.py`、`src/coding_agent_harness/providers/mock.py`；证据：`tests/agent/test_orchestrator.py`、`tests/agent/test_state_machine.py`。

## 确定性反馈

失败输出被分类并形成稳定指纹；相同失败无进展会停止等待人工，反馈可改变下一轮动作。源码：`src/coding_agent_harness/feedback/engine.py`；证据：`tests/feedback/test_engine.py`、`scripts/mechanism_demo.py`（`make demo`）。

## 治理、隔离与停止

计划审批先于执行；任务在 worktree 中运行，路径/副作用异常 fail closed 并保留现场。源码：`src/coding_agent_harness/governance`、`src/coding_agent_harness/workspace`；证据：`tests/governance`、`tests/workspace`、`tests/demo/test_mechanism_demo.py`。

## 六阶段工作台

工作台固定呈现项目接入、需求描述、计划审批、执行与验证、回放与纠正、交付与经验；阶段解锁由事件证据推导。源码：`web/src/workbench/workflow.ts`、`web/src/workbench/StageNavigator.tsx`；证据：`web/src/workbench/workflow.test.ts`、`web/src/App.test.tsx`、`web/e2e/harness.spec.ts`。

## 意图回放、提问与纠正

四类意图卡从事件投影；失败卡可零工具提问，单个失败节点可创建纠正分支并比较父子轨迹。源码：`src/coding_agent_harness/learning/intent.py`、`src/coding_agent_harness/replay/branches.py`；证据：`tests/learning/test_intent.py`、`tests/learning/test_questions.py`、`tests/replay/test_branches.py`。

## 项目经验

只有完成任务的最终摘要可被用户批准为有界经验，下一任务只接收该不可信上下文。源码：`src/coding_agent_harness/learning/`、`src/coding_agent_harness/api/learning_routes.py`；证据：`tests/learning/test_cards.py`、`tests/demo/test_router.py`、`web/src/App.test.tsx`。

## Provider / Mock 边界

课程演示固定为 `ScriptedMockProvider`，不访问网络。仓库也有真实 Provider 的 OpenAI-compatible 运行时适配与注册表，但本地契约测试不能替代真实外网任务验收。源码：`src/coding_agent_harness/providers/mock.py`、`src/coding_agent_harness/providers/openai_compatible.py`、`scripts/mechanism_demo.py`；证据：`tests/providers/test_registry.py`、`tests/providers/test_contract.py`、`tests/demo/test_mechanism_demo.py`。

## 工程交付

仓库包含单元、浏览器、静态检查、机制演示、Docker/Compose 静态契约和双 CI 配置。源码：`Makefile`、`.github/workflows/ci.yml`、`.gitlab-ci.yml`；证据：`tests/distribution/test_delivery_files.py`、`tests/demo/test_entrypoints.py`。

## 已知限制

WebUI 尚无连接测试和主动清除；没有用户认证或 HTTPS；Docker daemon、Nginx/ECS 浏览器和真实外网 Provider 任务均需要实机验收。公网 Mock 不能作为生产服务或真实数据通道。具体边界见 `README.md`、`docs/DEPLOYMENT.md` 和 `docs/SECURITY.md`。
