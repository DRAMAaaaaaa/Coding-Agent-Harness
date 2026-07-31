from __future__ import annotations

from pathlib import Path
import sys

import pytest
import yaml

from scripts import serve_demo


ROOT = Path(__file__).resolve().parents[2]


def _yaml(path: str) -> dict[str, object]:
    loaded = yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
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


def test_docker_runtime_is_non_root_and_exposes_only_web_port() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.count(" AS ") >= 2
    assert "USER harness" in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert "EXPOSE 8000 8080" not in dockerfile
    assert "scripts/serve_demo.py" in dockerfile
    assert '"--project-source", "/workspace/project"' in dockerfile
    assert "COPY examples/" not in dockerfile


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
    assert any("harness-state" in mount for mount in volumes)


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
    workflow_path = ROOT / ".github/workflows/ci.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = _yaml(".github/workflows/ci.yml")
    assert set(workflow["on"]) == {"push", "pull_request"}  # type: ignore[arg-type]
    jobs = workflow["jobs"]  # type: ignore[assignment]
    commands = "\n".join(
        step.get("run", "")
        for job in jobs.values()
        for step in job.get("steps", [])
        if isinstance(step, dict)
    )
    assert "make test" in commands
    assert "git grep" in commands and "-l" in commands
    assert "git grep -I -l" in commands and "git grep -n" not in commands
    assert ":!tests/" not in commands
    assert "hashlib.sha256" in commands
    assert "unexpected_files" in commands
    assert "docker build" in commands
    assert "HARNESS_LLM_API_KEY" not in workflow_text


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
