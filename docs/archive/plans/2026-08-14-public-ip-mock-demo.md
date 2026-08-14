# 公网 IP Mock 演示部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让阿里云香港 ECS 通过 `http://47.76.86.198` 提供短时、无密钥、仅 Mock 的 Harness 演示，同时保持容器 8000 端口只绑定宿主 localhost。

**Architecture:** 现有 Compose 继续以 `127.0.0.1:8000` 发布容器；新增公网专用 Compose 覆盖，把显式公网 IPv4/Origin 传给 `serve_demo.py`。Nginx 是唯一公网入口，保留 Host 并转发到本机 8000；Harness 复用现有 `HarnessSettings` 和 `SessionGuard` 校验公网 Host、同源 Origin 与临时会话 Token。

**Tech Stack:** Python 3.11、FastAPI/Uvicorn、Pydantic Settings、Docker Compose、Nginx、pytest、PowerShell/GNU Make。

## Global Constraints

- 公网模式必须固定 `HARNESS_LLM_PROVIDER=mock`，不得读取、提交或演示真实 API Key。
- `compose.yaml` 的 `127.0.0.1:8000:8000`、只读示例挂载、只读根文件系统、`cap_drop: ALL` 与 `no-new-privileges` 必须保持不变。
- 公网 Host 与 Origin 必须成对配置；本任务只允许 `47.76.86.198` 与 `http://47.76.86.198`，其他地址一律拒绝。
- Nginx 只公开 TCP 80；TCP 8000、443、Docker API、数据库与管理端口不得开放。
- HTTP 仅用于短时课程 Mock 演示；禁止真实凭据、隐私项目与长期生产运行。
- 新建/修改的说明文档和 Git 提交尽量使用中文。
- 实施前执行一次陌生审计；实现采用红—绿—重构，并在完成后依次通过规约符合性与代码质量审查。

---

## 文件结构

- Create: `deploy/compose.public-ip.yaml` — 只提供公网演示所需的环境覆盖，不复制基础安全配置。
- Create: `deploy/nginx/coding-agent-harness-ip.conf` — 拒绝未知 Host，并把指定公网 IP 的 HTTP/SSE 请求转发到本机 8000。
- Modify: `scripts/serve_demo.py` — 解析成对的公网环境配置并构造可信 Host/Origin。
- Modify: `tests/distribution/test_delivery_files.py` — 锁定 Compose、Nginx、Mock、localhost 端口与文档交付契约。
- Modify: `tests/demo/test_serve_cleanup.py` — 锁定公网目标校验及 `_serve()` 向 `HarnessSettings` 传值的行为。
- Modify: `README.md` — 增加受限公网 Mock 演示入口和安全警告。
- Modify: `docs/DEPLOYMENT.md` — 提供 ECS 安装、启动、验证、关闭和故障定位命令。
- Modify: `PLAN.md`、`AGENT_LOG.md` — 记录 Task 状态、审计、测试、评审和提交哈希。

### Task 1：公网 IP Mock 演示纵向切片

**Files:**
- Create: `deploy/compose.public-ip.yaml`
- Create: `deploy/nginx/coding-agent-harness-ip.conf`
- Modify: `scripts/serve_demo.py`
- Test: `tests/demo/test_serve_cleanup.py`
- Test: `tests/distribution/test_delivery_files.py`
- Modify: `README.md`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `PLAN.md`
- Modify: `AGENT_LOG.md`

**Interfaces:**
- Consumes: `HarnessSettings(trusted_hosts=..., trusted_origins=...)` 的现有规范化校验；基础 `compose.yaml` 的 localhost 发布和安全挂载。
- Produces: `_trusted_request_targets(bind_port: int, public_host: str | None, public_origin: str | None) -> tuple[tuple[str, ...], tuple[str, ...]]`；环境变量 `HARNESS_PUBLIC_HOST`、`HARNESS_PUBLIC_ORIGIN`；Nginx 公网入口 `http://47.76.86.198`。

- [x] **Step 1: 创建隔离 worktree 并登记进行中状态**

从最新 `p1` 创建 `codex/public-ip-mock-demo` worktree。只把 `PLAN.md` 对应条目标为“进行中”，并在 `AGENT_LOG.md` 写入基线提交、worktree 路径与技能；不得复制 `.env`、私钥或运行时状态。

运行：

```text
git status --short
git worktree add .worktrees/public-ip-mock-demo -b codex/public-ip-mock-demo p1
```

预期：worktree 创建成功；主目录既有 `.tmp/` 与 `.venv-py39-backup/` 保持未跟踪且不进入新分支提交。

- [x] **Step 2: 执行陌生冷启动审计**

