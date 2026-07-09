# Sync J&R business folders for phone Cursor + Dropbox workspace.
# Deploys 00_START_HERE files and links dropbox-records into business root.
param(
    [string]$BusinessRoot = "",
    [string]$DropboxRecords = "",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Templates = Join-Path $RepoRoot "scripts\templates\dropbox_workspace"

function Resolve-BusinessRoot {
    param([string]$Override)
    if ($Override -and (Test-Path -LiteralPath $Override)) { return $Override }
    $candidates = @(
        $env:JRC_DROPBOX_BUSINESS_ROOT,
        "C:\Users\enrag\Dropbox\All Files\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22",
        (Join-Path $env:USERPROFILE "Dropbox\All Files\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"),
        (Join-Path $env:USERPROFILE "Dropbox\dropbox-records"),
        "c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records"
    ) | Where-Object { $_ }
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

function Resolve-DropboxRecords {
    param([string]$Override)
    if ($Override -and (Test-Path -LiteralPath $Override)) { return $Override }
    $candidates = @(
        $env:JRC_DROPBOX_RECORDS,
        "c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records",
        (Join-Path $env:USERPROFILE "Dropbox\dropbox-records")
    ) | Where-Object { $_ }
    foreach ($p in $candidates) {
        $reg = Join-Path $p "08_Admin_Standards\JRC_JOB_RELATION_REGISTER.csv"
        if (Test-Path -LiteralPath $reg) { return $p }
    }
    return $null
}

function Copy-TemplateTree {
    param([string]$Src, [string]$Dest)
    if (-not (Test-Path -LiteralPath $Src)) {
        Write-Warning "Templates missing: $Src"
        return
    }
    Get-ChildItem -LiteralPath $Src -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($Src.Length).TrimStart('\')
        $target = Join-Path $Dest $rel
        $targetDir = Split-Path -Parent $target
        if (-not $WhatIf) {
            New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
        Write-Host "  -> $rel"
    }
}

$root = Resolve-BusinessRoot -Override $BusinessRoot
if (-not $root) {
    Write-Error @"
Dropbox business root not found.
Install Dropbox Desktop, wait for sync, or pass -BusinessRoot 'C:\Users\...\JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22\...'
"@
}

$records = Resolve-DropboxRecords -Override $DropboxRecords
$startHere = Join-Path $root "00_START_HERE"
$readable = Join-Path $startHere "READABLE"

Write-Host "=== Sync-JRCBusinessFolders ===" -ForegroundColor Cyan
Write-Host "Business root: $root"
Write-Host "dropbox-records: $(if ($records) { $records } else { '(not found — templates only)' })"
Write-Host ""

if (-not $WhatIf) {
    New-Item -ItemType Directory -Force -Path $startHere, $readable | Out-Null
}

if ($records) {
    Write-Host "Office dropbox-records found — skipping template deploy (live records protected)."
} else {
    Write-Host "Deploying phone Cursor workspace templates to 00_START_HERE..."
    Copy-TemplateTree -Src $Templates -Dest $startHere
}

# OPEN guide at Dropbox All Files level (parent of business root when applicable)
$allFilesGuide = Join-Path (Split-Path -Parent $root) "OPEN_JRC_BUSINESS_HERE.txt"
if (-not $WhatIf) {
    @"
Open this folder in Cursor on your PHONE for business work (quotes, logs, CSVs).

INNER FOLDER TO OPEN:
  $($root)

VERIFY: open 00_START_HERE\JRC-315_LILY_FENCE_QUOTE_CURRENT.txt
You should see the `$10,440 Lily Sassafras fence quote (251 LF, 65% deposit).

Do NOT use GitHub J-and-R-construction-management for business files.
"@ | Set-Content -Path $allFilesGuide -Encoding UTF8
}
Write-Host "  -> OPEN_JRC_BUSINESS_HERE.txt (parent folder)"

if ($records -and $records -ne $root) {
    $linkPath = Join-Path $root "dropbox-records"
    if (-not (Test-Path -LiteralPath $linkPath)) {
        if (-not $WhatIf) {
            try {
                cmd /c mklink /J "`"$linkPath`"" "`"$records`"" | Out-Null
                Write-Host "Linked dropbox-records junction -> $records"
            } catch {
                Write-Warning "Could not create junction; copy path in PHONE_CURSOR_DROPBOX_WORKSPACE.txt"
            }
        }
    }
}

Write-Host ""
Write-Host "Phone verify prompt:" -ForegroundColor Green
Write-Host '  Ask phone Cursor: "Open 00_START_HERE/JRC-315_LILY_FENCE_QUOTE_CURRENT.txt"'
Write-Host "  Expect: `$10,440 Lily Sassafras fence quote (251 LF)"
Write-Host ""
Write-Host "Next: run scripts\Refresh-ReadableBusinessReports.ps1" -ForegroundColor Yellow
