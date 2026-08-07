# Coding Agent Harness

## 项目简介

这是一个面向程序员的本地优先 Coding Agent Harness。程序员输入项目路径和编码需求，Harness 在独立 Git worktree 中执行受治理的文件修改，以测试结果驱动确定性纠错，最后从 WebUI 交付事件、验证证据和代码差异。Agent 循环、动作解析、治理、工具调度、反馈和停止逻辑均由本仓库实现。

## 核心机制

- `ScriptedMockProvider` 可注入且完全离线，使 Agent 行为可重复测试。
- 计划默认先等待批准；删除、越界、安装、网络、远端 Git 和高风险动作由代码策略拦截。
- 每项任务使用独立 worktree；写文件采用摘要复验和原子替换。
- 失败输出会被分类、形成稳定指纹并回灌下一轮；连续两轮无进展时停止并等待人工处理。
- SQLite 事件流、REST/SSE 与 WebUI 共同展示计划、动作、验证和最终 diff。

## 安装

要求 Python `>=3.11,<3.12`、Node.js 24、Git 和 GNU Make。首次准备环境会访问包仓库；请在可信终端中执行，不要由 Harness Agent 自动安装依赖。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm.cmd --prefix web ci
```

Linux/macOS 将 Python 路径替换为 `.venv/bin/python`，将 `npm.cmd` 替换为 `npm`。E2E 还需要本机可用的 Chromium/Edge；CI 会显式安装 Playwright Chromium。

## 源码运行

先构建前端，再启动完全离线的临时演示服务：

```powershell
npm.cmd --prefix web run build
.venv\Scripts\python.exe scripts\serve_demo.py --ready-file .tmp\ready.json --max-seconds 600
```

服务将实际 URL 写入 `.tmp/ready.json`，默认仅绑定随机 `127.0.0.1` 端口。它复制内置示例到临时 Git 仓库，不修改原始示例；完成最终批准或超时后自动退出并清理任务 worktree。

## WebUI

项目完成并经最终审批后，最终交付卡可由用户显式批准为一条项目经验；下一项任务仅在计划请求中收到这条带 ID 的不可信上下文，不能改变工具、治理或审批。真实 Provider 联网验收未执行。

WebUI 支持接入项目、提交需求、批准计划、查看 SSE 时间线、检查验证结果和 diff，以及最终批准。修改类请求需要首页返回的临时会话头和可信 Origin。当前生产工厂未接线真实模型；可执行完整路径由离线演示服务提供。

## Mock 演示

三机制演示不联网、不读取 API Key：

```powershell
mingw32-make demo
# 或
.venv\Scripts\python.exe scripts\mechanism_demo.py
```

固定输出分别证明：危险删除被治理护栏拦截、失败反馈使下一动作改变，以及相同失败指纹触发确定性停止。浏览器主路径由 Playwright 使用真实 REST/SSE 和临时 Git fixture 验收，详见 `docs/DEMO.md`。

## 一键验证

```text
make test-unit   # Python pytest + Web Vitest
make test-e2e    # Web 构建 + Playwright 浏览器验收
make test        # Ruff、mypy、全部测试、前端检查/构建和 E2E
make demo        # 三项确定性机制演示
```

Windows 可使用 `mingw32-make`，或运行 `powershell -File scripts/test.ps1 -Mode Unit|E2E|All|Demo`。

## Docker 与 Compose

```powershell
docker build -t coding-agent-harness:mvp .
docker run --rm -p 127.0.0.1:8000:8000 -v "${PWD}/examples/python_demo:/workspace/project:ro" -v "harness-state:/state" coding-agent-harness:mvp
# 或同时显式挂载只读示例项目
docker compose up --build
```

访问 `http://127.0.0.1:8000`。镜像用 Node/Python 多阶段构建并以非 root `harness` 用户运行；镜像不内置运行项目，容器 CMD 要求 `/workspace/project` 是显式挂载的现有目录。Compose 只把 localhost 端口、只读 `examples/python_demo` 和独立 state 卷暴露给容器。默认运行 Scripted Mock 演示，不需要 Key，完成最终批准后容器正常退出。缺少项目挂载或挂载目标不是目录时启动会 fail closed，不会删除宿主源。不要把用户主目录、真实 `.env` 或凭据目录挂入容器。

## 目录结构

```text
src/coding_agent_harness/  Agent、治理、反馈、工具、存储与 API
web/                       React WebUI、Vitest 与 Playwright
scripts/                   三机制和临时 WebUI 演示入口
examples/python_demo/      只读离线示例项目
tests/                     Python 单元、集成与交付契约测试
docs/                      安全、部署、演示及 Superpowers 过程文档
```

## 安全边界

Harness 只信任已批准的项目根、验证命令与配置指纹；普通工具不能访问 worktree 外路径或私有 `state_root`。安装依赖、工具网络、Git push/merge/release 和任意 Shell 不属于 MVP Agent 工具。已启动副作用若无法确认结果，会保留现场并等待人工接管，而不是自动重放或递归清理。详细边界见 `docs/SECURITY.md`。

## Provider 与凭据状态

面向最终用户的真实 DeepSeek/Qwen 调用尚未实现：仓库已有统一 Provider 协议和 OpenAI-compatible 底层适配器，但产品运行时未接线供应商选择、真实网络授权或凭据生命周期。首版只用 `ScriptedMockProvider` 验收。`.env.example` 仅含占位值；不要填写后提交，也不要把 Key 写入日志、事件、记忆或测试快照。

## 已知限制

- 公网部署尚未验收，也没有公开 URL、GHCR 镜像或多架构发布。
- Docker 动态构建/冷启动仍应在 Docker daemon 可用的机器上按 `docs/DEPLOYMENT.md` 验证；本次开发环境的 daemon 未运行。
- 首版不提供长期记忆、多 Agent 并发、真实 Provider 联网、凭据存储、依赖安装、网络工具或远端 Git 操作。
- 同一 UID 下的恶意原生进程不在首版防护保证内；发现路径身份或副作用不确定时必须人工检查。
- 容器是可重复的 Mock 演示，不是多租户或公网服务。

## 下一步

优先实现并安全评审 DeepSeek/Qwen 运行时接线和凭据生命周期；之后再考虑长期记忆、受审批的网络/依赖工具、多 Agent 调度、发布镜像与真实公网部署。延期范围以 `DEFERRED_WORK.md` 为准。