审计输入仅包含批准规格 `docs/superpowers/specs/2026-08-14-public-ip-mock-demo-design.md` 和本计划。审计员检查：环境变量是否能到达 Python 入口、Compose 合并后是否仍只绑定 localhost、Nginx 是否支持 SSE/拒绝未知 Host、测试命令是否可独立执行。把暂停点和修订写入 `SPEC_PROCESS.md`；若无阻塞，明确记录“可冷启动”。

预期：没有通过主对话、旧日志或真实 ECS 凭据补充隐含信息。

- [x] **Step 3: 写公网目标与交付契约失败测试**

在 `tests/demo/test_serve_cleanup.py` 增加：

```python
@pytest.mark.parametrize(
    ("host", "origin"),
    [
        (None, "http://47.76.86.198"),
        ("47.76.86.198", None),
        ("47.76.86.199", "http://47.76.86.199"),
        ("example.com", "http://example.com"),
        ("47.76.86.198:80", "http://47.76.86.198:80"),
        ("47.76.86.198", "https://47.76.86.198"),
    ],
)
def test_public_demo_targets_fail_closed(host: str | None, origin: str | None) -> None:
    with pytest.raises(ValueError, match="公网演示"):
        serve_demo._trusted_request_targets(8000, host, origin)


def test_public_demo_targets_append_exact_http_ipv4() -> None:
    hosts, origins = serve_demo._trusted_request_targets(
        8000, "47.76.86.198", "http://47.76.86.198",
    )
    assert hosts == ("127.0.0.1:8000", "localhost:8000", "47.76.86.198")
    assert origins == (
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://47.76.86.198",
    )
```

在 `tests/distribution/test_delivery_files.py` 增加断言：覆盖文件只传 `HARNESS_PUBLIC_HOST`/`HARNESS_PUBLIC_ORIGIN` 且 Provider 为 `mock`；基础服务命令仍调用 `scripts/serve_demo.py`，证明环境变量进入消费它们的 Python 入口；渲染后的端口仍为 `127.0.0.1:8000:8000`；Nginx 包含 `listen 80`、固定 `server_name 47.76.86.198`、拒绝默认 Host、`proxy_pass http://127.0.0.1:8000`、`proxy_set_header Host $host`、`proxy_buffering off`，且不包含 443/HSTS/API Key。

- [x] **Step 4: 运行测试并确认 RED**

运行：

```text
.venv/Scripts/python.exe -m pytest tests/demo/test_serve_cleanup.py tests/distribution/test_delivery_files.py -q
```

预期：FAIL，原因是 `_trusted_request_targets`、`deploy/compose.public-ip.yaml` 与 Nginx 配置尚不存在；既有测试继续通过。

- [x] **Step 5: 实现最小可信公网目标解析**

在 `scripts/serve_demo.py` 导入 `ip_address`，增加：

```python
def _trusted_request_targets(
    bind_port: int,
    public_host: str | None,
    public_origin: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    hosts = (f"127.0.0.1:{bind_port}", f"localhost:{bind_port}")
    origins = tuple(f"http://{host}" for host in hosts)
    if public_host is None and public_origin is None:
        return hosts, origins
    if public_host is None or public_origin is None:
        raise ValueError("公网演示 Host 与 Origin 必须同时配置")
    try:
        address = ip_address(public_host)
    except ValueError:
        raise ValueError("公网演示 Host 必须是无端口 IPv4 地址") from None
    if address.version != 4 or public_host != str(address) or public_host != "47.76.86.198":
        raise ValueError("公网演示 Host 必须是批准的固定 IPv4 地址")
    expected_origin = f"http://{public_host}"
    if public_origin != expected_origin:
        raise ValueError("公网演示 Origin 必须精确匹配 HTTP IPv4 Host")
    return (*hosts, public_host), (*origins, public_origin)
```

给 `_serve()` 增加关键字参数 `public_host`、`public_origin`，并用该函数结果构造 `HarnessSettings`。给参数解析器增加 `--public-host` 和 `--public-origin`，默认分别读取 `HARNESS_PUBLIC_HOST`、`HARNESS_PUBLIC_ORIGIN`；`main()` 把两值显式传入 `_serve()`。不得更改 Provider 构造，仍由 `ScriptedMockProvider(demo_script())` 驱动。

- [x] **Step 6: 增加 Compose 覆盖和 Nginx 配置**

创建 `deploy/compose.public-ip.yaml`：

```yaml
services:
  harness:
    environment:
      HARNESS_LLM_PROVIDER: mock
      HARNESS_PUBLIC_HOST: ${HARNESS_PUBLIC_HOST:?必须设置公网 IPv4}
      HARNESS_PUBLIC_ORIGIN: ${HARNESS_PUBLIC_ORIGIN:?必须设置 HTTP Origin}
```

