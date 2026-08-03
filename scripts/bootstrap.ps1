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
        uv sync --all-packages --group dev --locked
    }
    Invoke-Checked "Install frontend dependencies" { pnpm install }

    Write-Host ""
    Write-Host "WorldState CPU/replay environment is ready."
    Write-Host "No model checkpoints were downloaded."
    Write-Host "Run .\scripts\doctor.ps1, then use setup-wsl.ps1 for CUDA."
}
finally {
    Pop-Location
}
