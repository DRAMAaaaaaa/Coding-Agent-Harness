# 最小可用 Coding Agent Harness 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Scripted Mock LLM 打通“接入 Git 项目—审批计划—受治理修改—失败反馈—再次修正—测试通过—WebUI 交付 diff”的完整 Harness 流程。

**Architecture:** 复用 Task 1—4 的领域模型、事件存储、Provider 和治理能力，先把 Task 5 收敛为安全项目入口，再按纵向切片实现最小工具集、反馈/Agent 循环、FastAPI/WebUI 和交付门禁。首版不执行外部 checkout filter、不安装依赖、不联网调用真实 LLM，也不提供 Git push/merge/release。

**Tech Stack:** Python 3.11、Pydantic 2、SQLite/aiosqlite、FastAPI、React 19、TypeScript 6、Vite 8、Vitest、Playwright、Docker、GitHub Actions、GitLab CI。

## Global Constraints

- Python 固定 `>=3.11,<3.12`；使用仓库 `.venv` 和现有锁文件，不新增依赖，除非用户另行批准。
- Harness 循环、动作解析、工具调度、治理、反馈和停止逻辑必须由本仓库实现，不使用高层 Agent Runner。
- 所有核心测试使用 Scripted Mock，不访问网络、真实 LLM 或真实凭据。
- 删除文件必须审批；安装依赖、工具网络、Git push/merge/release 和任意 Shell 在 MVP 固定拒绝。
- 普通 Agent 工具永远不能访问项目 worktree 外路径或 Harness `state_root`。
- 每项行为遵循 RED—GREEN—REFACTOR；每个 Task 完成后先规约审查，再质量审查，再取得主控新鲜验证。
- 文档和提交说明尽量使用中文；每个 Task 独立提交，MVP-2 以后的每个 Task 都从最新 `p1` 创建新的隔离 worktree，评审通过后本地合并。
- 2 个 Critical 和 2 个 Important 全部是 MVP-1 合并阻塞项，不得登记为延期。
- 合法延期只包括设计文档第 3 节列出的非首版能力，并写入 `DEFERRED_WORK.md`。

---

## MVP-0：范围和问题治理

### Task 1：登记延期并冻结新的执行顺序

