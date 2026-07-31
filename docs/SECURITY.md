# 安全边界

## 信任与隔离

Harness 把被批准的 Git 项目根、每任务 worktree、验证配置指纹和私有 `state_root` 视为不同信任域。普通 Agent 工具只能处理仓库地图中的 worktree 文件，不能读取或修改 `state_root`。Git 操作使用最小环境并在 materialize 前拒绝活动 checkout filter，避免隐式执行仓库配置的外部程序。

每个任务只在独立 worktree 中写入；主分支不会在最终人工处理前自动 merge 或 push。`apply_patch` 使用摘要复验、同目录协作锁和原子替换。删除要求包含精确路径/摘要的审批；安装依赖、工具网络、远端 Git、发布和任意 Shell 在 MVP 中固定不可用。

## 命令信任

验证命令来自识别出的项目配置，必须先由用户批准其完整配置指纹。配置变化会使批准失效。即使测试命令通过，也不等于命令本身安全；只应接入可信仓库，并在批准前检查 `pyproject.toml`、`package.json` 或 `.harness.yml`。

## 不确定副作用

工具启动后若超时、进程中断或后验身份不一致，Harness 将结果标记为不确定副作用，保留 worktree、分支或活动标记并等待人工检查。它不会自动重放可能已经完成的动作，也不会为追求“干净”而递归删除不确定路径。

## 凭据与日志

MVP 只使用 Scripted Mock，不需要真实 Key。`.env.example` 只能保存占位值；真实 API Key、Token、密码、私钥、`.env`、凭据数据库和包含秘密的日志不得提交。错误、事件、测试和 `AGENT_LOG.md` 均不得回显秘密值。若发生泄露，应立即停止相关工作、轮换凭据并清理 Git 历史，仅记录事故类型而不记录原值。

## 同一 UID 边界

首版不能抵御同一 UID 下恶意原生进程主动替换、移动或篡改私有状态目录。当前缓解措施是让 `state_root` 不进入 LLM/普通工具、进行路径身份和 Git 注册后验验证，并在不一致时 fail closed。需要抵御该威胁时，应使用独立 OS 身份、ACL 或 broker；详见 `DEFERRED_WORK.md` 的 `DW-05-001`。

## 容器边界

镜像以非 root `harness` 用户运行。镜像不内置运行项目，Docker/Compose 必须把一个现有目录只读挂载到专用 `/workspace/project`，并把私有状态单独挂载到 `/state`；缺失或非目录项目源 fail closed，服务只复制到独立 session，不删除源。Compose 只发布 `127.0.0.1:8000`，使用只读根文件系统、`no-new-privileges` 并移除 Linux capabilities。容器隔离不是多租户安全边界；不要挂载宿主用户目录、Docker socket、SSH 目录或真实凭据。
