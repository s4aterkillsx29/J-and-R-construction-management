# Creates desktop shortcut for dedicated host laptop daily server start.
param(
    [string]$InstallDir = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Continue"
$InstallDir = (Resolve-Path -LiteralPath $InstallDir).Path

$desktop = [Environment]::GetFolderPath("Desktop")
$startBat = Join-Path $InstallDir "START_DEDICATED_HOST_SERVER.bat"
$setupBat = Join-Path $InstallDir "SETUP_DEDICATED_HOST_LAPTOP.bat"

if (-not (Test-Path -LiteralPath $startBat)) {
    Write-Output "START_DEDICATED_HOST_SERVER.bat not found in $InstallDir"
    exit 1
}

function New-Shortcut($lnkPath, $target, $workDir, $desc) {
    try {
        $wsh = New-Object -ComObject WScript.Shell
        $lnk = $wsh.CreateShortcut($lnkPath)
        $lnk.TargetPath = $target
        $lnk.WorkingDirectory = $workDir
        $lnk.Description = $desc
        $icon = Join-Path $InstallDir "assets\jrc_manager_app.ico"
        if (Test-Path -LiteralPath $icon) { $lnk.IconLocation = "$icon,0" }
        $lnk.Save()
        Write-Output "Created: $lnkPath"
    } catch {
        Write-Output "Could not create: $lnkPath"
    }
}

New-Shortcut `
    (Join-Path $desktop "START JRC Host Server (24-7).lnk") `
    $startBat `
    $InstallDir `
    "J and R Construction - local LAN host. Keep window open."

if (Test-Path -LiteralPath $setupBat) {
    New-Shortcut `
        (Join-Path $desktop "SETUP JRC Dedicated Host (once).lnk") `
        $setupBat `
        $InstallDir `
        "One-time setup for dedicated 24/7 host laptop."
}

Write-Output "Dedicated host shortcuts ready on Desktop."
