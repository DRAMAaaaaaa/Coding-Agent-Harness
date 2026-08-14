from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
from zipfile import ZipFile

import pytest
import yaml

from scripts import serve_demo


ROOT = Path(__file__).resolve().parents[2]


ARCHIVE_MOVES = {
    "MVP_ISSUES.md": "docs/archive/ledgers/MVP_ISSUES.md",
    "DEFERRED_WORK.md": "docs/archive/ledgers/DEFERRED_WORK.md",
    "docs/superpowers/specs/2026-07-14-coding-agent-harness-design.md": "docs/archive/specs/2026-07-14-coding-agent-harness-design.md",
    "docs/superpowers/specs/2026-07-16-minimal-viable-harness-design.md": "docs/archive/specs/2026-07-16-minimal-viable-harness-design.md",
    "docs/superpowers/specs/2026-07-16-usable-product-priority-design.md": "docs/archive/specs/2026-07-16-usable-product-priority-design.md",
    "docs/superpowers/specs/2026-08-07-co-learning-replay-harness-design.md": "docs/archive/specs/2026-08-07-co-learning-replay-harness-design.md",
    "docs/superpowers/specs/2026-08-10-ci-powershell-tests-design.md": "docs/archive/specs/2026-08-10-ci-powershell-tests-design.md",
    "docs/superpowers/specs/2026-08-10-provider-webui-probe-design.md": "docs/archive/specs/2026-08-10-provider-webui-probe-design.md",
    "docs/superpowers/specs/2026-08-14-co-learning-workbench-ui-design.md": "docs/archive/specs/2026-08-14-co-learning-workbench-ui-design.md",
    "docs/superpowers/specs/2026-08-14-documentation-refresh-design.md": "docs/archive/specs/2026-08-14-documentation-refresh-design.md",
    "docs/superpowers/specs/2026-08-14-public-ip-mock-demo-design.md": "docs/archive/specs/2026-08-14-public-ip-mock-demo-design.md",
    "docs/superpowers/plans/2026-07-16-minimal-viable-harness.md": "docs/archive/plans/2026-07-16-minimal-viable-harness.md",
    "docs/superpowers/plans/2026-08-07-co-learning-replay-mvp.md": "docs/archive/plans/2026-08-07-co-learning-replay-mvp.md",
    "docs/superpowers/plans/2026-08-07-real-providers-and-credentials.md": "docs/archive/plans/2026-08-07-real-providers-and-credentials.md",
    "docs/superpowers/plans/2026-08-10-ci-powershell-tests.md": "docs/archive/plans/2026-08-10-ci-powershell-tests.md",
    "docs/superpowers/plans/2026-08-10-provider-webui-probe.md": "docs/archive/plans/2026-08-10-provider-webui-probe.md",
    "docs/superpowers/plans/2026-08-14-co-learning-workbench-and-docs.md": "docs/archive/plans/2026-08-14-co-learning-workbench-and-docs.md",
    "docs/superpowers/plans/2026-08-14-documentation-refresh.md": "docs/archive/plans/2026-08-14-documentation-refresh.md",
    "docs/superpowers/plans/2026-08-14-public-ip-mock-demo.md": "docs/archive/plans/2026-08-14-public-ip-mock-demo.md",
    ".superpowers/sdd/2026-08-07-co-learning-replay-mvp/task-2-report.md": "docs/archive/reports/2026-08-07-co-learning-replay-mvp/task-2-report.md",
    ".superpowers/sdd/2026-08-07-co-learning-replay-mvp/task-3-report.md": "docs/archive/reports/2026-08-07-co-learning-replay-mvp/task-3-report.md",
    ".superpowers/sdd/2026-08-07-co-learning-replay-mvp/task-5-report.md": "docs/archive/reports/2026-08-07-co-learning-replay-mvp/task-5-report.md",
    ".superpowers/sdd/2026-08-07-real-providers-and-credentials/task-3-implementer-report.md": "docs/archive/reports/2026-08-07-real-providers-and-credentials/task-3-implementer-report.md",
    ".superpowers/sdd/task-6-report.md": "docs/archive/reports/task-6-report.md",
    ".superpowers/sdd/task-7-report.md": "docs/archive/reports/task-7-report.md",
    ".superpowers/sdd/task-10-report.md": "docs/archive/reports/task-10-report.md",
}


