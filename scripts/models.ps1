param(
    [Parameter(Mandatory = $false)]
    [string]$ModelId,
    [switch]$Defaults,
    [switch]$IncludeReconstruction
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
$portableRoot = $root.Replace("\", "/")
$wslRoot = (wsl.exe -d Ubuntu-24.04 -- wslpath -a $portableRoot).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Ubuntu-24.04 is not ready. Run scripts\setup-wsl.ps1 first."
}

if ($Defaults) {
    $extra = if ($IncludeReconstruction) { "--include-reconstruction" } else { "" }
    wsl.exe -d Ubuntu-24.04 -u worldstate -- bash -lc "export UV_PROJECT_ENVIRONMENT=/opt/worldstate/venv UV_PYTHON_INSTALL_DIR=/opt/worldstate/python UV_CACHE_DIR=/var/cache/worldstate-uv WORLDSTATE_DATA_ROOT='$wslRoot/.worldstate'; cd '$wslRoot' && uv run worldstate models install-defaults $extra"
}
elseif ($ModelId) {
    wsl.exe -d Ubuntu-24.04 -u worldstate -- bash -lc "export UV_PROJECT_ENVIRONMENT=/opt/worldstate/venv UV_PYTHON_INSTALL_DIR=/opt/worldstate/python UV_CACHE_DIR=/var/cache/worldstate-uv WORLDSTATE_DATA_ROOT='$wslRoot/.worldstate'; cd '$wslRoot' && uv run worldstate models install '$ModelId'"
}
else {
    wsl.exe -d Ubuntu-24.04 -u worldstate -- bash -lc "export UV_PROJECT_ENVIRONMENT=/opt/worldstate/venv UV_PYTHON_INSTALL_DIR=/opt/worldstate/python UV_CACHE_DIR=/var/cache/worldstate-uv WORLDSTATE_DATA_ROOT='$wslRoot/.worldstate'; cd '$wslRoot' && uv run worldstate models list"
}
if ($LASTEXITCODE -ne 0) {
    throw "Model operation failed with exit code $LASTEXITCODE."
}