**Files:**
- Modify: `DEFERRED_WORK.md`
- Modify: `PLAN.md`
- Modify: `AGENT_LOG.md`
- Modify: `MVP_ISSUES.md`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-07-16-minimal-viable-harness-design.md`
- Produces: MVP-1—MVP-4 唯一执行顺序与非首版能力台账

- [ ] **Step 1: 写入明确延期记录**

在 `DEFERRED_WORK.md` 增加以下记录，每项写明用户影响、MVP 替代和恢复条件：

```text
DW-MVP-001：长期记忆与跨任务经验，P2；替代为当前任务事件上下文。
DW-MVP-002：多任务并发与多 Agent 执行，P2；替代为每次一个写任务。
DW-MVP-003：真实 DeepSeek/Qwen 联网验收，P1；保留 Provider 接口，以 Mock 验收。
DW-MVP-004：依赖安装、工具网络、Git push/merge/release，P1；首版固定 DENY。
DW-MVP-005：Git LFS/加密 filter 正式执行，P1；首版发现活动 filter 后拒绝。
DW-MVP-006：高级凭据界面和高级 WebUI，P2；保留最小本地会话与状态页面。
```

- [ ] **Step 2: 同步根计划**

在 `PLAN.md` 的 Task 依赖表前增加：

```markdown
> 当前交付顺序由 `docs/superpowers/plans/2026-07-16-minimal-viable-harness.md`
> 的 MVP-1—MVP-4 取代原 Task 5—14 横向顺序；原条目保留为完整产品路线。
```

- [ ] **Step 3: 验证文档**

Run:

```powershell
$tokens = @('T' + 'BD', 'T' + 'ODO')
$matches = Select-String -Path DEFERRED_WORK.md,MVP_ISSUES.md,docs/superpowers/plans/2026-07-16-minimal-viable-harness.md -Pattern $tokens
if ($matches) { $matches; exit 1 }
git diff --check
```

Expected: 无占位符，`git diff --check` 退出 0。

- [ ] **Step 4: 提交**

```powershell
git add DEFERRED_WORK.md PLAN.md AGENT_LOG.md MVP_ISSUES.md
git commit -m "docs: 冻结最小可用产品执行顺序"
```

---

## MVP-1：安全项目接入与 worktree

### Task 2：统一路径身份并在文件访问前拒绝逃逸

**Files:**
- Create: `src/coding_agent_harness/governance/path_identity.py`
- Modify: `src/coding_agent_harness/governance/paths.py`
- Modify: `src/coding_agent_harness/storage/database.py`
- Modify: `src/coding_agent_harness/workspace/scanner.py`
- Modify: `src/coding_agent_harness/workspace/worktrees.py`
- Create: `tests/governance/test_path_identity.py`
- Modify: `tests/governance/test_paths.py`
- Modify: `tests/governance/test_approvals.py`
- Modify: `tests/workspace/test_scanner.py`
- Modify: `tests/workspace/test_worktrees.py`

**Interfaces:**
- Produces: `collapse_windows_extended_path(path: str) -> str`
- Produces: `path_key(path: Path) -> tuple[str, ...]`
- Produces: `same_path(left: Path, right: Path) -> bool`
- Produces: `is_within(candidate: Path, root: Path) -> bool`
- Produces: `paths_overlap(left: Path, right: Path) -> bool`
- Consumes: existing `PathGuard.resolve(candidate) -> Path`

- [ ] **Step 1: 写 Windows 别名和零访问 RED 测试**

```python
def test_extended_drive_alias_overlap_is_rejected_before_mkdir(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    ordinary = workspace.git_root.resolve()
    extended = Path("\\\\?\\" + str(ordinary))
    mkdir_calls: list[Path] = []
    monkeypatch.setattr(Path, "mkdir", lambda self, **kw: mkdir_calls.append(self))
    with pytest.raises(WorktreeStateError, match="必须位于项目外"):
        WorktreeManager(workspace, extended)
    assert mkdir_calls == []


@pytest.mark.parametrize(
    "tracked",
    [r"..\outside.py", r"C:outside.py", r"\\server\share\outside.py"],
)
def test_rejects_windows_escape_before_metadata_probe(
    tmp_path: Path, tracked: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes = 0
    def fail_probe(self: Path) -> bool:
        nonlocal probes
        probes += 1
        raise AssertionError("越界路径不得被探测")
    monkeypatch.setattr(Path, "exists", fail_probe)
    with pytest.raises(RepositoryScanError, match="路径越界"):
        WorkspaceScanner(RecordingGitRunner([tracked])).scan(tmp_path)
    assert probes == 0
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/governance/test_path_identity.py tests/workspace/test_scanner.py tests/workspace/test_worktrees.py -q
```

Expected: 扩展路径被旧比较放行，Windows 反斜杠/drive/UNC 候选在 containment 前触发探测或被接受。

- [ ] **Step 3: 实现共享路径身份**

```python
class UnsafePathNamespaceError(ValueError):
    pass

def collapse_windows_extended_path(path: str) -> str:
    extended_unc = "\\\\?\\UNC\\"
    if path[: len(extended_unc)].casefold() == extended_unc.casefold():
        return "\\\\" + path[len(extended_unc) :]
    extended = "\\\\?\\"
    if path.startswith(extended):
        tail = path[len(extended) :]
        if len(tail) >= 3 and tail[0].isalpha() and tail[1] == ":" and tail[2] in "\\/":
            return tail
        raise UnsafePathNamespaceError("不支持的 Windows 设备命名空间")
    if path.startswith("\\\\.\\"):
        raise UnsafePathNamespaceError("不支持的 Windows 设备命名空间")
    return path

def path_key(path: Path) -> tuple[str, ...]:
    resolved = str(path.resolve(strict=False))
    normalized = collapse_windows_extended_path(resolved) if os.name == "nt" else resolved
    return tuple(Path(os.path.normcase(os.path.normpath(normalized))).parts)

def is_within(candidate: Path, root: Path) -> bool:
    candidate_parts, root_parts = path_key(candidate), path_key(root)
    return candidate_parts[: len(root_parts)] == root_parts

def same_path(left: Path, right: Path) -> bool:
    if path_key(left) == path_key(right):
        return True
    try:
        return left.samefile(right)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise UnsafePathNamespaceError("无法确认路径身份") from error

def paths_overlap(left: Path, right: Path) -> bool:
    return is_within(left, right) or is_within(right, left)
```

只折叠 `\\?\X:\...` 和 `\\?\UNC\server\share\...`；`\\.\`、GLOBALROOT、Volume GUID 和畸形扩展路径固定拒绝。既有路径用 `samefile` 补证，权限/网络/重解析错误 fail closed。

- [ ] **Step 4: 让所有消费者使用同一关系操作**

- `PathGuard.resolve` 使用 `is_within`。
- `Database` 删除私有扩展路径折叠，改用共享 `path_key`。
- `WorktreeManager` 在首次 `mkdir` 前和每次 `_resolve_state_path` 使用 `paths_overlap/is_within`。
- scanner 无论候选是否存在，都先完成宿主语义解析和 containment，再执行 `exists/stat`。

- [ ] **Step 5: 转绿并回归 Task 4**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/governance tests/storage tests/workspace -q
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m mypy src
```

- [ ] **Step 6: 更新问题台账并提交**

把 `MVP-ISSUE-001/005` 标记为“实现完成，待复审”，记录 RED/GREEN。

```powershell
git add src tests MVP_ISSUES.md PLAN.md AGENT_LOG.md
git commit -m "fix: 统一路径身份并阻断扫描逃逸"
```

### Task 3：建立不隐式执行仓库代码的 Git 边界

**Files:**
- Create: `src/coding_agent_harness/workspace/git.py`
- Modify: `src/coding_agent_harness/workspace/processes.py`
- Modify: `src/coding_agent_harness/workspace/scanner.py`
- Modify: `src/coding_agent_harness/workspace/worktrees.py`
- Create: `tests/workspace/test_git_safety.py`
- Modify: `tests/workspace/test_processes.py`
- Modify: `tests/workspace/test_scanner.py`
- Modify: `tests/workspace/test_worktrees.py`

**Interfaces:**
- Produces: `ProcessRequest(argv, cwd, env, stdin)`
- Produces: `ProcessRunner.run(request) -> CommandResult`
- Produces: `SafeGit.run(root, args, stdin=b"") -> CommandResult`
- Produces: `SafeGit.assert_filter_free(root, commit, tracked_paths) -> None`
- Produces: `UnsupportedGitFilterError`

- [ ] **Step 1: 写真实 sentinel RED 测试**

```python
def test_scanner_does_not_execute_fsmonitor_or_gpg(real_git_repo: Path) -> None:
    fsmonitor = install_sentinel(real_git_repo, "fsmonitor")
    gpg = install_sentinel(real_git_repo, "gpg")
    git_config(real_git_repo, "core.fsmonitor", fsmonitor.command)
    git_config(real_git_repo, "log.showSignature", "true")
    git_config(real_git_repo, "gpg.program", gpg.command)
    WorkspaceScanner().scan(real_git_repo)
    assert not fsmonitor.marker.exists()
    assert not gpg.marker.exists()


def test_worktree_rejects_filter_before_hook_or_filter_runs(manager_factory) -> None:
    manager, sentinels = manager_factory(with_hook=True, with_filter=True)
    with pytest.raises(UnsupportedGitFilterError):
        manager.create(uuid4(), "HEAD")
    assert all(not item.marker.exists() for item in sentinels)
```

同时断言 argv 包含 `core.fsmonitor=` 且不含 `core.fsmonitor=false`，log 包含 `--no-show-signature`，Git 可执行文件为绝对路径，remove 前重做 filter gate。

- [ ] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/workspace/test_git_safety.py -v`

Expected: 当前 scanner 执行 fsmonitor/GPG，普通 worktree add/remove 执行 hooks 或 filter。

- [ ] **Step 3: 扩展低层进程请求但保留资源上限**

```python
@dataclass(frozen=True)
class ProcessRequest:
    argv: tuple[str, ...]
    cwd: Path | None = None
    env: Mapping[str, str] | None = None
    stdin: bytes = b""

class ProcessRunner(Protocol):
    def run(self, request: ProcessRequest) -> CommandResult:
        raise NotImplementedError
```

`Popen` 继续使用 `shell=False`、双 PIPE、每流 `limit+1`、总超时和 kill/drain/wait/join/close。stdin 使用有界 bytes，写入异常属于启动后不确定状态。

- [ ] **Step 4: 实现 SafeGit 固定环境**

SafeGit 固定绝对 Git 可执行文件，在 `state_root/git-safety` 创建并验证空 hooks 目录、空 global config 和空 attributes 文件。每次从最小宿主白名单构造环境，固定：

```python
SAFE_GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_ALLOW_PROTOCOL": ":",
    "GIT_PROTOCOL_FROM_USER": "0",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_PAGER": "cat",
}

SAFE_CONFIG = ("core.fsmonitor=", "gc.auto=0", "maintenance.auto=false")
```

清除继承的 `GIT_CONFIG_*`、GIT_DIR/WORK_TREE/INDEX_FILE、对象/alternates、diff、SSH、askpass 和 exec-path；只有 SafeGit 临时 index 可以显式注入 `GIT_INDEX_FILE`。

- [ ] **Step 5: 安全扫描与 materialize**

- scanner 使用 `ls-files -z`、`status --porcelain=v1 -z` 和 `log --no-show-signature -n 20`。
- 创建前用宿主临时 index 执行 `read-tree --reset <full_oid>`；把 `ls-tree -r --name-only -z` 输出传给 `check-attr --cached -z --stdin filter`。
- filter 值不是 `unspecified/unset` 时抛 `UnsupportedGitFilterError`，不得创建 marker、branch 或 target。
- filter-free 时执行 `worktree add --no-checkout -b <branch> <target> <full_oid>`，再在目标执行 `read-tree --reset <full_oid>` 和 `checkout-index --all`。
- release 前对当前 index/工作树重做 filter gate，再运行安全 status/remove；发现 filter 时保留 marker。

- [ ] **Step 6: 转绿与回归**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/workspace/test_git_safety.py -v
.venv\Scripts\python.exe -m pytest tests/workspace -q --durations=10
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m mypy src
```

- [ ] **Step 7: 更新台账并提交**

```powershell
git add src/coding_agent_harness/workspace tests/workspace MVP_ISSUES.md PLAN.md AGENT_LOG.md
git commit -m "fix: 隔离 Git 隐式外部执行面"
```

### Task 4：绑定全部验证配置并修复离线 fixture

**Files:**
- Modify: `src/coding_agent_harness/workspace/detector.py`
- Modify: `src/coding_agent_harness/workspace/models.py`
- Modify: `tests/workspace/test_detector.py`
- Modify: `tests/fixtures/python_project/pyproject.toml`
- Move: `tests/fixtures/python_project/src/sample.py` to `tests/fixtures/python_project/src/sample/__init__.py`
- Modify: `tests/fixtures/node_project/package.json`
- Modify: `tests/fixtures/node_project/tests/math.test.ts`

**Interfaces:**
- Produces: 只要存在验证命令，`ProjectProfile.requires_trust=True` 且 `trust_fingerprint` 为 64 位摘要
- Produces: `verification-trust/v1` 规范化 manifest

- [ ] **Step 1: 写信任变化和真实命令 RED 测试**

```python
def test_package_script_change_invalidates_fingerprint(tmp_path: Path) -> None:
    package = tmp_path / "package.json"
    package.write_text('{"scripts":{"test":"node --test"}}', encoding="utf-8")
    first = ProjectDetector().detect(tmp_path)
    package.write_text('{"scripts":{"test":"node --test --watch=false"}}', encoding="utf-8")
    second = ProjectDetector().detect(tmp_path)
    assert first.requires_trust and second.requires_trust
    assert first.commands.test == second.commands.test
    assert first.trust_fingerprint != second.trust_fingerprint


def test_python_fixture_detected_test_really_runs(tmp_path: Path) -> None:
    root = copy_fixture("python_project", tmp_path)
    command = ProjectDetector().detect(root).commands.test
    result = subprocess.run(command, cwd=root, env=clean_test_env(), capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
```

Node fixture 使用 Node 24 内置 `node:test`；Windows 断言 npm 启动器为 `npm.cmd`，POSIX 为 `npm`。

- [ ] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/workspace/test_detector.py -v`

Expected: pyproject/package profile 无指纹；Python fixture 导入失败；Node fixture 缺 vitest。

- [ ] **Step 3: 实现版本化信任 manifest**

```python
manifest = {
    "schema": "verification-trust/v1",
    "sources": {
        ".harness.yml": harness_digest_or_none,
        "package.json": package_digest_or_none,
        "pyproject.toml": pyproject_digest_or_none,
    },
    "effective": {
        "commands": commands.model_dump(mode="json"),
        "env_allowlist": list(env_allowlist),
        "timeout_seconds": timeout,
    },
}
encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
fingerprint = hashlib.sha256(
    b"coding-agent-harness\0verification-trust\0v1\0" + encoded
).hexdigest()
```

没有任何验证命令时才允许 `requires_trust=False/fingerprint=None`；模型校验器拒绝不一致组合。

- [ ] **Step 4: 让 fixture 离线可运行**

- Python 使用 `src/sample/__init__.py`，pytest 配置 `pythonpath = ["src"]`。
- Node test 使用 `node --test tests/math.test.ts`，测试改用 `node:test` 与 `node:assert/strict`；lint/typecheck/build 只用 Node 24 内置 `--check`。
- 真实测试复制 fixture 到 `tmp_path` 并清除 `PYTHONPATH/NODE_PATH`，不得借用祖先依赖。

- [ ] **Step 5: 全量门禁与双重评审**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/workspace -q --durations=10
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m mypy src
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: `MVP-ISSUE-001`—`007` 均有关闭证据；10,000 文件 CI 测试不硬断言 wall clock，本机单独基准小于 5 秒。

- [ ] **Step 6: 提交并合并 MVP-1**

规约审查全部问题台账，再质量审查完整 `6b2f21e..HEAD`。无 Critical/Important 后：

```powershell
git add src tests MVP_ISSUES.md PLAN.md AGENT_LOG.md
git commit -m "feat: 完成安全项目接入与任务工作树"
```

使用 `verification-before-completion` 后把 `codex/workspaces` 本地合并回 `p1`，不 push。

---

## MVP-2：最小工具、反馈和 Agent 主循环

### Task 5：实现受治理的最小工具集

**Files:**
- Create: `src/coding_agent_harness/tools/models.py`
- Create: `src/coding_agent_harness/tools/registry.py`
- Create: `src/coding_agent_harness/tools/files.py`
- Create: `src/coding_agent_harness/tools/search.py`
- Create: `src/coding_agent_harness/tools/verification.py`
- Create: `src/coding_agent_harness/tools/git.py`
- Create: `tests/tools/test_registry.py`
- Create: `tests/tools/test_files.py`
- Create: `tests/tools/test_search.py`
- Create: `tests/tools/test_verification.py`
- Create: `tests/tools/test_git.py`
- Modify: `src/coding_agent_harness/governance/policy.py`
- Modify: `tests/governance/test_policy.py`

**Interfaces:**
- Produces: `ToolResult(ok, code, output, changed_paths, retryable)` 与 `ToolContext`
- Produces: `ToolRegistry.execute(action: ToolAction, context: ToolContext) -> ToolResult`
- Consumes: `PolicyEngine`、`PathGuard`、`SafeGit`、当前 `ProjectProfile`

- [ ] **Step 1: 写注册表、原子替换和审批 RED 测试**

```python
async def test_apply_patch_is_compare_and_swap(registry, worktree: Path) -> None:
    target = worktree / "src/app.py"
    before = sha256(target.read_bytes()).hexdigest()
    result = await registry.execute(tool(
        "apply_patch",
        {"path": "src/app.py", "expected_sha256": before, "content": "VALUE = 2\n"},
    ))
    assert result.ok
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"

async def test_delete_waits_for_approval_and_shell_is_absent(registry) -> None:
    delete = await registry.execute(tool("delete_file", {"path": "x.py"}))
    assert delete.code == "APPROVAL_REQUIRED"
    shell = await registry.execute(tool("shell", {"argv": ["curl", "https://example.test"]}))
    assert shell.code == "UNSUPPORTED_TOOL"
```

- [ ] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/tools -q`

Expected: tools 包不存在。

- [ ] **Step 3: 实现严格工具协议**

`apply_patch` 使用全文件 compare-and-swap：同一 Workspace 最多一个 Harness 写任务，同目录 `O_EXCL` 协作锁线性化所有遵守协议的 Harness 实例。create 时摘要为 null 且以原子 no-replace 创建；replace 时摘要精确匹配，并在持锁、原子 replace 前复验。写入同目录独占临时文件、flush、fsync、原子 replace；复验前完成的用户编辑返回 `STALE_CONTENT`。普通跨平台文件系统没有按 SHA-256 条件原子 replace，忽略锁的同 UID 外部进程若恰在最终复验与 replace 之间改写属于 SPEC 9.2 已批准的外部竞争边界；已检测到不一致 fail closed，现场不确定时人工接管。`delete_file` 只接受单个普通文件和摘要，消费审批后删除；目录、symlink 和缺失摘要拒绝。

`PolicyEngine` 同步把 `apply_patch` 解析为结构化 `path/expected_sha256/content`，把 `delete_file` 解析为 `path/expected_sha256`；所有路径先经过 `PathGuard`，未知字段由 Pydantic 严格拒绝。

`search` 只扫描 RepositoryMap 跟踪文本文件并限制文件数、单文件 bytes、匹配数和总输出。`run_verification` 重新 detect 并比较批准指纹，只执行精确 argv；变化返回 `STALE_CONFIG` 且 runner 零调用。

- [ ] **Step 4: Git 工具只暴露 status/diff**

`git_status` 使用安全 porcelain；`git_diff` 固定 `--no-ext-diff --no-textconv --binary --`。checkpoint、push、merge 和任意 Git argv 不注册。

- [ ] **Step 5: 转绿并提交**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/tools tests/governance -q
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m mypy src
```

```powershell
git add src/coding_agent_harness/tools src/coding_agent_harness/governance tests/tools tests/governance PLAN.md AGENT_LOG.md
git commit -m "feat: 实现受治理的最小编码工具集"
```

### Task 6：实现确定性反馈和 Mock Agent 主循环

**Files:**
- Create: `src/coding_agent_harness/feedback/models.py`
- Create: `src/coding_agent_harness/feedback/classifier.py`
- Create: `src/coding_agent_harness/feedback/fingerprint.py`
- Create: `src/coding_agent_harness/feedback/engine.py`
- Create: `src/coding_agent_harness/agent/orchestrator.py`
- Modify: `src/coding_agent_harness/agent/state_machine.py`
- Create: `tests/feedback/test_engine.py`
- Create: `tests/agent/test_orchestrator.py`
- Modify: `tests/agent/test_state_machine.py`

**Interfaces:**
- Produces: `VerificationRun`、`FeedbackDecision`、`FeedbackEngine.evaluate(history, run)`
- Produces: `AgentOrchestrator.propose_plan`、`approve_plan`、`run_until_wait`、`approve_final`
- Consumes: `LLMProvider`、`ActionParser`、`ToolRegistry`、`EventStore`、`TaskRepository`

- [ ] **Step 1: 写 3/8/2 与完整 Mock RED 测试**

```python
async def test_feedback_changes_next_action_after_injected_failure(harness) -> None:
    task = await harness.create_demo_task("修复 add 函数")
    await harness.approve_plan(task.id)
    await harness.run_until_wait(task.id)
    assert "AssertionError" in json.dumps(
        harness.provider.requests[-1].messages, ensure_ascii=False
    )
    assert harness.actions[-2].idempotency_key != harness.actions[-1].idempotency_key
    assert (await harness.task(task.id)).state is TaskState.WAITING_FINAL_REVIEW

def test_two_unchanged_failure_rounds_wait_for_user(engine) -> None:
    first = engine.evaluate([], failed_run("same", count=2))
    second = engine.evaluate([first.observation], failed_run("same", count=2))
    assert second.next_state is TaskState.WAITING_USER
    assert second.reason_code == "NO_PROGRESS"
```

- [ ] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/feedback tests/agent/test_orchestrator.py -q`

Expected: feedback/orchestrator 不存在。

- [ ] **Step 3: 实现反馈和预算**

分类固定为 `TEST/LINT/TYPECHECK/BUILD/TIMEOUT/OUTPUT_LIMIT/POLICY/TOOL/UNKNOWN`。指纹移除临时绝对路径、耗时和行列噪声，保留测试节点、异常类型和规范化消息。相同指纹最多 3 次、总验证循环最多 8 次、连续 2 轮失败数和类别均无改善则 `WAITING_USER`。

- [ ] **Step 4: 实现事件驱动循环**

每次只做一个可落盘决定：计划、批准、LLM、动作解析、治理、started 事件、执行、finished 事件、验证、反馈或最终审查。只读工具后回 `DECIDING`，修改工具后进 `VERIFYING`。started 无 finished 的恢复结果为 `UNCERTAIN_SIDE_EFFECT`，不得自动重放。

Mock 脚本固定包含计划、读文件、错误 patch、失败反馈后的正确 patch、验证通过、完成摘要和一个被拦截的危险动作。

- [ ] **Step 5: 转绿并提交**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/feedback tests/agent tests/providers tests/storage -q
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m mypy src
```

```powershell
git add src/coding_agent_harness/feedback src/coding_agent_harness/agent tests/feedback tests/agent PLAN.md AGENT_LOG.md
git commit -m "feat: 打通确定性反馈和 Mock Agent 主循环"
```

---

## MVP-3：FastAPI 与最小 WebUI

### Task 7：持久化 Workspace 并提供 REST/SSE

**Files:**
- Create: `src/coding_agent_harness/storage/migrations/003_mvp_workspaces.sql`
- Create: `src/coding_agent_harness/storage/workspaces.py`
- Create: `src/coding_agent_harness/api/app.py`
- Create: `src/coding_agent_harness/api/dependencies.py`
- Create: `src/coding_agent_harness/api/session.py`
- Create: `src/coding_agent_harness/api/routes.py`
- Create: `src/coding_agent_harness/api/sse.py`
- Modify: `src/coding_agent_harness/config.py`
- Create: `tests/storage/test_workspace_repository.py`
- Create: `tests/api/test_projects.py`
- Create: `tests/api/test_tasks.py`
- Create: `tests/api/test_sse.py`
- Modify: `src/coding_agent_harness/storage/database.py`

**Interfaces:**
- Produces: `WorkspaceRepository.create/get/list`
- Produces: `POST /api/projects`、`POST /api/projects/{id}/trust`、`POST /api/tasks`、计划/运行/最终批准端点
- Produces: `GET /api/tasks/{id}/events?after=<sequence>` SSE

- [ ] **Step 1: 写迁移、会话与 API RED 测试**

```python
async def test_task_api_runs_to_plan_gate(client, python_repo: Path) -> None:
    project = await client.post("/api/projects", json={"path": str(python_repo)})
    trusted = await client.post(
        f"/api/projects/{project.json()['id']}/trust",
        json={"fingerprint": project.json()["trust_fingerprint"]},
        headers=session_headers(client),
    )
    task = await client.post(
        "/api/tasks",
        json={"workspace_id": trusted.json()["id"], "requirement": "修复 add"},
        headers=session_headers(client),
    )
    assert task.json()["state"] == "WAITING_PLAN_APPROVAL"
```

同时覆盖 Origin/header 缺失 403、SSE after 续传、重启恢复和迁移 0→1→2→3、v2→v3、v3 幂等。

- [ ] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/api tests/storage/test_workspace_repository.py -q`

Expected: API/repository/003 不存在。

- [ ] **Step 3: 实现最小持久化与会话**

003 为 workspace 增加 `root/git_root/default_branch/profile_json/trust_fingerprint/created_at`，并补齐计划/产物所需非空字段；不增加 memory、credentials 或 host transfer。服务启动生成随机会话 token，通过同源首页注入；mutation 同时校验 Origin 和 `X-Harness-Session`。错误体固定 `{code,message,details,event_id}` 且先脱敏。

`HarnessSettings` 增加宿主私有 `state_root` 与 SQLite 路径；默认位于用户应用数据目录而不是被接入项目内。API 请求不得覆盖这两个宿主配置。

- [ ] **Step 4: 实现 REST/SSE**

run 端点执行到下一等待/终态；SSE 按事件序号发送，重连从 after 继续。API 不接受任意命令、任意 state_root 或外部文件路径。

- [ ] **Step 5: 转绿、分发检查和提交**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/api tests/storage -q
.venv\Scripts\python.exe -m build --wheel --sdist --no-isolation
tar -tf dist\coding_agent_harness-0.1.0-py3-none-any.whl
```

Expected: wheel/sdist 中 001/002/003 各一份。

```powershell
git add src/coding_agent_harness/api src/coding_agent_harness/storage tests/api tests/storage PLAN.md AGENT_LOG.md
git commit -m "feat: 提供最小 Harness REST 与事件流"
```

### Task 8：实现单页最小 WebUI

**Files:**
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/api.ts`
- Create: `web/src/types.ts`
- Create: `web/src/styles.css`
- Create: `web/src/App.test.tsx`
- Create: `web/src/setupTests.ts`
- Modify: `src/coding_agent_harness/api/app.py`
- Modify: `web/package.json`
- Modify: `web/vite.config.ts`
- Modify: `web/tsconfig.json`

**Interfaces:**
- Consumes: Task 7 REST/SSE
- Produces: 项目接入、需求输入、计划审批、事件时间线、危险动作审批、测试/diff 六个区域

- [ ] **Step 1: 写用户路径 RED 测试**

```tsx
it("从项目接入运行到最终 diff", async () => {
  render(<App api={scriptedApi()} />);
  await user.type(screen.getByLabelText("项目路径"), "C:\\demo\\repo");
  await user.click(screen.getByRole("button", { name: "接入项目" }));
  await user.type(screen.getByLabelText("编码需求"), "修复 add 函数");
  await user.click(screen.getByRole("button", { name: "生成计划" }));
  await user.click(await screen.findByRole("button", { name: "批准计划" }));
  expect(await screen.findByText("测试已通过")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "最终差异" })).toBeVisible();
});
```

- [ ] **Step 2: 运行 RED**

Run: `npm.cmd --prefix web run test -- --run`

Expected: App 不存在。

- [ ] **Step 3: 实现单页状态 UI**

只使用现有 React/Vite 依赖。按钮由任务状态决定；SSE 断线显示重连；审批展示原因与精确范围；状态同时使用文本/图标，不能只靠颜色。不得显示或接收 API Key。

- [ ] **Step 4: 转绿并提交**

Run:

```powershell
npm.cmd --prefix web run test -- --run
npm.cmd --prefix web run lint
npm.cmd --prefix web run typecheck
npm.cmd --prefix web run build
```

```powershell
git add web PLAN.md AGENT_LOG.md
git commit -m "feat: 实现最小 Harness WebUI"
```

---

## MVP-4：演示、E2E 和交付

### Task 9：三机制演示、浏览器 E2E 和一键测试

**Files:**
- Create: `examples/python_demo/`
- Create: `scripts/mechanism_demo.py`
- Create: `scripts/serve_demo.py`
- Create: `web/e2e/harness.spec.ts`
- Create: `web/playwright.config.ts`
- Modify: `Makefile`
- Modify: `scripts/test.ps1`
- Modify: `web/package.json`
- Create: `tests/demo/test_mechanism_demo.py`

**Interfaces:**
- Produces: `make test-unit`、`make test-e2e`、`make test`、`make demo`
- Consumes: Mock 编排、API 和 WebUI

- [ ] **Step 1: 写 demo/E2E RED 测试**

```python
def test_demo_reports_all_three_mechanisms() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/mechanism_demo.py"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert result.stdout.splitlines()[-3:] == [
        "PASS governance_guard",
        "PASS feedback_changed_action",
        "PASS deterministic_stop",
    ]
```

Playwright 使用临时 fixture、`git init` 和固定 Mock，跑通接入、信任、计划批准、失败反馈和最终 diff；结束后确认主分支未变化且临时进程/worktree 回收。

- [ ] **Step 2: 运行 RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/demo -q
npm.cmd --prefix web exec -- playwright test
```

- [ ] **Step 3: 实现四个入口**

- test-unit：Python + Vitest。
- test-e2e：随机 localhost 端口 + Playwright。
- test：Ruff、mypy、Python、ESLint、TypeScript、Vite build、E2E。
- demo：固定三行 PASS。

所有临时仓库使用固定 Git identity，不访问外网或真实用户仓库。

- [ ] **Step 4: 连续两次验证并提交**

Run:

```powershell
make demo
make demo
make test-unit
make test-e2e
make test
```

Expected: 两次 demo 输出一致，全部退出 0。

```powershell
git add examples scripts web/e2e web/playwright.config.ts Makefile web/package.json tests/demo PLAN.md AGENT_LOG.md
git commit -m "test: 完成离线机制演示和端到端验收"
```

### Task 10：Docker、双 CI 与最终交付文档

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `compose.yaml`
- Create: `.github/workflows/ci.yml`
- Create: `.gitlab-ci.yml`
- Create: `docs/SECURITY.md`
- Create: `docs/DEPLOYMENT.md`
- Create: `docs/DEMO.md`
- Modify: `README.md`
- Modify: `.env.example`
- Create: `tests/distribution/test_delivery_files.py`

**Interfaces:**
- Produces: 本地源码运行、Docker WebUI、GitHub push/PR CI、GitLab `unit-test`

- [ ] **Step 1: 写交付 RED 测试**

```python
def test_delivery_contract(repo_root: Path) -> None:
    github = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    gitlab = (repo_root / ".gitlab-ci.yml").read_text(encoding="utf-8")
    dockerfile = (repo_root / "Dockerfile").read_text(encoding="utf-8")
    assert "make test" in github and "docker build" in github
    assert "unit-test:" in gitlab and "make test-unit" in gitlab
    assert "USER harness" in dockerfile
```

- [ ] **Step 2: 运行 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/distribution/test_delivery_files.py -v`

Expected: Docker/CI 文件不存在。

- [ ] **Step 3: 实现容器和 CI**

Docker 多阶段构建 WebUI 和 wheel，最终使用非 root `harness` 用户，只暴露应用端口和显式挂载项目/state。GitHub 每次 push/PR 执行 `make test`、秘密模式扫描和 `docker build`；GitLab 精确 job `unit-test` 执行 `make test-unit`。CI 不注入真实 LLM Key。

- [ ] **Step 4: 完成交付文档**

README 包含项目简介、安装、运行、Mock 演示、Python/Node、安全边界、已知限制、Docker 和测试命令。`SECURITY.md` 明确 filter 拒绝、同 UID 边界、验证命令信任和不确定副作用；不得把真实 Provider 或公网部署写成已验收。

- [ ] **Step 5: 最终新鲜验证**

Run:

```powershell
make test
make demo
docker build -t coding-agent-harness:mvp .
docker run --rm coding-agent-harness:mvp python scripts/mechanism_demo.py
.venv\Scripts\python.exe -m pip check
git diff --check
```

- [ ] **Step 6: 秘密审计与最终提交**

扫描只输出命中文件名，不回显疑似秘密；测试假凭据使用明确 allowlist。规约和质量最终评审无 Critical/Important 后：

```powershell
git add Dockerfile .dockerignore compose.yaml .github .gitlab-ci.yml docs README.md .env.example tests/distribution PLAN.md AGENT_LOG.md DEFERRED_WORK.md MVP_ISSUES.md
git commit -m "release: 交付最小可用 Coding Agent Harness"
```

使用 `verification-before-completion` 和 `finishing-a-development-branch` 本地合并回 `p1`，不得自动 push。

---

## 计划自审结论

- 完整 Mock Harness、Python/Node、计划审批、治理、反馈、worktree、WebUI、E2E、一键测试、Docker 和双 CI 均有对应 Task。
- 长期记忆、真实 Provider 联网、依赖安装、工具网络、Git 远程操作、高级 UI 和外部 filter 执行均明确延期。
- MVP-1 的路径别名和 Git 隐式执行均有真实 RED 与执行前门禁，不依赖提示词。
- 任务间接口名称唯一，后续 Task 只消费前序明确产出。
- 文档不含未决占位符，不使用不可执行的模糊描述。
