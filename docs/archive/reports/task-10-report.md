# MVP-4 Task 10 实现报告

## 交付

- 多阶段 `Dockerfile`：Node 24 Web 构建、Python wheel 构建、Python 3.11 非 root runtime。
- `compose.yaml`：仅发布 localhost、只读示例挂载、独立 state 卷、Scripted Mock。
- GitHub push/PR：`make test`、全仓秘密扫描、Docker build；GitLab 精确 `unit-test` 执行 `make test-unit`。
- 中文 README、SECURITY、DEPLOYMENT、DEMO 和安全占位 `.env.example`。
- 交付契约测试及容器 host/port、可重复启动行为回归。

## TDD 与修复

- 初始交付契约：`7 failed` → `9 passed`。
- 容器显式绑定：argparse RED → host/port 参数 GREEN。
- Compose 重启：第二次启动 `FileExistsError` RED → 每次唯一 `session-*`。
- E2E 收尾：临时目录过早删除导致 Git 128 → 保留唯一审计会话，Playwright `3 passed, 1 skipped`。
- 秘密扫描：拒绝整文件排除；全仓候选按文件路径和完整匹配 SHA-256 精确 allowlist，失败只打印文件名。

## 新鲜验证

- `mingw32-make test`：Python `730 passed, 15 skipped`；Vitest `21 passed`；Playwright `3 passed, 1 skipped`；Ruff、mypy、ESLint、TypeScript、Vite build 通过。
- `mingw32-make demo`：三项固定 PASS。
- `docker compose config --quiet`、`pip check`、精确秘密扫描通过。
- Docker client `29.1.3` 可用，但 daemon 管道不存在；未执行/伪造镜像 build、机制容器、非 root 身份和 WebUI health 动态通过。

## 边界

无新增延期。既有真实 DeepSeek/Qwen 产品接线、凭据生命周期、GHCR/多架构和公网部署仍明确未实现或未验收。未联网、安装依赖、push、发布或接触真实凭据。

## 规约 I1 返工

独立规约首审对 `783f835` 的原始结论保持 Spec No、Important 1。I1 RED 为 `7 failed, 4 passed`：镜像内置 examples、容器 CMD 无显式项目源、Compose/单条运行文档挂载点不符合专用边界，且无缺失/非目录源拒绝。GREEN 后 Dockerfile 不再 COPY examples，CMD 强制 `--project-source /workspace/project`；Compose 与 `docker run` 同时只读挂载项目并挂载 `/state`。源码演示未传参数时仍使用仓库内置示例。显式源在任何 fixture 创建前解析并要求现有目录，失败不删除源。

返工验证：distribution + 服务清理 `19 passed`（包含显式挂载源实际复制且源保持不变），Playwright `3 passed, 1 skipped`，`make demo` 三项 PASS，Compose 解析通过。无新增延期；等待独立规约复审，不在本报告中改写首审结论。

## 质量 I1 返工

质量首审关于 CI 秘密扫描的原始结论保持不变。本轮根因是工作流以 `|| true` 吞掉了 `git grep` 的全部非零退出码，无法区分无匹配（`1`）与扫描器错误（大于 `1`），从而产生 fail-open。先新增四项行为测试，RED 为 `4 failed`（扫描器入口不存在）；随后实现无第三方依赖的 `scripts/secret_scan.py`，CI 仅调用该脚本。脚本只接受 `0/1`，扫描器错误返回原非零码并只给出通用诊断；未知命中只输出文件名并失败；allowlist 仍精确匹配路径与完整命中 SHA-256。另新增 Git ERE 兼容回归，RED 为 `1 failed, 4 passed`（Python 非捕获分组不被 `git grep -E` 支持），GREEN 后区分 Git/Python 正则。

质量收紧：交付契约改为检查 Docker 最终 `USER`、全部 `EXPOSE` 与最终 JSON `CMD`，并对 Compose 的 `read_only`、`cap_drop`、`security_opt`、项目只读挂载与 `/state` 目标做结构化断言；GitHub workflow 检查精确的实际 `run` 命令。无新增延期、联网、安装依赖、Docker 功能或产品功能。

补充安全清理：扫描发现受版本控制的 Task 7 过程报告含一个测试式字符串；它不是测试夹具，已改为不匹配扫描规则的中文脱敏描述，未输出或记录原值。allowlist 现仅保留三个测试文件路径，并以回归测试锁定该集合。

## 返工闭环状态

规约 I1 返工提交为 `ea61388`，质量 I1 返工提交为 `f902512`。独立规约复审结论为 Spec Yes，质量复审结论为 Approved，Critical / Important / Minor 均为 `0 / 0 / 0`。

## 最终门禁

首次合并前全量测试发现 Web 正向用例在异步计划事件到达前同步查找按钮的竞态；`ba01cd7` 只把相关正向查询改为异步等待，不修改生产 Web，完整 Web 测试连续三轮均为 `21 passed`。最终独立复审覆盖 `5e08b07..ba01cd7`，结论为 Spec Yes、Quality Approved、Critical / Important / Minor `0 / 0 / 0`、Ready to merge Yes。

主控在 `ba01cd7` 上重新运行 `mingw32-make test`，得到 Python `739 passed, 15 skipped`、Vitest `21 passed`、Playwright `3 passed, 1 skipped`，Ruff、mypy、Web lint/typecheck/build 全部通过；`make demo` 三项 PASS，`pip check`、本地秘密扫描、Compose 解析与差异检查通过。Docker daemon 未运行，因此动态镜像验证仍按事实保留为环境未验收项；Task 10 无新增延期，待本地快进合并到 `p1`。

本地 `p1` 已以 `--ff-only` 合并到 Task 关闭 Head `d01796d`。合并后重新运行相同门禁，`make test` 仍为 Python `739 passed, 15 skipped`、Vitest `21 passed`、Playwright `3 passed, 1 skipped`，其余静态、构建、demo、依赖、秘密扫描与 Compose 门禁均通过；未 push。
