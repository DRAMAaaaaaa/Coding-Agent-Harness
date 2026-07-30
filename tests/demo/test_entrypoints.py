from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_makefile_uses_cross_platform_direct_tools() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "powershell.exe" not in makefile
    assert '"$(PYTHON)" -m pytest' in makefile
    assert '"$(NPM)" --prefix web run test -- --run' in makefile
    assert '"$(NPM)" --prefix web run e2e' in makefile
    assert "scripts/mechanism_demo.py" in makefile
    assert "Python environment missing" in makefile
    assert "Web dependencies missing" in makefile


def test_powershell_exposes_all_four_equivalent_modes() -> None:
    script = (ROOT / "scripts" / "test.ps1").read_text(encoding="utf-8")

    assert '[ValidateSet("Unit", "E2E", "All", "Demo")]' in script
    assert "scripts\\mechanism_demo.py" in script
    assert "run e2e" in script
    assert "run test -- --run" in script
