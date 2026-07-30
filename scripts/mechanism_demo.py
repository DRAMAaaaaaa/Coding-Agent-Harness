from __future__ import annotations

import asyncio
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coding_agent_harness.demo import run_mechanism_demo  # noqa: E402


def main() -> int:
    report = asyncio.run(run_mechanism_demo())
    if not report.passed:
        return 1
    print("PASS governance_guard")
    print("PASS feedback_changed_action")
    print("PASS deterministic_stop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
