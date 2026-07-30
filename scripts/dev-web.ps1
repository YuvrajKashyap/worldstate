$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    pnpm dev:web
    if ($LASTEXITCODE -ne 0) {
        throw "WorldState web app exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
