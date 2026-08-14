# 部署与运行边界

## 已验证的源码流程

```powershell
npm.cmd --prefix web run build
.venv\Scripts\python.exe scripts\serve_demo.py --ready-file .tmp\ready.json --max-seconds 600
make test
make demo
```

ready 文件给出 localhost URL。服务使用临时项目和状态；完成最终批准或超时后退出。`make demo` 是离线 Scripted Mock 的三机制演示，不是外网 Provider 验收。

## Docker 与 Compose 静态配置

```powershell
docker build -t coding-agent-harness:mvp .
docker run --rm -p 127.0.0.1:8000:8000 -v "${PWD}/examples/python_demo:/workspace/project:ro" -v "harness-state:/state" coding-agent-harness:mvp
docker compose up --build
```

镜像与 Compose 的配置约束为：`/workspace/project` 只读、`/state` 使用独立卷、容器非 root、根文件系统只读、仅发布 localhost、默认 Scripted Mock。缺少或非目录项目源会 fail closed，不删除源。静态交付契约已经测试；Docker daemon 冷启动仍须在有 daemon 的机器实机验收，不能把配置测试写成运行成功。

## 常驻公网 IP Mock 演示（需实机验收）

本节用于把 Mock WebUI 持续运行在 ECS 公网 IP 上，便于答辩前后反复演示。不要使用真实 Provider、API Key 或隐私项目。容器 8000 始终仅绑定 localhost，公网入口只由 Nginx 的 80 端口提供。

```powershell
$env:HARNESS_PUBLIC_HOST='47.76.86.198'
$env:HARNESS_PUBLIC_ORIGIN='http://47.76.86.198'
docker compose -f compose.yaml -f deploy/compose.public-ip.yaml up --build -d
```

```bash
HARNESS_PUBLIC_HOST=47.76.86.198 HARNESS_PUBLIC_ORIGIN=http://47.76.86.198 docker compose -f compose.yaml -f deploy/compose.public-ip.yaml up --build -d
sudo install -m 644 deploy/nginx/coding-agent-harness-ip.conf /etc/nginx/sites-available/coding-agent-harness
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sfn /etc/nginx/sites-available/coding-agent-harness /etc/nginx/sites-enabled/coding-agent-harness
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

公网覆盖文件使用 `--max-seconds 0 --keep-alive`，并设置 `restart: unless-stopped`：容器不会因 24 小时超时自动退出，ECS 或 Docker 重启后也会自动恢复，除非你显式执行 `docker compose ... down` 或 `docker compose ... stop`。

公网演示时，直接把下面这个确定路径交给用户输入到 WebUI 的“项目路径”：

```text
/state/fixture
```

该路径是容器内可写的示例项目副本，不需要用户读取 `/state/ready.json`，也不会随 `session-*` 变化。

ECS/目标主机安全组只开放 TCP 80，不要开放 8000。逐项用后端 localhost、固定 Host Nginx、本机外网 GET 与浏览器工作台完成实机验证后，才可记录为通过；当前 Docker daemon、Nginx 与 ECS 浏览器路径均未验收。入口没有用户认证或 HTTPS：HTTP 页面、请求及临时会话头均为明文；无身份认证，任何可访问者都能交互。常驻公网只适合无真实数据、无真实 Key 的 Mock 演示；生产或长期对外使用必须补 HTTPS、身份认证、会话与网络隔离等完整安全设计。

## 演示后撤销

```bash
HARNESS_PUBLIC_HOST=47.76.86.198 HARNESS_PUBLIC_ORIGIN=http://47.76.86.198 docker compose -f compose.yaml -f deploy/compose.public-ip.yaml down
sudo systemctl stop nginx
```

随后从安全组撤销 TCP 80。若你只是暂停容器但准备稍后继续，可使用 `docker compose -f compose.yaml -f deploy/compose.public-ip.yaml stop`；若要彻底关闭并停止自动恢复，使用上面的 `down`。

## 状态与剩余验收

`/state` 只应使用专用卷或目录；本地短时演示仍会创建唯一 `session-*`，公网常驻演示固定重建 `/state/fixture` 与 `/state/state`，`/state/ready.json` 指向当前服务。确认不再需要时由用户删除旧会话或重建专用卷。公网部署尚未验收；生产化还需要 HTTPS、认证、会话/Origin 防护、独立 OS 身份、备份、速率限制、网络策略与真实部署 E2E。
