from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import sys


PATTERN = (
    r"(?:sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|"
    r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY)"
)
GIT_PATTERN = (
    r"(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|"
    r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY)"
)
ALLOWED_MATCHES = {
    (
        "tests/agent/test_orchestrator.py",
        "573da6fd127efb9e9d07de2d30783788373e365fa5abe86c541064f326aebfad",
    ),
    (
        "tests/api/test_tasks.py",
        "0d771ce522997a102ba556a91cf3c1ba66a05c1fa33871f8e59669204e541e8d",
    ),
    (
        "tests/governance/test_redaction.py",
        "573da6fd127efb9e9d07de2d30783788373e365fa5abe86c541064f326aebfad",
    ),
}


def main() -> int:
    result = subprocess.run(
        [
            "git",
            "grep",
            "-I",
            "-l",
            "-E",
            GIT_PATTERN,
            "--",
            ".",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode == 1:
        return 0
    if result.returncode != 0:
        print("秘密扫描器执行失败", file=sys.stderr)
        return result.returncode

    unexpected_files: set[str] = set()
    expression = re.compile(PATTERN)
    for filename in result.stdout.splitlines():
        path = Path(filename)
        for match in expression.finditer(path.read_text(encoding="utf-8", errors="replace")):
            digest = hashlib.sha256(match.group(0).encode("utf-8")).hexdigest()
            if (path.as_posix(), digest) not in ALLOWED_MATCHES:
                unexpected_files.add(path.as_posix())
    if unexpected_files:
        print("\n".join(sorted(unexpected_files)))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
