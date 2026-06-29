# JRC v7.9.0 — Full phase live update (backup, Desktop install, sync, verify)
$ErrorActionPreference = "Stop"
$Src = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"

function Get-DesktopPath {
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        return [Environment]::GetFolderPath("Desktop")
    } catch {
        foreach ($sub in @("OneDrive\Desktop", "Desktop")) {
            $p = Join-Path $env:USERPROFILE $sub
            if (Test-Path -LiteralPath $p) { return $p }
        }
        return Join-Path $env:USERPROFILE "Desktop"
    }
}

$Desktop = Get-DesktopPath
$OwnerInstall = Join-Path $Desktop "J and R Construction Manager"
$AppDataInstall = Join-Path $env:LOCALAPPDATA "J_and_R_Construction_Manager"
$OfficeBackup = "c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records\07_JRC_MANAGER_PROGRAM_FILES\backups"
$DropboxRecords = "c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records"
$env:JRC_WORKSPACE_ROOT = ""
$env:JRC_DROPBOX_RECORDS = $DropboxRecords

New-Item -ItemType Directory -Force -Path $OfficeBackup | Out-Null

Write-Host "=== JRC 7.9.0 Phase Live Update ===" -ForegroundColor Cyan
Write-Host "Source: $Src"

# Backup live DB from AppData (richest data)
if (Test-Path "$AppDataInstall\data\jr_business.db") {
    $bak = Join-Path $OfficeBackup "jr_business_AppData_$Stamp.db"
    Copy-Item "$AppDataInstall\data\jr_business.db" $bak -Force
    Write-Host "Backed up AppData DB -> $bak"
}

# Create Desktop owner install if missing
if (-not (Test-Path $OwnerInstall)) {
    Write-Host "Creating Desktop owner install..."
    New-Item -ItemType Directory -Force -Path $OwnerInstall | Out-Null
    robocopy $Src $OwnerInstall /E /XD .git .venv __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    if (Test-Path "$AppDataInstall\data") {
        New-Item -ItemType Directory -Force -Path "$OwnerInstall\data" | Out-Null
        Copy-Item "$AppDataInstall\data\*" "$OwnerInstall\data\" -Recurse -Force
        Write-Host "Copied AppData data -> Desktop install"
    }
}

# Ensure venv on source (non-fatal — live update can still run with system python)
if (Test-Path (Join-Path $Src "setup_runtime_env.bat")) {
    Push-Location $Src
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        cmd /c "setup_runtime_env.bat" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Note: setup_runtime_env.bat exit $LASTEXITCODE (continuing with existing venv or system python)" -ForegroundColor Yellow
        }
    } finally {
        $ErrorActionPreference = $prevEap
        Pop-Location
    }
}

$Py = Join-Path $Src ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

$env:JRC_DROPBOX_RECORDS = $DropboxRecords

Write-Host "Running live full update..."
Push-Location $Src
& $Py -m app.live_full_update
$LiveCode = $LASTEXITCODE

Write-Host "Running phase verification..."
& $Py -m app.run_phase_verification $Src
$PhaseCode = $LASTEXITCODE

# Sync to AppData too (direct copy — SYNC_LIVE_INSTALL.bat has interactive pause)
foreach ($dest in @($AppDataInstall, $OwnerInstall)) {
    if (-not (Test-Path $dest)) { continue }
    Write-Host "Syncing to: $dest"
    $appDst = Join-Path $dest "app"
    New-Item -ItemType Directory -Force -Path $appDst | Out-Null
    Copy-Item (Join-Path $Src "app\*.py") $appDst -Force
    foreach ($f in @("VERSION.txt","requirements.txt","ensure_venv.bat","setup_runtime_env.bat","Launch-JRC-Manager.bat","SYNC_LIVE_INSTALL.bat","LIVE_FULL_UPDATE.vbs")) {
        $fp = Join-Path $Src $f
        if (Test-Path $fp) { Copy-Item $fp $dest -Force }
    }
    if (Test-Path (Join-Path $Src "scripts")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $dest "scripts") | Out-Null
        Copy-Item (Join-Path $Src "scripts\*") (Join-Path $dest "scripts") -Recurse -Force
    }
    if (Test-Path (Join-Path $Src "assets")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $dest "assets") | Out-Null
        Copy-Item (Join-Path $Src "assets\*") (Join-Path $dest "assets") -Recurse -Force
    }
}

# Desktop shortcuts
if (Test-Path (Join-Path $Src "scripts\Ensure-DesktopShortcuts.ps1")) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Src "scripts\Ensure-DesktopShortcuts.ps1") -InstallDir $OwnerInstall 2>$null
}

# Phone Cursor + Dropbox workspace (00_START_HERE files)
foreach ($script in @("Sync-JRCBusinessFolders.ps1", "Log-WorkspaceSync.ps1")) {
    $sp = Join-Path $Src "scripts\$script"
    if (Test-Path $sp) {
        Write-Host "Running $script ..."
        & powershell -NoProfile -ExecutionPolicy Bypass -File $sp 2>&1 | ForEach-Object { Write-Host $_ }
    }
}

Pop-Location

Write-Host ""
Write-Host "Live update complete." -ForegroundColor Green
Write-Host "  Desktop install: $OwnerInstall"
Write-Host "  AppData install: $AppDataInstall"
Write-Host "  Reports: $Src\LIVE_UPDATE_REPORT.txt , $Src\PHASE_VERIFICATION_REPORT.txt"
Write-Host "  live_full_update exit: $LiveCode | phase verify exit: $PhaseCode"

exit ([Math]::Max($LiveCode, $PhaseCode))
