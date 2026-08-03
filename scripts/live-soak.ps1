param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_-]{32,128}$')]
    [string]$Token,
    [ValidateRange(60, 7200)]
    [int]$DurationSeconds = 1800,
    [ValidateRange(1, 120)]
    [double]$TargetFps = 60,
    [string]$ReportPath = '.worldstate\benchmarks\dynamic-e2e-soak-final-repo-30m.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
$resolvedReport = [System.IO.Path]::GetFullPath((Join-Path $root $ReportPath))
if (-not $resolvedReport.StartsWith(
        $root + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    throw 'The soak report must stay inside the WorldState repository.'
}

$portableRoot = $root.Replace('\', '/')
$portableReport = $resolvedReport.Replace('\', '/')
$wslRoot = (wsl.exe -d Ubuntu-24.04 -- wslpath -a $portableRoot).Trim()
$wslReport = (wsl.exe -d Ubuntu-24.04 -- wslpath -a $portableReport).Trim()
if (-not $wslRoot -or -not $wslReport) {
    throw 'Ubuntu-24.04 is not ready. Run scripts\setup-wsl.ps1.'
}

wsl.exe -d Ubuntu-24.04 -u worldstate -- bash -lc (
    "export UV_PROJECT_ENVIRONMENT=/opt/worldstate/venv " +
    "UV_PYTHON_INSTALL_DIR=/opt/worldstate/python " +
    "UV_CACHE_DIR=/var/cache/worldstate-uv " +
    "WORLDSTATE_DATA_ROOT='$wslRoot/.worldstate' " +
    "WORLDSTATE_DATABASE_URL='sqlite:///$wslRoot/.worldstate/db/worldstate.sqlite3'; " +
    "cd '$wslRoot' && uv run python scripts/live-soak.py " +
    "--token '$Token' --duration-seconds $DurationSeconds " +
    "--target-fps $TargetFps --output '$wslReport'"
)
if ($LASTEXITCODE -ne 0) {
    throw "WorldState live soak failed with exit code $LASTEXITCODE."
}
