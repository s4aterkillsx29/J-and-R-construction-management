# Wrapper — ensures shortcuts for dev repo and live install.
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$installDir = Join-Path $env:LOCALAPPDATA "J_and_R_Construction_Manager"
$ensure = Join-Path $RepoRoot "scripts\Ensure-DesktopShortcuts.ps1"
& $ensure -InstallDir $installDir -PackageDir $RepoRoot
