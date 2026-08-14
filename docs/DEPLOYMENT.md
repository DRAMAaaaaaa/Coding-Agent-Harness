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

## 短时公网 IP Mock 演示（需实机验收）

本节仅用于短时答辩；不要使用真实 Provider、API Key 或隐私项目。容器 8000 始终仅绑定 localhost。

```powershell
$env:HARNESS_PUBLIC_HOST='47.76.86.198'
$env:HARNESS_PUBLIC_ORIGIN='http://47.76.86.198'
docker compose -f compose.yaml -f deploy/compose.public-ip.yaml up --build
```

```bash
HARNESS_PUBLIC_HOST=47.76.86.198 HARNESS_PUBLIC_ORIGIN=http://47.76.86.198 docker compose -f compose.yaml -f deploy/compose.public-ip.yaml up --build
sudo install -m 644 deploy/nginx/coding-agent-harness-ip.conf /etc/nginx/sites-available/coding-agent-harness
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sfn /etc/nginx/sites-available/coding-agent-harness /etc/nginx/sites-enabled/coding-agent-harness
sudo nginx -t
sudo systemctl reload nginx
```

ECS/目标主机安全组只临时开放 TCP 80。逐项用后端 localhost、固定 Host Nginx、本机外网 GET 与浏览器工作台完成实机验证后，才可记录为通过；当前 Docker daemon、Nginx 与 ECS 浏览器路径均未验收。入口没有用户认证或 HTTPS：HTTP 页面、请求及临时会话头均为明文；无身份认证，任何可访问者都能交互。仅允许用户在场进行短时 Mock 演示，完成后立即关闭入口；长期生产必须使用 HTTPS、身份认证、会话与网络隔离等完整安全设计。

## 演示后撤销

```bash
HARNESS_PUBLIC_HOST=47.76.86.198 HARNESS_PUBLIC_ORIGIN=http://47.76.86.198 docker compose -f compose.yaml -f deploy/compose.public-ip.yaml down
sudo systemctl stop nginx
```

随后从安全组撤销 TCP 80。不要保留公网入口，也不要将其描述为生产部署。

## 状态与剩余验收

`/state` 只应使用专用卷或目录；每次启动创建唯一 `session-*`，不会自动删除待审计现场。确认不再需要时由用户删除旧会话或重建专用卷。公网部署尚未验收；生产化还需要 HTTPS、认证、会话/Origin 防护、独立 OS 身份、备份、速率限制、网络策略与真实部署 E2E。
