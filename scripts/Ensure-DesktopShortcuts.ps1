# Ensures desktop + Start Menu shortcuts — program launcher + installer only (v7.6.1).
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "J_and_R_Construction_Manager"),
    [string]$PackageDir = "",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

function Write-JrcLog($msg) {
    if (-not $Quiet) { Write-Output $msg }
}

if (-not (Test-Path -LiteralPath $InstallDir)) {
    $resolved = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Resolve-InstallDir.ps1") -Hint $InstallDir -Profile "OwnerMaster" 2>$null
    if ($resolved -and (Test-Path -LiteralPath $resolved)) { $InstallDir = $resolved.Trim() }
}
if (-not (Test-Path -LiteralPath $InstallDir)) {
    Write-JrcLog "Install folder not found: $InstallDir"
    exit 0
}

$sourceFile = Join-Path $InstallDir "INSTALLER_SOURCE.txt"
if (-not $PackageDir -and (Test-Path -LiteralPath $sourceFile)) {
    $PackageDir = (Get-Content -LiteralPath $sourceFile -Raw).Trim()
}

$desktop = [Environment]::GetFolderPath("Desktop")
$publicDesktop = Join-Path $env:Public "Desktop"
$startMenu = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\J and R Construction"
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null

function Ensure-Icons($root) {
    $gen = Join-Path $root "scripts\generate_shortcut_icons.py"
    $icon = Join-Path $root "assets\jrc_manager_app.ico"
    if ((Test-Path -LiteralPath $icon) -or -not (Test-Path -LiteralPath $gen)) { return }
    $py = Join-Path $root ".venv\Scripts\python.exe"
    try {
        if (Test-Path -LiteralPath $py) { & $py $gen | Out-Null } else { py -3 $gen | Out-Null }
        Write-JrcLog "Generated shortcut icons."
    } catch {
        Write-JrcLog "Icon generation skipped: $($_.Exception.Message)"
    }
}

function New-JrcShortcut($path, $target, $workDir, $icon, $desc) {
    if (-not (Test-Path -LiteralPath $target)) { return }
    try {
        $parent = Split-Path -Parent $path
        if ($parent -and -not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        $wsh = New-Object -ComObject WScript.Shell
        $lnk = $wsh.CreateShortcut($path)
        $lnk.TargetPath = $target
        $lnk.WorkingDirectory = $workDir
        if ($desc) { $lnk.Description = $desc }
        if (Test-Path -LiteralPath $icon) { $lnk.IconLocation = "$icon,0" }
        $lnk.Save()
        Write-JrcLog "Shortcut: $path"
    } catch {
        Write-JrcLog "Skipped shortcut: $path"
    }
}

function Remove-LegacyShortcuts($locations) {
    $legacy = @(
        "JRC System Check.lnk",
        "JRC Shared Host.lnk",
        "JRC Local Program Folder.lnk",
        "JRC Program Folder.lnk",
        "J and R Construction Manager - Network Server.lnk",
        "J and R Construction Manager - Open Browser.lnk",
        "J and R Construction Manager - Best Host Server.lnk",
        "J and R Construction Manager - Public Host Mode.lnk",
        "J and R Construction Manager - Local LAN Host.lnk",
        "J and R Construction Manager - System Check.lnk",
        "J&R Job Manager Pro.lnk",
        "J and R Job Manager Pro.lnk"
    )
    foreach ($loc in $locations) {
        if (-not $loc -or -not (Test-Path -LiteralPath $loc)) { continue }
        foreach ($name in $legacy) {
            $p = Join-Path $loc $name
            if (Test-Path -LiteralPath $p) {
                try { Remove-Item -LiteralPath $p -Force; Write-JrcLog "Removed legacy: $p" } catch { }
            }
        }
    }
}

Ensure-Icons $InstallDir
Remove-LegacyShortcuts @($desktop, $publicDesktop, $startMenu)

$iconApp = Join-Path $InstallDir "assets\jrc_manager_app.ico"
if (-not (Test-Path -LiteralPath $iconApp)) { $iconApp = Join-Path $InstallDir "assets\j_and_r_manager_icon.ico" }
$iconInstaller = Join-Path $InstallDir "assets\jrc_installer.ico"

$managerBat = Join-Path $InstallDir "run_jr_manager_hidden.vbs"
if (-not (Test-Path -LiteralPath $managerBat)) {
    $managerBat = Join-Path $InstallDir "Launch-JRC-Manager.bat"
}

$installerVbs = Join-Path $InstallDir "!!! START INSTALL HERE.vbs"
if (-not (Test-Path -LiteralPath $installerVbs) -and $PackageDir) {
    $installerVbs = Join-Path $PackageDir "!!! START INSTALL HERE.vbs"
}

$shortcutMap = @(
    @{ Name = "J and R Construction Manager.lnk"; Target = $managerBat; Icon = $iconApp; Desc = "Open J and R Construction Manager" }
)
if (Test-Path -LiteralPath $installerVbs) {
    $shortcutMap += @{ Name = "JRC Install or Update.lnk"; Target = $installerVbs; Icon = $iconInstaller; Desc = "Install or update J and R Construction Manager" }
}

foreach ($desk in @($desktop, $publicDesktop)) {
    if (-not $desk -or -not (Test-Path -LiteralPath $desk)) { continue }
    foreach ($item in $shortcutMap) {
        $work = if ($item.Name -like "*Install*") { if ($PackageDir) { $PackageDir } else { $InstallDir } } else { $InstallDir }
        New-JrcShortcut (Join-Path $desk $item.Name) $item.Target $work $item.Icon $item.Desc
    }
}

foreach ($item in $shortcutMap) {
    $work = if ($item.Name -like "*Install*") { if ($PackageDir) { $PackageDir } else { $InstallDir } } else { $InstallDir }
    New-JrcShortcut (Join-Path $startMenu $item.Name) $item.Target $work $item.Icon $item.Desc
}

Write-JrcLog "Desktop shortcuts: program + installer only. All tools are in Admin Dashboard."
