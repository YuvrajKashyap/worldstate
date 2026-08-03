$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    uv run worldstate doctor
    if ($LASTEXITCODE -ne 0) {
        throw "WorldState diagnostics reported a blocking issue."
    }
}
finally {
    Pop-Location
}
