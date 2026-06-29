# Sync ONE unified J&R business workspace (Dropbox).
# Merges legacy dropbox-records into workspace if needed; deploys 00_START_HERE.
param(
    [string]$WorkspaceRoot = "",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Templates = Join-Path $RepoRoot "scripts\templates\dropbox_workspace"
$WorkspaceName = "JRC_COMPLETE_BUSINESS_FOLDER_2026-06-22"

function Resolve-WorkspaceRoot {
    param([string]$Override)
    if ($Override -and (Test-Path -LiteralPath $Override)) { return $Override }
    foreach ($p in @(
        $env:JRC_WORKSPACE_ROOT,
        $env:JRC_DROPBOX_BUSINESS_ROOT,
        $env:JRC_DROPBOX_RECORDS,
        "C:\Users\enrag\Dropbox\All Files\$WorkspaceName\$WorkspaceName",
        (Join-Path $env:USERPROFILE "Dropbox\All Files\$WorkspaceName\$WorkspaceName"),
        "c:\Users\enrag\projects\JRC-Construction-Office\dropbox-records"
    )) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    return $null
}

function Copy-TemplateTree {
    param([string]$Src, [string]$Dest)
    Get-ChildItem -LiteralPath $Src -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($Src.Length).TrimStart('\')
        $target = Join-Path $Dest $rel
        if (-not $WhatIf) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
        Write-Host "  -> 00_START_HERE\$rel"
    }
}

$root = Resolve-WorkspaceRoot -Override $WorkspaceRoot
if (-not $root) {
    Write-Error "Unified workspace not found. Install Dropbox Desktop and sync $WorkspaceName"
}

Write-Host "=== Sync-JRCBusinessFolders (ONE workspace) ===" -ForegroundColor Cyan
Write-Host "Workspace: $root"

# Python unify + merge legacy paths
$py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
Push-Location $RepoRoot
& $py -m app.jrc_workspace --ensure
Pop-Location

$startHere = Join-Path $root "00_START_HERE"
if (-not $WhatIf) { New-Item -ItemType Directory -Force -Path $startHere | Out-Null }
Write-Host "Deploying phone Cursor files..."
Copy-TemplateTree -Src $Templates -Dest $startHere

if (-not $WhatIf) {
    @"
J & R CONSTRUCTION — SINGLE BUSINESS WORKSPACE
Workspace: $root
Name: $WorkspaceName

Phone Cursor: open THIS folder only (not GitHub).
Verify: 00_START_HERE\JRC-315_LILY_FENCE_QUOTE_CURRENT.txt (`$13,890)
"@ | Set-Content -Path (Join-Path $root "JRC_WORKSPACE.txt") -Encoding UTF8
}

Write-Host ""
Write-Host "ONE workspace ready." -ForegroundColor Green
Write-Host "Phone: open $WorkspaceName inner folder in Cursor"
Write-Host "Desktop: Office Records Sync uses the same folder"

$refresh = Join-Path $RepoRoot "scripts\Refresh-ReadableBusinessReports.ps1"
if ((Test-Path $refresh) -and -not $WhatIf) {
    Write-Host ""
    & powershell -NoProfile -ExecutionPolicy Bypass -File $refresh -WorkspaceRoot $root
}