def test_historical_docs_are_archived_without_losing_evidence() -> None:
    assert (ROOT / "docs/archive/README.md").is_file()
    for source, target in ARCHIVE_MOVES.items():
        assert not (ROOT / source).is_file(), source
        archived = ROOT / target
        assert archived.is_file(), target
        assert archived.stat().st_size > 0, target


def test_current_markdown_links_resolve_after_archiving() -> None:
    current = (
        "README.md", "SPEC.md", "PLAN.md", "SPEC_PROCESS.md", "AGENT_LOG.md", "AGENTS.md",
        "docs/DEMO.md", "docs/DEPLOYMENT.md", "docs/SECURITY.md", "docs/archive/README.md",
    )
    link = re.compile(r"\[[^]]+\]\((?!https?://|mailto:)([^)#]+)(?:#[^)]+)?\)")
    for relative in current:
        document = ROOT / relative
        for target in link.findall(document.read_text(encoding="utf-8")):
            assert (document.parent / target).resolve().exists(), f"{relative} -> {target}"


def test_current_process_docs_point_to_archive_instead_of_old_locations() -> None:
    current = ("README.md", "SPEC.md", "PLAN.md", "SPEC_PROCESS.md", "AGENT_LOG.md", "AGENTS.md")
    content = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in current)
    assert "docs/superpowers/" not in content
    assert "`MVP_ISSUES.md`" not in content
    assert "`DEFERRED_WORK.md`" not in content


def _yaml(path: str) -> dict[str, object]:
    loaded = yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(loaded, dict)
    return loaded


def _docker_instructions(dockerfile: str) -> list[tuple[str, str]]:
    logical_lines: list[str] = []
    pending = ""
    for raw_line in dockerfile.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        pending = f"{pending}{line}"
        if pending.endswith("\\"):
            pending = f"{pending[:-1]} "
            continue
        instruction, arguments = pending.split(maxsplit=1)
        logical_lines.append((instruction.upper(), arguments))
        pending = ""
    assert not pending
    return logical_lines


