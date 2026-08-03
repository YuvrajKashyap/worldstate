$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$distribution = "Ubuntu-24.04"
$installed = @(wsl.exe --list --quiet) -replace "`0", ""
if ($installed -notcontains $distribution) {
    Write-Host "Installing $distribution. Windows may request administrator approval and a reboot."
    wsl.exe --install --distribution $distribution --no-launch
    if ($LASTEXITCODE -ne 0) {
        throw "WSL installation failed with exit code $LASTEXITCODE."
    }
    Write-Host "Restart Windows if requested, then rerun this script."
    exit 0
}

$root = Split-Path -Parent $PSScriptRoot
$portableRoot = $root.Replace("\", "/")
$wslRoot = (wsl.exe -d $distribution -- wslpath -a $portableRoot).Trim()
if (-not $wslRoot) {
    throw "Could not translate the repository path into WSL."
}
wsl.exe -d $distribution -u root -- bash "$wslRoot/scripts/setup-wsl.sh" "$wslRoot"
if ($LASTEXITCODE -ne 0) {
    throw "WSL bootstrap failed with exit code $LASTEXITCODE."
}
wsl.exe --manage $distribution --set-default-user worldstate
if ($LASTEXITCODE -ne 0) {
    throw "Could not set the unprivileged WorldState runtime user."
}
