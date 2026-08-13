# 部署与运行

## 源码方式

按 README 安装 Python/Node 依赖后执行：

```powershell
npm.cmd --prefix web run build
.venv\Scripts\python.exe scripts\serve_demo.py --ready-file .tmp\ready.json --max-seconds 600
```

读取 ready 文件中的 localhost URL。服务使用临时项目和状态，完成最终批准或超时后退出。

## Docker 构建与冷启动

```powershell
docker build -t coding-agent-harness:mvp .
docker run --rm -p 127.0.0.1:8000:8000 -v "${PWD}/examples/python_demo:/workspace/project:ro" -v "harness-state:/state" coding-agent-harness:mvp
```

推荐的完整本地配置为：

```powershell
docker compose up --build
```

Compose 将 `examples/python_demo` 只读挂载到专用 `/workspace/project`，并把 `/state` 放入独立命名卷；不会挂载整个用户主目录。镜像不 COPY 或内置运行项目，CMD 显式读取该挂载点；缺失、不可解析或非目录项目源会在复制/初始化前 fail closed，且不会删除源。WebUI 仅发布到 localhost。容器默认 Scripted Mock，不读取 API Key；完成最终批准后退出。

首次构建需要从镜像仓库和包仓库下载基础镜像及依赖。该网络动作应由用户在可信环境中显式执行，不是 Harness Agent 的网络工具能力。

## 短时公网 IP Mock 演示

本节仅用于 `http://47.76.86.198` 的短时答辩演示，不是生产部署。不要使用真实 Provider、API Key 或隐私项目；容器 8000 始终仅绑定宿主 localhost。

在目标主机的当前 PowerShell 会话设置两个非秘密变量，并使用两个 Compose 文件启动：

```powershell
$env:HARNESS_PUBLIC_HOST='47.76.86.198'
$env:HARNESS_PUBLIC_ORIGIN='http://47.76.86.198'
docker compose -f compose.yaml -f deploy/compose.public-ip.yaml up --build
```

POSIX/ECS 等价命令为：

```bash
HARNESS_PUBLIC_HOST=47.76.86.198 HARNESS_PUBLIC_ORIGIN=http://47.76.86.198 docker compose -f compose.yaml -f deploy/compose.public-ip.yaml up --build
```

把 `deploy/nginx/coding-agent-harness-ip.conf` 安装为 `/etc/nginx/sites-available/coding-agent-harness`，并链接到 `sites-enabled`：

```bash
sudo install -m 644 deploy/nginx/coding-agent-harness-ip.conf /etc/nginx/sites-available/coding-agent-harness
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sfn /etc/nginx/sites-available/coding-agent-harness /etc/nginx/sites-enabled/coding-agent-harness
sudo nginx -t
sudo systemctl reload nginx
```

若目标主机有其他 Nginx 站点，先人工确认其不需要作为默认 TCP 80 站点；本演示配置必须是唯一的 `default_server`，否则 `nginx -t` 会拒绝重复默认服务器。

安全组只开放 TCP 80，不开放 443 或 8000。依次验证容器后端 GET、本机带固定 Host 的 Nginx 代理 GET、公网 GET 和浏览器中的 Mock 主路径；只有用户从外部网络完成这些实际检查后，才能标记公网验收通过：

```bash
curl -i http://127.0.0.1:8000/
curl -i -H 'Host: 47.76.86.198' http://127.0.0.1/
curl -i http://47.76.86.198/
```

演示结束后停止容器和 Nginx，并在安全组撤销 TCP 80 规则：

```bash
docker compose -f compose.yaml -f deploy/compose.public-ip.yaml down
sudo systemctl stop nginx
```

随后从安全组删除 TCP 80 入站规则。需要再次演示时，重新执行上述完整流程和验证；不要保留公网入口。

## 动态验收清单

Docker daemon 可用时逐项执行：

```powershell
docker build -t coding-agent-harness:mvp .
docker run --rm coding-agent-harness:mvp python scripts/mechanism_demo.py
docker run --rm --entrypoint id coding-agent-harness:mvp
docker compose up --build
```

期望机制脚本仅输出三项 `PASS`，`id` 显示非 root `harness`，并可从 `http://127.0.0.1:8000` 打开 WebUI。不要在没有实际输出时宣称这些动态检查通过。本次开发环境的 Docker 客户端可用，但 daemon 未运行，因此只完成了静态交付契约与本地源码验证，动态镜像验收仍需在 daemon 可用环境复跑。

## 状态和恢复

`/state` 含演示 ready 信息以及每次启动时创建的唯一 `session-*` 目录，只能挂载专用目录或卷。服务会清理任务 worktree 和数据库状态，但保留会话 fixture 供最终 E2E/人工审计；因此同一个 Compose state 卷可重复启动，新启动不会复用或自动删除旧现场，而会创建另一唯一目录。确认不再需要审计证据后，由用户明确删除旧会话或重建专用卷。不要把 state 放进项目仓库。

## 发布状态

公网部署尚未验收。本仓库未提供真实公网 URL、托管密钥、GHCR 发布或多架构 release workflow；当前容器只面向本机、单用户、离线 Mock 演示。公网化前必须补充身份认证、CSRF/Origin 设计、独立 OS 身份、持久化备份、速率限制、网络策略与真实部署 E2E。
