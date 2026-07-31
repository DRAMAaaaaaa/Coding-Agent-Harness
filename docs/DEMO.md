# 机制与 WebUI 演示

## 三项确定性机制

运行：

```powershell
mingw32-make demo
```

或直接运行 `.venv\Scripts\python.exe scripts\mechanism_demo.py`。Scripted Mock 固定驱动真实 AgentOrchestrator，整个过程不访问网络、不读取真实 LLM，也不需要 API Key。

输出应严格包含：

```text
PASS governance_guard
PASS feedback_changed_action
PASS deterministic_stop
```

第一项证明危险删除被代码治理层拦截且工具零调用；第二项注入一次测试失败，证明反馈进入下一次 LLM 请求并使动作从验证改为 patch；第三项证明相同失败指纹连续两轮无进展后进入人工等待状态。这三项对应课程机制演示和本项目“确定性反馈闭环”的主要贡献。

## WebUI 完整路径

执行 `make test-e2e`。Playwright 启动真实 localhost 服务、临时 Git fixture 和 Scripted Mock，自动完成项目接入、信任确认、需求输入、计划批准、失败反馈、修改、再次验证、diff 展示和最终批准；收尾检查原 fixture HEAD/状态未被任务 worktree 污染，并回收临时资源。

也可按 README 的源码命令人工启动，将 ready JSON 中的 URL 粘贴到浏览器。示例需求可写“把 VALUE 修改为 2 并通过测试”。演示只适用于内置 `examples/python_demo` 的固定脚本，不是通用自然语言模型。

## Docker 演示

执行 `docker compose up --build` 后访问 `http://127.0.0.1:8000`。Compose 只读挂载示例并使用独立 state 卷。若 Docker daemon 不可用，保留失败证据并在另一台可用机器复跑，不得把静态配置测试描述成容器冷启动已经通过。
