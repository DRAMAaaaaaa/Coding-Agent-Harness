# GitHub Actions PowerShell 测试兼容性修复设计

## 背景与根因

GitHub Actions 的 Ubuntu 24.04 `test` 作业执行 `make test` 时，
`tests/demo/test_mechanism_demo.py` 中三个 Windows 启动脚本负向测试直接调用
`powershell.exe`。Ubuntu 不提供该可执行文件，因此测试在真正检查
`scripts/test.ps1` 的诊断行为之前就以 `FileNotFoundError` 失败。失败运行的事实为
`3 failed, 760 passed, 77 skipped`；Docker 构建与秘密扫描均成功。

## 目标与非目标

目标是恢复 Ubuntu 完整门禁，同时确保三个 Windows PowerShell 行为仍在 CI 中真实
执行。修复不得降低 Harness 核心测试、Mock 三机制演示、秘密扫描或 Docker 构建门禁。

本次不安装额外 PowerShell、不把完整门禁迁移到 Windows、不重写 Makefile，也不修改
Harness 产品代码。

## 方案

1. 三个 `scripts/test.ps1` 行为测试明确标记为仅 Windows 执行；Ubuntu 收集它们时给出
   可解释的 skip，而不是启动不存在的程序。
2. GitHub Actions 保留 Ubuntu 24.04 `test` 作业及原有 `make test`。
3. 新增轻量 `windows-powershell` 作业：使用 `windows-latest`、Python 3.11 和 Node 24，
   安装 `.[dev]` 后只运行 `tests/demo/test_mechanism_demo.py`。该文件同时验证 Mock 三机制
   报告与 PowerShell 启动脚本的三类 fail-closed 诊断；显式 Node 版本保证缺少 Web 依赖
   的测试不会依赖 runner 预装环境。
4. 交付契约测试固定 Windows 作业的 runner 与聚焦 pytest 命令，防止未来只跳过测试却
   意外移除 Windows 覆盖。

## 错误处理与验收

- Ubuntu：完整 `make test` 不再尝试执行 `powershell.exe`。
- Windows：三个负向测试必须实际运行，不能被 skip。
- 任一平台测试失败仍由原命令非零退出，CI 不使用 `continue-on-error`。
- 聚焦交付契约、机制演示测试、Ruff、完整一键测试和工作流 YAML 解析均须通过。
- Node.js Action 运行时弃用警告与本缺陷无关，本次不顺带升级第三方 Action 主版本。
