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
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv is required. Install it from https://docs.astral.sh/uv/."
    }
    if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
        throw "pnpm 10 is required. Run: corepack enable"
    }

    Invoke-Checked "Install Python 3.12" { uv python install 3.12 }
    Invoke-Checked "Synchronize Python workspace" {
        uv sync --all-packages --group dev
    }
    Invoke-Checked "Install frontend dependencies" { pnpm install }

    Write-Host ""
    Write-Host "WorldState foundation is ready."
    Write-Host "No model checkpoints were downloaded."
}
finally {
    Pop-Location
}