def _render_public_ip_compose() -> dict[str, object]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI 不可用，跳过 Compose 合并契约；CI docker-build 作业强制执行")
    environment = {
        "HARNESS_PUBLIC_HOST": "47.76.86.198",
        "HARNESS_PUBLIC_ORIGIN": "http://47.76.86.198",
    }
    rendered = subprocess.run(
        [
            docker,
            "compose",
            "-f",
            "compose.yaml",
            "-f",
            "deploy/compose.public-ip.yaml",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env={**os.environ, **environment},
        capture_output=True,
        check=False,
        text=True,
    )
    assert rendered.returncode == 0, rendered.stderr
    loaded = json.loads(rendered.stdout)
    assert isinstance(loaded, dict)
    return loaded


def test_required_delivery_files_exist() -> None:
    required = (
        "Dockerfile",
        ".dockerignore",
        "compose.yaml",
        ".github/workflows/ci.yml",
        ".gitlab-ci.yml",
        "docs/SECURITY.md",
        "docs/DEPLOYMENT.md",
        "docs/DEMO.md",
    )
    assert [path for path in required if not (ROOT / path).is_file()] == []


def test_wheel_and_sdist_include_migration_004_exactly_once(tmp_path: Path) -> None:
    output = tmp_path / "dist"
    result = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(output)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    expected = "coding_agent_harness/storage/migrations/004_provider_profiles.sql"
    wheel = next(output.glob("*.whl"))
    sdist = next(output.glob("*.tar.gz"))
    with ZipFile(wheel) as archive:
        assert sum(name == expected for name in archive.namelist()) == 1
    with tarfile.open(sdist) as archive:
        assert sum(name.endswith(expected) for name in archive.getnames()) == 1


def test_docker_runtime_is_non_root_and_exposes_only_web_port() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    instructions = _docker_instructions(dockerfile)
    assert sum(kind == "FROM" for kind, _ in instructions) >= 3
    assert [arguments for kind, arguments in instructions if kind == "USER"][-1] == "harness"
    assert [arguments for kind, arguments in instructions if kind == "EXPOSE"] == ["8000"]
    command = json.loads([arguments for kind, arguments in instructions if kind == "CMD"][-1])
    assert command == [
        "python",
        "scripts/serve_demo.py",
        "--ready-file",
        "/state/ready.json",
        "--runtime-root",
        "/state",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--project-source",
        "/workspace/project",
        "--max-seconds",
        "86400",
    ]
    assert not any(
        kind == "COPY" and arguments.startswith("examples/")
        for kind, arguments in instructions
    )


def test_compose_is_local_mock_with_explicit_mounts() -> None:
    compose = _yaml("compose.yaml")
    service = compose["services"]["harness"]  # type: ignore[index]
    assert service["ports"] == ["127.0.0.1:8000:8000"]  # type: ignore[index]
    assert service["environment"]["HARNESS_LLM_PROVIDER"] == "mock"  # type: ignore[index]
    volumes = service["volumes"]  # type: ignore[index]
    assert any(
        "examples/python_demo" in mount
        and mount.endswith(":/workspace/project:ro")
        for mount in volumes
    )
    assert all("/app/examples" not in mount for mount in volumes)
    assert "harness-state:/state" in volumes
    assert service["read_only"] == "true"  # type: ignore[index]
    assert service["cap_drop"] == ["ALL"]  # type: ignore[index]
    assert service["security_opt"] == ["no-new-privileges:true"]  # type: ignore[index]


def test_public_ip_overlay_keeps_mock_local_bind_and_passes_public_targets() -> None:
    base = _yaml("compose.yaml")
    overlay = _yaml("deploy/compose.public-ip.yaml")
    base_service = base["services"]["harness"]  # type: ignore[index]
    overlay_service = overlay["services"]["harness"]  # type: ignore[index]

    assert base_service["ports"] == ["127.0.0.1:8000:8000"]
    assert base_service["environment"]["HARNESS_LLM_PROVIDER"] == "mock"
    assert overlay_service["environment"] == {
        "HARNESS_LLM_PROVIDER": "mock",
        "HARNESS_PUBLIC_HOST": "${HARNESS_PUBLIC_HOST:?必须设置公网 IPv4}",
        "HARNESS_PUBLIC_ORIGIN": "${HARNESS_PUBLIC_ORIGIN:?必须设置 HTTP Origin}",
    }
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "scripts/serve_demo.py" in dockerfile


def test_public_ip_compose_render_preserves_local_mock_delivery_contract() -> None:
    service = _render_public_ip_compose()["services"]["harness"]  # type: ignore[index]
    assert service["ports"] == [
        {
            "mode": "ingress",
            "host_ip": "127.0.0.1",
            "target": 8000,
            "published": "8000",
            "protocol": "tcp",
        }
    ]
    assert service["environment"] == {
        "HARNESS_LLM_PROVIDER": "mock",
        "HARNESS_PUBLIC_HOST": "47.76.86.198",
        "HARNESS_PUBLIC_ORIGIN": "http://47.76.86.198",
    }
    assert any(
        volume["target"] == "/workspace/project" and volume["read_only"]
        for volume in service["volumes"]
    )
    assert service["read_only"]
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]


def test_public_ip_compose_contract_skips_explicitly_without_docker_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _command: None)

    with pytest.raises(pytest.skip.Exception, match="Docker CLI 不可用"):
        _render_public_ip_compose()


def test_public_ip_nginx_is_http_only_sse_proxy_with_default_host_rejection() -> None:
    nginx = (ROOT / "deploy/nginx/coding-agent-harness-ip.conf").read_text(encoding="utf-8")

    for directive in (
        "listen 80 default_server",
        "return 444",
        "listen 80",
        "server_name 47.76.86.198",
        "proxy_pass http://127.0.0.1:8000",
        "proxy_http_version 1.1",
        "proxy_set_header Host $host",
        "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for",
        "proxy_set_header X-Forwarded-Proto $scheme",
        "proxy_buffering off",
        "proxy_read_timeout 300s",
        "client_max_body_size 64k",
        "add_header X-Content-Type-Options nosniff always",
        "add_header X-Frame-Options DENY always",
        "add_header Referrer-Policy no-referrer always",
    ):
        assert directive in nginx
    assert "443" not in nginx
    assert "HSTS" not in nginx
    assert "API Key" not in nginx


