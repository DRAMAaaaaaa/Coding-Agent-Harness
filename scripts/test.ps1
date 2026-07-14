param(
    [ValidateSet("Unit", "All")]
    [string]$Mode = "All"
)
$Python = (Resolve-Path ".venv\Scripts\python.exe").Path
$Npm = (Get-Command npm.cmd -ErrorAction Stop).Source
if ($Mode -eq "Unit") {
    & $Python -m pytest
    exit $LASTEXITCODE
}
& $Python -m ruff check src tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m mypy src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Npm --prefix web run lint
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Npm --prefix web run typecheck
exit $LASTEXITCODE
