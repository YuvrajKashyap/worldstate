$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    pnpm build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed."
    }
    $portableRoot = $root.Replace("\", "/")
    $wslRoot = (wsl.exe -d Ubuntu-24.04 -- wslpath -a $portableRoot).Trim()
    if (-not $wslRoot) {
        throw "Ubuntu-24.04 is not ready. Run scripts\setup-wsl.ps1."
    }
    wsl.exe -d Ubuntu-24.04 -u worldstate -- bash "$wslRoot/scripts/run-worldstate.sh" "$wslRoot"
    if ($LASTEXITCODE -ne 0) {
        throw "WorldState exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
