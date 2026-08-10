# GitHub Actions PowerShell 测试兼容性修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Ubuntu 完整门禁通过，同时由 Windows CI 真实执行三个 PowerShell 启动脚本测试。

**Architecture:** 平台专用测试通过 pytest 条件标记限定到 Windows；GitHub Actions 保留 Ubuntu 主门禁，并增加只运行机制演示测试文件的轻量 Windows 作业。交付契约固定该覆盖关系。

**Tech Stack:** Python 3.11、pytest、GitHub Actions YAML、PowerShell。

## Global Constraints

- 不修改 Harness 产品代码、Makefile、GitLab CI、Docker 或秘密扫描。
- Ubuntu `test` 作业继续运行 `make test`，不允许 `continue-on-error`。
- Windows 作业必须真实运行 `tests/demo/test_mechanism_demo.py`。
- 新建或修改的说明文档与提交说明尽量使用中文。

---

### Task 1: 修复跨平台测试分工

**Files:**
- Modify: `tests/distribution/test_delivery_files.py`
- Modify: `tests/demo/test_mechanism_demo.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `PLAN.md`
- Modify: `AGENT_LOG.md`

**Interfaces:**
- Consumes: 现有 `scripts/test.ps1`、Ubuntu `make test` 和 GitHub Actions 交付契约。
- Produces: `windows-powershell` CI 作业；三个仅 Windows 的 pytest 测试；防止 Windows 覆盖被移除的静态契约。

- [ ] **Step 1: 写入失败的 CI 交付契约**

在 `test_github_ci_runs_all_delivery_gates_on_push_and_pull_request` 中增加：

```python
windows_job = jobs["windows-powershell"]
assert windows_job["runs-on"] == "windows-latest"
windows_commands = [
    step.get("run", "")
    for step in windows_job["steps"]
    if isinstance(step, dict)
]
assert (
    ".venv\\Scripts\\python.exe -m pytest tests/demo/test_mechanism_demo.py -q"
    in windows_commands
)
```

- [ ] **Step 2: 运行 RED 并确认失败原因**

Run: `.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py::test_github_ci_runs_all_delivery_gates_on_push_and_pull_request -q`

Expected: FAIL，原因是 `jobs` 中不存在 `windows-powershell`，不是语法或依赖错误。

- [ ] **Step 3: 最小实现平台分工**

在 `tests/demo/test_mechanism_demo.py` 导入 pytest，并给三个 PowerShell 启动脚本测试逐一增加：

```python
@pytest.mark.skipif(os.name != "nt", reason="仅 Windows PowerShell 启动器语义")
```

在 `.github/workflows/ci.yml` 增加：

```yaml
  windows-powershell:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: 安装 Python 测试依赖
        run: |
          python -m venv .venv
          .venv\Scripts\python.exe -m pip install --upgrade pip
          .venv\Scripts\python.exe -m pip install -e ".[dev]"
      - name: 验证 Windows PowerShell 入口与机制演示
        run: .venv\Scripts\python.exe -m pytest tests/demo/test_mechanism_demo.py -q
```

- [ ] **Step 4: 运行 GREEN 与静态检查**

Run:

```text
.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py::test_github_ci_runs_all_delivery_gates_on_push_and_pull_request tests/demo/test_mechanism_demo.py -q
.venv\Scripts\python.exe -m ruff check tests/distribution/test_delivery_files.py tests/demo/test_mechanism_demo.py
.venv\Scripts\python.exe -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))"
```

Expected: 全部退出 0；在 Windows 本机三个 PowerShell 测试实际执行而非 skip。

- [ ] **Step 5: 运行完整门禁和双重审查**

Run:

```text
mingw32-make test
mingw32-make demo
.venv\Scripts\python.exe scripts/secret_scan.py
git diff --check
```

Expected: 完整测试、三机制演示、秘密扫描和差异检查退出 0。随后分别进行规约符合性与代码质量审查，Critical/Important 清零。

- [ ] **Step 6: 更新记录并提交**

在 `PLAN.md` 和 `AGENT_LOG.md` 记录 RED、GREEN、完整验证、审查结论及提交哈希，然后执行：

```text
git add .github/workflows/ci.yml tests/demo/test_mechanism_demo.py tests/distribution/test_delivery_files.py PLAN.md AGENT_LOG.md docs/superpowers/plans/2026-08-10-ci-powershell-tests.md
git commit -m "fix: 修复 CI PowerShell 平台测试"
```
