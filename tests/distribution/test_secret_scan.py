from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts import secret_scan


ROOT = Path(__file__).resolve().parents[2]


def test_allowlist_contains_only_test_fixtures() -> None:
    assert {path for path, _digest in secret_scan.ALLOWED_MATCHES} == {
        "tests/agent/test_orchestrator.py",
        "tests/api/test_tasks.py",
        "tests/governance/test_redaction.py",
    }


def _run_scan(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int,
    output: str = "",
) -> int:
    monkeypatch.setattr(
        secret_scan.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["git", "grep"], returncode=returncode, stdout=output
        ),
    )
    return secret_scan.main()


def test_scan_fails_closed_when_git_grep_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _run_scan(monkeypatch, returncode=2)

    assert result == 2
    assert "秘密扫描器执行失败" in capsys.readouterr().err


def test_scan_allows_git_grep_no_match_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _run_scan(monkeypatch, returncode=1)

    assert result == 0
    assert capsys.readouterr().out == ""


def test_scan_allows_known_exact_false_positive(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    result = _run_scan(
        monkeypatch, returncode=0, output="tests/agent/test_orchestrator.py"
    )

    assert result == 0
    assert capsys.readouterr().out == ""


def test_scan_reports_only_unknown_filename_and_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    filename = "unknown.txt"
    token = "sk-" + "x" * 16
    (tmp_path / filename).write_text(token, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _run_scan(monkeypatch, returncode=0, output=filename)

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out.strip() == filename
    assert token not in captured.out


def test_scan_ignores_historical_paths_that_only_contain_filename_fragments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    filename = "historical-paths.md"
    (tmp_path / filename).write_text(
        "\n".join(
            (
                ".superpowers/sdd/task-3-implementer-report.md",
                ".superpowers/sdd/task-10-report.md",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = _run_scan(monkeypatch, returncode=0, output=filename)

    assert result == 0
    assert capsys.readouterr().out == ""


def test_git_pattern_is_compatible_with_git_grep() -> None:
    result = subprocess.run(
        ["git", "grep", "-I", "-l", "-E", secret_scan.GIT_PATTERN, "--", "."],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode in {0, 1}


def test_git_pattern_does_not_match_archive_or_delivery_filename_fragments() -> None:
    result = subprocess.run(
        [
            "git",
            "grep",
            "-I",
            "-l",
            "-E",
            secret_scan.GIT_PATTERN,
            "--",
            "docs/archive/plans/2026-08-14-co-learning-workbench-and-docs.md",
            "docs/archive/plans/2026-08-14-documentation-refresh.md",
            "tests/distribution/test_delivery_files.py",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
