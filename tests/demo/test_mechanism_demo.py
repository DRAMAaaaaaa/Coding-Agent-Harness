from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_LINES = [
    "PASS governance_guard",
    "PASS feedback_changed_action",
    "PASS deterministic_stop",
]


def test_demo_reports_real_mechanism_evidence() -> None:
    from coding_agent_harness.demo import run_mechanism_demo

    report = asyncio.run(run_mechanism_demo())

    assert report.governance_guard.blocked_event
    assert report.governance_guard.tool_calls == 0
    assert report.governance_guard.final_state == "WAITING_USER"
    assert report.feedback_changed_action.feedback_in_second_request
    assert report.feedback_changed_action.actions == (
        "run_verification",
        "apply_patch",
        "run_verification",
        "git_diff",
    )
    assert report.feedback_changed_action.final_state == "WAITING_FINAL_REVIEW"
    assert report.deterministic_stop.same_fingerprint_count == 2
    assert report.deterministic_stop.final_state == "WAITING_USER"


def test_demo_cli_is_deterministic_and_prints_only_pass_lines() -> None:
    command = [sys.executable, "scripts/mechanism_demo.py"]
    first = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    second = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stdout.splitlines() == EXPECTED_LINES
    assert first.stderr == second.stderr == ""


def test_test_script_fails_closed_when_python_environment_is_missing(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "scripts" / "test.ps1"),
            "-Mode",
            "Unit",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "ERROR: Python environment missing; create .venv and install project dependencies."
        in result.stdout
    )


def test_test_script_fails_closed_when_web_dependencies_are_missing(tmp_path: Path) -> None:
    scripts = tmp_path / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "python.exe").touch()
    (tmp_path / "web").mkdir()

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "scripts" / "test.ps1"),
            "-Mode",
            "Unit",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ERROR: Web dependencies missing; run npm --prefix web ci." in result.stdout


def test_test_script_fails_closed_when_npm_is_missing(tmp_path: Path) -> None:
    scripts = tmp_path / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "python.exe").touch()
    (tmp_path / "web" / "node_modules").mkdir(parents=True)
    environment = os.environ.copy()
    system_root = Path(environment.get("SYSTEMROOT", r"C:\Windows"))
    environment["PATH"] = os.pathsep.join(
        [
            str(system_root / "System32"),
            str(system_root / "System32" / "WindowsPowerShell" / "v1.0"),
        ]
    )

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "scripts" / "test.ps1"),
            "-Mode",
            "Unit",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "ERROR: npm command missing; install the required Node.js 24 runtime."
        in result.stdout
    )
