# 共学回放式 Coding Agent Harness

## 项目简介

这是一个本地优先的共学回放式 Coding Agent Harness。用户接入本地 Git 项目、描述需求并批准计划后，Harness 在隔离 worktree 中修改与验证；六阶段工作台把关键证据、意图和人工决定留在可回看的路径中。它交付可审查的差异与验证证据，不以模型口头声明代替验收。

## 产品特色

- 以“项目接入 → 需求描述 → 计划审批 → 执行与验证 → 回放与纠正 → 交付与经验”组织单个任务。
- 在失败或治理节点展示意图卡；失败卡可零工具提问，并能从一个失败节点创建纠正分支、查看比较。
- 用户可将已完成任务的最终交付批准为一条项目经验，供下一任务以有界、不可信上下文引用。
- `ScriptedMockProvider` 驱动离线、可重复的课程主路径；治理与反馈由仓库代码而非提示词保证。

## 已完成功能

当前已实现：受批准计划后的任务执行、确定性反馈与停止、隔离 worktree、意图卡、失败提问、单级纠正分支、最终审查与项目经验，以及六阶段 React WebUI。功能证据、源码入口和测试/演示路径见 [功能清单](docs/FEATURES.md)。

## 安装

要求 Python `>=3.11,<3.12`、Node.js 24、Git 和 GNU Make。首次安装会访问包仓库；请在可信终端显式执行，不能由 Harness 工具自动安装依赖。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm.cmd --prefix web ci
```

Linux/macOS 使用 `.venv/bin/python` 和 `npm`。浏览器 E2E 还需要本机 Chromium/Edge；CI 会显式安装 Playwright Chromium。

## 运行

先构建前端，再启动完全离线的临时演示服务：

```powershell
npm.cmd --prefix web run build
.venv\Scripts\python.exe scripts\serve_demo.py --ready-file .tmp\ready.json --max-seconds 600
```

读取 `.tmp/ready.json` 中的 localhost URL。服务把示例复制到临时 Git fixture，不修改原示例；完成最终批准或超时后退出。工作台的“高级设置”可显示 Provider 配置，但 WebUI 尚未提供连接测试和主动清除；勿将真实凭据用于课程 Mock 主路径。

## 演示

完整五分钟操作、最终 UI 名称和收尾检查见 [演示脚本](docs/DEMO.md)。离线三机制演示：

```powershell
make demo
```

`make demo` 由 Scripted Mock 固定驱动，不访问网络、无需 API Key。真实外网 Provider 任务尚未验收。

## 分发

源码全量门禁和单项门禁：

```powershell
make test-unit
make test-e2e
make test
make demo
```

Docker 镜像仅作本地 Mock 演示：

```powershell
docker build -t coding-agent-harness:mvp .
docker run --rm -p 127.0.0.1:8000:8000 -v "${PWD}/examples/python_demo:/workspace/project:ro" -v "harness-state:/state" coding-agent-harness:mvp
```

项目源必须只读挂载到 `/workspace/project`，状态单独存入 `/state` 卷。Compose 默认只发布 localhost。Docker daemon、Nginx 和 ECS 浏览器主路径仍须按 [部署说明](docs/DEPLOYMENT.md) 在实机验收，不能仅凭静态配置宣称通过。

公网 IP Mock 演示可按 [部署说明](docs/DEPLOYMENT.md) 以 `--max-seconds 0 --keep-alive` 和 `restart: unless-stopped` 常驻在 ECS 上：确认无需保留默认站点后，执行 `sudo rm -f /etc/nginx/sites-enabled/default`，再执行 `sudo ln -sfn /etc/nginx/sites-available/coding-agent-harness /etc/nginx/sites-enabled/coding-agent-harness`、`nginx -t`、`systemctl enable --now nginx` 和 reload；安全组只开放 TCP 80，不开放 8000。该入口是 HTTP：HTTP 页面、请求及临时会话头均为明文；无身份认证，任何可访问者都能交互。常驻公网只适合无真实数据、无真实 Key 的 Mock 演示；生产或长期对外使用必须使用 HTTPS、身份认证、会话与网络隔离等完整安全设计。

## 目录结构

```text
src/coding_agent_harness/  自研 Agent、治理、反馈、回放、学习、API
web/                       React 六阶段工作台、Vitest、Playwright
scripts/                   机制演示、临时服务、秘密扫描
tests/                     Python 单元、集成与交付契约
docs/                      当前功能、演示、部署与安全说明
docs/archive/              已归档的历史计划、规格、台账与报告
```

## 安全边界

普通工具不能访问私有 `state_root` 或 worktree 外路径；每任务在独立 worktree 工作，危险操作须由确定性治理审批。对不确定副作用保留现场并人工接管。镜像使用非 root 用户、只读项目挂载与独立状态卷，但这不是多租户边界。完整约束见 [安全说明](docs/SECURITY.md)。

## 已知限制

- 尚未提供用户认证或 HTTPS；公网入口只能用于无真实数据、无真实 Key 的 Mock 演示，不适合作为生产服务。
- WebUI 尚未提供连接测试和主动清除；真实 Provider 网络调用及其凭据生命周期不应据此推断已验收。
- 真实外网 Provider 任务尚未验收；公网 Docker/Nginx/ECS 操作也不等于生产部署。
- 同一 UID 的恶意原生进程、长期多用户服务、任意网络/依赖工具、自动 merge/push 不在当前保证内。

## 第三方组件与许可证

下表只记录当前锁定/已安装的直接证据；传递依赖与无法确认项不猜测，提交课程前请由学生复核上游 LICENSE。

| 组件 | 锁定版本 | 用途 | 许可证 | 证据 |
|---|---:|---|---|---|
| React / React DOM | 19.2.7 | WebUI | MIT | `web/package-lock.json` 的 `node_modules/react`、`react-dom` |
| React Router | 7.18.1 | 路由依赖 | MIT | `web/package-lock.json` 的 `node_modules/react-router-dom` |
| Vite / Vitest / ESLint | 8.1.4 / 4.1.10 / 10.7.0 | 构建、测试、静态检查 | MIT | `web/package-lock.json` 对应包条目 |
| TypeScript / Playwright | 6.0.3 / 1.61.1 | 类型检查、浏览器 E2E | Apache-2.0 | `web/package-lock.json` 对应包条目 |
| FastAPI / Pydantic / pydantic-settings | 0.139.0 / 2.13.4 / 2.14.2 | API、数据模型、配置 | MIT | 已安装 distribution metadata |
| Uvicorn / HTTPX | 0.51.0 / 0.28.1 | ASGI、HTTP 客户端 | BSD-3-Clause | 已安装 distribution metadata |
| Keyring / argon2-cffi / PyYAML | 25.7.0 / 25.1.0 / 6.0.3 | 凭据接口、哈希、YAML | MIT | 已安装 distribution metadata |
| cryptography | 49.0.0 | 加密原语 | Apache-2.0 OR BSD-3-Clause | 已安装 distribution metadata |
| aiosqlite | 0.22.1 | SQLite 异步访问 | 待学生复核 | metadata 未声明；查阅 [上游 LICENSE](https://github.com/omnilib/aiosqlite/blob/main/LICENSE) |

## 课程交付导航

- 当前产品能力：[docs/FEATURES.md](docs/FEATURES.md)
- 五分钟答辩与机制演示：[docs/DEMO.md](docs/DEMO.md)
- 本地/Docker/公网 Mock 的验收边界：[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- 安全与隐私边界：[docs/SECURITY.md](docs/SECURITY.md)
- 学生本人填写的反思提纲：[REFLECTION.md](REFLECTION.md)
- 历史规格、计划、台账与报告：[docs/archive/README.md](docs/archive/README.md)
