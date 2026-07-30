$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    uv run python -m worldstate_api
    if ($LASTEXITCODE -ne 0) {
        throw "WorldState API exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