def test_public_ip_docs_disable_conflicting_default_nginx_site() -> None:
    for path in ("README.md", "docs/DEPLOYMENT.md"):
        document = (ROOT / path).read_text(encoding="utf-8")
        assert "sudo rm -f /etc/nginx/sites-enabled/default" in document
        assert "sudo ln -sfn /etc/nginx/sites-available/coding-agent-harness" in document


def test_public_ip_docs_describe_explicit_env_down_and_http_risk() -> None:
    deployment = (ROOT / "docs/DEPLOYMENT.md").read_text(encoding="utf-8")
    assert (
        "HARNESS_PUBLIC_HOST=47.76.86.198 HARNESS_PUBLIC_ORIGIN=http://47.76.86.198 "
        "docker compose -f compose.yaml -f deploy/compose.public-ip.yaml down"
    ) in deployment
    for path in ("README.md", "docs/DEPLOYMENT.md"):
        document = (ROOT / path).read_text(encoding="utf-8")
        assert "HTTP 页面、请求及临时会话头均为明文" in document
        assert "无身份认证，任何可访问者都能交互" in document
        assert "仅允许用户在场进行短时 Mock 演示" in document
        assert "长期生产" in document


def test_demo_server_accepts_explicit_container_bind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = [
        "serve_demo.py",
        "--ready-file",
        "/state/ready.json",
        "--runtime-root",
        "/state/session",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--project-source",
        "/workspace/project",
    ]
    monkeypatch.setattr(sys, "argv", values)
    arguments = serve_demo._arguments()
    assert arguments.host == "0.0.0.0"
    assert arguments.port == 8000
    assert arguments.project_source == Path("/workspace/project")


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_project_source_must_be_an_existing_directory_without_deleting_it(
    tmp_path: Path,
    kind: str,
) -> None:
    source = tmp_path / "project-source"
    if kind == "file":
        source.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="演示项目源必须是现有目录"):
        serve_demo._create_fixture(tmp_path / "runtime", source)

    assert not (tmp_path / "runtime" / "fixture").exists()
    if kind == "file":
        assert source.read_text(encoding="utf-8") == "keep"


def test_fixture_is_copied_from_the_explicit_project_source(tmp_path: Path) -> None:
    source = tmp_path / "project-source"
    source.mkdir()
    marker = source / "mounted-project.txt"
    marker.write_text("source-only", encoding="utf-8")

    fixture, _ = serve_demo._create_fixture(tmp_path / "runtime", source)

    assert (fixture / marker.name).read_text(encoding="utf-8") == "source-only"
    assert marker.read_text(encoding="utf-8") == "source-only"


def test_explicit_runtime_parent_can_be_reused_across_starts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_parent = tmp_path / "state"
    ready_file = runtime_parent / "ready.json"
    sessions: list[Path] = []

    async def fake_serve(
        runtime_root: Path,
        _ready_file: Path,
        _max_seconds: float,
        **_options: object,
    ) -> int:
        sessions.append(runtime_root)
        return 0

    monkeypatch.setattr(serve_demo, "_serve", fake_serve)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "serve_demo.py",
            "--ready-file",
            str(ready_file),
            "--runtime-root",
            str(runtime_parent),
        ],
    )
    assert serve_demo.main() == 0
    assert serve_demo.main() == 0
    assert len(set(sessions)) == 2
    assert all(path.parent == runtime_parent for path in sessions)
    assert set(runtime_parent.glob("session-*")) == set(sessions)


