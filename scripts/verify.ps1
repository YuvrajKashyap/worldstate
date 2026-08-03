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
    Invoke-Checked "Contract generation" {
        uv run python scripts/generate-contracts.py
        pnpm --filter @worldstate/contracts check
        git diff --exit-code -- packages/contracts
    }
    Invoke-Checked "Migration round trip" {
        uv run python scripts/verify-migrations.py
    }
    Invoke-Checked "Frontend lint" { pnpm lint }
    Invoke-Checked "Frontend types" { pnpm typecheck }
    Invoke-Checked "Frontend tests" { pnpm test }
    Invoke-Checked "Frontend production build" { pnpm build }
    Invoke-Checked "Python dependency audit" { uv run pip-audit --skip-editable }
    Invoke-Checked "Python license policy" {
        uv run pip-licenses --fail-on="GNU Affero General Public License;GNU General Public License"
    }
    Invoke-Checked "JavaScript dependency audit" { pnpm audit --audit-level high }

    Write-Host ""
    Write-Host "WorldState verification passed."
}
finally {
    Pop-Location
}
