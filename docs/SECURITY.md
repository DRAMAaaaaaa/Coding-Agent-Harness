# 安全边界

## 治理护栏

计划和危险动作由确定性策略审批；验证配置指纹改变会使批准失效。删除需精确路径/摘要审批，安装依赖、工具网络、远端 Git、发布和任意 Shell 不属于当前 Agent 工具。验证通过不代表命令本身安全，只应接入可信仓库。

## 工作区、worktree 与进程

被批准的项目根、每任务 worktree、验证配置指纹和私有 `state_root` 是不同信任域。普通工具只能处理仓库地图中的 worktree，不能读写 `state_root`。每任务独立 worktree，主分支不会自动 merge 或 push；`apply_patch` 有摘要复验、协作锁和原子替换。超时、中断或身份不一致属于不确定副作用：保留现场，人工接管，不自动重放或递归清理。

## Provider 与凭据

课程路径使用 Scripted Mock，不访问网络且不需真实 Key。`.env.example` 仅可含占位值；Key、Token、密码、私钥、`.env`、凭据库及含秘密日志都不得提交或回显到事件、测试、快照和 `AGENT_LOG.md`。发生泄露时停止相关工作、轮换凭据、清理 Git 历史，仅记录事故类型。

## 项目经验与隐私

项目经验限制为 2048 UTF-8 字节；空文本、NUL 或 Redactor 命中会整体拒绝。只接受完成任务的 `FINAL_SUMMARY_PROPOSED`，并以不可信、有界上下文供下一任务引用；它不能改变工具、治理或审批。不要将个人数据、真实项目内容或凭据写入经验。

## 公网 Mock

Compose 只发布 localhost，容器非 root、根文件系统只读，项目以只读方式挂载到 `/workspace/project`，状态单独放 `/state`。短时公网演示没有用户认证或 HTTPS，HTTP 内容为明文；公网部署尚未验收，禁止用于真实 Provider 或私密数据。

## 剩余风险

同一 UID 的恶意原生进程可替换、移动或篡改私有目录，当前不能抵御；缓解方式是独立 OS 身份、ACL 或 broker。容器不是多租户安全边界；不得挂载用户主目录、Docker socket、SSH 目录或真实凭据。详见 [延期台账](archive/ledgers/DEFERRED_WORK.md) 的 `DW-05-001`。