def test_github_ci_runs_all_delivery_gates_on_push_and_pull_request() -> None:
    workflow = _yaml(".github/workflows/ci.yml")
    assert set(workflow["on"]) == {"push", "pull_request"}  # type: ignore[arg-type]
    jobs = workflow["jobs"]  # type: ignore[assignment]
    windows_job = jobs["windows-powershell"]
    assert windows_job["runs-on"] == "windows-latest"
    assert "if" not in windows_job
    assert windows_job.get("continue-on-error", False) is False
    setup_node_steps = [
        step
        for step in windows_job["steps"]
        if isinstance(step, dict) and step.get("uses") == "actions/setup-node@v4"
    ]
    assert len(setup_node_steps) == 1
    assert setup_node_steps[0]["with"]["node-version"] == "24"
    windows_commands = [
        step.get("run", "")
        for step in windows_job["steps"]
        if isinstance(step, dict)
    ]
    test_command = (
        ".\\.venv\\Scripts\\python.exe -m pytest "
        "tests/demo/test_mechanism_demo.py -q"
    )
    assert test_command in windows_commands
    test_step = next(
        step
        for step in windows_job["steps"]
        if isinstance(step, dict) and step.get("run") == test_command
    )
    assert "if" not in test_step
    assert test_step.get("continue-on-error", False) is False
    commands = [
        step.get("run", "")
        for job in jobs.values()
        for step in job.get("steps", [])
        if isinstance(step, dict)
    ]
    assert "make test" in commands
    assert "python3 scripts/secret_scan.py" in commands
    assert "docker build --tag coding-agent-harness:ci ." in commands
    assert (ROOT / "scripts" / "secret_scan.py").is_file()


def test_github_docker_job_forces_public_ip_compose_render() -> None:
    workflow = _yaml(".github/workflows/ci.yml")
    docker_steps = workflow["jobs"]["docker-build"]["steps"]  # type: ignore[index]
    compose_step = next(
        step
        for step in docker_steps
        if isinstance(step, dict) and "config --format json" in step.get("run", "")
    )
    assert compose_step["env"] == {
        "HARNESS_PUBLIC_HOST": "47.76.86.198",
        "HARNESS_PUBLIC_ORIGIN": "http://47.76.86.198",
    }
    assert compose_step["run"] == (
        "docker compose -f compose.yaml -f deploy/compose.public-ip.yaml "
        "config --format json"
    )


def test_gitlab_has_exact_unit_test_job() -> None:
    pipeline = _yaml(".gitlab-ci.yml")
    assert "unit-test" in pipeline
    script = pipeline["unit-test"]["script"]  # type: ignore[index]
    assert "make test-unit" in script


def test_readme_documents_real_mvp_commands_and_limits() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in (
        "项目简介",
        "核心机制",
        "安装",
        "源码运行",
        "WebUI",
        "Mock 演示",
        "一键验证",
        "Docker 与 Compose",
        "目录结构",
        "安全边界",
        "Provider 与凭据状态",
        "已知限制",
        "下一步",
    ):
        assert f"## {heading}" in readme
    for command in ("make test", "make test-unit", "make test-e2e", "make demo"):
        assert command in readme
    assert "真实 DeepSeek/Qwen 调用尚未实现" in readme
    assert "公网部署尚未验收" in readme
    docker_runs = [line for line in readme.splitlines() if line.startswith("docker run ")]
    assert any(
        ":/workspace/project:ro" in line and ":/state" in line
        for line in docker_runs
    )


def test_delivery_docs_and_env_use_safe_placeholders() -> None:
    security = (ROOT / "docs/SECURITY.md").read_text(encoding="utf-8")
    deployment = (ROOT / "docs/DEPLOYMENT.md").read_text(encoding="utf-8")
    demo = (ROOT / "docs/DEMO.md").read_text(encoding="utf-8")
    environment = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert all(term in security for term in ("state_root", "同一 UID", "不确定副作用"))
    assert all(term in deployment for term in ("只读", "localhost", "公网部署尚未验收"))
    deployment_runs = [
        line for line in deployment.splitlines() if line.startswith("docker run ")
    ]
    assert any(
        ":/workspace/project:ro" in line and ":/state" in line
        for line in deployment_runs
    )
    assert all(term in demo for term in ("Scripted Mock", "make demo", "不访问网络"))
    assert "HARNESS_LLM_PROVIDER=mock" in environment
    assert "HARNESS_LLM_API_KEY=<" in environment