创建 `deploy/nginx/coding-agent-harness-ip.conf`，包含默认 `return 444` server 和只接受 `47.76.86.198` 的 server；业务 location 使用 `proxy_http_version 1.1`、`proxy_set_header Host $host`、`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`、`proxy_set_header X-Forwarded-Proto $scheme`、`proxy_buffering off`、`proxy_read_timeout 300s`、`client_max_body_size 64k`，并转发到 `http://127.0.0.1:8000`。

- [x] **Step 7: 更新部署说明并转绿**

在 README 与 `docs/DEPLOYMENT.md` 写入以下准确流程：设置两个非秘密环境变量，使用两个 Compose 文件启动，将 Nginx 配置安装到 `/etc/nginx/sites-available/coding-agent-harness` 并链接到 `sites-enabled`，执行 `nginx -t` 后 reload；安全组仅开放 TCP 80；依次验证后端 GET、本机带 Host 的代理 GET、公网 GET和浏览器 Mock 主路径；演示后停止容器/Nginx并撤销 80 规则。

运行：

```text
.venv/Scripts/python.exe -m pytest tests/demo/test_serve_cleanup.py tests/distribution/test_delivery_files.py -q
.venv/Scripts/python.exe -m ruff check scripts/serve_demo.py tests/demo/test_serve_cleanup.py tests/distribution/test_delivery_files.py
.venv/Scripts/python.exe -m mypy scripts/serve_demo.py
docker compose -f compose.yaml -f deploy/compose.public-ip.yaml config
git diff --check
```

运行 Compose 渲染前，在当前 PowerShell 会话显式设置非秘密变量：

```powershell
$env:HARNESS_PUBLIC_HOST='47.76.86.198'
$env:HARNESS_PUBLIC_ORIGIN='http://47.76.86.198'
```

POSIX/ECS 等价命令为：

```bash
HARNESS_PUBLIC_HOST=47.76.86.198 HARNESS_PUBLIC_ORIGIN=http://47.76.86.198 docker compose -f compose.yaml -f deploy/compose.public-ip.yaml config
```

预期：聚焦测试、Ruff、mypy、Compose 渲染和差异检查全部退出 0；Compose 渲染仍显示 `127.0.0.1:8000:8000` 和 `HARNESS_LLM_PROVIDER: mock`。若本机没有 Docker daemon，Compose `config` 仍应可执行且不需要构建/启动容器。

- [x] **Step 8: 规约审查、质量审查与返工**

规约审查逐条核对：只读 Mock、localhost 8000、精确公网 Host/Origin、Nginx/SSE、完整启停文档与无密钥。规约通过后再做质量审查，重点检查环境变量 fail-closed、IPv4 规范化、Nginx 未知 Host、Compose 合并语义、测试确定性和文档没有虚假验收结论。所有 Critical/Important 清零后才能继续。

- [x] **Step 9: 执行完整新鲜验证（静态门禁）；Docker daemon/Nginx 容器/ECS 动态验收未执行**

运行：

```text
mingw32-make test
mingw32-make demo
.venv/Scripts/python.exe scripts/secret_scan.py
.venv/Scripts/python.exe -m pip check
docker compose -f compose.yaml -f deploy/compose.public-ip.yaml config
git diff --check
```

该步骤同样先设置 Step 7 的两个 PowerShell 非秘密环境变量。Docker daemon 可用时再执行确定性 Nginx 语法检查：

```powershell
docker run --rm -v "${PWD}/deploy/nginx/coding-agent-harness-ip.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.28-alpine nginx -t
```

预期：一键测试、三机制演示、秘密扫描、依赖检查、Compose 渲染和差异检查全部退出 0。Docker daemon 可用时额外执行镜像构建和容器本机冷启动；不可用时如实登记为 ECS 动态验收步骤，不宣称通过。

- [x] **Step 10: 提交、合并并给出 ECS 命令（代码已集成并推送；ECS 动态验收待用户执行）**

更新 `PLAN.md`、`AGENT_LOG.md` 和本计划复选框，写入技术提交和审查结论。提交标题：

```text
feat: 提供公网 IP Mock 演示部署
```

通过 `finishing-a-development-branch` 本地合并回 `p1`。用户随后明确授权自动推送并合并 `main`，因此 `p1` 与 `main` 已在非强制模式下推送到同一集成 Head。合并后已重新执行完整静态门禁；ECS 命令由 `docs/DEPLOYMENT.md` 提供。只有用户从外部网络实际打开 `http://47.76.86.198` 并完成 Mock 主路径后，才能把真实公网验收标记为通过。

## 自审结果

- 规格覆盖：公网 Host/Origin、localhost 端口、Mock、Nginx/SSE、测试、启停和风险声明均映射到 Task 1。
- 占位扫描：没有未决占位词、延后实施表述或未定义接口。
- 类型一致性：`_trusted_request_targets()` 的参数和返回类型在测试、入口与 `HarnessSettings` 消费处一致；固定 IP、Nginx `server_name`、环境变量名称与 Compose 完全一致。
