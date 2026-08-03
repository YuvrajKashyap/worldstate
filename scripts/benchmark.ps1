param(
    [ValidateRange(10, 10000)]
    [int]$Frames = 240
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    uv run worldstate benchmark --frames $Frames
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
