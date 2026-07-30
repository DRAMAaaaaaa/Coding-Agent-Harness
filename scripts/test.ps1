param(
    [ValidateSet("Unit", "E2E", "All", "Demo")]
    [string]$Mode = "All"
)

function Stop-WithDiagnostic([string]$Message) {
    Write-Output $Message
    exit 2
}

$PythonCandidate = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonCandidate -PathType Leaf)) {
    Stop-WithDiagnostic "ERROR: Python environment missing; create .venv and install project dependencies."
}
$Python = (Resolve-Path -LiteralPath $PythonCandidate).Path

if ($Mode -ne "Demo") {
    $NpmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $NpmCommand) {
        Stop-WithDiagnostic "ERROR: npm command missing; install the required Node.js 24 runtime."
    }
    $NodeModules = Join-Path (Get-Location) "web\node_modules"
    if (-not (Test-Path -LiteralPath $NodeModules -PathType Container)) {
        Stop-WithDiagnostic "ERROR: Web dependencies missing; run npm --prefix web ci."
    }
    $Npm = $NpmCommand.Source
}

function Invoke-Checked([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Mode -eq "Demo") {
    Invoke-Checked { & $Python scripts\mechanism_demo.py }
    exit 0
}

if ($Mode -eq "Unit") {
    Invoke-Checked { & $Python -m pytest }
    Invoke-Checked { & $Npm --prefix web run test -- --run }
    exit 0
}

if ($Mode -eq "E2E") {
    Invoke-Checked { & $Npm --prefix web run build }
    Invoke-Checked { & $Npm --prefix web run e2e }
    exit 0
}

Invoke-Checked { & $Python -m ruff check src tests }
Invoke-Checked { & $Python -m mypy src }
Invoke-Checked { & $Python -m pytest }
Invoke-Checked { & $Npm --prefix web run lint }
Invoke-Checked { & $Npm --prefix web run typecheck }
Invoke-Checked { & $Npm --prefix web run test -- --run }
Invoke-Checked { & $Npm --prefix web run build }
Invoke-Checked { & $Npm --prefix web run e2e }
exit 0
