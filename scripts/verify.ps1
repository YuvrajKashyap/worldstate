$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host "==> $Name"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    Invoke-Checked "Python format" { uv run ruff format --check . }
    Invoke-Checked "Python lint" { uv run ruff check . }
    Invoke-Checked "Python types" { uv run pyright }
    Invoke-Checked "Python tests" { uv run pytest }
    Invoke-Checked "Frontend lint" { pnpm lint }
    Invoke-Checked "Frontend types" { pnpm typecheck }
    Invoke-Checked "Frontend tests" { pnpm test }
    Invoke-Checked "Frontend production build" { pnpm build }

    Write-Host ""
    Write-Host "WorldState verification passed."
}
finally {
    Pop-Location
}
